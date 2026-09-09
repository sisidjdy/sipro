"""Komisi sales: list (row-scope sales), compute (tiered), approve. Slice Finance."""
from fastapi import APIRouter, Body, Depends, HTTPException

from db import db, ORG_ID
from core_utils import serialize_doc, parse_pagination
from rbac import require_permission, is_scoped_sales
import finance_engine as fe
from models import CommissionComputeReq

router = APIRouter(prefix="/finance/commissions", tags=["finance-commissions"])


@router.get("")
async def list_commissions(status: str = None, skip: int = 0, limit: int = 50,
                           user: dict = Depends(require_permission("commissions", "view"))):
    org = user.get("org_id", ORG_ID)
    skip, limit = parse_pagination(skip, limit)
    q = {"org_id": org}
    if status:
        q["status"] = status
    if is_scoped_sales(user):
        q["assigned_to"] = user.get("email")
    total = await db.commissions.count_documents(q)
    rows = await db.commissions.find(q, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    return {"data": serialize_doc(rows), "total": total}


@router.get("/summary")
async def commission_summary(user: dict = Depends(require_permission("commissions", "view"))):
    """Ringkasan komisi (EPIC 1.6): total/pending/approved/paid + daftar per-deal.
    Row-scope: sales hanya melihat komisinya sendiri."""
    org = user.get("org_id", ORG_ID)
    q = {"org_id": org}
    if is_scoped_sales(user):
        q["assigned_to"] = user.get("email")
    rows = await db.commissions.find(q, {"_id": 0}).sort("created_at", -1).to_list(1000)
    agg = {s: {"amount": 0, "count": 0} for s in ("pending", "approved", "paid")}
    total = 0
    for r in rows:
        amt = int(r.get("amount", 0) or 0)
        total += amt
        st = r.get("status", "pending")
        if st in agg:
            agg[st]["amount"] += amt
            agg[st]["count"] += 1
    earned = agg["approved"]["amount"] + agg["paid"]["amount"]
    summary = {
        "total": total, "count": len(rows), "earned": earned,
        "pending": agg["pending"], "approved": agg["approved"], "paid": agg["paid"],
    }
    return {"data": {"summary": summary, "deals": serialize_doc(rows)}}


@router.post("/{deal_id}/compute")
async def compute_commission(deal_id: str, payload: CommissionComputeReq,
                             user: dict = Depends(require_permission("finance", "create"))):
    org = user.get("org_id", ORG_ID)
    deal = await db.deals.find_one({"id": deal_id, "org_id": org}, {"_id": 0})
    if not deal:
        raise HTTPException(status_code=404, detail="Deal tidak ditemukan")
    scheme = await fe.get_default_commission_scheme(org)
    if payload.scheme_id:
        scheme = await db.commission_schemes.find_one({"id": payload.scheme_id, "org_id": org}, {"_id": 0}) or scheme
    trigger = scheme.get("trigger", "booked") if scheme else "booked"
    doc = await fe.create_commission_for_deal(deal, scheme_id=payload.scheme_id, org_id=org, trigger=trigger)
    if not doc:
        raise HTTPException(status_code=400,
                            detail="Komisi sudah ada untuk deal ini atau skema tidak tersedia.")
    return {"data": serialize_doc(doc)}


@router.post("/{commission_id}/approve")
async def approve_commission(commission_id: str,
                             user: dict = Depends(require_permission("commissions", "approve"))):
    try:
        doc = await fe.approve_commission(commission_id, user.get("email"), user.get("org_id", ORG_ID))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"data": serialize_doc(doc)}


@router.post("/{commission_id}/pay")
async def pay_commission(commission_id: str, payload: dict = Body(default=None),
                         user: dict = Depends(require_permission("commissions", "approve"))):
    try:
        doc = await fe.pay_commission(commission_id, user.get("email"), user.get("org_id", ORG_ID),
                                      cash_account_id=(payload or {}).get("cash_account_id"))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"data": serialize_doc(doc)}
