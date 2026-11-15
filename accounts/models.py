from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.translation import gettext_lazy as _


class Role(models.TextChoices):
    STUDENT = "student", _("Student")
    TEACHER = "teacher", _("Teacher")
    STAFF = "staff", _("Lab staff / Administrator")


class User(AbstractUser):
    """Custom user. Lab staff and administrators share the STAFF role (same rights)."""

    role = models.CharField(_("role"), max_length=10, choices=Role.choices, default=Role.STUDENT)
    student_id = models.CharField(_("student / staff ID"), max_length=20, blank=True)
    phone = models.CharField(_("phone"), max_length=20, blank=True)
    department = models.CharField(_("department / program"), max_length=150, blank=True)
    language = models.CharField(_("language"), max_length=2, choices=[("th", "ไทย"), ("en", "English")],
                                default="th")
    # NULL when not linked (unique allows many NULLs on SQLite and MySQL; never store "").
    line_user_id = models.CharField(_("LINE user ID"), max_length=64, null=True, blank=True, unique=True)
    line_link_code = models.CharField(max_length=6, blank=True)
    line_link_expires = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = _("user")
        verbose_name_plural = _("users")

    def __str__(self):
        return self.get_full_name() or self.username

    @property
    def is_lab_staff(self):
        return self.role == Role.STAFF or self.is_superuser

    @property
    def is_borrower(self):
        return self.role in (Role.STUDENT, Role.TEACHER)
