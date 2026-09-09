#!/usr/bin/env python3
"""mutasi_44.py — uji-mutasi gate Analitik & BI (`verify_analytics.py`).

Gate yang tidak bisa gagal tidak menjaga apa pun. Skrip ini merusak kode dengan sengaja (satu
cacat per kali), memastikan gate MEMERAH pada temuan yang tepat, lalu memulihkan dan
memastikan gate hijau kembali. Semua mutasi = cacat REALISTIS yang mudah lolos review:

  N1  kontrak kejujuran dilonggarkan: metrik tanpa input boleh mengirim angka  -> 0 palsu
  N2  metrik marketing menghitung ulang biaya iklan dengan rumusnya sendiri    -> dua kebenaran
  N3  kas masuk memakai deposit_amount alih-alih amount                        -> tie-out pecah
  N4  lead tanpa riwayat tahap dianggap lengkap (cakupan disembunyikan)        -> angka terlihat final
  N5  demografi kosong digambar sebagai 0                                      -> kesimpulan dari data yang tidak ada
  N6  drill LED-14 menunjuk daftar TANPA filter SLA                            -> angka ≠ daftar
  N7  snapshot menyimpan nilai lain dari hitungan langsung                     -> snapshot jadi kebenaran ke-2
  N8  index unik snapshot dihapus dari database                                -> titik tren ganda
  N9  row-scope dicabut: sales melihat angka seluruh organisasi                -> data orang lain bocor
  N10 rebuild snapshot boleh dipanggil peran tanpa izin manage                 -> beban & data
  N11 layar menjatuhkan nilai metrik ke 0 (`?? 0`)                             -> \"0\" palsu di layar
  N12 kartu metrik berhenti menampilkan rumus                                  -> angka tak bisa didebat
  N13 menu Analitik & BI ditutup lagi jadi \"Segera Hadir\"                      -> fitur hilang
  N14 metrik dashboard menunjuk kode yang tidak ada di kamus                   -> kartu kosong senyap
  N15 ekspor CSV berhenti menyebut kelengkapan data                            -> ekspor lebih \"rapi\" dari kenyataan

Pakai: `python3 scripts/mutasi_44.py` (atau `... N3 N9`). Exit != 0 bila ada yang tidak
tertangkap. Aman dijalankan berbarengan? TIDAK — ada kunci PID seperti `mutasi_43.py`.
"""
import os
import pathlib
import subprocess
import sys
import time
import urllib.request

from dotenv import load_dotenv
from pymongo import MongoClient

ROOT = pathlib.Path("/app")
load_dotenv(ROOT / "backend" / ".env")
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
results = []
LOCK = pathlib.Path("/tmp/mutasi_44.lock")

BASEM = "backend/metrics/base.py"
SALES = "backend/metrics/sales.py"
LEADS = "backend/metrics/leads.py"
MKT = "backend/metrics/marketing.py"
AENG = "backend/analytics_engine.py"
AROUTER = "backend/routers/analytics_router.py"
CARD = "frontend/src/components/bi/MetricCard.js"
VALUE = "frontend/src/components/bi/MetricValue.js"
NAV = "frontend/src/config/navigationConfig.js"
SNAP_KEY = [("org_id", 1), ("code", 1), ("period_key", 1)]


def wait_backend():
    for _ in range(120):
        try:
            with urllib.request.urlopen("http://localhost:8001/api/health", timeout=2) as r:
                if r.status == 200:
                    return
        except Exception:  # noqa: BLE001
            time.sleep(0.5)


def run(restart: bool = False) -> tuple:
    if restart:
        subprocess.run(["sudo", "supervisorctl", "restart", "backend"],
                       capture_output=True, text=True, timeout=180)
    else:
        time.sleep(2)
    wait_backend()
    time.sleep(1)
    p = subprocess.run([sys.executable, str(ROOT / "scripts" / "verify_analytics.py")],
                       capture_output=True, text=True, timeout=900)
    return p.returncode, (p.stdout + p.stderr)


def selected(label: str) -> bool:
    only = [a for a in sys.argv[1:] if not a.startswith("-")]
    return not only or any(label.split()[0] == o for o in only)


def record(label: str, code: int, out: str, expect: str, restart: bool):
    if "Connection refused" in out or "Max retries exceeded" in out:
        results.append((label, "TIDAK BISA DIUJI",
                        "aplikasi mati karena mutasi ini — gate tak bisa dijalankan"))
    else:
        detected = expect is None or expect in out
        ok = detected and code != 0
        results.append((label, "PASS" if ok else "FAIL",
                        "gate memerah pada temuan yang tepat" if ok else
                        f"cacat TIDAK TERTANGKAP (exit={code}, pola '{expect}' "
                        f"{'ada' if detected else 'TIDAK ada'}) :: ...{out.strip()[-300:]}"))
    code2, out2 = run(restart)
    results.append((f"{label} (pulih)", "PASS" if code2 == 0 else "FAIL",
                    "hijau kembali" if code2 == 0 else
                    f"MASIH MERAH setelah dipulihkan :: ...{out2.strip()[-240:]}"))


