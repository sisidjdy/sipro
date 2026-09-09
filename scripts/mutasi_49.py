#!/usr/bin/env python3
"""mutasi_49.py — UJI-MUTASI Fase 49: membuktikan gate 37 & 38 BERGIGI.

Cara kerja: satu per satu aturan dimatikan di kode (mutan), gate yang bersangkutan
dijalankan, lalu kode dipulihkan. Gate yang tetap HIJAU saat aturannya dimatikan berarti gate
itu tidak menguji apa pun (LOLOS = cacat perangkat uji, bukan kelulusan).

Pelajaran fase sebelumnya yang dipakai lagi:
  * **Matikan lapis yang BENAR.** Panjang alasan dijaga di kontrak permintaan (`models_p49`),
    izin dijaga di router, dan akibat pembukuannya di mesin. Mematikan lapis yang salah
    menghasilkan mutan ekuivalen yang membuat gate tampak longgar padahal tidak.
  * **Baseline dulu.** Bila gate sudah merah sebelum dirusak, hasil mutasi tidak berarti.
  * **Selalu pulihkan.** Kode dikembalikan walau gate gagal/putus di tengah jalan, lalu
    baseline diperiksa ulang di akhir.
"""
import pathlib
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
G_CLOSE = "verify_closing.py"
G_TAX = "verify_tax_compliance.py"

