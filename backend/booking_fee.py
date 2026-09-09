"""BOOKING FEE SEBAGAI KOMPONEN PEMBAYARAN TERPISAH (Fase 69B).

Cacat yang ditutup: booking fee hanya angka di `deals.booking_fee` — tidak ada tagihan, tidak
ada kwitansi, tidak ada status lunas/belum. Padahal ia dibayar PALING AWAL (saat keep unit)
dan menjadi syarat langkah berikutnya.

Sekarang: reservasi dengan booking fee > 0 melahirkan TAGIHAN (`booking_fee_invoices`,
nomor INV-BF); pembayaran melahirkan KWITANSI bernomor di `receipts` (kind=`booking_fee`) dan
dibukukan sebagai TITIPAN pelanggan (2-1450) lewat mesin titipan yang sudah ada — sehingga saat
booking dikonfirmasi, titipan itu bisa dialihkan ke termin (status `applied`). Tidak ada kas
yang tercatat tanpa jurnal.
"""
import logging

import sequences as seq
import settings_store as cfg
from core_utils import due_in, new_id, now_iso
from db import db
from engine import add_activity, emit

logger = logging.getLogger("sipro.booking_fee")


async def create_invoice(org: str, deal: dict, actor: str) -> dict:
    amount = int(deal.get("booking_fee") or 0)
    if amount <= 0:
        return None
    if await db.booking_fee_invoices.find_one({"org_id": org, "deal_id": deal["id"]}, {"_id": 1}):
        return await get_invoice(org, deal["id"])
    ts = now_iso()
    # Batas bayar DIKONFIGURASI (`booking_fee.due_days`), tidak melewati masa keep unit.
    due_days = int(await cfg.get("booking_fee.due_days", org_id=org) or 3)
    due = due_in(days=due_days)
    if deal.get("reserved_until") and str(deal["reserved_until"]) < due:
        due = str(deal["reserved_until"])
    inv = {
        "id": new_id(), "org_id": org,
        "no": await seq.next_number("booking_fee_invoice", org, prefix="INV-BF",
                                    context={"unit_id": deal.get("unit_id"),
                                             "customer_id": deal.get("customer_id")}),
        "deal_id": deal["id"], "unit_id": deal.get("unit_id"), "unit_code": deal.get("unit_code"),
        "lead_id": deal.get("lead_id"), "lead_name": deal.get("lead_name"),
        "project_id": deal.get("project_id"), "assigned_to": deal.get("assigned_to"),
        "amount": amount, "paid": 0, "outstanding": amount, "status": "unpaid",
        "due_date": due, "paid_at": None, "receipt_ids": [],
        "refunded_total": 0, "forfeited_total": 0, "refunds": [],
        "created_by": actor, "created_at": ts, "updated_at": ts,
    }
    await db.booking_fee_invoices.insert_one(dict(inv))
    await db.deals.update_one({"id": deal["id"]}, {"$set": {
        "booking_fee_status": "unverified", "booking_fee_invoice_id": inv["id"]}})
    inv.pop("_id", None)
    return inv


async def get_invoice(org: str, deal_id: str) -> dict:
    return await db.booking_fee_invoices.find_one({"org_id": org, "deal_id": deal_id}, {"_id": 0})


async def detail(org: str, deal_id: str) -> dict:
    inv = await get_invoice(org, deal_id)
    receipts = await db.receipts.find({"org_id": org, "deal_id": deal_id, "kind": "booking_fee"},
                                      {"_id": 0}).sort("created_at", 1).to_list(50)
    deal = await db.deals.find_one({"id": deal_id, "org_id": org},
                                   {"_id": 0, "status": 1, "reserved_until": 1}) or {}
    intakes = await db.payment_intakes.find({"org_id": org, "deal_id": deal_id,
                                             "kind": "booking_fee"},
                                            {"_id": 0}).sort("created_at", -1).to_list(20)
    return {"invoice": inv, "receipts": receipts, "deal_status": deal.get("status"),
            "proofs": intakes, "refund": refund_summary(inv, deal) if inv else None}


