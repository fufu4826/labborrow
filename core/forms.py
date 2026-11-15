from django import forms
from django.utils.translation import gettext_lazy as _

from .models import SystemSetting

WEEKDAYS = [
    ("0", _("Monday")), ("1", _("Tuesday")), ("2", _("Wednesday")), ("3", _("Thursday")),
    ("4", _("Friday")), ("5", _("Saturday")), ("6", _("Sunday")),
]


class SystemSettingForm(forms.ModelForm):
    open_weekdays = forms.MultipleChoiceField(
        label=_("open weekdays"), choices=WEEKDAYS, widget=forms.CheckboxSelectMultiple)

    class Meta:
        model = SystemSetting
        fields = ["max_items_per_request", "max_borrow_days", "max_advance_booking_days", "open_time",
                  "close_time", "open_weekdays", "due_reminder_hours", "cancel_before_hours"]
        widgets = {
            "open_time": forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
            "close_time": forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.initial["open_weekdays"] = [str(d) for d in self.instance.weekday_list]

    def clean_open_weekdays(self):
        return ",".join(sorted(self.cleaned_data["open_weekdays"]))

    def clean(self):
        data = super().clean()
        if data.get("open_time") and data.get("close_time") and data["open_time"] >= data["close_time"]:
            self.add_error("close_time", _("Closing time must be after opening time."))
        return data
