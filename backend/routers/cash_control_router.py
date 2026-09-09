"""ROUTER lanjutan Kas & Bank (Fase 85 & 87) — prefix `/cash-bank`.
Kunci periode per rekening (`bank:approve`) dan bukti kas BKM/BKK (turunan jurnal, `bank:view`).
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

import cash_period_lock as cpl
import cash_voucher as cv
from core_utils import parse_pagination, serialize_doc
from db import ORG_ID, ORG_NAME, db
from models_p85 import PeriodLockIn, ReasonIn
from rbac import audit_log, can, require_permission

router = APIRouter(prefix="/cash-bank", tags=["cash-bank-control"])


def _org(user: dict) -> str:
    return user.get("org_id", ORG_ID)


def _err(e: Exception) -> HTTPException:
    return HTTPException(status_code=400, detail=str(e))


# ------------------------------------------------------------------ kunci periode (Fase 85)
@router.get("/locks")
async def locks(user: dict = Depends(require_permission("bank", "view"))):
    data = await cpl.overview(_org(user))
    data["can_lock"] = await can(user.get("role"), "bank", "approve")
    return {"data": serialize_doc(data)}


@router.get("/locks/preview")
async def lock_preview(account_id: str = Query(...), period: str = Query(...),
                       counted_balance: int = Query(None),
                       user: dict = Depends(require_permission("bank", "view"))):
    try:
        return {"data": serialize_doc(await cpl.preview(_org(user), account_id, period, counted_balance))}
    except ValueError as e:
        raise _err(e)


@router.post("/locks")
async def lock(payload: PeriodLockIn, user: dict = Depends(require_permission("bank", "approve"))):
    try:
        doc = await cpl.lock(_org(user), payload.model_dump(), user.get("email"))
    except ValueError as e:
        raise _err(e)
    await audit_log(user, "lock", "cash_period_locks", doc["id"],
                    {"account": doc["account_name"], "period": doc["period"], "closing": doc["closing_balance"]})
    return {"data": serialize_doc(doc)}


@router.post("/locks/{lock_id}/unlock")
async def unlock(lock_id: str, payload: ReasonIn, user: dict = Depends(require_permission("bank", "approve"))):
    try:
        doc = await cpl.unlock(_org(user), lock_id, user.get("email"), payload.reason)
    except ValueError as e:
        raise _err(e)
    await audit_log(user, "unlock", "cash_period_locks", lock_id, {"reason": payload.reason})
    return {"data": serialize_doc(doc)}


# ------------------------------------------------------------------ bukti kas (Fase 87)
@router.get("/vouchers")
async def vouchers(kind: str = Query(None), account_id: str = Query(None), date_from: str = Query(None),
                   date_to: str = Query(None), q: str = Query(None), skip: int = 0, limit: int = 50,
                   user: dict = Depends(require_permission("bank", "view"))):
    skip, limit = parse_pagination(skip, limit)
    data = await cv.listing(_org(user), kind, account_id, date_from, date_to, q, skip, limit)
    return {"data": serialize_doc(data["rows"]), "total": data["total"],
            "sum_in": data["sum_in"], "sum_out": data["sum_out"]}


@router.get("/vouchers/{voucher_id}")
async def voucher_detail(voucher_id: str, user: dict = Depends(require_permission("bank", "view"))):
    doc = await db.cash_vouchers.find_one({"id": voucher_id, "org_id": _org(user)}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Bukti kas tidak ditemukan.")
    return {"data": serialize_doc(doc)}


async def _party(org: str, v: dict) -> str:
    st, sid = v.get("source_type"), v.get("source_id")
    if st == "receipt" or st == "ar_receipt":
        rc = await db.receipts.find_one({"id": sid, "org_id": org}, {"_id": 0, "deal_id": 1})
        deal = await db.deals.find_one({"id": (rc or {}).get("deal_id"), "org_id": org}, {"_id": 0, "lead_name": 1, "customer_name": 1})
        return (deal or {}).get("lead_name") or (deal or {}).get("customer_name")
    if st == "ap_bill":
        b = await db.ap_invoices.find_one({"id": sid, "org_id": org}, {"_id": 0, "vendor": 1})
        return (b or {}).get("vendor")
    if st == "cash_advance":
        a = await db.cash_advances.find_one({"id": sid, "org_id": org}, {"_id": 0, "requester_name": 1})
        return (a or {}).get("requester_name")
    if st == "petty_expense":
        p = await db.petty_expenses.find_one({"id": sid, "org_id": org}, {"_id": 0, "payee": 1})
        return (p or {}).get("payee")
    if st == "pdc":
        p = await db.pdc_instruments.find_one({"id": sid, "org_id": org}, {"_id": 0, "issuer_name": 1})
        return (p or {}).get("issuer_name")
    return None


@router.get("/vouchers/{voucher_id}/pdf")
async def voucher_pdf(voucher_id: str, user: dict = Depends(require_permission("bank", "view"))):
    import doc_layout as dl
    from pdf_utils import build_document_pdf
    org = _org(user)
    v = await db.cash_vouchers.find_one({"id": voucher_id, "org_id": org}, {"_id": 0})
    if not v:
        raise HTTPException(status_code=404, detail="Bukti kas tidak ditemukan.")
    layout = await dl.get_layout(org, v["kind"])
    pdf = build_document_pdf(title=v["kind_label"], doc_number=v["no"], content=cv.pdf_content(v, await _party(org, v)),
                             org_name=ORG_NAME, layout=layout, script_context={"date": v.get("date") or ""}, images=await dl.images(org, layout))
    name = v["no"].replace("/", "-")
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{name}.pdf"'})
