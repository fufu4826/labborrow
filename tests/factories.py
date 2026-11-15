"""Plain-function test factories shared by every app's tests. Extend, do not rename."""
import itertools

from accounts.models import Role, User

_seq = itertools.count(1)


def make_user(role=Role.STUDENT, password="pass12345!", **kw):
    n = next(_seq)
    kw.setdefault("username", f"user{n}")
    kw.setdefault("first_name", f"First{n}")
    kw.setdefault("last_name", f"Last{n}")
    kw.setdefault("email", f"user{n}@example.com")
    user = User(role=role, **kw)
    user.set_password(password)
    user.save()
    return user


def make_student(**kw):
    return make_user(Role.STUDENT, **kw)


def make_teacher(**kw):
    return make_user(Role.TEACHER, **kw)


def make_staff(**kw):
    return make_user(Role.STAFF, **kw)
