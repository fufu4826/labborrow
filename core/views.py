import hmac
import os
from pathlib import Path, PureWindowsPath
from urllib.parse import quote

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import render
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.views.generic import UpdateView
from django.views.i18n import set_language as django_set_language

from borrowing.models import ConditionImage
from maintenance.models import DamageReport

from .forms import SystemSettingForm
from .models import SystemSetting
from .permissions import StaffRequiredMixin


@require_POST
def set_language(request):
    """Switch language and remember it on the user (FR-14)."""
    lang = request.POST.get("language")
    if request.user.is_authenticated and lang in dict(settings.LANGUAGES):
        request.user.language = lang
        request.user.save(update_fields=["language"])
    return django_set_language(request)


@login_required
def home(request):
    return render(request, "core/home.html")


@login_required
def protected_media(request, path):
    parts = path.split("/")
    if (not path or ".." in parts or "\\" in path or "\x00" in path
            or Path(path).is_absolute() or PureWindowsPath(path).drive):
        raise Http404
    if parts[0] == "returns":
        images = ConditionImage.objects.filter(image=path)
        if not request.user.is_lab_staff:
            images = images.filter(return_record__request__user=request.user)
        if not images.exists():
            raise Http404
    elif parts[0] == "damage":
        reports = DamageReport.objects.filter(image=path)
        if not request.user.is_lab_staff:
            reports = reports.filter(reported_by=request.user)
        if not reports.exists():
            raise Http404
    elif parts[0] != "equipment":
        raise Http404
    root = Path(settings.MEDIA_ROOT).resolve()
    file_path = (root / path).resolve()
    if not file_path.is_relative_to(root):
        raise Http404
    if not settings.DEBUG and os.environ.get("MEDIA_ACCEL") == "1":
        response = HttpResponse()
        response["X-Accel-Redirect"] = "/protected-media/" + quote(path, safe="/")
    else:
        try:
            response = FileResponse(file_path.open("rb"))
        except (OSError, ValueError) as exc:
            raise Http404 from exc
    response["X-Content-Type-Options"] = "nosniff"
    return response


class SystemSettingUpdateView(StaffRequiredMixin, UpdateView):
    model = SystemSetting
    form_class = SystemSettingForm
    template_name = "core/settings_form.html"
    success_url = reverse_lazy("core:settings")

    def get_object(self, queryset=None):
        return SystemSetting.load()

    def form_valid(self, form):
        messages.success(self.request, _("Settings saved."))
        return super().form_valid(form)


@csrf_exempt
@require_POST
def cron(request):
    """Run the hourly jobs (due checks + LINE retries) for hosts without a scheduler.

    Called by an external scheduler (GitHub Actions) with header `X-Cron-Token: <CRON_TOKEN>`.
    Disabled (404) while CRON_TOKEN is empty.
    """
    from borrowing.services import run_due_checks
    from notifications.models import NotificationStatus
    from notifications.services import retry_failed

    expected = settings.CRON_TOKEN
    given = request.headers.get("X-Cron-Token", "")
    if not expected:
        raise Http404
    if not hmac.compare_digest(given.encode(), expected.encode()):
        return HttpResponse(status=403)
    counts = run_due_checks()
    results = retry_failed()
    counts["retried"] = len(results)
    counts["retry_sent"] = sum(1 for r in results if r and r.status == NotificationStatus.SENT)
    return JsonResponse(counts)
