"""ROUTER GIRO / CEK MUNDUR (Fase 86) — prefix `/pdc`. RBAC resource `bank`:
view = daftar; create = catat penerimaan giro; update = kliring / tolakan / batal.
"""
from fastapi import APIRouter, Depends, HTTPException, Query

import pdc_engine as pdc
from core_utils import serialize_doc
from db import ORG_ID
from models_p85 import PdcClearIn, PdcReceiveIn, ReasonIn
from rbac import audit_log, can, require_permission

router = APIRouter(prefix="/pdc", tags=["pdc"])


def _org(user: dict) -> str:
    return user.get("org_id", ORG_ID)


def _err(e: Exception) -> HTTPException:
    return HTTPException(status_code=400, detail=str(e))


@router.get("")
async def listing(status: str = Query(None), deal_id: str = Query(None), limit: int = Query(200, le=1000),
                  user: dict = Depends(require_permission("bank", "view"))):
    data = await pdc.listing(_org(user), status, deal_id, limit)
    return {"data": serialize_doc(data["rows"]), "total": data["total"], "summary": data["summary"],
            "kinds": data["kinds"], "can_create": await can(user.get("role"), "bank", "create"),
            "can_update": await can(user.get("role"), "bank", "update")}


@router.post("")
async def receive(payload: PdcReceiveIn, user: dict = Depends(require_permission("bank", "create"))):
    try:
        doc = await pdc.receive(_org(user), payload.model_dump(), user.get("email"))
    except ValueError as e:
        raise _err(e)
    await audit_log(user, "create", "pdc_instruments", doc["id"], {"no": doc["no"], "amount": doc["amount"]})
    return {"data": serialize_doc(doc)}


@router.post("/{pdc_id}/clear")
async def clear(pdc_id: str, payload: PdcClearIn, user: dict = Depends(require_permission("bank", "update"))):
    try:
        doc = await pdc.clear(_org(user), pdc_id, payload.model_dump(), user.get("email"))
    except ValueError as e:
        raise _err(e)
    await audit_log(user, "clear", "pdc_instruments", pdc_id, {"receipt_no": doc.get("receipt_no")})
    return {"data": serialize_doc(doc)}


@router.post("/{pdc_id}/bounce")
async def bounce(pdc_id: str, payload: ReasonIn, user: dict = Depends(require_permission("bank", "update"))):
    try:
        doc = await pdc.bounce(_org(user), pdc_id, payload.reason, user.get("email"))
    except ValueError as e:
        raise _err(e)
    await audit_log(user, "bounce", "pdc_instruments", pdc_id, {"reason": payload.reason})
    return {"data": serialize_doc(doc)}


@router.post("/{pdc_id}/cancel")
async def cancel(pdc_id: str, payload: ReasonIn, user: dict = Depends(require_permission("bank", "update"))):
    try:
        doc = await pdc.cancel(_org(user), pdc_id, payload.reason, user.get("email"))
    except ValueError as e:
        raise _err(e)
    await audit_log(user, "cancel", "pdc_instruments", pdc_id, {"reason": payload.reason})
    return {"data": serialize_doc(doc)}
