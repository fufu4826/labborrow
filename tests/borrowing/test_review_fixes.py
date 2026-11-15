from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone

from borrowing import services
from borrowing.models import Booking, BookingStatus, BorrowItem, BorrowRequest, RequestStatus
from core.models import SystemSetting
from tests.borrowing.test_booking import equipment, window

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("change", ["damage", "inactive", "unreturned"])
def test_hand_over_rechecks_current_stock_before_transition(student, staff, change):
    eq = equipment(quantity=2)
    req = services.create_request(student, [(eq, 2)], *window(), "Lab")
    services.approve(req, staff)
    if change == "damage":
        eq.quantity_out_of_service = 1
        eq.save()
    elif change == "inactive":
        eq.is_active = False
        eq.save()
    else:
        old = BorrowRequest.objects.create(
            user=student, purpose="Late return", status=RequestStatus.BORROWED,
            borrow_at=timezone.now() - timedelta(days=2), due_at=timezone.now() - timedelta(days=1),
        )
        BorrowItem.objects.create(request=old, equipment=eq, quantity=1)
    with pytest.raises(ValidationError, match="Not enough usable units"):
        services.hand_over(req, staff)
    req.refresh_from_db()
    assert req.status == RequestStatus.APPROVED
    assert req.handed_over_at is None


def test_hand_over_excludes_self_and_checks_only_remaining_window(student, staff, monkeypatch):
    eq = equipment(quantity=2)
    start, end = window()
    req = services.create_request(student, [(eq, 2)], start, end, "Lab")
    services.approve(req, staff)
    Booking.objects.create(user=student, equipment=eq, quantity=2, start_at=start,
                           end_at=start + timedelta(minutes=10))
    monkeypatch.setattr(services.timezone, "now", lambda: start + timedelta(minutes=15))
    services.hand_over(req, staff)
    req.refresh_from_db()
    assert req.status == RequestStatus.BORROWED


@pytest.mark.parametrize("age", [timedelta(minutes=5, seconds=1), timedelta(days=1)])
def test_convert_booking_rejects_started_or_passed_booking(student, monkeypatch, age):
    booking = services.create_booking(student, equipment(), 1, *window())
    monkeypatch.setattr(services.timezone, "now", lambda: booking.start_at + age)
    with pytest.raises(ValidationError, match="This booking has already started or passed"):
        services.convert_booking(booking, student, "Lab")
    booking.refresh_from_db()
    assert booking.status == BookingStatus.ACTIVE
    assert not BorrowRequest.objects.exists()


def test_convert_booking_allows_exact_five_minute_grace(student, monkeypatch):
    booking = services.create_booking(student, equipment(), 1, *window())
    monkeypatch.setattr(services.timezone, "now", lambda: booking.start_at + timedelta(minutes=5))
    assert services.convert_booking(booking, student, "Lab").booking == booking


def test_convert_booking_rechecks_reduced_maximum(student):
    booking = services.create_booking(student, equipment(), 2, *window())
    setting = SystemSetting.load()
    setting.max_items_per_request = 1
    setting.save()
    with pytest.raises(ValidationError, match="maximum number of items"):
        services.convert_booking(booking, student, "Lab")
    booking.refresh_from_db()
    assert booking.status == BookingStatus.ACTIVE
    assert not BorrowRequest.objects.exists()


@pytest.mark.parametrize("value", ["abc", "²", "", "1.5", "9" * 100, "9" * 5000])
@pytest.mark.parametrize("route", ["calendar", "calendar_events", "request_create", "my_requests"])
def test_invalid_numeric_get_parameters_are_ignored(student_client, student, value, route):
    services.create_request(student, [(equipment(), 1)], *window(), "Lab")
    url = reverse(f"borrowing:{route}")
    baseline = student_client.get(url)
    response = student_client.get(url, {"equipment": value, "page": value})
    assert response.status_code == 200
    if route == "calendar_events":
        assert response.json() == baseline.json()
    elif route == "request_create":
        assert response.context["formset"].initial == []
    elif route == "calendar":
        assert response.context["selected"] == ""


def test_valid_equipment_get_parameter_still_prefills_request(student_client):
    eq = equipment()
    response = student_client.get(reverse("borrowing:request_create"), {"equipment": str(eq.pk)})
    assert response.context["formset"].initial == [{"equipment": eq.pk, "quantity": 1}]


@pytest.mark.parametrize("value", ["²", "9" * 100, "9" * 5000, "REQ-²"])
def test_staff_search_ignores_invalid_numeric_request_ids(staff_client, student, value):
    services.create_request(student, [(equipment(), 1)], *window(), "Lab")
    response = staff_client.get(reverse("borrowing:staff_requests"), {"q": value})
    assert response.status_code == 200
    assert response.context["page_obj"].paginator.count == 0
