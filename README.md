# ระบบยืม–คืนครุภัณฑ์และอุปกรณ์ห้องปฏิบัติการเคมี (app)

โค้ด Django 5.2 LTS (Python 3.14) ของระบบจัดการการยืม–คืนอุปกรณ์ห้องปฏิบัติการ
ฐานข้อมูลโหมดพัฒนาใช้ SQLite ส่วน production ใช้ MySQL 8.4
แผนงานและสเปกอยู่ที่ `..\PLAN.md` และ `..\docs\`

## ภาพรวมระบบ

ผู้ใช้ค้นหาและจองอุปกรณ์ ส่งคำขอยืม เจ้าหน้าที่อนุมัติหรือปฏิเสธ จากนั้นส่งมอบและรับคืน
พร้อมบันทึกสภาพและรูปภาพ ผู้ใช้แจ้งอุปกรณ์ชำรุดได้ เจ้าหน้าที่ดูแดชบอร์ด ส่งออกรายงาน Excel/PDF
และระบบแจ้งเตือนผ่าน LINE Official Account

หลักการสำคัญ: business logic อยู่ใน `services.py` ของแต่ละแอป การเปลี่ยนสถานะทั้งหมดผ่าน
`borrowing/state.py` ทุก view ตรวจสิทธิ์ฝั่งเซิร์ฟเวอร์ และการแจ้งเตือนจะไม่ทำให้ธุรกรรมล้มเหลว

| แอป | หน้าที่ |
|---|---|
| `core` | `SystemSetting` (เงื่อนไขการยืม), mixin/decorator สิทธิ์, base template, context processor, คำสั่ง `seed_demo` และ `i18n` |
| `accounts` | User แบบกำหนดเอง (role, เบอร์โทร, `line_user_id`, ภาษา), สมัคร/เข้า–ออกระบบ, โปรไฟล์, จัดการผู้ใช้, ผูกบัญชี LINE |
| `inventory` | หมวดหมู่และอุปกรณ์ (CRUD, รูปภาพ, ค้นหาและกรอง) |
| `borrowing` | การจอง คำขอยืม รายการยืม การคืน, `state.py`, `services.py`, คำสั่ง `check_due` |
| `maintenance` | แจ้งอุปกรณ์ชำรุด (`DamageReport`) และบันทึกสถานะการซ่อม |
| `notifications` | `NotificationLog`, LINE client, webhook, การจับคู่บัญชี LINE, คำสั่ง `retry_notifications` |
| `reports` | Dashboard, ส่งออก Excel (openpyxl) และ PDF (ReportLab + ฟอนต์ TH Sarabun) |

## โครงสร้างโฟลเดอร์

```
D:\!โครงงานอ้วน\
├─ PLAN.md, proposal\, docs\      แผนงาน เล่มโครงการ และสเปก
└─ app\                           โค้ด Django (โฟลเดอร์นี้)
   ├─ manage.py
   ├─ config\settings\            base.py, dev.py, prod.py, test.py
   ├─ config\urls.py, wsgi.py
   ├─ accounts\ core\ inventory\ borrowing\ maintenance\ notifications\ reports\
   ├─ templates\                  base.html, partials\
   ├─ static\                     css, js
   ├─ locale\th\, locale\en\      ไฟล์แปลภาษา (django.po, django.mo)
   ├─ tests\                      pytest: tests\<แอป>\test_*.py, tests\e2e\
   ├─ deploy\                     DEPLOY.md และไฟล์ตั้งค่า production
   ├─ .venv\, .env                ไม่เข้า git
   └─ requirements.txt, requirements-dev.txt, pyproject.toml, .env.example
