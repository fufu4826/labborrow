import uuid

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from core.models import TimeStampedModel


class NotificationEvent(models.TextChoices):
    LINE_LINKED = "line_linked", _("LINE account linked")
    REQUEST_SUBMITTED = "request_submitted", _("New borrow request")
    REQUEST_APPROVED = "request_approved", _("Request approved")
    REQUEST_REJECTED = "request_rejected", _("Request rejected")
    BOOKING_CREATED = "booking_created", _("Booking created")
    BOOKING_CANCELLED = "booking_cancelled", _("Booking cancelled")
    REQUEST_CANCELLED = "request_cancelled", _("Request cancelled")
    DUE_SOON = "due_soon", _("Return due soon")
    OVERDUE = "overdue", _("Overdue")
    RETURNED = "returned", _("Return confirmed")
    DAMAGE_REPORTED = "damage_reported", _("Damage reported")


class NotificationStatus(models.TextChoices):
    PENDING = "pending", _("Pending")
    SENT = "sent", _("Sent")
    FAILED = "failed", _("Failed")
    SKIPPED = "skipped", _("Skipped (LINE not linked or disabled)")


class NotificationLog(TimeStampedModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications",
                             verbose_name=_("recipient"))
    event = models.CharField(_("event"), max_length=20, choices=NotificationEvent.choices)
    message = models.TextField(_("message"))
    status = models.CharField(_("status"), max_length=8, choices=NotificationStatus.choices,
                              default=NotificationStatus.PENDING, db_index=True)
    attempts = models.PositiveSmallIntegerField(_("attempts"), default=0)
    error = models.CharField(_("error"), max_length=400, blank=True)
    sent_at = models.DateTimeField(_("sent at"), null=True, blank=True)
    related_object = models.CharField(max_length=60, blank=True)
    retry_key = models.UUIDField(default=uuid.uuid4, editable=False)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("notification log")
        verbose_name_plural = _("notification logs")

    def __str__(self):
        return f"{self.get_event_display()} -> {self.user}"
