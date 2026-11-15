"""bulk_status must agree with the per-item display_status / free_now for every situation."""
from datetime import timedelta

import pytest
from django.utils import timezone

from borrowing.availability import bulk_status, display_status, free_now
from borrowing.models import Booking, BorrowItem, BorrowRequest, RequestStatus
from inventory.models import AdminStatus, Category, Equipment
from maintenance.models import DamageReport, RepairStatus
from tests.factories import make_student

pytestmark = pytest.mark.django_db


def test_bulk_matches_single_item_rules():
    now = timezone.now()
    cat = Category.objects.create(name_th="ทดสอบ")
    student = make_student()

    def eq(code, total=3, oos=0, **kw):
        return Equipment.objects.create(asset_code=code, name_th=code, category=cat, quantity_total=total,
                                        quantity_out_of_service=oos, **kw)

    items = [
        eq("free"),
        eq("off", status=AdminStatus.UNAVAILABLE),
        eq("broken", total=1, oos=1),
        eq("repair", total=1, oos=1),
        eq("loaned", total=1),
        eq("reserved", total=2),
        eq("partly", total=5),
    ]
    by = {e.asset_code: e for e in items}
    DamageReport.objects.create(equipment=by["repair"], problem="x", status=RepairStatus.IN_REPAIR)
    req = BorrowRequest.objects.create(user=student, purpose="p", borrow_at=now - timedelta(hours=1),
                                       due_at=now + timedelta(hours=3), status=RequestStatus.BORROWED)
    BorrowItem.objects.create(request=req, equipment=by["loaned"], quantity=1)
    BorrowItem.objects.create(request=req, equipment=by["partly"], quantity=2)
    pending = BorrowRequest.objects.create(user=student, purpose="p", borrow_at=now - timedelta(minutes=5),
                                           due_at=now + timedelta(hours=1), status=RequestStatus.PENDING)
    BorrowItem.objects.create(request=pending, equipment=by["reserved"], quantity=1)
    Booking.objects.create(user=student, equipment=by["reserved"], quantity=1, start_at=now - timedelta(minutes=1),
                           end_at=now + timedelta(hours=1))

    result = bulk_status(Equipment.objects.all(), at=now)
    for e in Equipment.objects.all():
        assert result[e.pk] == (display_status(e, now), free_now(e, now)), e.asset_code
    assert result[by["partly"].pk][1] == 3
