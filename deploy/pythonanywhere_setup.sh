#!/bin/bash
# One-time / repeatable setup on PythonAnywhere (free plan: SQLite, no MySQL, no scheduled tasks).
# Usage (Bash console):  bash ~/labborrow/deploy/pythonanywhere_setup.sh
# Creates ~/labborrow/.env once (random SECRET_KEY and CRON_TOKEN), then migrates and collects static files.
# LINE_CHANNEL_SECRET / LINE_CHANNEL_ACCESS_TOKEN are left empty: paste them into .env yourself.
set -euo pipefail
APP=~/labborrow
PY=~/.venvs/labborrow/bin/python
HOST="${USER}.pythonanywhere.com"
cd "$APP"

if [ ! -f .env ]; then
  umask 077
  SECRET=$("$PY" -c "import secrets; print(secrets.token_urlsafe(64))")
  CRON=$("$PY" -c "import secrets; print(secrets.token_urlsafe(32))")
  cat > .env <<EOF
DJANGO_SETTINGS_MODULE=config.settings.prod
SECRET_KEY=$SECRET
DEBUG=False
ALLOWED_HOSTS=$HOST
CSRF_TRUSTED_ORIGINS=https://$HOST
SITE_URL=https://$HOST
# PythonAnywhere: turn on "Force HTTPS" in the Web tab instead of redirecting in Django
SECURE_SSL_REDIRECT=False
CRON_TOKEN=$CRON
# LINE Messaging API: paste the values yourself (LINE Developers console)
LINE_CHANNEL_SECRET=
LINE_CHANNEL_ACCESS_TOKEN=
LINE_OA_BASIC_ID=@149vwolp
EOF
  echo ".env created"
else
  echo ".env exists, left unchanged"
fi

export DJANGO_SETTINGS_MODULE=config.settings.prod
"$PY" manage.py migrate --noinput
"$PY" manage.py collectstatic --noinput -v 0
"$PY" manage.py check --deploy 2>&1 | tail -n 15 || true
echo SETUP_OK
