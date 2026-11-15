from pathlib import Path

import polib
import pytest
from django.conf import settings
from django.urls import reverse


def test_tc10_switch_language_to_english(student_client, student):
    student.language = "th"
    student.save()
    th_page = student_client.get(reverse("core:home")).content.decode()
    assert "ค้นหาอุปกรณ์" in th_page

    student_client.post(reverse("core:set_language"), {"language": "en", "next": "/"})
    en_page = student_client.get(reverse("core:home")).content.decode()
    assert "Find equipment" in en_page
    assert "ค้นหาอุปกรณ์" not in en_page


@pytest.mark.django_db
def test_login_page_thai_by_default(client, settings):
    settings.LANGUAGE_CODE = "th"
    page = client.get(reverse("accounts:login"), HTTP_ACCEPT_LANGUAGE="th").content.decode()
    assert "เข้าสู่ระบบ" in page


def test_thai_catalog_complete_and_compiled():
    po_path = Path(settings.LOCALE_PATHS[0]) / "th" / "LC_MESSAGES" / "django.po"
    po = polib.pofile(str(po_path))
    assert po.percent_translated() == 100
    assert po_path.with_suffix(".mo").exists()