```

## เริ่มต้นบนเครื่อง Windows

รันใน PowerShell ที่โฟลเดอร์ `app`:

```powershell
cd "D:\!โครงงานอ้วน\app"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
copy .env.example .env
python manage.py migrate
python manage.py i18n compile
python manage.py seed_demo --with-activity
python manage.py runserver
```

- เปิดเบราว์เซอร์ที่ http://127.0.0.1:8000/
- `manage.py` ใช้ `config.settings.dev` เป็นค่าเริ่มต้น และ `.env.example` ตั้ง `DB_ENGINE=sqlite` ฐานข้อมูลจะอยู่ที่ `db.sqlite3`
- ถ้า `Activate.ps1` ถูกบล็อก ให้รัน `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` หนึ่งครั้ง
- `mysqlclient` อยู่ใน `requirements.txt` และบน Windows ต้องใช้ build tools ของ MySQL โหมดพัฒนาไม่ได้ใช้ MySQL ถ้าติดตั้งไม่ผ่าน ให้แจ้งผู้พัฒนาก่อนแก้ requirements

### บัญชีทดลอง

| ชื่อผู้ใช้ | บทบาท | รหัสผ่าน |
|---|---|---|
| `staff1` | เจ้าหน้าที่ (`is_staff`) | `Demo1234!` |
| `teacher1` | อาจารย์ | `Demo1234!` |
| `student1` | นักศึกษา | `Demo1234!` |

> **Local demo only:** `seed_demo` สร้างบัญชีเหล่านี้พร้อมรหัสผ่านที่เขียนไว้ในเอกสาร
> (ยังมี `teacher2` และ `student2`–`student5` ด้วย) ห้ามรัน `seed_demo` บนระบบจริง
> และต้องลบหรือเปลี่ยนรหัสผ่านบัญชีเหล่านี้ก่อนใช้งานจริง

## คำสั่งจัดการ

| คำสั่ง | ใช้ทำอะไร |
|---|---|
| `python manage.py seed_demo [--reset] [--with-activity]` | สร้างข้อมูลตัวอย่าง: ผู้ใช้, หมวดหมู่ 5 หมวด, อุปกรณ์ `CHEM-*` 40 รายการ. `--with-activity` เพิ่มประวัติการยืม การจอง และการแจ้งชำรุด. `--reset` ลบข้อมูลเดโมเดิมก่อนสร้างใหม่ |
| `python manage.py i18n extract` | อัปเดต `django.po` จากข้อความในโค้ดและเทมเพลต โดยคงคำแปลเดิมไว้ |
| `python manage.py i18n compile` | สร้าง `django.mo` ทุกภาษา (ไม่ต้องติดตั้ง GNU gettext) |
| `python manage.py i18n stats` | แสดงเปอร์เซ็นต์การแปลของแต่ละภาษา |
| `python manage.py check_due` | ทำเครื่องหมายคำขอเกินกำหนด ส่งแจ้งเตือนใกล้ถึงกำหนด และหมดอายุการจองที่ไม่ได้ใช้ (แสดงผล `overdue`, `due_soon`, `expired`) |
| `python manage.py retry_notifications` | ส่ง LINE ที่ล้มเหลวซ้ำ เฉพาะรายการที่ `attempts` น้อยกว่า 3 |

`check_due` ควรรันทุก 1 ชั่วโมง ใน production ใช้ systemd timer ตาม `deploy/DEPLOY.md` ข้อ 7
ส่วนบน Windows ใช้ Task Scheduler เรียก `.\.venv\Scripts\python.exe manage.py check_due` ในโฟลเดอร์ `app`

## การทดสอบ

```powershell
.\.venv\Scripts\python -m pytest -q                              # ชุดอัตโนมัติ (ค่าเริ่มต้น)
.\.venv\Scripts\python -m pytest -q --cov                        # พร้อม coverage (เป้าหมาย services/ อย่างน้อย 80%)
$env:E2E="1"; .\.venv\Scripts\python -m pytest tests/e2e -q      # E2E บน Chrome
Remove-Item Env:E2E
ruff check .                                                     # lint (ตั้งค่าใน pyproject.toml)
python manage.py makemigrations --check                          # ตรวจว่าไม่มี migration ค้าง
```

- pytest ใช้ `config.settings.test` (ตั้งใน `pyproject.toml`) เทสต์แยกตามแอปที่ `tests\<แอป>\test_*.py`
- ครั้งแรกของ E2E ให้รัน `python -m playwright install chromium`
- ถ้าไม่ตั้ง `E2E=1` เทสต์ใน `tests\e2e` จะถูกข้าม
- TC-14 (`tests/borrowing/test_concurrency.py::test_tc14_last_unit_concurrent_mysql`) ต้องรันบน MySQL จึงจะได้ผลจริง
- การจับคู่ FR → TC → ไฟล์เทสต์ ดูที่ `..\docs\07-test-matrix.md`

## การแปลภาษา

ภาษาเริ่มต้นคือไทย (`LANGUAGE_CODE = "th"`) ข้อความต้นฉบับ (msgid) เขียนเป็นภาษาอังกฤษ

1. หุ้มข้อความที่ผู้ใช้เห็นด้วย `_()` หรือ `gettext_lazy()` ในโค้ด Python และ `{% translate "..." %}` ในเทมเพลต
2. รัน `python manage.py i18n extract` เพื่ออัปเดต `locale\th\LC_MESSAGES\django.po` และ `locale\en\LC_MESSAGES\django.po`
3. กรอก `msgstr` ของข้อความใหม่ในไฟล์ `locale\th\LC_MESSAGES\django.po`
4. รัน `python manage.py i18n compile` เพื่อสร้าง `django.mo`
5. รัน `python manage.py i18n stats` ภาษาไทยต้องได้ 100%

- ตัวแปรในข้อความต้องตรงกันทั้งต้นฉบับและคำแปล เช่น `%(name)s` ถ้าไม่ตรง `compile` จะหยุดและแจ้งข้อผิดพลาด
- เทสต์กำหนดให้คำแปลไทยครบ 100%

## LINE (การแจ้งเตือน)

ตั้งค่าใน `.env` (ดูตัวอย่างใน `.env.example`)

| ตัวแปร | ความหมาย |
|---|---|
| `LINE_CHANNEL_SECRET` | ใช้ตรวจลายเซ็น webhook (`X-Line-Signature`) |
| `LINE_CHANNEL_ACCESS_TOKEN` | ใช้ส่งข้อความ push |
| `LINE_OA_BASIC_ID` | Basic ID ของ OA เช่น `@xxxxxxx` ใช้สร้างลิงก์เพิ่มเพื่อน |
| `SITE_URL` | URL ฐานของเว็บ ใช้ในลิงก์ของข้อความ |

ถ้า token และ secret ว่าง ระบบจะบันทึกการแจ้งเตือนไว้ใน log แต่ไม่ส่งจริง ดูประวัติได้ที่ `/notifications/log/`

**ทดสอบ webhook ในเครื่องด้วย ngrok**
1. รัน `ngrok http 8000`
2. ใน `.env` ตั้ง `ALLOWED_HOSTS` เป็นโดเมน ngrok (เช่น `xxxx.ngrok-free.app`) และตั้ง `SITE_URL` กับ `CSRF_TRUSTED_ORIGINS` เป็น `https://xxxx.ngrok-free.app`
3. รีสตาร์ต `runserver`
4. ใน LINE Developers ตั้ง Webhook URL เป็น `https://xxxx.ngrok-free.app/notifications/line/webhook/` แล้วกด Verify