async def portal_view(org: str, deal_id: str) -> dict:
    """Potongan yang boleh DIBACA PEMBELI: tagihan, kwitansi, status buktinya, refund."""
    d = await detail(org, deal_id)
    if not d["invoice"]:
        return None
    return {"invoice": d["invoice"], "receipts": d["receipts"],
            "proofs": [{k: p.get(k) for k in ("id", "amount", "transfer_date", "state",
                                              "state_label", "reject_reason", "created_at")}
                       for p in d["proofs"]],
            "refunds": (d.get("refund") or {}).get("refunds") or []}



def refund_summary(inv: dict, deal: dict) -> dict:
    """Berapa yang sudah dibayar, dikembalikan, hangus — dan berapa yang MASIH bisa dikembalikan."""
    paid = int(inv.get("paid") or 0)
    refunded = int(inv.get("refunded_total") or 0)
    forfeited = int(inv.get("forfeited_total") or 0)
    refundable = max(0, paid - refunded - forfeited)
    eligible = deal.get("status") in ("cancelled", "expired") and refundable > 0
    return {"paid": paid, "refunded_total": refunded, "forfeited_total": forfeited,
            "refundable": refundable, "eligible": eligible,
            "refunds": inv.get("refunds") or [],
            "blocked_reason": (None if eligible else
                               ("Tidak ada sisa booking fee yang bisa dikembalikan."
                                if refundable <= 0 else
                                "Refund hanya untuk deal yang dibatalkan/kedaluwarsa."))}


async def pay(org: str, deal_id: str, *, amount: int, method: str, note: str, actor: str) -> dict:
    """Terima booking fee → kwitansi bernomor + titipan pelanggan berjurnal + status tagihan."""
    from finance_engine import _deposit_move, notify_finance
    inv = await get_invoice(org, deal_id)
    if not inv:
        raise ValueError("Deal ini tidak memiliki tagihan booking fee.")
    if inv["status"] == "cancelled":
        raise ValueError("Tagihan booking fee sudah dibatalkan.")
    if inv["status"] == "paid":
        raise ValueError("Booking fee sudah LUNAS.")
    amount = int(amount or 0)
    if amount <= 0:
        raise ValueError("Nominal pembayaran harus lebih dari 0.")
    if amount > int(inv["outstanding"]):
        raise ValueError(f"Nominal Rp {amount:,} melebihi sisa tagihan booking fee "
                         f"Rp {int(inv['outstanding']):,}.".replace(",", "."))
    ts = now_iso()
    receipt = {
        "id": new_id(), "org_id": org, "kind": "booking_fee",
        "receipt_no": await seq.next_number("receipt", org, prefix="KWT",
                                            context={"unit_id": inv.get("unit_id")}),
        "deal_id": deal_id, "unit_id": inv.get("unit_id"), "unit_code": inv.get("unit_code"),
        "booking_fee_invoice_id": inv["id"], "invoice_no": inv["no"],
        "amount": amount, "applied": 0, "deposit_amount": amount, "funding": "cash",
        "method": method or "transfer", "note": note,
        "allocations": [{"item_id": None, "label": f"Booking fee ({inv['no']})", "amount": amount}],
        "actor": actor, "created_at": ts,
    }
    await db.receipts.insert_one(dict(receipt))
    receipt.pop("_id", None)
    ctx = {"unit_id": inv.get("unit_id"), "unit_code": inv.get("unit_code"),
           "customer_name": inv.get("lead_name")}
    deposit = await _deposit_move(org, deal_id, ctx, "in", amount,
                                  f"Booking fee {inv['no']}", actor, receipt_id=receipt["id"])
    paid = int(inv["paid"]) + amount
    outstanding = int(inv["amount"]) - paid
    status = "paid" if outstanding <= 0 else "partial"
    await db.booking_fee_invoices.update_one({"id": inv["id"]}, {
        "$set": {"paid": paid, "outstanding": outstanding, "status": status, "updated_at": ts,
                 "paid_at": ts if status == "paid" else None},
        "$push": {"receipt_ids": receipt["id"]}})
    await db.deals.update_one({"id": deal_id}, {"$set": {
        "booking_fee_status": "verified" if status == "paid" else "recorded",
        "booking_fee_paid_at": ts if status == "paid" else None, "updated_at": ts}})
    await add_activity(entity_type="lead", entity_id=inv.get("lead_id"), type="finance",
                       actor=actor, org_id=org,
                       body=(f"Booking fee {inv['no']} unit {inv.get('unit_code')} diterima "
                             f"Rp {amount:,} ({'LUNAS' if status == 'paid' else 'sebagian'}), "
                             f"kwitansi {receipt['receipt_no']}.").replace(",", "."))
    await emit("booking_fee.paid" if status == "paid" else "booking_fee.partial", "deal", deal_id,
               {"amount": amount, "receipt_id": receipt["id"]}, org_id=org)
    await notify_finance(org, "Booking fee diterima",
                         f"Rp {amount:,} booking fee unit {inv.get('unit_code') or '-'} "
                         f"({'lunas' if status == 'paid' else 'sebagian'}).",
                         "finance", "deal", deal_id, extra_emails=[inv.get("assigned_to")])
    return {"invoice": await get_invoice(org, deal_id), "receipt": receipt, "deposit": deposit}


