"""Availability and display status of equipment (docs/01, docs/02). Read-only helpers, no locking here.

Services that create bookings/requests call `available_quantity` again inside their transaction after
`select_for_update()` on the Equipment rows.
"""
from django.db.models import Q, Sum
from django.utils import timezone

from inventory.models import AdminStatus, DisplayStatus

from .models import HOLDING_BOOKING, HOLDING_REQUEST, ON_LOAN, Booking, BookingStatus, BorrowItem


def held_quantity(equipment, start, end, exclude_booking=None, exclude_request=None):
    """Units held by bookings and borrow requests that overlap [start, end)."""
    bookings = Booking.objects.filter(equipment=equipment, status__in=HOLDING_BOOKING,
                                      start_at__lt=end, end_at__gt=start)
    if exclude_booking is not None:
        bookings = bookings.exclude(pk=exclude_booking.pk)
    # Requests hold their own window; units already handed over (borrowed/overdue) hold from borrow_at
    # until they are actually returned, even after the due time and before check_due marks them overdue.
    items = BorrowItem.objects.filter(
        Q(request__status__in=HOLDING_REQUEST, request__borrow_at__lt=end, request__due_at__gt=start)
        | Q(request__status__in=ON_LOAN, request__borrow_at__lt=end),
        equipment=equipment,
    )
    if exclude_request is not None:
        items = items.exclude(request=exclude_request)
    total = (bookings.aggregate(s=Sum("quantity"))["s"] or 0) + (items.aggregate(s=Sum("quantity"))["s"] or 0)
    return total


def available_quantity(equipment, start, end, exclude_booking=None, exclude_request=None):
    """Free units of `equipment` for the whole window [start, end)."""
    if not equipment.is_active or equipment.status != AdminStatus.AVAILABLE:
        return 0
    held = held_quantity(equipment, start, end, exclude_booking, exclude_request)
    return max(equipment.usable_quantity - held, 0)


def on_loan_quantity(equipment, at=None):
    at = at or timezone.now()
    qs = BorrowItem.objects.filter(equipment=equipment, request__status__in=ON_LOAN)
    return qs.aggregate(s=Sum("quantity"))["s"] or 0


def reserved_quantity(equipment, at=None):
    at = at or timezone.now()
    b = Booking.objects.filter(equipment=equipment, status=BookingStatus.ACTIVE, start_at__lte=at, end_at__gt=at)
    r = BorrowItem.objects.filter(equipment=equipment, request__status__in=["pending", "approved"],
                                  request__borrow_at__lte=at, request__due_at__gt=at)
    return (b.aggregate(s=Sum("quantity"))["s"] or 0) + (r.aggregate(s=Sum("quantity"))["s"] or 0)


def display_status(equipment, at=None):
    """Status shown to users, by priority (docs/02)."""
    if not equipment.is_active or equipment.status != AdminStatus.AVAILABLE:
        return DisplayStatus.UNAVAILABLE
    if equipment.usable_quantity == 0:
        from maintenance.models import RepairStatus  # local import: maintenance depends on borrowing
        if equipment.damage_reports.filter(status=RepairStatus.IN_REPAIR).exists():
            return DisplayStatus.REPAIRING
        return DisplayStatus.DAMAGED
    loaned = on_loan_quantity(equipment, at)
    if loaned >= equipment.usable_quantity:
        return DisplayStatus.BORROWED
    if loaned + reserved_quantity(equipment, at) >= equipment.usable_quantity:
        return DisplayStatus.RESERVED
    return DisplayStatus.AVAILABLE


def free_now(equipment, at=None):
    """Units that can be taken right now (not on loan, not reserved now)."""
    if display_status(equipment, at) == DisplayStatus.UNAVAILABLE:
        return 0
    return max(equipment.usable_quantity - on_loan_quantity(equipment, at) - reserved_quantity(equipment, at), 0)


def _sum_by_equipment(qs):
    return {row["equipment_id"]: row["s"] for row in qs.values("equipment_id").annotate(s=Sum("quantity"))}


def bulk_status(equipment_list, at=None):
    """{equipment.pk: (display_status, free_now)} for many items with 4 queries in total.

    Same rules as `display_status` / `free_now`; use it for lists, dashboards and reports.
    """
    from maintenance.models import RepairStatus  # local import: maintenance depends on borrowing

    at = at or timezone.now()
    items = list(equipment_list)
    ids = [eq.pk for eq in items]
    loaned = _sum_by_equipment(BorrowItem.objects.filter(equipment_id__in=ids, request__status__in=ON_LOAN))
    booked = _sum_by_equipment(Booking.objects.filter(equipment_id__in=ids, status=BookingStatus.ACTIVE,
                                                      start_at__lte=at, end_at__gt=at))
    requested = _sum_by_equipment(BorrowItem.objects.filter(
        equipment_id__in=ids, request__status__in=["pending", "approved"],
        request__borrow_at__lte=at, request__due_at__gt=at))
    from maintenance.models import DamageReport
    repairing = set(DamageReport.objects.filter(equipment_id__in=ids, status=RepairStatus.IN_REPAIR)
                    .values_list("equipment_id", flat=True))
    result = {}
    for eq in items:
        if not eq.is_active or eq.status != AdminStatus.AVAILABLE:
            result[eq.pk] = (DisplayStatus.UNAVAILABLE, 0)
            continue
        usable = eq.usable_quantity
        if usable == 0:
            result[eq.pk] = (DisplayStatus.REPAIRING if eq.pk in repairing else DisplayStatus.DAMAGED, 0)
            continue
        out = loaned.get(eq.pk, 0)
        reserved = booked.get(eq.pk, 0) + requested.get(eq.pk, 0)
        if out >= usable:
            status = DisplayStatus.BORROWED
        elif out + reserved >= usable:
            status = DisplayStatus.RESERVED
        else:
            status = DisplayStatus.AVAILABLE
        result[eq.pk] = (status, max(usable - out - reserved, 0))
    return result


STATUS_BADGE = {
    DisplayStatus.AVAILABLE: "success",
    DisplayStatus.RESERVED: "info",
    DisplayStatus.BORROWED: "warning",
    DisplayStatus.REPAIRING: "secondary",
    DisplayStatus.DAMAGED: "danger",
    DisplayStatus.UNAVAILABLE: "dark",
}
