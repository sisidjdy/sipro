"""seed_phase49.py — data demo Fase 49 (idempoten): penutupan buku & kepatuhan pajak yang
BISA DICOBA.

Pelajaran Fase 46/48 dipakai lagi: **fitur yang tidak bisa dicapai sama saja dengan tidak
ada.** Layar Fase 49 (penutupan buku, paket laporan owner, e-Faktur & ekspor berkas, bukti
potong/e-Bupot, rekap SPT Masa PPN) mustahil dibuktikan bila database belum punya identitas
pajak perusahaan, belum ada satu pun faktur keluaran, dan belum ada satu pun potongan PPh
yang benar-benar terjadi di pembukuan.

Yang ditulis — semuanya BERSANDAR pada data nyata yang sudah ada (deal ber-AR, master vendor,
proyek), bukan objek karangan:

  * **Identitas pajak perusahaan contoh**: `tax.company_npwp` = 0012345678901000 dan
    `tax.company_idtku`. Tanpa ini SEMUA ekspor pajak ditahan ("NPWP perusahaan belum diisi")
    sehingga tombol unduh XML/CSV tidak pernah bisa dicoba. Nilai ini DITANDAI demo di
    alasan perubahan setelan, dan **tidak pernah menimpa** NPWP asli yang sudah diisi
    manusia (idempoten & aman untuk data sungguhan).
  * **1 faktur pajak keluaran** atas deal yang memang sudah punya jadwal AR, memakai NPWP
    pembeli dari master pelanggan. NPWP pelanggan demo masih 15 digit gaya lama, jadi layar
    ekspor sekaligus memperlihatkan **normalisasi PMK 112/2022** (15 → 16 digit) beserta
    pemberitahuannya — bukan diam-diam diubah.
  * **1 tagihan vendor demo yang DIBAYAR SEBAGIAN dengan potong PPh 4(2) jasa konstruksi**:
    vendor menerima NETO, potongan menjadi Utang Pajak (2-1300), dan **bukti potong bernomor
    terbit otomatis** lengkap dengan kode objek pajak. Ini yang membuat tab Bukti Potong
    punya isi, tie-out bisa dibaca, PDF bisa dicetak, dan ekspor e-Bupot bisa dicoba.

Yang SENGAJA TIDAK dibuat-buat:
  * **Daftar periksa tutup buku tidak dipoles.** Bulan berjalan memang punya pemeriksaan yang
    MENAHAN (mutasi bank belum dicocokkan, tagihan menunggu persetujuan, dst) — itu justru
    bahan mencoba jalur "tahan" dan "terobosan beralasan".
  * **Arus kas per proyek tidak diberi jurnal karangan.** Data nyata sudah menghasilkan baris
    proyek + baris "tidak teralokasi" dengan tie-out cocok; menambah jurnal palsu hanya akan
    merusak pembukuan demo.
  * **Tidak ada bulan/tahun yang ditutup oleh seed.** Menutup buku adalah keputusan manusia
    (dan melahirkan jurnal penutup), jadi tombolnya dibiarkan untuk pemakai.
  * **Potongan PPh fee mitra tidak diterbitkan bukti potongnya.** Ia dibiarkan tampil sebagai
    "kandidat" supaya daftar kerja e-Bupot punya isi yang jujur.

Semua dokumen yang dibuat seed bertanda `demo_batch="fase49"`.
"""
import logging
from datetime import date, timedelta

import build_engine as be
import finance_engine as fe
import settings_store as st
import tax_engine as te
import withholding_engine as wh
from core_utils import new_id, today_iso_date
from db import ORG_ID, db

logger = logging.getLogger("sipro.seed")
BATCH = "fase49"
DEMO_NPWP = "0012345678901000"
DEMO_IDTKU = "0012345678901000000000"
BILL_MARKER = "bill_pph_konstruksi"
DEAL_MARKER = "deal_faktur_demo"
# Kode objek pajak pelaksanaan konstruksi kualifikasi menengah & besar (KEP-143/PJ/2022).
DEMO_OBJECT_CODE = "28-409-11"


def _last_month_day(day: int = 15) -> str:
    """Tanggal di BULAN LALU (default tanggal 15) — dipakai agar data demo tidak menumpuk
    di masa pajak berjalan yang sedang dipakai uji inti."""
    first = date.fromisoformat(today_iso_date()).replace(day=1)
    prev_last = first - timedelta(days=1)
    return prev_last.replace(day=min(day, prev_last.day)).isoformat()


