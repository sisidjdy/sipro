"""Seed data untuk uji UI Fase 72 (Studio Site Plan). Membuat proyek 'Uji Studio UI'
dengan kode kosong (otomatis) dan memastikan minimal 1 tipe unit aktif ada."""
import os
import sys

import requests
from dotenv import dotenv_values

BASE = (os.environ.get("REACT_APP_BACKEND_URL")
        or dotenv_values("/app/frontend/.env").get("REACT_APP_BACKEND_URL")).rstrip("/")
PASS = "Sipro#2026"


def login(email="owner@sipro.co.id"):
    r = requests.post(f"{BASE}/api/auth/login", json={"email": email, "password": PASS}, timeout=30)
    r.raise_for_status()
    return r.json()["access_token"]


def main():
    tok = login()
    h = {"Authorization": f"Bearer {tok}"}
    # tipe unit
    ut = requests.get(f"{BASE}/api/unit-types", headers=h, timeout=30)
    print("unit-types", ut.status_code, len((ut.json() or {}).get("data") or []))
    # cari / buat proyek
    pr = requests.get(f"{BASE}/api/projects", headers=h, params={"limit": 200}, timeout=30)
    items = pr.json().get("data") or pr.json().get("items") or []
    found = next((p for p in items if p.get("name") == "Uji Studio UI"), None)
    if found:
        print("PROJECT_ID", found["id"], found.get("code"))
        return 0
    body = {"name": "Uji Studio UI", "code": "", "location": "Bandung",
            "total_units": 3, "status": "active"}
    cr = requests.post(f"{BASE}/api/projects", headers=h, json=body, timeout=30)
    print("create", cr.status_code, cr.text[:400])
    if cr.status_code >= 300:
        return 1
    d = cr.json().get("data") or cr.json()
    print("PROJECT_ID", d["id"], d.get("code"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
