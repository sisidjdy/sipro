#!/usr/bin/env python3
"""mutasi_58.py — UJI-MUTASI Fase 58: membuktikan GATE 49 BERGIGI.

Cara kerja: satu per satu aturan Fase 58 dimatikan di kode (mutan), lalu
`scripts/verify_late_fee.py` dijalankan. Gate yang tetap HIJAU ketika aturannya dimatikan
berarti gate itu tidak menguji apa pun — **LOLOS adalah cacat perangkat uji**, bukan
kelulusan produk. (Pelajaran Fase 55: gate 46 hijau pada percobaan pertama dan sembilan
pemeriksaannya ternyata tidak menguji apa-apa.)

Yang dimutasi di sini adalah janji yang tertulis pada dokumen yang ditandatangani pembeli:
  * toleransi yang disusun pemakai IKUT ke jadwal tagihan & menang atas angka bawaan;
  * "lewat tanggal" bukan berarti "menunggak" selama masih di dalam tenggang;
  * denda prorata sesudah tenggang, berbatas atas & bawah, dari Pusat Konfigurasi;
  * denda yang ditagihkan BERJURNAL, idempoten, dan tidak pernah dobel;
  * keringanan hanya oleh Manajer Keuangan, beralasan, membalik jurnal, dan tidak bisa
    dianulir bawahannya dengan menagihkan denda yang sama lagi;
  * layar & portal MENYEBUTKAN keadaan/sebabnya dengan bahasa Kamus Data, tanpa nomor akun.

Pakai:
    python3 scripts/mutasi_58.py --check           # cepat: pastikan semua pola masih ada
    python3 scripts/mutasi_58.py                   # penuh
    python3 scripts/mutasi_58.py --only=M01,M12    # sebagian
    python3 scripts/mutasi_58.py --from=M20        # lanjutkan run yang terputus
    python3 scripts/mutasi_58.py --ringkas         # laporan kumulatif
    python3 scripts/mutasi_58.py --pulihkan        # kembalikan kode bila run terputus
"""
import pathlib
import subprocess
import sys
import time

import requests
from dotenv import load_dotenv

ROOT = pathlib.Path(__file__).resolve().parent.parent
load_dotenv(ROOT / "backend" / ".env")
sys.path.insert(0, str(ROOT / "scripts"))

GATE = "verify_late_fee.py"                  # gate 49
HEALTH = "http://localhost:8001/api/health"

LF = "backend/late_fee_engine.py"
FIN = "backend/finance_engine.py"
FR = "backend/finance_reports.py"
RT = "backend/routers/late_fee_router.py"
PT = "backend/routers/portal_router.py"
RB = "backend/rbac_matrix.py"
GLE = "backend/gl_engine.py"
REF = "backend/reference_p58.py"
TAB = "frontend/src/components/customers/CustomerPaymentPlanTab.js"
PAN = "frontend/src/components/finance/LateFeePanel.js"
PPY = "frontend/src/components/portal/panels/PaymentsPanel.js"
IDS = "frontend/src/constants/testIds/p58.js"

# Berkas backend memicu reload uvicorn; berkas frontend diperiksa gate secara STATIS
# sehingga mutannya tidak perlu menunggu backend (memotong waktu run secara nyata).
BACKEND_FILES = {LF, FIN, FR, RT, PT, RB, GLE, REF}

