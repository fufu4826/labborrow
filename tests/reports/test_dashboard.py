from datetime import timedelta

from django.urls import reverse
from django.utils import timezone

from borrowing.models import BorrowItem, BorrowRequest, RequestStatus
from inventory.models import Category, Equipment
from maintenance.models import DamageReport, RepairStatus


def test_dashboard_staff_stats(staff_client, student):
    category = Category.objects.create(name_th="Lab", name_en="Lab")
    equipment = Equipment.objects.create(asset_code="LAB-1", name_th="Microscope", category=category,
                                         quantity_total=5, quantity_out_of_service=1)
    now = timezone.now()
    request = BorrowRequest.objects.create(user=student, purpose="class", borrow_at=now,
                                           due_at=now + timedelta(days=2),
                                           status=RequestStatus.BORROWED, handed_over_at=now)
    BorrowItem.objects.create(request=request, equipment=equipment, quantity=2)
    DamageReport.objects.create(equipment=equipment, reported_by=student, quantity=1,
                                problem="Broken lens", status=RepairStatus.CONFIRMED)
    BorrowRequest.objects.create(user=student, purpose="pending", borrow_at=now,
                                 due_at=now + timedelta(days=2), status=RequestStatus.PENDING)

    response = staff_client.get(reverse("reports:dashboard"))

    assert response.status_code == 200
    stats = response.context["stats"]
    assert stats["total_equipment"] == 5
    assert stats["available_units"] == 2
    assert stats["on_loan_units"] == 2
    assert stats["damaged_units"] == 1
    assert stats["pending_requests"] == 1
    assert stats["overdue_requests"] == 0
    assert stats["loans_this_month"] == 1
    assert stats["top_borrowed"][0]["total_quantity"] == 2


def test_dashboard_student_forbidden(student_client):
    response = student_client.get(reverse("reports:dashboard"))
    assert response.status_code == 403
