#!/usr/bin/env python3
"""mutasi_56.py — UJI-MUTASI Fase 56: membuktikan GATE 47 BERGIGI.

Cara kerja: satu per satu aturan Fase 56C dimatikan di kode (mutan), lalu
`scripts/verify_cancellation_refund.py` dijalankan. Gate yang tetap HIJAU ketika aturannya
dimatikan berarti gate itu tidak menguji apa pun — **LOLOS adalah cacat perangkat uji**,
bukan kelulusan produk. Pelajaran ini dibeli mahal di Fase 55 (`mutasi_53.py`): versi pertama
gate 46 hijau pada percobaan pertama, dan sembilan pemeriksaannya ternyata tidak menguji
apa-apa.

Yang dimutasi di sini adalah janji-janji yang ditandatangani pembeli di dokumen SPR:
  * potongan dibaca dari Pusat Konfigurasi & keadaan pembangunan NYATA (bukan angka karangan);
  * uang yang dikembalikan dibaca dari saldo kewajiban kontrak, bukan hitungan kedua;
  * "belum ada penerimaan" adalah KALIMAT, bukan Rp 0 tanpa sebab;
  * pengaju ≠ pemutus, dan tiap peran punya izinnya sendiri;
  * jurnal berimbang (uang muka diselesaikan, potongan jadi pendapatan, sisanya UTANG refund);
  * unit kembali ke stok secara ATOMIK dan meninggalkan jejak;
  * refund idempoten, tidak bisa melebihi sisa, dan penahanan SPR hanya boleh diabaikan
    Manajer Keuangan dengan alasan tertulis;
  * layar & portal tidak mengarang label, tidak menyembunyikan sebab, tidak membocorkan
    nomor akun, dan panel-panelnya benar-benar DIRENDER (bukan komponen mati).

Pakai:
    python3 scripts/mutasi_56.py --check           # cepat: pastikan semua pola masih ada
    python3 scripts/mutasi_56.py                   # penuh
    python3 scripts/mutasi_56.py --only=M01,M12    # sebagian
    python3 scripts/mutasi_56.py --from=M20        # lanjutkan run yang terputus
    python3 scripts/mutasi_56.py --ringkas         # laporan kumulatif
    python3 scripts/mutasi_56.py --pulihkan        # kembalikan kode & data bila run terputus
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

GATE = "verify_cancellation_refund.py"       # gate 47
HEALTH = "http://localhost:8001/api/health"

CX = "backend/cancellation_engine.py"
RT = "backend/routers/cancellation_router.py"
PT = "backend/routers/portal_router.py"
MD = "backend/models_p56.py"
PN = "frontend/src/components/contracts/CancellationPanel.js"
CP = "frontend/src/components/contracts/ContractPanel.js"
FP = "frontend/src/pages/FinancePage.js"
FC = "frontend/src/components/finance/CancellationsPanel.js"
PD = "frontend/src/components/portal/PortalDashboard.js"
PP = "frontend/src/components/portal/panels/CancellationPanel.js"
PL = "frontend/src/components/customers/CustomerPaymentPlanTab.js"
IDS = "frontend/src/constants/testIds/p56.js"

# Berkas backend memicu reload uvicorn; berkas frontend diperiksa gate secara STATIS
# sehingga mutannya tidak perlu menunggu backend (memotong waktu run secara nyata).
BACKEND_FILES = {CX, RT, PT, MD}

# (nama, [(berkas, cari, ganti), ...], pemeriksaan yang HARUS jatuh)
MUTATIONS = [
    # ============================================== hitungan: aturan SPR & keadaan nyata
    ("M01 persentase potongan ditanam di kode (bukan dari Pusat Konfigurasi)", [
        (CX, "    pct = int(await cfg.get(key, org_id=org) or 0)", "    pct = 35")], "K2"),
    ("M02 keadaan pembangunan unit diabaikan (dasar potongan dikarang)", [
        (CX, '    status = str(unit.get("construction_status") or "not_started")\n'
             '    progress = int(unit.get("construction_progress") or 0)',
             '    status = "not_started"\n    progress = 0')], "K3"),
    ("M03 uang diterima tidak dibaca dari saldo kewajiban kontrak", [
        (CX, '    received = max(0, int(liab.get("balance") or 0))',
             "    received = 0")], "D5"),
    ("M04 'belum ada penerimaan' menjadi Rp 0 tanpa sebab", [
        (CX, '        "note": ("Belum ada penerimaan yang tercatat pada kontrak ini, '
             'jadi tidak ada "\n                 "potongan maupun dana yang dikembalikan." '
             'if received + deposit == 0 else',
             '        "note": ("" if received + deposit == 0 else')], "K4b"),
    ("M05 nominal yang belum diketahui dicetak Rp 0 di dokumen", [
        (CX, '    if v is None:\n        return "belum ditetapkan"',
             "    if v is None:\n        return \"Rp 0\"")], "K4c"),

    # ============================================== pemisahan tugas & niat vs peristiwa
    ("M06 pengaju boleh memutuskan pengajuannya sendiri", [
        (CX, '    if cancel.get("requested_by") == actor:', "    if False:")], "K7"),
    ("M07 satu pengajuan bisa diputus dua kali", [
        (CX, '    if cancel["state"] != "diajukan":', "    if False:")], "K7b"),
    ("M08 keputusan memakai hitungan LAMA (tidak dihitung ulang)", [
        (CX, "    hitung = await compute(org, contract)\n"
             "    journal_ids = await _post_decision_journal",
             '    hitung = cancel["basis_at_request"]\n'
             "    journal_ids = await _post_decision_journal")], "K8b"),
    ("M09 pengajuan ganda tidak ditahan", [
        (CX, "    if open_doc:\n        out.append(_blk(\"pengajuan_berjalan\",",
             "    if False:\n        out.append(_blk(\"pengajuan_berjalan\",")], "D9b"),

    # ============================================== jurnal
    ("M10 potongan tidak dibukukan (jurnal tidak berimbang)", [
        (CX, '    if hitung["cut_amount"] > 0:\n'
             '        lines.append({"account_code": AKUN_POTONGAN',
             '    if False:\n        lines.append({"account_code": AKUN_POTONGAN')], "D12b"),
    ("M11 utang refund kepada pembeli tidak dibukukan", [
        (CX, '    if hitung["payable_total"] > 0:\n'
             '        lines.append({"account_code": AKUN_UTANG_REFUND',
             '    if False:\n        lines.append({"account_code": AKUN_UTANG_REFUND')],
     "D12b"),
    ("M12 utang refund dibukukan ke akun POTONGAN (uang pembeli hilang jejak)", [
        (CX, 'AKUN_UTANG_REFUND = "2-1460"', 'AKUN_UTANG_REFUND = "4-1200"')], "D12b"),

    # ============================================== unit tidak boleh hilang
    ("M13 unit tidak dilepas kembali ke stok", [
        (CX, "    released = await _release_unit(org, cancel, actor)",
             "    released = False")], "D14"),
    ("M14 pelepasan unit TIDAK atomik (unit deal lain bisa ikut dilepas)", [
        (CX, '        {"id": cancel["unit_id"], "org_id": org,\n'
             '         "$or": [{"booked_by_deal": cancel["deal_id"]},\n'
             '                 {"reserved_by_deal": cancel["deal_id"]},\n'
             '                 {"sold_by_deal": cancel["deal_id"]},\n'
             '                 {"deal_id": cancel["deal_id"]}]},',
             '        {"id": cancel["unit_id"], "org_id": org},')], "K10"),
    ("M15 pelepasan unit tidak meninggalkan jejak di riwayat unit", [
        (CX, '         "$push": {"status_history": {\n'
             '             "status": "available", "at": ts, "actor": actor,\n'
             '             "note": (f"Dilepas kembali ke stok karena pembatalan '
             '{cancel[\'number\']}: "\n'
             '                      f"{cancel.get(\'reason\')}")}}})',
             "         })")], "K10b"),

    # ============================================== refund: idempoten & berbatas
    ("M16 idempotensi `client_ref` dimatikan (bisa dibayar dua kali)", [
        (CX, "    if client_ref:\n"
             '        for p in cancel.get("refund_payments") or []:',
             "    if False:\n"
             '        for p in cancel.get("refund_payments") or []:')], "D19"),
    ("M17 pembayaran boleh MELEBIHI sisa utang refund", [
        (CX, "    if amount > sisa:", "    if False:")], "K12"),
    ("M18 penahanan refund bisa diabaikan siapa saja (bukan hanya Manajer Keuangan)", [
        (CX, "        if not may_override:", "        if False:")], "K13"),
    ("M19 alasan pengabaian tanpa batas huruf", [
        (CX, '        if len((override_reason or "").strip()) < 10:',
             "        if False:")], "K13"),
    ("M20 penahanan 'menunggu penjualan ulang' dimatikan (janji SPR diabaikan)", [
        (CX, "        if not terjual_ulang:", "        if False:")], "D17"),
    ("M21 urutan sebab dibalik: refund LUNAS dijawab 'belum disetujui'", [
        (CX, '    if int(cancel.get("refund_paid_total") or 0) >= payable > 0:',
             "    if False:")], "K14"),

    # ============================================== SSOT label & kode
    ("M22 sebab penahanan memakai KODE mentah sebagai label", [
        (CX, '    return {"code": code, "label": ref.label_of("cancel_block", code), '
             '"detail": detail}',
             '    return {"code": code, "label": code, "detail": detail}')], "K6c"),
    ("M23 kode penahan baru tidak didaftarkan di Kamus Data", [
        (CX, '        out.append(_blk("sudah_bast",', '        out.append(_blk("bast_done",')],
     "K5"),
    ("M24 batas alasan 10 huruf dicabut di lapis model", [
        (MD, "MIN_REASON = 10", "MIN_REASON = 0")], "K15"),

    # ============================================== router & portal
    ("M25 membayar refund memakai izin PEMUTUS (pemisahan tugas kabur)", [
        (RT, 'user: dict = Depends(require_permission("cancellation", "update"))):',
             'user: dict = Depends(require_permission("cancellation", "approve"))):')],
     "K16"),
    ("M26 lingkup data sales dimatikan (pembatalan rekan ikut terlihat)", [
        (RT, "    if is_scoped_sales(user):\n        milik = [r for r in out[\"data\"]",
             "    if False:\n        milik = [r for r in out[\"data\"]")], "K16c"),
    ("M27 portal berhenti memakai mesin (pembeli & staf bisa beda angka)", [
        (PT, '    out = await cx.portal_rows(pu.get("org_id", ORG_ID), '
             '[d["id"] for d in deals])',
             '    out = {"data": [], "reason": None}')], "K17"),

    # ============================================== layar: dirender, jujur, tanpa akun
    ("M28 panel pembatalan dicabut dari layar Kontrak & Legal", [
        (CP, "      <CancellationPanel contract={contract} onChanged={refresh} />\n", "")],
     "K18"),
    ("M29 tab 'Pembatalan & Refund' dicabut dari Keuangan", [
        (FP, '        <TabsContent value="cancellations" className="mt-4">'
             "<CancellationsPanel /></TabsContent>\n", "")], "K19"),
    ("M30 tab Keuangan tidak lagi hidup di URL (?tab=cancellations)", [
        (FP, '"bank", "labor", "cancellations", "reports", "config"',
             '"bank", "labor", "reports", "config"')], "K19"),
    ("M31 tab portal pembeli menjadi komponen MATI", [
        (PD, "Comp: CancellationPanel }", "Comp: OverviewPanel }")], "K20"),
    ("M32 daftar Keuangan mengetik label keadaan sendiri (SSOT bercabang)", [
        (FC, '<StatusPill status={r.state} group="cancel_state" />',
             "<StatusPill status={r.state} />")], "K22"),
    ("M32b pengajuan yang belum diputus ditulis 'Rp 0' (utang refund belum lahir)", [
        (FC, "                      {r.settlement ? (\n", "                      {true ? (\n")],
     "K22a"),
    ("M33 portal berhenti menyebut DASAR ATURAN potongan", [
        (PP, "          {r.rule_label ? (\n"
             '            <p className="mt-1 text-xs text-slate-500">{r.rule_label}</p>\n'
             "          ) : null}\n", "")], "K22b"),
    ("M34 nomor akun bocor ke mata PEMBELI", [
        (PP, '<p className="text-xs text-emerald-700">Yang dikembalikan kepada Anda</p>',
             '<p className="text-xs text-emerald-700">Dikembalikan (akun 2-1460)</p>')],
     "K23"),
    ("M35 dokumen portal dibuka lewat tautan mentah bertoken", [
        (PP, "      await portalDownload(`/portal/documents/${r.document_id}/pdf`,\n"
             '        { fallbackName: r.document_number || "berita-acara-pembatalan", '
             "open: true });",
             "      window.open(`/api/portal/documents/${r.document_id}/pdf`);")], "K23b"),
    ("M36 layar berhenti menyebut SEBAB pembatalan belum boleh", [
        (PN, "            {pre.blocks.map((b) => <li key={b.code}>• {b.detail}</li>)}\n", "")],
     "K24"),
    ("M37 tombol bayar refund tanpa penanda sekali-pakai (klik ganda bisa dobel)", [
        (PN, "        client_ref: `ui-${refundFor.id}-${Date.now()}`,\n", "")], "K24b"),
    ("M38 layar kembali mengaku mesin pembatalan/refund 'belum ada'", [
        (PL, "Pembatalan &amp; pengembalian dana <b>sudah berjurnal</b>",
             "<b>mesin pembatalan/refund berjurnal</b> belum ada")], "K25"),
    ("M39 testId Fase 56 menjadi MATI (terdaftar tetapi tidak lagi dipakai layar)", [
        (PP, "            <p data-testid={P56.portalWaiting}\n", "            <p\n")], "K21"),
    ("M40 riwayat pratinjau dikembalikan MENTAH (layar kehilangan sebab penahanan)", [
        (CX, '        "history": [await enrich(org, r) for r in riwayat],',
             '        "history": riwayat,')], "K17c"),
    ("M41 panel portal memanggil jalur STAF (401 → pembeli terlempar keluar)", [
        (PP, 'portalApi.get("/portal/cancellations")',
             'portalApi.get("/cancellations")')], "K23c"),
    ("M42 subledger kewajiban kontrak tidak ditutup (buku besar ≠ subledger)", [
        (CX, '    if hitung["received_total"] > 0:\n'
             "        # Cermin subledger dari `Dr 2-1400` pada jurnal keputusan",
             "    if False:\n"
             "        # Cermin subledger dari `Dr 2-1400` pada jurnal keputusan")], "K10f"),
    ("M43 tagihan yang SUDAH LUNAS ikut ditandai 'dibatalkan'", [
        (CX, "    if dibatalkan:\n"
             '        ubah.update({"status": "cancelled", "outstanding": 0, '
             '"cancelled_at": ts})',
             '    ubah.update({"status": "cancelled", "outstanding": 0, '
             '"cancelled_at": ts})')], "K10e"),
    ("M44 penahanan hilang karena tautan deal BASI dibaca sebagai pembeli baru", [
        (CX, '        terjual_ulang = (str(unit.get("status") or "") not in ("available", "")\n'
             '                         and bool(unit.get("reserved_by_deal") '
             'or unit.get("booked_by_deal")\n'
             '                                  or unit.get("deal_id"))\n'
             '                         and unit.get("deal_id") != cancel.get("deal_id")\n'
             '                         and unit.get("booked_by_deal") != '
             'cancel.get("deal_id")\n'
             '                         and unit.get("reserved_by_deal") != '
             'cancel.get("deal_id"))',
             '        terjual_ulang = bool(unit.get("reserved_by_deal") '
             'or unit.get("booked_by_deal")\n'
             '                             or unit.get("deal_id"))')], "K14c"),
    ("M45 penyaringan daftar Keuangan dikerjakan di PERAMBAN (baris yang dicari tersembunyi)", [
        (FC, "        ...(filter.state !== \"semua\" ? { state: filter.state } : {}),\n"
             "        ...(filter.q ? { q: filter.q } : {}),\n", "")], "K22q"),
    ("M46 daftar kosong karena saringan tidak dijelaskan sebabnya", [
        (FC, '            description={menyaring\n'
             '              ? "Kosongnya daftar ini karena saringan, bukan karena tidak ada '
             'pembatalan. "\n'
             '                + "Bersihkan saringan untuk melihat semuanya."\n'
             "              : (state.reason",
             "            description={(state.reason")], "K22r"),
    ("M47 unit yang kembali ke stok masih menyimpan tautan PENJUALAN (mengaku terjual)", [
        (CX, '        {"$set": {"status": "available", "reserved_by_deal": None, '
             '"booked_by_deal": None,\n'
             '                  "sold_by_deal": None, "sold_at": None,\n',
             '        {"$set": {"status": "available", "reserved_by_deal": None, '
             '"booked_by_deal": None,\n')], "K10b2"),
    ("M48 unit yang tertaut HANYA lewat penjualan tidak bisa dilepas ke stok", [
        (CX, '                 {"sold_by_deal": cancel["deal_id"]},\n', "")], "K10b3"),
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
SNAP = ROOT / "memory" / "mutasi56_snapshot"


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
    import _fixture56
    print(f"Bahan uji pembatalan dibuang: {_fixture56.purge()}")
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
    log = logdir / f"mut56_{tag}.log"
    with log.open("w", encoding="utf-8") as fh:
        p = subprocess.run([sys.executable, str(ROOT / "scripts" / GATE)],
                           stdout=fh, stderr=subprocess.STDOUT, cwd=str(ROOT))
    isi = log.read_text(encoding="utf-8", errors="ignore")
    jatuh = [ln.strip()[6:].split()[0] for ln in isi.splitlines()
             if ln.strip().startswith("MERAH")]
    return p.returncode == 0, jatuh


HASIL = ROOT / "memory" / "gatelogs" / "mutasi_56_hasil.tsv"


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
    print("RINGKASAN UJI-MUTASI FASE 56 (kumulatif) — gate 47 verify_cancellation_refund.py")
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
    print("PERIKSA POLA MUTASI FASE 56 (cepat, tanpa menjalankan gate)")
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
    print(f"UJI-MUTASI FASE 56 — {len(rows)} mutan · gate 47 {GATE}")
    print(f"Snapshot kode bersih: {SNAP.relative_to(ROOT)}")
    print("=" * 78)

    if "--tanpa-baseline" not in sys.argv:
        print("\nBASELINE (kode bersih): gate harus HIJAU sebelum mutasi apa pun.")
        ok, _ = run_gate("baseline")
        print(f"  baseline gate: {'HIJAU' if ok else 'MERAH'}")
        if not ok:
            print("  Baseline MERAH — mutasi dihentikan (hasilnya tidak akan berarti).")
            return 1

    import _fixture56
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
            _fixture56.purge()

    print()
    return ringkas()


if __name__ == "__main__":
    sys.exit(main())
