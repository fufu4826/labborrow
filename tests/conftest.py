import pytest

from tests.factories import make_staff, make_student, make_teacher


@pytest.fixture
def student(db):
    return make_student()


@pytest.fixture
def teacher(db):
    return make_teacher()


@pytest.fixture
def staff(db):
    return make_staff()


@pytest.fixture
def student_client(client, student):
    client.force_login(student)
    return client


@pytest.fixture
def staff_client(client, staff):
    client.force_login(staff)
    return client