# (nama, gate, [(berkas, cari, ganti), ...])
MUTATIONS = [
    # ------------------------------------------------ 49A/49B penutupan buku
    ("M01 penutupan periode tidak lagi MENAHAN daftar periksa yang gagal", G_CLOSE, [
        ("backend/closing_engine.py",
         "    if blocking and not override:\n"
         '        raise ClosingHold([i["detail"] for i in blocking], blocking)',
         "    if False:\n"
         '        raise ClosingHold([i["detail"] for i in blocking], blocking)')]),
    ("M02 siapa pun boleh MENEROBOS daftar periksa (izin dimatikan)", G_CLOSE, [
        ("backend/routers/gl_reports_router.py",
         '        if not await can(user.get("role"), "gl", "close_override"):',
         "        if False:")]),
    ("M03 alasan terobosan < 10 huruf diterima (kontrak permintaan dimatikan)", G_CLOSE, [
        ("backend/models_p49.py",
         "    @field_validator(\"override_reason\")\n    @classmethod\n"
         "    def _reason(cls, v):\n        if v is not None and len(v.strip()) < 10:",
         "    @field_validator(\"override_reason\")\n    @classmethod\n"
         "    def _reason(cls, v):\n        if False:")]),
    ("M04 mutasi bank tanggal TERAKHIR bulan lolos (off-by-one kembali)", G_CLOSE, [
        ("backend/closing_engine.py",
         '        {"org_id": org, "date": {"$gte": start[:10], "$lt": end[:10]},\n'
         '         "match_state": {"$nin": ["matched", "ignored"]}},',
         '        {"org_id": org, "date": {"$gte": start[:10], "$lt": start[:8] + "31"},\n'
         '         "match_state": {"$nin": ["matched", "ignored"]}},')]),
    ("M05 terobosan tidak melahirkan TUGAS tinjauan (hanya catatan)", G_CLOSE, [
        ("backend/closing_engine.py",
         "    if blocking and override:\n        await auto_create_task(",
         "    if False:\n        await auto_create_task(")]),
    ("M06 periode tertutup tetap menerima jurnal manual", G_CLOSE, [
        ("backend/gl_periods.py",
         "    if not auto:\n        raise ValueError(",
         "    if False:\n        raise ValueError(")]),
    ("M07 tutup tahun kedua kali TIDAK idempoten", G_CLOSE, [
        ("backend/closing_engine.py",
         '    if existing and existing.get("state") == "closed":\n'
         '        return {**existing, "idempotent": True}',
         "    if False:\n"
         '        return {**existing, "idempotent": True}')]),
    ("M08 buka tahun tidak menyimpan jejak jurnal pembalik", G_CLOSE, [
        ("backend/closing_engine.py",
         '        "reversal_entry_id": rev["id"], "reversal_entry_no": rev.get("entry_no"),',
         '        "reversal_entry_id": None, "reversal_entry_no": None,')]),
    ("M09 alasan buka tahun < 10 huruf diterima", G_CLOSE, [
        ("backend/models_p49.py",
         "    def _reason(cls, v):\n        if v is not None and len(v.strip()) < 10:\n"
         '            raise ValueError("Alasan minimal 10 huruf — buka kembali tahun buku',
         "    def _reason(cls, v):\n        if False:\n"
         '            raise ValueError("Alasan minimal 10 huruf — buka kembali tahun buku')]),
    ("M10 baris 'tidak teralokasi' disembunyikan dari arus kas per proyek", G_CLOSE, [
        ("backend/gl_project_cash.py",
         "    unassigned = rows.get(None)",
         "    unassigned = None")]),
    ("M11 laporan owner tidak mengaku bagian yang belum ada datanya", G_CLOSE, [
        ("backend/owner_pack.py",
         '    if not pl.get("total_revenue") and not pl.get("total_expense"):\n'
         '        missing.append("laba_rugi")',
         "    if False:\n"
         '        missing.append("laba_rugi")')]),
    # ------------------------------------------------ 49E/49F/49G pajak
    ("M12 ekspor e-Faktur tidak ditahan walau NPWP perusahaan kosong", G_TAX, [
        ("backend/tax_faktur_export.py",
         '    if not company["npwp_state"]["ok"]:',
         "    if False:")]),
    ("M13 unduhan berkas tidak memeriksa tahanan (berkas berkolom kosong lolos)", G_TAX, [
        ("backend/tax_faktur_export.py",
         '    chk = await export_check(org_id, period)\n    if chk["blocking"]:',
         "    chk = await export_check(org_id, period)\n    if False:")]),
    ("M14 faktur yang identitas pembelinya kurang tidak disebut di daftar tahanan", G_TAX, [
        ("backend/tax_faktur_export.py",
         '    for r in rows:\n        if not r["npwp_ok"]:',
         "    for r in rows:\n        if False:")]),
    ("M15 faktur pengganti tidak memakai kode status pengganti", G_TAX, [
        ("backend/tax_faktur_export.py",
         '    new_code = code[:2] + "1"  # status faktur 1 = pengganti (skema DJP)',
         "    new_code = code")]),
    ("M16 faktur yang sudah DIBATALKAN masih bisa diganti", G_TAX, [
        ("backend/tax_faktur_export.py",
         '    if status == "cancelled":\n        raise ValueError("Faktur yang sudah DIBATALKAN',
         '    if False:\n        raise ValueError("Faktur yang sudah DIBATALKAN')]),
    ("M17 faktur bisa dibatalkan dua kali", G_TAX, [
        ("backend/tax_faktur_export.py",
         '    if status == "cancelled":\n        raise ValueError("Faktur ini sudah dibatalkan.")',
         '    if False:\n        raise ValueError("Faktur ini sudah dibatalkan.")')]),
    ("M18 faktur batal & diganti ikut dihitung sebagai PPN keluaran", G_TAX, [
        ("backend/tax_faktur_export.py",
         '        "ppn": sum(int(r.get("ppn", 0) or 0) for r in active),',
         '        "ppn": sum(int(r.get("ppn", 0) or 0) for r in rows),')]),
    ("M19 potongan PPh yang menghabiskan seluruh pembayaran diterima", G_TAX, [
        ("backend/finance_engine.py",
         "    if withheld >= amount:",
         "    if False:")]),
    ("M20 potongan PPh tidak dicatat sebagai UTANG PAJAK (kas keluar bruto)", G_TAX, [
        ("backend/gl_engine.py",
         "    if withheld > 0:\n        lines.append(",
         "    if False:\n        lines.append(")]),
    ("M21 bukti potong bisa terbit DOBEL untuk potongan yang sama", G_TAX, [
        ("backend/withholding_engine.py",
         '        if existing:\n            return {**existing, "idempotent": True}',
         '        if False:\n            return {**existing, "idempotent": True}')]),
    ("M22 pembetulan bukti potong tidak menaikkan versi (riwayat hilang)", G_TAX, [
        ("backend/withholding_engine.py",
         '        "state": CORRECTED, "version": int(doc.get("version", 1)) + 1,',
         '        "state": CORRECTED, "version": int(doc.get("version", 1)),')]),
    ("M23 bukti potong yang DIBATALKAN masih bisa dibetulkan", G_TAX, [
        ("backend/withholding_engine.py",
         "    if doc.get(\"state\") == CANCELLED:\n"
         "        raise ValueError(f\"Bukti potong {doc['number']} sudah dibatalkan — terbitkan",
         "    if False:\n"
         "        raise ValueError(f\"Bukti potong {doc['number']} sudah dibatalkan — terbitkan")]),
    ("M24 tie-out bukti potong dipaksa 'cocok' (selisih disembunyikan)", G_TAX, [
        ("backend/withholding_engine.py",
         '            "unproven": unproven, "matches": unproven == 0,',
         '            "unproven": 0, "matches": True,')]),
]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def write(rel: str, src: str):
    (ROOT / rel).write_text(src, encoding="utf-8")


