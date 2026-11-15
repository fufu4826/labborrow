from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from borrowing.models import Booking, BookingStatus, RequestStatus
from borrowing.services import cancel_booking, convert_booking, create_booking, validate_window
from core.models import SystemSetting
from inventory.models import Category, Equipment
from notifications.models import NotificationEvent as E
from notifications.models import NotificationLog
from tests.factories import make_staff, make_student, make_teacher

pytestmark = pytest.mark.django_db
LOCAL = ZoneInfo("Asia/Bangkok")


def window():
    date = timezone.localtime(timezone.now(), LOCAL).date() + timedelta(days=3)
    while date.weekday() >= 5:
        date += timedelta(days=1)
    start = datetime.combine(date, datetime.min.time(), LOCAL).replace(hour=10)
    return start, start + timedelta(hours=2)


def equipment(code="BEAKER", quantity=5):
    category, _ = Category.objects.get_or_create(name_th="Glassware")
    return Equipment.objects.create(
        asset_code=code, name_th="Beaker", name_en="Beaker", category=category, quantity_total=quantity,
    )


def test_tc03_fully_booked():
    eq, user = equipment(quantity=1), make_student()
    start, end = window()
    create_booking(user, eq, 1, start, end)
    with pytest.raises(ValidationError):
        create_booking(make_teacher(), eq, 1, start, end)
    assert Booking.objects.count() == 1


@pytest.mark.parametrize("case", ["hours", "advance", "weekday"])
def test_tc04_invalid_open_window(case):
    start, end = window()
    if case == "hours":
        start, end = start.replace(hour=7), end.replace(hour=8)
    elif case == "advance":
        start += timedelta(days=SystemSetting.load().max_advance_booking_days + 1)
        end = start + timedelta(hours=1)
    else:
        start += timedelta(days=(5 - start.weekday()) % 7)
        end = start + timedelta(hours=1)
    with pytest.raises(ValidationError):
        create_booking(make_student(), equipment(), 1, start, end)
    assert not Booking.objects.exists()


def test_tc03_booking_notifications_and_cancel():
    staff, user, eq = make_staff(), make_student(), equipment()
    booking = create_booking(user, eq, 2, *window())
    assert booking.status == BookingStatus.ACTIVE
    assert set(NotificationLog.objects.filter(event=E.BOOKING_CREATED).values_list("user_id", flat=True)) == {
        user.pk, staff.pk,
    }
    cancel_booking(booking, user)
    assert booking.status == BookingStatus.CANCELLED
    assert NotificationLog.objects.filter(event=E.BOOKING_CANCELLED).count() == 2


def test_tc03_convert_keeps_held_quantity():
    make_staff()
    user, eq = make_teacher(), equipment(quantity=1)
    booking = create_booking(user, eq, 1, *window())
    req = convert_booking(booking, user, "Lab")
    assert booking.status == BookingStatus.CONVERTED
    assert req.status == RequestStatus.PENDING
    assert req.booking == booking
    assert (req.borrow_at, req.due_at) == (booking.start_at, booking.end_at)
    assert req.items.get().quantity == 1
    assert NotificationLog.objects.filter(event=E.REQUEST_SUBMITTED).count() == 1
    with pytest.raises(ValidationError):
        create_booking(user, eq, 1, *window())


@pytest.mark.parametrize("case", ["naive", "reverse", "duration", "past", "end_hours", "end_weekday"])
def test_tc04_window_boundaries(case):
    start, end = window()
    if case == "naive":
        start = start.replace(tzinfo=None)
    elif case == "reverse":
        end = start
    elif case == "duration":
        end = start + timedelta(days=8)
    elif case == "past":
        start, end = start - timedelta(days=14), end - timedelta(days=14)
    elif case == "end_hours":
        end = end.replace(hour=18)
    else:
        end += timedelta(days=(5 - end.weekday()) % 7)
    with pytest.raises(ValidationError):
        validate_window(start, end)


def test_tc04_timezone_conversion_and_grace(monkeypatch):
    start, end = window()
    monkeypatch.setattr("borrowing.services.timezone.now", lambda: start + timedelta(minutes=5))
    validate_window(start.astimezone(ZoneInfo("UTC")), end.astimezone(ZoneInfo("UTC")))
    monkeypatch.setattr("borrowing.services.timezone.now", lambda: start + timedelta(minutes=5, seconds=1))
    with pytest.raises(ValidationError):
        validate_window(start, end)


@pytest.mark.parametrize("quantity", [0, -1, True, 1.5, 6])
def test_tc05_booking_invalid_quantity(quantity):
    with pytest.raises(ValidationError):
        create_booking(make_student(), equipment(), quantity, *window())


def test_tc03_staff_cannot_book():
    with pytest.raises(ValidationError):
        create_booking(make_staff(), equipment(), 1, *window())
