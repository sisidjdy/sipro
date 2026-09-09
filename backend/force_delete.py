"""HAPUS PAKSA transaksi (deal) beserta seluruh turunannya — hanya peran akses penuh, wajib alasan.

Berbeda dengan `master_delete` (menolak bila ada jejak transaksi), modul ini MENGHAPUS jejaknya:
deal → AR + kuitansi + jurnal, booking fee (tagihan/kuitansi/titipan), invoice & kuitansi biaya
all-in, penyaluran, beban AP, kontrak + dokumen, komisi, pajak, KPR, penawaran, kupon dilepas,
peristiwa/tugas/notifikasi; unit dikembalikan `available`, lead dilepas dari unit.
Setiap pemanggilan tercatat di audit log oleh router.
"""
import re

from core_utils import now_iso
from db import db
from rbac import FULL_ACCESS_ROLES


def may_force(user: dict) -> bool:
    return (user or {}).get("role") in FULL_ACCESS_ROLES


# Koleksi yang berkunci `deal_id`.
DEAL_CHILD_COLLECTIONS = (
    "ar_invoices", "receipts", "booking_fee_invoices", "customer_deposits", "contract_liabilities",
    "revenue_recognitions", "tax_records", "commissions", "financing_apps", "payment_intakes",
    "cost_invoices", "cost_receipts", "cost_disbursements", "cost_expenses", "allin_amendments",
    "kpr_disbursements", "cancellations", "late_fees", "warning_letters", "coupon_redemptions",
    "unit_handovers", "refund_debts", "pdc_cheques",
)
CONTRACT_CHILD_COLLECTIONS = ("documents", "doc_submissions", "doc_shares", "wa_doc_shares",
                              "kpr_stages", "contract_documents")


async def _ids(coll: str, q: dict) -> list:
    try:
        return [r["id"] for r in await db[coll].find(q, {"_id": 0, "id": 1}).to_list(5000) if r.get("id")]
    except Exception:  # noqa: BLE001
        return []


async def _del(coll: str, q: dict, removed: dict) -> None:
    try:
        n = (await db[coll].delete_many(q)).deleted_count
    except Exception:  # noqa: BLE001
        return
    if n:
        removed[coll] = removed.get(coll, 0) + n


async def footprint(org: str, deal_id: str) -> dict:
    """Berapa banyak data turunan yang akan ikut terhapus — ditampilkan sebelum konfirmasi."""
    out = {}
    for coll in DEAL_CHILD_COLLECTIONS:
        try:
            n = await db[coll].count_documents({"org_id": org, "deal_id": deal_id})
        except Exception:  # noqa: BLE001
            n = 0
        if n:
            out[coll] = n
    n = await db.contracts.count_documents({"org_id": org, "deal_id": deal_id})
    if n:
        out["contracts"] = n
    n = await db.journal_entries.count_documents({"org_id": org, **_journal_q(deal_id, [])})
    if n:
        out["journal_entries"] = n
    return out


def _journal_q(deal_id: str, source_ids: list) -> dict:
    ors = [{"source_deal_id": deal_id}, {"source_event": {"$regex": re.escape(deal_id)}}]
    if source_ids:
        ors.append({"source_id": {"$in": source_ids}})
    return {"$or": ors}


async def delete_deal_cascade(org: str, deal: dict, actor: str) -> dict:
    did = deal["id"]
    removed = {}
    ts = now_iso()
    # Jurnal: semua yang bersumber dari dokumen turunan deal ini (kuitansi, titipan, biaya, AP, komisi).
    source_ids = [did]
    for coll in ("receipts", "cost_receipts", "cost_disbursements", "cost_expenses", "commissions",
                 "booking_fee_invoices", "customer_deposits", "ar_invoices", "cost_invoices", "kpr_disbursements"):
        source_ids += await _ids(coll, {"org_id": org, "deal_id": did})
    exp = await db.cost_expenses.find({"org_id": org, "deal_id": did}, {"_id": 0, "ap_bill_id": 1}).to_list(100)
    ap_ids = [e["ap_bill_id"] for e in exp if e.get("ap_bill_id")]
    source_ids += ap_ids
    await _del("journal_entries", {"org_id": org, **_journal_q(did, source_ids)}, removed)
    if ap_ids:
        await _del("ap_invoices", {"org_id": org, "id": {"$in": ap_ids}}, removed)
        await _del("payments_out", {"org_id": org, "ap_invoice_id": {"$in": ap_ids}}, removed)
    # Kupon: kuota dikembalikan sebelum jejaknya dihapus.
    async for r in db.coupon_redemptions.find({"org_id": org, "ref_type": "deal", "ref_id": did, "state": "used"}):
        await db.coupons.update_one({"id": r["coupon_id"], "used_count": {"$gt": 0}}, {"$inc": {"used_count": -1}})
    await _del("coupon_redemptions", {"org_id": org, "ref_type": "deal", "ref_id": did}, removed)
    # Kontrak + turunannya.
    for cid in await _ids("contracts", {"org_id": org, "deal_id": did}):
        for coll in CONTRACT_CHILD_COLLECTIONS:
            await _del(coll, {"org_id": org, "contract_id": cid}, removed)
        await _del("documents", {"org_id": org, "deal_id": did}, removed)
    await _del("contracts", {"org_id": org, "deal_id": did}, removed)
    for coll in DEAL_CHILD_COLLECTIONS:
        await _del(coll, {"org_id": org, "deal_id": did}, removed)
    await _del("quotations", {"org_id": org, "converted_deal_id": did}, removed)
    for coll, f1, f2 in (("activities", "entity_type", "entity_id"), ("tasks", "related_entity_type", "related_entity_id"),
                         ("notifications", "related_entity_type", "related_entity_id")):
        await _del(coll, {"org_id": org, f1: "deal", f2: did}, removed)
    await _del("events", {"org_id": org, "entity_id": did}, removed)
    # Unit kembali tersedia; ikatan ke deal/lead/pembeli/kontrak dilepas.
    await db.units.update_one({"id": deal.get("unit_id"), "org_id": org}, {
        "$set": {"status": "available", "payment_status": "none", "reserved_by_deal": None,
                 "booked_by_deal": None, "sold_by_deal": None, "updated_at": ts},
        "$unset": {"deal_id": "", "lead_id": "", "lead_name": "", "customer_id": "", "contract_id": "", "sold_at": ""}})
    await db.build_schedules.update_many({"org_id": org, "unit_id": deal.get("unit_id")},
                                         {"$unset": {"deal_id": "", "lead_id": "", "customer_id": ""}})
    await db.leads.update_one({"id": deal.get("lead_id"), "org_id": org},
                              {"$unset": {"unit_id": "", "deal_id": ""}, "$set": {"updated_at": ts}})
    await db.deals.delete_one({"id": did, "org_id": org})
    removed["deals"] = 1
    return {"id": did, "unit_code": deal.get("unit_code"), "deleted": True, "removed": removed,
            "deleted_by": actor, "deleted_at": ts}


