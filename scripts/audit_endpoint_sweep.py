#!/usr/bin/env python3
"""audit_endpoint_sweep.py — SIPRO (adopsi pola kn/KN3).

Login sebagai owner (full-access), hit SETIAP GET route /api dari openapi.json,
resolve query wajib bila diketahui, catat status + emptiness + error.
FAIL bila ada 5xx atau 4xx tak terduga (selain akses yang memang diblok).
"""
import sys
import time
from datetime import datetime

import requests

BASE = "http://localhost:8001"
API = BASE + "/api"
PW = "Sipro#2026"

# Query wajib untuk route tertentu (agar tidak 422/400).
# Nilai bisa berupa dict statis, atau fungsi(headers) -> dict yang MENCARI id NYATA lewat
# API lain. Memakai id nyata penting: probe palsu hanya membuktikan route tidak 500,
# sedangkan id nyata membuktikan route benar-benar mengembalikan data entitas itu.
QUERY_DEFAULTS = {
    "/api/activities": {"entity_type": "lead", "entity_id": "sweep-probe"},
}


def _first_id(headers, path, key="id"):
    try:
        r = requests.get(f"{API}{path}", headers=headers, timeout=10)
        rows = r.json().get("data") or []
        return rows[0].get(key) if rows else None
    except Exception:  # noqa: BLE001
        return None


def _lead_entity(headers):
    lead_id = _first_id(headers, "/leads?limit=1")
    return {"entity_type": "lead", "entity_id": lead_id} if lead_id else None


def _setting_keys(headers):
    key = _first_id(headers, "/settings", key="key")
    return {"keys": key} if key else None


def _cash_lock_period(headers):
    """Fase 82: pratinjau kunci kas WAJIB menyebut akun kas + periode (tanpa itu jawabannya
    akan mengarang saldo akun siapa). 400 tanpa parameter adalah validasi yang BENAR."""
    acc = _first_id(headers, "/cash-bank/accounts")
    return {"account_id": acc, "period": time.strftime("%Y-%m")} if acc else None


def _pricing_unit(headers):
    """Fase 77: opsi diskon/promo BERLAKU untuk satu unit — tanpa unit tidak ada jawaban jujur."""
    unit_id = _first_id(headers, "/units?limit=1")
    return {"unit_id": unit_id} if unit_id else None


def _unit_object(headers):
    """Fase 46: `/permits/coverage` WAJIB menyebut objeknya (unit/blok/cluster/proyek).

    400 tanpa objek adalah validasi yang BENAR (tanpa objek, jawabannya akan mengarang izin
    milik siapa). Sweep karena itu menyediakan unit NYATA supaya yang diuji adalah
    jawabannya, bukan pesan validasinya.
    """
    unit_id = _first_id(headers, "/units?limit=1")
    return {"unit_id": unit_id} if unit_id else None


# Fase 39b: tiga route baru (checklist dokumen + nilai efektif setting) WAJIB punya
# parameter entitas/kunci. Dulu sweep memanggilnya tanpa parameter lalu menghitung 400
# sebagai kerusakan — padahal 400 di situ adalah validasi yang benar. Sekarang sweep
# menyediakan parameter NYATA sehingga yang diuji adalah jawaban sebenarnya.
# Fase 47D: `/labor/attendance/diary-check` WAJIB menyebut proyek + tanggal kerja. Tanpa
# keduanya jawabannya akan mengarang "selisih" milik proyek/hari mana pun, jadi 400 di situ
# adalah validasi yang benar — sweep menyediakan proyek NYATA dan hari ini.
def _project_workday(headers):
    project_id = _first_id(headers, "/projects?limit=1")
    if not project_id:
        return None
    return {"project_id": project_id, "work_date": datetime.now().strftime("%Y-%m-%d")}


# Fase 50A: tiga route serah terima/garansi WAJIB menyebut rumah atau komplain yang dimaksud.
# Tanpa itu jawabannya akan mengarang daftar periksa/masa garansi milik rumah mana pun, jadi
# 400 di situ adalah validasi yang BENAR — sweep menyediakan id NYATA supaya yang diuji adalah
# jawabannya (daftar periksa & masa garansi), bukan pesan validasinya.
def _handover_unit(headers):
    unit_id = _first_id(headers, "/units?limit=1")
    return {"unit_id": unit_id} if unit_id else None


def _complaint_probe(headers):
    cid = _first_id(headers, "/complaints?limit=1")
    return {"complaint_id": cid} if cid else None


# Fase 56C: `/cancellations/preview` WAJIB menyebut kontrak yang dimaksud. Tanpa itu
# jawabannya akan mengarang potongan/refund milik kontrak mana pun, jadi 400 di situ adalah
# validasi yang BENAR — sweep menyediakan kontrak NYATA supaya yang diuji adalah hitungannya.
def _contract_probe(headers):
    cid = _first_id(headers, "/contracts?limit=1")
    return {"contract_id": cid} if cid else None


