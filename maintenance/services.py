"""Damage report business logic (docs/01-data-model.md counting rule)."""
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from accounts.models import Role
from inventory.models import Equipment
from inventory.services import resize_image
from notifications.models import NotificationEvent
from notifications.services import notify_staff

from .models import COUNTED, DamageReport, DamageSource, RepairStatus

S = RepairStatus
TRANSITIONS = {
    S.REPORTED: [S.CONFIRMED, S.IN_REPAIR, S.REJECTED],
    S.CONFIRMED: [S.IN_REPAIR, S.REPAIRED, S.WRITTEN_OFF],
    S.IN_REPAIR: [S.REPAIRED, S.WRITTEN_OFF],
}
RESOLVED = (S.REPAIRED, S.WRITTEN_OFF, S.REJECTED)


def _is_staff(user):
    return user.is_authenticated and (user.is_superuser or user.role == Role.STAFF)


def allowed_next(report):
    return TRANSITIONS.get(report.status, [])


def report_damage(user, equipment, quantity, problem, description="", image=None):
    if not user.is_authenticated or not user.is_active:
        raise PermissionDenied
    try:
        quantity = int(quantity)
    except (TypeError, ValueError):
        raise ValidationError(_("Invalid quantity.")) from None
    if quantity < 1 or quantity > equipment.usable_quantity:
        raise ValidationError(_("Quantity must be between 1 and %(max)s.") % {"max": equipment.usable_quantity})
    with transaction.atomic():
        report = DamageReport.objects.create(
            equipment=equipment, reported_by=user, quantity=quantity, problem=problem,
            description=description, image=image or "", source=DamageSource.USER, status=S.REPORTED)
        if report.image:
            resize_image(report.image)
        notify_staff(NotificationEvent.DAMAGE_REPORTED,
                     {"items": f"{equipment.display_name} x{quantity}", "reason": problem}, related=report)
    return report


def change_status(report, actor, new_status, staff_note=""):
    if not _is_staff(actor):
        raise PermissionDenied
    with transaction.atomic():
        report = DamageReport.objects.select_for_update().get(pk=report.pk)
        if new_status not in TRANSITIONS.get(report.status, []):
            raise ValidationError(_("This status change is not allowed."))
        eq = Equipment.objects.select_for_update().get(pk=report.equipment_id)
        qty = report.quantity
        if new_status in COUNTED and report.status not in COUNTED:
            eq.quantity_out_of_service = min(eq.quantity_out_of_service + qty, eq.quantity_total)
        elif new_status == S.REPAIRED:
            eq.quantity_out_of_service = max(eq.quantity_out_of_service - qty, 0)
        elif new_status == S.WRITTEN_OFF:
            if eq.quantity_total - qty <= 0:
                eq.quantity_total = 1
                eq.quantity_out_of_service = 1
                eq.is_active = False
            else:
                eq.quantity_total -= qty
                eq.quantity_out_of_service = max(eq.quantity_out_of_service - qty, 0)
        eq.save()
        report.status = new_status
        report.handled_by = actor
        if staff_note:
            report.staff_note = staff_note
        if new_status in RESOLVED:
            report.resolved_at = timezone.now()
        report.save()
    return report
