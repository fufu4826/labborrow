"""Bootstrap form rendering without third-party packages.

Usage in templates:  {% load form_tags %}  {% bs_form form %}   or   {{ form.field|bs_field }}
"""
from django import forms, template
from django.utils.html import format_html, format_html_join
from django.utils.safestring import mark_safe

register = template.Library()


def _add_class(field):
    widget = field.field.widget
    if isinstance(widget, (forms.CheckboxInput,)):
        css = "form-check-input"
    elif isinstance(widget, (forms.Select, forms.SelectMultiple)):
        css = "form-select"
    elif isinstance(widget, forms.CheckboxSelectMultiple | forms.RadioSelect):
        css = ""
    else:
        css = "form-control"
    if field.errors:
        css += " is-invalid"
    existing = widget.attrs.get("class", "")
    return field.as_widget(attrs={"class": f"{existing} {css}".strip()})


@register.filter
def bs_field(field):
    if field.is_hidden:
        return mark_safe(str(field))
    errors = format_html_join("", '<div class="invalid-feedback d-block">{}</div>', ((e,) for e in field.errors))
    if isinstance(field.field.widget, forms.CheckboxSelectMultiple | forms.RadioSelect):
        options = format_html_join(
            "",
            '<div class="form-check form-check-inline">{}<label class="form-check-label" for="{}">{}</label></div>',
            ((sub.tag(), sub.id_for_label, sub.choice_label) for sub in field.subwidgets),
        )
        options = options.replace('<input ', '<input class="form-check-input" ')
        return format_html('<div class="mb-3"><div class="form-label">{}</div>{}{}</div>',
                           field.label, mark_safe(options), errors)
    widget_html = _add_class(field)
    help_text = format_html('<div class="form-text">{}</div>', field.help_text) if field.help_text else ""
    if isinstance(field.field.widget, forms.CheckboxInput):
        return format_html(
            '<div class="form-check mb-3">{}<label class="form-check-label" for="{}">{}</label>{}{}</div>',
            widget_html, field.id_for_label, field.label, errors, help_text)
    required = mark_safe(' <span class="text-danger">*</span>') if field.field.required else ""
    return format_html('<div class="mb-3"><label class="form-label" for="{}">{}{}</label>{}{}{}</div>',
                       field.id_for_label, field.label, required, widget_html, errors, help_text)


@register.simple_tag
def bs_form(form):
    parts = []
    for err in form.non_field_errors():
        parts.append(format_html('<div class="alert alert-danger">{}</div>', err))
    for field in form:
        parts.append(bs_field(field))
    return mark_safe("".join(str(p) for p in parts))