**flow การผูกบัญชี LINE**
1. ผู้ใช้เปิด `/accounts/line/` ระบบสร้างรหัส 6 หลัก ใช้ได้ 15 นาที
2. ผู้ใช้เพิ่ม LINE OA เป็นเพื่อน แล้วส่งรหัสนั้นในแชต
3. webhook ตรวจลายเซ็น (ไม่ถูกต้องตอบ HTTP 400) จับคู่รหัส บันทึก `line_user_id` และตอบกลับ
4. ลองผิดครบ 5 ครั้งต่อบัญชี LINE หรือ 200 ครั้งรวมภายใน 15 นาที ระบบจะบล็อกชั่วคราว

## การ deploy

production ใช้ Ubuntu 24.04 + MySQL 8 + Gunicorn + Nginx (HTTPS ด้วย certbot) และ systemd timer สำหรับ `check_due`
ขั้นตอนทั้งหมดอยู่ใน [`deploy/DEPLOY.md`](deploy/DEPLOY.md):

- ข้อ 1–3: สิ่งที่ต้องมี, เตรียมเครื่อง, ฐานข้อมูล MySQL
- ข้อ 4–6: วางโค้ดและ virtualenv, ไฟล์ `.env` (`DEBUG=False`), migrate / collectstatic / `i18n compile`
- ข้อ 7–9: systemd, Nginx + HTTPS, ตั้งค่า LINE Developers Console
- ข้อ 10, 13: backup อัตโนมัติและการกู้คืน
- ข้อ 11–12: เช็กลิสต์ก่อนเปิดใช้งาน และการอัปเดตระบบ
- ข้อ 14: ทดลองบนเครื่อง Windows และ ngrok

## เอกสารออกแบบ

- [`../PLAN.md`](../PLAN.md): แผนพัฒนาตามเฟส ทีมและการแบ่งงาน ความเสี่ยง
- [`../docs/06-conventions.md`](../docs/06-conventions.md): กติกาโค้ด, Definition of Done, การตั้งชื่อ commit
- [`../docs/01-data-model.md`](../docs/01-data-model.md): ตาราง ฟิลด์ และข้อจำกัด
- [`../docs/02-state-machine.md`](../docs/02-state-machine.md): สถานะคำขอและอุปกรณ์ และเหตุการณ์ที่เปลี่ยนสถานะ
- [`../docs/03-permissions.md`](../docs/03-permissions.md): เมทริกซ์สิทธิ์และชื่อ permission
- [`../docs/04-urls-screens.md`](../docs/04-urls-screens.md): URL, view, template ของแต่ละหน้าจอ
- [`../docs/05-line.md`](../docs/05-line.md): เหตุการณ์แจ้งเตือน ข้อความ และ flow ผูกบัญชี
- [`../docs/07-test-matrix.md`](../docs/07-test-matrix.md): FR → TC → ไฟล์เทสต์
