from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import ProtectedError

from accounts.models import Role, User
from core.models import SystemSetting
from inventory.models import Category, Equipment

DEMO_PASSWORD = "Demo1234!"
DEPARTMENT = "เคมี"
ASSET_PREFIX = "CHEM-"

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


class Command(BaseCommand):
    help = "Seed idempotent demo data (users, categories, chemistry lab equipment)."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true",
                            help="Delete demo users and CHEM-* equipment before seeding.")

    def handle(self, *args, **options):
        removed_eq = removed_users = 0
        if options["reset"]:
            removed_eq, removed_users = self._reset()

        self._seed_users()
        self._seed_equipment()
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
