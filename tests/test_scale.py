"""Opt-in performance checks for the main staff pages and report exports."""
import os
import time
from datetime import datetime, timedelta
from datetime import time as datetime_time
from zoneinfo import ZoneInfo

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from accounts.models import Role, User
from borrowing.models import Booking, BookingStatus, BorrowItem, BorrowRequest, RequestStatus, Return
from core.models import SystemSetting
from inventory.models import Category, Equipment
from maintenance.models import DamageReport

pytestmark = [
    pytest.mark.django_db(transaction=True),
    pytest.mark.skipif(os.environ.get("SCALE") != "1", reason="set SCALE=1 to run scale tests"),
]

LOCAL = ZoneInfo("Asia/Bangkok")
REPORT_KINDS = ("loans", "equipment", "top_borrowed", "overdue", "damaged", "usage")


@pytest.fixture
def scale_data(client):
    now = timezone.now()
    local_now = timezone.localtime(now, LOCAL)
    categories = Category.objects.bulk_create([
        Category(name_th=f"หมวด {i}", name_en=f"Category {i}") for i in range(10)
    ])
    equipment = Equipment.objects.bulk_create([
        Equipment(asset_code=f"SC-{i:04}", name_th=f"อุปกรณ์ {i}", name_en=f"Equipment {i}",
                  category=categories[i % len(categories)], quantity_total=4)
        for i in range(500)
    ])
    users = []
    for i in range(60):
        role = Role.STAFF if i == 59 else Role.TEACHER if i % 4 == 0 else Role.STUDENT
        user = User(username=f"scale-user-{i}", first_name=f"Scale{i}", last_name="User", role=role,
                    student_id=f"S{i:04}", email=f"scale{i}@example.com")
        user.set_password("scale-test-password")
        users.append(user)
    User.objects.bulk_create(users)
    staff = users[-1]
    client.force_login(staff)

    requests = []
    returns = []
    returned_indices = []
    statuses = ([RequestStatus.RETURNED] * 2400 + [RequestStatus.REJECTED] * 150
                + [RequestStatus.CANCELLED] * 150 + [RequestStatus.PENDING] * 75
                + [RequestStatus.APPROVED] * 75 + [RequestStatus.BORROWED] * 75
                + [RequestStatus.OVERDUE] * 75)
    for i, status in enumerate(statuses):
        user = users[i % 59]
        days_ago = i % 365
        borrow_at = now - timedelta(days=days_ago)
        due_at = borrow_at + timedelta(days=3)
        handed_over_at = borrow_at if status in (RequestStatus.RETURNED, RequestStatus.BORROWED,
                                                 RequestStatus.OVERDUE) else None
        if status == RequestStatus.PENDING:
            borrow_at, due_at = now + timedelta(days=2), now + timedelta(days=5)
        elif status == RequestStatus.APPROVED:
            borrow_at, due_at = now + timedelta(days=3), now + timedelta(days=6)
        elif status == RequestStatus.BORROWED:
            borrow_at, due_at = now - timedelta(days=1), now + timedelta(days=2)
        elif status == RequestStatus.OVERDUE:
            borrow_at, due_at = now - timedelta(days=5), now - timedelta(days=2)
        req = BorrowRequest(user=user, purpose=f"Scale fixture {i}", borrow_at=borrow_at, due_at=due_at,
                            status=status, handed_over_at=handed_over_at)
        requests.append(req)
        if status == RequestStatus.RETURNED:
            returned_indices.append(i)
    BorrowRequest.objects.bulk_create(requests, batch_size=500)
    items = []
    for i, req in enumerate(requests):
        for offset in range(1 + i % 3):
            items.append(BorrowItem(request=req, equipment=equipment[(i * 3 + offset) % len(equipment)],
                                    quantity=1 + (i + offset) % 2))
    BorrowItem.objects.bulk_create(items, batch_size=1000)
    returns = [Return(request=requests[i], returned_at=requests[i].due_at + timedelta(hours=1),
                      received_by=staff) for i in returned_indices]
    Return.objects.bulk_create(returns, batch_size=500)

    start_day = local_now.date() + timedelta(days=1)
    bookings = []
    for i in range(300):
        start_date = start_day + timedelta(days=i % 60)
        start_at = datetime.combine(start_date, datetime_time(9, 0), LOCAL)
        bookings.append(Booking(user=users[i % 59], equipment=equipment[i % 500], quantity=1,
                                start_at=start_at, end_at=start_at + timedelta(hours=2),
                                status=BookingStatus.ACTIVE if i % 5 else BookingStatus.CANCELLED))
    Booking.objects.bulk_create(bookings, batch_size=500)
    DamageReport.objects.bulk_create([
        DamageReport(equipment=equipment[i % 500], reported_by=users[i % 59], quantity=1,
                     problem=f"Scale damage {i}") for i in range(100)
    ], batch_size=500)
    setting = SystemSetting.load()
    weekday = next((start_day + timedelta(days=i) for i in range(8)
                    if (start_day + timedelta(days=i)).weekday() in setting.weekday_list), start_day)
    return {"client": client, "equipment": equipment, "date": weekday}


def _measure(client, name, path):
    start = time.perf_counter()
    with CaptureQueriesContext(connection) as queries:
        response = client.get(path)
    elapsed = time.perf_counter() - start
    assert response.status_code == 200, f"{name}: HTTP {response.status_code}"
    return name, elapsed * 1000, len(queries)


def test_scale_pages_and_exports(scale_data):
    client = scale_data["client"]
    equipment = scale_data["equipment"][0]
    date = scale_data["date"].isoformat()
    start = timezone.localtime(timezone.now(), LOCAL).date().replace(day=1)
    for _month in range(11):
        start = (start - timedelta(days=1)).replace(day=1)
    end = (start.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    base = reverse("reports:export", kwargs={"kind": "loans", "fmt": "xlsx"})
    date_params = f"date_from={start.isoformat()}&date_to={end.isoformat()}"
    results = [
        _measure(client, "/equipment/", reverse("inventory:list")),
        _measure(client, "/equipment/?status=available", f"{reverse('inventory:list')}?status=available"),
        _measure(client, f"/equipment/?date={date}", f"{reverse('inventory:list')}?date={date}"),
        _measure(client, f"/equipment/{equipment.pk}/", reverse("inventory:detail", args=[equipment.pk])),
        _measure(client, "/borrow/staff/requests/?tab=all", f"{reverse('borrowing:staff_requests')}?tab=all"),
        _measure(client, "/borrow/history/", reverse("borrowing:history")),
        _measure(client, "/borrow/calendar/events/", reverse("borrowing:calendar_events")
                 + f"?start={timezone.now().isoformat()}&end={(timezone.now() + timedelta(days=30)).isoformat()}"),
        _measure(client, "/reports/dashboard/", reverse("reports:dashboard")),
    ]
    for kind in REPORT_KINDS:
        for fmt in ("xlsx", "pdf"):
            path = base.replace("loans/xlsx", f"{kind}/{fmt}") + f"?{date_params}"
            results.append(_measure(client, f"/reports/export/{kind}/{fmt}/", path))
    results.append(_measure(client, "/maintenance/", reverse("maintenance:list")))

    print("\nPage                                      ms    queries")
    for name, elapsed_ms, query_count in results:
        print(f"{name:40} {elapsed_ms:7.1f} {query_count:8}")
    assert all(elapsed_ms < 1500 for _name, elapsed_ms, _queries in results)
    assert all(query_count < 40 for _name, _elapsed_ms, query_count in results)