def run_gate(gate: str) -> bool:
    log = pathlib.Path(f"/tmp/mut49_{gate}.log")
    with log.open("w", encoding="utf-8") as fh:
        p = subprocess.run([sys.executable, str(ROOT / "scripts" / gate)],
                           stdout=fh, stderr=subprocess.STDOUT, cwd=str(ROOT))
    return p.returncode == 0


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


def restore(backup: dict):
    for path, src in backup.items():
        write(path, src)


def main() -> int:
    print("=" * 78)
    print("UJI-MUTASI FASE 49 — membuktikan gate penutupan buku & kepatuhan pajak BERGIGI")
    print("=" * 78)
    print("\nBaseline (dua gate harus HIJAU sebelum merusak apa pun):")
    for g in (G_CLOSE, G_TAX):
        ok = run_gate(g)
        print(f"  {'HIJAU' if ok else 'MERAH'}  {g}")
        if not ok:
            print(f"  BASELINE MERAH — perbaiki dulu (log: /tmp/mut49_{g}.log)")
            return 1

    caught, escaped, skipped = [], [], []
    for name, gate, patches in MUTATIONS:
        try:
            backup = apply_patches(patches)
        except RuntimeError as e:
            skipped.append(name)
            print(f"  LEWAT      {name} — {e}")
            continue
        try:
            time.sleep(6)          # tunggu backend memuat ulang kode yang dirusak
            ok = run_gate(gate)
        finally:
            restore(backup)
            time.sleep(6)          # tunggu backend kembali ke kode yang benar
        if ok:
            escaped.append(name)
            print(f"  LOLOS      {name}  <-- gate tidak menangkapnya")
        else:
            caught.append(name)
            print(f"  TERTANGKAP {name}")

    print("\n" + "=" * 78)
    print(f"TERTANGKAP: {len(caught)} · LOLOS: {len(escaped)} · LEWAT: {len(skipped)}")
    print("\nBaseline setelah semua mutasi dipulihkan:")
    final_ok = True
    for g in (G_CLOSE, G_TAX):
        ok = run_gate(g)
        final_ok = final_ok and ok
        print(f"  {'hijau kembali' if ok else 'MASIH MERAH'}  {g}")
    if escaped or skipped or not final_ok:
        for n in escaped:
            print(f"  - LOLOS: {n}")
        for n in skipped:
            print(f"  - LEWAT: {n}")
        return 1
    print("\nSEMUA MUTASI TERTANGKAP — gate Fase 49 terbukti bergigi.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
