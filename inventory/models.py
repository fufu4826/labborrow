from django.core.validators import MinValueValidator
from django.db import models
from django.urls import reverse
from django.utils.translation import get_language
from django.utils.translation import gettext_lazy as _

from core.models import TimeStampedModel
from core.uploads import RandomName


class Category(TimeStampedModel):
    name_th = models.CharField(_("name (Thai)"), max_length=100)
    name_en = models.CharField(_("name (English)"), max_length=100, blank=True)
    description = models.TextField(_("description"), blank=True)

    class Meta:
        ordering = ["name_th"]
        verbose_name = _("category")
        verbose_name_plural = _("categories")

    def __str__(self):
        return self.display_name

    @property
    def display_name(self):
        if get_language() == "en" and self.name_en:
            return self.name_en
        return self.name_th


class AdminStatus(models.TextChoices):
    AVAILABLE = "available", _("Available")
    UNAVAILABLE = "unavailable", _("Unavailable")


class DisplayStatus(models.TextChoices):
    """Computed status shown to users (docs/02)."""
    AVAILABLE = "available", _("Available")
    RESERVED = "reserved", _("Reserved")
    BORROWED = "borrowed", _("On loan")
    REPAIRING = "repairing", _("Under repair")
    DAMAGED = "damaged", _("Damaged")
    UNAVAILABLE = "unavailable", _("Unavailable")


class EquipmentQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_active=True)


class Equipment(TimeStampedModel):
    asset_code = models.CharField(_("asset code"), max_length=30, unique=True)
    name_th = models.CharField(_("name (Thai)"), max_length=150)
    name_en = models.CharField(_("name (English)"), max_length=150, blank=True)
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="equipment",
                                 verbose_name=_("category"))
    description = models.TextField(_("description"), blank=True)
    location = models.CharField(_("storage location"), max_length=100, blank=True)
    image = models.ImageField(_("image"), upload_to=RandomName("equipment"), blank=True)
    quantity_total = models.PositiveIntegerField(_("total quantity"), default=1,
                                                 validators=[MinValueValidator(1)])
    quantity_out_of_service = models.PositiveIntegerField(_("quantity out of service"), default=0)
    status = models.CharField(_("status"), max_length=12, choices=AdminStatus.choices,
                              default=AdminStatus.AVAILABLE)
    is_active = models.BooleanField(_("active"), default=True)

    objects = EquipmentQuerySet.as_manager()

    class Meta:
        ordering = ["asset_code"]
        verbose_name = _("equipment")
        verbose_name_plural = _("equipment")

    def __str__(self):
        return f"{self.asset_code} {self.display_name}"

    def get_absolute_url(self):
        return reverse("inventory:detail", args=[self.pk])

    @property
    def display_name(self):
        if get_language() == "en" and self.name_en:
            return self.name_en
        return self.name_th

    @property
    def usable_quantity(self):
        return max(self.quantity_total - self.quantity_out_of_service, 0)

    @property
    def is_bookable(self):
        return self.is_active and self.status == AdminStatus.AVAILABLE and self.usable_quantity > 0
