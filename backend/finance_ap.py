"""Thin AP (tagihan vendor/subkon) — dipisah dari finance_engine.py demi batas NFR 800 baris.
Tetap diekspos lewat `finance_engine.create_ap_bill/approve_ap_bill/pay_ap_bill/
ap_retention_release_sweeper` supaya pemanggil lama tidak berubah.
"""
from db import db, ORG_ID
from core_utils import new_id, now_iso
from engine import emit


async def create_ap_bill(vendor, project_id, claimed, retention_pct, due_date, note, actor, org_id=ORG_ID) -> dict:
    from finance_engine import notify_finance
    claimed = int(claimed)
    retention_pct = float(retention_pct or 0)
    retention_held = round(claimed * retention_pct / 100)
    net = claimed - retention_held
    ts = now_iso()
    doc = {
        "id": new_id(), "org_id": org_id, "vendor": vendor, "project_id": project_id,
        "claimed": claimed, "retention_pct": retention_pct, "retention_held": retention_held,
        "net": net, "paid": 0, "outstanding": net, "status": "pending_approval",
        "due_date": due_date, "note": note, "retention_released": False,
        "approved_by": None, "approved_at": None, "created_by": actor,
        "created_at": ts, "updated_at": ts}
    await db.ap_invoices.insert_one(dict(doc))
    await emit("ap.bill_created", "ap_bill", doc["id"], {"net": net}, org_id=org_id)
    await notify_finance(org_id, "Tagihan AP baru",
                         f"{vendor}: klaim Rp {claimed:,}, net Rp {net:,} (retensi {retention_pct}%). Menunggu approval.",
                         "finance", "ap_bill", doc["id"])
    doc.pop("_id", None)
    return doc


async def approve_ap_bill(bill_id, approver, org_id=ORG_ID) -> dict:
    from finance_engine import notify_finance
    bill = await db.ap_invoices.find_one({"id": bill_id, "org_id": org_id}, {"_id": 0})
    if not bill:
        raise ValueError("Tagihan AP tidak ditemukan.")
    if bill.get("status") != "pending_approval":
        raise ValueError("Tagihan sudah diproses (bukan status menunggu approval).")
    ts = now_iso()
    await db.ap_invoices.update_one({"id": bill_id},
        {"$set": {"status": "approved", "approved_by": approver, "approved_at": ts, "updated_at": ts}})
    await emit("ap.approved", "ap_bill", bill_id, {}, org_id=org_id)
    await notify_finance(org_id, "Tagihan AP disetujui",
                         f"{bill.get('vendor')}: net Rp {bill.get('net', 0):,} siap dibayar.",
                         "finance", "ap_bill", bill_id)
    return await db.ap_invoices.find_one({"id": bill_id, "org_id": org_id}, {"_id": 0})