MUTATIONS = [
    ("M01 toleransi termin HILANG saat skema diterjemahkan menjadi tagihan", [
        (FIN, '                    "grace_days": int(i.get("grace_days") or 0),\n', "")], "K1"),
    ("M02 tenggang termin diabaikan (hanya angka bawaan yang dipakai)", [
        (LF, '    g = item.get("grace_days")\n'
             '    return int(g) if g not in (None, "") else int(pol["grace_days"])',
             '    return int(pol["grace_days"])')], "K2"),
    ("M03 kebijakan denda kembali menjadi angka mati di kode", [
        (LF, '        "grace_days": int(await cfg.get(KEY_GRACE, org_id=org) or 0),\n'
             '        "rate_pct_month": float(await cfg.get(KEY_RATE, org_id=org) or 0),\n'
             '        "max_pct_of_term": float(await cfg.get(KEY_CAP, org_id=org) or 0),\n'
             '        "min_charge": int(await cfg.get(KEY_MIN, org_id=org) or 0),\n',
             '        "grace_days": 7,\n'
             '        "rate_pct_month": 2.0,\n'
             '        "max_pct_of_term": 5.0,\n'
             '        "min_charge": 50000,\n')], "K3"),
    ("M04 batas atas & minimum denda dibuang (tagihan tanpa kewajaran)", [
        (LF, '    batas = round(int(outstanding) * (pol["max_pct_of_term"] / 100.0)) \\\n'
             '        if pol["max_pct_of_term"] > 0 else kasar\n'
             '    nilai = min(kasar, batas)\n'
             '    return 0 if nilai < int(pol["min_charge"] or 0) else nilai',
             '    return kasar')], "K4"),
    ("M05 denda sebulan penuh sejak H+1 (bukan prorata sesudah tenggang)", [
        (LF, '    kasar = round(int(outstanding) * (pol["rate_pct_month"] / 100.0) * (int(days) / 30.0))',
             '    kasar = round(int(outstanding) * (pol["rate_pct_month"] / 100.0))')], "K4b"),
    ("M06 keadaan DALAM TOLERANSI dihapus (lewat tanggal = langsung menunggak)", [
        (LF, '        if grace_until and today <= grace_until:\n'
             '            row["state"] = "dalam_tenggang"\n'
             '            row["grace_left_days"] = max(0, (grace_until - today).days)\n'
             '        else:\n',
             '        if False:\n'
             '            pass\n'
             '        else:\n')], "K5"),
    ("M07 hari denda dihitung sejak jatuh tempo (tenggang tidak mengurangi apa pun)", [
        (LF, '            row["days_late"] = max(0, row["days_past_due"] - grace)',
             '            row["days_late"] = row["days_past_due"]')], "K5b"),
    ("M08 label keadaan diketik mesin sendiri (SSOT bercabang)", [
        (LF, '    row["state_label"] = ref.label_of("late_state", row["state"])',
             '    row["state_label"] = row["state"].replace("_", " ").title()')], "K5c"),
    ("M09 denda ditagihkan TANPA jurnal (angka di layar, bukan uang di buku)", [
        (LF, '        jr = await gl.post_journal(\n'
             '            org, (f"Denda keterlambatan {r[\'label\']} · unit {inv.get(\'unit_code\') or \'-\'} "\n'
             '                  f"({r[\'days_late\']} hari lewat toleransi)"),\n'
             '            [{"account_code": AKUN_PIUTANG, "debit": r["denda_billable"], "credit": 0},\n'
             '             {"account_code": AKUN_PENDAPATAN_DENDA, "debit": 0,\n'
             '              "credit": r["denda_billable"]}],\n'
             '            source_type="late_fee", source_id=deal_id, source_event=event,\n'
             '            source_deal_id=deal_id, posted_by=actor, auto=False)',
             '        jr = {"id": None}')], "K6"),
    ("M10 idempotensi jurnal denda dimatikan (klik dua kali = denda dua kali)", [
        (LF, '            source_type="late_fee", source_id=deal_id, source_event=event,',
             '            source_type="late_fee", source_id=deal_id, source_event=None,')], "K6b"),
    ("M11 yang ditagihkan bukan SELISIH, tetapi denda penuh setiap kali", [
        (LF, '        row["denda_billable"] = max(0, row["denda_running"] - row["denda_charged"]\n'
             '                                    - row["denda_waived_part"])',
             '        row["denda_billable"] = row["denda_running"]')], "K6c"),
    ("M12 keringanan boleh diberikan siapa pun tanpa alasan", [
        (LF, '    if not may_waive:\n'
             '        raise ValueError("Hanya Manajer Keuangan yang boleh memberi keringanan denda.")\n'
             '    if len((reason or "").strip()) < 10:\n'
             '        raise ValueError("Alasan keringanan wajib minimal 10 huruf — keputusan ini dibaca "\n'
             '                         "auditor.")\n', "")], "K7"),
    ("M13 keringanan TIDAK membalik jurnal (pendapatan denda tetap berdiri)", [
        (LF, '    jr = await gl.post_journal(\n'
             '        org, (f"Keringanan denda keterlambatan · unit {inv.get(\'unit_code\') or \'-\'}: "\n'
             '              f"{reason.strip()}"),\n'
             '        [{"account_code": AKUN_PENDAPATAN_DENDA, "debit": nilai, "credit": 0},\n'
             '         {"account_code": AKUN_PIUTANG, "debit": 0, "credit": nilai}],\n'
             '        source_type="late_fee_waiver", source_id=penalty_id,\n'
             '        source_event=f"late_fee_waive:{penalty_id}", source_deal_id=deal_id,\n'
             '        posted_by=actor, auto=False)',
             '    jr = {"id": None}')], "K7b"),
    ("M14 denda yang SUDAH DIBAYAR bisa 'diringankan' (uang pembeli lenyap)", [
        (LF, '    if int(row.get("paid_amount") or 0) > 0:\n'
             '        raise ValueError("Denda ini sudah dibayar sebagian/penuh — keringanan tidak boleh "\n'
             '                         "menghapus uang yang sudah diterima. Pakai pengembalian dana.")\n',
             "")], "K7c"),
    ("M15 keringanan bisa dianulir bawahan (denda sama ditagihkan ulang)", [
        (LF, '    waived_days = _waived_days_map(items)\n', '    waived_days = {}\n')], "K8"),
    ("M16 sebab penolakan tidak terdaftar di Kamus Data", [
        (REF, '            _o("masih_tenggang", "Masih di dalam masa toleransi kontrak"),\n',
              "")], "K9"),
    ("M17 akun pendapatan denda dihapus dari CoA (menumpang lain-lain)", [
        (GLE, '    ("4-1400", "Pendapatan Denda Keterlambatan", "revenue"),\n', "")], "K10"),
    ("M18 yang menagihkan denda boleh meringankannya sendiri (RBAC)", [
        (RB, '        "finance": ["view_all", "create"],\n'
             '        "finance_manager": ["view_all", "create", "override"],',
             '        "finance": ["view_all", "create", "override"],\n'
             '        "finance_manager": ["view_all", "create", "override"],')], "K11"),
    ("M19 endpoint keringanan memakai izin penagihan (pemisahan tugas hilang)", [
        (RT, 'require_permission("late_fee", "override")',
             'require_permission("late_fee", "create")')], "K12"),
    ("M20 sales lintas lingkup bisa membaca transaksi orang lain", [
        (RT, '    if is_scoped_sales(user) and deal.get("assigned_to") != user.get("email"):\n'
             '        raise HTTPException(status_code=403, detail="Akses ditolak: bukan transaksi Anda")\n',
             "")], "K12b"),
    ("M21 tombol 'Denda' lama menghitung & menagih sendiri lagi (rumus kedua)", [
        (FR, '    out = await lf.apply(org_id, deal_id, actor)\n'
             '    total = sum(int(c["amount"]) for c in out.get("created") or [])',
             '    inv = await db.ar_invoices.find_one({"org_id": org_id, "deal_id": deal_id},\n'
             '                                       {"_id": 0})\n'
             '    out = {"created": [{"amount": 0, "is_penalty": True}]}\n'
             '    total = 0')], "K13"),
    ("M22 rumus denda dikloning di modul laporan", [
        (FR, '    return lf.denda_of(int(overdue_amount or 0), eff, pol)',
             '    return round(int(overdue_amount or 0) * (float(rate_pct_month) / 100.0)\n'
             '                 * (eff / 30.0))')], "K13b"),
    ("M23 daftar penagihan mencampur tenggang dengan tunggakan", [
        (FR, '            if st["state"] == "terlambat":',
             '            if st["state"] in ("terlambat", "dalam_tenggang"):')], "K13c"),
    ("M24 nomor akun GL bocor ke mata pembeli di portal", [
        (LF, '    return {"policy_sentence": a["policy_sentence"], "rows": rows, "penalties": denda,',
             '    return {"policy_sentence": a["policy_sentence"] + " (akun 4-1400)",\n'
             '            "rows": rows, "penalties": denda,')], "K14b"),
    ("M25 layar kembali mengaku toleransi keterlambatan 'belum dibangun'", [
        (TAB, 'nyata dari Keuangan. <b>Toleransi keterlambatan &amp; denda</b> kini dijalankan mesin',
              'nyata dari Keuangan. Yang <b>belum</b> dibangun: <b>toleransi keterlambatan</b>. Mesin')],
     "K20"),
    ("M26 layar menghitung tenggang sendiri di peramban (bukan dari server)", [
        (TAB, '  const row = (late?.rows || []).find((r) => r.item_id === item.id);',
              '  const row = null;')], "K20b"),
    ("M27 panel denda menjadi komponen MATI (tidak pernah dirender)", [
        (TAB, '      <LateFeePanel dealId={deal.id} unitCode={deal.unit_code || inv.unit_code}\n'
              '        onChanged={onChanged} />\n', "")], "K20d"),
    ("M28 sebab denda belum bisa ditagihkan tidak disebutkan (tombol diam)", [
        (PAN, '        <p data-testid={P58.blockNote} data-code={data.block.code}',
              '        <p data-code={data.block.code}')], "K21b"),
    ("M29 keringanan bisa dikirim tanpa alasan dari layar", [
        (PAN, '              disabled={reason.trim().length < 10 || busy === "waive"}>',
              '              disabled={busy === "waive"}>')], "K21d"),
    ("M30 portal pembeli tidak lagi menampilkan toleransi & dendanya", [
        (PPY, '          {p.late && (p.late.rows?.length || p.late.penalties?.length) ? (',
              '          {false ? (')], "K22"),
    ("M31 testId Fase 58 menjadi MATI (terdaftar tetapi tidak dipakai layar)", [
        (IDS, '  panel: "late-fee-panel",',
              '  panel: "late-fee-panel",\n  hantu: "late-fee-hantu",')], "K23"),
]
def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def write(rel: str, src: str) -> None:
    (ROOT / rel).write_text(src, encoding="utf-8")


