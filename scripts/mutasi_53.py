#!/usr/bin/env python3
"""mutasi_53.py — UJI-MUTASI Fase 53: membuktikan GATE 46 BERGIGI.

Cara kerja: satu per satu aturan Fase 53 dimatikan di kode (mutan), lalu
`scripts/verify_contract_legal_docgen.py` dijalankan. Gate yang tetap HIJAU saat aturannya
dimatikan berarti gate itu tidak menguji apa pun — **LOLOS adalah cacat perangkat uji**,
bukan kelulusan produk.

## Kenapa berkas ini ada (utang yang dibayar di Fase 55)

Gate 46 lahir di Fase 54 sebagai pembayaran utang Fase 53 — tetapi ia **HIJAU pada percobaan
pertama** dan tidak pernah diuji-mutasi. Di repo ini itu tanda bahaya, bukan kabar baik:
`mutasi_51.py` (C10a) dan `mutasi_54.py` sudah dua kali membuktikan bahwa pemeriksaan
berbentuk "apakah nama X ada di berkas" tetap hijau walau aturannya dicabut, karena namanya
masih tertulis di tempat lain — kadang cuma di baris impor.

Putaran pertama berkas ini menemukan dua kelas kebohongan yang lebih mahal daripada dugaan:

1. **Sembilan pemeriksaan gate 46 versi pertama tidak menguji apa pun** (`"won" in cc`,
   `"total_is_provisional" in ce`, `"belum ditetapkan" in dg`, dst.). Sekarang gate memakai
   `fungsi()` (pemeriksaan PER-LINGKUP) dan membaca **syarat** kodenya.
2. **Satu pemeriksaan LULUS karena alasan yang salah.** "SP3K ditolak tanpa berkas" hijau
   bukan karena gerbang berkas bekerja, melainkan karena gerbang URUTAN tahap menolak lebih
   dahulu ("Tahap sebelumnya belum selesai: Diajukan ke bank"). Gerbang berkasnya sendiri
   TIDAK PERNAH tersentuh — dan mutan M23 (yang mencabut gerbang itu) LOLOS. Uji negatif kini
   dijalankan pada tahap yang tepat, sebabnya ikut diperiksa, dan setiap uji negatif
   berpasangan dengan uji POSITIF (gerbang yang menolak semua hal tidak bisa dibedakan dari
   fitur yang mati).

## Yang dimutasi (empat lubang Fase 53 + penjaganya)

  * **satu jalur reservasi**: penahanan unit atomik, bentuk deal, masa keep, tahap lead;
  * **lead → pembeli**: idempotensi, tautan `lead_id`, tahap `won`, dedup NIK, gerbang
    "booking dulu" (di pratinjau DAN di server), kode penahan yang harus terdaftar SSOT;
  * **kejujuran angka**: `None` bukan `0`, keadaan `empty`, total SEMENTARA;
  * **rantai legal & KPR**: gerbang DP, akad kredit di urutan legal, syarat SP3K/SPKT/
    kelebihan tanah lunas, gerbang berkas & plafon SP3K;
  * **dokumen owner**: bulan romawi, "belum ditetapkan" (bukan Rp 0), varian menurut skema,
    plafon dari kontrak, nomor dari mesin urutan;
  * **pemisahan tugas (RBAC)**: yang mengisi angka bukan yang memajukan tahap legal;
  * **kejujuran layar**: biaya kosong tidak dicetak Rp 0, field Bank bukan teks bebas,
    testId tidak mati.

## Perangkat uji (mewarisi pelajaran mahal dari `mutasi_51/52/54.py`)

1. **Menunggu reload secara DETERMINISTIK.** `time.sleep()` buta melahirkan dua kebohongan:
   gate berjalan sebelum backend siap (dicatat "TERTANGKAP" tanpa pernah menguji apa pun)
   atau sebelum reload dimulai (dicatat "LOLOS" padahal kodenya masih utuh). PID proses ANAK
   `uvicorn` ditunggu berganti, lalu `/api/health` hidup.
2. **Mutasi FRONTEND tidak perlu menunggu backend** — gate 46 memeriksanya statis.
3. **Hasil ditulis SEGERA** ke `memory/gatelogs/mutasi_53_hasil.tsv`; `--ringkas` menyusun
   laporannya walau run dipecah atau dibunuh lingkungan di tengah jalan.
4. **Snapshot kode bersih** di `memory/mutasi53_snapshot/` + `--pulihkan`, supaya kode mutan
   tidak pernah tertinggal di repo.
5. **Jejak DATA dibersihkan** lewat `scripts/_fixture53.py` sesudah SETIAP mutan: di bawah
   mutan tertentu (mis. M11 "konversi mengabaikan penahan") gate membuat pembeli/kontrak yang
   TIDAK dibuatnya pada kode bersih, dan jalur pembersihan gate bisa terlewat.

Pakai:
    python3 scripts/mutasi_53.py --check           # cepat: pastikan semua pola masih ada
    python3 scripts/mutasi_53.py                   # penuh
    python3 scripts/mutasi_53.py --only=M01,M08    # sebagian
    python3 scripts/mutasi_53.py --from=M15        # lanjutkan run yang terputus
    python3 scripts/mutasi_53.py --ringkas         # laporan kumulatif
    python3 scripts/mutasi_53.py --pulihkan        # kembalikan kode & data bila run terputus
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

GATE = "verify_contract_legal_docgen.py"     # gate 46
HEALTH = "http://localhost:8001/api/health"

SR = "backend/sales_reserve.py"
QE = "backend/quotation_engine.py"
CC = "backend/customer_convert.py"
CE = "backend/contracts_engine.py"
KPR = "backend/kpr_engine.py"
DG = "backend/docgen.py"
CR = "backend/routers/contracts_router.py"
PANEL = "frontend/src/components/contracts/ContractPanel.js"
CONVERT = "frontend/src/components/contracts/ConvertToCustomerDialog.js"
KPANEL = "frontend/src/components/contracts/KprPanel.js"
LEGALTL = "frontend/src/components/contracts/LegalTimeline.js"

# Berkas backend memicu reload uvicorn; berkas frontend tidak perlu ditunggu karena gate
# memeriksanya secara statis.
BACKEND_FILES = {SR, QE, CC, CE, KPR, DG, CR}

# (nama, [(berkas, cari, ganti), ...], pemeriksaan yang HARUS jatuh)
MUTATIONS = [
    # ============================================== SATU JALUR RESERVASI (cacat asli 2)
    ("M01 penahanan unit tidak lagi ATOMIK (satu rumah bisa dijanjikan dua kali)", [
        (SR, '        {"id": unit["id"], "org_id": org, "status": "available"},',
         '        {"id": unit["id"], "org_id": org},')], "D3"),
    ("M02 reservasi menulis deal `status=\"active\"` (bentuk deal bercabang lagi)", [
        (SR, '        "status": "reserved", "price": int(unit.get("price") or 0),',
         '        "status": "active", "price": int(unit.get("price") or 0),')], "D1"),
    ("M03 masa keep unit tidak diisi (reservasi tidak pernah kedaluwarsa)", [
        (SR, '        "reserved_at": ts, "reserved_until": reserved_until, "booked_at": None,',
         '        "reserved_at": ts, "reserved_until": None, "booked_at": None,')], "D2"),
    ("M04 tahap lead tidak dimajukan oleh BUKTI reservasi (mundur ke pilihan manual)", [
        (SR,
         '    await lc.advance_on_deal({"id": deal_id, "lead_id": lead["id"], '
         '"status": "draft",\n'
         '                             "org_id": org}, stage="booking", actor=actor,\n'
         "                            reason=f\"Reservasi unit {unit.get('code')}\")",
         "    pass  # tahap lead tidak lagi dimajukan oleh bukti reservasi")], "D4"),
    ("M05 CACAT ASLI: penawaran membuat deal SENDIRI berbentuk lain", [
        (QE,
         "    import sales_reserve as sr\n"
         "    deal = await sr.reserve(\n"
         "        org, lead=lead, unit=unit, actor=actor, notes=note,\n"
         '        extra={"price": int(q["net_price"]), '
         '"discount": int(q.get("discount_amount") or 0),\n'
         '               "quotation_id": q["id"], "quotation_no": q.get("no"),\n'
         '               "addons": q.get("addons") or [],\n'
         '               "scheme_id": (q.get("scheme") or {}).get("id")})',
         '    deal = {"id": new_id(), "org_id": org, "lead_id": q["lead_id"],\n'
         '            "unit_id": unit["id"], "stage": "reserved", "status": "active",\n'
         '            "price": int(q["net_price"]), "quotation_id": q["id"],\n'
         '            "quotation_no": q.get("no"), "addons": q.get("addons") or [],\n'
         '            "created_by": actor, "created_at": ts, "updated_at": ts}\n'
         "    await db.deals.insert_one(dict(deal))")], "K2"),

    # ============================================== LEAD → PEMBELI (cacat asli 1)
    ("M06 konversi tidak lagi idempoten (kontrak kembar untuk satu deal)", [
        (CC,
         '    existing_contract = await db.contracts.find_one({"org_id": org, '
         '"deal_id": deal_id},\n'
         '                                                    {"_id": 0})\n'
         "    if existing_contract:",
         "    existing_contract = None\n"
         "    if existing_contract:")], "D13"),
    ("M07 CACAT ASLI: pembeli baru tidak menyimpan tautan ke lead", [
        (CC, '            "lead_id": lead.get("id"), "lead_ids": [lead.get("id")],',
         '            "lead_ids": [],')], "D11"),
    ("M08 tahap lead tidak diakhiri `won` (lead hidup selamanya)", [
        (CC, '    if lead and lead.get("stage") != "won":',
         "    if False and lead.get(\"stage\") != \"won\":")], "D14"),
    ("M09 dedup NIK dimatikan (satu manusia jadi dua baris pembeli)", [
        (CC, '    for kandidat in ((nik or "").strip(), (lead.get("nik") or "").strip()):',
         "    for kandidat in ():")], "D40"),
    ("M10 penahan 'booking dulu' hilang dari pratinjau (status kembali mengalahkan bukti)", [
        (CC, '    elif deal.get("status") == "reserved":\n'
             '        blocks.append(_blk("deal_belum_booking",',
         '    elif False:\n'
         '        blocks.append(_blk("deal_belum_booking",')], "D5"),
    ("M11 konversi MENGABAIKAN penahan (layar menahan, server mengizinkan)", [
        (CC, '    blocks = [b for b in pre["blocks"] if b["code"] != "sudah_pembeli"]\n'
             "    if blocks:",
         "    blocks = []\n"
         "    if blocks:")], "D8"),
    ("M12 label penahan konversi diketik kode sendiri (bukan Kamus Data)", [
        (CC,
         '    return {"code": code, "label": ref.label_of("convert_block", code), '
         '"detail": detail}',
         '    return {"code": code, "label": code.replace("_", " "), "detail": detail}')],
     "K11"),
    ("M13 kode penahan tidak terdaftar di Kamus Data (layar menampilkan kode mentah)", [
        (CC, '        blocks.append(_blk("deal_belum_booking",',
         '        blocks.append(_blk("deal_belum_dibooking",')], "D7"),
    ("M14 pengajuan KPR tidak dibuat untuk kontrak KPR (sub-alur KPR mati)", [
        (CC, '    if scheme == "kpr":\n'
             "        await kprmod.ensure_kpr_app(org, contract, actor)",
         "    if False:\n"
         "        await kprmod.ensure_kpr_app(org, contract, actor)")], "D19"),

    # ============================================== KEJUJURAN ANGKA (aturan repo)
    ("M15 nominal kosong dipaksa 0 saat baris disusun (dokumen ikut berbohong)", [
        (CE, '                     "amount": (int(amount) if amount is not None else None),',
         '                     "amount": int(amount or 0),')], "D16"),
    ("M16 komponen biaya kosong dianggap TERISI bernilai 0", [
        (CE, "        val = costs.get(field)", "        val = int(costs.get(field) or 0)")],
     "D16"),
    ("M17 total tidak pernah ditandai SEMENTARA (angka setengah tampak final)", [
        (CE, '        "total_is_provisional": bool(empty),',
         '        "total_is_provisional": False,')], "D17"),

    # ============================================== RANTAI LEGAL & KPR (cacat asli 3)
    ("M18 gerbang PPJB dimatikan (PPJB bisa maju tanpa DP masuk)", [
        (CE,
         "    if not inv:\n"
         '        b.append(("dp_belum_bayar", "Jadwal tagihan belum ada — booking dulu."))\n'
         "    elif paid < dp_amount or paid <= 0:",
         "    if False:\n"
         '        b.append(("dp_belum_bayar", "Jadwal tagihan belum ada — booking dulu."))\n'
         "    elif False:")], "D18"),
    ("M19 label penahan legal diketik sendiri (SSOT tahap legal bercabang)", [
        (CE,
         '            "blocks": [{"code": c, "label": ref.label_of("legal_block", c), '
         '"detail": d}',
         '            "blocks": [{"code": c, "label": c.replace("_", " "), "detail": d}')],
     "K10"),
    ("M20 `akad_kredit` dicabut dari urutan legal (cacat asli 3 kembali)", [
        (CE, 'LEGAL_ORDER = ("ppjb", "akad_kredit", "pelunasan", "bast", "ajb", "sertifikat")',
         'LEGAL_ORDER = ("ppjb", "pelunasan", "bast", "ajb", "sertifikat")')], "K9"),
    ("M21 gerbang akad kredit berhenti membaca SP3K", [
        (CE,
         '        if not (sp3k.get("file_id") and int(app.get("approved_plafon") or 0) > 0):\n'
         '            b.append(("sp3k_belum",',
         "        if False:\n"
         '            b.append(("sp3k_belum",')], "K12"),
    ("M22 syarat SPKT dicabut dari gerbang akad (kelebihan tanah tanpa surat)", [
        (CE,
         '        if bd.get("has_excess_land"):\n'
         "            if not await _spkt_exists(org, contract):",
         "        if False:\n"
         "            if not await _spkt_exists(org, contract):")], "K12b"),
    ("M23 kelebihan tanah tidak wajib lunas sebelum akad `[DOC]`", [
        (CE,
         "            if not await _excess_land_paid(org, contract, bd):\n"
         '                b.append(("kelebihan_tanah_belum_lunas",',
         "            if False:\n"
         '                b.append(("kelebihan_tanah_belum_lunas",')], "K12c"),
    ("M24 tahap SP3K tidak lagi menuntut BERKAS bukti", [
        (KPR,
         '        if not payload.get("file_id"):\n'
         '            raise ValueError("SP3K wajib disertai berkasnya '
         '(unggah dulu berkas SP3K).")',
         "        if False:\n"
         '            raise ValueError("SP3K wajib disertai berkasnya '
         '(unggah dulu berkas SP3K).")')], "D19"),
    ("M25 tahap SP3K tidak lagi menuntut plafon yang DISETUJUI bank", [
        (KPR,
         '        if not int(payload.get("plafon") or 0):\n'
         '            raise ValueError("Plafon yang DISETUJUI bank wajib diisi '
         'pada tahap SP3K.")',
         "        if False:\n"
         '            raise ValueError("Plafon yang DISETUJUI bank wajib diisi '
         'pada tahap SP3K.")')], "D37"),
    ("M26 akad kredit berhenti memeriksa ULANG SP3K di mesin KPR", [
        (KPR,
         '        if not (sp3k.get("file_id") and int(app.get("approved_plafon") or 0) > 0):\n'
         '            raise ValueError("Akad kredit butuh SP3K yang sudah tercatat lengkap "',
         "        if False:\n"
         '            raise ValueError("Akad kredit butuh SP3K yang sudah tercatat lengkap "')],
     "K13b"),

    # ============================================== DOKUMEN OWNER (cacat asli 4)
    ("M27 bulan pada nomor dokumen jadi angka (bukan format owner)", [
        (DG, '    return f"{str(n).zfill(width)}/{doc_code}/{pcode}/{ROMAN[month]}/{year}"',
         '    return f"{str(n).zfill(width)}/{doc_code}/{pcode}/{month:02d}/{year}"')], "D33"),
    ("M28 biaya yang belum diisi dicetak 'Rp 0' (dokumen legal berbohong)", [
        (DG, "def _rp(v) -> str:\n    if v is None:\n        return BELUM",
         'def _rp(v) -> str:\n    if v is None:\n        return "Rp 0"')], "D25"),
    ("M29 varian dokumen tidak lagi mengikuti skema kontrak", [
        (DG,
         '        if scheme and contract.get("scheme") != scheme:\n'
         '            blocks.append(("skema_tidak_cocok",',
         "        if False:\n"
         '            blocks.append(("skema_tidak_cocok",')], "D30"),
    ("M30 plafon tidak lagi dibaca dari kontrak (SPR KPR tanpa angka bank)", [
        (DG,
         '        "dp_line": (f"Plafon Kredit : {money(\'PLAFON_KREDIT\')}\\n'
         'Uang Muka : {_pct(dp_pct)}"',
         '        "dp_line": (f"Plafon Kredit : {BELUM}\\nUang Muka : {_pct(dp_pct)}"')],
     "D34"),
    ("M31 nomor urut dokumen dari HITUNGAN dokumen (nomor bisa berulang)", [
        (DG, "    n = await seq.next_seq(scope, org, period)",
         "    n = await db.documents.count_documents(\n"
         '        {"org_id": org, "template_code": code}) + 1')], "K14b"),

    # ============================================== PEMISAHAN TUGAS (RBAC)
    ("M32 tahap legal boleh dimajukan pengisi angka (izin dilonggarkan)", [
        (CR,
         "async def legal_advance(contract_id: str, stage: str, payload: LegalAdvanceIn,\n"
         '                        user: dict = Depends(require_permission("contracts", '
         '"manage"))):',
         "async def legal_advance(contract_id: str, stage: str, payload: LegalAdvanceIn,\n"
         '                        user: dict = Depends(require_permission("contracts", '
         '"update"))):')], "D23"),
    ("M33 mengisi biaya menuntut izin `manage` (Keuangan kehilangan tugasnya)", [
        (CR,
         "async def set_costs(contract_id: str, payload: ContractCostsIn,\n"
         '                    user: dict = Depends(require_permission("contracts", '
         '"update"))):',
         "async def set_costs(contract_id: str, payload: ContractCostsIn,\n"
         '                    user: dict = Depends(require_permission("contracts", '
         '"manage"))):')], "D24"),
    ("M34 usulan varian dokumen dihapus dari jawaban API (layar menebak sendiri)", [
        (CR, '            "recommended_code": ce.SCHEME_DOC.get(c.get("scheme"))}',
         '            "recommended_code": None}')], "D29"),

    # ============================================== KEJUJURAN LAYAR
    ("M35 layar mencetak Rp 0 untuk biaya yang belum diisi", [
        (PANEL,
         "                    {r.amount === null ? (\n"
         "                      <span data-testid={P53.breakdownEmptyState}\n"
         '                        className="text-xs italic text-muted-foreground">'
         "{r.state_label}</span>\n"
         "                    ) : <MoneyText value={r.amount} />}",
         "                    <MoneyText value={r.amount || 0} />")], "K18"),
    ("M36 field Bank kembali menjadi kotak teks bebas (empat ejaan 'BTN' = empat bank)", [
        (KPANEL,
         '                <ReferenceSelect group="financing_bank" testId="kpr-bank"\n'
         '                  value={form.bank || ""} onChange={(v) => set("bank", v)}\n'
         '                  placeholder="Pilih bank penyalur KPR…" />',
         '                <Input id="kpr-bank" className="bg-background" '
         'value={form.bank || ""}\n'
         '                  onChange={(e) => set("bank", e.target.value)} />')], "K19b"),
    ("M37 testId penahan legal dilepas dari layar (uji kehilangan pegangan tanpa suara)", [
        (LEGALTL, "                  <p data-testid={P53.legalBlocked}",
         "                  <p")], "K20b"),

    # ===================================== FASE 56: janji layar & bahasa layar
    # Tiga cacat yang LOLOS dari gate versi Fase 55 dan baru tertangkap oleh manusia di
    # peramban. Semuanya tidak bisa dilihat dari uji HTTP: layar MENJANJIKAN sesuatu
    # (membawa ke kontrak), atau MENGATAKAN sesuatu yang tidak benar ("belum ada kontrak"),
    # atau berbicara dalam bahasa mesin (nama kolom) kepada manusia.
    ("M38 tombol 'Jadikan Pembeli' kembali memakai penanda `?hub=` "
     "(mendarat di Ringkasan sambil mengaku membawa ke kontrak)", [
        (CONVERT, "      if (cid) navigate(`/customers/${cid}?tab=kontrak53`);",
         "      if (cid) navigate(`/customers/${cid}?hub=kontrak53`);")], "K21b"),
    ("M39 tautan 'Buka Kontrak & Legal' memakai penanda yang tidak dibaca halamannya", [
        (PANEL, "          <Link to={`/customers/${contract.customer_id}?tab=kontrak53`}",
         "          <Link to={`/customers/${contract.customer_id}?hub=kontrak53`}")], "K21b"),
    ("M40 daftar komponen belum-diisi kembali berisi KODE KOLOM (bukan label manusia)", [
        (CE, '    empty_labels = [r["label"] for r in cost_rows if r["state"] == "empty"]',
         '    empty_labels = [r["code"] for r in cost_rows if r["state"] == "empty"]')],
     "D26c"),
    ("M41 catatan 'total masih SEMENTARA' pada API kembali menyebut kode kolom", [
        (CE, '        "note": ("Total masih SEMENTARA: " + ", ".join(empty_labels)'
             ' + " belum diisi."\n                 if empty_labels else None),',
         '        "note": ("Total masih SEMENTARA: " + ", ".join(empty) + " belum diisi."\n'
         "                 if empty else None),")], "K22b"),
    ("M42 DOKUMEN yang ditandatangani pembeli kembali mencetak kode kolom", [
        (DG, '        "total_note": (f"Catatan: total masih SEMENTARA — komponen "\n'
             "                       f\"{', '.join(bd.get('costs_incomplete_labels') or [])}"
             ' belum diisi, "\n'
             '                       "jadi angka di atas belum lengkap."\n'
             '                       if bd["costs_incomplete"] else ""),',
         '        "total_note": (f"Catatan: total masih SEMENTARA — komponen "\n'
         "                       f\"{', '.join(bd['costs_incomplete'])} belum diisi, \"\n"
         '                       "jadi angka di atas belum lengkap."\n'
         '                       if bd["costs_incomplete"] else ""),')], "D26e"),
    ("M43 peringatan panel dokumen kembali menyebut kode kolom", [
        (DG, '            "warnings": ([("Komponen biaya belum lengkap ("\n'
             '                           + ", ".join(bd.get("costs_incomplete_labels") or [])'
             "\n"
             '                           + ") — dokumen akan menulis \'belum ditetapkan\','
             ' bukan Rp 0.")]',
         '            "warnings": ([("Komponen biaya belum lengkap ("\n'
         '                           + ", ".join(bd["costs_incomplete"])\n'
         '                           + ") — dokumen akan menulis \'belum ditetapkan\','
         ' bukan Rp 0.")]')], "D26f"),
    ("M44 spanduk 'masih SEMENTARA' di layar kembali menyebut kode kolom", [
        (PANEL, "                masih SEMENTARA — {(bd.costs_incomplete_labels\n"
                '                  || bd.costs_incomplete || []).join(", ")} belum diisi',
         "                masih SEMENTARA — "
         '{(bd.costs_incomplete || []).join(", ")} belum diisi')], "K24"),
    ("M45 CACAT ASLI: baris di luar lingkup disembunyikan TANPA SEBAB "
     "(layar berkata 'belum ada kontrak' untuk kontrak yang ADA)", [
        (CR, '    tersembunyi = 0\n'
             '    if is_scoped_sales(user):\n'
             '        milik = [r for r in out["data"] if r.get("assigned_to")'
             ' == user.get("email")]\n'
             '        tersembunyi = len(out["data"]) - len(milik)\n'
             '        out["data"] = milik\n'
             '        out["total"] = len(milik)',
         '    tersembunyi = 0\n'
         '    if is_scoped_sales(user):\n'
         '        out["data"] = [r for r in out["data"]\n'
         '                       if r.get("assigned_to") == user.get("email")]\n'
         '        out["total"] = len(out["data"])')], "D26h"),
    ("M46 layar berhenti membedakan 'belum ada' dari 'bukan lingkup Anda'", [
        (PANEL, '    if (state.reasonCode === "di_luar_lingkup") {\n'
                "      return (\n"
                "        <EmptyState testId={P53.contractScoped} icon={ShieldOff}\n"
                '          title="Kontrak ini di luar lingkup data Anda"\n'
                "          description={state.reason} />\n"
                "      );\n"
                "    }\n",
         "")], "K25b"),
]


# --------------------------------------------------------------------------- berkas
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
SNAP = ROOT / "memory" / "mutasi53_snapshot"


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
    import _fixture53
    print(f"Bahan uji Fase 53 dibuang: {_fixture53.purge()}")
    return 0


# ------------------------------------------------------- menunggu backend memuat ulang
def server_pids() -> tuple:
    """PID proses PEKERJA (anak) `uvicorn server:app --reload`.

    Induknya TIDAK pernah berganti PID saat reload; yang berganti adalah anaknya.
    """
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
            time.sleep(1.2)     # beri jeda agar router selesai terpasang
            return (f"reload {time.time() - mulai:.0f}s" if ganti else
                    f"TANPA reload terdeteksi ({time.time() - mulai:.0f}s)")
        time.sleep(0.5)
    return "backend TIDAK sehat setelah menunggu"


# --------------------------------------------------------------------------- gate
def run_gate(tag: str) -> tuple:
    logdir = ROOT / "memory" / "gatelogs"
    logdir.mkdir(parents=True, exist_ok=True)
    log = logdir / f"mut53_{tag}.log"
    with log.open("w", encoding="utf-8") as fh:
        p = subprocess.run([sys.executable, str(ROOT / "scripts" / GATE)],
                           stdout=fh, stderr=subprocess.STDOUT, cwd=str(ROOT))
    isi = log.read_text(encoding="utf-8", errors="ignore")
    jatuh = [ln.strip()[6:].split()[0] for ln in isi.splitlines()
             if ln.strip().startswith("MERAH")]
    return p.returncode == 0, jatuh


HASIL = ROOT / "memory" / "gatelogs" / "mutasi_53_hasil.tsv"


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
    print("RINGKASAN UJI-MUTASI FASE 53 (kumulatif) — gate 46 verify_contract_legal_docgen.py")
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
    print("PERIKSA POLA MUTASI FASE 53 (cepat, tanpa menjalankan gate)")
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
    print(f"UJI-MUTASI FASE 53 — {len(rows)} mutan · gate 46 {GATE}")
    print(f"Snapshot kode bersih: {SNAP.relative_to(ROOT)}")
    print("=" * 78)

    import _fixture53
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
                          f"jatuh — gate menangkapnya lewat jalan lain)")
                catat_hasil(nama, "TERTANGKAP",
                            f"{harus_jatuh}{'' if tepat else ' (lewat jalan lain)'}: "
                            f"{','.join(jatuh[:6])}")
        finally:
            restore(backup)
            if butuh_reload:
                wait_reload(server_pids())
            _fixture53.purge()

    print()
    return ringkas()


if __name__ == "__main__":
    sys.exit(main())
