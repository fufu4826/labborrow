"""LINE Messaging API helpers: webhook signature check and reply messages."""
import base64
import hashlib
import hmac
import logging

import requests
from django.conf import settings

log = logging.getLogger(__name__)
REPLY_URL = "https://api.line.me/v2/bot/message/reply"


def verify_signature(body: bytes, signature: str) -> bool:
    secret = settings.LINE_CHANNEL_SECRET
    if not secret or not signature:
        return False
    digest = hmac.new(secret.encode(), body, hashlib.sha256).digest()
    expected = base64.b64encode(digest)
    try:
        return hmac.compare_digest(expected, signature.encode("ascii"))
    except (UnicodeError, AttributeError, TypeError):
        return False


def reply(reply_token: str, text: str) -> bool:
    """Reply to a webhook event. No-op without a token; never raises."""
    token = settings.LINE_CHANNEL_ACCESS_TOKEN
    if not token or not reply_token:
        return False
    try:
        resp = requests.post(
            REPLY_URL, timeout=5,
            headers={"Authorization": f"Bearer {token}"},
            json={"replyToken": reply_token, "messages": [{"type": "text", "text": text[:4900]}]},
        )
        if not 200 <= resp.status_code < 300:
            log.warning("LINE reply failed: %s %s", resp.status_code, resp.text[:200])
            return False
        return True
    except Exception as exc:  # noqa: BLE001 - never bubble up to the webhook
        log.warning("LINE reply error: %s", exc)
        return False
