"""Marketing Fee agen / broker / referral (Fase 27 — menutup gap kompetitor #9).

Berbeda dari `commissions` (komisi sales INTERNAL): modul ini untuk MITRA EKSTERNAL —
agen properti, kantor broker, referral pembeli, influencer — dengan master agen sendiri,
pengajuan per deal, approval finance, potongan PPh, dan pembayaran.

Alur: submitted -> approved -> paid   (cabang: rejected)

Jurnal (idempoten via `source_event`):
    Approve  Dr 6-1200 Beban Pemasaran (bruto) / Cr 2-1500 Utang Marketing Fee (netto)
                                               (+ Cr 2-1300 Utang Pajak bila PPh dipotong)
    Bayar    Dr 2-1500 Utang Marketing Fee     / Cr 1-1200 Bank | 1-1100 Kas

Invarian: 2-1500 = Σ (netto − terbayar) fee berstatus approved.
"""
import logging

import gl_engine as gl
import sequences as seq
from core_utils import new_id, now_iso
from db import db, ORG_ID
from engine import add_activity
from finance_engine import notify_finance
from p27_utils import cash_account, rp

logger = logging.getLogger("sipro.marketingfee")
FEE_PAYABLE_ACC = "2-1500"
FEE_EXPENSE_ACC = "6-1200"
TAX_PAYABLE_ACC = "2-1300"
OPEN_STATUSES = ("submitted", "approved", "paid")


# ----------------------------- Master agen -----------------------------
async def create_agent(payload, actor: str, org_id=ORG_ID) -> dict:
    dup = await db.agents.find_one({"org_id": org_id, "name": payload.name}, {"_id": 0, "id": 1})
    if dup:
        raise ValueError(f"Agen dengan nama '{payload.name}' sudah terdaftar.")
    ts = now_iso()
    code = await seq.next_number("agent", org_id, prefix="AGN", width=4)
    doc = {
        "id": new_id(), "org_id": org_id, "code": code, "name": payload.name,
        "agent_type": payload.agent_type, "company": payload.company, "phone": payload.phone,
        "email": payload.email, "npwp": payload.npwp, "bank_name": payload.bank_name,
        "bank_account": payload.bank_account, "note": payload.note, "status": "active",
        "fee_total": 0, "fee_paid": 0, "deals_count": 0,
        "created_by": actor, "created_at": ts, "updated_at": ts,
    }
    await db.agents.insert_one(dict(doc))
    doc.pop("_id", None)
    await add_activity(entity_type="agent", entity_id=doc["id"], type="system",
                       body=f"Agen {code} — {payload.name} terdaftar.", actor=actor, org_id=org_id)
    return doc


async def update_agent(agent_id: str, payload, actor: str, org_id=ORG_ID) -> dict:
    agent = await db.agents.find_one({"id": agent_id, "org_id": org_id}, {"_id": 0})
    if not agent:
        raise ValueError("Agen tidak ditemukan.")
    patch = {k: v for k, v in payload.model_dump(exclude_none=True).items()}
    if not patch:
        return agent
    if patch.get("name") and patch["name"] != agent["name"]:
        dup = await db.agents.find_one({"org_id": org_id, "name": patch["name"]}, {"_id": 0, "id": 1})
        if dup:
            raise ValueError(f"Agen dengan nama '{patch['name']}' sudah terdaftar.")
    patch["updated_at"] = now_iso()
    await db.agents.update_one({"id": agent_id}, {"$set": patch})
    return await db.agents.find_one({"id": agent_id, "org_id": org_id}, {"_id": 0})


async def _refresh_agent_totals(agent_id: str, org_id: str):
    fees = await db.marketing_fees.find(
        {"org_id": org_id, "agent_id": agent_id, "status": {"$in": ("approved", "paid")}},
        {"_id": 0, "amount_net": 1, "paid_amount": 1, "deal_id": 1}).to_list(2000)
    await db.agents.update_one({"id": agent_id}, {"$set": {
        "fee_total": sum(int(f.get("amount_net", 0)) for f in fees),
        "fee_paid": sum(int(f.get("paid_amount", 0)) for f in fees),
        "deals_count": len({f.get("deal_id") for f in fees}),
        "updated_at": now_iso()}})


# ----------------------------- Pengajuan fee -----------------------------
async def _get_fee(fee_id: str, org_id: str) -> dict:
    doc = await db.marketing_fees.find_one({"id": fee_id, "org_id": org_id}, {"_id": 0})
    if not doc:
        raise ValueError("Pengajuan marketing fee tidak ditemukan.")
    return doc


