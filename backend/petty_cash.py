"""Kas Bon / Petty Cash (Fase 27 — menutup gap kompetitor #6).

Siklus jujur & berjurnal:
    submitted -> approved -> disbursed -> settled   (cabang: rejected / cancelled)

Jurnal (double-entry, idempoten via `source_event`):
    Pencairan          Dr 1-1500 Uang Muka Karyawan   / Cr 1-1100 Kas | 1-1200 Bank
    Pertanggungjawaban Dr beban/WIP per kategori
                       (+ Dr kas bila ada sisa dikembalikan)
                                                      / Cr 1-1500 (nominal cair)
                                                      (+ Cr kas bila realisasi > cair)

Invarian: saldo 1-1500 = Σ nominal cair kas bon berstatus `disbursed`
(begitu dipertanggungjawabkan, akun uang muka kembali nol untuk kas bon tsb).
"""
import logging

import gl_engine as gl
import reference_p27 as r27
import sequences as seq
from core_utils import new_id, now_iso
from db import db, ORG_ID
from engine import add_activity, create_notification, emit
from finance_engine import notify_finance
from p27_utils import cash_account, rp

logger = logging.getLogger("sipro.pettycash")
ADVANCE_ACCOUNT = "1-1500"


async def _get(advance_id: str, org_id: str) -> dict:
    doc = await db.cash_advances.find_one({"id": advance_id, "org_id": org_id}, {"_id": 0})
    if not doc:
        raise ValueError("Kas bon tidak ditemukan.")
    return doc


async def _project_name(project_id, org_id):
    if not project_id:
        return None
    p = await db.projects.find_one({"id": project_id, "org_id": org_id}, {"_id": 0, "name": 1})
    return (p or {}).get("name")


async def create_advance(payload, actor: str, actor_name: str, org_id=ORG_ID) -> dict:
    """Pengajuan kas bon oleh staf mana pun (status langsung `submitted`)."""
    ts = now_iso()
    no = await seq.next_number("cash_advance", org_id, prefix="KB", width=4,
                               context={"project_id": payload.project_id})
    doc = {
        "id": new_id(), "org_id": org_id, "no": no, "status": "submitted",
        "purpose": payload.purpose, "category": payload.category,
        "amount_requested": int(payload.amount), "needed_date": payload.needed_date,
        "project_id": payload.project_id,
        "project_name": await _project_name(payload.project_id, org_id),
        "note": payload.note, "requested_by": actor, "requester_name": actor_name,
        "approved_by": None, "approved_at": None, "rejected_by": None, "rejected_at": None,
        "reject_reason": None, "disbursed_amount": 0, "disbursed_at": None,
        "disbursed_by": None, "source": None, "expenses": [], "expense_total": 0,
        "returned_amount": 0, "reimburse_amount": 0, "settled_at": None, "settled_by": None,
        "outstanding": 0, "journal_ids": [], "created_at": ts, "updated_at": ts,
    }
    await db.cash_advances.insert_one(dict(doc))
    doc.pop("_id", None)
    await add_activity(entity_type="cash_advance", entity_id=doc["id"], type="system",
                       body=f"Kas bon {no} diajukan sebesar {rp(payload.amount)} — {payload.purpose}.",
                       actor=actor, org_id=org_id)
    await notify_finance(org_id, "Pengajuan kas bon baru",
                         f"{actor_name or actor} mengajukan kas bon {no} {rp(payload.amount)} "
                         f"untuk {payload.purpose}.", "approval", "cash_advance", doc["id"])
    await emit("cashbon.submitted", "cash_advance", doc["id"],
               {"amount": int(payload.amount)}, org_id=org_id)
    return doc


async def approve_advance(advance_id: str, actor: str, note=None, org_id=ORG_ID) -> dict:
    adv = await _get(advance_id, org_id)
    if adv["status"] != "submitted":
        raise ValueError("Hanya kas bon berstatus 'Diajukan' yang dapat disetujui.")
    if adv.get("requested_by") == actor:
        raise ValueError("Pemisahan tugas: pemohon tidak boleh menyetujui kas bonnya sendiri.")
    ts = now_iso()
    await db.cash_advances.update_one({"id": advance_id}, {"$set": {
        "status": "approved", "approved_by": actor, "approved_at": ts,
        "approve_note": note, "updated_at": ts}})
    await add_activity(entity_type="cash_advance", entity_id=advance_id, type="system",
                       body=f"Kas bon {adv['no']} disetujui.", actor=actor, org_id=org_id)
    await create_notification(user_email=adv["requested_by"], title="Kas bon disetujui",
                              body=f"Kas bon {adv['no']} {rp(adv['amount_requested'])} disetujui "
                                   "dan menunggu pencairan.",
                              type="approval", related_entity_type="cash_advance",
                              related_entity_id=advance_id, org_id=org_id)
    return await _get(advance_id, org_id)


