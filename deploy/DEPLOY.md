# คู่มือ Deploy ระบบยืม-คืนอุปกรณ์ห้องปฏิบัติการ (Ubuntu 24.04)

## 1. สิ่งที่ต้องมี
- Ubuntu 24.04, Python 3.12+, MySQL 8, Nginx, Gunicorn, certbot
- โดเมนที่ชี้มายังเซิร์ฟเวอร์ (ตัวอย่าง `labborrow.example.ac.th`) และเปิดพอร์ต 80/443 (LINE webhook ต้องเป็น HTTPS สาธารณะ)

## 2. เตรียมเครื่อง
```bash
sudo apt update
sudo apt install -y python3-venv python3-dev git nginx mysql-server certbot python3-certbot-nginx \
    pkg-config default-libmysqlclient-dev build-essential
sudo adduser --system --group --home /srv/labborrow labborrow
sudo usermod -aG labborrow www-data    # ให้ nginx อ่าน static/media ได้
sudo chmod 750 /srv/labborrow
```

## 3. ฐานข้อมูล MySQL
แก้รหัสผ่าน `CHANGE_ME` ใน `deploy/mysql-setup.sql` แล้วรัน
```bash
sudo mysql < /srv/labborrow/app/deploy/mysql-setup.sql
```

## 4. วางโค้ดและ virtualenv
```bash
sudo -u labborrow git clone <URL_ของ_repo> /srv/labborrow/app     # หรือ scp/rsync โฟลเดอร์ app มาไว้ที่นี่
sudo -u labborrow python3 -m venv /srv/labborrow/venv
sudo -u labborrow /srv/labborrow/venv/bin/pip install -U pip
sudo -u labborrow /srv/labborrow/venv/bin/pip install -r /srv/labborrow/app/requirements.txt gunicorn
```
> `mysqlclient` ต้องใช้ `pkg-config default-libmysqlclient-dev build-essential` (ติดตั้งแล้วในข้อ 2)
> `gunicorn` ไม่อยู่ใน requirements.txt จึงติดตั้งแยก

## 5. ไฟล์ .env
```bash
cd /srv/labborrow/app
sudo -u labborrow cp .env.example .env
sudo -u labborrow chmod 600 .env
/srv/labborrow/venv/bin/python -c "import secrets; print(secrets.token_urlsafe(64))"   # ใช้เป็น SECRET_KEY
sudo -u labborrow nano .env
```
ค่าที่ต้องตั้ง:
```
SECRET_KEY=<ค่าที่สร้างจากคำสั่งด้านบน>
DEBUG=False
ALLOWED_HOSTS=labborrow.example.ac.th
CSRF_TRUSTED_ORIGINS=https://labborrow.example.ac.th
SITE_URL=https://labborrow.example.ac.th
DB_ENGINE=mysql
DB_NAME=labborrow
DB_USER=labborrow
DB_PASSWORD=<รหัสผ่านเดียวกับใน mysql-setup.sql>
DB_HOST=127.0.0.1
DB_PORT=3306
LINE_CHANNEL_SECRET=...
LINE_CHANNEL_ACCESS_TOKEN=...
LINE_OA_BASIC_ID=@xxxxxxx
```
(ตั้ง `SECURE_HSTS_SECONDS=31536000` ได้ภายหลังเมื่อ HTTPS เสถียรแล้ว)

## 6. migrate, static, แปลภาษา, ผู้ดูแล
```bash
cd /srv/labborrow/app
export DJANGO_SETTINGS_MODULE=config.settings.prod
PY=/srv/labborrow/venv/bin/python
sudo -E -u labborrow $PY manage.py migrate
sudo -E -u labborrow $PY manage.py collectstatic --noinput
sudo -E -u labborrow $PY manage.py i18n compile     # ไม่ต้องติดตั้ง gettext
sudo -E -u labborrow $PY manage.py createsuperuser
sudo -E -u labborrow $PY manage.py shell -c "from accounts.models import User; User.objects.filter(username='ADMIN_USERNAME').update(role='staff')"
sudo -u labborrow mkdir -p /srv/labborrow/app/media /srv/labborrow/backups
```
(แทน `ADMIN_USERNAME` ด้วยชื่อผู้ใช้ที่เพิ่งสร้าง)

## 7. เปิดบริการ systemd
Gunicorn ต้องตั้ง `Environment=MEDIA_ACCEL=1` เพื่อส่งไฟล์ที่ตรวจสิทธิ์แล้วผ่าน Nginx internal location
```bash
cd /srv/labborrow/app/deploy
sudo cp gunicorn.service labborrow-check-due.service labborrow-check-due.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now gunicorn
sudo systemctl enable --now labborrow-check-due.timer
systemctl status gunicorn
systemctl list-timers | grep labborrow
```

## 8. Nginx + HTTPS (certbot)
```bash
sudo cp /srv/labborrow/app/deploy/nginx-labborrow.conf /etc/nginx/sites-available/labborrow
sudo sed -i 's/labborrow.example.ac.th/<โดเมนจริง>/' /etc/nginx/sites-available/labborrow
sudo ln -s /etc/nginx/sites-available/labborrow /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d <โดเมนจริง>
sudo certbot renew --dry-run
```

