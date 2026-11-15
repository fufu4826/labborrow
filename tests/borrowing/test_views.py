import io
import json
from datetime import timedelta

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from borrowing.models import Booking, BookingStatus, BorrowRequest, RequestStatus
from borrowing.services import approve, create_booking, create_request, hand_over
from inventory.models import Equipment
from tests.borrowing.test_booking import equipment, window
from tests.factories import make_staff, make_student

pytestmark = pytest.mark.django_db


def fmt(dt):
    return timezone.localtime(dt).strftime("%Y-%m-%dT%H:%M")


def formset_data(rows):
    data = {"form-TOTAL_FORMS": len(rows), "form-INITIAL_FORMS": 0, "form-MIN_NUM_FORMS": 1,
            "form-MAX_NUM_FORMS": 1000}
    for i, (eq, qty) in enumerate(rows):
        data[f"form-{i}-equipment"] = eq.pk
        data[f"form-{i}-quantity"] = qty
    return data


def post_request(client, rows, start, end, purpose="Lab work"):
    data = formset_data(rows)
    data.update({"borrow_at": fmt(start), "due_at": fmt(end), "purpose": purpose})
    return client.post(reverse("borrowing:request_create"), data)


def make_request(user=None, qty=1, eq=None):
    eq = eq or Equipment.objects.filter(asset_code="BEAKER").first() or equipment()
    return create_request(user or make_student(), [(eq, qty)], *window(), "Lab")


def test_booking_create_via_post(client, student):
    client.force_login(student)
    eq = equipment()
    start, end = window()
    resp = client.post(reverse("borrowing:booking_create", args=[eq.pk]),
                       {"start_at": fmt(start), "end_at": fmt(end), "quantity": 2, "note": "x"})
    assert resp.status_code == 302
    booking = Booking.objects.get()
    assert booking.user == student and booking.quantity == 2 and booking.start_at == start


def test_booking_invalid_window_shows_error(client, student):
    client.force_login(student)
    eq = equipment()
    start, end = window()
    resp = client.post(reverse("borrowing:booking_create", args=[eq.pk]),
                       {"start_at": fmt(start.replace(hour=22)), "end_at": fmt(end.replace(hour=23)), "quantity": 1})
    assert resp.status_code == 200
    assert resp.context["form"].non_field_errors()
    assert not Booking.objects.exists()


def test_booking_cancel_and_convert(client, student):
    client.force_login(student)
    eq = equipment()
    b1 = create_booking(student, eq, 1, *window())
    assert client.get(reverse("borrowing:booking_cancel", args=[b1.pk])).status_code == 405
    client.post(reverse("borrowing:booking_cancel", args=[b1.pk]))
    b1.refresh_from_db()
    assert b1.status == BookingStatus.CANCELLED
    b2 = create_booking(student, eq, 1, *window())
    resp = client.post(reverse("borrowing:booking_convert", args=[b2.pk]), {"purpose": "Practical"})
    req = BorrowRequest.objects.get()
    assert resp.status_code == 302 and resp.url == req.get_absolute_url()


def test_request_create_multi_item(client, student):
    client.force_login(student)
    a, b = equipment("A1"), equipment("B1")
    resp = post_request(client, [(a, 1), (b, 2)], *window())
    assert resp.status_code == 302
    req = BorrowRequest.objects.get()
    assert req.status == RequestStatus.PENDING
    assert sorted((i.equipment_id, i.quantity) for i in req.items.all()) == sorted([(a.pk, 1), (b.pk, 2)])


def test_request_create_error_and_prefill(client, student):
    client.force_login(student)
    eq = equipment(quantity=1)
    resp = post_request(client, [(eq, 3)], *window())
    assert resp.status_code == 200 and resp.context["form"].non_field_errors()
    resp = client.get(reverse("borrowing:request_create"), {"equipment": eq.pk})
    assert resp.context["formset"].forms[0].initial["equipment"] == eq.pk


