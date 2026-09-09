#!/usr/bin/env python3
"""fase52_permission_toggle.py — alat uji: buat/pulihkan keadaan "primer 200 + panel 403".

KENAPA ALAT INI ADA
Cacat Fase 52 hanya menampakkan diri ketika sebuah panel samping dijawab 403 SEMENTARA
permintaan primer halaman dijawab 200. Sesudah izin `appointments` diberikan ke keuangan
(perbaikan backend Fase 52), tidak ada lagi peran demo yang menghasilkan kombinasi itu —
padahal kombinasinya masih MUNGKIN kapan saja, karena admin boleh mencabut izin apa pun dari
layar Hak Akses (`/admin/permissions`). Tanpa alat ini, penguji manusia/agen harus mengklik
matriks izin dan berisiko LUPA memulihkannya.

Alat ini memakai API resmi (`PUT /api/admin/permissions`) — bukan menulis langsung ke
database — sehingga jalur yang diuji sama dengan jalur yang dipakai admin sungguhan.

PEMAKAIAN
    python3 scripts/fase52_permission_toggle.py --revoke     # cabut appointments dari finance
    python3 scripts/fase52_permission_toggle.py --status     # lihat keadaan sekarang + bukti HTTP
    python3 scripts/fase52_permission_toggle.py --restore    # PULIHKAN ke ["view_all"]

Cadangan matriks disimpan di `memory/gatelogs/fase52_matrix_backup.json` supaya pemulihan
tetap bisa dilakukan walau proses uji mati di tengah jalan.
"""
import argparse
import copy
import json
import os
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
BACKUP = ROOT / "memory" / "gatelogs" / "fase52_matrix_backup.json"
BASE = os.environ.get("SIPRO_API", "http://localhost:8001/api")
PASSWORD = os.environ.get("SIPRO_DEMO_PASSWORD", "Sipro#2026")
ADMIN = "superadmin@sipro.co.id"
ROLE = "finance"
RESOURCE = "appointments"
# Izin yang BENAR menurut kode (backend/rbac.py DEFAULT_PERMISSIONS["appointments"]):
# keuangan boleh MEMBACA jadwal survei, tidak menjadwalkan.
CORRECT = ["view_all"]


def token(email: str) -> str:
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": PASSWORD}, timeout=20)
    r.raise_for_status()
    return r.json()["access_token"]


def head(t: str):
    print(f"\n{t}\n" + "-" * len(t))


def get_matrix(h: dict) -> dict:
    r = requests.get(f"{BASE}/admin/permissions", headers=h, timeout=30)
    r.raise_for_status()
    return r.json()["data"]["matrix"]


def put_matrix(h: dict, matrix: dict) -> list:
    r = requests.put(f"{BASE}/admin/permissions", headers=h, json={"matrix": matrix}, timeout=30)
    if r.status_code != 200:
        print(f"  GAGAL menyimpan matriks: {r.status_code} {r.text[:200]}")
        sys.exit(2)
    return r.json()["data"].get("changes") or []


def probe(lead_id: str = None) -> dict:
    """Bukti HTTP: apa yang server jawab untuk permintaan halaman profil lead."""
    h = {"Authorization": f"Bearer {token(ROLE + '@sipro.co.id')}"}
    if not lead_id:
        rows = requests.get(f"{BASE}/leads", headers=h, params={"limit": 1}, timeout=20)
        if rows.status_code != 200 or not (rows.json().get("data") or []):
            return {"error": f"tidak bisa mengambil lead uji ({rows.status_code})"}
        lead_id = rows.json()["data"][0]["id"]
    out = {"lead_id": lead_id}
    out["primer /leads/{id}"] = requests.get(f"{BASE}/leads/{lead_id}", headers=h, timeout=20).status_code
    out["panel /appointments"] = requests.get(f"{BASE}/appointments", headers=h,
                                              params={"lead_id": lead_id}, timeout=20).status_code
    out["panel /deals"] = requests.get(f"{BASE}/deals", headers=h,
                                       params={"lead_id": lead_id}, timeout=20).status_code
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--revoke", action="store_true",
                   help=f"cabut '{RESOURCE}' dari peran '{ROLE}' (daftar aksi kosong = pencabutan)")
    g.add_argument("--restore", action="store_true", help=f"pulihkan menjadi {CORRECT}")
    g.add_argument("--status", action="store_true", help="tampilkan keadaan + bukti HTTP")
    ap.add_argument("--lead", default=None, help="id lead uji (opsional)")
    args = ap.parse_args()

    h = {"Authorization": f"Bearer {token(ADMIN)}"}
    matrix = get_matrix(h)
    sekarang = (matrix.get(RESOURCE) or {}).get(ROLE, "(tidak tertulis di matriks)")

    if args.status:
        head("Keadaan izin sekarang")
        print(f"  {RESOURCE}.{ROLE} = {sekarang}")
        head("Bukti HTTP (sebagai finance@)")
        for k, v in probe(args.lead).items():
            print(f"  {k:24s} = {v}")
        print("\nCatatan: kombinasi yang menguji cacat Fase 52 adalah "
              "primer=200 SEKALIGUS panel=403.")
        return

    if args.revoke:
        BACKUP.parent.mkdir(parents=True, exist_ok=True)
        BACKUP.write_text(json.dumps(matrix, indent=1))
        draft = copy.deepcopy(matrix)
        draft.setdefault(RESOURCE, {})[ROLE] = []
        changes = put_matrix(h, draft)
        head("Izin DICABUT (sementara, untuk pengujian)")
        print(f"  cadangan matriks: {BACKUP.relative_to(ROOT)}")
        for c in changes:
            print(f"  {c['resource']}.{c['role']}: {c['dari']} -> {c['menjadi']}")
        head("Bukti HTTP (sebagai finance@)")
        bukti = probe(args.lead)
        for k, v in bukti.items():
            print(f"  {k:24s} = {v}")
        siap = bukti.get("primer /leads/{id}") == 200 and bukti.get("panel /appointments") == 403
        print(f"\n  Keadaan uji siap? {'YA' if siap else 'BELUM'} "
              f"(butuh primer=200 & panel=403)")
        print("\n  JANGAN LUPA: python3 scripts/fase52_permission_toggle.py --restore")
        sys.exit(0 if siap else 3)

    # --restore
    draft = copy.deepcopy(matrix)
    draft.setdefault(RESOURCE, {})[ROLE] = list(CORRECT)
    changes = put_matrix(h, draft)
    head("Izin DIPULIHKAN")
    for c in changes:
        print(f"  {c['resource']}.{c['role']}: {c['dari']} -> {c['menjadi']}")
    if not changes:
        print(f"  (tidak ada perubahan — {RESOURCE}.{ROLE} sudah {CORRECT})")
    head("Bukti HTTP (sebagai finance@)")
    bukti = probe(args.lead)
    for k, v in bukti.items():
        print(f"  {k:24s} = {v}")
    ok = bukti.get("primer /leads/{id}") == 200 and bukti.get("panel /appointments") == 200
    print(f"\n  Pemulihan benar? {'YA' if ok else 'BELUM — periksa manual'}")
    sys.exit(0 if ok else 4)


if __name__ == "__main__":
    main()