async def delete_deals_of(org: str, q: dict, actor: str) -> dict:
    """Hapus paksa semua deal yang cocok (dipakai hapus paksa lead/customer/unit/proyek)."""
    removed = {}
    async for d in db.deals.find({"org_id": org, **q}, {"_id": 0}):
        out = await delete_deal_cascade(org, d, actor)
        for k, v in out["removed"].items():
            removed[k] = removed.get(k, 0) + v
    return removed


async def delete_receipt(org: str, receipt: dict, actor: str) -> dict:
    """Hapus SATU pembayaran (kuitansi) beserta jurnalnya; alokasi termin & titipan dibalik."""
    rid = receipt["id"]
    did = receipt.get("deal_id")
    removed = {}
    kind = receipt.get("kind") or "ar"
    if kind == "booking_fee":
        inv = await db.booking_fee_invoices.find_one({"org_id": org, "deal_id": did}, {"_id": 0})
        if inv:
            paid = max(0, int(inv.get("paid") or 0) - int(receipt.get("amount") or 0))
            await db.booking_fee_invoices.update_one({"id": inv["id"]}, {
                "$set": {"paid": paid, "outstanding": int(inv["amount"]) - paid,
                         "status": "paid" if paid >= int(inv["amount"]) else ("partial" if paid else "unpaid"),
                         "paid_at": None if paid < int(inv["amount"]) else inv.get("paid_at"), "updated_at": now_iso()},
                "$pull": {"receipt_ids": rid}})
            await db.deals.update_one({"id": did}, {"$set": {"booking_fee_status": "recorded" if paid else "unverified"}})
        await db.customer_deposits.update_one({"org_id": org, "deal_id": did}, {
            "$inc": {"balance": -int(receipt.get("deposit_amount") or receipt.get("amount") or 0),
                     "received_total": -int(receipt.get("amount") or 0)},
            "$pull": {"entries": {"receipt_id": rid}}})
    else:
        inv = await db.ar_invoices.find_one({"org_id": org, "deal_id": did}, {"_id": 0})
        if inv:
            items = inv.get("items") or []
            for al in receipt.get("allocations") or []:
                it = next((x for x in items if x.get("id") == al.get("item_id")), None)
                if it:
                    it["paid_amount"] = max(0, int(it.get("paid_amount") or 0) - int(al.get("amount") or 0))
                    it["status"] = "paid" if it["paid_amount"] >= int(it["amount"]) else ("partial" if it["paid_amount"] else "unpaid")
            paid = sum(int(i.get("paid_amount") or 0) for i in items)
            await db.ar_invoices.update_one({"id": inv["id"]}, {"$set": {
                "items": items, "paid": paid, "outstanding": int(inv["total"]) - paid,
                "status": "paid" if paid >= int(inv["total"]) else ("partial" if paid else "unpaid"),
                "updated_at": now_iso()}})
            await db.units.update_one({"id": inv.get("unit_id")}, {"$set": {
                "payment_status": "paid_off" if paid >= int(inv["total"]) else ("partial" if paid else "booking_fee")}})
        if int(receipt.get("deposit_amount") or 0) and receipt.get("funding") != "deposit":
            await db.customer_deposits.update_one({"org_id": org, "deal_id": did}, {
                "$inc": {"balance": -int(receipt["deposit_amount"])}, "$pull": {"entries": {"receipt_id": rid}}})
        if receipt.get("funding") == "deposit":
            await db.customer_deposits.update_one({"org_id": org, "deal_id": did}, {
                "$inc": {"balance": int(receipt.get("applied") or receipt.get("amount") or 0),
                         "applied_total": -int(receipt.get("applied") or receipt.get("amount") or 0)},
                "$pull": {"entries": {"receipt_id": rid}}})
    await _del("journal_entries", {"org_id": org, "$or": [{"source_id": rid}, {"source_event": {"$regex": re.escape(rid)}}]}, removed)
    await _del("payment_intakes", {"org_id": org, "receipt_id": rid}, removed)
    await db.receipts.delete_one({"id": rid, "org_id": org})
    removed["receipts"] = 1
    return {"id": rid, "receipt_no": receipt.get("receipt_no"), "deleted": True, "removed": removed, "deleted_by": actor}
