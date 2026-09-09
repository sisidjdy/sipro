#!/usr/bin/env python3
"""mutasi_57.py — UJI-MUTASI Fase 57A: membuktikan GATE 48 BERGIGI.

Aturan mainnya sama dengan `mutasi_53.py`/`mutasi_56.py`: aturan Fase 57A dimatikan satu per
satu di kode, lalu `scripts/verify_payment_schemes.py` dijalankan. Gate yang tetap HIJAU
ketika aturannya dimatikan **tidak menguji apa pun** — LOLOS adalah cacat perangkat uji.

Pakai:
    python3 scripts/mutasi_57.py --check      # cepat: pastikan semua pola masih ada
    python3 scripts/mutasi_57.py              # penuh
    python3 scripts/mutasi_57.py --only=M03
    python3 scripts/mutasi_57.py --ringkas
    python3 scripts/mutasi_57.py --pulihkan
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

GATE = "verify_payment_schemes.py"
HEALTH = "http://localhost:8001/api/health"

PS = "backend/payment_scheme_engine.py"
FE_ENG = "backend/finance_engine.py"
CX = "backend/contracts_engine.py"
MD = "backend/models_p57.py"
RT = "backend/routers/payment_scheme_router.py"
PN = "frontend/src/components/config/PaymentSchemePanel.js"
CP = "frontend/src/pages/ConfigCenterPage.js"
PK = "frontend/src/components/contracts/ContractSchemePicker.js"
CTR = "frontend/src/components/contracts/ContractPanel.js"

BACKEND_FILES = {PS, FE_ENG, CX, MD, RT}

MUTATIONS = [
    ("M01 pratinjau menghitung sendiri (bukan mesin termin yang menagih)", [
        (PS, "    items = fin.compute_scheme_items(scheme, price, base_date or now_iso())",
             "    items = [{**t, \"amount\": 0, \"due_date\": now_iso()} "
             "for t in (scheme.get('items') or [])]")], "K1"),
    ("M02 dasar 'sisa harga' tidak menutup selisih", [
        (FE_ENG, '        if basis == "remaining":\n'
                 '            amt = max(0, int(price) - sum(x["amount"] for x in out))',
                 '        if basis == "remaining":\n            amt = 0')], "K2"),
    ("M03 tanggal cicilan bulanan diabaikan (kembali ke hitung hari)", [
        (FE_ENG, '    if mode == "monthly_day":', "    if False:")], "K3"),
    ("M04 skema yang persennya bukan 100% diterima", [
        (PS, "        elif abs(pct - 100) > 0.01:", "        elif False:")], "K4"),
    ("M05 dua termin 'sisa harga' diterima (yang kedua selalu Rp 0)", [
        (PS, "    if len(sisa_idx) > 1:", "    if False:")], "D2e"),
    ("M06 campuran nominal tanpa termin 'sisa harga' diterima", [
        (PS, '        if ada_nominal:\n            out.append(_blk("nominal_tanpa_sisa",',
             '        if False:\n            out.append(_blk("nominal_tanpa_sisa",')], "K4c"),
    ("M07 termin bernilai nol diterima (tagihan yang tidak menagih)", [
        (PS, '        if r["basis"] != "remaining" and r["value"] <= 0:',
             "        if False:")], "D2f"),
    ("M08 sebab penolakan tidak terdaftar di Kamus Data", [
        (PS, '    if len(sisa_idx) > 1:\n        out.append(_blk("sisa_ganda"',
             '    if len(sisa_idx) > 1:\n        out.append(_blk("sisa_dobel"')], "K5"),
    ("M09 kalimat jatuh tempo peristiwa berpura-pura tanggal pasti", [
        (PS, '        return f"{peristiwa.lower()}{jeda}{ekor} — tanggal pada jadwal masih '
             'perkiraan"',
             '        return f"{peristiwa.lower()}{jeda}{ekor}"')], "K6"),
    ("M10 termin tidak lagi membawa kalimat aturan dari mesin", [
        (PS, '        row["due_rule"] = due_sentence(row)',
             '        row["due_rule"] = t.get("due_rule") or ""')], "K6b"),
    ("M11 skema bawaan MENIMPA suntingan pemakai saat kontrak diaktifkan", [
        (CX, "    doc = await db.payment_schemes.find_one({\"org_id\": org, \"code\": scheme}, "
             "{\"_id\": 0})\n    if doc:\n        return doc",
             "    doc = await db.payment_schemes.find_one({\"org_id\": org, \"code\": scheme}, "
             "{\"_id\": 0})\n    if doc and False:\n        return doc")], "K7"),
    ("M12 kontrak berhenti membaca skema tersimpan (kembali ke termin dalam kode)", [
        (CX, "    if contract is not None:\n        hasil = await psx.resolve_for_contract(",
             "    if False:\n        hasil = await psx.resolve_for_contract(")], "K7b"),
    ("M13 tidak ada skema cocok dijawab termin karangan tanpa sebab", [
        (PS, '    return {"scheme": None, "source": None,\n'
             '            "reason": (f"Belum ada skema pembayaran aktif berjenis "',
             '    return {"scheme": None, "source": None,\n'
             '            "reason": (f"" or (f"Belum ada skema pembayaran aktif berjenis "')],
     None),
    ("M14 skema yang dipakai kontrak beruang bisa diubah diam-diam", [
        (PS, "        if terpakai and items != (lama.get(\"items\") or []):",
             "        if False:")], "D9b"),
    ("M15 jenis skema tidak diperiksa (akad kredit muncul di kontrak tunai)", [
        (PS, '    if doc.get("kind") != contract.get("scheme"):', "    if False:")], "K9"),
    ("M16 skema di luar proyek kontrak diterima", [
        (PS, "    if proyek and contract.get(\"project_id\") not in proyek:",
             "    if False:")], "D7e"),
    ("M17 kontrak yang sudah dibayar boleh ganti skema (jadwal ditulis ulang)", [
        (PS, '    if int((inv or {}).get("paid") or 0) > 0:\n'
             '        raise ValueError(\n'
             '            f"Sudah ada penerimaan',
             '    if False:\n        raise ValueError(\n            f"Sudah ada penerimaan')],
     "K9c"),
    ("M18 menetapkan skema pada kontrak memakai izin yang sama dengan menyusunnya", [
        (RT, 'require_permission("payment_scheme", "assign")',
             'require_permission("payment_scheme", "create")')], "K10"),
    ("M19 penggantian skema kontrak tanpa alasan", [
        (MD, "MIN_REASON = 10", "MIN_REASON = 0")], "K10b"),
    ("M20 tanggal jatuh tempo 31 diterima (Februari membuat tagihan meleset)", [
        (MD, "        if v is not None and not (1 <= int(v) <= 28):", "        if False:")],
     "K11"),
    ("M21 sisa pembulatan cicilan hilang (jumlah persen tidak tepat)", [
        (PS, "        nilai = per if i < count - 1 else round(float(percent_total) - "
             "per * (count - 1), 4)",
             "        nilai = per")], "K12"),
    # ------------------------------------------------------------------ layar
    ("M22 tab 'Skema Pembayaran' dicabut dari Pusat Konfigurasi", [
        (CP, '        <TabsContent value="scheme"><PaymentSchemePanel /></TabsContent>\n', "")],
     "K13"),
    ("M23 skema yang dipakai kontrak disembunyikan dari layar", [
        (CTR, "        <ContractSchemePicker contract={contract} onChanged={refresh} />\n", "")],
     "K13b"),
    ("M24 pilihan editor diketik layar (bukan dari Kamus Data)", [
        (PN, '<ReferenceSelect group="term_basis" value={t.basis} testId={P57.termBasis}',
             '<ReferenceSelect group="uom" value={t.basis} testId={P57.termBasis}')], "K15"),
    ("M25 tombol simpan tetap hidup walau pratinjau menyebut penolakan", [
        (PN, 'disabled={!!(preview?.blocks || []).length}', "disabled={false}")], "K16b"),
    ("M26 termin yang masih diisi dilaporkan sebagai galat teknis", [
        (PN, '        note: "Beri nama setiap termin dahulu — pratinjau menunggu itu." });',
             '        note: "terms.0.label: validation error" });')], "K16d"),
    ("M27 layar tidak lagi mengaku memakai termin BAWAAN sistem", [
        (PK, "            {\" \"}· belum ada skema tersimpan untuk jenis ini, sistem memakai "
             "termin bawaan", "            {\" \"}· skema aktif")], "K17"),
    ("M28 sebab skema tidak bisa diganti disembunyikan (tombol diam)", [
        (PK, "              Sudah ada penerimaan pada kontrak ini. Mengganti skema akan "
             "menyusun ulang", "              Tidak dapat diganti. Mengganti skema akan "
             "menyusun ulang")], "K17b"),
]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def write(rel: str, src: str) -> None:
    (ROOT / rel).write_text(src, encoding="utf-8")


def apply_patches(patches) -> dict:
    backup = {}
    for path, find, repl in patches:
        src = read(path)
        backup.setdefault(path, src)
        if find not in src:
            raise RuntimeError(f"pola tidak ditemukan di {path}: {find[:70]}")
        write(path, src.replace(find, repl, 1))
    return backup


def restore(backup: dict) -> None:
    for path, src in backup.items():
        write(path, src)


SNAP = ROOT / "memory" / "mutasi57_snapshot"


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
        print("Tidak ada snapshot kode.")
        return 0
    n = 0
    for rel in files_touched():
        src = SNAP / rel.replace("/", "__")
        if src.exists() and src.read_text(encoding="utf-8") != read(rel):
            write(rel, src.read_text(encoding="utf-8"))
            print(f"  dipulihkan  {rel}")
            n += 1
    print(f"{n} berkas dipulihkan.")
    return 0


def server_pids() -> tuple:
    induk = subprocess.run(["pgrep", "-f", "uvicorn server:app"],
                           capture_output=True, text=True)
    pids = []
    for p in induk.stdout.split():
        if p.strip().isdigit():
            anak = subprocess.run(["pgrep", "-P", p.strip()], capture_output=True, text=True)
            pids += [int(x) for x in anak.stdout.split() if x.strip().isdigit()]
    return tuple(sorted(pids))


def health_ok() -> bool:
    try:
        return requests.get(HEALTH, timeout=3).status_code == 200
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
            return (f"reload {time.time() - mulai:.0f}s" if ganti
                    else f"TANPA reload terdeteksi ({time.time() - mulai:.0f}s)")
        time.sleep(0.5)
    return "backend TIDAK sehat setelah menunggu"


def run_gate(tag: str) -> tuple:
    logdir = ROOT / "memory" / "gatelogs"
    logdir.mkdir(parents=True, exist_ok=True)
    log = logdir / f"mut57_{tag}.log"
    with log.open("w", encoding="utf-8") as fh:
        p = subprocess.run([sys.executable, str(ROOT / "scripts" / GATE)],
                           stdout=fh, stderr=subprocess.STDOUT, cwd=str(ROOT))
    isi = log.read_text(encoding="utf-8", errors="ignore")
    jatuh = [ln.strip()[6:].split()[0] for ln in isi.splitlines()
             if ln.strip().startswith("MERAH")]
    return p.returncode == 0, jatuh


HASIL = ROOT / "memory" / "gatelogs" / "mutasi_57_hasil.tsv"


def catat(nama: str, hasil: str, catatan: str = "") -> None:
    HASIL.parent.mkdir(parents=True, exist_ok=True)
    with HASIL.open("a", encoding="utf-8") as fh:
        fh.write(f"{nama.split()[0]}\t{hasil}\t{nama}\t{catatan}\n")


def baca() -> dict:
    if not HASIL.exists():
        return {}
    out = {}
    for line in HASIL.read_text(encoding="utf-8").splitlines():
        b = line.split("\t")
        if len(b) >= 3:
            out[b[0]] = (b[1], b[2], b[3] if len(b) > 3 else "")
    return out


def ringkas() -> int:
    hasil = baca()
    print("=" * 78)
    print("RINGKASAN UJI-MUTASI FASE 57A — gate 48 verify_payment_schemes.py")
    print("=" * 78)
    tertangkap, lolos, lewat, belum = [], [], [], []
    for nama, _p, _c in MUTATIONS:
        row = hasil.get(nama.split()[0])
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
          f"BELUM: {len(belum)} · TOTAL: {len(MUTATIONS)}")
    if lolos:
        print("\nMutasi yang LOLOS (gate harus diperkuat):")
        for e in lolos:
            print(f"   - {e}")
    return 0 if (not lolos and not lewat and not belum) else 1


def check_patterns() -> int:
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
    print(f"UJI-MUTASI FASE 57A — {len(rows)} mutan · gate 48 {GATE}")
    print("=" * 78)
    if "--tanpa-baseline" not in sys.argv:
        ok, _ = run_gate("baseline")
        print(f"baseline gate: {'HIJAU' if ok else 'MERAH'}")
        if not ok:
            print("Baseline MERAH — mutasi dihentikan.")
            return 1
    for nama, patches, harus in rows:
        kode = nama.split()[0]
        print(f"\n--- {nama}")
        butuh_reload = any(p in BACKEND_FILES for p, _f, _r in patches)
        before = server_pids() if butuh_reload else ()
        try:
            backup = apply_patches(patches)
        except RuntimeError as e:
            print(f"  LEWAT — {e}")
            catat(nama, "LEWAT", str(e)[:80])
            continue
        try:
            if butuh_reload:
                print(f"  {wait_reload(before)}")
            ok, jatuh = run_gate(kode)
            if ok:
                print("  LOLOS — gate tetap HIJAU walau aturannya dimatikan (GATE LEMAH)")
                catat(nama, "LOLOS", "")
            else:
                tepat = (harus in jatuh) if harus else True
                print(f"  TERTANGKAP — gate MERAH; jatuh: {','.join(jatuh[:6])}")
                catat(nama, "TERTANGKAP",
                      f"{harus or '-'}{'' if tepat else ' (lewat jalan lain)'}: "
                      f"{','.join(jatuh[:6])}")
        finally:
            restore(backup)
            if butuh_reload:
                wait_reload(server_pids())
    print()
    return ringkas()


if __name__ == "__main__":
    sys.exit(main())
