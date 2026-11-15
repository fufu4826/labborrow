from unittest import mock

import pytest
from django.core.management import call_command
from django.test import override_settings
from django.urls import reverse

from notifications.models import NotificationEvent, NotificationStatus
from notifications.services import notify, render_message, retry_failed
from tests.factories import make_student


def resp(status, text=""):
    m = mock.Mock()
    m.status_code, m.text = status, text
    return m


@pytest.mark.django_db
@override_settings(LINE_CHANNEL_ACCESS_TOKEN="tok")
def test_send_success(django_capture_on_commit_callbacks):
    user = make_student(line_user_id="U1")
    with mock.patch("requests.post", return_value=resp(200)) as rp, django_capture_on_commit_callbacks(execute=True):
        entry = notify(user, NotificationEvent.LINE_LINKED)
    entry.refresh_from_db()
    assert entry.status == NotificationStatus.SENT and entry.attempts == 1 and entry.sent_at
    headers = rp.call_args.kwargs["headers"]
    assert headers["Authorization"] == "Bearer tok"
    assert headers["X-Line-Retry-Key"] == str(entry.retry_key)


@pytest.mark.django_db
@override_settings(LINE_CHANNEL_ACCESS_TOKEN="tok")
def test_send_failure_records_error(django_capture_on_commit_callbacks):
    user = make_student(line_user_id="U1")
    with mock.patch("requests.post", return_value=resp(500, "oops")), django_capture_on_commit_callbacks(execute=True):
        entry = notify(user, NotificationEvent.LINE_LINKED)
    entry.refresh_from_db()
    assert entry.status == NotificationStatus.FAILED and entry.error.startswith("500") and entry.attempts == 1


@pytest.mark.django_db
@override_settings(LINE_CHANNEL_ACCESS_TOKEN="tok")
def test_no_line_user_id_skipped(django_capture_on_commit_callbacks):
    user = make_student()
    with mock.patch("requests.post") as rp, django_capture_on_commit_callbacks(execute=True):
        entry = notify(user, NotificationEvent.LINE_LINKED)
    entry.refresh_from_db()
    assert entry.status == NotificationStatus.SKIPPED
    rp.assert_not_called()


@pytest.mark.django_db
@override_settings(LINE_CHANNEL_ACCESS_TOKEN="tok")
def test_retry_failed_resends_only_under_max_attempts(django_capture_on_commit_callbacks):
    user = make_student(line_user_id="U1")
    with mock.patch("requests.post", return_value=resp(500)), django_capture_on_commit_callbacks(execute=True):
        failed = notify(user, NotificationEvent.LINE_LINKED)
        exhausted = notify(user, NotificationEvent.LINE_LINKED)
    exhausted.refresh_from_db()
    exhausted.attempts = 3
    exhausted.save()
    with mock.patch("requests.post", return_value=resp(200)) as rp:
        retry_failed()
    assert rp.call_count == 1
    failed.refresh_from_db()
    exhausted.refresh_from_db()
    assert failed.status == NotificationStatus.SENT and failed.attempts == 2
    assert exhausted.status == NotificationStatus.FAILED


@pytest.mark.django_db
def test_render_message_uses_user_language():
    th, en = make_student(language="th"), make_student(language="en")
    m_th = render_message(th, NotificationEvent.LINE_LINKED, {})
    m_en = render_message(en, NotificationEvent.LINE_LINKED, {})
    assert m_th and m_en
    assert m_en.startswith("Your LINE account")


@pytest.mark.django_db
def test_log_list_permissions(client, staff, student):
    url = reverse("notifications:log_list")
    for _i in range(31):
        notify(student, NotificationEvent.LINE_LINKED)
    client.force_login(student)
    assert client.get(url).status_code == 403
    client.force_login(staff)
    r = client.get(url)
    assert r.status_code == 200 and len(r.context["logs"]) == 30
    assert client.get(url, {"status": "pending", "event": "line_linked", "page": 2}).status_code == 200
    assert client.post(url).status_code == 302


@pytest.mark.django_db
def test_retry_command(capsys):
    call_command("retry_notifications")
    assert "Retried 0" in capsys.readouterr().out
