#!/usr/bin/env python3
"""_fixture56.py — pembersih jejak bahan uji Fase 56 (pembatalan & refund).

Aturan repo: **gate & POC tidak boleh meninggalkan jejak.** POC/gate Fase 56 menjalankan
rantai penuh (lead → reservasi → booking → pembeli → kontrak → pembayaran → pembatalan →
refund), sehingga ia membuat: lead, deal, kontrak, pembeli, kwitansi, AR, dokumen (SPR/BAP),
**pengajuan pembatalan**, dan **jurnal** (uang muka, potongan, utang refund, pembayaran
refund). Kalau jejaknya ditinggal:

  * `verify_data_integrity` menemukan tugas/aktivitas menggantung;
  * `verify_closing` menyatakan bulan berjalan tidak bersih (ada jurnal tanpa sumber);
  * saldo `2-1460 Utang Refund Pembatalan` berdiri untuk pembeli yang tidak pernah ada;
  * unit bahan uji tidak kembali ke stok, sehingga layar demo kehabisan rumah.

Yang dibuang HANYA yang berciri bahan uji: nama lead diawali `POC56`.

Pakai:
    python3 scripts/_fixture56.py             # bersihkan + laporkan
    python3 scripts/_fixture56.py --periksa    # hanya melaporkan
"""
import os
import sys

from dotenv import load_dotenv
from pymongo import MongoClient

import _purge_cascade as _cascade

load_dotenv("/app/backend/.env")
PREFIX = "POC56"


def _db():
    return MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def purge(dry: bool = False) -> dict:
    db = _db()
    lead_ids = [x["id"] for x in db.leads.find({"name": {"$regex": f"^{PREFIX}"}},
                                               {"_id": 0, "id": 1})]
    deals = list(db.deals.find({"lead_id": {"$in": lead_ids}},
                               {"_id": 0, "id": 1, "unit_id": 1}))
    deal_ids = [d["id"] for d in deals]
    unit_ids = [d["unit_id"] for d in deals if d.get("unit_id")]
    contracts = list(db.contracts.find({"deal_id": {"$in": deal_ids}},
                                       {"_id": 0, "id": 1, "customer_id": 1}))
    contract_ids = [c["id"] for c in contracts]
    cust_ids = [c["id"] for c in db.customers.find(
        {"id": {"$in": [c["customer_id"] for c in contracts if c.get("customer_id")]},
         "name": {"$regex": f"^{PREFIX}"}}, {"_id": 0, "id": 1})]
    cancels = list(db.cancellations.find({"deal_id": {"$in": deal_ids}},
                                         {"_id": 0, "id": 1, "refund_payments": 1}))
    cancel_ids = [c["id"] for c in cancels]
    # Jurnal pembayaran refund memakai `source_id` = id PEMBAYARAN (bukan id pengajuan),
    # supaya dua pembayaran pada satu pembatalan tetap bisa dibedakan. Karena itu id-nya
    # harus dikumpulkan dari dalam dokumen — kalau tidak, jurnalnya tertinggal yatim.
    payment_ids = [p["id"] for c in cancels for p in (c.get("refund_payments") or [])
                   if p.get("id")]
    receipt_ids = [r["id"] for r in db.receipts.find({"deal_id": {"$in": deal_ids}},
                                                     {"_id": 0, "id": 1})] if deal_ids else []
    owner_ids = lead_ids + cust_ids + deal_ids + contract_ids
    file_rows = list(db.files.find({"owner_id": {"$in": owner_ids}},
                                   {"_id": 0, "id": 1, "path": 1})) if owner_ids else []
    hitung = {
        "leads": len(lead_ids), "deals": len(deal_ids), "contracts": len(contract_ids),
        "customers": len(cust_ids), "pembatalan": len(cancel_ids),
        "pembayaran_refund": len(payment_ids), "units_dilepas": len(set(unit_ids)),
        "kwitansi": len(receipt_ids), "berkas": len(file_rows),
        "akun_portal": (db.portal_users.count_documents({"customer_id": {"$in": cust_ids}})
                        if cust_ids else 0),
    }
    if dry:
        return hitung
    if deal_ids:
        _cascade.purge_deal_children(db, deal_ids, lead_ids)
        for coll in ("documents", "ar_invoices", "receipts", "tax_records",
                     "contract_liabilities", "customer_deposits", "financing_apps",
                     "commissions", "revenue_recognitions", "quotations",
                     "payment_intakes", "cancellations"):
            db[coll].delete_many({"deal_id": {"$in": deal_ids}})
        db.journal_entries.delete_many({"$or": [
            {"source_type": "receipt", "source_id": {"$in": receipt_ids}},
            {"source_type": "cancellation", "source_id": {"$in": cancel_ids}},
            {"source_type": "cancellation_refund", "source_id": {"$in": payment_ids}},
            {"source_type": "contract", "source_id": {"$in": contract_ids}},
            {"source_deal_id": {"$in": deal_ids}},
        ]})
        db.events.delete_many({"entity_id": {"$in": deal_ids + cust_ids + cancel_ids}})
        db.contracts.delete_many({"id": {"$in": contract_ids}})
        db.customers.delete_many({"id": {"$in": cust_ids}})
        db.deals.delete_many({"id": {"$in": deal_ids}})
    db.quotations.delete_many({"lead_id": {"$in": lead_ids}})
    db.tasks.delete_many({"related_entity_id": {
        "$in": lead_ids + cust_ids + deal_ids + contract_ids + cancel_ids}})
    db.notifications.delete_many({"related_entity_id": {"$in": cancel_ids}})
    db.activities.delete_many({"entity_id": {"$in": lead_ids + cust_ids + deal_ids}})
    db.doc_submissions.delete_many({"entity_id": {"$in": lead_ids + cust_ids}})
    if file_rows:
        db.files.delete_many({"id": {"$in": [f["id"] for f in file_rows]}})
        jalur = [f.get("path") for f in file_rows if f.get("path")]
        if jalur:
            db.file_blobs.delete_many({"path": {"$in": jalur}})
    db.leads.delete_many({"id": {"$in": lead_ids}})
    # Login OTP portal melahirkan baris `portal_users`. Membuang pembelinya tanpa membuang
    # akun portalnya meninggalkan akun YATIM — dan itu temuan CRITICAL di `forensic_audit`
    # (integritas referensial portal_users → customers) yang membuat lima gate lain merah
    # tanpa ada hubungannya dengan fase ini.
    if cust_ids:
        db.portal_users.delete_many({"customer_id": {"$in": cust_ids}})
    for uid in set(unit_ids):
        db.units.update_one({"id": uid}, {"$set": {
            "status": "available", "payment_status": "none",
            "reserved_by_deal": None, "booked_by_deal": None, "sold_by_deal": None,
            "sold_at": None, "deal_id": None, "lead_id": None, "lead_name": None,
            "customer_id": None, "contract_id": None}})
        db.build_schedules.update_many({"unit_id": uid}, {"$set": {
            "deal_id": None, "lead_id": None, "lead_name": None,
            "customer_id": None, "customer_name": None}})
    return hitung


def main() -> int:
    dry = "--periksa" in sys.argv
    hasil = purge(dry=dry)
    print(f"Bahan uji Fase 56 {'AKAN dibuang' if dry else 'dibuang'}: {hasil}")
    if not dry:
        db = _db()
        print(f"Unit tersedia sekarang: {db.units.count_documents({'status': 'available'})}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