def apply_patches(patches) -> dict:
    backup = {}
    for path, find, repl in patches:
        src = read(path)
        if path not in backup:
            backup[path] = src
        if find not in src:
            raise RuntimeError(f"pola tidak ditemukan di {path}: {find[:70]}")
        write(path, src.replace(find, repl, 1))
    return backup


def restore(backup: dict) -> None:
    for path, src in backup.items():
        write(path, src)


# ---------------------------------------------- jaring pengaman bila run terputus
SNAP = ROOT / "memory" / "mutasi58_snapshot"


def files_touched() -> list:
    out = []
    for _n, patches, _c in MUTATIONS:
        for path, _f, _r in patches:
            if path not in out:
                out.append(path)
    return out


def snapshot() -> None:
    SNAP.mkdir(parents=True, exist_ok=True)
    for rel in files_touched():
        (SNAP / rel.replace("/", "__")).write_text(read(rel), encoding="utf-8")


def pulihkan() -> int:
    if not SNAP.exists():
        print("Tidak ada snapshot kode — tidak ada berkas yang perlu dipulihkan.")
        return 0
    n = 0
    for rel in files_touched():
        src = SNAP / rel.replace("/", "__")
        if src.exists() and src.read_text(encoding="utf-8") != read(rel):
            write(rel, src.read_text(encoding="utf-8"))
            print(f"  dipulihkan  {rel}")
            n += 1
    print(f"{n} berkas kode dipulihkan dari snapshot.")
    return 0


