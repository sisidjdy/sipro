#!/usr/bin/env python3
"""mutasi_43.py — uji-mutasi gate Fase 43 (`verify_ads.py`) + gate IA V2 versi ledger pintu.

Gate yang tidak bisa gagal tidak menjaga apa pun. Skrip ini MERUSAK kode/keadaan dengan
sengaja (satu cacat per kali), memastikan gate MEMERAH pada temuan yang tepat, lalu
memulihkannya dan memastikan gate HIJAU kembali.

Setiap mutasi = satu janji yang gate klaim dijaganya, dan semuanya cacat REALISTIS (bukan
sintaks yang dirusak):

  Biaya iklan & impor (verify_ads.py)
    M1  setiap impor dianggap perubahan           -> angka "direvisi" tanpa ada yang berubah
    M2  index unik kunci natural dihapus dari DB  -> database berhenti menjaga idempotensi
    M3  dry-run ikut menyimpan                    -> "pratinjau" menulis data tanpa diminta
    M4  validasi mata uang dicabut                -> USD masuk sebagai rupiah
    M5  penjagaan baris kembar dalam berkas hilang-> satu hari dihitung dua kali
    M8  jejak perubahan (history) dicabut         -> biaya berubah diam-diam
    M9  penjaga "sudah dikomit" dicabut           -> riwayat commit pertama ditulis ulang

  Kejujuran angka (verify_ads.py)
    M6  status biaya "missing" tidak pernah muncul-> rentang tanpa biaya terlihat lengkap
    M7  CPL jatuh ke 0 saat biaya belum ada       -> kampanye tanpa biaya terlihat paling murah
    M18 biaya kampanye dibagi ke tingkat adset    -> rincian karangan

  Integrasi & kredensial (verify_ads.py)
    M10 health mengirim NILAI env, bukan terisi/tidak -> kredensial bocor ke layar
    M11 penolakan sync tidak menyebut env yang kosong -> pemakai tak tahu harus mengisi apa

  CAPI (verify_ads.py)
    M12 event_id tidak deterministik lagi         -> retry dihitung sebagai konversi baru
    M13 dedup memeriksa field yang salah          -> event kembar bisa tersimpan
    M14 user_data menyimpan nomor telepon mentah  -> PII bocor di koleksi yang dibaca luas

  Layar & navigasi (verify_ads.py + verify_ia_v2.py)
    M15 menu "Kampanye & Biaya Iklan" ditutup lagi jadi "Segera Hadir"
    M16 pintu menu baru tanpa mendaftarkannya di ledger docs -> IA sprawl tanpa jejak
    M17 layar menuliskan label enum sendiri       -> layar beda dengan kamus data

  RBAC (verify_ads.py)
    M19 endpoint kinerja memakai izin resource lain -> manajer proyek bisa membaca biaya iklan

Pakai: `python3 scripts/mutasi_43.py` (atau `... M7 M12` untuk sebagian).
Exit !=0 bila ada mutasi yang TIDAK tertangkap.
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
LOCK = pathlib.Path("/tmp/mutasi_43.lock")

ENGINE = "backend/ads_engine.py"
REPORT = "backend/ads_report.py"
ROUTER = "backend/routers/ads_router.py"
CAPI = "backend/capi.py"
NAV = "frontend/src/config/navigationConfig.js"
IMPREP = "frontend/src/components/ads/ImportReport.js"

NATURAL_KEY = [("org_id", 1), ("platform", 1), ("campaign_id", 1), ("adset_id", 1),
               ("ad_id", 1), ("date", 1)]


def wait_backend():
    """Mutasi backend membuat uvicorn memuat ulang. Tanpa jeda ini gate bisa
    memerah/menghijau karena ALASAN YANG SALAH (server belum siap)."""
    for _ in range(120):
        try:
            with urllib.request.urlopen("http://localhost:8001/api/health", timeout=2) as r:
                if r.status == 200:
                    return
        except Exception:  # noqa: BLE001
            time.sleep(0.5)


def run(script: str, restart: bool = False) -> tuple:
    """Jalankan satu gate. `restart=True` untuk mutasi yang menyentuh berkas BACKEND.

    Kenapa restart eksplisit, bukan mengandalkan `uvicorn --reload`: pemantau berkas baru
    melihat perubahan beberapa saat kemudian, dan startup SIPRO ikut menjalankan index +
    migrasi + seed (belasan detik). Akibatnya urutan yang tampak "aman" (tulis berkas →
    tunggu health 200 → jalankan gate) sebenarnya menjalankan gate di atas server LAMA yang
    lalu mati di tengah jalan — gate mati karena koneksi terputus dan mutasi terlihat "tidak
    tertangkap" padahal yang rusak adalah harness-nya.
    """
    if restart:
        subprocess.run(["sudo", "supervisorctl", "restart", "backend"],
                       capture_output=True, text=True, timeout=180)
    else:
        time.sleep(3)
    wait_backend()
    time.sleep(1)
    p = subprocess.run([sys.executable, str(ROOT / "scripts" / script)],
                       capture_output=True, text=True, timeout=900)
    return p.returncode, (p.stdout + p.stderr)


def selected(label: str) -> bool:
    only = [a for a in sys.argv[1:] if not a.startswith("-")]
    return not only or any(label.split()[0] == o for o in only)


def record(label: str, code: int, out: str, expect: str, script: str, restart: bool = False):
    detected = expect is None or expect in out
    # Bila aplikasinya MATI karena mutasi, gate memang gagal — tetapi bukan pada temuan yang
    # dimaksud, jadi mutasi itu tidak membuktikan apa pun tentang gigi gate. Dilaporkan apa
    # adanya (bukan dihitung PASS) supaya tidak ada rasa aman yang palsu.
    if "Connection refused" in out or "Max retries exceeded" in out:
        results.append((label, "TIDAK BISA DIUJI",
                        "aplikasi mati karena mutasi ini — gate tak bisa dijalankan; "
                        "pilih mutasi yang membiarkan server hidup"))
    else:
        ok = detected and code != 0
        results.append((label, "PASS" if ok else "FAIL",
                        "gate memerah pada temuan yang tepat" if ok else
                        f"cacat TIDAK TERTANGKAP (exit={code}, pola '{expect}' "
                        f"{'ada' if detected else 'TIDAK ada'}) :: ...{out.strip()[-320:]}"))
    code2, out2 = run(script, restart=restart)
    results.append((f"{label} (pulih)", "PASS" if code2 == 0 else "FAIL",
                    "hijau kembali" if code2 == 0 else
                    f"MASIH MERAH setelah dipulihkan :: ...{out2.strip()[-260:]}"))


def mutate(label: str, edits: list, script: str, expect: str = None):
    """edits: [(path, old, new)] — satu mutasi boleh menyentuh beberapa berkas."""
    if not selected(label):
        return
    restart = any(path.startswith("backend/") for path, _, _ in edits)
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
        code, out = run(script, restart=restart)
    finally:
        for p, s in originals.items():
            (ROOT / p).write_text(s)
    record(label, code, out, expect, script, restart=restart)


def mutate_state(label: str, break_fn, restore_fn, script: str, expect: str = None):
    """Mutasi KEADAAN (index database / isi dokumen) — bukan kode. Dipakai untuk janji yang
    dijaga oleh database, bukan oleh berkas python."""
    if not selected(label):
        return
    state = break_fn()
    try:
        code, out = run(script)
    finally:
        restore_fn(state)
    record(label, code, out, expect, script)


# ------------------------------------------------------ mutasi keadaan database
def drop_natural_index():
    try:
        db.ad_spend.drop_index("uq_ad_spend_natural")
    except Exception:  # noqa: BLE001 — index memang boleh sudah tidak ada
        pass
    return True


def restore_natural_index(_state):
    db.ad_spend.create_index(NATURAL_KEY, unique=True, name="uq_ad_spend_natural")


def leak_pii():
    row = db.conversion_events.find_one({"user_data": {"$ne": None}}, {"_id": 0})
    if not row:
        return None
    db.conversion_events.update_one({"id": row["id"]},
                                    {"$set": {"user_data": {"ph": "+628122222222"}}})
    return row


def restore_pii(row):
    if row:
        db.conversion_events.update_one({"id": row["id"]},
                                        {"$set": {"user_data": row.get("user_data") or {}}})


def guard_single_run():
    """Cegah DUA suite mutasi berjalan bersamaan.

    Ini bukan kehati-hatian teoretis: saat menulis suite ini dua proses sempat berjalan
    bersamaan, dan karena keduanya menulis lalu MEMULIHKAN berkas yang sama, salah satu
    memulihkan versi yang sudah termutasi — repo tertinggal dengan tiga cacat "hantu"
    (`existing = None`, `committed-never`, `spend_days < 0`) yang lolos dari mata karena
    tidak ada yang mengubahnya secara sengaja. Kunci ini + pemeriksaan baseline di bawah
    membuat kejadian itu tidak bisa terulang tanpa terlihat.
    """
    if LOCK.exists():
        pid = LOCK.read_text().strip()
        alive = pathlib.Path(f"/proc/{pid}").exists() if pid.isdigit() else False
        if alive:
            print(f"BATAL: suite mutasi lain masih berjalan (PID {pid}). "
                  "Tunggu selesai atau hentikan dulu — dua suite bersamaan akan saling "
                  "menimpa pemulihan berkas.")
            sys.exit(2)
        LOCK.unlink(missing_ok=True)
    LOCK.write_text(str(os.getpid()))


def guard_baseline():
    """Baseline WAJIB hijau sebelum mutasi. Kalau tidak, setiap mutasi akan "tertangkap"
    karena alasan yang salah (gate sudah merah sejak awal)."""
    for script in ("verify_ads.py", "verify_ia_v2.py"):
        code, out = run(script)
        if code != 0:
            print(f"BATAL: baseline {script} SUDAH MERAH sebelum mutasi apa pun.\n"
                  f"{out.strip()[-800:]}")
            LOCK.unlink(missing_ok=True)
            sys.exit(2)


def main():
    guard_single_run()
    try:
        guard_baseline()
        run_mutations()
    finally:
        LOCK.unlink(missing_ok=True)


def run_mutations():
    # ------------------------------------------------- idempotensi & impor CSV
    mutate("M1 setiap impor dianggap perubahan (angka lama 'direvisi' tanpa ada yang berubah)",
           [(ENGINE, '    diff = changed_fields(existing, values)\n    if not diff:\n'
                     '        return "unchanged", existing',
             '    diff = changed_fields(existing, values)\n    if not diff and False:\n'
             '        return "unchanged", existing')],
           "verify_ads.py", "FAIL  impor ulang berkas yang SAMA = unchanged")

    mutate_state("M2 index unik kunci natural dihapus dari database",
                 drop_natural_index, restore_natural_index, "verify_ads.py",
                 "FAIL  index unik uq_ad_spend_natural ada & unik")

    mutate("M3 dry-run ikut menyimpan (pratinjau menulis data tanpa diminta)",
           [(ENGINE, '    if dry_run or not plan["ok"]:\n        return doc',
             '    if not plan["ok"]:\n        return doc')],
           "verify_ads.py", "FAIL  dry-run TIDAK menulis satu pun baris biaya")

    mutate("M4 validasi mata uang dicabut (USD masuk sebagai rupiah)",
           [(ENGINE, '    currency = (_s(raw.get("currency")) or CURRENCY).upper()\n'
                     '    if currency != CURRENCY:',
             '    currency = (_s(raw.get("currency")) or CURRENCY).upper()\n'
             '    if currency == "XXX":')],
           "verify_ads.py", "FAIL  alasan penolakan menyebut mata uang bukan IDR")

    mutate("M5 penjagaan baris kembar dalam satu berkas hilang",
           [(ENGINE, "    key = key_string(row)\n    if key in seen:",
             "    key = key_string(row)\n    if key in {}:")],
           "verify_ads.py", "FAIL  alasan penolakan menyebut baris kembar di dalam berkas")

    mutate("M8 jejak perubahan (history) dicabut — biaya berubah diam-diam",
           [(ENGINE, '        "$inc": {"revisions": 1},\n'
                     '        "$push": {"history": {"at": ts, "by": actor, "source": source, '
                     '"changes": diff}},',
             '        "$inc": {"revisions": 1},')],
           "verify_ads.py", "FAIL  nilai lama tersimpan di history")

    mutate("M9 penjaga 'sudah dikomit' dicabut (riwayat commit pertama ditulis ulang)",
           [(ENGINE, '    if import_doc.get("status") == "committed":\n        return import_doc',
             '    if import_doc.get("status") == "committed-never":\n        return import_doc')],
           "verify_ads.py", "FAIL  commit kedua TIDAK menulis ulang hasil commit pertama")

    # ------------------------------------------------------- kejujuran angka
    mutate("M6 status 'missing' tidak pernah muncul (rentang tanpa biaya terlihat lengkap)",
           [(REPORT, '    if spend_days <= 0:\n        return "missing"',
             '    if spend_days < 0:\n        return "missing"')],
           "verify_ads.py", "FAIL  rentang tanpa biaya → cost_status 'missing'")

    mutate("M7 CPL jatuh ke 0 saat biaya belum ada",
           [(REPORT, '        "cpl": int(round(spend / leads)) if has_cost and leads else None,',
             '        "cpl": int(round(spend / leads)) if has_cost and leads else 0,')],
           "verify_ads.py", "FAIL  kampanye tanpa biaya TIDAK ditulis 0 untuk metrik biaya")

    mutate("M18 biaya kampanye dibagi ke tingkat adset (rincian karangan)",
           [(REPORT, '        r["spend"] = sp["spend"] if (sp and level == "campaign") else None',
             '        r["spend"] = sp["spend"] if sp else None')],
           "verify_ads.py", "FAIL  biaya TIDAK dibagi-bagi ke tingkat adset")

    # -------------------------------------------------- integrasi & kredensial
    mutate("M10 health mengirim NILAI env, bukan terisi/tidak (kredensial bocor)",
           [(REPORT, '        filled = {name: bool(os.environ.get(name)) for name in spec["env"]}',
             '        filled = {name: os.environ.get(name) for name in spec["env"]}')],
           "verify_ads.py", "FAIL  [meta_ads] env hanya melaporkan terisi/tidak")

    mutate("M11 penolakan sync tidak menyebut env yang kosong",
           [(ROUTER, '            f"kredensial belum diisi ({missing}). Selama itu biaya iklan '
                     'diisi manual atau "',
             '            "kredensial belum lengkap. Selama itu biaya iklan diisi manual atau "')],
           "verify_ads.py", "FAIL  penolakan sync menyebut mode simulasi + env yang belum diisi")

    # ----------------------------------------------------------------- CAPI
    mutate("M12 event_id tidak deterministik (retry dihitung sebagai konversi baru)",
           [(CAPI, '    raw = f"{org_id}|{event_name}|{lead_id or \'\'}|{deal_id or \'\'}"',
             '    raw = f"{org_id}|{event_name}|{lead_id or \'\'}|{deal_id or \'\'}|{now_iso()}"')],
           "verify_ads.py", "FAIL  event_id DETERMINISTIK")

    mutate("M13 dedup CAPI memeriksa field yang salah (event kembar bisa tersimpan)",
           [(CAPI, '    existing = await db.conversion_events.find_one({"org_id": org_id, '
                   '"event_id": event_id},',
             '    existing = await db.conversion_events.find_one({"org_id": org_id, '
             '"id": event_id},')],
           "verify_ads.py", "FAIL  kode CAPI memeriksa event_id sebelum menulis")

    mutate_state("M14 user_data menyimpan nomor telepon mentah (PII bocor)",
                 leak_pii, restore_pii, "verify_ads.py",
                 "FAIL  user_data hanya berisi hash SHA-256")

    # ------------------------------------------------------- layar & navigasi
    mutate("M15 menu Kampanye & Biaya Iklan ditutup lagi jadi 'Segera Hadir'",
           [(NAV, '{ id: "campaigns", label: "Kampanye & Biaya Iklan", icon: Megaphone, '
                  'path: "/campaigns",\n        roles: ADS_SIDE },',
             '{ id: "campaigns", label: "Kampanye & Biaya Iklan", icon: Megaphone, '
             'comingSoon: true,\n        note: "Fase 44", roles: ADS_SIDE },')],
           "verify_ads.py", "FAIL  menu 'campaigns' TIDAK lagi 'Segera Hadir'")

    mutate("M16 pintu menu baru tanpa mendaftarkannya di ledger docs (sprawl tanpa jejak)",
           [(NAV, '      { id: "config-center", label: "Pusat Konfigurasi", '
                  'icon: SlidersHorizontal,\n        path: "/config", roles: ADMIN_SIDE },',
             '      { id: "config-center", label: "Pusat Konfigurasi", '
             'icon: SlidersHorizontal,\n        path: "/config", roles: ADMIN_SIDE },\n'
             '      { id: "config-extra", label: "Pengaturan Tambahan", '
             'icon: SlidersHorizontal,\n        path: "/config-extra", roles: ADMIN_SIDE },')],
           "verify_ia_v2.py", "FAIL  tidak ada pintu sidebar di luar ledger")

    mutate("M17 layar menuliskan label enum sendiri (layar beda dengan kamus data)",
           [(IMPREP, '          ["rejected", labelOf("ads_row_status", "rejected"), s.rejected],',
             '          ["rejected", "Ditolak", s.rejected],')],
           "verify_ads.py", "FAIL  layar iklan tidak menuliskan label enum sendiri")

    # ----------------------------------------------------------------- RBAC
    mutate("M19 endpoint kinerja memakai izin resource lain (biaya iklan bocor ke PM)",
           [(ROUTER, '                      user: dict = Depends(require_permission("ads", '
                     '"view"))):\n    """CPL/CAC/ROAS per kampanye.',
             '                      user: dict = Depends(require_permission("projects", '
             '"view"))):\n    """CPL/CAC/ROAS per kampanye.')],
           "verify_ads.py", "FAIL  manajer proyek GET /ads/performance → 403")

    print("\n==================== HASIL UJI-MUTASI FASE 43 ====================")
    bad = [r for r in results if r[1] != "PASS"]
    for label, status, detail in results:
        print(f"  {status:15} {label}\n{' ' * 19}{detail}")
    print("=" * 66)
    print(f"{len(results) - len(bad)}/{len(results)} pemeriksaan PASS "
          f"({len([r for r in results if '(pulih)' not in r[0]])} mutasi)")
    if bad:
        print("ADA MUTASI YANG TIDAK TERTANGKAP / TIDAK PULIH — gate belum bergigi.")
        sys.exit(1)
    print("SEMUA MUTASI TERTANGKAP dan baseline pulih hijau.")


if __name__ == "__main__":
    main()
