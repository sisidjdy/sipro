#!/usr/bin/env bash
# _tok.sh <email> -> cetak access_token. Sandi demo seragam Sipro#2026.
E="${1:-superadmin@sipro.co.id}"
curl -s -X POST http://localhost:8001/api/auth/login -H "Content-Type: application/json" \
  -d "{\"email\":\"$E\",\"password\":\"Sipro#2026\"}" \
  | python3 -c "import sys,json;print(json.load(sys.stdin).get('access_token',''))"
