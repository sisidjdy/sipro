#!/usr/bin/env python3
"""_fixture53.py — pembersih jejak bahan uji Fase 53.

## Kenapa berkas ini ada

POC Fase 53 menjalankan RANTAI PENUH: lead → penawaran → reservasi → booking → pembeli →
kontrak → SPR/SPKT → akad → AJB. Artinya setiap kali dijalankan ia **memakan satu unit**
(unit berakhir `sold`) dan meninggalkan pembeli + kontrak + dokumen sintetis. Setelah
beberapa kali jalan, seluruh unit demo habis dan aplikasi jadi tidak bisa dipakai untuk
mencoba reservasi — pemakai melihatnya sebagai kerusakan, padahal itu jejak perangkat uji.

Aturan repo ini: **gate & POC tidak boleh meninggalkan jejak.** Berkas ini yang menepatinya.

Yang dibuang HANYA yang berciri bahan uji (nama lead diawali `POC53`), beserta seluruh
turunannya, lalu unitnya dikembalikan menjadi `available`.

Pakai:
    python3 scripts/_fixture53.py            # bersihkan + laporkan
    python3 scripts/_fixture53.py --periksa   # hanya melaporkan apa yang akan dibuang
"""
import os
import sys

from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv("/app/backend/.env")
PREFIX = "POC53"


def _db():
    return MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def sweep_orphans(dry: bool = False) -> dict:
    """Buang sisa MENGGANTUNG dari run POC/gate versi lama yang pembersihnya belum benar.

    ## Kenapa fungsi ini perlu ada, bukan cukup memperbaiki `purge()`

    `purge()` mencari bahan uji lewat NAMA lead (`^POC53`). Begitu run lama sudah menghapus
    lead-nya tetapi meninggalkan turunannya, tidak ada lagi nama yang bisa dijadikan pegangan
    — jejaknya menjadi **yatim**: tidak bertanda, tidak bisa ditemukan lewat lead, tetapi
    tetap membuat gate merah. Agen lanjutan yang mewarisi database seperti itu akan melihat
    7 gate merah dan mengejar cacat yang sebenarnya tidak ada di kode.

    Yang dibuang di sini HANYA rujukan yang pasti salah (bukan sekadar "kelihatan tua"):
      * jurnal yang mengaku bersumber dari kwitansi yang sudah tidak ada  -> buku besar
        menunjuk bukti yang lenyap (dicari `_fixture47.orphans()['jurnal_tanpa_kuitansi']`);
      * penawaran yang menunjuk lead yang sudah tidak ada (temuan CRITICAL `forensic_audit`);
      * tugas yang menunjuk lead/pembeli/deal/kontrak yang sudah tidak ada
        (dicari `verify_data_integrity` sebagai "tasks.related_entity_id menggantung").
    """
    db = _db()
    rec_ids = {r["id"] for r in db.receipts.find({}, {"_id": 0, "id": 1})}
    lead_ids = {x["id"] for x in db.leads.find({}, {"_id": 0, "id": 1})}
    cust_ids = {x["id"] for x in db.customers.find({}, {"_id": 0, "id": 1})}
    deal_ids = {x["id"] for x in db.deals.find({}, {"_id": 0, "id": 1})}
    ctr_ids = {x["id"] for x in db.contracts.find({}, {"_id": 0, "id": 1})}

    jr = [j["id"] for j in db.journal_entries.find(
        {"source_type": "receipt"}, {"_id": 0, "id": 1, "source_id": 1})
        if j.get("source_id") not in rec_ids]
    qo = [q["id"] for q in db.quotations.find({}, {"_id": 0, "id": 1, "lead_id": 1})
          if q.get("lead_id") and q["lead_id"] not in lead_ids]
    # Hanya jenis yang MEMANG koleksi entitas ikut disapu. `jobdesk`, `punch_item`,
    # `cash_advance`, `conversation`, dst. sengaja TIDAK disentuh: id-nya bukan id koleksi
    # ini, jadi menyapunya berarti menghapus tugas yang sah.
    known = {"lead": lead_ids, "customer": cust_ids, "deal": deal_ids, "contract": ctr_ids}
    tk = [t["id"] for t in db.tasks.find(
        {"related_entity_type": {"$in": list(known)}},
        {"_id": 0, "id": 1, "related_entity_type": 1, "related_entity_id": 1})
        if t.get("related_entity_id") not in known[t["related_entity_type"]]]

    hasil = {"jurnal_yatim": len(jr), "penawaran_yatim": len(qo), "tugas_yatim": len(tk)}
    if not dry:
        if jr:
            db.journal_entries.delete_many({"id": {"$in": jr}})
        if qo:
            db.quotations.delete_many({"id": {"$in": qo}})
        if tk:
            db.tasks.delete_many({"id": {"$in": tk}})
    return hasil