def mutate(label: str, edits: list, expect: str = None):
    if not selected(label):
        return
    restart = any(p.startswith("backend/") for p, _, _ in edits)
    originals = {}
    for path, old, new in edits:
        f = ROOT / path
        src = f.read_text()
        if old not in src:
            for p, s in originals.items():
                (ROOT / p).write_text(s)
            results.append((label, "TIDAK BISA DIUJI", f"pola tidak ditemukan di {path}"))
            return
        originals.setdefault(path, src)
        f.write_text(src.replace(old, new, 1))
    try:
        code, out = run(restart)
    finally:
        for p, s in originals.items():
            (ROOT / p).write_text(s)
    record(label, code, out, expect, restart)


def mutate_state(label: str, break_fn, restore_fn, expect: str = None):
    if not selected(label):
        return
    state = break_fn()
    try:
        code, out = run(False)
    finally:
        restore_fn(state)
    record(label, code, out, expect, False)


def drop_snapshot_index():
    try:
        db.metric_snapshots.drop_index("uq_metric_snapshot")
    except Exception:  # noqa: BLE001
        pass
    return True


def restore_snapshot_index(_s):
    db.metric_snapshots.create_index(SNAP_KEY, unique=True, name="uq_metric_snapshot")


def poison_snapshot():
    row = db.metric_snapshots.find_one({"value": {"$ne": None}}, {"_id": 0})
    if not row:
        return None
    db.metric_snapshots.update_one({"id": row["id"]},
                                   {"$set": {"value": int(row["value"] or 0) + 999}})
    return row


def restore_snapshot(row):
    if row:
        db.metric_snapshots.update_one({"id": row["id"]}, {"$set": {"value": row.get("value")}})


def guard_single_run():
    if LOCK.exists():
        pid = LOCK.read_text().strip()
        if pid.isdigit() and pathlib.Path(f"/proc/{pid}").exists():
            print(f"BATAL: suite mutasi lain masih berjalan (PID {pid}).")
            sys.exit(2)
        LOCK.unlink(missing_ok=True)
    LOCK.write_text(str(os.getpid()))


def guard_baseline():
    code, out = run(False)
    if code != 0:
        print("BATAL: baseline verify_analytics.py SUDAH MERAH sebelum mutasi.\n"
              f"{out.strip()[-800:]}")
        LOCK.unlink(missing_ok=True)
        sys.exit(2)


