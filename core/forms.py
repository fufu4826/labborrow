from django import forms

from .models import SystemSetting


class SystemSettingForm(forms.ModelForm):
    class Meta:
        model = SystemSetting
        fields = ["max_items_per_request", "max_borrow_days", "max_advance_booking_days", "open_time",
                  "close_time", "open_weekdays", "due_reminder_hours", "cancel_before_hours"]
        widgets = {
            "open_time": forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
            "close_time": forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
        }
