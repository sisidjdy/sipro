#!/usr/bin/env python3
"""mutasi_46.py — UJI-MUTASI gate Fase 46 (Konsolidasi Proyek & Konstruksi).

Kenapa uji-mutasi ada: gate yang HIJAU belum tentu **bergigi**. Gate bisa hijau karena
pemeriksaannya longgar (mis. hanya memastikan kata tertentu ada di berkas), dan gate seperti
itu memberi rasa aman yang salah. Cara membuktikannya hanya satu: SENGAJA MERUSAK kode/data,
lalu memastikan gate MEMERAH — dan setelah dipulihkan, hijau lagi.

Setiap mutasi menyerang satu janji Fase 46:

  N01  unit tanpa jadwal dilaporkan 0% (bukan "belum ada data")
  N02  papan menyembunyikan unit yang belum dijadwalkan (kembali ke papan per-jadwal)
  N03  progres papan dihitung ulang sendiri (dua kebenaran dengan build_engine)
  N04  DP tanpa rencana bayar dianggap "belum bayar" (bukan belum ada data)
  N05  kesiapan di tabel memakai rumus berbeda dari evaluator
  N06  peringatan boleh diabaikan tanpa pengakuan (ack tidak lagi wajib)
  N07  alasan mulai bangun tidak lagi wajib panjang minimal (DUA lapis dimatikan)
  N08  pemisahan tugas dilonggarkan (pelaksana lapangan boleh menekan mulai bangun)
  N09  mode TEGAS tidak lagi memblokir (kebijakan jadi hiasan)
  N10  setting `build.require_dp_before_start` bawaannya dinyalakan diam-diam
  N11  izin `approved` yang lewat tanggal dianggap tetap sehat
  N12  izin wajib yang hilang diam-diam dianggap terpenuhi
  N13  rantai izin berhenti di unit (warisan blok/cluster/proyek hilang)
  N14  peringatan izin hanya mengirim notifikasi, tanpa tugas Work Hub
  N15  fitur konstruksi lama hilang dari hub (panel dihapus dari JSX tab)
  N16  rata-rata progres dibagi SEMUA unit (termasuk yang belum dijadwalkan)

Dua temuan NYATA dari uji-mutasi ini (diperbaiki, bukan disembunyikan):

  * Gate dulu SEKALI PAKAI: bahan uji gerbang "mulai bangun" dipungut dari unit seed,
    sehingga begitu satu mutasi berhasil menekan start, unit itu berubah "berjalan" dan
    gate berikutnya merah karena datanya habis — bukan karena kodenya salah. Ini membuat
    N07..N16 tampak "tertangkap" secara palsu. Sekarang gate & POC MEMBUAT SENDIRI unit
    sementara (`GATE46-01`, `POC46-01/02`) lalu membuangnya.
  * N15 benar-benar LOLOS: gate memeriksa `"ForemanBoard" in isi_berkas`, dan baris
    `import ForemanBoard ...` membuat pemeriksaan itu tetap hijau walau komponennya
    dihapus dari JSX. Gate sekarang menuntut `<ForemanBoard` (benar-benar dirender).

Jalankan: `python3 scripts/mutasi_46.py`. Exit != 0 bila ADA mutasi yang tidak tertangkap.
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
GATE = ROOT / "scripts" / "verify_build_hub.py"
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
results = []


def run_gate() -> bool:
    """True bila gate LULUS."""
    r = subprocess.run([sys.executable, str(GATE)], capture_output=True, text=True,
                       timeout=1200)
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
        results.append((name, "LEWAT"))
        print(f"  LEWAT  {name} (pola tidak ditemukan — perbarui mutasi ini)")
        return
    try:
        if restart and backend:
            restart_backend()
        caught = not run_gate()
        results.append((name, "TERTANGKAP" if caught else "LOLOS"))
        print(f"  {'TERTANGKAP' if caught else 'LOLOS'}  {name}")
    finally:
        restore(path)
        if restart and backend:
            restart_backend()


def case_files(name: str, edits: list, *, backend=True, restart=True):
    """Satu mutasi yang merusak BEBERAPA berkas sekaligus.

    Kenapa perlu: beberapa aturan dijaga BERLAPIS (mis. panjang alasan mulai bangun
    diperiksa di model permintaan *dan* di `build_readiness.start_build`). Merusak satu
    lapis saja TIDAK mengubah perilaku, jadi gate tetap hijau dan mutasinya "lolos" secara
    palsu — padahal yang diuji adalah aturannya, bukan salah satu lapisnya. Mutasi
    berlapis mematikan seluruh lapis sehingga gate benar-benar diuji.
    """
    paths = [mutate_file(rel, old, new, backend=backend) for rel, old, new in edits]
    if any(p is None for p in paths):
        for p in paths:
            restore(p)
        results.append((name, "LEWAT"))
        print(f"  LEWAT  {name} (pola tidak ditemukan — perbarui mutasi ini)")
        return
    try:
        if restart and backend:
            restart_backend()
        caught = not run_gate()
        results.append((name, "TERTANGKAP" if caught else "LOLOS"))
        print(f"  {'TERTANGKAP' if caught else 'LOLOS'}  {name}")
    finally:
        for p in paths:
            restore(p)
        if restart and backend:
            restart_backend()


def case_data(name: str, mutate, undo):
    mutate()
    try:
        caught = not run_gate()
        results.append((name, "TERTANGKAP" if caught else "LOLOS"))
        print(f"  {'TERTANGKAP' if caught else 'LOLOS'}  {name}")
    finally:
        undo()


def main():
    print("=" * 74)
    print("UJI-MUTASI FASE 46 — membuktikan gate Konsolidasi Konstruksi BERGIGI")
    print("=" * 74)
    print("\nBaseline (harus HIJAU sebelum merusak apa pun):")
    if not run_gate():
        print("  BASELINE MERAH — perbaiki gate/kode dulu sebelum uji-mutasi.")
        return 1
    print("  baseline hijau\n")

    case_file("N01 unit tanpa jadwal dilaporkan 0% (bukan 'belum ada data')",
              "build_unit_board.py",
              '    if not sched:\n        missing.append("jadwal_pembangunan")',
              '    if not sched:\n        missing.append("jadwal_pembangunan")\n'
              '        row.update({"planned_progress": 0, "deviation": 0, "days_late": 0})')

    case_file("N02 papan menyembunyikan unit yang belum dijadwalkan",
              "build_unit_board.py",
              "    rows = []\n    projects =",
              "    units = [u for u in units if u['id'] in smap]\n    rows = []\n    projects =")

    case_file("N03 progres papan dihitung ulang sendiri (dua kebenaran)",
              "build_unit_board.py",
              '            "actual_progress": float(sched.get("progress") or 0),',
              '            "actual_progress": round(float(sched.get("progress") or 0) + 5, 1),')

    case_file("N04 DP tanpa rencana bayar dianggap 'belum bayar'",
              "build_unit_board.py",
              '    else:\n        missing.append("rencana_bayar")',
              '    else:\n        row["dp_paid"] = False')

    case_file("N05 kesiapan tabel memakai rumus berbeda dari evaluator",
              "build_unit_board.py",
              '        state = "blocked" if codes else ("warning" if warn else "ready")',
              '        state = "ready"')

    case_file("N06 peringatan boleh diabaikan tanpa pengakuan",
              "build_readiness.py",
              "    if ev[\"warnings\"]:\n        if not ack:",
              "    if ev[\"warnings\"] and False:\n        if not ack:")

    case_files("N07 alasan mulai bangun tidak wajib panjang minimal (dua lapis dimatikan)",
               [("models_p46.py",
                 "        if v is not None and v.strip() and len(v.strip()) < MIN_REASON:",
                 "        if False:"),
                ("build_readiness.py",
                 "        if len(note) < MIN_REASON:",
                 "        if False:")])

    case_file("N08 pemisahan tugas dilonggarkan (pelaksana boleh mulai bangun)",
              "routers/build_board_router.py",
              'user: dict = Depends(require_permission("construction",\n'
              '                                                                   "approve"))',
              'user: dict = Depends(require_permission("construction",\n'
              '                                                                   "update"))')

    case_file("N09 mode TEGAS tidak lagi memblokir (kebijakan jadi hiasan)",
              "build_readiness.py",
              '    sev = "blocker" if require_dp else "warning"',
              '    sev = "warning"')

    case_file("N10 setting DP bawaannya dinyalakan diam-diam",
              "settings_store.py",
              '_d("build.require_dp_before_start", False,',
              '_d("build.require_dp_before_start", True,')

    case_file("N11 izin lewat tanggal dianggap tetap sehat",
              "permit_scope.py",
              '    elif status == "expired" or (expiry and days_left is not None and days_left < 0):\n'
              '        code = "expired"',
              '    elif status == "expired":\n        code = "expired"')

    case_file("N12 izin wajib yang hilang diam-diam dianggap terpenuhi",
              "permit_scope.py",
              '        "satisfied": bool(good),',
              '        "satisfied": True,')

    case_file("N13 rantai izin berhenti di unit (warisan hilang)",
              "permit_scope.py",
              "    for level in PERMIT_SCOPES:\n        sid = chain.get(f\"{level}_id\")",
              "    for level in (\"unit\",):\n        sid = chain.get(f\"{level}_id\")")

    case_file("N14 peringatan izin tidak lagi membuat tugas Work Hub",
              "permit_alerts.py",
              "        await wh.spawn(porg, JOBDESK,",
              "        _ = JOBDESK and None\n        await _noop(porg,")

    case_file("N15 fitur lama hilang dari hub (panel dihapus dari JSX tab)",
              "components/build/BuildFieldTab.js",
              "          <ForemanBoard projectId={projectId} />",
              "          {/* dihapus */}", backend=False, restart=False)

    case_file("N16 rata-rata progres dibagi SEMUA unit (termasuk belum dijadwalkan)",
              "build_unit_board.py",
              '        summary["avg_progress"] = round(sum(prog) / len(prog), 1)',
              '        summary["avg_progress"] = round(sum(prog) / max(1, len(rows)), 1)')

    print("\n" + "=" * 74)
    lolos = [n for n, s in results if s == "LOLOS"]
    lewat = [n for n, s in results if s == "LEWAT"]
    caught = [n for n, s in results if s == "TERTANGKAP"]
    print(f"TERTANGKAP: {len(caught)} · LOLOS: {len(lolos)} · LEWAT: {len(lewat)}")
    for n in lolos:
        print(f"  LOLOS  {n}")
    for n in lewat:
        print(f"  LEWAT  {n}")
    print("\nBaseline setelah semua mutasi dipulihkan:")
    ok = run_gate()
    print("  " + ("hijau kembali" if ok else "MASIH MERAH — periksa pemulihan berkas!"))
    return 0 if (not lolos and not lewat and ok) else 1


if __name__ == "__main__":
    sys.exit(main())
