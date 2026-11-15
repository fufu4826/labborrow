from django import forms
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from PIL import Image

from inventory.models import Equipment

from .models import RepairStatus

Image.MAX_IMAGE_PIXELS = 40_000_000


class DamageImageField(forms.ImageField):
    def to_python(self, data):
        if data and data.size > 5 * 1024 * 1024:
            raise forms.ValidationError(_("Images must be at most 5 MB."))
        try:
            image = super().to_python(data)
            if image:
                try:
                    with Image.open(image) as opened:
                        if opened.format not in ("JPEG", "PNG", "WEBP"):
                            raise forms.ValidationError(_("Upload a JPEG, PNG or WEBP image."))
                finally:
                    image.seek(0)
        except Image.DecompressionBombError as exc:
            raise forms.ValidationError(_("The image has too many pixels.")) from exc
        return image


class DamageReportForm(forms.Form):
    equipment = forms.ModelChoiceField(Equipment.objects.none(), label=gettext_lazy("Equipment"))
    quantity = forms.IntegerField(min_value=1, initial=1, label=gettext_lazy("Quantity"))
    problem = forms.CharField(max_length=150, label=gettext_lazy("Problem"))
    description = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}),
                                  label=gettext_lazy("Description"))
    image = DamageImageField(required=False, label=gettext_lazy("Photo"))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["equipment"].queryset = Equipment.objects.active()

    def clean(self):
        data = super().clean()
        eq, qty = data.get("equipment"), data.get("quantity")
        if eq and qty and qty > eq.usable_quantity:
            self.add_error("quantity", _("Quantity must be between 1 and %(max)s.") % {"max": eq.usable_quantity})
        return data


class StatusForm(forms.Form):
    status = forms.ChoiceField(label=gettext_lazy("New status"))
    staff_note = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}),
                                 label=gettext_lazy("Staff note"))

    def __init__(self, *args, allowed=(), **kwargs):
        super().__init__(*args, **kwargs)
        labels = dict(RepairStatus.choices)
        self.fields["status"].choices = [(s, labels[s]) for s in allowed]


class StatusFilterForm(forms.Form):
    q = forms.CharField(required=False, label=gettext_lazy("Search"))
    status = forms.ChoiceField(required=False, label=gettext_lazy("Status"),
                               choices=[("", gettext_lazy("All statuses")), *RepairStatus.choices])
