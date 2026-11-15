"""Reporting queries and dashboard aggregates."""
from datetime import datetime, time, timedelta

from django.db.models import Count, Q, Sum
from django.utils import timezone
from django.utils.translation import get_language
from django.utils.translation import gettext as _

from borrowing.availability import bulk_status
from borrowing.models import BorrowItem, BorrowRequest, RequestStatus
from inventory.models import DisplayStatus, Equipment
from maintenance.models import DamageReport

BORROWED_STATUSES = (RequestStatus.BORROWED, RequestStatus.OVERDUE, RequestStatus.RETURNED)


def _month_start(day):
    return day.replace(day=1)


def _next_month(day):
    return (day.replace(day=28) + timedelta(days=4)).replace(day=1)


def _local_midnight(day):
    return timezone.make_aware(datetime.combine(day, time.min), timezone.get_current_timezone())


def _equipment_name(equipment):
    return f"{equipment.asset_code} - {equipment.display_name}"


def _item_names(request):
    return ", ".join(f"{item.equipment.display_name} × {item.quantity}" for item in request.items.all())


def _borrowed_items(start=None, end=None):
    qs = BorrowItem.objects.filter(request__status__in=BORROWED_STATUSES)
    if start:
        qs = qs.filter(request__borrow_at__date__gte=start)
    if end:
        qs = qs.filter(request__borrow_at__date__lte=end)
    return qs


def dashboard_stats():
    now = timezone.localtime()
    equipment = list(Equipment.objects.active().select_related("category"))
    statuses = bulk_status(equipment, now)
    loaned_by_id = {
        row["equipment_id"]: row["quantity"]
        for row in BorrowItem.objects.filter(equipment_id__in=[item.pk for item in equipment],
                                             request__status__in=(RequestStatus.BORROWED, RequestStatus.OVERDUE))
        .values("equipment_id").annotate(quantity=Sum("quantity"))
    }
    total_equipment = sum(item.quantity_total for item in equipment)
    on_loan_units = sum(loaned_by_id.values())
    available_units = sum(statuses[item.pk][1] for item in equipment)
    damaged_units = sum(item.quantity_out_of_service for item in equipment)
    month_start = _month_start(now.date())
    month_end = _next_month(month_start)
    loans_this_month = BorrowRequest.objects.filter(
        handed_over_at__gte=_local_midnight(month_start), handed_over_at__lt=_local_midnight(month_end)
    ).count()

    top_rows = list(
        _borrowed_items().values("equipment_id", "equipment__asset_code", "equipment__name_th", "equipment__name_en")
        .annotate(times_borrowed=Count("request_id", distinct=True), total_quantity=Sum("quantity"))
        .order_by("-total_quantity", "equipment__asset_code")[:10]
    )
    top_borrowed = []
    for row in top_rows:
        name = row["equipment__name_en"] if get_language() == "en" and row["equipment__name_en"] \
            else row["equipment__name_th"]
        top_borrowed.append({
            "name": f'{row["equipment__asset_code"]} - {name}',
            "times_borrowed": row["times_borrowed"],
            "total_quantity": row["total_quantity"] or 0,
        })

    return {
        "total_equipment": total_equipment,
        "available_units": available_units,
        "on_loan_units": on_loan_units,
        "damaged_units": damaged_units,
        "pending_requests": BorrowRequest.objects.filter(status=RequestStatus.PENDING).count(),
        "overdue_requests": BorrowRequest.objects.filter(status=RequestStatus.OVERDUE).count(),
        "loans_this_month": loans_this_month,
        "top_borrowed": top_borrowed,
    }


def monthly_loans(months=12):
    """Return month labels and handover counts, including the current month."""
    today = timezone.localdate()
    first = _month_start(today)
    starts = []
    cursor = first
    for _month in range(months - 1):
        cursor = (cursor - timedelta(days=1)).replace(day=1)
    for _month in range(months):
        starts.append(cursor)
        cursor = _next_month(cursor)
    counts = BorrowRequest.objects.aggregate(**{
        f"month_{index}": Count("pk", filter=Q(
            handed_over_at__gte=_local_midnight(start),
            handed_over_at__lt=_local_midnight(_next_month(start)),
        ))
        for index, start in enumerate(starts)
    })
    return [(start.strftime("%m/%Y"), counts[f"month_{index}"])
            for index, start in enumerate(starts)]


def status_breakdown():
    equipment = list(Equipment.objects.active().select_related("category"))
    counts = {status.value: 0 for status in DisplayStatus}
    statuses = bulk_status(equipment)
    for status, _free_now in statuses.values():
        counts[status] += 1
    return {"labels": [str(status.label) for status in DisplayStatus],
            "values": [counts[status.value] for status in DisplayStatus]}


