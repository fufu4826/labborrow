"""Staff-only reports dashboard and downloads."""
from datetime import date, timedelta

from django import forms
from django.http import Http404
from django.shortcuts import render
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views import View

from core.permissions import StaffRequiredMixin

from .exports import to_pdf, to_xlsx
from .services import REPORT_BUILDERS, build_report, dashboard_stats, monthly_loans, status_breakdown

REPORT_LABELS = {
    "loans": _("Loan report"),
    "equipment": _("Equipment report"),
    "top_borrowed": _("Most borrowed equipment"),
    "overdue": _("Overdue report"),
    "damaged": _("Damaged equipment report"),
    "usage": _("Usage by user"),
}


class ReportFilterForm(forms.Form):
    kind = forms.ChoiceField(label=_("Report"), choices=[(key, value) for key, value in REPORT_LABELS.items()])
    date_from = forms.DateField(label=_("From"), widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"))
    date_to = forms.DateField(label=_("To"), widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"))
    fmt = forms.ChoiceField(label=_("Format"), choices=[("xlsx", "Excel (.xlsx)"), ("pdf", "PDF")])

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("date_from") and cleaned.get("date_to") and cleaned["date_from"] > cleaned["date_to"]:
            raise forms.ValidationError(_("The start date must be before the end date."))
        return cleaned


def _default_dates():
    today = timezone.localdate()
    return today - timedelta(days=30), today


def _parse_date(value, default):
    if not value:
        return default
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        raise Http404 from None


class DashboardView(StaffRequiredMixin, View):
    def get(self, request):
        stats = dashboard_stats()
        months = monthly_loans(12)
        statuses = status_breakdown()
        data = {
            "stats": stats,
            "monthly": {"labels": [label for label, _count in months],
                        "values": [count for _label, count in months]},
            "top": {"labels": [item["name"] for item in stats["top_borrowed"]],
                    "values": [item["total_quantity"] for item in stats["top_borrowed"]]},
            "status": statuses,
        }
        return render(request, "reports/dashboard.html", {"stats": stats, "data": data})


class ReportIndexView(StaffRequiredMixin, View):
    def get(self, request):
        date_from, date_to = _default_dates()
        initial = {"date_from": date_from, "date_to": date_to}
        form = ReportFilterForm(request.GET or None, initial=initial)
        if form.is_bound and form.is_valid():
            data = form.cleaned_data
            return self._render(request, form, data["date_from"], data["date_to"], data["kind"], data["fmt"])
        return self._render(request, form, date_from, date_to)

    def post(self, request):
        date_from, date_to = _default_dates()
        form = ReportFilterForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            return self._render(request, form, data["date_from"], data["date_to"], data["kind"], data["fmt"])
        return self._render(request, form, date_from, date_to)

    @staticmethod
    def _render(request, form, date_from, date_to, selected_kind=None, selected_fmt="xlsx"):
        reports = [{"kind": key, "label": label, "xlsx_url": _export_url(key, "xlsx", date_from, date_to),
                    "pdf_url": _export_url(key, "pdf", date_from, date_to)}
                   for key, label in REPORT_LABELS.items()]
        return render(request, "reports/index.html", {"form": form, "reports": reports,
                                                       "selected_kind": selected_kind,
                                                       "selected_fmt": selected_fmt,
                                                       "date_from": date_from, "date_to": date_to})


def _export_url(kind, fmt, date_from, date_to):
    from django.urls import reverse
    from django.utils.http import urlencode

    path = reverse("reports:export", kwargs={"kind": kind, "fmt": fmt})
    return f"{path}?{urlencode({'date_from': date_from.isoformat(), 'date_to': date_to.isoformat()})}"


class ExportView(StaffRequiredMixin, View):
    def get(self, request, kind, fmt):
        if kind not in REPORT_BUILDERS or fmt not in ("xlsx", "pdf"):
            raise Http404
        default_from, default_to = _default_dates()
        date_from = _parse_date(request.GET.get("date_from"), default_from)
        date_to = _parse_date(request.GET.get("date_to"), default_to)
        if date_from > date_to:
            raise Http404
        title, headers, rows = build_report(kind, date_from, date_to)
        exporter = to_xlsx if fmt == "xlsx" else to_pdf
        return exporter(title, headers, rows, date_from, date_to, kind=kind)