def run_mutations():
    # N1 & N5 sengaja merusak DUA lapis sekaligus. Kejujuran angka dijaga berlapis: (a) tiap
    # metrik mengembalikan None saat inputnya tidak ada, dan (b) `base.result` MEMAKSA None bila
    # ada `missing` tanpa `coverage`. Merusak satu lapis saja tidak menghasilkan gejala di API
    # (lapis lain menahannya) — jadi mutasi yang hanya membuka satu lapis akan tampak "tidak
    # tertangkap" padahal aplikasinya masih jujur. Yang diuji di sini: gate menangkap saat
    # KEDUA lapis dibuka, yaitu satu-satunya keadaan yang benar-benar berbahaya.
    GUARD = ("    if missing and coverage is None:\n"
             "        # Tidak ada input -> tidak ada angka. Ini pemaksaan, bukan saran.\n"
             "        value = None")
    GUARD_OFF = "    if missing and coverage is None and False:\n        value = None"
    mutate("N1 kontrak kejujuran dilonggarkan + LED-12 mengirim 0 untuk data yang tidak ada",
           [(BASEM, GUARD, GUARD_OFF),
            (LEADS, '        return result("LED-12", None, '
                    'label=f"Demografi lead ({dimension})", unit="count",',
             '        return result("LED-12", 0, '
             'label=f"Demografi lead ({dimension})", unit="count",')],
           "FAIL  TIDAK ADA metrik yang mengirim angka tanpa input")

    mutate("N2 metrik marketing menghitung ulang biaya iklan dengan rumus sendiri",
           [(MKT, '    return result("MKT-01", totals["spend"], label="Biaya iklan", unit="idr",',
             '    return result("MKT-01", totals["spend"] + 1, label="Biaya iklan", unit="idr",')],
           "FAIL  MKT-01 biaya iklan = total laporan kampanye")

    mutate("N3 kas masuk memakai field yang salah (deposit, bukan penerimaan)",
           [(SALES, '    total = sum(int(r.get("amount") or 0) for r in rows)\n    per_method = {}',
             '    total = sum(int(r.get("deposit_amount") or 0) for r in rows)\n'
             '    per_method = {}')],
           "FAIL  SLS-05 kas masuk = Σ kuitansi")

    mutate("N4 lead tanpa riwayat tahap dianggap lengkap (cakupan disembunyikan)",
           [(LEADS, '                  coverage={"rows": len(rows) - len(tanpa_riwayat), '
                    '"total": len(rows)}\n                  if tanpa_riwayat else None,',
             '                  coverage=None,')],
           "FAIL  LED-02 mengaku dihitung dari sebagian data")

    mutate("N5 pendapatan add-on tanpa rincian harga dikirim sebagai 0 (dua lapis dibuka)",
           [(BASEM, GUARD, GUARD_OFF),
            (SALES, '        return result("SLS-09", None, label="Pendapatan add-on", unit="idr",',
             '        return result("SLS-09", 0, label="Pendapatan add-on", unit="idr",')],
           "FAIL  TIDAK ADA metrik yang mengirim angka tanpa input")

    mutate("N6 drill LED-14 menunjuk daftar TANPA filter SLA (angka ≠ daftar)",
           [(LEADS, '                  inputs={"diperiksa_pada": now}, drill="/leads?sla=over")',
             '                  inputs={"diperiksa_pada": now}, drill="/leads")')],
           "FAIL  LED-14 menunjuk daftar lead lewat SLA")

    mutate("N7 rebuild berhenti MEMPERBAIKI snapshot lama (snapshot jadi kebenaran ke-2)",
           [(AENG, '            {"$set": doc, "$setOnInsert": {"id": new_id()}}, upsert=True)',
             '            {"$setOnInsert": {**doc, "id": new_id()}}, upsert=True)')],
           "FAIL  nilai snapshot yang dirusak DIPERBAIKI rebuild")

    mutate_state("N8 index unik snapshot dihapus dari database",
                 drop_snapshot_index, restore_snapshot_index,
                 "FAIL  index unik snapshot ada")

    mutate("N9 row-scope dicabut (sales melihat angka seluruh organisasi)",
           [(AROUTER, '    return user.get("email") if user.get("role") in SALES_SCOPED_ROLES '
                      'else None',
             '    return None')],
           "FAIL  data sales DIBATASI ke dirinya sendiri")

    mutate("N10 rebuild snapshot terbuka untuk peran tanpa izin manage",
           [(AROUTER, 'async def rebuild_snapshots(date: str = None,\n'
                      '                            user: dict = Depends('
                      'require_permission("analytics", "manage"))):',
             'async def rebuild_snapshots(date: str = None,\n'
             '                            user: dict = Depends('
             'require_permission("analytics", "view"))):')],
           "FAIL  sales DITOLAK menghitung ulang snapshot")

    mutate("N11 layar menjatuhkan nilai metrik ke 0",
           [(VALUE, "  const text = formatMetric(metric?.value, metric?.unit);",
             "  const text = formatMetric(metric?.value ?? 0, metric?.unit);")],
           "FAIL  tidak ada nilai metrik yang dijatuhkan ke 0 di layar")

    mutate("N12 kartu metrik berhenti menampilkan rumus (angka tak bisa didebat)",
           [(CARD, "      {metric.formula ? (", "      {false ? (")],
           "FAIL  kartu metrik benar-benar merender rumus metrik")

    mutate("N13 menu Analitik & BI ditutup lagi jadi 'Segera Hadir'",
           [(NAV, '{ id: "bi", label: "Analitik & BI", icon: BarChart3, path: "/bi", roles: ALL },',
             '{ id: "bi", label: "Analitik & BI", icon: BarChart3, comingSoon: true,\n'
             '        note: "Fase 45", roles: ALL },')],
           "FAIL  menu Analitik & BI TIDAK lagi 'Segera Hadir'")

    mutate("N14 dashboard menunjuk kode metrik yang tidak ada di kamus",
           [(AENG, '    "tim": ["USR-01", "USR-02", "USR-03", "USR-04", "USR-05", "USR-06", '
                   '"USR-07"],',
             '    "tim": ["USR-01", "USR-02", "USR-03", "USR-04", "USR-05", "USR-06", '
             '"USR-07", "USR-99"],')],
           "FAIL  dashboard tidak memakai kode metrik yang tidak ada di kamus")

    mutate("N15 ekspor CSV berhenti menyebut kelengkapan data",
           [(AROUTER, '    writer.writerow(["kelengkapan", res["state"], '
                      '"; ".join(res.get("missing") or [])])',
             '    writer.writerow(["catatan", "-"])')],
           "FAIL  ekspor CSV menyebut kelengkapan datanya")

    print("\n=============== HASIL UJI-MUTASI FASE 44 (Analitik & BI) ===============")
    bad = [r for r in results if r[1] != "PASS"]
    for label, status, detail in results:
        print(f"  {status:15} {label}\n{' ' * 19}{detail}")
    print("=" * 72)
    print(f"{len(results) - len(bad)}/{len(results)} pemeriksaan PASS "
          f"({len([r for r in results if '(pulih)' not in r[0]])} mutasi)")
    if bad:
        print("ADA MUTASI YANG TIDAK TERTANGKAP / TIDAK PULIH — gate belum bergigi.")
        sys.exit(1)
    print("SEMUA MUTASI TERTANGKAP dan baseline pulih hijau.")


def main():
    guard_single_run()
    try:
        guard_baseline()
        run_mutations()
    finally:
        LOCK.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
