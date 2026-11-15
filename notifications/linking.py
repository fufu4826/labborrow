"""LINE account linking by 6-digit code (docs/05-line.md)."""
import re
import secrets
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from accounts.models import User

from . import line
from .models import LineLinkAttempt

CODE_TTL = timedelta(minutes=15)
CODE_RE = re.compile(r"^\d{6}$")


class LinkRateLimited(Exception):
    pass


def create_link_code(user):
    now = timezone.now()
    while True:
        code = f"{secrets.randbelow(1_000_000):06d}"
        taken = User.objects.filter(line_link_code=code, line_link_expires__gt=now).exclude(pk=user.pk)
        if not taken.exists():
            break
    user.line_link_code = code
    user.line_link_expires = now + CODE_TTL
    try:
        with transaction.atomic():
            user.save(update_fields=["line_link_code", "line_link_expires"])
    except IntegrityError:
        user.refresh_from_db(fields=["line_link_code", "line_link_expires"])
        return None
    return code


def link_by_code(code, line_user_id, reply_token=""):
    failures = LineLinkAttempt.objects.filter(success=False, created_at__gte=timezone.now() - CODE_TTL)
    if failures.filter(line_user_id=line_user_id).count() >= 5 or failures.count() >= 200:
        LineLinkAttempt.objects.create(line_user_id=line_user_id, success=False)
        if reply_token:
            line.reply(reply_token, _("Too many attempts, please try again later."))
        raise LinkRateLimited
    user = None
    code = (code or "").strip()
    try:
        with transaction.atomic():
            if CODE_RE.fullmatch(code) and line_user_id:
                user = User.objects.select_for_update().filter(
                    line_link_code=code, line_link_expires__gt=timezone.now()).first()
                if user is not None:
                    previous = User.objects.select_for_update().filter(line_user_id=line_user_id).exclude(pk=user.pk)
                    for other in previous:
                        other.line_user_id = None
                        other.save(update_fields=["line_user_id"])
                    user.line_user_id = line_user_id
                    user.line_link_code = ""
                    user.line_link_expires = None
                    user.save(update_fields=["line_user_id", "line_link_code", "line_link_expires"])
    except IntegrityError:
        user = None
    LineLinkAttempt.objects.create(line_user_id=line_user_id, success=user is not None)
    return user


def unlink(line_user_id):
    if not line_user_id:
        return 0
    return User.objects.filter(line_user_id=line_user_id).update(
        line_user_id=None, line_link_code="", line_link_expires=None)
