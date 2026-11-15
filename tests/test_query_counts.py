from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from borrowing.models import BorrowItem, BorrowRequest, RequestStatus, Return, ReturnItem
from inventory.models import Category, Equipment
from maintenance.models import DamageReport, RepairStatus


@pytest.fixture
def query_count_data(staff_client, staff, student):
    category = Category.objects.create(name_th="Lab", name_en="Lab")
    equipment = [
        Equipment.objects.create(asset_code=f"QC-{index:03}", name_th=f"Tool {index}", name_en=f"Tool {index}",
                                 category=category, quantity_total=4)
        for index in range(30)
    ]
    now = timezone.now()
    for index in range(30):
        status = (RequestStatus.BORROWED, RequestStatus.OVERDUE, RequestStatus.RETURNED)[index % 3]
        request = BorrowRequest.objects.create(
            user=student, purpose="Query count fixture", borrow_at=now - timedelta(days=2),
            due_at=now - timedelta(days=1), status=status,
            handed_over_at=now - timedelta(days=2) if status != RequestStatus.RETURNED else None,
        )
        item = BorrowItem.objects.create(request=request, equipment=equipment[index], quantity=1)
        if status == RequestStatus.RETURNED:
            record = Return.objects.create(request=request, returned_at=now, received_by=staff)
            ReturnItem.objects.create(return_record=record, borrow_item=item, quantity_good=1)
        if index % 5 == 0:
            DamageReport.objects.create(equipment=equipment[index], reported_by=student, quantity=1,
                                        problem="Query count damage", status=RepairStatus.CONFIRMED)
    return equipment


@pytest.mark.django_db
def test_equipment_list_query_count(django_assert_max_num_queries, staff_client, query_count_data):
    with django_assert_max_num_queries(12):
        response = staff_client.get(reverse("inventory:list"))
    assert response.status_code == 200


@pytest.mark.django_db
def test_equipment_available_filter_query_count(django_assert_max_num_queries, staff_client, query_count_data):
    with django_assert_max_num_queries(12):
        response = staff_client.get(reverse("inventory:list"), {"status": "available"})
    assert response.status_code == 200


@pytest.mark.django_db
def test_dashboard_query_count(django_assert_max_num_queries, staff_client, query_count_data):
    with django_assert_max_num_queries(20):
        response = staff_client.get(reverse("reports:dashboard"))
    assert response.status_code == 200


@pytest.mark.django_db
@pytest.mark.parametrize("kind", ["loans", "equipment", "top_borrowed", "overdue", "damaged", "usage"])
def test_xlsx_export_query_count(django_assert_max_num_queries, staff_client, query_count_data, kind):
    with django_assert_max_num_queries(15):
        response = staff_client.get(reverse("reports:export", kwargs={"kind": kind, "fmt": "xlsx"}))
    assert response.status_code == 200


@pytest.mark.django_db
def test_staff_requests_query_count(django_assert_max_num_queries, staff_client, query_count_data):
    with django_assert_max_num_queries(15):
        response = staff_client.get(reverse("borrowing:staff_requests"), {"tab": "all"})
    assert response.status_code == 200


@pytest.mark.django_db
def test_borrowing_history_query_count(django_assert_max_num_queries, staff_client, query_count_data):
    with django_assert_max_num_queries(15):
        response = staff_client.get(reverse("borrowing:history"))
    assert response.status_code == 200