async def cancel(org: str, deal_id: str, actor: str) -> None:
    """Deal batal: tagihan yang belum dibayar ditutup; yang sudah dibayar tetap (refund via titipan)."""
    inv = await get_invoice(org, deal_id)
    if not inv or inv["status"] == "paid":
        return
    await db.booking_fee_invoices.update_one({"id": inv["id"]}, {"$set": {
        "status": "cancelled", "cancelled_at": now_iso(), "cancelled_by": actor}})


async def block_booking_reason(org: str, deal: dict) -> str:
    """Alasan booking DITAHAN (atau None) — hanya bila organisasi menyalakan syaratnya."""
    if not await cfg.get("booking_fee.require_paid_before_booking", org_id=org):
        return None
    inv = await get_invoice(org, deal["id"])
    if inv and inv["status"] not in ("paid", "cancelled"):
        return (f"Booking fee {inv['no']} belum LUNAS (sisa Rp {int(inv['outstanding']):,}) — "
                "catat pembayarannya lebih dulu.").replace(",", ".")
    return None


async def listing(org: str, status: str = None, limit: int = 200) -> list:
    q = {"org_id": org}
    if status:
        q["status"] = status
    return await db.booking_fee_invoices.find(q, {"_id": 0}).sort("created_at", -1).to_list(limit)


# ------------------------------------------------------------------ bukti bayar dari portal
async def submit_proof(org: str, *, customer: dict, deal: dict, amount: int, transfer_date: str,
                       file_ids: list, bank_name: str = None, note: str = None,
                       actor: str = None) -> dict:
    """Klaim pembeli 'sudah transfer booking fee' — BUKAN pelunasan sampai keuangan menekan
    verifikasi (yang memanggil `pay`). Memakai wadah bukti yang sama (`payment_intakes`)."""
    from finance_engine import notify_finance
    from payment_intake import _files
    inv = await get_invoice(org, deal["id"])
    if not inv or inv["status"] in ("paid", "cancelled"):
        raise ValueError("Tidak ada tagihan booking fee yang menunggu pembayaran pada transaksi ini.")
    files = await _files(org, file_ids)
    if not files:
        raise ValueError("Bukti transfer (foto/PDF) wajib dilampirkan.")
    shas = [f.get("sha256") for f in files if f.get("sha256")]
    if shas and await db.payment_intakes.find_one(
            {"org_id": org, "file_shas": {"$in": shas}, "state": {"$ne": "rejected"}}, {"_id": 1}):
        raise ValueError("Bukti transfer ini sudah pernah dikirim — tidak perlu dikirim ulang.")
    if await db.payment_intakes.find_one({"org_id": org, "deal_id": deal["id"],
                                          "kind": "booking_fee", "state": "pending"}, {"_id": 1}):
        raise ValueError("Masih ada bukti booking fee yang menunggu verifikasi keuangan.")
    ts = now_iso()
    doc = {
        "id": new_id(), "org_id": org, "kind": "booking_fee", "deal_id": deal["id"],
        "booking_fee_invoice_id": inv["id"], "invoice_no": inv["no"],
        "customer_id": customer.get("id") if not customer.get("is_lead") else None,
        "lead_id": deal.get("lead_id"), "customer_name": customer.get("name"),
        "unit_id": deal.get("unit_id"), "unit_code": inv.get("unit_code"),
        "amount": int(amount), "transfer_date": str(transfer_date)[:10],
        "bank_name": bank_name, "note": note, "source": "portal",
        "file_ids": [f["id"] for f in files], "file_shas": shas, "files": files,
        "state": "pending", "state_label": "Menunggu verifikasi",
        "outstanding_at_submit": inv["outstanding"], "receipt_id": None, "reject_reason": None,
        "verified_by": None, "verified_at": None,
        "submitted_by": {"customer_id": customer.get("id"), "name": customer.get("name"),
                         "contact": actor or customer.get("phone") or customer.get("email")},
        "created_by": "portal", "created_at": ts, "updated_at": ts,
    }
    await db.payment_intakes.insert_one(dict(doc))
    doc.pop("_id", None)
    await notify_finance(org, "Bukti booking fee dari pembeli",
                         (f"{customer.get('name')} mengirim bukti Rp {int(amount):,} untuk "
                          f"booking fee {inv['no']} (unit {inv.get('unit_code') or '-'}). "
                          "Verifikasi satu klik di rincian deal.").replace(",", "."),
                         "finance", "payment_intake", doc["id"],
                         extra_emails=[inv.get("assigned_to")])
    await add_activity(entity_type="lead", entity_id=deal.get("lead_id"), type="finance",
                       actor=f"portal:{customer.get('name') or 'pembeli'}", org_id=org,
                       body=(f"Pembeli mengirim bukti transfer booking fee Rp {int(amount):,} "
                             "— menunggu verifikasi keuangan.").replace(",", "."))
    return doc