# Fase 62: `/docs/warning-letters/state` WAJIB menyebut transaksi yang dimaksud. Tanpa itu
# jawabannya akan mengarang tunggakan milik pembeli mana pun, jadi 400 di situ adalah
# validasi yang BENAR — sweep menyediakan transaksi menunggak NYATA.
def _arrears_deal(headers):
    try:
        r = requests.get(f"{API}/finance/arrears/candidates", headers=headers, timeout=20)
        rows = ((r.json().get("data") or {}).get("rows") or [])
        return {"deal_id": rows[0]["deal_id"]} if rows else None
    except Exception:  # noqa: BLE001
        return None


QUERY_RESOLVERS = {
    "/api/doc/submissions": _lead_entity,
    "/api/doc/matrix": _lead_entity,
    "/api/settings/effective": _setting_keys,
    "/api/permits/coverage": _unit_object,
    "/api/labor/attendance/diary-check": _project_workday,
    "/api/handover/check": _handover_unit,
    "/api/handover/warranty/unit": _handover_unit,
    "/api/handover/warranty/for-complaint": _complaint_probe,
    "/api/cancellations/preview": _contract_probe,
    "/api/docs/warning-letters/state": _arrears_deal,
    "/api/cash-bank/locks/preview": _cash_lock_period,
    "/api/pricing/options": _pricing_unit,
}
# Endpoint streaming (SSE) yang TIDAK boleh disweep (koneksi long-lived -> akan timeout).
SKIP_STREAMING = {"/api/notifications/stream"}
# GERBANG KEPATUHAN (Fase 49E/49F): endpoint berkas pajak MEMANG menjawab 409 bila data wajib
# belum lengkap — "tidak ada berkas berkolom kosong" adalah perilaku yang diminta, bukan cacat.
# Tetap diperiksa: jawabannya WAJIB menyebut alasannya (bukan 409 tanpa penjelasan).
EXPORT_GATED = {"/api/tax/compliance/faktur-export/file",
                "/api/tax/compliance/withholding-export/file"}
errors = []


def login(email):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": PW}, timeout=10)
    r.raise_for_status()
    return r.json()["access_token"]


def main():
    token = login("owner@sipro.co.id")
    headers = {"Authorization": f"Bearer {token}"}
    spec = requests.get(f"{BASE}/openapi.json", timeout=10).json()
    paths = spec.get("paths", {})
    get_routes = [(p, i) for p, i in paths.items() if "get" in i and p.startswith("/api")]
    print(f"Menyapu {len(get_routes)} GET route /api sebagai owner...\n")

    for p, _info in sorted(get_routes):
        if p in SKIP_STREAMING:
            print(f"  [SKIP] GET {p} (streaming SSE endpoint — long-lived, tidak disweep)")
            continue
        if "{" in p:
            print(f"  [SKIP] GET {p} (butuh path param — belum ada resolver di Fase 0)")
            continue
        params = QUERY_DEFAULTS.get(p, {})
        if p in QUERY_RESOLVERS:
            resolved = QUERY_RESOLVERS[p](headers)
            if not resolved:
                print(f"  [ERROR] GET {p} -> parameter wajib tidak bisa di-resolve "
                      f"(tidak ada data untuk diuji)")
                errors.append(p)
                continue
            params = resolved
        try:
            r = requests.get(f"{BASE}{p}", headers=headers, params=params, timeout=10)
        except Exception as e:  # noqa: BLE001
            print(f"  [ERROR] GET {p} -> exception {e}")
            errors.append(p)
            continue
        status = r.status_code
        note = ""
        if status == 200:
            try:
                j = r.json()
                d = j.get("data") if isinstance(j, dict) else None
                if isinstance(d, list):
                    note = f" (data: {len(d)} item)"
                elif isinstance(d, dict):
                    note = " (objek)"
            except Exception:
                pass
            print(f"  [OK {status}] GET {p}{note}")
        elif status in (401, 403):
            print(f"  [WARN {status}] GET {p} (akses ditolak untuk owner — tinjau)")
        elif status == 409 and p in EXPORT_GATED and "ditahan" in r.text.lower():
            print(f"  [OK {status}] GET {p} (ekspor DITAHAN beralasan — perilaku benar)")
        else:
            print(f"  [ERROR {status}] GET {p}")
            errors.append(p)

    print("-" * 50)
    if errors:
        print(f"ENDPOINT SWEEP FAILED: {len(errors)} route bermasalah")
        sys.exit(1)
    print("ENDPOINT SWEEP PASSED")


if __name__ == "__main__":
    main()