def _date_filtered(qs, field, date_from, date_to):
    if date_from:
        qs = qs.filter(**{f"{field}__date__gte": date_from})
    if date_to:
        qs = qs.filter(**{f"{field}__date__lte": date_to})
    return qs


def loans_report(date_from=None, date_to=None):
    qs = _date_filtered(BorrowRequest.objects.select_related("user", "return_record")
                        .prefetch_related("items__equipment"),
                        "borrow_at", date_from, date_to)
    rows = [(req.code, req.user.get_full_name() or req.user.username, _item_names(req), req.borrow_at, req.due_at,
             req.get_status_display(), getattr(getattr(req, "return_record", None), "returned_at", None))
            for req in qs]
    return _("Loan report"), [_ ("Request code"), _("Borrower"), _("Items"), _("Borrow at"), _("Due at"),
                               _("Status"), _("Returned at")], rows


def equipment_report(date_from=None, date_to=None):
    equipment = list(Equipment.objects.active().select_related("category"))
    statuses = bulk_status(equipment)
    rows = [(item.asset_code, item.display_name, item.category.display_name, item.quantity_total,
             item.quantity_out_of_service, str(statuses[item.pk][0].label)) for item in equipment]
    return _("Equipment report"), [_ ("Asset"), _("Name"), _("Category"), _("Total"), _("Out of service"),
                                   _("Display status")], rows


def top_borrowed_report(date_from=None, date_to=None):
    rows = list(_borrowed_items(date_from, date_to).values("equipment_id", "equipment__asset_code")
                .annotate(times=Count("request_id", distinct=True), quantity=Sum("quantity"))
                .order_by("-quantity", "equipment__asset_code"))
    equipment = {item.pk: item for item in Equipment.objects.filter(
        pk__in=[r["equipment_id"] for r in rows]).select_related("category")}
    data = [(_equipment_name(equipment[row["equipment_id"]]), row["times"], row["quantity"] or 0) for row in rows]
    return _("Most borrowed equipment"), [_ ("Equipment"), _("Times borrowed"), _("Total quantity")], data


def overdue_report(date_from=None, date_to=None):
    qs = _date_filtered(BorrowRequest.objects.filter(status=RequestStatus.OVERDUE).select_related("user")
                        .prefetch_related("items__equipment"), "borrow_at", date_from, date_to)
    today = timezone.localdate()
    rows = [(req.code, req.user.get_full_name() or req.user.username, req.user.phone, _item_names(req), req.due_at,
             max((today - timezone.localtime(req.due_at).date()).days, 0)) for req in qs]
    return _("Overdue report"), [_ ("Request code"), _("Borrower"), _("Phone"), _("Items"), _("Due at"),
                                  _("Days overdue")], rows


def damaged_report(date_from=None, date_to=None):
    qs = _date_filtered(DamageReport.objects.select_related("equipment", "reported_by"), "created_at",
                        date_from, date_to)
    rows = [(str(report), _equipment_name(report.equipment), report.quantity, report.problem,
             report.get_status_display(), report.created_at,
             report.reported_by.get_full_name() or report.reported_by.username if report.reported_by else "")
            for report in qs]
    return _("Damaged equipment report"), [_ ("Damage code"), _("Equipment"), _("Quantity"), _("Problem"),
                                             _("Status"), _("Reported at"), _("Reported by")], rows


def usage_report(date_from=None, date_to=None):
    qs = _date_filtered(BorrowRequest.objects.select_related("user").prefetch_related("items"),
                        "created_at", date_from, date_to)
    grouped = {}
    for req in qs:
        key = req.user_id
        if key not in grouped:
            grouped[key] = [req.user, 0, 0]
        grouped[key][1] += 1
        grouped[key][2] += sum(item.quantity for item in req.items.all())
    rows = [(user.get_full_name() or user.username, user.get_role_display(), requests, items)
            for user, requests, items in grouped.values()]
    return _("Usage by user"), [_ ("Name"), _("Role"), _("Number of requests"), _("Total items")], rows


REPORT_BUILDERS = {
    "loans": loans_report,
    "equipment": equipment_report,
    "top_borrowed": top_borrowed_report,
    "overdue": overdue_report,
    "damaged": damaged_report,
    "usage": usage_report,
}


def build_report(kind, date_from=None, date_to=None):
    return REPORT_BUILDERS[kind](date_from, date_to)
