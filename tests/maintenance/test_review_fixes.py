from io import BytesIO

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from PIL import Image

from maintenance import services
from maintenance.forms import DamageReportForm
from maintenance.models import DamageReport, RepairStatus
from tests.borrowing.test_booking import equipment

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("status", [RepairStatus.CONFIRMED, RepairStatus.IN_REPAIR])
def test_counted_status_rechecks_remaining_usable_units(student, staff, status):
    eq = equipment(quantity=3)
    first = services.report_damage(student, eq, 2, "First")
    second = services.report_damage(student, eq, 2, "Second")
    services.change_status(first, staff, RepairStatus.CONFIRMED)
    with pytest.raises(ValidationError, match="Only 1 usable unit"):
        services.change_status(second, staff, status)
    eq.refresh_from_db()
    second.refresh_from_db()
    assert eq.quantity_out_of_service == 2
    assert second.status == RepairStatus.REPORTED


@pytest.mark.parametrize("status", [RepairStatus.REPAIRED, RepairStatus.WRITTEN_OFF])
@pytest.mark.parametrize("total", [2, 3])
def test_resolving_inconsistent_damage_counts_fails_without_clamping(student, staff, status, total):
    eq = equipment(quantity=total)
    report = services.report_damage(student, eq, 2, "Broken")
    services.change_status(report, staff, RepairStatus.CONFIRMED)
    eq.quantity_out_of_service = 1
    eq.save()
    with pytest.raises(ValidationError, match="inconsistent"):
        services.change_status(report, staff, status)
    eq.refresh_from_db()
    report.refresh_from_db()
    assert (eq.quantity_total, eq.quantity_out_of_service, eq.is_active) == (total, 1, True)
    assert report.status == RepairStatus.CONFIRMED


def image_upload(fmt="PNG", padding=0):
    stream = BytesIO()
    Image.new("RGB", (4, 4)).save(stream, format=fmt)
    return SimpleUploadedFile("photo.png", stream.getvalue() + b"\0" * padding, content_type="image/png")


def damage_form(eq, upload):
    return DamageReportForm({"equipment": eq.pk, "quantity": 1, "problem": "Broken"}, {"image": upload})


@pytest.mark.parametrize("fmt", ["JPEG", "PNG", "WEBP"])
def test_damage_image_accepts_supported_actual_formats(fmt):
    form = damage_form(equipment(), image_upload(fmt))
    assert form.is_valid(), form.errors
    assert form.cleaned_data["image"].read()


@pytest.mark.parametrize("fmt", ["GIF", "BMP", "TIFF"])
def test_damage_image_rejects_disallowed_formats_despite_png_name_and_mime(fmt):
    form = damage_form(equipment(), image_upload(fmt))
    assert not form.is_valid()
    assert "JPEG, PNG or WEBP" in str(form.errors["image"])


def test_damage_image_rejects_over_five_mb():
    form = damage_form(equipment(), image_upload(padding=5 * 1024 * 1024))
    assert not form.is_valid()
    assert "5 MB" in str(form.errors["image"])


def test_damage_image_accepts_exact_five_mb():
    upload = image_upload()
    upload = image_upload(padding=5 * 1024 * 1024 - upload.size)
    assert upload.size == 5 * 1024 * 1024
    form = damage_form(equipment(), upload)
    assert form.is_valid(), form.errors


def test_damage_image_decompression_bomb_becomes_validation_error(monkeypatch):
    upload = image_upload()
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 1)
    form = damage_form(equipment(), upload)
    assert not form.is_valid()
    assert "image" in form.errors


@pytest.mark.parametrize("upload_kind", ["oversize", "unsupported", "bomb"])
def test_damage_upload_view_uses_image_validation(student_client, monkeypatch, upload_kind):
    eq = equipment()
    upload = image_upload("GIF") if upload_kind == "unsupported" else image_upload(
        padding=5 * 1024 * 1024 if upload_kind == "oversize" else 0)
    if upload_kind == "bomb":
        monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 1)
    response = student_client.post(reverse("maintenance:create"), {
        "equipment": eq.pk, "quantity": 1, "problem": "Broken", "image": upload,
    })
    assert response.status_code == 200
    assert "image" in response.context["form"].errors
    assert not DamageReport.objects.exists()