async def reject_advance(advance_id: str, actor: str, reason=None, org_id=ORG_ID) -> dict:
    adv = await _get(advance_id, org_id)
    if adv["status"] not in ("submitted", "approved"):
        raise ValueError("Kas bon ini tidak dapat ditolak (sudah dicairkan atau selesai).")
    ts = now_iso()
    await db.cash_advances.update_one({"id": advance_id}, {"$set": {
        "status": "rejected", "rejected_by": actor, "rejected_at": ts,
        "reject_reason": reason, "updated_at": ts}})
    await create_notification(user_email=adv["requested_by"], title="Kas bon ditolak",
                              body=f"Kas bon {adv['no']} ditolak. {reason or ''}".strip(),
                              type="approval", related_entity_type="cash_advance",
                              related_entity_id=advance_id, org_id=org_id)
    return await _get(advance_id, org_id)


async def cancel_advance(advance_id: str, actor: str, org_id=ORG_ID) -> dict:
    adv = await _get(advance_id, org_id)
    if adv["status"] not in ("submitted", "approved"):
        raise ValueError("Hanya kas bon yang belum dicairkan dapat dibatalkan.")
    ts = now_iso()
    await db.cash_advances.update_one({"id": advance_id}, {"$set": {
        "status": "cancelled", "cancelled_by": actor, "cancelled_at": ts, "updated_at": ts}})
    return await _get(advance_id, org_id)


async def disburse_advance(advance_id: str, amount, source: str, note, actor: str,
                           org_id=ORG_ID, cash_account_id: str = None) -> dict:
    """Cairkan kas bon: kas keluar, timbul uang muka karyawan (bukan beban)."""
    adv = await _get(advance_id, org_id)
    if adv["status"] != "approved":
        raise ValueError("Kas bon harus disetujui terlebih dahulu sebelum dicairkan.")
    requested = int(adv["amount_requested"])
    amt = int(amount) if amount else requested
    if amt <= 0:
        raise ValueError("Nominal pencairan harus lebih dari 0.")
    if amt > requested:
        raise ValueError(f"Pencairan {rp(amt)} melebihi nominal yang disetujui {rp(requested)}.")
    ts = now_iso()
    import cash_bank as _cb
    cash_code = await _cb.resolve_code(org_id, cash_account_id, cash_account(source))
    cash_acc = await _cb.account_by_code(org_id, cash_code)
    je = await gl.post_journal(
        org_id, f"Pencairan kas bon {adv['no']} — {adv.get('requester_name') or adv['requested_by']}",
        [{"account_code": ADVANCE_ACCOUNT, "debit": amt, "credit": 0},
         {"account_code": cash_code, "debit": 0, "credit": amt}],
        source_type="cash_advance", source_id=advance_id,
        source_event=f"cashbon.disburse:{advance_id}", posted_by=actor)
    await db.cash_advances.update_one({"id": advance_id}, {"$set": {
        "status": "disbursed", "disbursed_amount": amt, "disbursed_at": ts,
        "disbursed_by": actor, "source": source, "disburse_note": note,
        "cash_account_id": (cash_acc or {}).get("id"), "cash_account_code": cash_code,
        "cash_account_name": (cash_acc or {}).get("name"),
        "outstanding": amt, "updated_at": ts}, "$push": {"journal_ids": je["id"]}})
    await add_activity(entity_type="cash_advance", entity_id=advance_id, type="system",
                       body=f"Kas bon {adv['no']} dicairkan {rp(amt)} ({source}). Jurnal {je['entry_no']}.",
                       actor=actor, org_id=org_id)
    await create_notification(user_email=adv["requested_by"], title="Kas bon dicairkan",
                              body=f"Kas bon {adv['no']} cair {rp(amt)}. Segera lampirkan "
                                   "pertanggungjawaban setelah dipakai.",
                              type="finance", related_entity_type="cash_advance",
                              related_entity_id=advance_id, org_id=org_id)
    await emit("cashbon.disbursed", "cash_advance", advance_id, {"amount": amt}, org_id=org_id)
    return await _get(advance_id, org_id)


def _settle_lines(adv: dict, items: list) -> tuple:
    """Bangun baris jurnal pertanggungjawaban + hitung sisa/reimburse."""
    disbursed = int(adv.get("disbursed_amount", 0))
    per_account = {}
    total = 0
    for it in items:
        amt = int(it["amount"])
        total += amt
        code = r27.CASHBON_ACCOUNT.get(it["category"], "6-1300")
        per_account[code] = per_account.get(code, 0) + amt
    returned = max(0, disbursed - total)
    reimburse = max(0, total - disbursed)
    lines = [{"account_code": c, "debit": v, "credit": 0, "memo": "realisasi kas bon"}
             for c, v in sorted(per_account.items())]
    cash = adv.get("cash_account_code") or cash_account(adv.get("source"))
    if returned:
        lines.append({"account_code": cash, "debit": returned, "credit": 0,
                      "memo": "sisa kas bon dikembalikan"})
    lines.append({"account_code": ADVANCE_ACCOUNT, "debit": 0, "credit": disbursed})
    if reimburse:
        lines.append({"account_code": cash, "debit": 0, "credit": reimburse,
                      "memo": "penggantian kelebihan pengeluaran"})
    return lines, total, returned, reimburse


