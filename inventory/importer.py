"""Excel import of equipment (all-or-nothing, optional dry run)."""
from dataclasses import dataclass, field

from django.db import transaction
from django.utils.translation import gettext as _
from openpyxl import Workbook, load_workbook

from .models import Category, Equipment

MAX_ROWS = 2000
MAX_BYTES = 5 * 1024 * 1024
HEADERS = ["asset_code", "name_th", "name_en", "category_th", "category_en", "quantity_total",
           "location", "description"]
REQUIRED = ["asset_code", "name_th", "category_th", "quantity_total"]
EXAMPLE = ["CHEM-GL-001", "บีกเกอร์ 250 มล.", "Beaker 250 mL", "เครื่องแก้ว", "Glassware", 20, "ตู้ A1",
           "บีกเกอร์แก้วทนความร้อน"]
HELP = [
    ("asset_code", "รหัสครุภัณฑ์ (จำเป็น, ไม่เกิน 30 ตัวอักษร, ห้ามซ้ำ) ถ้ามีอยู่แล้วจะอัปเดตรายการเดิม"),
    ("name_th", "ชื่อภาษาไทย (จำเป็น, ไม่เกิน 150 ตัวอักษร)"),
    ("name_en", "ชื่อภาษาอังกฤษ (ไม่บังคับ)"),
    ("category_th", "ชื่อหมวดหมู่ภาษาไทย (จำเป็น) ถ้ายังไม่มีจะสร้างหมวดหมู่ใหม่"),
    ("category_en", "ชื่อหมวดหมู่ภาษาอังกฤษ (ไม่บังคับ)"),
    ("quantity_total", "จำนวนทั้งหมด (จำเป็น, จำนวนเต็มตั้งแต่ 1 ขึ้นไป)"),
    ("location", "สถานที่เก็บ (ไม่บังคับ, ไม่เกิน 100 ตัวอักษร)"),
    ("description", "รายละเอียดเพิ่มเติม (ไม่บังคับ)"),
]


@dataclass
class ImportResult:
    created: int = 0
    updated: int = 0
    errors: list = field(default_factory=list)  # [(row_number, message)]

    @property
    def ok(self):
        return not self.errors


class _Rollback(Exception):
    pass


def build_template():
    wb = Workbook()
    ws = wb.active
    ws.title = "equipment"
    ws.append(HEADERS)
    ws.append(EXAMPLE)
    help_ws = wb.create_sheet("คำอธิบาย")
    help_ws.append(["คอลัมน์", "คำอธิบาย"])
    for row in HELP:
        help_ws.append(list(row))
    help_ws.column_dimensions["A"].width = 18
    help_ws.column_dimensions["B"].width = 90
    for col in "ABCDEFGH":
        ws.column_dimensions[col].width = 20
    return wb


def _text(value):
    return "" if value is None else str(value).strip()


def _parse_quantity(value):
    if isinstance(value, bool):
        raise ValueError
    if isinstance(value, float):
        if not value.is_integer():
            raise ValueError
        return int(value)
    if isinstance(value, int):
        return value
    return int(_text(value))


def _read_rows(file_obj):
    wb = load_workbook(file_obj, read_only=True, data_only=True)
    try:
        rows = wb.worksheets[0].iter_rows(values_only=True)
        yield next(rows, None)
        yield from enumerate(rows, start=2)
    finally:
        wb.close()


def _apply_row(row_no, data, result, cache):
    code, name_th, cat_th = data["asset_code"], data["name_th"], data["category_th"]
    missing = [k for k in REQUIRED[:3] if not data[k]]
    if missing:
        result.errors.append((row_no, _("Missing required value: %(cols)s") % {"cols": ", ".join(missing)}))
        return
    try:
        qty = _parse_quantity(data["quantity_total"])
        if qty < 1:
            raise ValueError
    except (ValueError, TypeError):
        result.errors.append((row_no, _("quantity_total must be a whole number of at least 1.")))
        return
    for key, limit in (("asset_code", 30), ("name_th", 150), ("name_en", 150), ("location", 100),
                       ("category_th", 100), ("category_en", 100)):
        if len(data[key]) > limit:
            result.errors.append((row_no, _("%(col)s is longer than %(n)d characters.")
                                  % {"col": key, "n": limit}))
            return
    if code in cache["codes"]:
        result.errors.append((row_no, _("Duplicate asset_code in file: %(code)s") % {"code": code}))
        return
    cache["codes"].add(code)

    category = cache["categories"].get(cat_th)
    if category is None:
        category = Category.objects.filter(name_th=cat_th).first()
        if category is None:
            category = Category.objects.create(name_th=cat_th, name_en=data["category_en"])
        elif data["category_en"] and category.name_en != data["category_en"]:
            category.name_en = data["category_en"]
            category.save(update_fields=["name_en", "updated_at"])
        cache["categories"][cat_th] = category

    eq = Equipment.objects.filter(asset_code=code).first()
    if eq is None:
        Equipment.objects.create(asset_code=code, name_th=name_th, name_en=data["name_en"],
                                 category=category, description=data["description"],
                                 location=data["location"], quantity_total=qty)
        result.created += 1
        return
    if qty < eq.quantity_out_of_service:
        result.errors.append((row_no, _("quantity_total (%(q)d) is below the quantity out of service "
                                        "(%(o)d).") % {"q": qty, "o": eq.quantity_out_of_service}))
        return
    eq.name_th, eq.name_en, eq.category = name_th, data["name_en"], category
    eq.description, eq.location, eq.quantity_total = data["description"], data["location"], qty
    eq.is_active = True
    eq.save()
    result.updated += 1


def import_equipment(file_obj, dry_run=False):
    result = ImportResult()
    try:
        size = getattr(file_obj, "size", None)
        if size is None and hasattr(file_obj, "seek"):
            file_obj.seek(0, 2)
            size = file_obj.tell()
            file_obj.seek(0)
        if size is not None and size > MAX_BYTES:
            result.errors.append((0, _("File is larger than 5 MB.")))
            return result
        reader = _read_rows(file_obj)
        header = next(reader)
    except Exception:
        result.errors.append((0, _("The file is not a valid .xlsx workbook.")))
        return result
    keys = [_text(h).lower() for h in (header or ())]
    absent = [k for k in REQUIRED if k not in keys]
    if absent:
        result.errors.append((1, _("Missing header column(s): %(cols)s") % {"cols": ", ".join(absent)}))
        return result
    index = {k: keys.index(k) for k in HEADERS if k in keys}
    cache = {"codes": set(), "categories": {}}
    try:
        with transaction.atomic():
            count = 0
            for row_no, values in reader:
                values = tuple(values or ())
                if all(v is None or _text(v) == "" for v in values):
                    continue
                count += 1
                if count > MAX_ROWS:
                    result.errors.append((row_no, _("Too many rows (maximum %(n)d).") % {"n": MAX_ROWS}))
                    break
                data = {}
                for k in HEADERS:
                    i = index.get(k)
                    raw = values[i] if i is not None and i < len(values) else None
                    data[k] = raw if k == "quantity_total" else _text(raw)
                _apply_row(row_no, data, result, cache)
            if result.errors or dry_run:
                raise _Rollback
    except _Rollback:
        pass
    except Exception:
        result.errors.append((0, _("The file could not be read.")))
    return result
