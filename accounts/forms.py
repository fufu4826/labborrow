from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.utils.translation import gettext_lazy as _

from .models import Role, User


class SignUpForm(UserCreationForm):
    role = forms.ChoiceField(
        label=_("I am a"),
        choices=[(Role.STUDENT.value, Role.STUDENT.label), (Role.TEACHER.value, Role.TEACHER.label)],
        initial=Role.STUDENT.value,
    )

    class Meta:
        model = User
        fields = ("username", "first_name", "last_name", "email", "phone", "student_id", "department", "role")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ("first_name", "last_name", "email"):
            self.fields[name].required = True


class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ("first_name", "last_name", "email", "phone", "department", "language")


class StaffUserForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ("role", "is_active", "first_name", "last_name", "email", "phone", "student_id",
                  "department")

    def __init__(self, *args, acting_user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.acting_user = acting_user

    def clean(self):
        cleaned = super().clean()
        me = self.acting_user
        if me is not None and self.instance.pk == me.pk:
            if cleaned.get("role") and cleaned["role"] != Role.STAFF:
                self.add_error("role", _("You cannot remove your own staff role."))
            if "is_active" in cleaned and not cleaned["is_active"]:
                self.add_error("is_active", _("You cannot deactivate your own account."))
        return cleaned