# ------------------------------------------------------- menunggu backend memuat ulang
def server_pids() -> tuple:
    induk = subprocess.run(["pgrep", "-f", "uvicorn server:app"],
                           capture_output=True, text=True)
    pids = []
    for p in induk.stdout.split():
        if not p.strip().isdigit():
            continue
        anak = subprocess.run(["pgrep", "-P", p.strip()], capture_output=True, text=True)
        pids += [int(x) for x in anak.stdout.split() if x.strip().isdigit()]
    return tuple(sorted(pids))


def health_ok(timeout: float = 3.0) -> bool:
    try:
        return requests.get(HEALTH, timeout=timeout).status_code == 200
    except requests.RequestException:
        return False


def wait_reload(before: tuple, batas_ganti: int = 40, batas_sehat: int = 240) -> str:
    mulai = time.time()
    ganti = False
    while time.time() - mulai < batas_ganti:
        now = server_pids()
        if now and now != before:
            ganti = True
            break
        time.sleep(0.4)
    while time.time() - mulai < batas_sehat:
        if health_ok():
            time.sleep(1.2)
            return (f"reload {time.time() - mulai:.0f}s" if ganti else
                    f"TANPA reload terdeteksi ({time.time() - mulai:.0f}s)")
        time.sleep(0.5)
    return "backend TIDAK sehat setelah menunggu"


