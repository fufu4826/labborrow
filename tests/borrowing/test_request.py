from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError

from borrowing.models import Booking, BookingStatus, BorrowItem, BorrowRequest, RequestStatus
from borrowing.services import approve, cancel_request, create_request, hand_over, reject, run_due_checks
from borrowing.state import TransitionError
from core.models import SystemSetting
from notifications.models import NotificationEvent as E
from notifications.models import NotificationLog
from tests.borrowing.test_booking import equipment, window
from tests.factories import make_staff, make_student, make_teacher

pytestmark = pytest.mark.django_db


def test_tc05_maximum_items():
    eq, user = equipment(quantity=10), make_student()
    start, end = window()
    with pytest.raises(ValidationError):
        create_request(user, [(eq, 3), (eq, 3)], start, end, "Lab")
    assert not BorrowRequest.objects.exists()


def test_tc05_multiple_items_merge_duplicates():
    staff, user = make_staff(), make_teacher()
    first, second = equipment(), equipment("FLASK")
    req = create_request(user, [(second, 2), (first, 1), (first, 2)], *window(), "Lab")
    assert req.total_quantity == SystemSetting.load().max_items_per_request
    assert dict(req.items.values_list("equipment_id", "quantity")) == {first.pk: 3, second.pk: 2}
    assert NotificationLog.objects.get(event=E.REQUEST_SUBMITTED).user == staff
    approve(req, staff)
    assert req.status == RequestStatus.APPROVED
    assert NotificationLog.objects.get(event=E.REQUEST_APPROVED).user == user
    hand_over(req, staff)
    assert req.status == RequestStatus.BORROWED


def test_tc15_owner_cannot_cancel_after_limit(monkeypatch):
    user = make_student()
    start, end = window()
    req = create_request(user, [(equipment(), 1)], start, end, "Lab")
    monkeypatch.setattr("borrowing.state.timezone.now", lambda: start - timedelta(hours=1))
    with pytest.raises(TransitionError):
        cancel_request(req, user)
    req.refresh_from_db()
    assert req.status == RequestStatus.PENDING
    assert not NotificationLog.objects.filter(event=E.REQUEST_CANCELLED).exists()


def test_tc03_approve_rechecks_other_approved_request():
    staff, user, eq = make_staff(), make_student(), equipment(quantity=1)
    start, end = window()
    req = create_request(user, [(eq, 1)], start, end, "Lab")
    other = BorrowRequest.objects.create(user=user, borrow_at=start, due_at=end, purpose="Other")
    BorrowItem.objects.create(request=other, equipment=eq, quantity=1)
    # Simulate an existing approved loan that has consumed the remaining stock.
    from borrowing.state import transition

    transition(other, "approve", staff)
    with pytest.raises(ValidationError):
        approve(req, staff)
    req.refresh_from_db()
    assert req.status == RequestStatus.PENDING
    assert not NotificationLog.objects.filter(event=E.REQUEST_APPROVED).exists()


def test_tc06_reject_and_tc15_cancel_notifications():
    staff, user, eq = make_staff(), make_student(), equipment()
    req = create_request(user, [(eq, 1)], *window(), "Lab")
    with pytest.raises(TransitionError):
        reject(req, staff, " ")
    reject(req, staff, "Unavailable")
    assert req.status == RequestStatus.REJECTED
    assert "Unavailable" in NotificationLog.objects.get(event=E.REQUEST_REJECTED).message
    req = create_request(user, [(eq, 1)], *window(), "Lab")
    cancel_request(req, user)
    assert req.status == RequestStatus.CANCELLED
    assert NotificationLog.objects.filter(event=E.REQUEST_CANCELLED).count() == 2


def test_tc08_due_checks_overdue_remind_once_and_expire():
    staff, user, eq = make_staff(), make_student(), equipment()
    start, end = window()
    overdue = create_request(user, [(eq, 1)], start, end, "Lab")
    soon = create_request(user, [(eq, 1)], start, end + timedelta(hours=1), "Lab")
    for req in (overdue, soon):
        approve(req, staff)
        hand_over(req, staff)
    expired = Booking.objects.create(user=user, equipment=eq, start_at=start, end_at=end)
    boundary = Booking.objects.create(user=user, equipment=eq, start_at=end - timedelta(hours=1), end_at=end)
    assert run_due_checks(end) == {"overdue": 1, "due_soon": 1, "expired": 1}
    assert run_due_checks(end) == {"overdue": 0, "due_soon": 0, "expired": 0}
    overdue.refresh_from_db()
    soon.refresh_from_db()
    expired.refresh_from_db()
    boundary.refresh_from_db()
    assert overdue.status == RequestStatus.OVERDUE
    assert overdue.overdue_notified_at is not None
    assert soon.reminder_sent_at == end
    assert expired.status == BookingStatus.EXPIRED
    assert boundary.status == BookingStatus.ACTIVE
    assert NotificationLog.objects.filter(event=E.OVERDUE).count() == 2
    assert NotificationLog.objects.filter(event=E.DUE_SOON).count() == 1


@pytest.mark.parametrize("items", [[], [0], [-1], [True]])
def test_tc05_request_invalid_items(items):
    eq = equipment()
    with pytest.raises(ValidationError):
        create_request(make_student(), [(eq, qty) for qty in items], *window(), "Lab")


def test_tc03_multi_item_unavailable_rolls_back():
    user, first, second = make_student(), equipment(), equipment("FLASK", quantity=1)
    create_request(user, [(second, 1)], *window(), "Existing")
    with pytest.raises(ValidationError):
        create_request(user, [(first, 1), (second, 1)], *window(), "Lab")
    assert BorrowRequest.objects.count() == 1
    assert not BorrowItem.objects.filter(equipment=first).exists()
