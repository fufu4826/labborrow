import datetime

from django.core.validators import MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        abstract = True


class SystemSetting(TimeStampedModel):
    """Single-row table of borrowing rules that staff can edit (see docs/01-data-model.md)."""

    max_items_per_request = models.PositiveSmallIntegerField(
        _("max items per request"), default=5, validators=[MinValueValidator(1)])
    max_borrow_days = models.PositiveSmallIntegerField(
        _("max borrow days"), default=7, validators=[MinValueValidator(1)])
    max_advance_booking_days = models.PositiveSmallIntegerField(
        _("max advance booking days"), default=14, validators=[MinValueValidator(0)])
    open_time = models.TimeField(_("opening time"), default=datetime.time(8, 30))
    close_time = models.TimeField(_("closing time"), default=datetime.time(16, 30))
    open_weekdays = models.CharField(
        _("open weekdays"), max_length=20, default="0,1,2,3,4",
        help_text=_("Comma separated, Monday=0 ... Sunday=6"))
    due_reminder_hours = models.PositiveSmallIntegerField(_("due reminder (hours before)"), default=24)
    cancel_before_hours = models.PositiveSmallIntegerField(
        _("cancel allowed until (hours before start)"), default=2)

    class Meta:
        verbose_name = _("system setting")
        verbose_name_plural = _("system settings")

    def __str__(self):
        return str(_("System settings"))

    def save(self, *args, **kwargs):
        self.pk = 1
        existing = type(self).objects.filter(pk=1).values_list("created_at", flat=True).first()
        if existing is not None:
            self._state.adding = False
            self.created_at = existing
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _created = cls.objects.get_or_create(pk=1)
        return obj

    @property
    def weekday_list(self):
        return [int(x) for x in self.open_weekdays.split(",") if x.strip().isdigit()]
