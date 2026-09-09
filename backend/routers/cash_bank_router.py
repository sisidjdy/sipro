"""ROUTER KAS & BANK (Fase 82) — prefix `/cash-bank`. RBAC memakai resource `bank`:
view = lihat posisi/buku; create = daftarkan rekening & ajukan transfer; update = ubah master;
approve = menyetujui/menolak transfer internal (supervisor keuangan/direksi, SoD).
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse

import cash_bank as cb
from core_utils import now_iso, serialize_doc
from db import ORG_ID, db
from models_p82 import CashAccountIn, CashAccountUpdate, CashTransferIn, CashTransferReject
from rbac import audit_log, can, require_permission

router = APIRouter(prefix="/cash-bank", tags=["cash-bank"])


def _org(user: dict) -> str:
    return user.get("org_id", ORG_ID)


def _err(e: Exception) -> HTTPException:
    return HTTPException(status_code=400, detail=str(e))


@router.get("/accounts")
async def list_accounts(active: bool = Query(False), kind: str = Query(None),
                        user: dict = Depends(require_permission("bank", "view"))):
    rows = await cb.list_accounts(_org(user), active_only=active)
    if kind:
        rows = [r for r in rows if r["kind"] == kind]
    return {"data": serialize_doc(rows), "total": len(rows),
            "can_manage": await can(user.get("role"), "bank", "create"),
            "can_approve": await can(user.get("role"), "bank", "approve")}


@router.post("/accounts")
async def create_account(payload: CashAccountIn,
                         user: dict = Depends(require_permission("bank", "create"))):
    try:
        doc = await cb.create_account(_org(user), payload.model_dump(), user.get("email"))
    except ValueError as e:
        raise _err(e)
    await audit_log(user, "create", "bank_accounts", doc["id"], {"name": doc["name"], "kind": doc["kind"]})
    return {"data": serialize_doc(doc)}


@router.put("/accounts/{account_id}")
async def update_account(account_id: str, payload: CashAccountUpdate,
                         user: dict = Depends(require_permission("bank", "update"))):
    try:
        doc = await cb.update_account(_org(user), account_id,
                                      payload.model_dump(exclude_none=True), user.get("email"))
    except ValueError as e:
        raise _err(e)
    await audit_log(user, "update", "bank_accounts", account_id, {"name": doc["name"]})
    return {"data": serialize_doc(doc)}


@router.post("/accounts/{account_id}/set-default")
async def set_default(account_id: str, user: dict = Depends(require_permission("bank", "update"))):
    try:
        doc = await cb.set_default(_org(user), account_id)
    except ValueError as e:
        raise _err(e)
    await audit_log(user, "update", "bank_accounts", account_id, {"is_default": True})
    return {"data": serialize_doc(doc)}


@router.get("/position")
async def position(user: dict = Depends(require_permission("bank", "view"))):
    return {"data": serialize_doc(await cb.position(_org(user)))}


@router.get("/book")
async def book(account_id: str = Query(None), date_from: str = Query(None),
               date_to: str = Query(None), format: str = Query("json"),
               user: dict = Depends(require_permission("bank", "view"))):
    today = now_iso()[:10]
    date_to = (date_to or today)[:10]
    date_from = (date_from or f"{date_to[:7]}-01")[:10]
    if date_from > date_to:
        raise HTTPException(status_code=400, detail="Tanggal awal tidak boleh melewati tanggal akhir.")
    try:
        if not account_id:
            account_id = (await cb.default_account(_org(user), "bank"))["id"]
        data = await cb.book(_org(user), account_id, date_from, date_to)
    except ValueError as e:
        raise _err(e)
    if format == "csv":
        name = f"buku-{data['account']['account_no']}-{date_from}-{date_to}.csv"
        return PlainTextResponse(cb.book_csv(data), media_type="text/csv",
                                 headers={"Content-Disposition": f'attachment; filename="{name}"'})
    return {"data": serialize_doc(data)}


@router.get("/transfers")
async def list_transfers(status: str = Query(None), limit: int = Query(50, le=200),
                         user: dict = Depends(require_permission("bank", "view"))):
    q = {"org_id": _org(user)}
    if status:
        q["status"] = status
    rows = await db.cash_transfers.find(q, {"_id": 0}).sort("created_at", -1).to_list(limit)
    return {"data": serialize_doc(rows), "total": len(rows),
            "kinds": [{"value": k, "label": v} for k, v in cb.TRANSFER_KINDS.items()],
            "can_create": await can(user.get("role"), "bank", "create"),
            "can_approve": await can(user.get("role"), "bank", "approve")}


@router.post("/transfers")
async def create_transfer(payload: CashTransferIn,
                          user: dict = Depends(require_permission("bank", "create"))):
    try:
        doc = await cb.create_transfer(_org(user), payload.model_dump(), user.get("email"))
    except ValueError as e:
        raise _err(e)
    await audit_log(user, "create", "cash_transfers", doc["id"], {"no": doc["no"], "amount": doc["amount"]})
    return {"data": serialize_doc(doc)}


@router.post("/transfers/{transfer_id}/approve")
async def approve_transfer(transfer_id: str,
                           user: dict = Depends(require_permission("bank", "approve"))):
    try:
        doc = await cb.approve_transfer(_org(user), transfer_id, user.get("email"))
    except ValueError as e:
        raise _err(e)
    await audit_log(user, "approve", "cash_transfers", transfer_id, {"journal_no": doc["journal_no"]})
    return {"data": serialize_doc(doc)}


@router.post("/transfers/{transfer_id}/reject")
async def reject_transfer(transfer_id: str, payload: CashTransferReject,
                          user: dict = Depends(require_permission("bank", "approve"))):
    try:
        doc = await cb.reject_transfer(_org(user), transfer_id, user.get("email"), payload.reason)
    except ValueError as e:
        raise _err(e)
    await audit_log(user, "reject", "cash_transfers", transfer_id, {"reason": payload.reason})
    return {"data": serialize_doc(doc)}
