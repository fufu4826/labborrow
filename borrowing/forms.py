from zoneinfo import ZoneInfo

from django import forms
from django.core.exceptions import ValidationError
from django.forms import formset_factory
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from inventory.models import Equipment

from .models import RequestStatus

LOCAL = ZoneInfo("Asia/Bangkok")
DT_FORMAT = "%Y-%m-%dT%H:%M"
MAX_IMAGES = 5
MAX_IMAGE_BYTES = 5 * 1024 * 1024
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}


class LocalDateTimeField(forms.DateTimeField):
    """`datetime-local` input interpreted in Asia/Bangkok."""

    def __init__(self, **kwargs):
        kwargs.setdefault("widget", forms.DateTimeInput(attrs={"type": "datetime-local"}, format=DT_FORMAT))
        kwargs.setdefault("input_formats", [DT_FORMAT, "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M"])
        super().__init__(**kwargs)

    def to_python(self, value):
        with timezone.override(LOCAL):
            return super().to_python(value)


class BookingForm(forms.Form):
    start_at = LocalDateTimeField(label=_("Start"))
    end_at = LocalDateTimeField(label=_("End"))
    quantity = forms.IntegerField(label=_("Quantity"), min_value=1, initial=1)
    note = forms.CharField(label=_("Note"), max_length=255, required=False)


class ConvertForm(forms.Form):
    purpose = forms.CharField(label=_("Purpose"), max_length=255)


class ItemForm(forms.Form):
    equipment = forms.ModelChoiceField(
        label=_("Equipment"), queryset=Equipment.objects.none(),
        widget=forms.Select(attrs={"class": "form-select"}))
    quantity = forms.IntegerField(
        label=_("Quantity"), min_value=1, initial=1,
        widget=forms.NumberInput(attrs={"class": "form-control", "min": 1}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["equipment"].queryset = Equipment.objects.active().order_by("asset_code")


ItemFormSet = formset_factory(ItemForm, extra=0, min_num=1, validate_min=True)


class RequestForm(forms.Form):
    borrow_at = LocalDateTimeField(label=_("Borrow at"))
    due_at = LocalDateTimeField(label=_("Due at"))
    purpose = forms.CharField(label=_("Purpose"), max_length=255)


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleImageField(forms.ImageField):
    widget = MultipleFileInput(attrs={"accept": "image/*", "multiple": True})

    def clean(self, data, initial=None):
        if not data:
            return []
        files = list(data) if isinstance(data, (list, tuple)) else [data]
        if len(files) > MAX_IMAGES:
            raise ValidationError(_("Upload at most five condition images."))
        cleaned = []
        for f in files:
            if f.size > MAX_IMAGE_BYTES:
                raise ValidationError(_("Each image must be 5 MB or smaller."))
            f = super().clean(f, initial)
            if f.image.format not in ALLOWED_FORMATS:
                raise ValidationError(_("Only JPG, PNG or WebP images are allowed."))
            cleaned.append(f)
        return cleaned


class ReturnForm(forms.Form):
    note = forms.CharField(label=_("General note"), required=False, widget=forms.Textarea(attrs={"rows": 3}))
    images = MultipleImageField(label=_("Condition photos"), required=False,
                                help_text=_("Up to 5 images (JPG, PNG, WebP), 5 MB each."))

    def __init__(self, *args, items, **kwargs):
        super().__init__(*args, **kwargs)
        self.items = list(items)
        num = forms.NumberInput(attrs={"class": "form-control", "min": 0})
        for item in self.items:
            self.fields[f"good_{item.pk}"] = forms.IntegerField(min_value=0, initial=item.quantity, widget=num)
            self.fields[f"damaged_{item.pk}"] = forms.IntegerField(min_value=0, initial=0, widget=num)
            self.fields[f"note_{item.pk}"] = forms.CharField(
                max_length=255, required=False, widget=forms.TextInput(attrs={"class": "form-control"}))

    @property
    def rows(self):
        return [{"item": item, "good": self[f"good_{item.pk}"], "damaged": self[f"damaged_{item.pk}"],
                 "note": self[f"note_{item.pk}"]} for item in self.items]

    def clean(self):
        data = super().clean()
        for item in self.items:
            good, damaged = data.get(f"good_{item.pk}"), data.get(f"damaged_{item.pk}")
            if good is not None and damaged is not None and good + damaged != item.quantity:
                self.add_error(f"good_{item.pk}", _("Good + damaged must equal the borrowed quantity (%(qty)s).")
                               % {"qty": item.quantity})
        return data

    def results(self):
        d = self.cleaned_data
        return {item.pk: (d[f"good_{item.pk}"], d[f"damaged_{item.pk}"], d.get(f"note_{item.pk}", ""))
                for item in self.items}


class HistoryFilterForm(forms.Form):
    date_from = forms.DateField(label=_("From"), required=False, widget=forms.DateInput(attrs={"type": "date"}))
    date_to = forms.DateField(label=_("To"), required=False, widget=forms.DateInput(attrs={"type": "date"}))
    status = forms.ChoiceField(label=_("Status"), required=False,
                               choices=[("", _("All"))] + list(RequestStatus.choices))
    user = forms.CharField(label=_("Borrower"), required=False)
    equipment = forms.ModelChoiceField(label=_("Equipment"), required=False, queryset=Equipment.objects.none(),
                                       empty_label=_("All"))

    def __init__(self, *args, show_user=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["equipment"].queryset = Equipment.objects.order_by("asset_code")
        if not show_user:
            del self.fields["user"]