async def _tax_identity(org: str) -> dict:
    """Isi NPWP/IDTKU perusahaan HANYA bila masih kosong (jangan timpa data sungguhan)."""
    out = {}
    current = await st.get_many(["tax.company_npwp", "tax.company_idtku"], org_id=org)
    if not str(current.get("tax.company_npwp") or "").strip():
        await st.set_value("tax.company_npwp", DEMO_NPWP, actor="seed",
                           reason=("Data DEMO Fase 49 — NPWP perusahaan contoh agar ekspor "
                                   "e-Faktur/e-Bupot bisa dicoba. Ganti dengan NPWP asli "
                                   "sebelum berkas dikirim ke DJP."),
                           org_id=org)
        out["npwp"] = DEMO_NPWP
    if not str(current.get("tax.company_idtku") or "").strip():
        await st.set_value("tax.company_idtku", DEMO_IDTKU, actor="seed",
                           reason="Data DEMO Fase 49 — IDTKU contoh (cabang pusat).",
                           org_id=org)
        out["idtku"] = DEMO_IDTKU
    return out


async def _faktur(org: str) -> dict:
    """Faktur keluaran DEMO atas satu unit yang dibukukan khusus untuk fase ini.

    Kenapa memakai deal sendiri, bukan deal yang sudah ada: deal ber-AR yang belum berfaktur
    adalah bahan uji inti (`poc/poc_49.py` dan gate kepatuhan pajak memakainya untuk menguji
    penerbitan faktur). Bila seed menghabiskannya, uji inti kehilangan bahan dan hanya bisa
    lulus di database kosong — itu bentuk lain dari "hijau bohong".

    Kenapa bertanggal BULAN LALU: masa pajak berjalan adalah ruang kerja uji inti (POC & gate
    menghitung PPN keluaran masa ini dan menguji ekspor yang ditahan). Data demo yang menetap
    di masa yang sama akan mengubah angka yang sedang diuji. Demo ini karena itu berupa
    penjualan yang dibukukan bulan lalu — utuh dan bisa ditelusuri, tanpa mengganggu masa
    berjalan.

    Pembelinya SENGAJA belum punya NPWP, sehingga layar ekspor memperlihatkan jalur paling
    penting apa adanya: ekspor DITAHAN + menyebut faktur mana yang harus dilengkapi, lalu
    bisa dituntaskan lewat tombol "Ganti" (faktur pengganti) sampai berkas siap diunduh.
    """
    deal = await db.deals.find_one({"org_id": org, "demo_marker": DEAL_MARKER}, {"_id": 0})
    booked = _last_month_day()
    if not deal:
        unit = await db.units.find_one({"org_id": org, "status": "available"},
                                       {"_id": 0, "id": 1, "code": 1, "price": 1,
                                        "project_id": 1}, sort=[("code", 1)])
        lead = await db.leads.find_one({"org_id": org, "stage": {"$in": ["recycle", "nurturing"]}},
                                       {"_id": 0, "id": 1, "name": 1})
        if not unit or not lead:
            return {}
        ts = f"{booked}T09:00:00+00:00"
        deal = {
            "id": new_id(), "org_id": org, "demo_batch": BATCH, "demo_marker": DEAL_MARKER,
            "lead_id": lead["id"], "unit_id": unit["id"], "project_id": unit.get("project_id"),
            "assigned_to": "sales@sipro.co.id", "status": "booked",
            "price": int(unit.get("price") or 0), "booking_fee": 5_000_000,
            "reserved_at": ts, "reserved_until": ts, "booked_at": ts,
            "notes": ("DEMO Fase 49 — unit dibukukan bulan lalu untuk menguji faktur pajak "
                      "keluaran & ekspor e-Faktur. Pembeli belum menyerahkan NPWP."),
            "created_by": "seed", "created_at": ts, "updated_at": ts,
        }
        await db.deals.insert_one(dict(deal))
        deal.pop("_id", None)
        await db.units.update_one({"id": unit["id"], "org_id": org}, {"$set": {
            "status": "booked", "booked_by_deal": deal["id"], "payment_status": "booking_fee",
            "updated_at": ts}})
        await db.leads.update_one({"id": lead["id"], "org_id": org},
                                  {"$set": {"stage": "booking", "updated_at": ts}})
        # Cacat D-F: unit yang dibukukan WAJIB terikat lead & deal di dokumen unitnya sendiri
        # (dipakai laporan, portal pembeli, dan gate integritas data). Seed Fase 31 melakukan
        # pengikatan ini untuk unit yang sudah ada; unit yang baru dibukukan di sini berjalan
        # SESUDAH seed itu, jadi ikatannya harus dipasang langsung — kalau tidak, gate
        # `verify_data_integrity` benar-benar menemukan "unit terjual tanpa ikatan lead/deal".
        await be.sync_unit_binding(org, unit["id"])
        await fe.create_ar_for_deal(deal, org_id=org, actor="seed")

    existing = await db.faktur_pajak.find_one(
        {"org_id": org, "deal_id": deal["id"], "status": {"$in": [None, "issued"]}}, {"_id": 0})
    if existing:
        return {"number": existing.get("number"), "created": False}
    doc = await te.issue_faktur(org, deal["id"], "seed")
    stamp = f"{booked}T09:30:00+00:00"
    await db.faktur_pajak.update_one({"id": doc["id"], "org_id": org}, {"$set": {
        "demo_batch": BATCH, "issued_at": stamp, "period": booked[:7],
        "created_at": stamp, "updated_at": stamp}})
    return {"number": doc.get("number"), "buyer": doc.get("buyer_name"),
            "npwp": doc.get("buyer_npwp"), "period": booked[:7], "created": True}


