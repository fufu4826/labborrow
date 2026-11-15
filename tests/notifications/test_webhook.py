import base64
import hashlib
import hmac
import json
from datetime import timedelta
from unittest import mock

import pytest
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from notifications import linking
from notifications.models import NotificationEvent, NotificationLog
from tests.factories import make_student

SECRET = "test-secret"


def sign(body: bytes, secret=SECRET):
    return base64.b64encode(hmac.new(secret.encode(), body, hashlib.sha256).digest()).decode()


def post(client, payload, signature=None):
    body = json.dumps(payload).encode()
    headers = {} if signature is False else {"HTTP_X_LINE_SIGNATURE": signature or sign(body)}
    return client.post(reverse("notifications:line_webhook"), data=body, content_type="application/json", **headers)


def text_event(text, uid="Uabc"):
    return {"events": [{"type": "message", "replyToken": "rt", "source": {"userId": uid},
                        "message": {"type": "text", "text": text}}]}


@pytest.mark.django_db
def test_tc18_bad_signature_returns_400(client):
    assert post(client, {"events": []}, signature="bogus").status_code == 400
    assert post(client, {"events": []}, signature=False).status_code == 400


@pytest.mark.django_db
@override_settings(LINE_CHANNEL_SECRET="")
def test_empty_secret_returns_400(client):
    assert post(client, {"events": []}, signature=sign(b"x", "")).status_code == 400


@pytest.mark.django_db
def test_get_not_allowed(client):
    assert client.get(reverse("notifications:line_webhook")).status_code == 405


@pytest.mark.django_db
def test_valid_code_links_account(client, django_capture_on_commit_callbacks):
    user = make_student()
    other = make_student(line_user_id="Uabc")
    code = linking.create_link_code(user)
    with mock.patch("requests.post") as rp, django_capture_on_commit_callbacks(execute=True):
        resp = post(client, text_event(f" {code} "))
    assert resp.status_code == 200
    rp.assert_not_called()  # no token configured in test settings
    user.refresh_from_db()
    other.refresh_from_db()
    assert user.line_user_id == "Uabc" and user.line_link_code == ""
    assert other.line_user_id == ""
    assert NotificationLog.objects.filter(user=user, event=NotificationEvent.LINE_LINKED).count() == 1


@pytest.mark.django_db
@override_settings(LINE_CHANNEL_ACCESS_TOKEN="tok")
def test_reply_sent_when_token_configured(client, django_capture_on_commit_callbacks):
    user = make_student()
    code = linking.create_link_code(user)
    with mock.patch("requests.post") as rp, django_capture_on_commit_callbacks(execute=True):
        rp.return_value.status_code = 200
        assert post(client, text_event(code)).status_code == 200
    urls = [c.args[0] for c in rp.call_args_list]
    assert any(u.endswith("/message/reply") for u in urls)


@pytest.mark.django_db
@override_settings(LINE_CHANNEL_ACCESS_TOKEN="tok")
def test_reply_exception_does_not_bubble(client):
    with mock.patch("requests.post", side_effect=RuntimeError("boom")):
        assert post(client, text_event("hello")).status_code == 200


@pytest.mark.django_db
def test_expired_code_does_not_link(client):
    user = make_student()
    code = linking.create_link_code(user)
    user.line_link_expires = timezone.now() - timedelta(minutes=1)
    user.save()
    assert post(client, text_event(code)).status_code == 200
    user.refresh_from_db()
    assert user.line_user_id == ""
    assert not NotificationLog.objects.filter(event=NotificationEvent.LINE_LINKED).exists()


@pytest.mark.django_db
def test_unfollow_unlinks(client):
    user = make_student(line_user_id="Uxyz")
    resp = post(client, {"events": [{"type": "unfollow", "source": {"userId": "Uxyz"}}]})
    assert resp.status_code == 200
    user.refresh_from_db()
    assert user.line_user_id == ""


@pytest.mark.django_db
def test_unknown_event_returns_200(client):
    assert post(client, {"events": [{"type": "beacon"}, "junk"]}).status_code == 200
    body = b"not json"
    resp = client.post(reverse("notifications:line_webhook"), data=body, content_type="application/json",
                       HTTP_X_LINE_SIGNATURE=sign(body))
    assert resp.status_code == 200
