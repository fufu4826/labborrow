import pytest
from django.urls import reverse

from accounts.models import Role, User
from tests.factories import make_staff, make_student

pytestmark = pytest.mark.django_db


def test_tc01_login_wrong_password(client, student):
    resp = client.post(reverse("accounts:login"), {"username": student.username, "password": "nope"})
    assert resp.status_code == 200
    assert resp.context["form"].errors
    assert "_auth_user_id" not in client.session


def _signup_data(**kw):
    data = {"username": "newbie", "first_name": "New", "last_name": "Bie", "email": "n@example.com",
            "phone": "0812345678", "student_id": "6401", "department": "Chem", "role": "teacher",
            "password1": "S3cure-pass-99", "password2": "S3cure-pass-99"}
    data.update(kw)
    return data


def test_tc11_signup_then_use_immediately(client):
    resp = client.post(reverse("accounts:signup"), _signup_data())
    assert resp.status_code == 302
    user = User.objects.get(username="newbie")
    assert user.role == Role.TEACHER
    assert client.session["_auth_user_id"] == str(user.pk)
    assert client.get(reverse("accounts:profile")).status_code == 200


def test_signup_cannot_create_staff(client):
    resp = client.post(reverse("accounts:signup"), _signup_data(role="staff"))
    assert resp.status_code == 200
    assert not User.objects.filter(username="newbie").exists()


def test_signup_redirects_when_authenticated(student_client):
    assert student_client.get(reverse("accounts:signup")).status_code == 302


def test_profile_edit(student_client, student):
    resp = student_client.post(reverse("accounts:profile"), {
        "first_name": "Changed", "last_name": "Name", "email": "c@example.com",
        "phone": "099", "department": "Bio", "language": "en"})
    assert resp.status_code == 302
    student.refresh_from_db()
    assert (student.first_name, student.language) == ("Changed", "en")


def test_password_change(student_client, student):
    resp = student_client.post(reverse("accounts:password_change"), {
        "old_password": "pass12345!", "new_password1": "Br4nd-new-pw!", "new_password2": "Br4nd-new-pw!"})
    assert resp.status_code == 302
    student.refresh_from_db()
    assert student.check_password("Br4nd-new-pw!")


def test_user_list_forbidden_for_student(student_client):
    assert student_client.get(reverse("accounts:user_list")).status_code == 403


def test_user_list_visible_to_staff_with_search_and_filter(staff_client):
    make_student(username="findme", student_id="ZZ99")
    resp = staff_client.get(reverse("accounts:user_list"), {"q": "ZZ99", "role": "student"})
    assert resp.status_code == 200
    assert [u.username for u in resp.context["users"]] == ["findme"]


def test_staff_can_change_other_users_role(staff_client):
    target = make_student()
    resp = staff_client.post(reverse("accounts:user_edit", args=[target.pk]), {
        "role": "staff", "is_active": "on", "first_name": "A", "last_name": "B", "email": "a@example.com"})
    assert resp.status_code == 302
    target.refresh_from_db()
    assert target.role == Role.STAFF


def test_self_demotion_and_deactivation_blocked(staff_client, staff):
    url = reverse("accounts:user_edit", args=[staff.pk])
    resp = staff_client.post(url, {"role": "student", "first_name": "A", "last_name": "B",
                                   "email": "a@example.com"})
    assert resp.status_code == 200
    assert resp.context["form"].errors
    staff.refresh_from_db()
    assert staff.role == Role.STAFF and staff.is_active


def test_user_edit_forbidden_for_student(student_client):
    other = make_staff()
    assert student_client.get(reverse("accounts:user_edit", args=[other.pk])).status_code == 403
