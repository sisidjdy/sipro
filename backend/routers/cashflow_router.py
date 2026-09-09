"""Cash-flow projection + Collections worklist (EPIC 3.5) — worksheet-level.

Routes: /finance/cashflow, /finance/collections,
/finance/collections/{deal_id}/remind, /finance/collections/{deal_id}/late-fee.
"""
from fastapi import APIRouter, Depends, HTTPException, Query

from db import ORG_ID
from core_utils import serialize_doc
from rbac import require_permission
import finance_reports as fr

router = APIRouter(prefix="/finance", tags=["finance"])


@router.get("/cashflow")
async def cashflow(bucket: str = Query("month"), horizon: int = Query(6),
                   user: dict = Depends(require_permission("finance", "view"))):
    data = await fr.cashflow_projection(user.get("org_id", ORG_ID), bucket=bucket, horizon=horizon)
    return {"data": serialize_doc(data)}


@router.get("/collections")
async def collections(user: dict = Depends(require_permission("finance", "view"))):
    return {"data": serialize_doc(await fr.collections_worklist(user.get("org_id", ORG_ID)))}


@router.post("/collections/{deal_id}/remind")
async def remind(deal_id: str, user: dict = Depends(require_permission("finance", "update"))):
    try:
        res = await fr.send_reminder(deal_id, user.get("email"), user.get("org_id", ORG_ID))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"data": serialize_doc(res)}


@router.post("/collections/{deal_id}/late-fee")
async def late_fee(deal_id: str, user: dict = Depends(require_permission("finance", "update"))):
    try:
        res = await fr.apply_late_fee(deal_id, user.get("email"), user.get("org_id", ORG_ID))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"data": serialize_doc(res)}
