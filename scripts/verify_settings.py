#!/usr/bin/env python3
"""verify_settings.py — GATE Pusat Konfigurasi (Fase 39).

Janji bisnis yang dijaga:
  1. Aturan bisnis TIDAK hard-code: registry setting terisi & nilai efektif bisa dibaca.
  2. Setting SENSITIF tidak bisa diubah tanpa ALASAN (uang/legal wajib punya jejak).
  3. Nilai di luar batas ditolak (setting salah tidak boleh merusak sistem).
  4. Riwayat perubahan menyimpan AKTOR + ALASAN, dan reset mengembalikan nilai bawaan.
  5. RBAC: peran non-admin boleh MELIHAT, tidak boleh MENGUBAH.

Exit !=0 bila ada FAIL.
"""
import sys

import requests

BASE = "http://localhost:8001/api"
PW = "Sipro#2026"
KEY = "reservation.max_active_per_lead"
fails = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f" — {detail}" if detail else ""))
    if not cond:
        fails.append(name)


def login(email):
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": PW}, timeout=15)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def main():
    admin = login("superadmin@sipro.co.id")
    sales = login("sales@sipro.co.id")

    print("\n1. Registry setting terbaca")
    r = requests.get(f"{BASE}/settings", headers=admin, timeout=20)
    check("GET /settings = 200", r.status_code == 200, f"got {r.status_code}")
    body = r.json() if r.status_code == 200 else {}
    rows = body.get("data") or []
    check("jumlah setting >= 40", len(rows) >= 40, f"{len(rows)} setting")
    check("setiap setting punya label+help+tipe",
          all(x.get("label") and x.get("help") and x.get("type") for x in rows))
    doc_based = [x for x in rows if x.get("source") == "DOC"]
    check("ada setting berdasar dokumen legal owner", len(doc_based) >= 10,
          f"{len(doc_based)} setting bersumber DOC")
    check("kelompok setting terisi", len(body.get("groups") or []) >= 8)

    print("\n2. Setting sensitif wajib beralasan")
    r = requests.put(f"{BASE}/settings/{KEY}", headers=admin, json={"value": 2}, timeout=15)
    check("ubah tanpa alasan = 400", r.status_code == 400, f"got {r.status_code}")
    r = requests.put(f"{BASE}/settings/{KEY}", headers=admin,
                     json={"value": 2, "reason": "gate verify_settings"}, timeout=15)
    check("ubah dengan alasan = 200", r.status_code == 200, f"got {r.status_code}")

    print("\n3. Nilai efektif & validasi batas")
    r = requests.get(f"{BASE}/settings/effective?keys={KEY}", headers=admin, timeout=15)
    check("nilai efektif mengikuti perubahan",
          r.status_code == 200 and r.json()["data"][KEY] == 2, r.text[:120])
    r = requests.put(f"{BASE}/settings/{KEY}", headers=admin,
                     json={"value": 99, "reason": "uji batas"}, timeout=15)
    check("nilai di luar batas = 400", r.status_code == 400, f"got {r.status_code}")
    r = requests.get(f"{BASE}/settings/effective?keys=tidak.ada.key", headers=admin, timeout=15)
    check("key tidak dikenal = 400", r.status_code == 400, f"got {r.status_code}")

    print("\n4. Jejak & reset")
    r = requests.get(f"{BASE}/settings/{KEY}/history", headers=admin, timeout=15)
    hist = (r.json().get("data") or []) if r.status_code == 200 else []
    check("riwayat mencatat aktor & alasan",
          bool(hist) and hist[0].get("by") and hist[0].get("reason"), str(hist[:1])[:150])
    r = requests.post(f"{BASE}/settings/{KEY}/reset", headers=admin, timeout=15)
    check("reset = 200", r.status_code == 200, f"got {r.status_code}")
    r = requests.get(f"{BASE}/settings/effective?keys={KEY}", headers=admin, timeout=15)
    check("nilai kembali ke bawaan (1)",
          r.status_code == 200 and r.json()["data"][KEY] == 1, r.text[:120])

    print("\n5. RBAC")
    r = requests.get(f"{BASE}/settings", headers=sales, timeout=15)
    check("sales boleh melihat setting (200)", r.status_code == 200, f"got {r.status_code}")
    r = requests.put(f"{BASE}/settings/reservation.hold_days", headers=sales,
                     json={"value": 30}, timeout=15)
    check("sales TIDAK boleh mengubah (403)", r.status_code == 403, f"got {r.status_code}")

    print("-" * 56)
    if fails:
        print(f"SETTINGS GATE FAILED: {len(fails)} temuan — {fails}")
        sys.exit(1)
    print("SETTINGS GATE PASSED")


if __name__ == "__main__":
    main()
