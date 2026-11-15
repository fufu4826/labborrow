from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import PasswordChangeView
from django.db.models import Q
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.views.generic import CreateView, ListView, UpdateView

from core.permissions import StaffRequiredMixin

from .forms import ProfileForm, SignUpForm, StaffUserForm
from .models import Role, User


class SignUpView(CreateView):
    form_class = SignUpForm
    template_name = "accounts/signup.html"

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect("core:home")
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        self.object = form.save()
        login(self.request, self.object, backend="django.contrib.auth.backends.ModelBackend")
        messages.success(self.request, _("Welcome! Your account has been created."))
        return redirect("core:home")


class ProfileView(LoginRequiredMixin, UpdateView):
    form_class = ProfileForm
    template_name = "accounts/profile.html"
    success_url = reverse_lazy("accounts:profile")

    def get_object(self, queryset=None):
        return self.request.user

    def form_valid(self, form):
        messages.success(self.request, _("Profile updated."))
        return super().form_valid(form)


class PasswordChange(LoginRequiredMixin, PasswordChangeView):
    template_name = "accounts/password_change.html"
    success_url = reverse_lazy("accounts:profile")

    def form_valid(self, form):
        messages.success(self.request, _("Password changed."))
        return super().form_valid(form)


class UserListView(StaffRequiredMixin, ListView):
    model = User
    template_name = "accounts/user_list.html"
    paginate_by = 20
    context_object_name = "users"

    def get_queryset(self):
        qs = User.objects.order_by("username")
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(
                Q(username__icontains=q) | Q(first_name__icontains=q) | Q(last_name__icontains=q)
                | Q(student_id__icontains=q)
            )
        role = self.request.GET.get("role", "")
        if role in Role.values:
            qs = qs.filter(role=role)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        params = self.request.GET.copy()
        params.pop("page", None)
        ctx.update(q=self.request.GET.get("q", ""), role=self.request.GET.get("role", ""),
                   roles=Role.choices, querystring=params.urlencode())
        return ctx


class UserEditView(StaffRequiredMixin, UpdateView):
    model = User
    form_class = StaffUserForm
    template_name = "accounts/user_edit.html"
    success_url = reverse_lazy("accounts:user_list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["acting_user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, _("User updated."))
        return super().form_valid(form)
