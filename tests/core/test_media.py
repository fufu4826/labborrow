from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from borrowing.models import BorrowRequest, ConditionImage, Return
from inventory.models import Category, Equipment
from maintenance.models import DamageReport
from tests.factories import make_staff, make_student

pytestmark = pytest.mark.django_db


@pytest.fixture
def media(settings, tmp_path, monkeypatch, student):
    settings.MEDIA_ROOT = tmp_path
    settings.DEBUG = False
    monkeypatch.delenv("MEDIA_ACCEL", raising=False)
    category = Category.objects.create(name_th="Test")
    equipment = Equipment.objects.create(asset_code="MEDIA", name_th="Test", category=category)
    request = BorrowRequest.objects.create(
        user=student, purpose="Test", borrow_at=timezone.now(), due_at=timezone.now() + timedelta(days=1))
    record = Return.objects.create(request=request, returned_at=timezone.now())
    ConditionImage.objects.create(return_record=record, image="returns/photo.jpg")
    DamageReport.objects.create(equipment=equipment, reported_by=student, problem="Test", image="damage/photo.jpg")
    for folder in ("equipment", "returns", "damage"):
        (tmp_path / folder).mkdir()
        (tmp_path / folder / "photo.jpg").write_bytes(b"photo")
    return tmp_path


@pytest.mark.parametrize("folder", ["equipment", "returns", "damage"])
def test_owner_can_read_media(client, student, media, folder):
    client.force_login(student)
    response = client.get(reverse("core:media", args=[f"{folder}/photo.jpg"]))
    assert response.status_code == 200
    assert b"".join(response.streaming_content) == b"photo"
    response.close()
    assert response["X-Content-Type-Options"] == "nosniff"


@pytest.mark.parametrize("folder", ["returns", "damage"])
def test_other_borrower_cannot_read_media(client, media, folder):
    client.force_login(make_student())
    response = client.get(reverse("core:media", args=[f"{folder}/photo.jpg"]))
    assert response.status_code in (403, 404)


@pytest.mark.parametrize("folder", ["returns", "damage"])
def test_staff_can_read_media(client, media, folder):
    client.force_login(make_staff())
    response = client.get(reverse("core:media", args=[f"{folder}/photo.jpg"]))
    assert response.status_code == 200
    response.close()


@pytest.mark.parametrize("path", [
    "returns/../equipment/photo.jpg", "../equipment/photo.jpg", "/equipment/photo.jpg",
    "C:/equipment/photo.jpg", "equipment/..\\photo.jpg", "unknown/photo.jpg", "damage/missing.jpg",
    "equipment/missing.jpg", "returns/%2e%2e/photo.jpg",
])
def test_invalid_media_path_returns_404(client, student, media, path):
    client.force_login(student)
    assert client.get(reverse("core:media", args=[path])).status_code == 404


def test_anonymous_redirects_to_login(client, media):
    response = client.get(reverse("core:media", args=["returns/photo.jpg"]))
    assert response.status_code == 302
    assert reverse("accounts:login") in response.url


@pytest.mark.parametrize("folder", ["equipment", "returns", "damage"])
def test_accel_redirect_after_authorization(client, student, media, monkeypatch, folder):
    monkeypatch.setenv("MEDIA_ACCEL", "1")
    client.force_login(student)
    response = client.get(reverse("core:media", args=[f"{folder}/photo.jpg"]))
    assert response.status_code == 200
    assert response["X-Accel-Redirect"] == f"/protected-media/{folder}/photo.jpg"
    assert response.content == b""


def test_accel_does_not_bypass_authorization(client, media, monkeypatch):
    monkeypatch.setenv("MEDIA_ACCEL", "1")
    client.force_login(make_student())
    response = client.get(reverse("core:media", args=["returns/photo.jpg"]))
    assert response.status_code == 404
    assert "X-Accel-Redirect" not in response


def test_debug_uses_file_response(client, student, media, settings, monkeypatch):
    monkeypatch.setenv("MEDIA_ACCEL", "1")
    settings.DEBUG = True
    client.force_login(student)
    response = client.get(reverse("core:media", args=["returns/photo.jpg"]))
    assert response.status_code == 200 and response.streaming
    assert "X-Accel-Redirect" not in response
    response.close()
