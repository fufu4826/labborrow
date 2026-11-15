"""Notification queue + LINE push (docs/05-line.md).

`notify(user, event, context, related=None)` and `notify_staff(...)` are safe to call inside a
transaction: the log row is written now, the HTTP call happens after commit. Without a channel access
token (dev/test) logs are marked `skipped`, so tests never touch the network.
"""
import logging

import requests
from django.conf import settings
from django.db import transaction
from django.utils import timezone, translation
from django.utils.translation import gettext as _

from accounts.models import Role, User

from .models import NotificationEvent, NotificationLog, NotificationStatus

log = logging.getLogger(__name__)
PUSH_URL = "https://api.line.me/v2/bot/message/push"
MAX_ATTEMPTS = 3

E = NotificationEvent


def _templates():
    """Message templates; evaluated inside translation.override so each user gets their language."""
    return {
        E.LINE_LINKED: _("Your LINE account is now linked to the Chem Lab Borrow system."),
        E.REQUEST_SUBMITTED: _("New borrow request %(code)s from %(name)s: %(items)s, %(start)s – %(end)s."),
        E.REQUEST_APPROVED: _("Your request %(code)s was approved. Pick up the equipment at %(start)s."),
        E.REQUEST_REJECTED: _("Your request %(code)s was not approved. Reason: %(reason)s"),
        E.BOOKING_CREATED: _("Booking %(code)s confirmed: %(items)s, %(start)s – %(end)s."),
        E.BOOKING_CANCELLED: _("Booking %(code)s was cancelled: %(items)s, %(start)s."),
        E.REQUEST_CANCELLED: _("Request %(code)s was cancelled."),
        E.DUE_SOON: _("Reminder: please return %(items)s (request %(code)s) by %(end)s."),
        E.OVERDUE: _("Request %(code)s is overdue since %(end)s: %(items)s. Please return it as soon as possible."),
        E.RETURNED: _("Return of request %(code)s is confirmed. Thank you."),
        E.DAMAGE_REPORTED: _("Damage reported for %(items)s: %(reason)s"),
    }


def render_message(user, event, context):
    lang = getattr(user, "language", None) or settings.LANGUAGE_CODE
    with translation.override(lang):
        ctx = {k: (v(lang) if callable(v) else v) for k, v in context.items()}
        ctx.setdefault("code", "")
        try:
            text = _templates()[event] % ctx
        except (KeyError, ValueError):
            text = str(_templates()[event])
        if ctx.get("url"):
            text += "\n" + ctx["url"]
    return text


def notify(user, event, context=None, related=None):
    entry = NotificationLog.objects.create(
        user=user, event=event, message=render_message(user, event, context or {}),
        related_object=f"{related._meta.label}:{related.pk}" if related is not None else "",
    )
    transaction.on_commit(lambda: send_log(entry.pk))
    return entry


def notify_staff(event, context=None, related=None, exclude=None):
    staff = User.objects.filter(role=Role.STAFF, is_active=True)
    if exclude is not None:
        staff = staff.exclude(pk=exclude.pk)
    return [notify(u, event, context, related) for u in staff]


def send_log(log_id):
    entry = NotificationLog.objects.select_related("user").filter(pk=log_id).first()
    if entry is None or entry.status == NotificationStatus.SENT:
        return entry
    token = settings.LINE_CHANNEL_ACCESS_TOKEN
    if not token or not entry.user.line_user_id:
        entry.status = NotificationStatus.SKIPPED
        entry.save(update_fields=["status", "updated_at"])
        return entry
    entry.attempts += 1
    try:
        resp = requests.post(
            PUSH_URL, timeout=10,
            headers={"Authorization": f"Bearer {token}", "X-Line-Retry-Key": str(entry.retry_key)},
            json={"to": entry.user.line_user_id, "messages": [{"type": "text", "text": entry.message[:4900]}]},
        )
        # 409 = same retry key already accepted -> treat as sent.
        if 200 <= resp.status_code < 300 or resp.status_code == 409:
            entry.status, entry.sent_at, entry.error = NotificationStatus.SENT, timezone.now(), ""
        else:
            entry.status = NotificationStatus.FAILED
            entry.error = f"{resp.status_code} {resp.text[:300]}"
    except requests.RequestException as exc:
        entry.status, entry.error = NotificationStatus.FAILED, str(exc)[:390]
        log.warning("LINE push failed for log %s: %s", entry.pk, exc)
    entry.save(update_fields=["status", "attempts", "error", "sent_at", "updated_at"])
    return entry


def retry_failed():
    ids = NotificationLog.objects.filter(status=NotificationStatus.FAILED, attempts__lt=MAX_ATTEMPTS)
    return [send_log(pk) for pk in ids.values_list("pk", flat=True)]