async def settle_advance(advance_id: str, items: list, note, actor: str, org_id=ORG_ID) -> dict:
    """Pertanggungjawaban: uang muka menjadi beban/WIP; sisa dikembalikan atau ditambah."""
    adv = await _get(advance_id, org_id)
    if adv["status"] != "disbursed":
        raise ValueError("Pertanggungjawaban hanya untuk kas bon yang sudah dicairkan.")
    rows = [{"id": new_id(), "category": it.category, "description": it.description,
             "amount": int(it.amount), "date": it.date or now_iso()} for it in items]
    lines, total, returned, reimburse = _settle_lines(adv, rows)
    if total <= 0:
        raise ValueError("Total realisasi pengeluaran harus lebih dari 0.")
    ts = now_iso()
    je = await gl.post_journal(
        org_id, f"Pertanggungjawaban kas bon {adv['no']}", lines,
        source_type="cash_advance", source_id=advance_id,
        source_event=f"cashbon.settle:{advance_id}", posted_by=actor)
    await db.cash_advances.update_one({"id": advance_id}, {"$set": {
        "status": "settled", "expenses": rows, "expense_total": total,
        "returned_amount": returned, "reimburse_amount": reimburse, "outstanding": 0,
        "settled_at": ts, "settled_by": actor, "settle_note": note, "updated_at": ts},
        "$push": {"journal_ids": je["id"]}})
    detail = f"realisasi {rp(total)}"
    if returned:
        detail += f", sisa dikembalikan {rp(returned)}"
    if reimburse:
        detail += f", penggantian {rp(reimburse)}"
    await add_activity(entity_type="cash_advance", entity_id=advance_id, type="system",
                       body=f"Kas bon {adv['no']} dipertanggungjawabkan: {detail}. "
                            f"Jurnal {je['entry_no']}.", actor=actor, org_id=org_id)
    await notify_finance(org_id, "Kas bon dipertanggungjawabkan",
                         f"Kas bon {adv['no']} — {detail}.", "finance",
                         "cash_advance", advance_id)
    await emit("cashbon.settled", "cash_advance", advance_id, {"amount": total}, org_id=org_id)
    return await _get(advance_id, org_id)


async def outstanding_total(org_id=ORG_ID) -> int:
    total = 0
    async for r in db.cash_advances.aggregate([
            {"$match": {"org_id": org_id, "status": "disbursed"}},
            {"$group": {"_id": None, "s": {"$sum": "$disbursed_amount"}}}]):
        total = int(r.get("s") or 0)
    return total


async def summary(org_id=ORG_ID) -> dict:
    rows = await db.cash_advances.find({"org_id": org_id}, {"_id": 0}).to_list(5000)
    by_status = {}
    for r in rows:
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1
    outstanding = sum(int(r.get("disbursed_amount", 0)) for r in rows if r["status"] == "disbursed")
    return {
        "count": len(rows), "by_status": by_status,
        "waiting_approval": sum(1 for r in rows if r["status"] == "submitted"),
        "waiting_approval_amount": sum(int(r["amount_requested"]) for r in rows
                                       if r["status"] == "submitted"),
        "ready_to_disburse": sum(1 for r in rows if r["status"] == "approved"),
        "ready_to_disburse_amount": sum(int(r["amount_requested"]) for r in rows
                                        if r["status"] == "approved"),
        "outstanding_count": sum(1 for r in rows if r["status"] == "disbursed"),
        "outstanding_amount": outstanding,
        "settled_amount": sum(int(r.get("expense_total", 0)) for r in rows
                              if r["status"] == "settled"),
        "advance_account": ADVANCE_ACCOUNT,
    }


async def unsettled_reminder(org_id=ORG_ID) -> int:
    """Ingatkan pemohon atas kas bon cair yang belum dipertanggungjawabkan >7 hari.

    Idempoten: memakai `auto_create_task` (source_event unik) sehingga sweeper yang
    berjalan berulang tidak membanjiri notifikasi.
    """
    from engine import auto_create_task
    from p27_utils import days_overdue
    rows = await db.cash_advances.find(
        {"org_id": org_id, "status": "disbursed"}, {"_id": 0}).to_list(1000)
    hit = 0
    for r in rows:
        aging = days_overdue(r.get("disbursed_at"))
        if aging < 7:
            continue
        task = await auto_create_task(
            source_event=f"cashbon_unsettled:{r['id']}",
            title=f"Pertanggungjawaban kas bon {r['no']}", type="follow_up",
            related_entity_type="cash_advance", related_entity_id=r["id"],
            assigned_to=r.get("requested_by"), priority="high",
            description=f"Kas bon {rp(r.get('disbursed_amount'))} cair {aging} hari lalu "
                        "dan belum dipertanggungjawabkan.", org_id=org_id)
        if not task:
            continue
        hit += 1
        await create_notification(
            user_email=r["requested_by"], title="Kas bon belum dipertanggungjawabkan",
            body=f"Kas bon {r['no']} {rp(r.get('disbursed_amount'))} cair {aging} hari lalu. "
                 "Mohon lengkapi rincian penggunaannya.",
            type="finance", related_entity_type="cash_advance", related_entity_id=r["id"],
            org_id=org_id)
    return hit
