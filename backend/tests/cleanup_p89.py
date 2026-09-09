"""Bersihkan kupon TEST_ yang dibuat saat uji Fase 89 (endpoint hanya mendukung nonaktifkan)."""
import os

import requests
from dotenv import dotenv_values

fe = dotenv_values("/app/frontend/.env")
API = (os.environ.get("REACT_APP_BACKEND_URL") or fe.get("REACT_APP_BACKEND_URL")).rstrip("/") + "/api"
s = requests.Session()
s.post(f"{API}/auth/login", json={"email": "superadmin@sipro.co.id", "password": "Sipro#2026"}, timeout=60)
rows = s.get(f"{API}/pricing/coupons", timeout=60).json()["data"]
for r in rows:
    if str(r.get("code", "")).startswith("UJI-DP-89") and r.get("active"):
        out = s.put(f"{API}/pricing/coupons/{r['id']}", json={"active": False}, timeout=60)
        print(r["code"], out.status_code)
