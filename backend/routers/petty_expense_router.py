"""ROUTER KAS KECIL IMPREST (Fase 84) — prefix `/petty-cash` (berdampingan dengan kas bon).
RBAC memakai resource `bank`: view = lihat pengeluaran & keadaan imprest; create = kasir mencatat
pengeluaran & mengajukan pengisian; approve = membatalkan pengeluaran (SoD: bukan pencatatnya).
"""
from fastapi import APIRouter, Depends, HTTPException, Query

import petty_expense as pe
import reference_p27 as r27
from core_utils import serialize_doc
from db import ORG_ID
from models_p84 import PettyExpenseIn, PettyExpenseVoid, ReplenishIn
from rbac import audit_log, can, require_permission

router = APIRouter(prefix="/petty-cash", tags=["petty-cash-imprest"])


def _org(user: dict) -> str:
    return user.get("org_id", ORG_ID)


def _err(e: Exception) -> HTTPException:
    return HTTPException(status_code=400, detail=str(e))


@router.get("/imprest")
async def imprest(user: dict = Depends(require_permission("bank", "view"))):
    data = await pe.imprest_status(_org(user))
    data["can_create"] = await can(user.get("role"), "bank", "create")
    data["can_void"] = await can(user.get("role"), "bank", "approve")
    return {"data": serialize_doc(data)}


@router.post("/imprest/{account_id}/replenish")
async def replenish(account_id: str, payload: ReplenishIn,
                    user: dict = Depends(require_permission("bank", "create"))):
    try:
        doc = await pe.propose_replenish(_org(user), account_id, user.get("email"),
                                         payload.from_account_id, payload.amount, payload.note)
    except ValueError as e:
        raise _err(e)
    await audit_log(user, "create", "cash_transfers", doc["id"],
                    {"no": doc["no"], "amount": doc["amount"], "reason": "imprest_replenish"})
    return {"data": serialize_doc(doc)}


@router.get("/expenses")
async def list_expenses(account_id: str = Query(None), status: str = Query(None),
                        date_from: str = Query(None), date_to: str = Query(None),
                        limit: int = Query(100, le=500),
                        user: dict = Depends(require_permission("bank", "view"))):
    data = await pe.list_expenses(_org(user), account_id, status, date_from, date_to, limit)
    return {"data": serialize_doc(data["rows"]), "total": data["total"],
            "sum_posted": data["sum_posted"],
            "categories": [{"value": k, "account_code": v} for k, v in r27.CASHBON_ACCOUNT.items()],
            "can_create": await can(user.get("role"), "bank", "create"),
            "can_void": await can(user.get("role"), "bank", "approve")}


@router.post("/expenses")
async def create_expense(payload: PettyExpenseIn,
                         user: dict = Depends(require_permission("bank", "create"))):
    try:
        doc = await pe.create_expense(_org(user), payload.model_dump(), user.get("email"),
                                      user.get("name"))
    except ValueError as e:
        raise _err(e)
    await audit_log(user, "create", "petty_expenses", doc["id"],
                    {"no": doc["no"], "amount": doc["amount"], "category": doc["category"]})
    return {"data": serialize_doc(doc)}


@router.post("/expenses/{expense_id}/void")
async def void_expense(expense_id: str, payload: PettyExpenseVoid,
                       user: dict = Depends(require_permission("bank", "approve"))):
    try:
        doc = await pe.void_expense(_org(user), expense_id, user.get("email"), payload.reason)
    except ValueError as e:
        raise _err(e)
    await audit_log(user, "void", "petty_expenses", expense_id, {"reason": payload.reason})
    return {"data": serialize_doc(doc)}
