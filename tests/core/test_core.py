import pytest
from django.urls import reverse

from core.models import SystemSetting


@pytest.mark.django_db
def test_home_requires_login(client):
    resp = client.get(reverse("core:home"))
    assert resp.status_code == 302
    assert reverse("accounts:login") in resp["Location"]


def test_home_renders_for_student(student_client):
    assert student_client.get(reverse("core:home")).status_code == 200


def test_settings_forbidden_for_student(student_client):
    assert student_client.get(reverse("core:settings")).status_code == 403


def test_settings_staff_can_edit(staff_client):
    url = reverse("core:settings")
    assert staff_client.get(url).status_code == 200
    data = {"max_items_per_request": 3, "max_borrow_days": 5, "max_advance_booking_days": 10,
            "open_time": "08:00", "close_time": "17:00", "open_weekdays": ["0", "1", "2", "3", "5"],
            "due_reminder_hours": 12, "cancel_before_hours": 1}
    resp = staff_client.post(url, data)
    assert resp.status_code == 302
    setting = SystemSetting.load()
    assert setting.max_items_per_request == 3
    assert setting.weekday_list == [0, 1, 2, 3, 5]
    page = staff_client.get(url).content.decode()
    assert 'class="form-check-input"' in page
    assert page.count("checked") == 5


def test_settings_close_must_be_after_open(staff_client):
    data = {"max_items_per_request": 3, "max_borrow_days": 5, "max_advance_booking_days": 10,
            "open_time": "17:00", "close_time": "08:00", "open_weekdays": ["0"],
            "due_reminder_hours": 12, "cancel_before_hours": 1}
    resp = staff_client.post(reverse("core:settings"), data)
    assert resp.status_code == 200
    assert SystemSetting.load().open_time.hour != 17


def test_setting_is_singleton(db):
    SystemSetting.load()
    SystemSetting(max_items_per_request=9).save()
    assert SystemSetting.objects.count() == 1


def test_language_switch_saved_on_user(student_client, student):
    student_client.post(reverse("core:set_language"), {"language": "en", "next": "/"})
    student.refresh_from_db()
    assert student.language == "en"
