import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.urls import reverse

from inventory.models import Category, Equipment
from maintenance import services
from maintenance.models import DamageReport, RepairStatus
from notifications.models import NotificationEvent, NotificationLog
from tests.factories import make_staff, make_student


@pytest.fixture
def eq(db):
    cat = Category.objects.create(name_th="เครื่องแก้ว")
    return Equipment.objects.create(asset_code="D-1", name_th="บีกเกอร์", category=cat, quantity_total=5)


def _reload(obj):
    obj.refresh_from_db()
    return obj


def test_tc16_report_then_staff_confirms_updates_out_of_service(eq, student, staff):
    report = services.report_damage(student, eq, 2, "Cracked")
    assert report.status == RepairStatus.REPORTED
    assert _reload(eq).quantity_out_of_service == 0
    services.change_status(report, staff, RepairStatus.CONFIRMED, "ok")
    assert _reload(eq).quantity_out_of_service == 2
    assert eq.usable_quantity == 3
    services.change_status(report, staff, RepairStatus.IN_REPAIR)
    assert _reload(eq).quantity_out_of_service == 2
    report.refresh_from_db()
    assert report.handled_by == staff and report.staff_note == "ok"


def test_repaired_restores(eq, student, staff):
    report = services.report_damage(student, eq, 2, "Cracked")
    services.change_status(report, staff, RepairStatus.CONFIRMED)
    services.change_status(report, staff, RepairStatus.REPAIRED)
    assert _reload(eq).quantity_out_of_service == 0
    assert _reload(report).resolved_at is not None


def test_written_off_reduces_total(eq, student, staff):
    report = services.report_damage(student, eq, 2, "Broken")
    services.change_status(report, staff, RepairStatus.IN_REPAIR)
    services.change_status(report, staff, RepairStatus.WRITTEN_OFF)
    _reload(eq)
    assert (eq.quantity_total, eq.quantity_out_of_service) == (3, 0)


def test_written_off_last_unit_deactivates(db, student, staff):
    cat = Category.objects.create(name_th="x")
    one = Equipment.objects.create(asset_code="D-2", name_th="หลอด", category=cat, quantity_total=1)
    report = services.report_damage(student, one, 1, "Broken")
    services.change_status(report, staff, RepairStatus.CONFIRMED)
    services.change_status(report, staff, RepairStatus.WRITTEN_OFF)
    _reload(one)
    assert not one.is_active and one.quantity_total == 1 and one.quantity_out_of_service == 1


def test_rejected_no_change(eq, student, staff):
    report = services.report_damage(student, eq, 2, "Maybe")
    services.change_status(report, staff, RepairStatus.REJECTED)
    _reload(eq)
    assert (eq.quantity_total, eq.quantity_out_of_service) == (5, 0)


def test_invalid_move_rejected(eq, student, staff):
    report = services.report_damage(student, eq, 1, "x")
    with pytest.raises(ValidationError):
        services.change_status(report, staff, RepairStatus.REPAIRED)
    services.change_status(report, staff, RepairStatus.REJECTED)
    with pytest.raises(ValidationError):
        services.change_status(report, staff, RepairStatus.CONFIRMED)
    with pytest.raises(PermissionDenied):
        services.change_status(report, student, RepairStatus.CONFIRMED)


def test_quantity_validated(eq, student):
    with pytest.raises(ValidationError):
        services.report_damage(student, eq, 6, "x")
    with pytest.raises(ValidationError):
        services.report_damage(student, eq, 0, "x")


def test_student_cannot_change_status(client, eq, student):
    report = services.report_damage(student, eq, 1, "x")
    client.force_login(student)
    resp = client.post(reverse("maintenance:detail", args=[report.pk]), {"status": "confirmed"})
    assert resp.status_code == 403
    assert _reload(report).status == RepairStatus.REPORTED


def test_staff_changes_status_via_view(client, eq, student, staff):
    report = services.report_damage(student, eq, 1, "x")
    client.force_login(staff)
    resp = client.post(reverse("maintenance:detail", args=[report.pk]),
                       {"status": "confirmed", "staff_note": "yes"})
    assert resp.status_code == 302
    assert _reload(report).status == RepairStatus.CONFIRMED


def test_borrower_sees_only_own_reports(client, eq, student):
    other = make_student()
    mine = services.report_damage(student, eq, 1, "mine-problem")
    theirs = services.report_damage(other, eq, 1, "their-problem")
    client.force_login(student)
    resp = client.get(reverse("maintenance:list"))
    assert resp.status_code == 200
    assert [r.pk for r in resp.context["reports"]] == [mine.pk]
    assert client.get(reverse("maintenance:detail", args=[theirs.pk])).status_code == 403


def test_create_view_prefill_and_submit(client, eq, student):
    client.force_login(student)
    resp = client.get(reverse("maintenance:create") + f"?equipment={eq.pk}")
    assert resp.status_code == 200
    resp = client.post(reverse("maintenance:create"),
                       {"equipment": eq.pk, "quantity": 1, "problem": "Chipped", "description": ""})
    assert resp.status_code == 302
    assert DamageReport.objects.filter(reported_by=student, problem="Chipped").exists()


def test_notification_log_created_for_staff_on_report(eq, student):
    staff = make_staff()
    services.report_damage(student, eq, 1, "Leaking")
    logs = NotificationLog.objects.filter(event=NotificationEvent.DAMAGE_REPORTED)
    assert list(logs.values_list("user", flat=True)) == [staff.pk]
    assert "Leaking" in logs[0].message
