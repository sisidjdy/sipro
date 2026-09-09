"""Kas Bon / Petty Cash (Fase 27). SoD: siapa pun mengajukan, finance/owner menyetujui & mencairkan."""
from fastapi import APIRouter, Depends, HTTPException

import petty_cash as pc
from core_utils import parse_pagination, serialize_doc
from db import db, ORG_ID
from models_p27 import CashAdvanceCreate, CashAdvanceDisburse, CashAdvanceSettle, NoteOnly
from rbac import audit_log, can, require_permission

router = APIRouter(prefix="/petty-cash", tags=["petty-cash"])


async def _scope(user: dict, q: dict) -> dict:
    """Pemohon dengan izin `view_own` hanya melihat kas bonnya sendiri."""
    q = dict(q)
    q["org_id"] = user.get("org_id", ORG_ID)
    if not await can(user.get("role"), "petty_cash", "view_all"):
        q["requested_by"] = user.get("email")
    return q


@router.get("/advances")
async def list_advances(status: str = None, skip: int = 0, limit: int = 50,
                       user: dict = Depends(require_permission("petty_cash", "view"))):
    skip, limit = parse_pagination(skip, limit)
    q = await _scope(user, {})
    if status:
        q["status"] = status
    total = await db.cash_advances.count_documents(q)
    rows = await db.cash_advances.find(q, {"_id": 0}).sort("created_at", -1) \
        .skip(skip).limit(limit).to_list(limit)
    return {"data": serialize_doc(rows), "total": total,
            "can_approve": await can(user.get("role"), "petty_cash", "approve")}


@router.get("/summary")
async def summary(user: dict = Depends(require_permission("petty_cash", "view"))):
    return {"data": await pc.summary(user.get("org_id", ORG_ID))}


@router.get("/advances/{advance_id}")
async def detail(advance_id: str,
                 user: dict = Depends(require_permission("petty_cash", "view"))):
    q = await _scope(user, {"id": advance_id})
    doc = await db.cash_advances.find_one(q, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Kas bon tidak ditemukan.")
    return {"data": serialize_doc(doc)}


@router.post("/advances")
async def create(payload: CashAdvanceCreate,
                 user: dict = Depends(require_permission("petty_cash", "create"))):
    doc = await pc.create_advance(payload, user.get("email"), user.get("name"),
                                  user.get("org_id", ORG_ID))
    await audit_log(user, "create", "petty_cash", doc["id"], {"amount": doc["amount_requested"]})
    return {"data": serialize_doc(doc)}


@router.post("/advances/{advance_id}/approve")
async def approve(advance_id: str, payload: NoteOnly,
                  user: dict = Depends(require_permission("petty_cash", "approve"))):
    try:
        doc = await pc.approve_advance(advance_id, user.get("email"), payload.note,
                                       user.get("org_id", ORG_ID))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit_log(user, "approve", "petty_cash", advance_id)
    return {"data": serialize_doc(doc)}


@router.post("/advances/{advance_id}/reject")
async def reject(advance_id: str, payload: NoteOnly,
                 user: dict = Depends(require_permission("petty_cash", "approve"))):
    try:
        doc = await pc.reject_advance(advance_id, user.get("email"), payload.note,
                                      user.get("org_id", ORG_ID))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit_log(user, "reject", "petty_cash", advance_id)
    return {"data": serialize_doc(doc)}


@router.post("/advances/{advance_id}/cancel")
async def cancel(advance_id: str,
                 user: dict = Depends(require_permission("petty_cash", "update"))):
    org = user.get("org_id", ORG_ID)
    adv = await db.cash_advances.find_one({"id": advance_id, "org_id": org}, {"_id": 0})
    if not adv:
        raise HTTPException(status_code=404, detail="Kas bon tidak ditemukan.")
    if adv.get("requested_by") != user.get("email") and \
            not await can(user.get("role"), "petty_cash", "approve"):
        raise HTTPException(status_code=403, detail="Hanya pemohon atau finance yang "
                                                   "dapat membatalkan kas bon ini.")
    try:
        doc = await pc.cancel_advance(advance_id, user.get("email"), org)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"data": serialize_doc(doc)}


@router.post("/advances/{advance_id}/disburse")
async def disburse(advance_id: str, payload: CashAdvanceDisburse,
                   user: dict = Depends(require_permission("petty_cash", "approve"))):
    try:
        doc = await pc.disburse_advance(advance_id, payload.amount, payload.source,
                                        payload.note, user.get("email"),
                                        user.get("org_id", ORG_ID),
                                        cash_account_id=payload.cash_account_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit_log(user, "disburse", "petty_cash", advance_id,
                    {"amount": doc.get("disbursed_amount")})
    return {"data": serialize_doc(doc)}


@router.post("/advances/{advance_id}/settle")
async def settle(advance_id: str, payload: CashAdvanceSettle,
                 user: dict = Depends(require_permission("petty_cash", "update"))):
    org = user.get("org_id", ORG_ID)
    adv = await db.cash_advances.find_one({"id": advance_id, "org_id": org}, {"_id": 0})
    if not adv:
        raise HTTPException(status_code=404, detail="Kas bon tidak ditemukan.")
    if adv.get("requested_by") != user.get("email") and \
            not await can(user.get("role"), "petty_cash", "approve"):
        raise HTTPException(status_code=403, detail="Hanya pemohon atau finance yang dapat "
                                                   "mengisi pertanggungjawaban kas bon ini.")
    try:
        doc = await pc.settle_advance(advance_id, payload.items, payload.note,
                                      user.get("email"), org)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit_log(user, "settle", "petty_cash", advance_id,
                    {"expense_total": doc.get("expense_total")})
    return {"data": serialize_doc(doc)}
