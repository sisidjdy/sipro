#!/usr/bin/env python3
"""verify_31.py — GATE Fase 31: jadwal pembangunan berbukti per unit.

Melengkapi `poc_31.py` (yang menguji ATURAN BISNIS lewat API nyata) dengan tiga cek
yang justru sering terlewat dan membuat fitur terasa "setengah jadi":

  A. Tidak ada endpoint `/build/...` yatim — setiap kemampuan backend HARUS punya
     jalan masuk di frontend (dulu banyak fitur hanya bisa dipakai lewat curl).
  B. Tidak ada `data-testid` Fase 31 yang mati — testId yang didaftarkan tetapi tidak
     dipakai membuat skenario uji otomatis memilih selector yang tidak pernah ada.
  C. Kontrak antrean kerja: filter `status=todo|open` benar-benar mempersempit daftar
     (dipakai UI "Perlu saya kerjakan") dan ringkasan monitoring memuat kunci yang
     dipakai kartu beranda.

Jalankan: python3 scripts/verify_31.py
"""
import os
import re
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
BE = ROOT / "backend"
FE = ROOT / "frontend" / "src"
BASE = os.environ.get("SIPRO_BASE", "http://localhost:8001/api")
PW = "Sipro#2026"

ok_n, fail_n = 0, 0


def check(cond, label, detail=""):
    global ok_n, fail_n
    if cond:
        ok_n += 1
        print(f"  PASS  {label}")
    else:
        fail_n += 1
        print(f"  FAIL  {label} {detail}")


def fe_sources() -> str:
    out = []
    for p in FE.rglob("*.js"):
        if "components/ui/" in p.as_posix():
            continue
        out.append(p.read_text(encoding="utf-8", errors="ignore"))
    return "\n".join(out)


def backend_build_routes() -> list:
    src = (BE / "routers" / "build_router.py").read_text(encoding="utf-8")
    routes = []
    for m in re.finditer(r'@router\.(get|post|put|delete)\("([^"]*)"', src):
        routes.append((m.group(1).upper(), "/build" + m.group(2)))
    return routes


def audit_orphan_endpoints(fe: str):
    print("\nA. Endpoint /build yang tidak punya pemakai di frontend")
    for method, path in backend_build_routes():
        pattern = re.escape(path).replace(r"\{", "{").replace(r"\}", "}")
        pattern = re.sub(r"\{[a-z_]+\}", r"[^\"'`/]+", pattern)
        check(re.search(pattern, fe) is not None,
              f"{method} {path} dipakai frontend", "-> tidak ada pemanggil di src/")


def audit_dead_testids(fe: str):
    print("\nB. data-testid Fase 31 yang tidak dipakai komponen")
    src = (FE / "constants" / "testIds" / "build.js").read_text(encoding="utf-8")
    keys = re.findall(r"^\s{2}([a-zA-Z]+):", src, re.M)
    dead = [k for k in keys if f"BUILD.{k}" not in fe]
    check(not dead, f"{len(keys)} testId Fase 31 semuanya terpakai",
          f"-> mati: {', '.join(dead)}")


def login(email: str) -> str:
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": PW}, timeout=20)
    r.raise_for_status()
    return r.json()["access_token"]


def h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def audit_queue_contract():
    print("\nC. Kontrak antrean kerja & ringkasan monitoring")
    try:
        pm = login("pm@sipro.co.id")
        site = login("site@sipro.co.id")
    except Exception as e:                                    # noqa: BLE001
        check(False, "login akun uji", f"-> {e}")
        return
    allr = requests.get(f"{BASE}/build/items", headers=h(pm),
                        params={"limit": 1}).json()
    todo = requests.get(f"{BASE}/build/items", headers=h(pm),
                        params={"status": "todo", "limit": 100}).json()
    openq = requests.get(f"{BASE}/build/items", headers=h(pm),
                         params={"status": "open", "limit": 1}).json()
    mine = requests.get(f"{BASE}/build/items", headers=h(site),
                        params={"mine": "true", "status": "todo", "limit": 100}).json()
    check(allr.get("total", 0) > 0, "daftar pekerjaan terisi", f"-> {allr.get('total')}")
    check(todo.get("total", 0) <= openq.get("total", 0) <= allr.get("total", 0),
          "filter todo <= open <= semua",
          f"-> todo={todo.get('total')} open={openq.get('total')} all={allr.get('total')}")
    check(all(i["status"] in ("ready", "in_progress", "rework") for i in todo.get("data", [])),
          "status=todo hanya memuat pekerjaan yang boleh dikerjakan")
    check(all(i.get("assigned_to") == "site@sipro.co.id" for i in mine.get("data", [])),
          "mine=true hanya memuat pekerjaan milik pengguna")
    s = requests.get(f"{BASE}/build/summary", headers=h(pm)).json().get("data") or {}
    need = ["units_total", "scheduled", "unscheduled", "avg_progress", "avg_planned",
            "awaiting_verification", "rework", "late_items", "blocked_items", "overrides",
            "at_risk"]
    missing = [k for k in need if k not in s]
    check(not missing, "ringkasan monitoring memuat semua kunci kartu beranda",
          f"-> hilang: {missing}")
    can = requests.get(f"{BASE}/build/schedules", headers=h(site),
                       params={"limit": 1}).json().get("can") or {}
    check(can.get("submit") is True and can.get("verify") is False,
          "hak akses pelaksana: boleh ajukan, tidak boleh verifikasi", f"-> {can}")


def main():
    fe = fe_sources()
    print("VERIFIKASI FASE 31 — Jadwal Pembangunan Berbukti")
    audit_orphan_endpoints(fe)
    audit_dead_testids(fe)
    audit_queue_contract()
    print("-" * 60)
    print(f"HASIL: {ok_n} PASS, {fail_n} FAIL")
    if fail_n:
        sys.exit(1)
    print("VERIFY 31 PASSED")


if __name__ == "__main__":
    main()
