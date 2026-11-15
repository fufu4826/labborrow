"""Django built-in messages that Django's own Thai catalog leaves untranslated.

Never imported at runtime: listing them here lets `manage.py i18n extract` put them in our catalog, which
takes priority over Django's (LOCALE_PATHS). Thai has one plural form, so plurals need only msgstr[0].
"""
from django.utils.translation import gettext_noop, ngettext


def _messages():  # pragma: no cover - for the extractor only
    gettext_noop("Enter the same password as before, for verification.")
    gettext_noop("Required. 150 characters or fewer. Letters, digits and @/./+/-/_ only.")
    gettext_noop("The password is too similar to the %(verbose_name)s.")
    gettext_noop("Your password can’t be too similar to your other personal information.")
    gettext_noop("This password is too common.")
    gettext_noop("Your password can’t be a commonly used password.")
    gettext_noop("This password is entirely numeric.")
    gettext_noop("Your password can’t be entirely numeric.")
    gettext_noop("Enter a valid username. This value may contain only letters, numbers, and @/./+/-/_ characters.")
    gettext_noop("Enter a valid integer.")
    gettext_noop("Enter a complete value.")
    gettext_noop("%(model_name)s with this %(field_labels)s already exists.")
    ngettext("This password is too short. It must contain at least %d character.",
             "This password is too short. It must contain at least %d characters.", 1)
    ngettext("Your password must contain at least %(min_length)d character.",
             "Your password must contain at least %(min_length)d characters.", 1)
    ngettext("Ensure this value has at least %(limit_value)d character (it has %(show_value)d).",
             "Ensure this value has at least %(limit_value)d characters (it has %(show_value)d).", 1)
    ngettext("Ensure this value has at most %(limit_value)d character (it has %(show_value)d).",
             "Ensure this value has at most %(limit_value)d characters (it has %(show_value)d).", 1)
