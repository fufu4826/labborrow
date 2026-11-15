"""Transactional booking, lending and return operations."""
from datetime import timedelta
from zoneinfo import ZoneInfo

from django.conf import settings as django_settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.urls import NoReverseMatch
from django.utils import timezone
from django.utils.translation import gettext as _

from core.models import SystemSetting
from inventory.models import Equipment
from maintenance.models import DamageReport, DamageSource, RepairStatus
from notifications.models import NotificationEvent as E
from notifications.services import notify, notify_staff

from .availability import available_quantity
from .models import (
    Booking,
    BookingStatus,
    BorrowItem,
    BorrowRequest,
    ConditionImage,
    RequestStatus,
    Return,
    ReturnItem,
)
from .state import transition

LOCAL = ZoneInfo("Asia/Bangkok")


def validate_window(start, end, settings=None):
    if timezone.is_naive(start) or timezone.is_naive(end):
        raise ValidationError(_("Start and end must include a time zone."))
    settings = settings or SystemSetting.load()
    now = timezone.now()
    if end <= start or end - start > timedelta(days=settings.max_borrow_days):
        raise ValidationError(_("Choose an end after the start within the maximum borrowing duration."))
    if start < now - timedelta(minutes=5):
        raise ValidationError(_("The start cannot be in the past."))
    if start > now + timedelta(days=settings.max_advance_booking_days):
        raise ValidationError(_("The start exceeds the advance booking limit."))
    opening = SystemSetting._meta.get_field("open_time").to_python(settings.open_time)
    closing = SystemSetting._meta.get_field("close_time").to_python(settings.close_time)
    for value in (start, end):
        local = timezone.localtime(value, LOCAL)
        if (local.weekday() not in settings.weekday_list
                or not opening <= local.time() <= closing):
            raise ValidationError(_("Choose a time on an open weekday within opening hours."))


def _context(obj):
    if isinstance(obj, Booking):
        items = [(obj.equipment, obj.quantity)]
        start, end = obj.start_at, obj.end_at
    else:
        items = [(item.equipment, item.quantity) for item in obj.items.select_related("equipment")]
        start, end = obj.borrow_at, obj.due_at
    url = ""
    if hasattr(obj, "get_absolute_url"):
        try:
            url = django_settings.SITE_URL.rstrip("/") + obj.get_absolute_url()
        except NoReverseMatch:
            pass  # Detail routes may not be registered yet.
    return {
        "code": getattr(obj, "code", str(obj)),
        "name": obj.user.first_name,
        "items": ", ".join(f"{eq.display_name} x{qty}" for eq, qty in items),
        "start": timezone.localtime(start, LOCAL).strftime("%d/%m/%Y %H:%M"),
        "end": timezone.localtime(end, LOCAL).strftime("%d/%m/%Y %H:%M"),
        "reason": getattr(obj, "reject_reason", ""),
        "url": url,
    }


def _borrower(user):
    if not user.is_active or not user.is_borrower:
        raise ValidationError(_("Only borrowers can create bookings or requests."))


def _quantity(quantity):
    if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 1:
        raise ValidationError(_("Quantity must be a positive integer."))


def _lock(obj):
    locked = type(obj).objects.select_for_update().get(pk=obj.pk)
    obj.__dict__.update(locked.__dict__)
    return obj


def _equipment(ids):
    rows = list(Equipment.objects.select_for_update().filter(pk__in=ids).order_by("pk"))
    if len(rows) != len(set(ids)):
        raise ValidationError(_("Equipment no longer exists."))
    return {eq.pk: eq for eq in rows}


def _available(eq, quantity, start, end, exclude_request=None):
    if not eq.is_bookable or available_quantity(eq, start, end, exclude_request=exclude_request) < quantity:
        raise ValidationError(_("The requested equipment quantity is not available."))


def _both(obj, event):
    context = _context(obj)
    notify(obj.user, event, context, obj)
    notify_staff(event, context, obj)


def create_booking(user, equipment, quantity, start, end, note=""):
    _borrower(user)
    _quantity(quantity)
    settings = SystemSetting.load()
    validate_window(start, end, settings)
    if quantity > settings.max_items_per_request:
        raise ValidationError(_("The maximum number of items per request was exceeded."))
    with transaction.atomic():
        eq = _equipment([equipment.pk])[equipment.pk]
        _available(eq, quantity, start, end)
        booking = Booking.objects.create(
            user=user, equipment=eq, quantity=quantity, start_at=start, end_at=end, note=note,
        )
        _both(booking, E.BOOKING_CREATED)
        return booking


@transaction.atomic
def cancel_booking(booking, actor):
    transition(_lock(booking), "cancel", actor)
    _both(booking, E.BOOKING_CANCELLED)
    return booking


@transaction.atomic
def convert_booking(booking, actor, purpose):
    equipment_id = Booking.objects.values_list("equipment_id", flat=True).get(pk=booking.pk)
    _equipment([equipment_id])
    transition(_lock(booking), "convert", actor)
    req = BorrowRequest.objects.create(
        user=booking.user, booking=booking, purpose=purpose,
        borrow_at=booking.start_at, due_at=booking.end_at,
    )
    BorrowItem.objects.create(request=req, equipment=booking.equipment, quantity=booking.quantity)
    notify_staff(E.REQUEST_SUBMITTED, _context(req), req)
    return req