## 9. ตั้งค่า LINE Developers Console
1. เข้า https://developers.line.biz/console/ สร้าง Provider แล้วสร้าง Channel ชนิด **Messaging API**
2. แท็บ Basic settings คัดลอก **Channel secret** ใส่ `LINE_CHANNEL_SECRET`
3. แท็บ Messaging API กด Issue **Channel access token (long-lived)** ใส่ `LINE_CHANNEL_ACCESS_TOKEN`; ใส่ Basic ID ของ OA ใน `LINE_OA_BASIC_ID`
4. ตั้ง Webhook URL เป็น `https://<โดเมน>/notifications/line/webhook/` แล้วกด Verify
5. เปิด **Use webhook**
6. ปิด **Auto-reply messages** (และ Greeting messages) ที่ LINE Official Account Manager
7. `sudo systemctl restart gunicorn` หลังแก้ .env

## 10. Backup อัตโนมัติ
สร้าง `~/.my.cnf` ของผู้ใช้ `labborrow` (สิทธิ์ 600) — ห้ามใส่รหัสผ่านในอาร์กิวเมนต์
```ini
[client]
user=labborrow
password=<รหัสผ่านฐานข้อมูล>
```
```bash
sudo -u labborrow chmod 600 /srv/labborrow/.my.cnf
sudo chmod 750 /srv/labborrow/app/deploy/backup-db.sh
sudo -u labborrow crontab -e
```
เพิ่มบรรทัด (ทุกวัน 02:30):
```
30 2 * * * /srv/labborrow/app/deploy/backup-db.sh >> /srv/labborrow/backups/backup.log 2>&1
```
สคริปต์เก็บไฟล์ `.sql.gz` ย้อนหลัง 30 วัน (home ของ labborrow คือ /srv/labborrow จึงวาง .my.cnf ที่นั่น)

## 11. เช็กลิสต์ครั้งแรก
- [ ] เปิด https://<โดเมน>/ ได้ มีกุญแจ HTTPS และ http redirect ไป https
- [ ] ล็อกอินด้วยผู้ดูแล (role = staff) และเข้าเมนูจัดการได้
- [ ] CSS/รูปโหลดครบ (/static/), อัปโหลดรูป (/media/) ได้ ไม่เกิน 12 MB
- [ ] ภาษาไทยแสดงถูกต้อง (รัน `i18n compile` แล้ว)
- [ ] LINE: Verify webhook ผ่าน, ผูกบัญชีด้วยรหัส 6 หลักได้
- [ ] `sudo -E -u labborrow $PY manage.py check --deploy` ไม่มี error
- [ ] `systemctl list-timers` เห็น labborrow-check-due.timer; ทดสอบ `sudo systemctl start labborrow-check-due.service` แล้วดู `journalctl -u labborrow-check-due`
- [ ] รัน backup-db.sh ด้วยมือหนึ่งครั้ง ได้ไฟล์ใน /srv/labborrow/backups

## 12. การอัปเดตระบบ
```bash
cd /srv/labborrow/app
sudo -u labborrow deploy/backup-db.sh        # สำรองก่อนอัปเดต
sudo -u labborrow git pull
sudo -u labborrow /srv/labborrow/venv/bin/pip install -r requirements.txt
export DJANGO_SETTINGS_MODULE=config.settings.prod
PY=/srv/labborrow/venv/bin/python
sudo -E -u labborrow $PY manage.py migrate
sudo -E -u labborrow $PY manage.py collectstatic --noinput
sudo -E -u labborrow $PY manage.py i18n compile
sudo systemctl restart gunicorn
```

## 13. การกู้คืนจาก backup
```bash
sudo systemctl stop gunicorn
gunzip -c /srv/labborrow/backups/labborrow_YYYY-MM-DD_HHMM.sql.gz | sudo mysql labborrow
sudo systemctl start gunicorn
```
ถ้าฐานข้อมูลเสียหายมาก ให้ `DROP DATABASE labborrow;` แล้วรัน mysql-setup.sql ใหม่ก่อน
ไฟล์รูปใน `/srv/labborrow/app/media/` ต้องสำรองแยก เช่น `tar czf media.tgz media/` หรือ rsync

## 14. ทดลองบนเครื่องตัวเอง (Windows)
```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env        # DB_ENGINE=sqlite, DEBUG=True สำหรับทดลอง
python manage.py migrate
python manage.py i18n compile
python manage.py seed_demo
python manage.py runserver
```
เปิด http://127.0.0.1:8000/ (manage.py ใช้ `config.settings.dev` เป็นค่าเริ่มต้น)

ทดสอบ LINE webhook ด้วย ngrok:
```powershell
ngrok http 8000
```
นำ URL `https://xxxx.ngrok-free.app` ไปตั้ง Webhook URL เป็น `https://xxxx.ngrok-free.app/notifications/line/webhook/` และตั้ง `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `SITE_URL` ใน .env ให้ตรงกับโดเมน ngrok แล้วรีสตาร์ท runserver