async def create_fee(payload, actor: str, org_id=ORG_ID) -> dict:
    agent = await db.agents.find_one({"id": payload.agent_id, "org_id": org_id}, {"_id": 0})
    if not agent:
        raise ValueError("Agen tidak ditemukan.")
    if agent.get("status") != "active":
        raise ValueError(f"Agen {agent['name']} berstatus tidak aktif / daftar hitam — "
                         "tidak dapat diajukan fee.")
    deal = await db.deals.find_one({"id": payload.deal_id, "org_id": org_id}, {"_id": 0})
    if not deal:
        raise ValueError("Deal tidak ditemukan.")
    dup = await db.marketing_fees.find_one({
        "org_id": org_id, "agent_id": payload.agent_id, "deal_id": payload.deal_id,
        "trigger": payload.trigger, "status": {"$in": OPEN_STATUSES}}, {"_id": 0, "no": 1})
    if dup:
        raise ValueError(f"Fee untuk agen ini pada deal & pemicu yang sama sudah diajukan "
                         f"({dup['no']}). Ajukan pemicu berbeda atau tolak pengajuan lama.")
    price = int(deal.get("price", 0))
    if payload.basis == "percent":
        gross = round(price * float(payload.value) / 100.0)
    else:
        gross = int(payload.value)
    if gross <= 0:
        raise ValueError("Nilai fee hasil perhitungan harus lebih dari 0.")
    if gross > price and price > 0:
        raise ValueError(f"Fee {rp(gross)} melebihi harga jual unit {rp(price)}.")
    pph = round(gross * float(payload.pph_pct or 0) / 100.0)
    ts = now_iso()
    no = await seq.next_number("marketing_fee", org_id, prefix="MF", width=4)
    doc = {
        "id": new_id(), "org_id": org_id, "no": no, "status": "submitted",
        "agent_id": agent["id"], "agent_name": agent["name"], "agent_type": agent["agent_type"],
        "deal_id": deal["id"], "unit_code": deal.get("unit_code"),
        "project_id": deal.get("project_id"), "deal_price": price,
        "basis": payload.basis, "value": float(payload.value), "trigger": payload.trigger,
        "amount_gross": int(gross), "pph_pct": float(payload.pph_pct or 0),
        "pph_amount": int(pph), "amount_net": int(gross - pph), "paid_amount": 0,
        "note": payload.note, "requested_by": actor, "approved_by": None, "approved_at": None,
        "rejected_by": None, "rejected_at": None, "reject_reason": None, "paid_at": None,
        "journal_ids": [], "created_at": ts, "updated_at": ts,
    }
    await db.marketing_fees.insert_one(dict(doc))
    doc.pop("_id", None)
    await add_activity(entity_type="marketing_fee", entity_id=doc["id"], type="system",
                       body=f"Marketing fee {no} untuk {agent['name']} diajukan {rp(gross)} "
                            f"(unit {deal.get('unit_code') or '-'}).", actor=actor, org_id=org_id)
    await notify_finance(org_id, "Pengajuan marketing fee",
                         f"{agent['name']} — {rp(gross)} atas unit {deal.get('unit_code') or '-'} "
                         "menunggu persetujuan.", "approval", "marketing_fee", doc["id"])
    return doc


async def approve_fee(fee_id: str, actor: str, note=None, org_id=ORG_ID) -> dict:
    fee = await _get_fee(fee_id, org_id)
    if fee["status"] != "submitted":
        raise ValueError("Hanya pengajuan berstatus 'Diajukan' yang dapat disetujui.")
    gross = int(fee["amount_gross"])
    pph = int(fee.get("pph_amount", 0))
    net = int(fee["amount_net"])
    lines = [{"account_code": FEE_EXPENSE_ACC, "debit": gross, "credit": 0,
              "memo": f"marketing fee {fee['agent_name']}"},
             {"account_code": FEE_PAYABLE_ACC, "debit": 0, "credit": net}]
    if pph:
        lines.append({"account_code": TAX_PAYABLE_ACC, "debit": 0, "credit": pph,
                      "memo": f"PPh dipotong {fee.get('pph_pct')}%"})
    ts = now_iso()
    je = await gl.post_journal(
        org_id, f"Akrual marketing fee {fee['no']} — {fee['agent_name']}", lines,
        source_type="marketing_fee", source_id=fee_id,
        source_event=f"mfee.approve:{fee_id}", posted_by=actor)
    await db.marketing_fees.update_one({"id": fee_id}, {"$set": {
        "status": "approved", "approved_by": actor, "approved_at": ts,
        "approve_note": note, "updated_at": ts}, "$push": {"journal_ids": je["id"]}})
    await _refresh_agent_totals(fee["agent_id"], org_id)
    await add_activity(entity_type="marketing_fee", entity_id=fee_id, type="system",
                       body=f"Marketing fee {fee['no']} disetujui. Utang {rp(net)} "
                            f"(PPh {rp(pph)}). Jurnal {je['entry_no']}.",
                       actor=actor, org_id=org_id)
    return await _get_fee(fee_id, org_id)