def create_request(user, items, borrow_at, due_at, purpose):
    _borrower(user)
    quantities = {}
    for eq, qty in items:
        _quantity(qty)
        quantities[eq.pk] = quantities.get(eq.pk, 0) + qty
    settings = SystemSetting.load()
    if not quantities or sum(quantities.values()) > settings.max_items_per_request:
        raise ValidationError(_("Choose items within the maximum number of items per request."))
    validate_window(borrow_at, due_at, settings)
    with transaction.atomic():
        equipment = _equipment(quantities)
        for pk, qty in quantities.items():
            _available(equipment[pk], qty, borrow_at, due_at)
        req = BorrowRequest.objects.create(user=user, purpose=purpose, borrow_at=borrow_at, due_at=due_at)
        for pk, qty in quantities.items():
            BorrowItem.objects.create(request=req, equipment=equipment[pk], quantity=qty)
        notify_staff(E.REQUEST_SUBMITTED, _context(req), req)
        return req


@transaction.atomic
def approve(req, actor):
    items = list(req.items.all())
    equipment = _equipment({item.equipment_id for item in items})
    transition(_lock(req), "approve", actor)
    for item in items:
        _available(equipment[item.equipment_id], item.quantity, req.borrow_at, req.due_at, req)
    notify(req.user, E.REQUEST_APPROVED, _context(req), req)
    return req


@transaction.atomic
def reject(req, actor, reason):
    transition(_lock(req), "reject", actor, reason=reason)
    notify(req.user, E.REQUEST_REJECTED, _context(req), req)
    return req


@transaction.atomic
def cancel_request(req, actor):
    transition(_lock(req), "cancel", actor)
    _both(req, E.REQUEST_CANCELLED)
    return req


@transaction.atomic
def hand_over(req, actor):
    return transition(_lock(req), "hand_over", actor)


@transaction.atomic
def receive_return(req, actor, item_results, note="", images=()):
    images = list(images)
    if len(images) > 5:
        raise ValidationError(_("Upload at most five condition images."))
    items = list(req.items.order_by("equipment_id", "pk"))
    equipment = _equipment({item.equipment_id for item in items})
    _lock(req)
    if set(item_results) != {item.pk for item in items}:
        raise ValidationError(_("Provide return quantities for every borrowed item."))
    for item in items:
        result = item_results[item.pk]
        if not isinstance(result, (tuple, list)) or len(result) != 3:
            raise ValidationError(_("Provide good and damaged quantities and a note for each item."))
        good, damaged, _note = result
        if (any(isinstance(q, bool) or not isinstance(q, int) or q < 0 for q in (good, damaged))
                or good + damaged != item.quantity):
            raise ValidationError(_("Return quantities must match the borrowed quantity."))
    transition(req, "receive_return", actor)
    record = Return.objects.create(request=req, received_by=actor, returned_at=timezone.now(), note=note)
    for item in items:
        good, damaged, item_note = item_results[item.pk]
        returned = ReturnItem.objects.create(
            return_record=record, borrow_item=item, quantity_good=good, quantity_damaged=damaged, note=item_note,
        )
        if damaged:
            eq = equipment[item.equipment_id]
            eq.quantity_out_of_service = min(eq.quantity_total, eq.quantity_out_of_service + damaged)
            eq.save(update_fields=["quantity_out_of_service", "updated_at"])
            DamageReport.objects.create(
                equipment=eq, reported_by=actor, quantity=damaged,
                problem=(item_note or note or _("Damaged at return"))[:150],
                source=DamageSource.RETURN, status=RepairStatus.CONFIRMED, return_item=returned,
            )
    for image in images:
        ConditionImage.objects.create(return_record=record, image=image)
    notify(req.user, E.RETURNED, _context(req), req)
    return record


@transaction.atomic
def run_due_checks(now=None):
    now = now or timezone.now()
    settings = SystemSetting.load()
    counts = {"overdue": 0, "due_soon": 0, "expired": 0}
    requests = BorrowRequest.objects.select_for_update().filter(
        status=RequestStatus.BORROWED, due_at__lte=now + timedelta(hours=settings.due_reminder_hours),
    ).order_by("pk")
    for req in requests:
        if req.due_at <= now:
            transition(req, "mark_overdue", None)
            _both(req, E.OVERDUE)
            counts["overdue"] += 1
        elif req.reminder_sent_at is None:
            notify(req.user, E.DUE_SOON, _context(req), req)
            req.reminder_sent_at = now
            req.save(update_fields=["reminder_sent_at", "updated_at"])
            counts["due_soon"] += 1
    bookings = Booking.objects.select_for_update().filter(
        status=BookingStatus.ACTIVE, start_at__lt=now - timedelta(hours=1),
    ).order_by("pk")
    for booking in bookings:
        transition(booking, "expire", None)
        counts["expired"] += 1
    return counts
