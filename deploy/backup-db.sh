#!/usr/bin/env bash
# Daily MySQL backup. Credentials come from ~/.my.cnf ([client]) of the running user, never from args.
set -euo pipefail
BACKUP_DIR=/srv/labborrow/backups
DB_NAME=labborrow
KEEP_DAYS=30
umask 077
mkdir -p "$BACKUP_DIR"
OUT="$BACKUP_DIR/${DB_NAME}_$(date +%F_%H%M).sql.gz"
mysqldump --single-transaction --routines --default-character-set=utf8mb4 "$DB_NAME" | gzip -9 > "$OUT.tmp"
mv "$OUT.tmp" "$OUT"
find "$BACKUP_DIR" -name "${DB_NAME}_*.sql.gz" -type f -mtime +"$KEEP_DAYS" -delete
echo "backup ok: $OUT"
