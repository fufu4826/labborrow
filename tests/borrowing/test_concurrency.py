from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from django.core.exceptions import ValidationError
from django.db import close_old_connections, connection

from borrowing.models import Booking
from borrowing.services import create_booking
from core.models import SystemSetting
from tests.borrowing.test_booking import equipment, window
from tests.factories import make_student

pytestmark = pytest.mark.django_db(transaction=True)


def test_tc14_last_unit_sequential():
    eq, first, second = equipment(quantity=1), make_student(), make_student()
    start, end = window()
    create_booking(first, eq, 1, start, end)
    with pytest.raises(ValidationError):
        create_booking(second, eq, 1, start, end)
    assert Booking.objects.count() == 1


@pytest.mark.skipif(connection.vendor != "mysql", reason="SQLite does not implement row locks")
def test_tc14_last_unit_concurrent_mysql():
    SystemSetting.load()
    eq, first, second = equipment(quantity=1), make_student(), make_student()
    start, end = window()
    barrier = Barrier(2)

    def book(user):
        close_old_connections()
        try:
            barrier.wait(timeout=10)
            create_booking(user, eq, 1, start, end)
            return "created"
        except ValidationError:
            return "unavailable"
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(book, [first, second]))
    assert sorted(results) == ["created", "unavailable"]
    assert Booking.objects.count() == 1
