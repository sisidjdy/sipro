"""Pembiayaan korporat (kredit bank / leasing) + jadwal angsuran (Fase 27).

Beda dari `financing_router` (/financing) yang menangani KPR PEMBELI: router ini untuk
utang perusahaan. Akses: finance + owner/super_admin.
"""
from fastapi import APIRouter, Depends, HTTPException

import loans as ln
from core_utils import parse_pagination, serialize_doc
from db import db, ORG_ID
from models_p27 import InstallmentPay, LoanActivate, LoanCreate
from rbac import audit_log, require_permission

router = APIRouter(prefix="/corp-financing", tags=["corp-financing"])


@router.get("/loans")
async def list_loans(status: str = None, skip: int = 0, limit: int = 100,
                     user: dict = Depends(require_permission("loans", "view"))):
    skip, limit = parse_pagination(skip, limit)
    q = {"org_id": user.get("org_id", ORG_ID)}
    if status:
        q["status"] = status
    total = await db.loans.count_documents(q)
    rows = await db.loans.find(q, {"_id": 0}).sort("created_at", -1) \
        .skip(skip).limit(limit).to_list(limit)
    for r in rows:
        r["metrics"] = ln.loan_metrics(r)
        r.pop("schedule", None)  # jadwal lengkap hanya di endpoint detail (payload ramping)
    return {"data": serialize_doc(rows), "total": total}


@router.get("/summary")
async def summary(user: dict = Depends(require_permission("loans", "view"))):
    return {"data": await ln.summary(user.get("org_id", ORG_ID))}


@router.get("/payments")
async def list_payments(loan_id: str = None, skip: int = 0, limit: int = 100,
                        user: dict = Depends(require_permission("loans", "view"))):
    skip, limit = parse_pagination(skip, limit)
    q = {"org_id": user.get("org_id", ORG_ID)}
    if loan_id:
        q["loan_id"] = loan_id
    total = await db.loan_payments.count_documents(q)
    rows = await db.loan_payments.find(q, {"_id": 0}).sort("created_at", -1) \
        .skip(skip).limit(limit).to_list(limit)
    return {"data": serialize_doc(rows), "total": total,
            "paid_total": sum(int(r.get("amount", 0)) for r in rows)}


@router.get("/loans/{loan_id}")
async def detail(loan_id: str, user: dict = Depends(require_permission("loans", "view"))):
    org = user.get("org_id", ORG_ID)
    doc = await db.loans.find_one({"id": loan_id, "org_id": org}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Fasilitas pembiayaan tidak ditemukan.")
    payments = await db.loan_payments.find(
        {"org_id": org, "loan_id": loan_id}, {"_id": 0}).sort("created_at", -1).to_list(600)
    preview = None
    if doc["status"] == "draft":
        preview = ln.annotate_schedule(ln.build_schedule(
            doc["principal"], doc["interest_rate_pct"], doc["tenor_months"],
            doc["amortization_method"], doc.get("start_date")))
    doc["schedule"] = ln.annotate_schedule(doc.get("schedule"))
    return {"data": serialize_doc(doc), "metrics": ln.loan_metrics(doc),
            "payments": serialize_doc(payments), "schedule_preview": preview}


@router.post("/loans")
async def create(payload: LoanCreate,
                 user: dict = Depends(require_permission("loans", "create"))):
    try:
        doc = await ln.create_loan(payload, user.get("email"), user.get("org_id", ORG_ID))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit_log(user, "create", "loans", doc["id"], {"principal": doc["principal"]})
    return {"data": serialize_doc(doc)}


@router.post("/loans/{loan_id}/activate")
async def activate(loan_id: str, payload: LoanActivate,
                   user: dict = Depends(require_permission("loans", "approve"))):
    try:
        doc = await ln.activate_loan(loan_id, payload.source, payload.date, payload.note,
                                     user.get("email"), user.get("org_id", ORG_ID))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit_log(user, "activate", "loans", loan_id, {"principal": doc["principal"]})
    doc["schedule"] = ln.annotate_schedule(doc.get("schedule"))
    return {"data": serialize_doc(doc), "metrics": ln.loan_metrics(doc)}


@router.post("/loans/{loan_id}/pay")
async def pay(loan_id: str, payload: InstallmentPay,
              user: dict = Depends(require_permission("loans", "approve"))):
    try:
        doc = await ln.pay_installment(loan_id, payload.installment_no, payload.amount,
                                       payload.source, payload.date, payload.note,
                                       user.get("email"), user.get("org_id", ORG_ID))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit_log(user, "pay_installment", "loans", loan_id,
                    {"installment_no": payload.installment_no, "amount": payload.amount})
    doc["schedule"] = ln.annotate_schedule(doc.get("schedule"))
    return {"data": serialize_doc(doc), "metrics": ln.loan_metrics(doc)}
