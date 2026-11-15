import io
import os
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.core.files.base import ContentFile
from django.db.models import Q
from PIL import Image, ImageOps

from borrowing.availability import STATUS_BADGE, available_quantity, display_status, free_now
from core.models import SystemSetting

TZ = ZoneInfo("Asia/Bangkok")


def resize_image(field_file, max_px=1600):
    """Downscale to max_px, apply EXIF orientation, re-save as JPEG (quality 85)."""
    if not field_file:
        return
    field_file.open("rb")
    try:
        img = Image.open(field_file)
        img = ImageOps.exif_transpose(img)
        img.thumbnail((max_px, max_px))
        if img.mode != "RGB":
            img = img.convert("RGB")
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=85, optimize=True)
    finally:
        field_file.close()
    base = os.path.splitext(os.path.basename(field_file.name))[0]
    field_file.save(f"{base}.jpg", ContentFile(buf.getvalue()), save=True)


def _as_time(value):
    """A freshly created SystemSetting row still holds its string defaults."""
    return time.fromisoformat(value) if isinstance(value, str) else value


def day_window(day, setting=None):
    """Open-hours window for a date, or None when the lab is closed that weekday."""
    setting = setting or SystemSetting.load()
    if day.weekday() not in setting.weekday_list:
        return None
    return (datetime.combine(day, _as_time(setting.open_time), tzinfo=TZ),
            datetime.combine(day, _as_time(setting.close_time), tzinfo=TZ))


def free_on_day(equipment, day, setting=None):
    window = day_window(day, setting)
    if window is None:
        return 0
    return available_quantity(equipment, *window)


def availability_strip(equipment, start_day, days=14):
    setting = SystemSetting.load()
    rows = []
    for i in range(days):
        day = start_day + timedelta(days=i)
        closed = day.weekday() not in setting.weekday_list
        rows.append({"date": day, "closed": closed,
                     "free": 0 if closed else free_on_day(equipment, day, setting)})
    return rows


def filter_equipment(qs, cleaned_data):
    """Return a list of equipment annotated with `status_value`, `badge` and `free_qty`."""
    q = (cleaned_data.get("q") or "").strip()
    if q:
        qs = qs.filter(Q(asset_code__icontains=q) | Q(name_th__icontains=q) | Q(name_en__icontains=q))
    if cleaned_data.get("category"):
        qs = qs.filter(category=cleaned_data["category"])
    status = cleaned_data.get("status")
    day = cleaned_data.get("date")
    setting = SystemSetting.load() if day else None
    result = []
    for eq in qs:
        eq.status_value = display_status(eq)
        if status and eq.status_value != status:
            continue
        eq.badge = STATUS_BADGE[eq.status_value]
        eq.free_qty = free_on_day(eq, day, setting) if day else free_now(eq)
        result.append(eq)
    return result
