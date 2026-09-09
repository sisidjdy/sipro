"""ROUTER BUKTI TRANSFER PELANGGAN (Fase 47B, sisi staf) — prefix `/payment-intakes`.

Sisi pelanggan ada di `portal_router.py`. Yang penting di sini: **verifikasi** adalah satu-
satunya pintu yang boleh mengubah tagihan, dan ia butuh izin `finance:approve` — bukan
`update` — karena mengakui uang masuk adalah keputusan kas, bukan penyuntingan data.
"""
from fastapi import APIRouter, Depends, HTTPException

import payment_intake as intake
from core_utils import parse_pagination, serialize_doc
from db import ORG_ID
from models_p47 import IntakeRejectIn, IntakeVerifyIn
from rbac import audit_log, require_permission

router = APIRouter(prefix="/payment-intakes", tags=["payment-intakes"])


def _org(user: dict) -> str:
    return user.get("org_id", ORG_ID)


@router.get("")
async def listing(state: str = None, deal_id: str = None, skip: int = 0, limit: int = 25,
                  user: dict = Depends(require_permission("finance", "view"))):
    skip, limit = parse_pagination(skip, limit)
    out = await intake.listing(_org(user), state=state, deal_id=deal_id, skip=skip,
                              limit=limit)
    return {"data": serialize_doc(out["data"]), "total": out["total"],
            "summary": out["summary"]}


@router.get("/{intake_id}")
async def detail(intake_id: str,
                 user: dict = Depends(require_permission("finance", "view"))):
    try:
        return {"data": serialize_doc(await intake.intake_or_error(_org(user), intake_id))}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{intake_id}/verify")
async def verify(intake_id: str, payload: IntakeVerifyIn,
                 user: dict = Depends(require_permission("finance", "approve"))):
    """Verifikasi bukti → tagihan berkurang lewat jalur resmi `apply_receipt`."""
    try:
        out = await intake.verify(_org(user), intake_id, user.get("email"),
                                  bank_txn_id=payload.bank_txn_id, note=payload.note,
                                  allow_overpay=payload.allow_overpay)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit_log(user, "verify", "payment_intakes", intake_id,
                    {"amount": out["intake"]["amount"],
                     "receipt_id": out["receipt"]["id"]})
    return {"data": serialize_doc(out),
            "message": "Bukti transfer diverifikasi — tagihan pelanggan sudah berkurang."}


@router.post("/{intake_id}/reject")
async def reject(intake_id: str, payload: IntakeRejectIn,
                 user: dict = Depends(require_permission("finance", "approve"))):
    """Tolak bukti + alasan yang DIBACA pelanggan di portal. Tagihan tidak berubah."""
    try:
        out = await intake.reject(_org(user), intake_id, user.get("email"), payload.reason)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit_log(user, "reject", "payment_intakes", intake_id, {"reason": payload.reason})
    return {"data": serialize_doc(out), "message": "Bukti transfer ditolak dengan alasan."}
