#!/usr/bin/env bash
# Tarik kode terbaru dari GitHub, rebuild, restart tanpa menghapus data.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "[update] git pull"
git fetch --all --prune
git reset --hard "origin/$(git rev-parse --abbrev-ref HEAD)"

cd deploy
echo "[update] build & restart"
docker compose up -d --build --remove-orphans
docker image prune -f >/dev/null

echo -n "[update] menunggu backend sehat "
for i in $(seq 1 60); do
  if docker compose exec -T backend python3 -c "import urllib.request;urllib.request.urlopen('http://localhost:8001/api/health',timeout=3)" >/dev/null 2>&1; then
    echo " ok"; exit 0
  fi
  echo -n "."; sleep 5
done
echo; echo "[update] backend belum sehat — docker compose logs backend"; exit 1