async def reject_fee(fee_id: str, actor: str, reason=None, org_id=ORG_ID) -> dict:
    fee = await _get_fee(fee_id, org_id)
    if fee["status"] != "submitted":
        raise ValueError("Hanya pengajuan berstatus 'Diajukan' yang dapat ditolak.")
    ts = now_iso()
    await db.marketing_fees.update_one({"id": fee_id}, {"$set": {
        "status": "rejected", "rejected_by": actor, "rejected_at": ts,
        "reject_reason": reason, "updated_at": ts}})
    await add_activity(entity_type="marketing_fee", entity_id=fee_id, type="system",
                       body=f"Marketing fee {fee['no']} ditolak. {reason or ''}".strip(),
                       actor=actor, org_id=org_id)
    return await _get_fee(fee_id, org_id)


async def pay_fee(fee_id: str, amount, source: str, note, actor: str, org_id=ORG_ID) -> dict:
    fee = await _get_fee(fee_id, org_id)
    if fee["status"] != "approved":
        raise ValueError("Marketing fee harus disetujui terlebih dahulu sebelum dibayar.")
    net = int(fee["amount_net"])
    paid = int(fee.get("paid_amount", 0))
    remaining = net - paid
    amt = int(amount) if amount else remaining
    if amt <= 0:
        raise ValueError("Nominal pembayaran harus lebih dari 0.")
    if amt > remaining:
        raise ValueError(f"Pembayaran {rp(amt)} melebihi sisa utang fee {rp(remaining)}.")
    ts = now_iso()
    payment_id = new_id()
    je = await gl.post_journal(
        org_id, f"Pembayaran marketing fee {fee['no']} — {fee['agent_name']}",
        [{"account_code": FEE_PAYABLE_ACC, "debit": amt, "credit": 0},
         {"account_code": cash_account(source), "debit": 0, "credit": amt}],
        source_type="marketing_fee_payment", source_id=payment_id,
        source_event=f"mfee.pay:{payment_id}", posted_by=actor)
    new_paid = paid + amt
    status = "paid" if new_paid >= net else "approved"
    await db.marketing_fees.update_one({"id": fee_id}, {"$set": {
        "paid_amount": new_paid, "status": status, "source": source,
        "paid_at": ts if status == "paid" else fee.get("paid_at"),
        "pay_note": note, "updated_at": ts}, "$push": {"journal_ids": je["id"]}})
    await db.payments_out.insert_one({
        "id": payment_id, "org_id": org_id, "bill_id": None, "marketing_fee_id": fee_id,
        "vendor": fee["agent_name"], "amount": amt, "note": note or f"Marketing fee {fee['no']}",
        "actor": actor, "journal_id": je["id"], "created_at": ts})
    await _refresh_agent_totals(fee["agent_id"], org_id)
    await add_activity(entity_type="marketing_fee", entity_id=fee_id, type="system",
                       body=f"Marketing fee {fee['no']} dibayar {rp(amt)} ke {fee['agent_name']}. "
                            f"Jurnal {je['entry_no']}.", actor=actor, org_id=org_id)
    return await _get_fee(fee_id, org_id)


async def summary(org_id=ORG_ID) -> dict:
    fees = await db.marketing_fees.find({"org_id": org_id}, {"_id": 0}).to_list(5000)
    agents = await db.agents.find({"org_id": org_id}, {"_id": 0}).to_list(2000)
    approved = [f for f in fees if f["status"] in ("approved", "paid")]
    payable = sum(int(f["amount_net"]) - int(f.get("paid_amount", 0)) for f in approved)
    board = {}
    for f in approved:
        b = board.setdefault(f["agent_id"], {
            "agent_id": f["agent_id"], "agent_name": f["agent_name"],
            "agent_type": f.get("agent_type"), "fee_total": 0, "fee_paid": 0,
            "deals": set()})
        b["fee_total"] += int(f["amount_net"])
        b["fee_paid"] += int(f.get("paid_amount", 0))
        b["deals"].add(f["deal_id"])
    rows = []
    for b in board.values():
        b["deals_count"] = len(b.pop("deals"))
        b["fee_outstanding"] = b["fee_total"] - b["fee_paid"]
        rows.append(b)
    rows.sort(key=lambda x: -x["fee_total"])
    return {
        "fee_count": len(fees), "agent_count": len(agents),
        "active_agent_count": sum(1 for a in agents if a.get("status") == "active"),
        "waiting_approval": sum(1 for f in fees if f["status"] == "submitted"),
        "waiting_approval_amount": sum(int(f["amount_gross"]) for f in fees
                                       if f["status"] == "submitted"),
        "approved_amount": sum(int(f["amount_net"]) for f in approved),
        "paid_amount": sum(int(f.get("paid_amount", 0)) for f in fees),
        "payable_amount": payable,
        "pph_total": sum(int(f.get("pph_amount", 0)) for f in approved),
        "leaderboard": rows[:10], "payable_account": FEE_PAYABLE_ACC,
    }
