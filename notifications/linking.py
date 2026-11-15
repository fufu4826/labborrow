"""LINE account linking by 6-digit code (docs/05-line.md)."""
import re
import secrets
from datetime import timedelta

from django.utils import timezone

from accounts.models import User

CODE_TTL = timedelta(minutes=15)
CODE_RE = re.compile(r"^\d{6}$")


def create_link_code(user):
    now = timezone.now()
    code = ""
    for _attempt in range(50):
        code = f"{secrets.randbelow(1_000_000):06d}"
        taken = User.objects.filter(line_link_code=code, line_link_expires__gt=now).exclude(pk=user.pk)
        if not taken.exists():
            break
    user.line_link_code = code
    user.line_link_expires = now + CODE_TTL
    user.save(update_fields=["line_link_code", "line_link_expires"])
    return code


def link_by_code(code, line_user_id):
    code = (code or "").strip()
    if not CODE_RE.match(code) or not line_user_id:
        return None
    user = User.objects.filter(line_link_code=code, line_link_expires__gt=timezone.now()).first()
    if user is None:
        return None
    User.objects.filter(line_user_id=line_user_id).exclude(pk=user.pk).update(line_user_id="")
    user.line_user_id = line_user_id
    user.line_link_code = ""
    user.line_link_expires = None
    user.save(update_fields=["line_user_id", "line_link_code", "line_link_expires"])
    return user


def unlink(line_user_id):
    if not line_user_id:
        return 0
    return User.objects.filter(line_user_id=line_user_id).update(line_user_id="")