async def _bill_paid_with_withholding(org: str) -> dict:
    """Tagihan vendor demo yang dibayar SEBAGIAN dengan potong PPh 4(2) jasa konstruksi.

    Sengaja dibayar sebagian: sisanya membuat status `partial` tetap bisa dicoba, dan bukti
    potong yang terbit hanya menyangkut kas yang BENAR-BENAR keluar.
    """
    bill = await db.ap_invoices.find_one({"org_id": org, "demo_marker": BILL_MARKER}, {"_id": 0})
    doc = None
    if not bill:
        vendor = await db.vendors.find_one({"org_id": org}, {"_id": 0, "name": 1})
        project = await db.projects.find_one({"org_id": org}, {"_id": 0, "id": 1, "name": 1})
        if not vendor or not project:
            return {}
        bill = await fe.create_ap_bill(
            vendor["name"], project["id"], 60_000_000, 0, None,
            "Termin pekerjaan struktur (DEMO Fase 49) — dibayar dengan potong PPh 4(2).",
            "seed", org)
        await db.ap_invoices.update_one({"id": bill["id"], "org_id": org}, {"$set": {
            "demo_batch": BATCH, "demo_marker": BILL_MARKER}})
        bill = await fe.approve_ap_bill(bill["id"], "seed", org)

    already = await db.payments_out.find_one({"org_id": org, "bill_id": bill["id"]}, {"_id": 0})
    if already:
        doc = await db.withholding_docs.find_one(
            {"org_id": org, "ref_id": already["id"]}, {"_id": 0, "number": 1, "amount": 1})
        return {"bill": bill.get("vendor"), "payment": already["id"],
                "bupot": (doc or {}).get("number"), "created": False}

    rate = await wh.default_rate(org, "pph4_2_konstruksi")
    if rate <= 0:
        return {}
    amount = 50_000_000
    withheld = wh.tax_of(amount, rate)
    memo = (f"PPh pph4_2_konstruksi {rate}% atas {bill.get('vendor')} "
            f"(dasar Rp {amount:,})")
    updated, payment = await fe.pay_ap_bill(
        bill["id"], amount, "Pembayaran termin DEMO Fase 49 dengan potong PPh.", "seed", org,
        withhold={"kind": "pph4_2_konstruksi", "base": amount, "rate": rate,
                  "amount": withheld, "memo": memo},
        return_payment=True)
    doc = await wh.issue_for_bill_payment(
        org, "seed", bill=bill, payment=payment, kind="pph4_2_konstruksi", base=amount,
        rate=rate, object_code=DEMO_OBJECT_CODE,
        note="Bukti potong DEMO Fase 49 (terbit otomatis dari pembayaran tagihan).")
    await db.withholding_docs.update_one({"id": doc["id"], "org_id": org},
                                         {"$set": {"demo_batch": BATCH}})
    return {"bill": updated.get("vendor"), "cash_out": amount - withheld,
            "withheld": withheld, "bupot": doc.get("number"), "created": True}


async def seed_phase49(org_id: str = ORG_ID) -> dict:
    identity = await _tax_identity(org_id)
    faktur = await _faktur(org_id)
    bill = await _bill_paid_with_withholding(org_id)
    out = {"tax_identity": identity or "sudah diisi", "faktur": faktur.get("number"),
           "bupot": bill.get("bupot"), "withheld": bill.get("withheld")}
    if identity or faktur.get("created") or bill.get("created"):
        logger.info("Seed Fase 49: %s", out)
    return out
