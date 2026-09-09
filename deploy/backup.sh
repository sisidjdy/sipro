#!/usr/bin/env bash
# Backup / restore MongoDB SIPRO.
#   bash deploy/backup.sh                       → buat arsip di deploy/backups/, simpan 14 hari
#   bash deploy/backup.sh restore <arsip.gz>    → pulihkan (menimpa database!)
set -euo pipefail
cd "$(dirname "$0")"
set -a; . ./.env; set +a
DB="${DB_NAME:-sipro}"
mkdir -p backups

if [ "${1:-}" = "restore" ]; then
  ARCHIVE="${2:?Sebutkan berkas arsip .archive.gz}"
  echo "[backup] restore $ARCHIVE → database $DB (menimpa)"
  docker compose exec -T mongo mongorestore --archive --gzip --drop --nsInclude="$DB.*" < "$ARCHIVE"
  echo "[backup] selesai; restart backend"
  docker compose restart backend >/dev/null
  exit 0
fi

OUT="backups/sipro-$(date +%Y-%m-%d_%H%M).archive.gz"
docker compose exec -T mongo mongodump --archive --gzip --db "$DB" > "$OUT"
find backups -name 'sipro-*.archive.gz' -mtime +14 -delete
echo "[backup] $OUT ($(du -h "$OUT" | cut -f1))"