def test_staff_approve_reject_handover_return(client, staff):
    client.force_login(staff)
    eq = equipment()
    req1 = make_request(eq=eq)
    assert client.post(reverse("borrowing:request_approve", args=[req1.pk])).status_code == 302
    req1.refresh_from_db()
    assert req1.status == RequestStatus.APPROVED
    client.post(reverse("borrowing:request_hand_over", args=[req1.pk]))
    req1.refresh_from_db()
    assert req1.status == RequestStatus.BORROWED

    item = req1.items.get()
    buf = io.BytesIO()
    Image.new("RGB", (2000, 1000), "red").save(buf, "PNG")
    photo = SimpleUploadedFile("p.png", buf.getvalue(), content_type="image/png")
    assert client.get(reverse("borrowing:request_return", args=[req1.pk])).status_code == 200
    resp = client.post(reverse("borrowing:request_return", args=[req1.pk]), {
        f"good_{item.pk}": 0, f"damaged_{item.pk}": 1, f"note_{item.pk}": "Cracked", "note": "ok", "images": [photo],
    })
    assert resp.status_code == 302
    req1.refresh_from_db()
    assert req1.status == RequestStatus.RETURNED
    image = req1.return_record.images.get()
    assert max(Image.open(image.image.path).size) <= 1600

    req2 = make_request(eq=eq)
    client.post(reverse("borrowing:request_reject", args=[req2.pk]), {"reason": ""})
    req2.refresh_from_db()
    assert req2.status == RequestStatus.PENDING
    client.post(reverse("borrowing:request_reject", args=[req2.pk]), {"reason": "No stock"})
    req2.refresh_from_db()
    assert req2.status == RequestStatus.REJECTED and req2.reject_reason == "No stock"


def test_return_quantity_mismatch_shows_error(client, staff):
    client.force_login(staff)
    req = make_request(qty=2)
    approve(req, staff)
    hand_over(req, staff)
    item = req.items.get()
    resp = client.post(reverse("borrowing:request_return", args=[req.pk]),
                       {f"good_{item.pk}": 1, f"damaged_{item.pk}": 0})
    assert resp.status_code == 200 and resp.context["form"].errors
    req.refresh_from_db()
    assert req.status == RequestStatus.BORROWED


def test_my_requests_lists_only_own(client, student):
    mine = make_request(student)
    other = make_request(make_student())
    client.force_login(student)
    resp = client.get(reverse("borrowing:my_requests"))
    codes = [r.pk for r in resp.context["page_obj"]]
    assert codes == [mine.pk] and other.pk not in codes


def test_staff_requests_tabs_and_search(client, staff):
    user = make_student(first_name="Somchai")
    req = make_request(user)
    client.force_login(staff)
    url = reverse("borrowing:staff_requests")
    assert [r.pk for r in client.get(url).context["page_obj"]] == [req.pk]
    assert client.get(url, {"tab": "all", "q": "somchai"}).context["page_obj"].paginator.count == 1
    assert client.get(url, {"tab": "all", "q": req.code}).context["page_obj"].paginator.count == 1
    assert client.get(url, {"tab": "all", "q": "nobody"}).context["page_obj"].paginator.count == 0
    assert client.get(url, {"tab": "loan"}).context["page_obj"].paginator.count == 0


def test_history_scope_and_filters(client, staff, student):
    mine = make_request(student)
    make_request(make_student())
    client.force_login(student)
    assert [r.pk for r in client.get(reverse("borrowing:history")).context["page_obj"]] == [mine.pk]
    client.force_login(staff)
    assert client.get(reverse("borrowing:history")).context["page_obj"].paginator.count == 2
    resp = client.get(reverse("borrowing:history"), {"status": "approved"})
    assert resp.context["page_obj"].paginator.count == 0


def test_calendar_events_hides_other_names(client, student):
    other = make_student(first_name="Secret", last_name="Person")
    eq = equipment()
    create_booking(other, eq, 1, *window())
    make_request(other, eq=eq)
    own = make_request(student, eq=eq)
    client.force_login(student)
    resp = client.get(reverse("borrowing:calendar_events"))
    body = resp.content.decode()
    assert resp.status_code == 200 and "Secret" not in body and other.username not in body
    events = json.loads(body)
    titles = [e["title"] for e in events]
    assert len(events) == 3
    assert sum("Booked" in t for t in titles) == 2
    assert any(own.code in t for t in titles)

    staff_client = client.__class__()
    staff_client.force_login(make_staff())
    assert "Secret Person" in staff_client.get(reverse("borrowing:calendar_events")).content.decode()


def test_calendar_events_filters_by_equipment_and_range(client, student):
    a, b = equipment("A1"), equipment("B1")
    make_request(student, eq=a)
    client.force_login(student)
    url = reverse("borrowing:calendar_events")
    assert len(client.get(url, {"equipment": b.pk}).json()) == 0
    assert len(client.get(url, {"equipment": a.pk}).json()) == 1
    far = (timezone.now() + timedelta(days=200)).isoformat()
    assert client.get(url, {"start": far}).json() == []
    assert client.get(reverse("borrowing:calendar")).status_code == 200


def test_check_due_command(capsys):
    req = make_request()
    staff = make_staff()
    approve(req, staff)
    hand_over(req, staff)
    BorrowRequest.objects.filter(pk=req.pk).update(due_at=timezone.now() - timedelta(hours=1))
    call_command("check_due")
    assert "overdue=1" in capsys.readouterr().out
    req.refresh_from_db()
    assert req.status == RequestStatus.OVERDUE
