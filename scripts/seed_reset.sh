#!/usr/bin/env bash
# Reset DB to a clean seeded state, then run gates. Usage: bash scripts/seed_reset.sh
set -e
cd "$(dirname "$0")/.."

echo "[seed_reset] Dropping application database..."
python3 - <<'PY'
import os
from pymongo import MongoClient
from dotenv import load_dotenv
load_dotenv('/app/backend/.env')
c = MongoClient(os.environ['MONGO_URL'])
c.drop_database(os.environ['DB_NAME'])
print('  dropped', os.environ['DB_NAME'])
PY

echo "[seed_reset] Restarting backend (re-seeds on startup)..."
# Pastikan MongoDB menjawab dulu (drop database pernah membuat mongod SIGABRT & di-spawn ulang
# supervisor; backend yang start di celah itu gagal startup dan reloader-nya diam selamanya).
for i in $(seq 1 60); do
  python3 -c "import os;from pymongo import MongoClient;from dotenv import load_dotenv;load_dotenv('/app/backend/.env');MongoClient(os.environ['MONGO_URL'],serverSelectionTimeoutMS=2000).admin.command('ping')" >/dev/null 2>&1 && break
  sleep 1
done
sudo supervisorctl restart backend >/dev/null 2>&1 || true
# Seed Fase 28b/31/33 mengunggah foto contoh & membangkitkan jadwal: butuh lebih dari
# beberapa detik. Dulu skrip ini tidur 7s lalu langsung menjalankan gate, sehingga gate
# runtime gagal HANYA karena backend belum siap (bukan karena kode salah).
for i in $(seq 1 240); do
  if curl -sf http://localhost:8001/api/health >/dev/null 2>&1; then
    echo "  backend siap setelah ${i}s"
    break
  fi
  # Startup gagal (mis. Mongo belum siap) tidak dipulihkan reloader: coba restart sekali lagi.
  if [ "$i" -eq 90 ] && grep -q "Application startup failed" <(tail -n 5 /var/log/supervisor/backend.err.log); then
    echo "  startup gagal, restart ulang backend"
    sudo supervisorctl restart backend >/dev/null 2>&1 || true
  fi
  sleep 1
done
# Antrean peristiwa seed harus kosong sebelum gate membaca buku besar.
for i in $(seq 1 60); do
  p=$(curl -sf http://localhost:8001/api/health | python3 -c "import sys,json;print(json.load(sys.stdin).get('events_pending',0))" 2>/dev/null || echo 1)
  [ "$p" = "0" ] && echo "  antrean peristiwa kosong" && break
  sleep 2
done
sleep 3

echo "[seed_reset] Running gates..."
bash scripts/run_all_gates.sh
echo "[seed_reset] DONE"