# --------------------------------------------------------------------------- gate
def run_gate(tag: str) -> tuple:
    logdir = ROOT / "memory" / "gatelogs"
    logdir.mkdir(parents=True, exist_ok=True)
    log = logdir / f"mut58_{tag}.log"
    with log.open("w", encoding="utf-8") as fh:
        p = subprocess.run([sys.executable, str(ROOT / "scripts" / GATE)],
                           stdout=fh, stderr=subprocess.STDOUT, cwd=str(ROOT))
    isi = log.read_text(encoding="utf-8", errors="ignore")
    jatuh = [ln.strip()[6:].split()[0] for ln in isi.splitlines()
             if ln.strip().startswith("MERAH")]
    return p.returncode == 0, jatuh


HASIL = ROOT / "memory" / "gatelogs" / "mutasi_58_hasil.tsv"


def catat_hasil(nama: str, hasil: str, catatan: str = "") -> None:
    HASIL.parent.mkdir(parents=True, exist_ok=True)
    with HASIL.open("a", encoding="utf-8") as fh:
        fh.write(f"{nama.split()[0]}\t{hasil}\t{nama}\t{catatan}\n")


def baca_hasil() -> dict:
    if not HASIL.exists():
        return {}
    out = {}
    for line in HASIL.read_text(encoding="utf-8").splitlines():
        b = line.split("\t")
        if len(b) >= 3:
            out[b[0]] = (b[1], b[2], b[3] if len(b) > 3 else "")
    return out


def ringkas() -> int:
    hasil = baca_hasil()
    print("=" * 78)
    print("RINGKASAN UJI-MUTASI FASE 58 (kumulatif) — gate 49 verify_late_fee.py")
    print("=" * 78)
    tertangkap, lolos, lewat, belum = [], [], [], []
    for nama, _p, _c in MUTATIONS:
        kode = nama.split()[0]
        row = hasil.get(kode)
        if not row:
            belum.append(nama)
            print(f"  BELUM      {nama}")
            continue
        status, _n, catatan = row
        print(f"  {status:<10} {nama}" + (f"  [{catatan}]" if catatan else ""))
        {"TERTANGKAP": tertangkap, "LOLOS": lolos,
         "LEWAT": lewat}.get(status, belum).append(nama)
    print("-" * 78)
    print(f"TERTANGKAP: {len(tertangkap)} · LOLOS: {len(lolos)} · LEWAT: {len(lewat)} · "
          f"BELUM DIJALANKAN: {len(belum)} · TOTAL: {len(MUTATIONS)}")
    if lolos:
        print("\nMutasi yang LOLOS (gate harus diperkuat, bukan diabaikan):")
        for e in lolos:
            print(f"   - {e}")
    print("=" * 78)
    return 0 if (not lolos and not lewat and not belum) else 1


