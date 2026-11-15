from datetime import timedelta
from unittest import mock

import pytest
from django.urls import reverse
from django.utils import timezone

from notifications import linking
from tests.factories import make_student


@pytest.mark.django_db
def test_code_format_and_expiry():
    user = make_student()
    code = linking.create_link_code(user)
    user.refresh_from_db()
    assert len(code) == 6 and code.isdigit() and user.line_link_code == code
    delta = user.line_link_expires - timezone.now()
    assert timedelta(minutes=14) < delta <= timedelta(minutes=15)


@pytest.mark.django_db
def test_code_unique_among_unexpired():
    a, b = make_student(), make_student()
    first = linking.create_link_code(a)
    with mock.patch("notifications.linking.secrets.randbelow", side_effect=[int(first), 123456]):
        second = linking.create_link_code(b)
    assert second == "123456" != first


@pytest.mark.django_db
def test_link_by_code_and_unlink():
    user = make_student()
    code = linking.create_link_code(user)
    assert linking.link_by_code("abc", "U1") is None
    assert linking.link_by_code(code, "U1") == user
    assert linking.link_by_code(code, "U2") is None  # code cleared
    assert linking.unlink("U1") == 1
    user.refresh_from_db()
    assert user.line_user_id == ""


@pytest.mark.django_db
def test_line_link_view_generate_and_unlink(client):
    user = make_student(line_user_id="Uold")
    client.force_login(user)
    resp = client.get(reverse("accounts:line_link"))
    assert resp.status_code == 200
    resp = client.post(reverse("accounts:line_link"), {"action": "generate"})
    user.refresh_from_db()
    assert resp.status_code == 200 and user.line_link_code in resp.content.decode()
    resp = client.post(reverse("accounts:line_link"), {"action": "unlink"})
    assert resp.status_code == 302
    user.refresh_from_db()
    assert user.line_user_id == ""


@pytest.mark.django_db
def test_line_link_requires_login(client):
    assert client.get(reverse("accounts:line_link")).status_code == 302


@pytest.mark.django_db
def test_profile_has_line_button(client):
    client.force_login(make_student())
    assert reverse("accounts:line_link") in client.get(reverse("accounts:profile")).content.decode()
