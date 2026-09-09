#!/usr/bin/env bash
# run_legacy_suite.sh — jalankan suite pytest legacy secara TERISOLASI dari data demo.
#
# Masalah yang diselesaikan (backlog P1 "fixture legacy mandiri"): suite lama menanam lead,
# pembeli, kontrak, proyek berlabel uji ke basis data demo; gate forensik/invarian kemudian
# merah karena bahan uji "dipajang ke pengguna". Pembersihan per fixture tidak pernah tuntas.
#
# Pendekatan: snapshot org lewat API aplikasi SEBELUM suite → jalankan pytest → pulihkan
# snapshot (mode replace) SESUDAH suite → hapus snapshot. Basis data kembali ke keadaan
# pra-suite; gate yang membaca data tetap hijau. Memakai fitur backup/restore produk sendiri
# (diuji oleh test_datamgmt_fase56), bukan manipulasi DB langsung.
#
# Pakai:  bash scripts/run_legacy_suite.sh [argumen pytest tambahan]
# Contoh: bash scripts/run_legacy_suite.sh -k "p88 or p93"
set -u
cd "$(dirname "$0")/.."
API="http://localhost:8001/api"
LOG_DIR="memory/verification"; mkdir -p "$LOG_DIR"
STAMP="$(date +%Y%m%d-%H%M%S)"
LOG="$LOG_DIR/legacy-suite-$STAMP.log"

TOKEN=$(curl -s -X POST "$API/auth/login" -H "Content-Type: application/json" \
  -d '{"email":"superadmin@sipro.co.id","password":"Sipro#2026"}' \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])") || { echo "login gagal"; exit 2; }
AUTH="Authorization: Bearer $TOKEN"

SNAP_ID=$(curl -s -X POST "$API/data-mgmt/snapshots" -H "$AUTH" \
  -F "label=pra-suite-legacy-$STAMP" -F "include_files=true" \
  | python3 -c "import sys,json;d=json.load(sys.stdin);print(d.get('id') or d['data']['id'])") || { echo "snapshot gagal"; exit 2; }
echo "snapshot pra-suite: $SNAP_ID" | tee "$LOG"

pushd backend >/dev/null
timeout 3000 python -m pytest tests -p no:cacheprovider --ignore=tests/test_iter148_purge_and_org.py \
  -q --no-header -rsfE --maxfail=500 -o addopts="" "$@" 2>&1 | tee -a "../$LOG"
RC=${PIPESTATUS[0]}
popd >/dev/null

echo "--- pulihkan snapshot $SNAP_ID (replace) ---" | tee -a "$LOG"
curl -s -X POST "$API/data-mgmt/snapshots/$SNAP_ID/restore" -H "$AUTH" \
  -F "mode=replace" -F "confirm=RESTORE" \
  | python3 -c "import sys,json;d=json.load(sys.stdin);r=d.get('report') or d.get('data',{}).get('report') or {};print('koleksi dipulihkan:',len(r), '| peringatan:', r.get('_warnings'))" | tee -a "$LOG"
curl -s -X DELETE "$API/data-mgmt/snapshots/$SNAP_ID" -H "$AUTH" >/dev/null
# snapshot 'pra-restore' otomatis dari proses restore juga dibuang (tidak ada gunanya di sini)
curl -s "$API/data-mgmt/snapshots" -H "$AUTH" | python3 -c "
import sys,json,subprocess
rows=json.load(sys.stdin); rows=rows.get('data', rows) if isinstance(rows, dict) else rows
for s in rows:
    if s.get('kind')=='auto' and 'pra-restore' in (s.get('label') or ''):
        subprocess.run(['curl','-s','-o','/dev/null','-X','DELETE','$API/data-mgmt/snapshots/'+s['id'],'-H','$AUTH'])"
echo "selesai — hasil pytest rc=$RC, log: $LOG" | tee -a "$LOG"
exit "$RC"
