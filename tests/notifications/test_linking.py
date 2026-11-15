from datetime import timedelta
from unittest import mock

import pytest
from django.urls import reverse
from django.utils import timezone

from notifications import linking
from tests.factories import make_student


@pytest.mark.django_db
def test_code_format_and_expiry():
    user = make_student()
    code = linking.create_link_code(user)
    user.refresh_from_db()
    assert len(code) == 6 and code.isdigit() and user.line_link_code == code
    delta = user.line_link_expires - timezone.now()
    assert timedelta(minutes=14) < delta <= timedelta(minutes=15)


@pytest.mark.django_db
def test_code_unique_among_unexpired():
    a, b = make_student(), make_student()
    first = linking.create_link_code(a)
    with mock.patch("notifications.linking.secrets.randbelow", side_effect=[int(first), 123456]):
        second = linking.create_link_code(b)
    assert second == "123456" != first


@pytest.mark.django_db
def test_link_by_code_and_unlink():
    user = make_student()
    code = linking.create_link_code(user)
    assert linking.link_by_code("abc", "U1") is None
    assert linking.link_by_code(code, "U1") == user
    assert linking.link_by_code(code, "U2") is None  # code cleared
    assert linking.unlink("U1") == 1
    user.refresh_from_db()
    assert user.line_user_id is None
    assert user.line_link_code == "" and user.line_link_expires is None


@pytest.mark.django_db
def test_line_link_view_generate_and_unlink(client):
    user = make_student(line_user_id="Uold")
    client.force_login(user)
    resp = client.get(reverse("accounts:line_link"))
    assert resp.status_code == 200
    resp = client.post(reverse("accounts:line_link"), {"action": "generate"})
    user.refresh_from_db()
    assert resp.status_code == 200 and user.line_link_code in resp.content.decode()
    resp = client.post(reverse("accounts:line_link"), {"action": "unlink"})
    assert resp.status_code == 302
    user.refresh_from_db()
    assert user.line_user_id is None
    assert user.line_link_code == "" and user.line_link_expires is None


@pytest.mark.django_db
def test_line_link_requires_login(client):
    assert client.get(reverse("accounts:line_link")).status_code == 302


@pytest.mark.django_db
def test_profile_has_line_button(client):
    client.force_login(make_student())
    assert reverse("accounts:line_link") in client.get(reverse("accounts:profile")).content.decode()


@pytest.mark.django_db
@pytest.mark.parametrize("global_limit", [False, True])
def test_guess_rate_limit(global_limit):
    from notifications.models import LineLinkAttempt

    user = make_student()
    code = linking.create_link_code(user)
    attempts = [LineLinkAttempt(line_user_id=f"U{i}" if global_limit else "Uguess", success=False)
                for i in range(200 if global_limit else 5)]
    LineLinkAttempt.objects.bulk_create(attempts)
    with mock.patch("notifications.linking.line.reply") as reply, pytest.raises(linking.LinkRateLimited):
        linking.link_by_code(code, "Uguess", reply_token="reply")
    reply.assert_called_once()
    assert str(reply.call_args.args[1]) == "Too many attempts, please try again later."
    user.refresh_from_db()
    assert user.line_user_id is None and user.line_link_code == code
    assert LineLinkAttempt.objects.count() == len(attempts) + 1


@pytest.mark.django_db
def test_old_failures_and_successes_do_not_block():
    from notifications.models import LineLinkAttempt

    old = LineLinkAttempt.objects.create(line_user_id="Uguess", success=False)
    LineLinkAttempt.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(minutes=16))
    LineLinkAttempt.objects.bulk_create([LineLinkAttempt(line_user_id="Uguess", success=True) for _ in range(5)])
    user = make_student()
    assert linking.link_by_code(linking.create_link_code(user), "Uguess") == user
    assert LineLinkAttempt.objects.filter(success=True).count() == 6


@pytest.mark.django_db
def test_link_integrity_error_rolls_back_transfer():
    from django.db import IntegrityError

    previous = make_student(line_user_id="Uexisting")
    user = make_student()
    code = linking.create_link_code(user)
    original_save = type(user).save

    def save(instance, *args, **kwargs):
        if instance.pk == user.pk:
            raise IntegrityError("collision")
        return original_save(instance, *args, **kwargs)

    with mock.patch.object(type(user), "save", save):
        assert linking.link_by_code(code, "Uexisting") is None
    previous.refresh_from_db()
    user.refresh_from_db()
    assert previous.line_user_id == "Uexisting"
    assert user.line_user_id is None and user.line_link_code == code


@pytest.mark.django_db
def test_generate_integrity_error_does_not_500(client):
    from django.db import IntegrityError

    user = make_student()
    client.force_login(user)
    with mock.patch("notifications.linking.User.save", side_effect=IntegrityError("collision")):
        response = client.post(reverse("accounts:line_link"), {"action": "generate"})
    assert response.status_code == 200


@pytest.mark.django_db
def test_code_generation_retries_beyond_fifty_collisions():
    previous, user = make_student(), make_student()
    previous.line_link_code = "111111"
    previous.line_link_expires = timezone.now() + timedelta(minutes=15)
    previous.save()
    with mock.patch("notifications.linking.secrets.randbelow", side_effect=[111111] * 51 + [222222]):
        assert linking.create_link_code(user) == "222222"
