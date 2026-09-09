#!/usr/bin/env python3
"""verify_32.py — GATE Fase 32: setiap step konstruksi = task berinstruksi + bervalidasi.

Melengkapi `poc_32.py` (aturan bisnis lewat API) dengan cek struktural yang justru sering
membuat fitur terasa setengah jadi:

  A. Tidak ada endpoint `/build` (ops) yatim — Papan Mandor, kebijakan bukti kerja,
     laporan mingguan, dan analitik HARUS punya jalan masuk di frontend.
  B. Tidak ada `data-testid` Fase 32 yang mati.
  C. PENJAGA ANTI-BYPASS masih terpasang di kode: task pekerjaan konstruksi tidak boleh
     bisa diselesaikan lewat jalur task generik (ini pernah bocor dan membuat task tampak
     selesai tanpa bukti sementara progres rumah tidak bergerak).
  D. Kontrak API: kelompok Papan Mandor, kunci kebijakan, isi laporan mingguan, dan
     bentuk analitik sesuai yang dipakai UI.

Jalankan: python3 scripts/verify_32.py
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


def audit_orphan_endpoints(fe: str):
    print("\nA. Endpoint operasional /build tanpa pemakai di frontend")
    src = (BE / "routers" / "build_ops_router.py").read_text(encoding="utf-8")
    for m in re.finditer(r'@router\.(get|post|put|delete)\("([^"]*)"', src):
        method, path = m.group(1).upper(), "/build" + m.group(2)
        pattern = re.escape(path)
        pattern = re.sub(r"\\\{[a-z_]+\\\}", r"[^\"'`]+", pattern)
        check(re.search(pattern, fe) is not None,
              f"{method} {path} dipakai frontend", "-> tidak ada pemanggil di src/")
    check("/build/items/${" in fe or "/build/items/" in fe,
          "GET /build/items/{id} (deep link task) dipakai frontend")


def audit_dead_testids(fe: str):
    print("\nB. data-testid Fase 32 yang tidak dipakai komponen")
    src = (FE / "constants" / "testIds" / "build.js").read_text(encoding="utf-8")
    keys = re.findall(r"^\s{2}([a-zA-Z]+):", src, re.M)
    dead = [k for k in keys if f"BUILD.{k}" not in fe]
    check(not dead, f"{len(keys)} testId modul pembangunan semuanya terpakai",
          f"-> mati: {', '.join(dead)}")
    msrc = (FE / "constants" / "testIds" / "master.js").read_text(encoding="utf-8")
    mkeys = [k for k in re.findall(r"^\s{2}([a-zA-Z]+):", msrc, re.M) if k.startswith("policy")
             or k in ("tabBuildPolicy", "buildPolicyPanel")]
    mdead = [k for k in mkeys if f"MASTER.{k}" not in fe]
    check(not mdead, f"{len(mkeys)} testId kebijakan bukti kerja terpakai",
          f"-> mati: {', '.join(mdead)}")


def audit_bypass_guards():
    print("\nC. Penjaga anti-bypass task konstruksi (kode)")
    wh = (BE / "routers" / "workhub_router.py").read_text(encoding="utf-8")
    wr = (BE / "routers" / "work_router.py").read_text(encoding="utf-8")
    check("def build_item_id_of" in wh and "def build_task_message" in wh,
          "helper pengalih task konstruksi tersedia")
    for ep in ("start", "submit", "verify", "reject"):
        blocks = re.findall(rf'@router\.post\("/tasks/{{task_id}}/{ep}"\)(.*?)(?=@router\.|\Z)',
                            wh, re.S)
        check(bool(blocks) and "build_item_id_of" in blocks[0],
              f"/work/tasks/{{id}}/{ep} menolak task konstruksi")
    check("build_item_id" in wr and "build_task_message" in wr,
          "/work/tasks/{id}/complete menolak task konstruksi")
    fe_card = (FE / "components" / "patterns" / "TaskCard.js").read_text(encoding="utf-8")
    check("build_item_id" in fe_card,
          "kartu tugas mengarahkan task konstruksi ke Papan Mandor (bukan tombol yang ditolak)")
    be_eng = (BE / "build_engine.py").read_text(encoding="utf-8")
    check("reconcile_item_tasks" in be_eng and "task_description" in be_eng,
          "instruksi kerja + rekonsiliasi task hantu terpasang di engine")


def login(email: str) -> dict:
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": PW}, timeout=20)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def audit_contracts():
    print("\nD. Kontrak API Papan Mandor / kebijakan / laporan / analitik")
    try:
        pm = login("pm@sipro.co.id")
        site = login("site@sipro.co.id")
    except Exception as e:                                    # noqa: BLE001
        check(False, "login akun uji", f"-> {e}")
        return
    bd = requests.get(f"{BASE}/build/board/today", headers=site, timeout=60).json().get("data") or {}
    need = ["overdue", "today", "in_progress", "rework", "awaiting_verification",
            "to_verify", "upcoming", "scheduled_later"]
    missing = [k for k in need if k not in (bd.get("groups") or {})]
    check(not missing, "papan mandor memuat semua kelompok yang dirender UI",
          f"-> hilang: {missing}")
    check("geo_required" in (bd.get("policy") or {}),
          "papan mandor membawa kebijakan bukti kerja")
    rows = [r for g in need for r in (bd["groups"].get(g) or [])]
    if rows:
        keys = ["step_code", "name", "unit_code", "min_photos", "checklist_total",
                "instruction", "planned_finish", "status"]
        bad = [k for k in keys if k not in rows[0]]
        check(not bad, "kartu papan mandor memuat instruksi & syarat bukti", f"-> hilang: {bad}")
    else:
        check(True, "kartu papan mandor memuat instruksi & syarat bukti (tidak ada baris hari ini)")
    pol = requests.get(f"{BASE}/build/policy", headers=site, timeout=30).json()
    check(all(k in (pol.get("data") or {}) for k in
              ("geo_required", "camera_only", "min_note_chars", "min_accuracy_m")),
          "kebijakan bukti kerja memuat semua sakelar yang dirender UI")
    check(pol.get("can_edit") is False, "pelaksana tidak diberi hak ubah kebijakan")
    lst = requests.get(f"{BASE}/build/reports/weekly", headers=pm, timeout=60).json()
    check("can_run" in lst, "daftar laporan mingguan menyertakan hak jalankan")
    if lst.get("data"):
        rid = lst["data"][0]["id"]
        rep = requests.get(f"{BASE}/build/reports/weekly/{rid}", headers=pm,
                           timeout=60).json().get("data") or {}
        bad = [k for k in ("totals", "houses", "curve", "delays_top", "week_key") if k not in rep]
        check(not bad, "laporan mingguan memuat bagian yang dirender UI", f"-> hilang: {bad}")
        pdf = requests.get(f"{BASE}/build/reports/weekly/{rid}/pdf", headers=pm, timeout=90)
        check(pdf.status_code == 200 and pdf.content[:4] == b"%PDF",
              "PDF laporan mingguan valid", f"-> {pdf.status_code}")
    else:
        check(False, "ada laporan mingguan untuk diuji", "-> jalankan POST /build/reports/weekly/run")
    an = requests.get(f"{BASE}/build/analytics/delays", headers=pm, timeout=90).json().get("data") or {}
    bad = [k for k in ("summary", "by_step", "by_person", "by_unit_type",
                       "recommendations") if k not in an]
    check(not bad, "analitik keterlambatan memuat semua bagian", f"-> hilang: {bad}")


def main():
    fe = fe_sources()
    audit_orphan_endpoints(fe)
    audit_dead_testids(fe)
    audit_bypass_guards()
    audit_contracts()
    print("-" * 60)
    print(f"HASIL: {ok_n} PASS, {fail_n} FAIL")
    if fail_n:
        sys.exit(1)
    print("VERIFY 32 PASSED")


if __name__ == "__main__":
    main()
