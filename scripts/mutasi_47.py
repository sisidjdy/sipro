#!/usr/bin/env python3
"""mutasi_47.py — UJI-MUTASI gate Fase 47 (uang masuk, bukti pelanggan, harga & upah).

Kenapa uji-mutasi ada: gate yang HIJAU belum tentu **bergigi**. Gate bisa hijau karena
pemeriksaannya longgar (mis. hanya memastikan sebuah kunci ada di jawaban API), dan gate
seperti itu memberi rasa aman yang salah — justru pada bagian yang paling mahal bila salah:
uang. Cara membuktikannya hanya satu: SENGAJA MERUSAK kode/data, memastikan gate MEMERAH,
lalu memulihkan dan memastikan hijau lagi.

Setiap mutasi menyerang satu janji Fase 47 (nama gate yang seharusnya menangkapnya di
dalam tanda kurung):

  REKONSILIASI BANK (verify_bank_recon.py)
    N01  pratinjau impor (dry-run) diam-diam MENULIS ke database
    N02  impor tidak idempoten — berkas yang sama diimpor ulang melahirkan mutasi kembar
    N03  mutasi tanpa kolom saldo dicatat bersaldo 0 (kebohongan, bukan "belum ada data")
    N04  selisih yang belum bisa dijelaskan disembunyikan dari ringkasan rekonsiliasi
    N05  pembatalan pencocokan tidak membatalkan kuitansinya (tagihan tetap "lunas")
    N06  pemisahan tugas dilonggarkan: finance biasa boleh MEMBALIK pembukuan

  BUKTI TRANSFER PORTAL (verify_portal_proof.py)
    N07  klaim pelanggan langsung diverifikasi sistem — tagihan berkurang tanpa finance
    N08  sidik jari berkas (sha256) diabaikan — satu bukti bisa dikirim berkali-kali
    N09  penolakan bukti tidak lagi wajib beralasan — DUA lapis (kontrak + service)
    N10  jejak audit palsu: `created_by` diisi email pelanggan yang bukan pengguna sistem

  PENAWARAN & UPAH HARIAN (verify_quotation_labor.py)
    N11  termin penawaran dihitung dari angka lain (rumus kedua di luar mesin AR)
    N12  simulasi KPR tanpa tenor/bunga menjawab Rp 0, bukan "belum ada data"
    N13  diskon di atas kewenangan langsung menjadi draf siap konversi (tanpa persetujuan)
    N14  revisi penawaran tidak menandai versi lama sebagai "diganti" (dua harga hidup)
    N15  setengah hari dibayar penuh (rumus upah tidak lagi bisa dihitung ulang tangan)
    N16  index UNIK absensi dihapus — absensi kembar bisa masuk lewat jalur data
    N17  rekap upah tidak tie-out dengan absensi (total ditambah angka karangan)
    N18  upah bisa dibayar sebelum disetujui (pemisahan tugas jadi hiasan)
    N19  yang MENGAJUKAN rekap upah boleh menyetujui pembayarannya sendiri

Cara pakai: `python3 scripts/mutasi_47.py` (butuh backend hidup di :8001).
Exit != 0 bila ADA mutasi yang LOLOS (gate tetap hijau padahal kode dirusak) atau LEWAT
(pola mutasi tidak ditemukan lagi karena kode berubah — mutasinya wajib diperbarui).
"""
import os
import pathlib
import shutil
import subprocess
import sys
import time

import requests
from dotenv import load_dotenv
from pymongo import MongoClient

ROOT = pathlib.Path(__file__).resolve().parent.parent
load_dotenv(ROOT / "backend" / ".env")
BE = ROOT / "backend"
FE = ROOT / "frontend" / "src"
GATES = ROOT / "scripts"
BANK = "verify_bank_recon.py"
PORTAL = "verify_portal_proof.py"
QL = "verify_quotation_labor.py"
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
results = []
# `--check` hanya MEMASTIKAN pola mutasi masih ada di kode (cepat, tanpa menjalankan gate).
# Dipakai setelah refactor: mutasi yang polanya sudah hilang = uji-mutasi yang bohong hijau.
CHECK_ONLY = "--check" in sys.argv


def run_gate(gate: str) -> bool:
    """True bila gate LULUS. Log lengkap disimpan supaya sebab merahnya bisa dibaca."""
    r = subprocess.run([sys.executable, str(GATES / gate)], capture_output=True, text=True,
                       timeout=1800)
    (pathlib.Path("/tmp") / f"mut47_{gate}.log").write_text(r.stdout + r.stderr,
                                                            encoding="utf-8")
    return r.returncode == 0


