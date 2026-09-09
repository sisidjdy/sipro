#!/usr/bin/env python3
"""mutasi_48.py — UJI-MUTASI Fase 48: membuktikan gate 34/35/36 BERGIGI.

Cara kerja: satu per satu aturan dimatikan di kode (mutan), gate yang bersangkutan
dijalankan, lalu kode dipulihkan. Gate yang tetap HIJAU saat aturannya dimatikan berarti
gate itu tidak menguji apa pun (LOLOS = cacat perangkat uji, bukan kelulusan).

Pelajaran Fase 46/47 yang dipakai lagi di sini:
  * **matikan SEMUA lapis.** Panjang alasan dijaga di kontrak permintaan (`models_p48`) DAN
    di service; mematikan satu lapis saja menghasilkan mutan ekuivalen yang membuat gate
    tampak longgar padahal tidak.
  * **baseline dulu.** Bila gate sudah merah sebelum dirusak, hasil mutasi tidak berarti.
"""
import pathlib
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
G_PROC = "verify_procurement_vendor.py"
G_SUB = "verify_subcon_retention.py"
G_STOCK = "verify_stock_control.py"

# (nama, gate, [(berkas, cari, ganti), ...])
MUTATIONS = [
    ("M01 kode vendor kembar diperbolehkan (satu rekanan jadi tiga nama)", G_PROC, [
        ("backend/vendor_engine.py",
         'if await db.vendors.find_one({"org_id": org, "code": code}, {"_id": 0, "id": 1}):',
         'if False:')]),
    ("M02 pembanding harga kosong menjawab angka 0 (bukan 'belum ada data')", G_PROC, [
        ("backend/vendor_engine.py",
         '        return {"state": "missing_data", "rows": [], "best": None,',
         '        return {"state": "complete", "rows": [], "best": {"unit_price": 0},')]),
    ("M03 harga di atas acuan dianggap wajar (peringatan dimatikan)", G_PROC, [
        ("backend/vendor_engine.py",
         "    if var_pct > PRICE_WARN_PCT:",
         "    if False:")]),
    ("M04 PO kedua dari permintaan yang sama diperbolehkan (DUA lapis dimatikan)", G_PROC, [
        ("backend/procurement_extra.py",
         '        if row["shortage"] <= 0:',
         '        if False:'),
        # Lapis kedua: batas kuantitas terhadap kekurangan. Mematikan satu lapis saja
        # menghasilkan mutan EKUIVALEN (gate tetap merah karena lapis lain menangkap),
        # sehingga hasil uji-mutasi tampak "lolos" padahal aturannya masih hidup.
        ("backend/procurement_extra.py",
         '        if qty > row["shortage"] + 1e-9:',
         '        if False:')]),
    ("M05 kuantitas terpesan tidak dicatat di permintaan (PO bisa dobel diam-diam)", G_PROC, [
        ("backend/procurement_extra.py",
         '        short = round(max(0.0, outstanding - max(0.0, stock) - ordered), 2)',
         '        short = round(max(0.0, outstanding - max(0.0, stock)), 2)')]),
    ("M06 retur tidak mengurangi stok (barang menguap dari catatan)", G_PROC, [
        ("backend/procurement_extra.py",
         '    for ln in lines:\n        if ln.get("material_id"):',
         '    for ln in []:\n        if ln.get("material_id"):')]),
    ("M07 retur tidak menurunkan nilai diterima PO", G_PROC, [
        ("backend/procurement_extra.py",
         '        "items": pitems, "received_value": max(0, received_after), "status": status,',
         '        "items": pitems, "received_value": int(po.get("received_value", 0)), "status": status,')]),
    ("M08 retur di bawah nilai yang sudah ditagih dibiarkan lolos", G_PROC, [
        ("backend/procurement_extra.py",
         "    if billed > received_after:",
         "    if False:")]),
    ("M09 3-way match kembali hanya MENANDAI (tidak menahan tagihan)", G_PROC, [
        ("backend/routers/procurement_router.py",
         '    if match["state"] == "held":',
         '    if False:')]),
    ("M10 siapa pun boleh menerobos tahanan 3-way (dua lapis dimatikan)", G_PROC, [
        ("backend/routers/procurement_router.py",
         '        if user.get("role") not in ("finance_manager",) + SENIOR_ROLES:',
         '        if False:'),
        ("backend/routers/procurement_router.py",
         '        if len((payload.override_reason or "").strip()) < 10:',
         '        if False:')]),
    ("M11 evaluasi vendor tanpa bukti mengarang skor 0", G_PROC, [
        ("backend/vendor_engine.py",
         "    got = {k: v for k, v in components.items() if v.get(\"score\") is not None}",
         "    got = {k: (v if v.get('score') is not None else {'score': 0}) "
         "for k, v in components.items()}")]),
    ("M12 uang muka melebihi kebijakan 30% diperbolehkan", G_SUB, [
        ("backend/subcon_finance.py",
         "    if cv and total > cv * 0.3:",
         "    if False:")]),
    ("M13 uang muka dibayar dibebankan sebagai BIAYA (bukan aset 1-1800)", G_SUB, [
        ("backend/subcon_finance.py",
         '        [{"account_code": GL_SUBCON_ADVANCE, "debit": amount, "credit": 0,',
         '        [{"account_code": "6-1300", "debit": amount, "credit": 0,')]),
    ("M14 finance biasa boleh memutuskan uang muka (SoD longgar)", G_SUB, [
        ("backend/routers/subcon_finance_router.py",
         'async def decide_advance(aid: str, payload: AdvanceDecisionIn,\n'
         '                        user: dict = Depends(require_permission("subcon_finance", "manage"))):',
         'async def decide_advance(aid: str, payload: AdvanceDecisionIn,\n'
         '                        user: dict = Depends(require_permission("subcon_finance", "view"))):')]),
    ("M15 angsuran melebihi sisa uang muka diperbolehkan", G_SUB, [
        ("backend/subcon_finance.py",
         '        if amount > int(adv.get("outstanding", 0)):',
         '        if False:')]),
    ("M16 potongan diabaikan saat termin disetujui (subkon dibayar penuh)", G_SUB, [
        ("backend/routers/subcon_claims_router.py",
         "        bill = await sf.attach_deductions(org, bill, spk, claim, user.get(\"email\"))",
         "        bill = bill")]),
    ("M17 retensi tidak pernah masuk daftar (uang tertahan tanpa jalan pulang)", G_SUB, [
        ("backend/subcon_finance.py",
         '    amount = int(bill.get("retention_held", 0) or 0)\n    if amount <= 0:',
         '    amount = int(bill.get("retention_held", 0) or 0)\n    if True:')]),
    ("M18 gerbang retensi buta terhadap punch list terbuka", G_SUB, [
        ("backend/subcon_finance.py",
         "    open_punch, scope_note = await _open_punch(org, ret)",
         "    open_punch, scope_note = [], await _open_punch(org, ret) and ''")]),
    ("M19 retensi bisa dicairkan dua kali (TIGA lapis dimatikan)", G_SUB, [
        ("backend/subcon_finance.py",
         '    if ret.get("state") == "released":\n        raise ValueError("Retensi ini sudah dicairkan',
         '    if False:\n        raise ValueError("Retensi ini sudah dicairkan'),
        ("backend/subcon_finance.py",
         '    if ret.get("state") != "release_requested":\n        raise ValueError("Pencairan harus DIAJUKAN',
         '    if False:\n        raise ValueError("Pencairan harus DIAJUKAN'),
        # Lapis ketiga ada di gerbang: `already_released`. Tanpa mematikan ketiganya,
        # mutan ini EKUIVALEN dan uji-mutasi berbohong tentang ketajaman gate.
        ("backend/subcon_finance.py",
         '    if ret.get("state") == "released":\n        blocks.append({"code": "already_released",',
         '    if False:\n        blocks.append({"code": "already_released",')]),
    ("M20 pengaju pencairan boleh mencairkan sendiri (SoD retensi longgar)", G_SUB, [
        ("backend/subcon_finance.py",
         '    if ret.get("requested_by") == actor:',
         '    if False:')]),
    ("M21 transfer melebihi stok diperbolehkan (barang tercipta)", G_STOCK, [
        ("backend/stock_control.py",
         "    if qty > stock + 1e-9:",
         "    if False:")]),
    ("M22 transfer hanya menulis mutasi MASUK (barang berlipat)", G_STOCK, [
        ("backend/stock_control.py",
         '        {"id": new_id(), **common, "project_id": data["from_project_id"], "material_id": src["id"],\n'
         '         "type": "out", "qty": qty, **price_fields,',
         '        {"id": new_id(), **common, "project_id": data["from_project_id"], "material_id": src["id"],\n'
         '         "type": "out", "qty": 0, **price_fields,')]),
    ("M23 peringatan stok minimum dimatikan (selalu 'aman')", G_STOCK, [
        ("backend/stock_control.py",
         '    return "below_min" if stock < float(min_qty) else "ok"',
         '    return "ok"')]),
    ("M24 nilai persediaan dikarang untuk material tanpa harga masuk", G_STOCK, [
        ("backend/stock_control.py",
         "    if qty <= 0:\n        return None",
         "    if qty <= 0:\n        return 1")]),
]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, text: str):
    (ROOT / path).write_text(text, encoding="utf-8")


def run_gate(gate: str) -> bool:
    log = pathlib.Path(f"/tmp/mut48_{gate}.log")
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
    print("UJI-MUTASI FASE 48 — membuktikan gate pengadaan/subkon/stok BERGIGI")
    print("=" * 78)
    print("\nBaseline (tiga gate harus HIJAU sebelum merusak apa pun):")
    for g in (G_PROC, G_SUB, G_STOCK):
        ok = run_gate(g)
        print(f"  {'HIJAU' if ok else 'MERAH'}  {g}")
        if not ok:
            print(f"  BASELINE MERAH — perbaiki dulu (log: /tmp/mut48_{g}.log)")
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
    for g in (G_PROC, G_SUB, G_STOCK):
        ok = run_gate(g)
        final_ok = final_ok and ok
        print(f"  {'hijau kembali' if ok else 'MASIH MERAH'}  {g}")
    if escaped or skipped or not final_ok:
        for n in escaped:
            print(f"  - LOLOS: {n}")
        for n in skipped:
            print(f"  - LEWAT: {n}")
        return 1
    print("\nSEMUA MUTASI TERTANGKAP — gate Fase 48 terbukti bergigi.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
