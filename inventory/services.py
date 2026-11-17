import io
import os
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.core.files.base import ContentFile
from django.db.models import Q
from PIL import Image, ImageOps

from borrowing.availability import STATUS_BADGE, available_quantity, bulk_status, peak_quantity
from borrowing.models import HOLDING_BOOKING, HOLDING_REQUEST, ON_LOAN, Booking, BorrowItem
from core.models import SystemSetting
from inventory.models import AdminStatus

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
    old_name = field_file.name
    base = os.path.splitext(os.path.basename(old_name))[0]
    field_file.save(f"{base}.jpg", ContentFile(buf.getvalue()), save=True)
    if old_name != field_file.name:  # e.g. the uploaded .png: keep only the resized .jpg
        field_file.storage.delete(old_name)


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


def _free_on_day_bulk(equipment_list, day, setting):
    window = day_window(day, setting)
    if window is None:
        return {eq.pk: 0 for eq in equipment_list}
    start, end = window
    ids = [eq.pk for eq in equipment_list]
    bookings = Booking.objects.filter(equipment_id__in=ids, status__in=HOLDING_BOOKING,
                                     start_at__lt=end, end_at__gt=start)
    intervals = {pk: [] for pk in ids}
    for booking in bookings:
        intervals[booking.equipment_id].append(
            (max(booking.start_at, start), min(booking.end_at, end), booking.quantity))
    requests = BorrowItem.objects.filter(
        Q(request__status__in=HOLDING_REQUEST, request__borrow_at__lt=end, request__due_at__gt=start)
        | Q(request__status__in=ON_LOAN), equipment_id__in=ids,
    ).select_related("request")
    for item in requests:
        req = item.request
        if req.status in ON_LOAN:
            begin = min(req.borrow_at, req.handed_over_at or req.borrow_at)
            finish = end
        else:
            begin, finish = req.borrow_at, req.due_at
        begin, finish = max(begin, start), min(finish, end)
        if begin < finish:
            intervals[item.equipment_id].append((begin, finish, item.quantity))
    return {
        eq.pk: max(eq.usable_quantity - peak_quantity(intervals[eq.pk]), 0)
        if eq.is_active and eq.status == AdminStatus.AVAILABLE else 0
        for eq in equipment_list
    }


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
    equipment = list(qs)
    statuses = bulk_status(equipment)
    day_free = _free_on_day_bulk(equipment, day, setting) if day else None
    result = []
    for eq in equipment:
        eq.status_value, free = statuses[eq.pk]
        if status and eq.status_value != status:
            continue
        eq.badge = STATUS_BADGE[eq.status_value]
        eq.free_now = free
        eq.free_qty = day_free[eq.pk] if day else eq.free_now
        result.append(eq)
    return result
