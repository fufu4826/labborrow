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
    assert other.line_user_id is None
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
    assert next(c for c in rp.call_args_list if c.args[0].endswith("/message/reply")).kwargs["timeout"] == 5


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
    assert user.line_user_id is None
    assert not NotificationLog.objects.filter(event=NotificationEvent.LINE_LINKED).exists()


@pytest.mark.django_db
def test_unfollow_unlinks(client):
    user = make_student(line_user_id="Uxyz", line_link_code="123456",
                        line_link_expires=timezone.now() + timedelta(minutes=15))
    resp = post(client, {"events": [{"type": "unfollow", "source": {"userId": "Uxyz"}}]})
    assert resp.status_code == 200
    user.refresh_from_db()
    assert user.line_user_id is None
    assert user.line_link_code == "" and user.line_link_expires is None


@pytest.mark.django_db
def test_unknown_event_returns_200(client):
    assert post(client, {"events": [{"type": "beacon"}, "junk"]}).status_code == 200
    body = b"not json"
    resp = client.post(reverse("notifications:line_webhook"), data=body, content_type="application/json",
                       HTTP_X_LINE_SIGNATURE=sign(body))
    assert resp.status_code == 200


@pytest.mark.django_db
@pytest.mark.parametrize("signature", ["???????", "?", "!!!!", "A" * 44])
def test_malformed_signature_returns_400(client, signature):
    assert post(client, {"events": []}, signature=signature).status_code == 400


@pytest.mark.django_db
def test_duplicate_event_processed_once(client):
    from notifications.models import LineWebhookEvent

    event = {"webhookEventId": "event-1", "type": "follow"}
    with mock.patch("notifications.views._handle_event") as handle:
        assert post(client, {"events": [event, event]}).status_code == 200
        event["deliveryContext"] = {"isRedelivery": True}
        assert post(client, {"events": [event]}).status_code == 200
    handle.assert_called_once()
    assert LineWebhookEvent.objects.count() == 1


@pytest.mark.django_db
def test_failing_event_does_not_stop_next_event(client):
    events = [{"webhookEventId": f"event-{i}", "type": "follow"} for i in range(2)]
    with mock.patch("notifications.views._handle_event", side_effect=[RuntimeError("boom"), None]) as handle:
        assert post(client, {"events": events}).status_code == 200
    assert handle.call_count == 2


@pytest.mark.django_db
def test_old_webhook_events_pruned(client):
    from notifications.models import LineWebhookEvent

    old = LineWebhookEvent.objects.create(event_id="old")
    LineWebhookEvent.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=8))
    fresh = LineWebhookEvent.objects.create(event_id="fresh")
    assert post(client, {"events": []}).status_code == 200
    assert list(LineWebhookEvent.objects.values_list("pk", flat=True)) == [fresh.pk]


@pytest.mark.django_db
def test_rate_limit_reply_without_help_reply(client):
    from notifications.models import LineLinkAttempt

    LineLinkAttempt.objects.bulk_create([LineLinkAttempt(line_user_id="Uabc") for _ in range(5)])
    with mock.patch("notifications.line.reply") as reply:
        assert post(client, text_event("123456")).status_code == 200
    reply.assert_called_once()
    assert str(reply.call_args.args[1]) == "Too many attempts, please try again later."
