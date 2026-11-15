import pytest
from django.urls import reverse

from inventory.models import Category, Equipment


@pytest.fixture
def eq(db):
    cat = Category.objects.create(name_th="แก้ว")
    return Equipment.objects.create(asset_code="G-1", name_th="บีกเกอร์", category=cat)


def test_tc02_student_cannot_manage_equipment(student_client, eq):
    cat = eq.category
    urls = [
        reverse("inventory:create"),
        reverse("inventory:update", args=[eq.pk]),
        reverse("inventory:delete", args=[eq.pk]),
        reverse("inventory:category_list"),
        reverse("inventory:category_create"),
        reverse("inventory:category_update", args=[cat.pk]),
        reverse("inventory:category_delete", args=[cat.pk]),
    ]
    for url in urls:
        assert student_client.get(url).status_code == 403, url
        assert student_client.post(url, {}).status_code == 403, url
    eq.refresh_from_db()
    assert eq.is_active


def test_anonymous_redirected_to_login(client, eq):
    resp = client.get(reverse("inventory:list"))
    assert resp.status_code == 302


def test_student_can_view_list_and_detail(student_client, eq):
    assert student_client.get(reverse("inventory:list")).status_code == 200
    resp = student_client.get(reverse("inventory:detail", args=[eq.pk]))
    assert resp.status_code == 200
    assert b"inventory/" not in resp.content or b"/edit/" not in resp.content
