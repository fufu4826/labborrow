"""Role checks used by every view (docs/03-permissions.md)."""
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied

from accounts.models import Role

BORROWERS = (Role.STUDENT, Role.TEACHER)
STAFF = (Role.STAFF,)
ALL_ROLES = (Role.STUDENT, Role.TEACHER, Role.STAFF)


def has_role(user, roles):
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return user.role in roles


class RoleRequiredMixin(LoginRequiredMixin):
    roles = ALL_ROLES

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not has_role(request.user, self.roles):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)


class StaffRequiredMixin(RoleRequiredMixin):
    roles = STAFF


class BorrowerRequiredMixin(RoleRequiredMixin):
    roles = BORROWERS


def role_required(*roles):
    def decorator(view):
        @login_required
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            if not has_role(request.user, roles):
                raise PermissionDenied
            return view(request, *args, **kwargs)
        return wrapped
    return decorator


staff_required = role_required(*STAFF)
borrower_required = role_required(*BORROWERS)
