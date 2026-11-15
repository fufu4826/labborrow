from django import forms
from django.utils.translation import gettext_lazy as _

from .models import Category, DisplayStatus, Equipment

MAX_IMAGE_BYTES = 5 * 1024 * 1024
ALLOWED_IMAGE_TYPES = {"JPEG", "PNG", "WEBP"}


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ["name_th", "name_en", "description"]
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}


class EquipmentForm(forms.ModelForm):
    class Meta:
        model = Equipment
        fields = ["asset_code", "name_th", "name_en", "category", "description", "location", "image",
                  "quantity_total", "quantity_out_of_service", "status", "is_active"]
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}

    def clean_image(self):
        image = self.cleaned_data.get("image")
        if image and hasattr(image, "size") and hasattr(image, "image"):
            if image.size > MAX_IMAGE_BYTES:
                raise forms.ValidationError(_("Image must be 5 MB or smaller."))
            if (image.image.format or "").upper() not in ALLOWED_IMAGE_TYPES:
                raise forms.ValidationError(_("Only JPG, PNG or WEBP images are allowed."))
        return image

    def clean(self):
        cleaned = super().clean()
        total = cleaned.get("quantity_total")
        out = cleaned.get("quantity_out_of_service")
        if total is not None and out is not None and out > total:
            self.add_error("quantity_out_of_service",
                           _("Quantity out of service cannot exceed the total quantity."))
        return cleaned


class EquipmentFilterForm(forms.Form):
    q = forms.CharField(label=_("Search"), required=False,
                        widget=forms.TextInput(attrs={"placeholder": _("Name or asset code"),
                                                      "class": "form-control"}))
    category = forms.ModelChoiceField(label=_("Category"), queryset=Category.objects.all(), required=False,
                                      empty_label=_("All categories"),
                                      widget=forms.Select(attrs={"class": "form-select"}))
    status = forms.ChoiceField(label=_("Status"), required=False,
                               choices=[("", _("All statuses")), *DisplayStatus.choices],
                               widget=forms.Select(attrs={"class": "form-select"}))
    date = forms.DateField(label=_("Date"), required=False,
                           widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}))