def check_patterns() -> int:
    print("=" * 78)
    print("PERIKSA POLA MUTASI FASE 58 (cepat, tanpa menjalankan gate)")
    print("=" * 78)
    bad = []
    for nama, patches, _c in MUTATIONS:
        missing = [f"{p} :: {find[:60]}" for p, find, _r in patches if find not in read(p)]
        print(f"  {'OK    ' if not missing else 'HILANG'} {nama}")
        for m in missing:
            print(f"        - {m}")
        bad += missing
    print("-" * 78)
    print(f"{len(MUTATIONS)} mutasi · {len(bad)} pola hilang")
    return 1 if bad else 0


def selected():
    only, start = None, None
    for arg in sys.argv[1:]:
        if arg.startswith("--only="):
            only = {x.strip().upper() for x in arg.split("=", 1)[1].split(",") if x.strip()}
        elif arg.startswith("--from="):
            start = arg.split("=", 1)[1].strip().upper()
    rows = list(MUTATIONS)
    if only:
        rows = [m for m in rows if m[0].split()[0].upper() in only]
    if start:
        idx = next((i for i, m in enumerate(rows) if m[0].split()[0].upper() == start), 0)
        rows = rows[idx:]
    return rows


def main() -> int:
    if "--check" in sys.argv:
        return check_patterns()
    if "--pulihkan" in sys.argv:
        return pulihkan()
    if "--ringkas" in sys.argv:
        return ringkas()

    rows = selected()
    snapshot()
    print("=" * 78)
    print(f"UJI-MUTASI FASE 58 — {len(rows)} mutan · gate 49 {GATE}")
    print(f"Snapshot kode bersih: {SNAP.relative_to(ROOT)}")
    print("=" * 78)

    if "--tanpa-baseline" not in sys.argv:
        print("\nBASELINE (kode bersih): gate harus HIJAU sebelum mutasi apa pun.")
        ok, _ = run_gate("baseline")
        print(f"  baseline gate: {'HIJAU' if ok else 'MERAH'}")
        if not ok:
            print("  Baseline MERAH — mutasi dihentikan (hasilnya tidak akan berarti).")
            return 1

    for nama, patches, harus_jatuh in rows:
        kode = nama.split()[0]
        print(f"\n--- {nama}")
        butuh_reload = any(p in BACKEND_FILES for p, _f, _r in patches)
        before = server_pids() if butuh_reload else ()
        try:
            backup = apply_patches(patches)
        except RuntimeError as e:
            print(f"  LEWAT — {e}")
            catat_hasil(nama, "LEWAT", str(e)[:80])
            continue
        try:
            if butuh_reload:
                print(f"  {wait_reload(before)}")
            ok, jatuh = run_gate(kode)
            if ok:
                print("  LOLOS — gate tetap HIJAU walau aturannya dimatikan (GATE LEMAH)")
                catat_hasil(nama, "LOLOS", "")
            else:
                tepat = harus_jatuh in jatuh
                print(f"  TERTANGKAP — gate MERAH; jatuh: {','.join(jatuh[:6])}")
                if not tepat:
                    print(f"  (catatan: pemeriksaan {harus_jatuh} yang diharapkan TIDAK "
                          "jatuh — gate menangkapnya lewat jalan lain)")
                catat_hasil(nama, "TERTANGKAP",
                            f"{harus_jatuh}{'' if tepat else ' (lewat jalan lain)'}: "
                            f"{','.join(jatuh[:6])}")
        finally:
            restore(backup)
            if butuh_reload:
                wait_reload(server_pids())

    print()
    return ringkas()


if __name__ == "__main__":
    sys.exit(main())
