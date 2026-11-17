from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from core.models import TimeStampedModel
from core.uploads import RandomName
from inventory.models import Equipment

User = settings.AUTH_USER_MODEL


class BookingStatus(models.TextChoices):
    ACTIVE = "active", _("Active")
    CANCELLED = "cancelled", _("Cancelled")
    CONVERTED = "converted", _("Converted to request")
    EXPIRED = "expired", _("Expired")


class RequestStatus(models.TextChoices):
    PENDING = "pending", _("Pending approval")
    APPROVED = "approved", _("Approved")
    REJECTED = "rejected", _("Rejected")
    CANCELLED = "cancelled", _("Cancelled")
    BORROWED = "borrowed", _("On loan")
    OVERDUE = "overdue", _("Overdue")
    RETURNED = "returned", _("Returned")


HOLDING_BOOKING = [BookingStatus.ACTIVE]
HOLDING_REQUEST = [RequestStatus.PENDING, RequestStatus.APPROVED, RequestStatus.BORROWED, RequestStatus.OVERDUE]
ON_LOAN = [RequestStatus.BORROWED, RequestStatus.OVERDUE]


class Booking(TimeStampedModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="bookings", verbose_name=_("user"))
    equipment = models.ForeignKey(Equipment, on_delete=models.PROTECT, related_name="bookings",
                                  verbose_name=_("equipment"))
    quantity = models.PositiveIntegerField(_("quantity"), default=1, validators=[MinValueValidator(1)])
    start_at = models.DateTimeField(_("start"))
    end_at = models.DateTimeField(_("end"))
    status = models.CharField(_("status"), max_length=10, choices=BookingStatus.choices,
                              default=BookingStatus.ACTIVE, db_index=True)
    note = models.CharField(_("note"), max_length=255, blank=True)
    cancelled_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    cancelled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-start_at"]
        verbose_name = _("booking")
        verbose_name_plural = _("bookings")
        indexes = [models.Index(fields=["equipment", "status", "start_at", "end_at"])]

    def __str__(self):
        return f"BK-{self.pk:05d}" if self.pk else "BK-new"


class BorrowRequest(TimeStampedModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="borrow_requests",
                             verbose_name=_("borrower"))
    booking = models.OneToOneField(Booking, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name="request", verbose_name=_("booking"))
    purpose = models.CharField(_("purpose"), max_length=255)
    borrow_at = models.DateTimeField(_("borrow at"))
    due_at = models.DateTimeField(_("due at"))
    status = models.CharField(_("status"), max_length=10, choices=RequestStatus.choices,
                              default=RequestStatus.PENDING, db_index=True)
    reject_reason = models.CharField(_("reason for rejection"), max_length=255, blank=True)
    decided_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
                                   verbose_name=_("decided by"))
    decided_at = models.DateTimeField(null=True, blank=True)
    handed_over_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    handed_over_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    cancelled_at = models.DateTimeField(null=True, blank=True)
    reminder_sent_at = models.DateTimeField(null=True, blank=True)
    overdue_notified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("borrow request")
        verbose_name_plural = _("borrow requests")
        indexes = [models.Index(fields=["status", "borrow_at", "due_at"])]

    def __str__(self):
        return self.code

    @property
    def code(self):
        if not self.pk:
            return "REQ-new"
        year = self.created_at.year if self.created_at else 0
        return f"REQ-{year}{self.pk:05d}"

    @property
    def total_quantity(self):
        return sum(i.quantity for i in self.items.all())

    def get_absolute_url(self):
        return reverse("borrowing:request_detail", args=[self.pk])


class BorrowItem(TimeStampedModel):
    request = models.ForeignKey(BorrowRequest, on_delete=models.CASCADE, related_name="items")
    equipment = models.ForeignKey(Equipment, on_delete=models.PROTECT, related_name="borrow_items",
                                  verbose_name=_("equipment"))
    quantity = models.PositiveIntegerField(_("quantity"), default=1, validators=[MinValueValidator(1)])

    class Meta:
        verbose_name = _("borrowed item")
        verbose_name_plural = _("borrowed items")

    def __str__(self):
        return f"{self.equipment} x{self.quantity}"


class Return(TimeStampedModel):
    request = models.OneToOneField(BorrowRequest, on_delete=models.CASCADE, related_name="return_record")
    returned_at = models.DateTimeField(_("returned at"))
    received_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="+",
                                    verbose_name=_("received by"))
    note = models.TextField(_("note"), blank=True)

    class Meta:
        verbose_name = _("return")
        verbose_name_plural = _("returns")

    def __str__(self):
        return f"{self.request.code} return"


class ReturnItem(TimeStampedModel):
    return_record = models.ForeignKey(Return, on_delete=models.CASCADE, related_name="items")
    borrow_item = models.ForeignKey(BorrowItem, on_delete=models.CASCADE, related_name="return_items")
    quantity_good = models.PositiveIntegerField(_("good"), default=0)
    quantity_damaged = models.PositiveIntegerField(_("damaged"), default=0)
    note = models.CharField(_("note"), max_length=255, blank=True)

    def __str__(self):
        return f"{self.borrow_item}: {self.quantity_good} good / {self.quantity_damaged} damaged"


class ConditionImage(TimeStampedModel):
    return_record = models.ForeignKey(Return, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(_("image"), upload_to=RandomName("returns"))
    caption = models.CharField(_("caption"), max_length=150, blank=True)

    def __str__(self):
        return self.caption or self.image.name
