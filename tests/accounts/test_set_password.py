import pytest
from django.urls import reverse

from tests.factories import make_staff, make_student

pytestmark = pytest.mark.django_db

NEW_PW = "Fr3sh-start-pw!"


def _url(user):
    return reverse("accounts:user_set_password", args=[user.pk])


def test_staff_sets_password_and_user_can_log_in(staff_client):
    target = make_student(username="forgetful")
    resp = staff_client.post(_url(target), {"new_password1": NEW_PW, "new_password2": NEW_PW})
    assert resp.status_code == 302
    assert resp.url == reverse("accounts:user_edit", args=[target.pk])
    target.refresh_from_db()
    assert target.check_password(NEW_PW)

    staff_client.logout()
    assert staff_client.login(username="forgetful", password=NEW_PW)


def test_success_message_and_edit_button(staff_client):
    target = make_student(first_name="Ann", last_name="Lee")
    resp = staff_client.post(_url(target), {"new_password1": NEW_PW, "new_password2": NEW_PW}, follow=True)
    assert "Password updated for Ann Lee." in [str(m) for m in resp.context["messages"]]
    assert reverse("accounts:user_set_password", args=[target.pk]) in resp.content.decode()


def test_set_password_page_renders_for_staff(staff_client):
    target = make_student()
    resp = staff_client.get(_url(target))
    assert resp.status_code == 200
    assert "form" in resp.context


def test_student_gets_403(student_client):
    target = make_student()
    assert student_client.get(_url(target)).status_code == 403
    assert student_client.post(_url(target), {"new_password1": NEW_PW, "new_password2": NEW_PW}).status_code == 403
    assert target.check_password("pass12345!")


def test_staff_on_own_account_redirected(staff_client, staff):
    resp = staff_client.post(_url(staff), {"new_password1": NEW_PW, "new_password2": NEW_PW})
    assert resp.status_code == 302
    assert resp.url == reverse("accounts:password_change")
    staff.refresh_from_db()
    assert staff.check_password("pass12345!")


def test_staff_cannot_reset_superuser(staff_client):
    root = make_student(is_superuser=True)
    resp = staff_client.post(_url(root), {"new_password1": NEW_PW, "new_password2": NEW_PW})
    assert resp.status_code == 403
    root.refresh_from_db()
    assert root.check_password("pass12345!")


def test_superuser_staff_can_reset_superuser(client):
    admin_user = make_staff(is_superuser=True)
    root = make_student(is_superuser=True)
    client.force_login(admin_user)
    resp = client.post(_url(root), {"new_password1": NEW_PW, "new_password2": NEW_PW})
    assert resp.status_code == 302
    root.refresh_from_db()
    assert root.check_password(NEW_PW)


def test_weak_password_rejected(staff_client):
    target = make_student()
    resp = staff_client.post(_url(target), {"new_password1": "123", "new_password2": "123"})
    assert resp.status_code == 200
    assert resp.context["form"].errors
    target.refresh_from_db()
    assert target.check_password("pass12345!")
