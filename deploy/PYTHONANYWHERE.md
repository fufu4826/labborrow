# ติดตั้งบน PythonAnywhere (แพ็กเกจฟรี)

เว็บ: https://kafu4826.pythonanywhere.com · โค้ด: https://github.com/fufu4826/labborrow (public)

## ข้อจำกัดของแพ็กเกจฟรี และวิธีที่ใช้แทน
| ข้อจำกัด | ใช้แทน |
|---|---|
| ไม่มี MySQL | ใช้ SQLite (`~/labborrow/db.sqlite3`) ไฟล์อยู่ถาวร |
| ไม่มี Scheduled tasks | GitHub Actions `.github/workflows/cron.yml` เรียก `POST /cron/` ทุกชั่วโมง (ต้องตั้ง secret `CRON_URL`, `CRON_TOKEN`) |
| เว็บหยุดถ้าไม่ต่ออายุ | เข้าแท็บ Web แล้วกด **Run until 1 month from today** ทุกเดือน |
| ไม่มี nginx | ตั้ง static files ในแท็บ Web: `/static/` → `~/labborrow/staticfiles`, `/media/equipment/` → `~/labborrow/media/equipment` รูปการคืน/ชำรุดส่งผ่าน Django (`/files/...`) |

## ค่าในแท็บ Web
- Source code: `/home/kafu4826/labborrow` · Virtualenv: `/home/kafu4826/.venvs/labborrow` · Python 3.13
- WSGI: คัดลอกจาก `deploy/pythonanywhere_wsgi.py` · Force HTTPS: Enabled

## อัปเดตโค้ด (Bash console)
```bash
cd ~/labborrow && git pull && bash deploy/pythonanywhere_setup.sh
```
แล้วกด **Reload** ในแท็บ Web

## ความลับ (ใส่เองใน `~/labborrow/.env` ผ่านแท็บ Files ห้ามวางในแชต)
- `LINE_CHANNEL_SECRET`, `LINE_CHANNEL_ACCESS_TOKEN`
- `CRON_TOKEN` สร้างให้อัตโนมัติแล้ว คัดลอกค่าเดียวกันไปใส่ GitHub → Settings → Secrets and variables → Actions → `CRON_TOKEN`

## สร้างบัญชีเจ้าหน้าที่คนแรก
```bash
cd ~/labborrow && DJANGO_SETTINGS_MODULE=config.settings.prod ~/.venvs/labborrow/bin/python manage.py createsuperuser
```

LINE Webhook URL: `https://kafu4826.pythonanywhere.com/notifications/line/webhook/`
