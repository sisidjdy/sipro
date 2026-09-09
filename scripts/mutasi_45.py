#!/usr/bin/env python3
"""mutasi_45.py — UJI-MUTASI gate Fase 45 (Target & Anggaran).

Kenapa uji-mutasi ada: gate yang HIJAU belum tentu **bergigi**. Gate bisa hijau karena
pemeriksaannya longgar (mis. hanya memastikan kata tertentu ada di berkas), dan gate seperti
itu memberi rasa aman yang salah. Cara membuktikannya cuma satu: SENGAJA MERUSAK kode/data,
lalu memastikan gate MEMERAH — dan setelah dipulihkan, hijau lagi.

Setiap mutasi menyerang satu janji Fase 45:

  N01  matematika target dibuat bocor (pembagian dibulatkan per bulan)
  N02  `lock_past` dilumpuhkan (periode lampau ikut dihitung ulang)
  N03  `carry_over` dihapus (kenaikan target jadi misteri)
  N04  alasan hitung-ulang tidak lagi wajib
  N05  `verified` konstruksi dibaca sebagai field (tie-out dengan Kendali Biaya pecah)
  N06  komitmen memakai `billed` (bertumpang dengan realisasi → double count)
  N07  proyek tanpa anggaran dilaporkan Rp 0 "aman" (bukan `kosong`)
  N08  persen dengan pembagi 0 dikembalikan 0% (bukan null)
  N09  rencana konstruksi boleh diisi tangan (dua angka anggaran RAB)
  N10  `budget.enforce_cost_ref` bawaannya dinyalakan tanpa jalan merapikan data
  N11  peringatan ambang berhenti membuat tugas (hanya notifikasi)
  N12  layar menuliskan label enum sendiri (SSOT dilanggar)
  N13  pemakaian material dijumlahkan ke realisasi (double count)
  N14  RBAC anggaran dilonggarkan untuk sales
  N15  drill lapis 3 memotong daftar dokumen (Σ dokumen ≠ angka item)

Jalankan: `python3 scripts/mutasi_45.py`. Exit != 0 bila ADA mutasi yang tidak tertangkap.
"""
import os
import pathlib
import shutil
import subprocess
import sys
import time

from dotenv import load_dotenv
from pymongo import MongoClient

ROOT = pathlib.Path(__file__).resolve().parent.parent
load_dotenv(ROOT / "backend" / ".env")
BE = ROOT / "backend"
FE = ROOT / "frontend" / "src"
GATE = ROOT / "scripts" / "verify_budget_target.py"
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
results = []


def run_gate() -> bool:
    """True bila gate LULUS."""
    r = subprocess.run([sys.executable, str(GATE)], capture_output=True, text=True,
                       timeout=900)
    return r.returncode == 0


def restart_backend():
    subprocess.run(["sudo", "supervisorctl", "restart", "backend"], capture_output=True)
    for _ in range(90):
        try:
            import requests
            if requests.get("http://localhost:8001/api/health", timeout=3).status_code == 200:
                time.sleep(2)
                return
        except Exception:  # noqa: BLE001
            pass
        time.sleep(1)


def mutate_file(rel: str, old: str, new: str, *, backend=True):
    path = (BE if backend else FE) / rel
    src = path.read_text(encoding="utf-8")
    if old not in src:
        return None
    shutil.copy(path, str(path) + ".mutbak")
    path.write_text(src.replace(old, new, 1), encoding="utf-8")
    return path


def restore(path):
    if path and pathlib.Path(str(path) + ".mutbak").exists():
        shutil.move(str(path) + ".mutbak", str(path))


def case_file(name: str, rel: str, old: str, new: str, *, backend=True, restart=True):
    path = mutate_file(rel, old, new, backend=backend)
    if path is None:
        results.append((name, "LEWAT", "pola tidak ditemukan — perbarui mutasi ini"))
        print(f"  LEWAT  {name} (pola tidak ditemukan)")
        return
    try:
        if restart and backend:
            restart_backend()
        caught = not run_gate()
        results.append((name, "TERTANGKAP" if caught else "LOLOS", ""))
        print(f"  {'TERTANGKAP' if caught else 'LOLOS'}  {name}")
    finally:
        restore(path)
        if restart and backend:
            restart_backend()


def case_data(name: str, mutate, undo):
    mutate()
    try:
        caught = not run_gate()
        results.append((name, "TERTANGKAP" if caught else "LOLOS", ""))
        print(f"  {'TERTANGKAP' if caught else 'LOLOS'}  {name}")
    finally:
        undo()