async def verify_proof(org: str, intake_id: str, actor: str, note: str = None) -> dict:
    """Satu klik keuangan: bukti → kwitansi + titipan + status LUNAS (lewat `pay`)."""
    from payment_intake import _tell_customer
    row = await db.payment_intakes.find_one({"id": intake_id, "org_id": org, "kind": "booking_fee"},
                                            {"_id": 0})
    if not row:
        raise ValueError("Bukti booking fee tidak ditemukan.")
    if row["state"] != "pending":
        raise ValueError("Bukti ini sudah diproses.")
    inv = await get_invoice(org, row["deal_id"])
    amount = min(int(row["amount"]), int(inv["outstanding"])) if inv else int(row["amount"])
    out = await pay(org, row["deal_id"], amount=amount, method="transfer",
                    note=note or f"Verifikasi bukti transfer pembeli ({row['transfer_date']})",
                    actor=actor)
    ts = now_iso()
    await db.payment_intakes.update_one({"id": intake_id}, {"$set": {
        "state": "verified", "state_label": "Terverifikasi", "receipt_id": out["receipt"]["id"],
        "verified_by": actor, "verified_at": ts, "verify_note": note, "updated_at": ts}})
    await _tell_customer(org, {**row, "customer_id": row.get("customer_id")},
                         (f"Bukti transfer booking fee Anda Rp {amount:,} sudah DIVERIFIKASI. "
                          f"Kwitansi {out['receipt']['receipt_no']} tersedia di Portal.")
                         .replace(",", "."))
    return {**out, "intake": await db.payment_intakes.find_one({"id": intake_id}, {"_id": 0})}


