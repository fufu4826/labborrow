from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST
from django.views.generic import UpdateView
from django.views.i18n import set_language as django_set_language

from .forms import SystemSettingForm
from .models import SystemSetting
from .permissions import StaffRequiredMixin


@require_POST
def set_language(request):
    """Switch language and remember it on the user (FR-14)."""
    lang = request.POST.get("language")
    if request.user.is_authenticated and lang in dict(settings.LANGUAGES):
        request.user.language = lang
        request.user.save(update_fields=["language"])
    return django_set_language(request)


@login_required
def home(request):
    return render(request, "core/home.html")


class SystemSettingUpdateView(StaffRequiredMixin, UpdateView):
    model = SystemSetting
    form_class = SystemSettingForm
    template_name = "core/settings_form.html"
    success_url = reverse_lazy("core:settings")

    def get_object(self, queryset=None):
        return SystemSetting.load()

    def form_valid(self, form):
        messages.success(self.request, _("Settings saved."))
        return super().form_valid(form)
