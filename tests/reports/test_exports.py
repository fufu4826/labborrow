from contextlib import closing
from datetime import date, datetime, timedelta
from io import BytesIO

import pytest
from django.urls import reverse
from django.utils import timezone
from openpyxl import load_workbook

from borrowing.models import BorrowItem, BorrowRequest, RequestStatus
from inventory.models import Category, Equipment
from reports.exports import to_xlsx


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


def test_equipment_formula_exported_as_text(staff_client, loan_report_data):
    name = '=HYPERLINK("http://x")'
    Equipment.objects.update(name_th=name, name_en=name)
    response = staff_client.get(reverse("reports:export", kwargs={"kind": "equipment", "fmt": "xlsx"}))
    with closing(load_workbook(BytesIO(response.content))) as workbook:
        cell = workbook.active.cell(row=4, column=2)
        assert cell.value == "'" + name
        assert cell.data_type == "s"


@pytest.mark.parametrize("prefix", ["=", "+", "-", "@", "\t", "\r"])
def test_xlsx_escapes_all_string_cells_and_preserves_types(prefix):
    text = prefix + "value"
    day = date(2026, 1, 1)
    moment = datetime(2026, 1, 1, 12, 30)
    response = to_xlsx(text, [text], [[text, -2, day, moment]], day, day)
    with closing(load_workbook(BytesIO(response.content))) as workbook:
        sheet = workbook.active
        for address in ("A1", "A3", "A4"):
            assert sheet[address].value == "'" + text.replace("\r", "\n")
            assert sheet[address].data_type == "s"
        assert sheet["B4"].value == -2 and sheet["B4"].data_type == "n"
        assert sheet["C4"].value.date() == day and sheet["C4"].data_type == "d"
        assert sheet["D4"].value == moment and sheet["D4"].data_type == "d"
