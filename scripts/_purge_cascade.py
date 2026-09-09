"""_purge_cascade — turunan deal yang lahir di fase belakangan (booking fee titipan Fase 75–78,
bukti bayar, WA doc share). Fixture gate lama membuang lead/deal tetapi tidak tahu koleksi ini,
sehingga forensic_audit menemukan baris YATIM (booking_fee_invoices → deal tidak ada).
Dipanggil setiap fixture purge SEBELUM deals dihapus (butuh id-nya)."""

DEAL_CHILDREN = ("booking_fee_invoices", "customer_deposits", "receipts", "payment_intakes",
                 "contract_liabilities", "wa_doc_shares")


def purge_deal_children(db, deal_ids: list, lead_ids: list = None) -> dict:
    deal_ids = list(deal_ids or [])
    lead_ids = list(lead_ids or [])
    out = {}
    if not deal_ids and not lead_ids:
        return out
    q_deal = {"deal_id": {"$in": deal_ids}}
    receipts = [r["id"] for r in db.receipts.find(q_deal, {"_id": 0, "id": 1})] if deal_ids else []
    bf = [r["id"] for r in db.booking_fee_invoices.find(q_deal, {"_id": 0, "id": 1})] if deal_ids else []
    deps = [r["id"] for r in db.customer_deposits.find(q_deal, {"_id": 0, "id": 1})] if deal_ids else []
    if deal_ids:
        for coll in DEAL_CHILDREN:
            out[coll] = db[coll].delete_many(q_deal).deleted_count
        out["journal_entries"] = db.journal_entries.delete_many({"$or": [
            {"source_id": {"$in": receipts + bf + deps + deal_ids}},
            {"source_deal_id": {"$in": deal_ids}},
        ]}).deleted_count
    if lead_ids:
        out["lead_capture_events"] = db.lead_capture_events.delete_many(
            {"lead_id": {"$in": lead_ids}}).deleted_count
        out["conversion_events"] = db.conversion_events.delete_many(
            {"lead_id": {"$in": lead_ids}}).deleted_count
        out["wa_doc_shares_lead"] = db.wa_doc_shares.delete_many(
            {"entity_type": "lead", "entity_id": {"$in": lead_ids}}).deleted_count
    return out
