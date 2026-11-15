import json
import logging
from datetime import timedelta

from django.contrib import messages
from django.http import HttpResponse, HttpResponseNotAllowed
from django.shortcuts import redirect
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import override
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import ListView

from core.permissions import StaffRequiredMixin

from . import line, linking
from .models import LineWebhookEvent, NotificationEvent, NotificationLog, NotificationStatus
from .services import notify, retry_failed

log = logging.getLogger(__name__)


def _help_text():
    with override("th"):
        return _("Send the 6-digit code shown on the LINE link page of the system to link your account.")


def _follow_text():
    with override("th"):
        return _("Thank you for adding us. Open the LINE link page in the system, then send the 6-digit code here.")


def _handle_event(ev):
    etype = ev.get("type")
    token = ev.get("replyToken", "")
    uid = (ev.get("source") or {}).get("userId", "")
    if etype == "message":
        msg = ev.get("message") or {}
        if msg.get("type") != "text":
            return
        try:
            user = linking.link_by_code(msg.get("text", ""), uid, reply_token=token)
        except linking.LinkRateLimited:
            return
        if user:
            entry = notify(user, NotificationEvent.LINE_LINKED)
            line.reply(token, entry.message)
        else:
            line.reply(token, _help_text())
    elif etype == "unfollow":
        linking.unlink(uid)
    elif etype == "follow":
        line.reply(token, _follow_text())


@csrf_exempt
def line_webhook(request):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    if not line.verify_signature(request.body, request.headers.get("X-Line-Signature", "")):
        return HttpResponse(status=400)
    try:
        events = json.loads(request.body or b"{}").get("events", [])
    except (ValueError, AttributeError):
        return HttpResponse(status=200)
    for ev in events if isinstance(events, list) else []:
        try:
            if isinstance(ev, dict):
                event_id = ev.get("webhookEventId")
                if event_id:
                    _, created = LineWebhookEvent.objects.get_or_create(
                        event_id=event_id, defaults={"event_type": ev.get("type", "")})
                    if not created:
                        continue
                _handle_event(ev)
        except Exception:  # noqa: BLE001
            log.exception("LINE webhook event failed")
    LineWebhookEvent.objects.filter(created_at__lt=timezone.now() - timedelta(days=7)).delete()
    return HttpResponse(status=200)


class LogListView(StaffRequiredMixin, ListView):
    model = NotificationLog
    template_name = "notifications/log_list.html"
    paginate_by = 30
    context_object_name = "logs"

    def get_queryset(self):
        qs = NotificationLog.objects.select_related("user")
        status, event = self.request.GET.get("status", ""), self.request.GET.get("event", "")
        if status in NotificationStatus.values:
            qs = qs.filter(status=status)
        if event in NotificationEvent.values:
            qs = qs.filter(event=event)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(statuses=NotificationStatus.choices, events=NotificationEvent.choices,
                   status=self.request.GET.get("status", ""), event=self.request.GET.get("event", ""))
        q = self.request.GET.copy()
        q.pop("page", None)
        ctx["query"] = q.urlencode()
        return ctx

    def post(self, request, *args, **kwargs):
        results = retry_failed()
        sent = sum(1 for r in results if r and r.status == NotificationStatus.SENT)
        messages.info(request, _("Retried %(n)d failed notifications, %(ok)d sent.") % {"n": len(results), "ok": sent})
        return redirect("notifications:log_list")
