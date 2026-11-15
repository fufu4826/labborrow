from datetime import date, datetime, timedelta

import pytest
from django.urls import reverse

from borrowing.models import Booking
from inventory.models import AdminStatus, Category, Equipment
from inventory.services import TZ


@pytest.fixture
def data(db):
    glass = Category.objects.create(name_th="เครื่องแก้ว", name_en="Glassware")
    chem = Category.objects.create(name_th="สารเคมี", name_en="Chemicals")
    beaker = Equipment.objects.create(asset_code="GL-001", name_th="บีกเกอร์", name_en="Beaker",
                                      category=glass, quantity_total=5)
    acid = Equipment.objects.create(asset_code="CH-010", name_th="กรดเกลือ", name_en="HCl",
                                    category=chem, quantity_total=2)
    off = Equipment.objects.create(asset_code="GL-002", name_th="ขวดวัดปริมาตร", category=glass,
                                   status=AdminStatus.UNAVAILABLE)
    return glass, chem, beaker, acid, off


def names(resp):
    return {e.asset_code for e in resp.context["equipment_list"]}


def test_tc13_search_by_name_code_category_status(staff_client, data):
    glass = data[0]
    url = reverse("inventory:list")
    assert names(staff_client.get(url, {"q": "Beaker"})) == {"GL-001"}
    assert names(staff_client.get(url, {"q": "กรด"})) == {"CH-010"}
    assert names(staff_client.get(url, {"q": "GL-"})) == {"GL-001", "GL-002"}
    assert names(staff_client.get(url, {"category": glass.pk})) == {"GL-001", "GL-002"}
    assert names(staff_client.get(url, {"status": "unavailable"})) == {"GL-002"}
    assert names(staff_client.get(url, {"status": "available"})) == {"GL-001", "CH-010"}


def test_pagination_keeps_filters(staff_client, data):
    glass = data[0]
    for i in range(14):
        Equipment.objects.create(asset_code=f"P-{i:02d}", name_th="หลอด", category=glass)
    resp = staff_client.get(reverse("inventory:list"), {"q": "P-"})
    assert len(resp.context["equipment_list"]) == 12
    assert "q=P-&amp;page=2" in resp.content.decode()


def test_date_filter_shows_reduced_free_qty(staff_client, student, data):
    beaker = data[2]
    day = date.today() + timedelta(days=1)
    while day.weekday() not in (0, 1, 2, 3, 4):
        day += timedelta(days=1)
    Booking.objects.create(user=student, equipment=beaker, quantity=2,
                           start_at=datetime(day.year, day.month, day.day, 9, 0, tzinfo=TZ),
                           end_at=datetime(day.year, day.month, day.day, 12, 0, tzinfo=TZ))
    resp = staff_client.get(reverse("inventory:list"), {"q": "GL-001", "date": day.isoformat()})
    (eq,) = resp.context["equipment_list"]
    assert eq.free_qty == 3
    resp = staff_client.get(reverse("inventory:list"), {"q": "GL-001"})
    assert resp.context["equipment_list"][0].free_qty == 5


def test_detail_strip_has_14_days_and_closed_days(student_client, data):
    resp = student_client.get(reverse("inventory:detail", args=[data[2].pk]))
    strip = resp.context["strip"]
    assert len(strip) == 14
    assert all(d["closed"] == (d["date"].weekday() >= 5) for d in strip)
