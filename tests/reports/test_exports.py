from datetime import timedelta
from io import BytesIO

import pytest
from django.urls import reverse
from django.utils import timezone
from openpyxl import load_workbook

from borrowing.models import BorrowItem, BorrowRequest, RequestStatus
from inventory.models import Category, Equipment


@pytest.fixture
def loan_report_data(staff_client, student):
    category = Category.objects.create(name_th="Glassware", name_en="Glassware")
    equipment = Equipment.objects.create(asset_code="GL-001", name_th="Beaker", category=category)
    now = timezone.now()
    request = BorrowRequest.objects.create(user=student, purpose="Chemistry class", borrow_at=now,
                                           due_at=now + timedelta(days=2), status=RequestStatus.BORROWED,
                                           handed_over_at=now)
    BorrowItem.objects.create(request=request, equipment=equipment, quantity=1)
    return request


@pytest.mark.parametrize("fmt", ["xlsx", "pdf"])
def test_tc09_export_loan_report(staff_client, loan_report_data, fmt):
    request = loan_report_data
    day = timezone.localdate().isoformat()
    response = staff_client.get(reverse("reports:export", kwargs={"kind": "loans", "fmt": fmt}),
                                {"date_from": day, "date_to": day})

    assert response.status_code == 200
    if fmt == "xlsx":
        sheet = load_workbook(BytesIO(response.content), read_only=True).active
        assert [cell.value for cell in sheet[3]][:3] == ["Request code", "Borrower", "Items"]
        assert sheet[4][0].value == request.code
    else:
        assert response.content.startswith(b"%PDF")


@pytest.mark.parametrize("kind", ["loans", "equipment", "top_borrowed", "overdue", "damaged", "usage"])
@pytest.mark.parametrize("fmt", ["xlsx", "pdf"])
def test_every_report_format_downloads(staff_client, loan_report_data, kind, fmt):
    response = staff_client.get(reverse("reports:export", kwargs={"kind": kind, "fmt": fmt}))
    assert response.status_code == 200
    assert response["Content-Disposition"].startswith("attachment;")


def test_unknown_kind_returns_404(staff_client):
    response = staff_client.get(reverse("reports:export", kwargs={"kind": "unknown", "fmt": "xlsx"}))
    assert response.status_code == 404


def test_unknown_format_returns_404(staff_client):
    response = staff_client.get(reverse("reports:export", kwargs={"kind": "loans", "fmt": "csv"}))
    assert response.status_code == 404