# ------------------------------------------------------------------ refund
async def refund(org: str, deal_id: str, *, amount: int, method: str, note: str, actor: str,
                 finalize: bool = False) -> dict:
    """Kembalikan booking fee deal yang batal: kas keluar berjurnal (titipan turun) + bukti
    pengembalian bernomor. `finalize` = sisa yang tidak dikembalikan dicatat HANGUS."""
    from finance_engine import _deposit_move, notify_finance
    inv = await get_invoice(org, deal_id)
    if not inv:
        raise ValueError("Deal ini tidak memiliki tagihan booking fee.")
    deal = await db.deals.find_one({"id": deal_id, "org_id": org}, {"_id": 0}) or {}
    summ = refund_summary(inv, deal)
    if not summ["eligible"]:
        raise ValueError(summ["blocked_reason"])
    amount = int(amount or 0)
    if amount < 0 or (amount == 0 and not finalize):
        raise ValueError("Nominal refund harus lebih dari 0 (atau tandai sisa sebagai hangus).")
    if amount > summ["refundable"]:
        raise ValueError(f"Nominal Rp {amount:,} melebihi sisa yang bisa dikembalikan "
                         f"Rp {summ['refundable']:,}.".replace(",", "."))
    ts = now_iso()
    rec = {"id": new_id(), "org_id": org, "kind": "booking_fee_refund",
           "receipt_no": await seq.next_number("booking_fee_refund", org, prefix="RF-BF",
                                               context={"unit_id": inv.get("unit_id")}),
           "deal_id": deal_id, "unit_id": inv.get("unit_id"), "unit_code": inv.get("unit_code"),
           "lead_name": inv.get("lead_name"), "booking_fee_invoice_id": inv["id"],
           "invoice_no": inv["no"], "amount": amount, "method": method or "transfer",
           "note": note, "forfeited": 0, "actor": actor, "created_at": ts}
    if amount > 0:
        ctx = {"unit_id": inv.get("unit_id"), "unit_code": inv.get("unit_code"),
               "customer_name": inv.get("lead_name")}
        await _deposit_move(org, deal_id, ctx, "refund", amount,
                            f"Refund booking fee {inv['no']} ({rec['receipt_no']})", actor,
                            receipt_id=rec["id"])
    forfeited = summ["refundable"] - amount if finalize else 0
    rec["forfeited"] = forfeited
    if forfeited > 0:
        # Hangus = titipan berpindah menjadi pendapatan lain-lain (tidak ada kas bergerak).
        import gl_engine as gl
        entry = await gl.post_journal(
            org, f"Booking fee hangus {inv['no']}", [
                {"account_code": "2-1450", "debit": forfeited, "credit": 0,
                 "memo": f"Titipan booking fee {inv.get('lead_name') or ''}"},
                {"account_code": "4-1200", "debit": 0, "credit": forfeited,
                 "memo": "Pendapatan lain-lain: booking fee hangus"},
            ], source_type="booking_fee_forfeit", source_id=rec["id"],
            source_event=f"bf:{inv['id']}:forfeit:{rec['id']}", posted_by=actor, auto=True,
            source_deal_id=deal_id)
        rec["forfeit_journal_id"] = entry["id"]
        await db.customer_deposits.update_one({"org_id": org, "deal_id": deal_id},
                                              {"$inc": {"balance": -forfeited}})
    await db.receipts.insert_one(dict(rec))
    rec.pop("_id", None)
    new_refunded = int(inv.get("refunded_total") or 0) + amount
    new_forfeited = int(inv.get("forfeited_total") or 0) + forfeited
    status = inv["status"]
    if new_refunded + new_forfeited >= int(inv["paid"]):
        status = "refunded" if new_refunded > 0 else "forfeited"
    await db.booking_fee_invoices.update_one({"id": inv["id"]}, {
        "$set": {"refunded_total": new_refunded, "forfeited_total": new_forfeited,
                 "status": status, "updated_at": ts},
        "$push": {"refunds": {"id": rec["id"], "receipt_no": rec["receipt_no"], "amount": amount,
                              "forfeited": forfeited, "method": rec["method"], "at": ts,
                              "actor": actor}}})
    await db.deals.update_one({"id": deal_id}, {"$set": {
        "booking_fee_status": "refunded" if new_refunded > 0 else "forfeited", "updated_at": ts}})
    await add_activity(entity_type="lead", entity_id=inv.get("lead_id"), type="finance",
                       actor=actor, org_id=org,
                       body=(f"Refund booking fee {inv['no']}: Rp {amount:,} dikembalikan"
                             + (f", Rp {forfeited:,} hangus" if forfeited else "")
                             + f" ({rec['receipt_no']}).").replace(",", "."))
    await notify_finance(org, "Refund booking fee dibayar",
                         (f"Rp {amount:,} dikembalikan untuk {inv['no']} unit "
                          f"{inv.get('unit_code') or '-'}.").replace(",", "."),
                         "finance", "deal", deal_id, extra_emails=[inv.get("assigned_to")])
    return {"invoice": await get_invoice(org, deal_id), "refund": rec}
