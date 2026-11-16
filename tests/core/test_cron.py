from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from borrowing.models import BorrowItem, BorrowRequest, RequestStatus
from inventory.models import Category, Equipment
from tests.factories import make_student

pytestmark = pytest.mark.django_db

URL = reverse("core:cron")


def test_disabled_without_token(client, settings):
    settings.CRON_TOKEN = ""
    assert client.post(URL, HTTP_X_CRON_TOKEN="").status_code == 404


def test_wrong_token_forbidden(client, settings):
    settings.CRON_TOKEN = "right-token"
    assert client.post(URL, HTTP_X_CRON_TOKEN="wrong").status_code == 403
    assert client.post(URL).status_code == 403


def test_get_not_allowed(client, settings):
    settings.CRON_TOKEN = "right-token"
    assert client.get(URL, HTTP_X_CRON_TOKEN="right-token").status_code == 405


def test_runs_due_checks(client, settings):
    settings.CRON_TOKEN = "right-token"
    cat = Category.objects.create(name_th="แก้ว")
    eq = Equipment.objects.create(asset_code="C-1", name_th="บีกเกอร์", category=cat, quantity_total=2)
    now = timezone.now()
    req = BorrowRequest.objects.create(user=make_student(), purpose="x", borrow_at=now - timedelta(days=2),
                                       due_at=now - timedelta(hours=1), status=RequestStatus.BORROWED)
    BorrowItem.objects.create(request=req, equipment=eq, quantity=1)

    resp = client.post(URL, HTTP_X_CRON_TOKEN="right-token")

    assert resp.status_code == 200
    assert resp.json()["overdue"] == 1
    req.refresh_from_db()
    assert req.status == RequestStatus.OVERDUE
