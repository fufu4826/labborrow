import pytest
from django.core.management import call_command

from accounts.models import Role, User
from borrowing.models import BorrowRequest, RequestStatus
from inventory.models import Category, Equipment


@pytest.mark.django_db
def test_seed_demo_twice_keeps_counts():
    call_command("seed_demo")
    call_command("seed_demo")

    assert User.objects.count() == 8
    assert Category.objects.count() == 5
    assert Equipment.objects.count() == 40
    assert User.objects.get(username="staff1").role == Role.STAFF


@pytest.mark.django_db
def test_seed_demo_reset_reseeds():
    call_command("seed_demo")
    call_command("seed_demo", reset=True)

    assert User.objects.count() == 8
    assert Equipment.objects.filter(asset_code__startswith="CHEM-").count() == 40


@pytest.mark.django_db
def test_seed_demo_with_activity_is_idempotent():
    call_command("seed_demo", "--with-activity")
    first = BorrowRequest.objects.count()
    call_command("seed_demo", "--with-activity")

    assert BorrowRequest.objects.count() == first
    assert first > 100
    assert BorrowRequest.objects.filter(status=RequestStatus.OVERDUE).exists()
    assert BorrowRequest.objects.filter(status=RequestStatus.RETURNED).exists()
