import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from PIL import Image

from inventory.models import Category, Equipment


def make_png(w=3000, h=2000):
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (200, 30, 30)).save(buf, "PNG")
    return SimpleUploadedFile("big.png", buf.getvalue(), content_type="image/png")


@pytest.fixture
def cat(db):
    return Category.objects.create(name_th="เครื่องแก้ว", name_en="Glassware")


def payload(cat, **kw):
    data = {"asset_code": "CH-001", "name_th": "บีกเกอร์", "name_en": "Beaker", "category": cat.pk,
            "description": "", "location": "A1", "quantity_total": 5, "quantity_out_of_service": 0,
            "status": "available", "is_active": "on"}
    data.update(kw)
    return data


def test_tc12_staff_adds_equipment_with_image(staff_client, cat):
    resp = staff_client.post(reverse("inventory:create"), payload(cat, image=make_png()))
    assert resp.status_code == 302
    eq = Equipment.objects.get(asset_code="CH-001")
    assert eq.image
    with Image.open(eq.image.path) as img:
        assert max(img.size) <= 1600
        assert img.format == "JPEG"


def test_out_of_service_cannot_exceed_total(staff_client, cat):
    resp = staff_client.post(reverse("inventory:create"),
                             payload(cat, quantity_total=2, quantity_out_of_service=3))
    assert resp.status_code == 200
    assert not Equipment.objects.exists()


def test_bad_image_type_rejected(staff_client, cat):
    bad = SimpleUploadedFile("x.png", b"not an image", content_type="image/png")
    resp = staff_client.post(reverse("inventory:create"), payload(cat, image=bad))
    assert resp.status_code == 200
    assert not Equipment.objects.exists()


def test_soft_delete(staff_client, cat):
    eq = Equipment.objects.create(asset_code="X1", name_th="ขวด", category=cat)
    url = reverse("inventory:delete", args=[eq.pk])
    assert staff_client.get(url).status_code == 200
    assert staff_client.post(url).status_code == 302
    eq.refresh_from_db()
    assert eq.is_active is False
    resp = staff_client.get(reverse("inventory:list"))
    assert eq not in resp.context["equipment_list"]


def test_category_delete_protected(staff_client, cat):
    Equipment.objects.create(asset_code="X1", name_th="ขวด", category=cat)
    resp = staff_client.post(reverse("inventory:category_delete", args=[cat.pk]), follow=True)
    assert resp.status_code == 200
    assert Category.objects.filter(pk=cat.pk).exists()
    assert "cannot be deleted" in resp.content.decode()


def test_category_crud(staff_client):
    assert staff_client.post(reverse("inventory:category_create"), {"name_th": "สาร"}).status_code == 302
    c = Category.objects.get(name_th="สาร")
    assert staff_client.post(reverse("inventory:category_update", args=[c.pk]),
                             {"name_th": "สารเคมี"}).status_code == 302
    assert staff_client.post(reverse("inventory:category_delete", args=[c.pk])).status_code == 302
    assert not Category.objects.exists()
