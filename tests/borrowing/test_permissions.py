import pytest
from django.urls import reverse

from borrowing.models import RequestStatus
from tests.borrowing.test_booking import equipment, window
from tests.borrowing.test_views import make_request, post_request
from tests.factories import make_student

pytestmark = pytest.mark.django_db


def test_tc17_borrower_cannot_open_other_request(client, student):
    req = make_request(make_student())
    client.force_login(student)
    assert client.get(reverse("borrowing:request_detail", args=[req.pk])).status_code == 404
    assert client.post(reverse("borrowing:request_cancel", args=[req.pk])).status_code == 404


def test_owner_and_staff_can_open_request(client, student, staff):
    req = make_request(student)
    client.force_login(student)
    assert client.get(req.get_absolute_url()).status_code == 200
    client.force_login(staff)
    assert client.get(req.get_absolute_url()).status_code == 200


def test_student_forbidden_on_staff_views(client, student):
    req = make_request(make_student())
    client.force_login(student)
    assert client.get(reverse("borrowing:staff_requests")).status_code == 403
    assert client.post(reverse("borrowing:request_approve", args=[req.pk])).status_code == 403
    assert client.post(reverse("borrowing:request_reject", args=[req.pk])).status_code == 403
    assert client.post(reverse("borrowing:request_hand_over", args=[req.pk])).status_code == 403
    assert client.get(reverse("borrowing:request_return", args=[req.pk])).status_code == 403
    req.refresh_from_db()
    assert req.status == RequestStatus.PENDING


def test_anonymous_redirected_to_login(client):
    resp = client.get(reverse("borrowing:my_requests"))
    assert resp.status_code == 302 and "login" in resp.url


def test_teacher_can_create_request(client, teacher):
    client.force_login(teacher)
    eq = equipment()
    assert client.get(reverse("borrowing:request_create")).status_code == 200
    assert post_request(client, [(eq, 1)], *window()).status_code == 302
    assert teacher.borrow_requests.count() == 1


def test_staff_cannot_open_borrower_only_pages(client, staff):
    client.force_login(staff)
    assert client.get(reverse("borrowing:my_requests")).status_code == 403
    assert client.get(reverse("borrowing:request_create")).status_code == 403


def test_state_changing_views_are_post_only(client, staff):
    req = make_request()
    client.force_login(staff)
    for name in ("request_approve", "request_reject", "request_hand_over", "request_cancel"):
        assert client.get(reverse(f"borrowing:{name}", args=[req.pk])).status_code == 405