def restart_backend():
    subprocess.run(["sudo", "supervisorctl", "restart", "backend"], capture_output=True)
    for _ in range(120):
        try:
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


def _record(name: str, caught: bool):
    results.append((name, "TERTANGKAP" if caught else "LOLOS"))
    print(f"  {'TERTANGKAP' if caught else 'LOLOS'}  {name}", flush=True)


def _pattern_exists(rel: str, old: str, *, backend=True) -> bool:
    return old in ((BE if backend else FE) / rel).read_text(encoding="utf-8")


def case_file(name: str, gate: str, rel: str, old: str, new: str, *, backend=True,
              restart=True):
    """Satu mutasi pada SATU berkas."""
    if CHECK_ONLY:
        ok = _pattern_exists(rel, old, backend=backend)
        results.append((name, "ADA" if ok else "LEWAT"))
        print(f"  {'ADA  ' if ok else 'LEWAT'}  {name}", flush=True)
        return
    path = mutate_file(rel, old, new, backend=backend)
    if path is None:
        results.append((name, "LEWAT"))
        print(f"  LEWAT  {name} (pola tidak ditemukan — perbarui mutasi ini)", flush=True)
        return
    try:
        if restart and backend:
            restart_backend()
        _record(name, not run_gate(gate))
    finally:
        restore(path)
        if restart and backend:
            restart_backend()


def case_files(name: str, gate: str, edits: list, *, backend=True, restart=True):
    """Satu mutasi yang mematikan BEBERAPA lapis sekaligus.

    Perlu karena beberapa aturan dijaga berlapis (model + service). Mematikan satu lapis
    saja tidak mengubah perilaku, jadi mutasinya "lolos" secara palsu padahal yang diuji
    adalah aturannya, bukan salah satu lapisnya.
    """
    if CHECK_ONLY:
        ok = all(_pattern_exists(rel, old, backend=backend) for rel, old, _ in edits)
        results.append((name, "ADA" if ok else "LEWAT"))
        print(f"  {'ADA  ' if ok else 'LEWAT'}  {name}", flush=True)
        return
    paths = [mutate_file(rel, old, new, backend=backend) for rel, old, new in edits]
    if any(p is None for p in paths):
        for p in paths:
            restore(p)
        results.append((name, "LEWAT"))
        print(f"  LEWAT  {name} (pola tidak ditemukan — perbarui mutasi ini)", flush=True)
        return
    try:
        if restart and backend:
            restart_backend()
        _record(name, not run_gate(gate))
    finally:
        for p in paths:
            restore(p)
        if restart and backend:
            restart_backend()


def case_data(name: str, gate: str, mutate, undo):
    """Mutasi pada DATA/DATABASE (mis. index unik dihapus) — tanpa menyentuh kode."""
    if CHECK_ONLY:
        ok = IDX in db.labor_attendance.index_information()
        results.append((name, "ADA" if ok else "LEWAT"))
        print(f"  {'ADA  ' if ok else 'LEWAT'}  {name}", flush=True)
        return
    if mutate() is False:
        results.append((name, "LEWAT"))
        print(f"  LEWAT  {name} (sasaran mutasi tidak ada — perbarui mutasi ini)", flush=True)
        return
    try:
        _record(name, not run_gate(gate))
    finally:
        undo()


# ---------------------------------------------------------------- N16: index unik absensi
IDX = "uq_labor_attendance"


def drop_attendance_index():
    if IDX not in db.labor_attendance.index_information():
        return False
    db.labor_attendance.drop_index(IDX)
    return True


def restore_attendance_index():
    # Sisa absensi kembar (buatan gate saat index mati) harus dibuang lebih dulu, kalau
    # tidak index unik-nya menolak dibuat ulang dan lingkungan tertinggal rusak.
    seen, dupes = set(), []
    for row in db.labor_attendance.find({}, {"_id": 1, "org_id": 1, "project_id": 1,
                                             "work_date": 1, "worker_id": 1}):
        key = (row.get("org_id"), row.get("project_id"), row.get("work_date"),
               row.get("worker_id"))
        if key in seen:
            dupes.append(row["_id"])
        else:
            seen.add(key)
    if dupes:
        db.labor_attendance.delete_many({"_id": {"$in": dupes}})
        print(f"         (bersih-bersih: {len(dupes)} absensi kembar dibuang)", flush=True)
    if IDX not in db.labor_attendance.index_information():
        db.labor_attendance.create_index(
            [("org_id", 1), ("project_id", 1), ("work_date", 1), ("worker_id", 1)],
            unique=True, name=IDX)


