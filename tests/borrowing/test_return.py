import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile

from borrowing.models import RequestStatus, Return
from borrowing.services import approve, create_request, hand_over, receive_return
from borrowing.state import TransitionError
from maintenance.models import DamageReport, DamageSource, RepairStatus
from notifications.models import NotificationEvent as E
from notifications.models import NotificationLog
from tests.borrowing.test_booking import equipment, window
from tests.factories import make_staff, make_student

pytestmark = pytest.mark.django_db


def loan():
    user, staff, eq = make_student(), make_staff(), equipment()
    req = create_request(user, [(eq, 3)], *window(), "Lab")
    approve(req, staff)
    hand_over(req, staff)
    return req, staff, eq


def test_tc07_damaged_return():
    req, staff, eq = loan()
    item = req.items.get()
    record = receive_return(req, staff, {item.pk: (1, 2, "Cracked glass")})
    eq.refresh_from_db()
    assert req.status == RequestStatus.RETURNED
    assert eq.quantity_out_of_service == 2
    report = DamageReport.objects.get()
    assert report.source == DamageSource.RETURN
    assert report.status == RepairStatus.CONFIRMED
    assert report.quantity == 2 and report.reported_by == staff
    assert report.problem == "Cracked glass"
    assert report.return_item == record.items.get()
    assert NotificationLog.objects.get(event=E.RETURNED).user == req.user
    with pytest.raises(TransitionError):
        receive_return(req, staff, {item.pk: (1, 2, "Cracked glass")})
    eq.refresh_from_db()
    assert eq.quantity_out_of_service == 2


@pytest.mark.parametrize("result", [(1, 1, ""), (-1, 4, ""), (True, 2, ""), (1.5, 1.5, "")])
def test_tc07_return_quantities_must_match(result):
    req, staff, eq = loan()
    with pytest.raises(ValidationError):
        receive_return(req, staff, {req.items.get().pk: result})
    req.refresh_from_db()
    eq.refresh_from_db()
    assert req.status == RequestStatus.BORROWED
    assert eq.quantity_out_of_service == 0
    assert not Return.objects.exists()
    assert not DamageReport.objects.exists()


def test_tc07_missing_or_foreign_item_refused():
    req, staff, _eq = loan()
    for results in ({}, {req.items.get().pk + 100: (3, 0, "")}):
        with pytest.raises(ValidationError):
            receive_return(req, staff, results)
    assert not Return.objects.exists()


def test_tc07_condition_images_and_limit(settings):
    settings.STORAGES = {
        **settings.STORAGES,
        "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
    }
    req, staff, _eq = loan()
    images = [SimpleUploadedFile(f"condition{i}.gif", b"GIF89a", content_type="image/gif") for i in range(6)]
    with pytest.raises(ValidationError):
        receive_return(req, staff, {req.items.get().pk: (3, 0, "")}, images=images)
    assert not Return.objects.exists()
    record = receive_return(req, staff, {req.items.get().pk: (3, 0, "")}, images=images[:5])
    assert record.images.count() == 5
    assert all(image.image.storage.exists(image.image.name) for image in record.images.all())
    assert not DamageReport.objects.exists()


def test_tc07_damage_never_exceeds_total():
    req, staff, eq = loan()
    eq.quantity_out_of_service = 4
    eq.save(update_fields=["quantity_out_of_service"])
    receive_return(req, staff, {req.items.get().pk: (0, 3, "")})
    eq.refresh_from_db()
    assert eq.quantity_out_of_service == eq.quantity_total
    assert DamageReport.objects.get().quantity == 3