async def pay_ap_bill(bill_id, amount, note, actor, org_id=ORG_ID, withhold: dict = None,
                      return_payment: bool = False, cash_account_id: str = None):
    """Bayar tagihan AP. `withhold` (Fase 49F) memotong PPh dari kas yang keluar.

    Tanpa fitur ini, potongan PPh jasa konstruksi/PPh 23 hanya bisa dicatat di luar sistem,
    sehingga bukti potong yang diterbitkan tidak punya pasangan di pembukuan dan vendor
    dibayar bruto padahal kewajiban setornya ada di kita. `withhold` berisi
    `{kind, base, rate, amount, memo}` — nilai potongan dihitung pemanggil (router) supaya
    tarif & dasar yang dipakai TERBACA di layar sebelum uang keluar.
    """
    from finance_engine import notify_finance
    bill = await db.ap_invoices.find_one({"id": bill_id, "org_id": org_id}, {"_id": 0})
    if not bill:
        raise ValueError("Tagihan AP tidak ditemukan.")
    if bill.get("status") not in ("approved", "partial"):
        raise ValueError("Tagihan harus disetujui terlebih dahulu sebelum dibayar.")
    amount = int(amount)
    if amount <= 0:
        raise ValueError("Nominal pembayaran harus lebih dari 0.")
    withheld = int((withhold or {}).get("amount", 0) or 0)
    if withheld < 0:
        raise ValueError("Potongan PPh tidak boleh negatif.")
    if withheld >= amount:
        raise ValueError(f"Potongan PPh Rp {withheld:,} tidak boleh sama dengan atau melebihi "
                         f"nilai pembayaran Rp {amount:,}.")
    outstanding_before = int(bill.get("net", 0)) - int(bill.get("paid", 0))
    if amount > outstanding_before:
        # Fase 26: dulu tidak ada guard -> paid bisa > net dan akun 2-1100 jadi negatif.
        raise ValueError(f"Pembayaran Rp {amount:,} melebihi sisa tagihan "
                         f"Rp {outstanding_before:,} untuk {bill.get('vendor')}.")
    paid = bill.get("paid", 0) + amount
    outstanding = bill.get("net", 0) - paid
    status = "paid" if outstanding <= 0 else "partial"
    ts = now_iso()
    import cash_bank as _cb
    cash_code = await _cb.resolve_code(org_id, cash_account_id, "1-1200")
    cash_acc = await _cb.account_by_code(org_id, cash_code)
    cash_account_id = (cash_acc or {}).get("id")
    await db.ap_invoices.update_one({"id": bill_id}, {"$set": {
        "paid": paid, "outstanding": max(0, outstanding), "status": status, "updated_at": ts},
        "$inc": {"withheld_total": withheld}})
    payment = {
        "id": new_id(), "org_id": org_id, "bill_id": bill_id, "vendor": bill.get("vendor"),
        "amount": amount, "cash_out": amount - withheld, "withheld_amount": withheld,
        "withheld_kind": (withhold or {}).get("kind"),
        "withheld_base": int((withhold or {}).get("base", 0) or 0),
        "withheld_rate": float((withhold or {}).get("rate", 0) or 0),
        "cash_account_id": cash_account_id, "cash_account_name": (cash_acc or {}).get("name"),
        "cash_account_code": cash_code,
        "note": note, "actor": actor, "created_at": ts,
    }
    await db.payments_out.insert_one(dict(payment))
    payment.pop("_id", None)
    await emit("ap.paid", "ap_bill", bill_id,
               {"amount": amount, "withheld": withheld, "cash_account_id": cash_account_id,
                "withheld_memo": (withhold or {}).get("memo")}, org_id=org_id)
    body = f"Bayar Rp {amount:,} ke {bill.get('vendor')}. Sisa Rp {max(0, outstanding):,}."
    if withheld:
        body += f" Dipotong PPh Rp {withheld:,} (kas keluar Rp {amount - withheld:,})."
    await notify_finance(org_id, "Pembayaran AP", body, "finance", "ap_bill", bill_id)
    updated = await db.ap_invoices.find_one({"id": bill_id, "org_id": org_id}, {"_id": 0})
    return (updated, payment) if return_payment else updated


async def ap_retention_release_sweeper(org_id=ORG_ID) -> int:
    """Lepas retensi AP yang sudah lewat release_due_at (bila di-set). Fase awal: no-op aman."""
    from finance_engine import notify_finance
    released = 0
    cur = await db.ap_invoices.find({
        "org_id": org_id, "retention_released": False,
        "release_due_at": {"$ne": None, "$lt": now_iso()}}).to_list(1000)
    for b in cur:
        ts = now_iso()
        await db.ap_invoices.update_one({"id": b["id"]}, {"$set": {"retention_released": True, "updated_at": ts}})
        await db.payments_out.insert_one({
            "id": new_id(), "org_id": org_id, "bill_id": b["id"], "vendor": b.get("vendor"),
            "amount": b.get("retention_held", 0), "note": "Pelepasan retensi", "actor": "system", "created_at": ts})
        await notify_finance(org_id, "Retensi dilepas",
                             f"Retensi Rp {b.get('retention_held', 0):,} untuk {b.get('vendor')} dilepas.",
                             "finance", "ap_bill", b["id"])
        released += 1
    return released
