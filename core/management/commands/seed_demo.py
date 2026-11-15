import random
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import ProtectedError
from django.utils import timezone

from accounts.models import Role, User
from borrowing.models import (
    Booking,
    BookingStatus,
    BorrowItem,
    BorrowRequest,
    RequestStatus,
    Return,
    ReturnItem,
)
from core.models import SystemSetting
from inventory.models import Category, Equipment
from maintenance.models import DamageReport, DamageSource, RepairStatus

DEMO_PASSWORD = "Demo1234!"
DEPARTMENT = "เคมี"
ASSET_PREFIX = "CHEM-"

# Activity (--with-activity) settings
ACTIVITY_TAG = "[demo]"
ACTIVITY_SEED = 2569
BANGKOK = ZoneInfo("Asia/Bangkok")
BORROWER_USERNAMES = ["student1", "student2", "student3", "student4", "student5", "teacher1", "teacher2"]
# 107 past requests + 13 current requests = 120 borrow requests in total.
PAST_REQUESTS = 107
PAST_REJECTED = 9
PAST_CANCELLED = 7
PURPOSES = [
    "ปฏิบัติการเคมี การไทเทรตกรด-เบส",
    "ปฏิบัติการเคมี การกลั่นสารละลาย",
    "ปฏิบัติการเคมี การวิเคราะห์ค่า pH",
    "ปฏิบัติการเคมี การเตรียมสารละลายมาตรฐาน",
    "ปฏิบัติการเคมี การกรองแบบสุญญากาศ",
    "ปฏิบัติการเคมี การให้ความร้อนและการระเหย",
]
REJECT_REASONS = [
    "อุปกรณ์ไม่เพียงพอในช่วงเวลาที่ขอ",
    "ข้อมูลการขอยังไม่ครบถ้วน",
    "ต้องผ่านการอบรมความปลอดภัยก่อนยืมอุปกรณ์นี้",
    "มีรายการซ้ำซ้อนกับคำขอที่อนุมัติแล้ว",
]
RETURN_NOTES = ["", "", "", "คืนครบถ้วน", "สภาพปกติ"]
DEMO_DAMAGE = [
    ("บีกเกอร์แตกร้าว", RepairStatus.REPORTED),
    ("pH meter ค่าอ่านคลาดเคลื่อน", RepairStatus.REPORTED),
    ("ขาตั้งหลวม", RepairStatus.IN_REPAIR),
    ("ฮอตเพลตให้ความร้อนไม่สม่ำเสมอ", RepairStatus.REPAIRED),
    ("แว่นตานิรภัยมีรอยขีดข่วน", RepairStatus.REPAIRED),
]

# username, role, first name, last name, is_staff, student_id
DEMO_USERS = [
    ("staff1", Role.STAFF, "ปิยะ", "วงศ์ทอง", True, ""),
    ("teacher1", Role.TEACHER, "อรุณี", "สุขสม", False, ""),
    ("teacher2", Role.TEACHER, "ธนพล", "แก้วมณี", False, ""),
    ("student1", Role.STUDENT, "กานต์", "พรหมดี", False, "67102122101"),
    ("student2", Role.STUDENT, "นภัสสร", "ศรีสุข", False, "67102122102"),
    ("student3", Role.STUDENT, "ภูวดล", "ชัยวงษ์", False, "67102122103"),
    ("student4", Role.STUDENT, "วรรณิศา", "ทองดี", False, "67102122104"),
    ("student5", Role.STUDENT, "เอกชัย", "มีสุข", False, "67102122105"),
]

# code, name (Thai), name (English), shelf location
CATEGORIES = [
    ("GL", "เครื่องแก้ว", "Glassware", "ตู้ A1"),
    ("MI", "เครื่องมือวัด", "Measuring instruments", "ตู้ A2"),
    ("EX", "เครื่องมือทดลอง", "Experimental apparatus", "ตู้ A3"),
    ("SF", "อุปกรณ์ความปลอดภัย", "Safety equipment", "ตู้ A4"),
    ("HT", "อุปกรณ์ให้ความร้อน", "Heating equipment", "ตู้ A5"),
]