def purge(dry: bool = False) -> dict:
    db = _db()
    leads = list(db.leads.find({"name": {"$regex": f"^{PREFIX}"}}, {"_id": 0, "id": 1}))
    lead_ids = [x["id"] for x in leads]
    deals = list(db.deals.find({"lead_id": {"$in": lead_ids}}, {"_id": 0, "id": 1,
                                                               "unit_id": 1}))
    deal_ids = [d["id"] for d in deals]
    if not dry:
        import _purge_cascade as _cascade
        _cascade.purge_deal_children(db, deal_ids, lead_ids)
    unit_ids = [d["unit_id"] for d in deals if d.get("unit_id")]
    contracts = list(db.contracts.find({"deal_id": {"$in": deal_ids}},
                                       {"_id": 0, "id": 1, "customer_id": 1}))
    contract_ids = [c["id"] for c in contracts]
    cust_ids = [c["customer_id"] for c in contracts if c.get("customer_id")]
    # Pembeli hanya dibuang bila ia MEMANG lahir dari bahan uji (namanya berawalan POC53).
    cust_ids = [c["id"] for c in db.customers.find(
        {"id": {"$in": cust_ids}, "name": {"$regex": f"^{PREFIX}"}}, {"_id": 0, "id": 1})]
    # KWITANSI & JURNALNYA (Fase 54) — dikumpulkan SEBELUM apa pun dibuang.
    # Cacat yang ditutup: pembayaran DP di POC melahirkan kwitansi DAN jurnal
    # (Dr bank / Cr piutang). Dulu hanya kwitansinya yang dibuang, jurnalnya
    # ditinggal menggantung sehingga `verify_bank_recon`, `verify_portal_proof`,
    # `verify_quotation_labor` merah pada "jurnal_tanpa_kuitansi: 1" dan
    # `verify_closing` K1b ikut merah (bulan berjalan tidak lagi "bersih").
    receipt_ids = [r["id"] for r in db.receipts.find(
        {"deal_id": {"$in": deal_ids}}, {"_id": 0, "id": 1})] if deal_ids else []
    # BERKAS BUKTI (Fase 55). Gate 46 mengunggah berkas SP3K karena "gerbang menolak" saja
    # bukan bukti: gerbang yang menolak SEMUA hal terlihat sama dengan fitur yang mati.
    # Berkasnya menempel pada kontrak/deal bahan uji, jadi ia ikut dibuang — termasuk isi
    # binernya di `file_blobs`. Kalau hanya barisnya yang dibuang, byte-nya menumpuk tanpa
    # pemilik dan `forensic_audit` benar ketika menyebutnya sampah.
    owner_ids = lead_ids + cust_ids + deal_ids + contract_ids
    file_rows = list(db.files.find({"owner_id": {"$in": owner_ids}},
                                   {"_id": 0, "id": 1, "path": 1})) if owner_ids else []
    hitung = {
        "leads": len(lead_ids), "deals": len(deal_ids), "contracts": len(contract_ids),
        "customers": len(cust_ids), "units_dilepas": len(set(unit_ids)),
        "kwitansi": len(receipt_ids), "berkas": len(file_rows),
    }
    if dry:
        return hitung
    if deal_ids:
        for coll in ("documents", "ar_invoices", "receipts", "tax_records",
                     "contract_liabilities", "financing_apps", "commissions",
                     "revenue_recognitions", "quotations"):
            db[coll].delete_many({"deal_id": {"$in": deal_ids}})
        # Jurnal yang lahir dari kwitansi/kontrak bahan uji. Tanpa ini, kwitansinya
        # hilang tetapi jurnalnya tetap ada -> buku besar menunjuk bukti yang tidak
        # ada lagi (tepat yang dicari gate "jurnal_tanpa_kuitansi").
        db.journal_entries.delete_many({"$or": [
            {"source_type": "receipt", "source_id": {"$in": receipt_ids}},
            {"source_type": "contract", "source_id": {"$in": contract_ids}},
            {"source_type": "deal", "source_id": {"$in": deal_ids}},
            {"source_deal_id": {"$in": deal_ids}},
        ]})
        db.events.delete_many({"entity_id": {"$in": deal_ids + cust_ids}})
        db.contracts.delete_many({"id": {"$in": contract_ids}})
        db.customers.delete_many({"id": {"$in": cust_ids}})
        db.deals.delete_many({"id": {"$in": deal_ids}})
    # PENTING: yang di bawah ini TIDAK boleh bergantung pada adanya deal. Bila POC gagal
    # di tengah (mis. sebelum reservasi), lead + penawaran + tugasnya tetap harus terbuang;
    # dulu semuanya terkurung di dalam `if deal_ids:` sehingga run yang gagal justru
    # meninggalkan jejak paling banyak.
    #
    # Penawaran lahir dari LEAD (deal_id baru terisi setelah dikonversi), jadi ia harus
    # dicari lewat lead_id juga — inilah sumber temuan CRITICAL `forensic_audit`:
    # "quotations.<id> -> lead_id=<id> tidak ada di leads".
    db.quotations.delete_many({"lead_id": {"$in": lead_ids}})
    # Tugas menempel pada LEAD ("Hubungi lead baru: POC53 …") dan pada PEMBELI
    # ("Lengkapi berkas & KYC pembeli: POC53 …"), bukan hanya pada deal/kontrak —
    # dua tugas itulah yang dulu tertinggal dan membuat `verify_data_integrity` merah
    # pada "tasks.related_entity_id menggantung: 1".
    db.tasks.delete_many({"related_entity_id": {
        "$in": lead_ids + cust_ids + deal_ids + contract_ids}})
    db.activities.delete_many({"entity_id": {"$in": lead_ids + cust_ids + deal_ids}})
    db.doc_submissions.delete_many({"entity_id": {"$in": lead_ids + cust_ids}})
    if file_rows:
        db.files.delete_many({"id": {"$in": [f["id"] for f in file_rows]}})
        jalur = [f.get("path") for f in file_rows if f.get("path")]
        if jalur:
            db.file_blobs.delete_many({"path": {"$in": jalur}})
    db.leads.delete_many({"id": {"$in": lead_ids}})
    for uid in set(unit_ids):
        db.units.update_one({"id": uid}, {"$set": {
            "status": "available", "payment_status": "none",
            "reserved_by_deal": None, "booked_by_deal": None, "sold_by_deal": None,
            "sold_at": None, "deal_id": None, "lead_id": None, "lead_name": None,
            "customer_id": None, "contract_id": None}})
        db.build_schedules.update_many({"unit_id": uid}, {"$set": {
            "deal_id": None, "lead_id": None, "lead_name": None,
            "customer_id": None, "customer_name": None}})
    # Selalu tutup dengan menyapu yang yatim: janji berkas ini adalah "tidak meninggalkan
    # jejak", dan jejak dari run VERSI LAMA tetap jejak. Tanpa ini, satu run POC yang
    # pembersihnya masih buggy membuat 7 gate merah selamanya.
    hitung.update(sweep_orphans())
    return hitung


def main() -> int:
    dry = "--periksa" in sys.argv
    if "--sapu-yatim" in sys.argv:
        hasil = sweep_orphans(dry=dry)
        kata = "AKAN disapu" if dry else "disapu"
        print(f"Sisa yatim Fase 53 {kata}: {hasil}")
        return 0
    hasil = purge(dry=dry)
    kata = "AKAN dibuang" if dry else "dibuang"
    print(f"Bahan uji Fase 53 {kata}: {hasil}")
    if not dry:
        db = _db()
        tersedia = db.units.count_documents({"status": "available"})
        print(f"Unit tersedia sekarang: {tersedia}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
