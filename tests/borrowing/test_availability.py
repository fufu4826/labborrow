from datetime import timedelta

import pytest
from django.utils import timezone

from borrowing.availability import available_quantity
from borrowing.models import BorrowItem, BorrowRequest, RequestStatus
from inventory.models import Category, Equipment
from tests.factories import make_student

pytestmark = pytest.mark.django_db


@pytest.fixture
def eq():
    cat = Category.objects.create(name_th="เครื่องมือวัด")
    return Equipment.objects.create(asset_code="A-1", name_th="pH meter", category=cat, quantity_total=2)


def _loan(eq, status, borrow_at, due_at, qty=1):
    req = BorrowRequest.objects.create(user=make_student(), purpose="x", borrow_at=borrow_at, due_at=due_at,
                                       status=status)
    BorrowItem.objects.create(request=req, equipment=eq, quantity=qty)
    return req


def test_past_due_loan_still_marked_borrowed_holds_future_window(eq):
    now = timezone.now()
    _loan(eq, RequestStatus.BORROWED, now - timedelta(days=3), now - timedelta(days=1))
    start = now + timedelta(days=2)
    assert available_quantity(eq, start, start + timedelta(hours=2)) == 1


def test_returned_and_pending_outside_window_do_not_hold(eq):
    now = timezone.now()
    _loan(eq, RequestStatus.RETURNED, now - timedelta(days=3), now - timedelta(days=1))
    _loan(eq, RequestStatus.PENDING, now + timedelta(days=10), now + timedelta(days=11))
    start = now + timedelta(days=2)
    assert available_quantity(eq, start, start + timedelta(hours=2)) == 2


def test_back_to_back_holds_use_peak_not_sum(eq):
    """Stock 2: bookings 09-10 and 10-11 each hold 1, so 1 unit is free for 09-11 the whole time."""
    from borrowing.models import Booking

    base = (timezone.now() + timedelta(days=3)).replace(hour=2, minute=0, second=0, microsecond=0)
    for h in (0, 1):
        Booking.objects.create(user=make_student(), equipment=eq, quantity=1,
                               start_at=base + timedelta(hours=h), end_at=base + timedelta(hours=h + 1))
    assert available_quantity(eq, base, base + timedelta(hours=2)) == 1
    # touching intervals (end == start) do not overlap
    assert available_quantity(eq, base + timedelta(hours=2), base + timedelta(hours=3)) == 2


def test_overlapping_holds_add_up(eq):
    from borrowing.models import Booking

    base = (timezone.now() + timedelta(days=3)).replace(hour=2, minute=0, second=0, microsecond=0)
    Booking.objects.create(user=make_student(), equipment=eq, quantity=1, start_at=base,
                           end_at=base + timedelta(hours=2))
    Booking.objects.create(user=make_student(), equipment=eq, quantity=1, start_at=base + timedelta(hours=1),
                           end_at=base + timedelta(hours=3))
    assert available_quantity(eq, base, base + timedelta(hours=3)) == 0


def test_early_hand_over_holds_from_hand_over_time(eq):
    now = timezone.now()
    req = _loan(eq, RequestStatus.BORROWED, now + timedelta(hours=5), now + timedelta(hours=8), qty=2)
    req.handed_over_at = now - timedelta(minutes=1)
    req.save()
    assert available_quantity(eq, now, now + timedelta(hours=1)) == 0


def test_overdue_loan_holds(eq):
    now = timezone.now()
    _loan(eq, RequestStatus.OVERDUE, now - timedelta(days=5), now - timedelta(days=2), qty=2)
    start = now + timedelta(days=1)
    assert available_quantity(eq, start, start + timedelta(hours=1)) == 0