# Per category: (name_th, name_en, quantity_total). Eight items each.
EQUIPMENT = {
    "GL": [
        ("บีกเกอร์ 250 มล.", "Beaker 250 mL", 20),
        ("บีกเกอร์ 100 มล.", "Beaker 100 mL", 20),
        ("ขวดรูปชมพู่ 250 มล.", "Erlenmeyer flask 250 mL", 15),
        ("ขวดปรับปริมาตร 100 มล.", "Volumetric flask 100 mL", 10),
        ("หลอดทดลอง", "Test tube", 20),
        ("กระบอกตวง 100 มล.", "Graduated cylinder 100 mL", 12),
        ("กรวยกรอง", "Funnel", 10),
        ("บิวเรตต์ 50 มล.", "Burette 50 mL", 8),
    ],
    "MI": [
        ("เครื่องชั่งดิจิทัล 4 ตำแหน่ง", "Analytical balance 4-digit", 1),
        ("pH meter", "pH meter", 2),
        ("ปิเปตต์อัตโนมัติ", "Micropipette", 3),
        ("เทอร์โมมิเตอร์ดิจิทัล", "Digital thermometer", 3),
        ("เครื่องวัดการนำไฟฟ้า", "Conductivity meter", 1),
        ("เครื่องชั่งทศนิยม 2 ตำแหน่ง", "Top-loading balance 2-digit", 2),
        ("เครื่องสเปกโตรโฟโตมิเตอร์", "UV-Vis spectrophotometer", 1),
        ("ไฮโดรมิเตอร์", "Hydrometer", 3),
    ],
    "EX": [
        ("ชุดกลั่นแบบธรรมดา", "Simple distillation set", 2),
        ("ชุดกรองสุญญากาศ", "Vacuum filtration set", 2),
        ("ชุดรีฟลักซ์พร้อมคอนเดนเซอร์", "Reflux condenser set", 2),
        ("ขาตั้งพร้อมที่หนีบ", "Ring stand with clamp", 5),
        ("ชุดไทเทรต", "Titration set", 3),
        ("โกร่งและสาก", "Mortar and pestle", 5),
        ("ช้อนตักสาร", "Spatula", 10),
        ("ชุดแยกสารด้วยกรวยแยก", "Separatory funnel set", 2),
    ],
    "SF": [
        ("แว่นตานิรภัย", "Safety goggles", 10),
        ("ถุงมือไนไตรล์", "Nitrile gloves", 10),
        ("เสื้อกาวน์", "Lab coat", 10),
        ("ชุดปฐมพยาบาล", "First aid kit", 2),
        ("เครื่องดับเพลิงชนิดผงเคมีแห้ง", "Dry chemical fire extinguisher", 2),
        ("หน้ากากกรองสารเคมี", "Chemical respirator mask", 5),
        ("ผ้ากันเปื้อนกันสารเคมี", "Chemical apron", 5),
        ("ถาดรองกันสารเคมีหก", "Chemical spill tray", 3),
    ],
    "HT": [
        ("ฮอตเพลตกวนสาร", "Hotplate stirrer", 3),
        ("เตาให้ความร้อนแบบโคนไฟฟ้า", "Electric heating mantle", 3),
        ("ตะเกียงแก๊ส", "Bunsen burner", 5),
        ("ตู้อบลมร้อน", "Drying oven", 1),
        ("อ่างน้ำควบคุมอุณหภูมิ", "Water bath", 2),
        ("บล็อกให้ความร้อนแบบแห้ง", "Dry block heater", 2),
        ("ตะแกรงลวดรองความร้อน", "Wire gauze", 10),
        ("เครื่องเขย่าสารแบบวงโคจร", "Orbital shaker", 2),
    ],
}


def _pick_weekday(rng, first, last):
    """Random Monday-Friday date between first and last (inclusive)."""
    days = [first + timedelta(days=i) for i in range((last - first).days + 1)]
    return rng.choice([d for d in days if d.weekday() < 5])


def _business_time(rng, day):
    """Random Asia/Bangkok datetime on ``day`` between 09:00 and 14:59."""
    naive = datetime.combine(day, time(rng.randint(9, 14), rng.randint(0, 59)))
    return timezone.make_aware(naive, BANGKOK)


