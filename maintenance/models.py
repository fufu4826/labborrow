from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from core.models import TimeStampedModel
from core.uploads import RandomName
from inventory.models import Equipment


class RepairStatus(models.TextChoices):
    REPORTED = "reported", _("Reported")
    CONFIRMED = "confirmed", _("Confirmed damaged")
    IN_REPAIR = "in_repair", _("Under repair")
    REPAIRED = "repaired", _("Repaired")
    WRITTEN_OFF = "written_off", _("Written off")
    REJECTED = "rejected", _("Not damaged")


COUNTED = [RepairStatus.CONFIRMED, RepairStatus.IN_REPAIR]
OPEN = [RepairStatus.REPORTED, RepairStatus.CONFIRMED, RepairStatus.IN_REPAIR]


class DamageSource(models.TextChoices):
    USER = "user", _("Reported by user")
    RETURN = "return", _("Found at return")


class DamageReport(TimeStampedModel):
    equipment = models.ForeignKey(Equipment, on_delete=models.PROTECT, related_name="damage_reports",
                                  verbose_name=_("equipment"))
    reported_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
                                    related_name="damage_reports", verbose_name=_("reported by"))
    quantity = models.PositiveIntegerField(_("quantity"), default=1, validators=[MinValueValidator(1)])
    problem = models.CharField(_("problem"), max_length=150)
    description = models.TextField(_("description"), blank=True)
    image = models.ImageField(_("image"), upload_to=RandomName("damage"), blank=True)
    source = models.CharField(_("source"), max_length=10, choices=DamageSource.choices, default=DamageSource.USER)
    return_item = models.ForeignKey("borrowing.ReturnItem", on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name="damage_reports")
    status = models.CharField(_("status"), max_length=12, choices=RepairStatus.choices,
                              default=RepairStatus.REPORTED, db_index=True)
    staff_note = models.TextField(_("staff note"), blank=True)
    handled_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name="+", verbose_name=_("handled by"))
    resolved_at = models.DateTimeField(_("resolved at"), null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("damage report")
        verbose_name_plural = _("damage reports")

    def __str__(self):
        return f"DMG-{self.pk:05d}" if self.pk else "DMG-new"

    def get_absolute_url(self):
        return reverse("maintenance:detail", args=[self.pk])
