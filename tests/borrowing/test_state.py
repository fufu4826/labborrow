from datetime import timedelta

import pytest
from django.utils import timezone

from borrowing.models import Booking, BookingStatus, BorrowRequest, RequestStatus
from borrowing.state import TransitionError, allowed_events, transition
from inventory.models import Category, Equipment
from tests.factories import make_staff, make_student

pytestmark = pytest.mark.django_db


@pytest.fixture
def eq():
    cat = Category.objects.create(name_th="เครื่องแก้ว")
    return Equipment.objects.create(asset_code="T-1", name_th="บีกเกอร์", category=cat, quantity_total=5)


def make_request(user, hours_ahead=48):
    start = timezone.now() + timedelta(hours=hours_ahead)
    return BorrowRequest.objects.create(user=user, purpose="lab", borrow_at=start, due_at=start + timedelta(days=1))


def test_full_happy_path():
    student, staff = make_student(), make_staff()
    req = make_request(student)
    transition(req, "approve", staff)
    assert req.status == RequestStatus.APPROVED and req.decided_by == staff
    transition(req, "hand_over", staff)
    assert req.status == RequestStatus.BORROWED and req.handed_over_at
    transition(req, "mark_overdue", None)
    assert req.status == RequestStatus.OVERDUE
    transition(req, "receive_return", staff)
    req.refresh_from_db()
    assert req.status == RequestStatus.RETURNED


def test_student_cannot_approve():
    student = make_student()
    req = make_request(student)
    with pytest.raises(TransitionError):
        transition(req, "approve", student)


def test_tc06_reject_needs_reason():
    staff = make_staff()
    req = make_request(make_student())
    with pytest.raises(TransitionError):
        transition(req, "reject", staff, reason="  ")
    transition(req, "reject", staff, reason="ไม่ว่าง")
    assert req.status == RequestStatus.REJECTED and req.reject_reason == "ไม่ว่าง"


def test_invalid_source_status():
    staff = make_staff()
    req = make_request(make_student())
    with pytest.raises(TransitionError):
        transition(req, "hand_over", staff)


def test_owner_cancel_window():
    student = make_student()
    late = make_request(student, hours_ahead=1)  # default cancel_before_hours = 2
    with pytest.raises(TransitionError):
        transition(late, "cancel", student)
    early = make_request(student, hours_ahead=48)
    transition(early, "cancel", student)
    assert early.status == RequestStatus.CANCELLED


def test_staff_can_cancel_late_and_other_user_cannot():
    student, other, staff = make_student(), make_student(), make_staff()
    req = make_request(student, hours_ahead=1)
    with pytest.raises(TransitionError):
        transition(req, "cancel", other)
    transition(req, "cancel", staff)
    assert req.status == RequestStatus.CANCELLED


def test_booking_convert_only_owner(eq):
    student, staff = make_student(), make_staff()
    start = timezone.now() + timedelta(days=2)
    bk = Booking.objects.create(user=student, equipment=eq, start_at=start, end_at=start + timedelta(hours=3))
    with pytest.raises(TransitionError):
        transition(bk, "convert", staff)
    transition(bk, "convert", student)
    assert bk.status == BookingStatus.CONVERTED


def test_allowed_events_lists_buttons():
    student, staff = make_student(), make_staff()
    req = make_request(student)
    assert set(allowed_events(req, staff)) == {"approve", "reject", "cancel"}
    assert allowed_events(req, student) == ["cancel"]