class Command(BaseCommand):
    help = "Seed idempotent demo data (users, categories, chemistry lab equipment)."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true",
                            help="Delete demo users, CHEM-* equipment and demo activity before seeding.")
        parser.add_argument("--with-activity", action="store_true",
                            help="Also create demo borrowing history and damage reports.")

    def handle(self, *args, **options):
        removed_eq = removed_users = 0
        if options["reset"]:
            # Activity first: it references equipment and users, which are deleted below.
            self._reset_activity()
            removed_eq, removed_users = self._reset()

        self._seed_users()
        self._seed_equipment()
        if options["with_activity"]:
            self._seed_activity(timezone.now().astimezone(BANGKOK))
        SystemSetting.load()

        summary = (
            f"Demo data ready: {User.objects.filter(username__in=[u[0] for u in DEMO_USERS]).count()} users, "
            f"{Category.objects.filter(name_th__in=[c[1] for c in CATEGORIES]).count()} categories, "
            f"{Equipment.objects.filter(asset_code__startswith=ASSET_PREFIX).count()} equipment"
        )
        if options["reset"]:
            summary += f" (reset removed {removed_users} users, {removed_eq} equipment)"
        self.stdout.write(self.style.SUCCESS(summary))

    def _reset(self):
        removed_eq = 0
        for eq in Equipment.objects.filter(asset_code__startswith=ASSET_PREFIX):
            try:
                with transaction.atomic():
                    eq.delete()
                removed_eq += 1
            except ProtectedError:
                self.stdout.write(self.style.WARNING(
                    f"Warning: {eq.asset_code} is referenced by other records and was not deleted."))

        removed_users = 0
        for user in User.objects.filter(username__in=[u[0] for u in DEMO_USERS]):
            try:
                with transaction.atomic():
                    user.delete()
                removed_users += 1
            except ProtectedError:
                self.stdout.write(self.style.WARNING(
                    f"Warning: user {user.username} is referenced by other records and was not deleted."))
        return removed_eq, removed_users

    def _reset_activity(self):
        demo_reports = DamageReport.objects.filter(problem__startswith=ACTIVITY_TAG)
        # Give back the units that were taken out of service for demo repairs.
        for report in demo_reports.filter(status=RepairStatus.IN_REPAIR).select_related("equipment"):
            eq = report.equipment
            eq.quantity_out_of_service = max(eq.quantity_out_of_service - report.quantity, 0)
            eq.save(update_fields=["quantity_out_of_service"])
        demo_reports.delete()
        BorrowRequest.objects.filter(purpose__startswith=ACTIVITY_TAG).delete()
        Booking.objects.filter(note__startswith=ACTIVITY_TAG).delete()

    def _seed_users(self):
        for username, role, first, last, is_staff, student_id in DEMO_USERS:
            user, _ = User.objects.update_or_create(
                username=username,
                defaults={
                    "role": role,
                    "first_name": first,
                    "last_name": last,
                    "is_staff": is_staff,
                    "is_active": True,
                    "student_id": student_id,
                    "department": DEPARTMENT,
                },
            )
            user.set_password(DEMO_PASSWORD)
            user.save()

    def _seed_equipment(self):
        for code, name_th, name_en, location in CATEGORIES:
            category, _ = Category.objects.update_or_create(
                name_th=name_th, defaults={"name_en": name_en})
            for index, (item_th, item_en, qty) in enumerate(EQUIPMENT[code], start=1):
                Equipment.objects.update_or_create(
                    asset_code=f"{ASSET_PREFIX}{code}-{index:03d}",
                    defaults={
                        "name_th": item_th,
                        "name_en": item_en,
                        "category": category,
                        "location": location,
                        "quantity_total": qty,
                        "is_active": True,
                    },
                )

    def _seed_activity(self, now):
        if BorrowRequest.objects.filter(purpose__startswith=ACTIVITY_TAG).exists():
            self.stdout.write("activity already seeded")
            return

        rng = random.Random(ACTIVITY_SEED)
        today = now.date()
        staff = User.objects.get(username="staff1")
        borrowers = [User.objects.get(username=name) for name in BORROWER_USERNAMES]
        pool = list(Equipment.objects.filter(asset_code__startswith=ASSET_PREFIX, is_active=True)
                    .order_by("asset_code"))

        # Past requests: borrowed 12-180 days ago, so every return date is already in the past.
        past_statuses = (
            [RequestStatus.RETURNED] * (PAST_REQUESTS - PAST_REJECTED - PAST_CANCELLED)
            + [RequestStatus.REJECTED] * PAST_REJECTED
            + [RequestStatus.CANCELLED] * PAST_CANCELLED
        )
        rng.shuffle(past_statuses)
        for status in past_statuses:
            borrower = rng.choice(borrowers)
            borrow_day = _pick_weekday(rng, today - timedelta(days=180), today - timedelta(days=12))
            due_day = _pick_weekday(rng, borrow_day + timedelta(days=1), borrow_day + timedelta(days=7))
            borrow_at = _business_time(rng, borrow_day)
            due_at = _business_time(rng, due_day)
            created_at = borrow_at - timedelta(days=rng.randint(1, 5))
            decided_at = created_at + timedelta(hours=rng.randint(2, 20))

            if status == RequestStatus.REJECTED:
                extra = {"decided_by": staff, "decided_at": decided_at,
                         "reject_reason": rng.choice(REJECT_REASONS)}
            elif status == RequestStatus.CANCELLED:
                extra = {"cancelled_by": borrower,
                         "cancelled_at": created_at + timedelta(hours=rng.randint(1, 24))}
            else:
                extra = {"decided_by": staff, "decided_at": decided_at,
                         "handed_over_by": staff, "handed_over_at": borrow_at}
            req = self._create_request(rng, pool, borrower, status, borrow_at, due_at, created_at, extra)
            if status == RequestStatus.RETURNED:
                self._create_return(rng, req, staff, due_at)

        # Current requests.
        for _ in range(4):  # pending approval, future borrow
            borrow_day = _pick_weekday(rng, today + timedelta(days=1), today + timedelta(days=10))
            borrow_at = _business_time(rng, borrow_day)
            due_at = _business_time(rng, _pick_weekday(rng, borrow_day + timedelta(days=1),
                                                       borrow_day + timedelta(days=7)))
            created_at = now - timedelta(hours=rng.randint(6, 60))
            self._create_request(rng, pool, rng.choice(borrowers), RequestStatus.PENDING,
                                 borrow_at, due_at, created_at, {})

        for _ in range(3):  # approved, future borrow
            borrow_day = _pick_weekday(rng, today + timedelta(days=1), today + timedelta(days=10))
            borrow_at = _business_time(rng, borrow_day)
            due_at = _business_time(rng, _pick_weekday(rng, borrow_day + timedelta(days=1),
                                                       borrow_day + timedelta(days=7)))
            decided_at = now - timedelta(hours=rng.randint(6, 40))
            created_at = decided_at - timedelta(hours=rng.randint(4, 30))
            self._create_request(rng, pool, rng.choice(borrowers), RequestStatus.APPROVED,
                                 borrow_at, due_at, created_at,
                                 {"decided_by": staff, "decided_at": decided_at})

        for _ in range(4):  # on loan, due within 3 days
            borrow_day = _pick_weekday(rng, today - timedelta(days=3), today - timedelta(days=1))
            borrow_at = _business_time(rng, borrow_day)
            due_at = _business_time(rng, _pick_weekday(rng, today + timedelta(days=1),
                                                       today + timedelta(days=3)))
            decided_at = borrow_at - timedelta(hours=rng.randint(4, 20))
            created_at = decided_at - timedelta(hours=rng.randint(4, 30))
            self._create_request(rng, pool, rng.choice(borrowers), RequestStatus.BORROWED,
                                 borrow_at, due_at, created_at,
                                 {"decided_by": staff, "decided_at": decided_at,
                                  "handed_over_by": staff, "handed_over_at": borrow_at})

        for _ in range(2):  # overdue, due date already passed
            borrow_day = _pick_weekday(rng, today - timedelta(days=14), today - timedelta(days=10))
            borrow_at = _business_time(rng, borrow_day)
            due_at = _business_time(rng, _pick_weekday(rng, borrow_day + timedelta(days=1),
                                                       borrow_day + timedelta(days=3)))
            decided_at = borrow_at - timedelta(hours=rng.randint(4, 20))
            created_at = decided_at - timedelta(hours=rng.randint(4, 30))
            self._create_request(rng, pool, rng.choice(borrowers), RequestStatus.OVERDUE,
                                 borrow_at, due_at, created_at,
                                 {"decided_by": staff, "decided_at": decided_at,
                                  "handed_over_by": staff, "handed_over_at": borrow_at,
                                  "overdue_notified_at": due_at + timedelta(days=1)})

        # Future bookings that are not tied to a request.
        for _ in range(6):
            eq = rng.choice(pool)
            start_day = _pick_weekday(rng, today + timedelta(days=2), today + timedelta(days=20))
            start_at = _business_time(rng, start_day)
            end_at = _business_time(rng, _pick_weekday(rng, start_day + timedelta(days=1),
                                                       start_day + timedelta(days=3)))
            booking = Booking.objects.create(
                user=rng.choice(borrowers), equipment=eq,
                quantity=rng.randint(1, min(eq.quantity_total, 2)),
                start_at=start_at, end_at=end_at, status=BookingStatus.ACTIVE,
                note=f"{ACTIVITY_TAG} จองล่วงหน้า",
            )
            Booking.objects.filter(pk=booking.pk).update(
                created_at=now - timedelta(hours=rng.randint(1, 72)))

        # Damage reports, one per equipment item.
        for (problem, status), eq in zip(DEMO_DAMAGE, rng.sample(pool, len(DEMO_DAMAGE)), strict=True):
            reported_at = _business_time(rng, _pick_weekday(rng, today - timedelta(days=150),
                                                            today - timedelta(days=3)))
            resolved_at = None
            if status == RepairStatus.REPAIRED:
                resolved_at = min(reported_at + timedelta(days=rng.randint(2, 10)), now)
            report = DamageReport.objects.create(
                equipment=eq, reported_by=rng.choice(borrowers), quantity=1,
                problem=f"{ACTIVITY_TAG} {problem}", source=DamageSource.USER, status=status,
                handled_by=None if status == RepairStatus.REPORTED else staff,
                resolved_at=resolved_at,
            )
            DamageReport.objects.filter(pk=report.pk).update(created_at=reported_at)
            if status == RepairStatus.IN_REPAIR:
                eq.quantity_out_of_service = min(eq.quantity_out_of_service + report.quantity,
                                                 eq.quantity_total)
                eq.save(update_fields=["quantity_out_of_service"])

        reqs = BorrowRequest.objects.filter(purpose__startswith=ACTIVITY_TAG)
        counts = ", ".join(f"{s.value} {reqs.filter(status=s).count()}" for s in RequestStatus)
        self.stdout.write(self.style.SUCCESS(
            f"Activity seeded: {reqs.count()} borrow requests ({counts}), "
            f"{Booking.objects.filter(note__startswith=ACTIVITY_TAG).count()} bookings, "
            f"{DamageReport.objects.filter(problem__startswith=ACTIVITY_TAG).count()} damage reports"))

    def _create_request(self, rng, pool, borrower, status, borrow_at, due_at, created_at, extra):
        req = BorrowRequest.objects.create(
            user=borrower,
            purpose=f"{ACTIVITY_TAG} {rng.choice(PURPOSES)}",
            borrow_at=borrow_at,
            due_at=due_at,
            status=status,
            **extra,
        )
        for eq in rng.sample(pool, rng.randint(1, 3)):
            BorrowItem.objects.create(request=req, equipment=eq,
                                      quantity=rng.randint(1, min(eq.quantity_total, 3)))
        BorrowRequest.objects.filter(pk=req.pk).update(created_at=created_at)
        return req

    def _create_return(self, rng, req, staff, due_at):
        window_first = (due_at - timedelta(days=1)).date()
        window_last = (due_at + timedelta(days=2)).date()
        returned_at = _business_time(rng, _pick_weekday(rng, window_first, window_last))
        returned_at = min(max(returned_at, due_at - timedelta(days=1)), due_at + timedelta(days=2))
        ret = Return.objects.create(request=req, returned_at=returned_at, received_by=staff,
                                    note=rng.choice(RETURN_NOTES))
        Return.objects.filter(pk=ret.pk).update(created_at=returned_at)
        for item in req.items.all():
            ReturnItem.objects.create(return_record=ret, borrow_item=item,
                                      quantity_good=item.quantity, quantity_damaged=0)