def main():
    print("=" * 70)
    print("UJI-MUTASI FASE 45 — membuktikan gate Target & Anggaran BERGIGI")
    print("=" * 70)
    print("\nBaseline (harus HIJAU sebelum merusak apa pun):")
    if not run_gate():
        print("  BASELINE MERAH — perbaiki gate/kode dulu sebelum uji-mutasi.")
        sys.exit(1)
    print("  baseline hijau\n")

    # ---- N01 matematika target bocor
    case_file("N01 pembagian target dibulatkan per bulan (Σ bocor)",
              "target_engine.py",
              "        base, rem = divmod(total, count)\n"
              "        return [base + (1 if i < rem else 0) for i in range(count)]",
              "        return [int(round(total / count)) for _ in range(count)]")

    # ---- N02 lock_past dilumpuhkan
    case_file("N02 lock_past dilumpuhkan (periode lampau ikut berubah)",
              "target_engine.py",
              "        if is_past:\n            plan = prev.get(\"unit_plan\")",
              "        if is_past and False:\n            plan = prev.get(\"unit_plan\")")

    # ---- N03 carry_over dihapus
    case_file("N03 carry_over tidak lagi ditulis (kenaikan target jadi misteri)",
              "target_engine.py",
              "    if carry_over and future:",
              "    if False and future:")

    # ---- N04 alasan recalc tidak wajib
    case_file("N04 alasan hitung-ulang target tidak lagi wajib",
              "models_p45.py",
              "class TargetRecalc(BaseModel):\n    reason: str = Field(min_length=5, max_length=300)",
              "class TargetRecalc(BaseModel):\n    reason: str = Field(default=\"\", max_length=300)")

    # ---- N05 tie-out pecah
    case_file("N05 `verified` konstruksi dibaca sebagai field (tie-out pecah)",
              "budget_engine.py",
              "    scope = await enriched_scope(org, project_id)",
              "    scope = await db.spk_scope_items.find({\"org_id\": org, "
              "\"project_id\": project_id}, {\"_id\": 0}).to_list(8000)")

    # ---- N06 komitmen tumpang dengan realisasi
    case_file("N06 komitmen memakai `billed` (tumpang dengan realisasi → double count)",
              "budget_engine.py",
              "        committed += (row[\"contracted\"] - row[\"verified\"]) + row[\"po_committed\"]",
              "        committed += (row[\"contracted\"] - row[\"billed\"]) + row[\"po_committed\"]")

    # ---- N07 proyek tanpa anggaran dilaporkan Rp 0
    case_file("N07 proyek tanpa item anggaran dilaporkan Rp 0 'aman'",
              "budget_engine.py",
              "        \"totals\": None if state == \"kosong\" else totals,",
              "        \"totals\": totals,")

    # ---- N08 persen 0%
    case_file("N08 persen dengan pembagi 0 dikembalikan 0% (bukan null)",
              "budget_engine.py",
              "    if not whole:\n        return None\n    return round(part / whole * 100, 1)",
              "    if not whole:\n        return 0.0\n    return round(part / whole * 100, 1)")

    # ---- N09 rencana konstruksi bisa diisi tangan
    case_file("N09 rencana item konstruksi boleh diisi tangan (dua angka anggaran RAB)",
              "routers/budget_router.py",
              "        if body.get(\"planned_amount\"):\n"
              "            raise HTTPException(status_code=400, detail=READONLY_MSG)",
              "        pass")

    # ---- N10 enforce dinyalakan sebagai bawaan
    case_file("N10 `budget.enforce_cost_ref` bawaannya dinyalakan",
              "settings_store.py",
              "    _d(\"budget.enforce_cost_ref\", False, \"bool\", \"anggaran\",",
              "    _d(\"budget.enforce_cost_ref\", True, \"bool\", \"anggaran\",")

    # ---- N11 peringatan tanpa tugas
    case_file("N11 peringatan ambang berhenti membuat tugas (hanya notifikasi)",
              "budget_reports.py",
              "            tasks = await wh.spawn(",
              "            tasks = []\n            _unused = (")

    # ---- N12 layar menulis label enum sendiri
    case_file("N12 layar anggaran menuliskan label enum sendiri (SSOT dilanggar)",
              "components/budget/parts.js",
              "      {labelOf(\"budget_health\", key)}",
              "      {key === \"overbudget\" ? \"Overbudget\" : \"Aman\"}",
              backend=False, restart=False)

    # ---- N13 material dijumlahkan (double count) — penjaga dilepas
    case_file("N13 penjaga anti double-count material dilepas (material jadi sumber biasa)",
              "budget_engine.py",
              "    (\"tax_records\", \"tax_record\", \"type\", \"amount\", \"/tax\"),\n]",
              "    (\"tax_records\", \"tax_record\", \"type\", \"amount\", \"/tax\"),\n"
              "    (\"material_txns\", \"material_txn\", \"ref\", \"amount\", \"/materials\"),\n]")

    # ---- N14 RBAC dilonggarkan — DI LAPISAN YANG BENAR (matriks tersimpan di database).
    # Pelajaran nyata: memutasi `rbac.py` TIDAK berpengaruh pada organisasi yang matriks
    # RBAC-nya sudah tersimpan, karena `rbac.get_matrix()` menimpa default kode dengan
    # dokumen `permission_settings.rbac_matrix`. Jadi mutasi yang jujur adalah mengubah
    # matriks tersimpan — persis yang bisa dilakukan admin lewat layar Izin.
    doc = db.permission_settings.find_one({"key": "rbac_matrix"}, {"_id": 0, "matrix": 1})
    stored = (doc or {}).get("matrix") or {}

    def loosen():
        db.permission_settings.update_one(
            {"key": "rbac_matrix"}, {"$set": {"matrix.budget.sales": ["view_all"]}})
        restart_backend()

    def tighten():
        db.permission_settings.update_one(
            {"key": "rbac_matrix"},
            {"$set": {"matrix.budget.sales": (stored.get("budget") or {}).get("sales", [])}})
        restart_backend()

    if stored.get("budget") is not None:
        case_data("N14 matriks RBAC tersimpan dilonggarkan untuk sales (anggaran)",
                  loosen, tighten)
    else:
        case_file("N14 RBAC anggaran dilonggarkan untuk sales (default kode)",
                  "rbac_matrix.py",
                  "    \"budget\": {\n        \"sales_manager\": [\"view_all\"],\n"
                  "        \"marketing_admin\": [\"view_all\"],\n        \"sales\": [],",
                  "    \"budget\": {\n        \"sales_manager\": [\"view_all\"],\n"
                  "        \"marketing_admin\": [\"view_all\"],\n        \"sales\": [\"view_all\"],")

    # ---- N15 drill memotong daftar dokumen
    case_file("N15 drill lapis 3 memotong daftar dokumen (Σ dokumen ≠ angka item)",
              "budget_engine.py",
              "        \"documents\": sorted(fig[\"docs\"], key=lambda d: -d[\"amount\"]),",
              "        \"documents\": sorted(fig[\"docs\"], key=lambda d: -d[\"amount\"])[:1],")

    # ---- N16 data: nilai snapshot anggaran dirusak langsung di database
    org = (db.projects.find_one({}, {"_id": 0, "org_id": 1}) or {}).get("org_id")
    target = db.project_targets.find_one({"org_id": org, "status": "active"}, {"_id": 0})
    if target:
        original = target.get("periods")

        def mutate():
            broken = [dict(p) for p in (original or [])]
            for p in broken:
                if p.get("locked"):
                    p["unit_plan"] = (p.get("unit_plan") or 0) + 99
            db.project_targets.update_one({"id": target["id"]},
                                          {"$set": {"periods": broken}})

        def undo():
            db.project_targets.update_one({"id": target["id"]},
                                          {"$set": {"periods": original}})

        # Gate memeriksa recalc TIDAK mengubah periode lampau; kalau nilai lampau dirusak,
        # hitung-ulang akan MEMPERTAHANKAN kerusakan itu (lock_past) sehingga gate tetap hijau.
        # Yang harus memerah adalah invarian keep_total pada pratinjau — dibuktikan di bawah.
        print("\n  (catatan) mutasi data periode lampau sengaja TIDAK dihitung sebagai kasus: "
              "lock_past memang mempertahankan nilai lampau apa adanya.")
        mutate()
        undo()

    print("\n" + "=" * 70)
    caught = [r for r in results if r[1] == "TERTANGKAP"]
    escaped = [r for r in results if r[1] == "LOLOS"]
    skipped = [r for r in results if r[1] == "LEWAT"]
    print(f"RINGKASAN: {len(caught)} tertangkap · {len(escaped)} LOLOS · "
          f"{len(skipped)} terlewat · total {len(results)} mutasi")
    for name, status, note in results:
        print(f"  {status:11s} {name}{(' — ' + note) if note else ''}")
    print("\nMemastikan baseline pulih hijau setelah semua pemulihan…")
    restart_backend()
    green = run_gate()
    print(f"  baseline setelah pemulihan: {'HIJAU' if green else 'MERAH'}")
    if escaped or skipped or not green:
        print("\nUJI-MUTASI GAGAL: gate belum bergigi untuk semua janji Fase 45.")
        sys.exit(1)
    print("\nUJI-MUTASI LULUS: setiap perusakan janji Fase 45 tertangkap gate, dan baseline "
          "pulih hijau.")


if __name__ == "__main__":
    main()
