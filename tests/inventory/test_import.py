import io
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.urls import reverse
from openpyxl import Workbook, load_workbook

from inventory import importer
from inventory.importer import HEADERS, import_equipment
from inventory.models import Category, Equipment

pytestmark = pytest.mark.django_db


def make_xlsx(rows, header=HEADERS):
    wb = Workbook()
    ws = wb.active
    ws.append(header)
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def row(code="A-1", name="บีกเกอร์", cat="เครื่องแก้ว", qty=5, en="Beaker", cat_en="Glassware"):
    return [code, name, en, cat, cat_en, qty, "ตู้ A", ""]


def test_template_download(staff_client):
    resp = staff_client.get(reverse("inventory:import_template"))
    assert resp.status_code == 200
    wb = load_workbook(io.BytesIO(resp.content))
    assert [c.value for c in wb.worksheets[0][1]] == HEADERS
    assert len(wb.sheetnames) == 2


def test_import_creates():
    res = import_equipment(make_xlsx([row("A-1"), row("A-2", cat="โลหะ")]))
    assert (res.created, res.updated, res.errors) == (2, 0, [])
    assert Category.objects.count() == 2
    assert Category.objects.get(name_th="เครื่องแก้ว").name_en == "Glassware"
    assert Equipment.objects.count() == 2


def test_second_import_updates():
    import_equipment(make_xlsx([row("A-1")]))
    Equipment.objects.update(is_active=False)
    res = import_equipment(make_xlsx([row("A-1", name="ใหม่", qty=9)]))
    assert (res.created, res.updated) == (0, 1)
    eq = Equipment.objects.get()
    assert eq.name_th == "ใหม่" and eq.quantity_total == 9 and eq.is_active


def test_bad_rows_roll_back():
    res = import_equipment(make_xlsx([row("A-1"), row("A-2", name=""), row("A-3", qty=0),
                                      row("A-4", qty="abc")]))
    assert [r for r, _m in res.errors] == [3, 4, 5]
    assert res.created == 1
    assert Equipment.objects.count() == 0 and Category.objects.count() == 0


def test_quantity_below_out_of_service():
    import_equipment(make_xlsx([row("A-1", qty=5)]))
    Equipment.objects.update(quantity_out_of_service=3)
    res = import_equipment(make_xlsx([row("A-1", qty=2)]))
    assert [r for r, _m in res.errors] == [2]
    assert Equipment.objects.get().quantity_total == 5


def test_dry_run_saves_nothing():
    res = import_equipment(make_xlsx([row("A-1")]), dry_run=True)
    assert res.created == 1 and not res.errors
    assert Equipment.objects.count() == 0 and Category.objects.count() == 0


def test_view_staff_import_and_dry_run(staff_client):
    url = reverse("inventory:import")
    f = SimpleUploadedFile("e.xlsx", make_xlsx([row("A-1")]).read())
    resp = staff_client.post(url, {"file": f, "dry_run": "on"})
    assert resp.status_code == 200 and Equipment.objects.count() == 0
    f = SimpleUploadedFile("e.xlsx", make_xlsx([row("A-1")]).read())
    resp = staff_client.post(url, {"file": f})
    assert resp.status_code == 302 and Equipment.objects.count() == 1


def test_student_forbidden(student_client):
    assert student_client.get(reverse("inventory:import")).status_code == 403
    assert student_client.get(reverse("inventory:import_template")).status_code == 403


def test_non_xlsx_rejected(staff_client):
    f = SimpleUploadedFile("e.csv", b"a,b")
    resp = staff_client.post(reverse("inventory:import"), {"file": f})
    assert resp.status_code == 200 and resp.context["form"].errors
    f = SimpleUploadedFile("e.xlsx", b"not a workbook")
    resp = staff_client.post(reverse("inventory:import"), {"file": f})
    assert resp.context["result"].errors


def test_command(tmp_path):
    p = tmp_path / "e.xlsx"
    p.write_bytes(make_xlsx([row("A-1")]).read())
    call_command("import_equipment", str(p), "--dry-run")
    assert Equipment.objects.count() == 0
    call_command("import_equipment", str(p))
    assert Equipment.objects.count() == 1


@pytest.mark.parametrize("kind", ["not_zip", "members", "member_size", "total_size", "ratio"])
def test_unsafe_archive_rejected_before_loading(monkeypatch, kind):
    buf = io.BytesIO()
    if kind == "not_zip":
        buf.write(b"not a zip")
    else:
        compression = ZIP_STORED if kind == "total_size" else ZIP_DEFLATED
        with ZipFile(buf, "w", compression=compression) as archive:
            if kind == "members":
                for i in range(201):
                    archive.writestr(str(i), b"")
            elif kind == "member_size":
                archive.writestr("huge.xml", b"x" * (20 * 1024 * 1024 + 1))
            elif kind == "total_size":
                for i in range(3):
                    archive.writestr(str(i), b"x" * (17 * 1024 * 1024))
            else:
                archive.writestr("compressed.xml", b"x" * (1024 * 1024))
    monkeypatch.setattr(importer, "MAX_BYTES", 60 * 1024 * 1024)

    def unexpected_load(*args, **kwargs):
        pytest.fail("Unsafe archive reached openpyxl")

    monkeypatch.setattr(importer, "load_workbook", unexpected_load)
    res = import_equipment(buf)
    assert res.errors and res.errors[0][0] == 0
    assert Equipment.objects.count() == 0


@pytest.mark.parametrize("blank_rows", [False, True])
def test_too_many_physical_rows(monkeypatch, blank_rows):
    monkeypatch.setattr(importer, "MAX_ROWS", 2)
    rows = [row("A-1"), [] if blank_rows else row("A-2"), row("A-3")]
    res = import_equipment(make_xlsx(rows))
    assert res.errors == [(4, importer._("Too many rows (maximum %(n)d).") % {"n": 2})]
    assert Equipment.objects.count() == 0


def test_maximum_rows_accepted(monkeypatch):
    monkeypatch.setattr(importer, "MAX_ROWS", 2)
    res = import_equipment(make_xlsx([row("A-1"), row("A-2")]))
    assert res.errors == [] and res.created == 2


def test_update_preserves_out_of_service_changed_after_load(monkeypatch):
    import_equipment(make_xlsx([row()]))
    original_apply = importer._apply_row
    original_save = Equipment.save

    def change_after_load(row_no, data, result, cache):
        Equipment.objects.filter(asset_code="A-1").update(quantity_out_of_service=3)
        return original_apply(row_no, data, result, cache)

    def check_update_fields(self, *args, **kwargs):
        assert set(kwargs["update_fields"]) == {"name_th", "quantity_total", "updated_at"}
        return original_save(self, *args, **kwargs)

    monkeypatch.setattr(importer, "_apply_row", change_after_load)
    monkeypatch.setattr(Equipment, "save", check_update_fields)
    res = import_equipment(make_xlsx([row(name="Updated", qty=9)]))
    assert res.errors == [] and res.updated == 1
    eq = Equipment.objects.get()
    assert eq.name_th == "Updated" and eq.quantity_total == 9
    assert eq.quantity_out_of_service == 3