def main():
    print("=" * 78)
    print("UJI-MUTASI FASE 47 — membuktikan gate uang/bukti/harga/upah BERGIGI")
    print("=" * 78)
    print("\nBaseline (tiga gate harus HIJAU sebelum merusak apa pun):", flush=True)
    for g in (BANK, PORTAL, QL):
        if CHECK_ONLY:
            print(f"  (dilewati --check)  {g}", flush=True)
            continue
        ok = run_gate(g)
        print(f"  {'hijau' if ok else 'MERAH'}  {g}", flush=True)
        if not ok:
            print(f"  BASELINE MERAH — perbaiki dulu (log: /tmp/mut47_{g}.log)")
            return 1
    print("", flush=True)

    # ================================================== 47A rekonsiliasi bank
    case_file("N01 pratinjau impor (dry-run) diam-diam MENULIS ke database", BANK,
              "bank_import.py",
              '    """Impor satu berkas mutasi. `dry_run=True` HANYA melaporkan, tanpa '
              'menulis apa pun."""\n    acc = await account_or_error(org, account_id)',
              '    """Impor satu berkas mutasi. `dry_run=True` HANYA melaporkan, tanpa '
              'menulis apa pun."""\n    dry_run = False\n'
              '    acc = await account_or_error(org, account_id)')

    case_file("N02 impor tidak idempoten (berkas sama melahirkan mutasi kembar)", BANK,
              "bank_import.py",
              '    return hashlib.sha1(key.encode("utf-8")).hexdigest()',
              '    return hashlib.sha1((key + new_id()).encode("utf-8")).hexdigest()')

    case_file("N03 mutasi tanpa kolom saldo dicatat bersaldo 0 (bukan 'belum ada data')",
              BANK, "bank_import.py",
              '                     "balance": (int(balance) if balance not in (None, 0) '
              'else None)})',
              '                     "balance": int(balance or 0)})')

    case_file("N04 selisih yang belum bisa dijelaskan disembunyikan dari ringkasan", BANK,
              "bank_match.py",
              "        unexplained = statement_balance - (book + unmatched_in - unmatched_out)"
              "\n        if unexplained:",
              "        unexplained = statement_balance - (book + unmatched_in - unmatched_out)"
              "\n        if False:")

    case_file("N05 pembatalan pencocokan tidak membatalkan kuitansinya", BANK,
              "bank_match.py",
              '        rid = (m.get("result") or {}).get("receipt_id")\n        if rid:',
              '        rid = (m.get("result") or {}).get("receipt_id")\n        if False:')

    case_file("N06 finance biasa boleh MEMBALIK pembukuan (pemisahan tugas dilonggarkan)",
              BANK, "routers/bank_router.py",
              'async def do_unmatch(txn_id: str, payload: BankUnmatchIn,\n'
              '                     user: dict = Depends(require_permission("bank", '
              '"approve"))):',
              'async def do_unmatch(txn_id: str, payload: BankUnmatchIn,\n'
              '                     user: dict = Depends(require_permission("bank", '
              '"update"))):')

    # ================================================== 47B bukti transfer portal
    case_file("N07 klaim pelanggan langsung diverifikasi sistem (tagihan berkurang sendiri)",
              PORTAL, "routers/portal_router.py",
              '    except ValueError as e:\n        raise HTTPException(status_code=400, '
              'detail=str(e))\n    return {"data": serialize_doc(doc),\n'
              '            "message": ("Bukti transfer terkirim.',
              '    except ValueError as e:\n        raise HTTPException(status_code=400, '
              'detail=str(e))\n    doc = (await intake.verify(org, doc["id"], '
              '"mutasi47"))["intake"]\n    return {"data": serialize_doc(doc),\n'
              '            "message": ("Bukti transfer terkirim.')

    case_file("N08 sidik jari berkas (sha256) diabaikan — bukti kembar lolos", PORTAL,
              "payment_intake.py",
              "    shas = [f.get(\"sha256\") for f in files if f.get(\"sha256\")]\n    if shas:",
              "    shas = [f.get(\"sha256\") for f in files if f.get(\"sha256\")]\n    if False:")

    # Aturan panjang alasan dijaga DUA lapis (kontrak permintaan `models_p47` + service
    # `payment_intake`). Mematikan satu lapis saja tidak mengubah perilaku — mutan
    # ekuivalen yang membuat gate tampak longgar padahal tidak. Karena itu keduanya dimatikan.
    case_files("N09 penolakan bukti tidak lagi wajib beralasan (dua lapis dimatikan)", PORTAL,
               [("models_p47.py", "MIN_REJECT_REASON = 10", "MIN_REJECT_REASON = 0"),
                ("payment_intake.py", "MIN_REJECT_REASON = 10", "MIN_REJECT_REASON = 0")])

    case_file("N10 jejak audit palsu: created_by diisi email pelanggan (bukan pengguna)",
              PORTAL, "payment_intake.py",
              '        "created_by": "portal", "created_at": ts, "updated_at": ts,',
              '        "created_by": (customer.get("email") or "portal"), '
              '"created_at": ts, "updated_at": ts,')

    # ================================================== 47C penawaran
    case_file("N11 termin penawaran dihitung dari angka lain (rumus kedua)", QL,
              "quotation_engine.py",
              "    terms = fin.compute_scheme_items(scheme, net, today_iso_date())",
              "    terms = fin.compute_scheme_items(scheme, net - 1_000_000, "
              "today_iso_date())")

    case_file("N12 simulasi KPR tanpa tenor/bunga menjawab Rp 0 (bukan 'belum ada data')",
              QL, "quotation_engine.py",
              '    if missing:\n        return {"state": "missing_data"',
              '    if False:\n        return {"state": "missing_data"')

    case_file("N13 diskon di atas kewenangan langsung jadi draf (tanpa persetujuan)", QL,
              "quotation_engine.py",
              '    state = "awaiting_approval" if calc["needs_discount_approval"] '
              'else "draft"',
              '    state = "draft"')

    case_file("N14 revisi tidak menandai versi lama sebagai 'diganti' (dua harga hidup)",
              QL, "quotation_engine.py",
              '            "state": "superseded", "state_label": _label("superseded"),',
              '            "state_label": _label("superseded"),')

    # ================================================== 47D absensi & upah
    case_file("N15 setengah hari dibayar penuh (upah tak bisa dihitung ulang tangan)", QL,
              "labor_engine.py",
              '    factor = ATTENDANCE_DAY_FACTOR.get(entry.get("status"), 0.0)',
              '    factor = 1.0 if ATTENDANCE_DAY_FACTOR.get(entry.get("status"), 0.0) '
              'else 0.0')

    case_data("N16 index UNIK absensi dihapus — absensi kembar bisa masuk lewat jalur data",
              QL, drop_attendance_index, restore_attendance_index)

    case_file("N17 rekap upah tidak tie-out dengan absensi (total ditambah karangan)", QL,
              "labor_engine.py",
              '        "total": sum(x["total"] for x in lines),',
              '        "total": sum(x["total"] for x in lines) + 50_000,')

    case_file("N18 upah bisa dibayar sebelum disetujui", QL, "labor_engine.py",
              '    if p["state"] != "approved":', '    if False:')

    case_file("N19 pengaju rekap upah boleh menyetujui pembayarannya sendiri", QL,
              "routers/labor_router.py",
              'async def decide_payroll(payroll_id: str, payload: PayrollDecisionIn,\n'
              '                         user: dict = Depends(require_permission("labor", '
              '"approve"))):',
              'async def decide_payroll(payroll_id: str, payload: PayrollDecisionIn,\n'
              '                         user: dict = Depends(require_permission("labor", '
              '"update"))):')

    print("\n" + "=" * 78)
    lolos = [n for n, s in results if s == "LOLOS"]
    lewat = [n for n, s in results if s == "LEWAT"]
    caught = [n for n, s in results if s in ("TERTANGKAP", "ADA")]
    if CHECK_ONLY:
        print(f"POLA MUTASI ADA: {len(caught)} · HILANG: {len(lewat)}")
        for n in lewat:
            print(f"  LEWAT  {n}")
        return 0 if not lewat else 1
    print(f"TERTANGKAP: {len(caught)} · LOLOS: {len(lolos)} · LEWAT: {len(lewat)}")
    for n in lolos:
        print(f"  LOLOS  {n}")
    for n in lewat:
        print(f"  LEWAT  {n}")
    print("\nBaseline setelah semua mutasi dipulihkan:", flush=True)
    ok = True
    for g in (BANK, PORTAL, QL):
        good = run_gate(g)
        ok = ok and good
        print(f"  {'hijau kembali' if good else 'MASIH MERAH — periksa pemulihan!'}  {g}")
    return 0 if (not lolos and not lewat and ok) else 1


if __name__ == "__main__":
    sys.exit(main())
