from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views import View

from core.permissions import ALL_ROLES, STAFF, RoleRequiredMixin, has_role

from . import services
from .forms import DamageReportForm, StatusFilterForm, StatusForm
from .models import DamageReport

BADGES = {
    "reported": "warning text-dark", "confirmed": "danger", "in_repair": "info text-dark",
    "repaired": "success", "written_off": "dark", "rejected": "secondary",
}


def _decorate(report):
    report.badge = BADGES.get(report.status, "secondary")
    return report


class ListView(RoleRequiredMixin, View):
    roles = ALL_ROLES

    def get(self, request):
        staff = has_role(request.user, STAFF)
        qs = DamageReport.objects.select_related("equipment", "reported_by")
        form = StatusFilterForm(request.GET)
        if not staff:
            qs = qs.filter(reported_by=request.user)
        elif form.is_valid():
            if form.cleaned_data["status"]:
                qs = qs.filter(status=form.cleaned_data["status"])
            q = form.cleaned_data["q"].strip()
            if q:
                qs = qs.filter(Q(equipment__asset_code__icontains=q) | Q(equipment__name_th__icontains=q)
                               | Q(equipment__name_en__icontains=q) | Q(problem__icontains=q)
                               | Q(reported_by__username__icontains=q))
        return render(request, "maintenance/list.html",
                      {"reports": [_decorate(r) for r in qs], "form": form, "is_staff_view": staff})


class CreateView(RoleRequiredMixin, View):
    roles = ALL_ROLES

    def get(self, request):
        pk = request.GET.get("equipment")
        initial = {"equipment": pk} if pk and pk.isdigit() else {}
        return render(request, "maintenance/form.html", {"form": DamageReportForm(initial=initial)})

    def post(self, request):
        form = DamageReportForm(request.POST, request.FILES)
        if form.is_valid():
            d = form.cleaned_data
            try:
                report = services.report_damage(request.user, d["equipment"], d["quantity"], d["problem"],
                                                d["description"], d["image"])
            except ValidationError as e:
                form.add_error(None, e)
            else:
                messages.success(request, _("Damage report submitted."))
                return redirect(report)
        return render(request, "maintenance/form.html", {"form": form})


class DetailView(RoleRequiredMixin, View):
    roles = ALL_ROLES

    def _report(self, request, pk):
        report = get_object_or_404(
            DamageReport.objects.select_related("equipment", "reported_by", "handled_by"), pk=pk)
        staff = has_role(request.user, STAFF)
        if not staff and report.reported_by_id != request.user.pk:
            raise PermissionDenied
        return report, staff

    def _render(self, request, report, staff, form=None):
        allowed = services.allowed_next(report) if staff else []
        if allowed and form is None:
            form = StatusForm(allowed=allowed)
        return render(request, "maintenance/detail.html",
                      {"report": _decorate(report), "form": form if allowed else None,
                       "is_staff_view": staff})

    def get(self, request, pk):
        report, staff = self._report(request, pk)
        return self._render(request, report, staff)

    def post(self, request, pk):
        report, staff = self._report(request, pk)
        if not staff:
            raise PermissionDenied
        form = StatusForm(request.POST, allowed=services.allowed_next(report))
        if form.is_valid():
            try:
                services.change_status(report, request.user, form.cleaned_data["status"],
                                       form.cleaned_data["staff_note"])
            except ValidationError as e:
                messages.error(request, "; ".join(e.messages))
            else:
                messages.success(request, _("Status updated."))
            return redirect(report)
        return self._render(request, report, staff, form)
