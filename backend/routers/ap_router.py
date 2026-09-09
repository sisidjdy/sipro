"""AP (utang subcon) tipis: bills manual + retensi + approval + pembayaran + aging.

Fase 49F menambah satu pintu: pembayaran yang MEMOTONG PPh (vendor terima neto, potongan
menjadi utang pajak + bukti potong bernomor terbit otomatis).
"""
from fastapi import APIRouter, Depends, HTTPException

from db import db, ORG_ID
from core_utils import serialize_doc, parse_pagination
from rbac import require_permission, audit_log
import finance_engine as fe
import withholding_engine as wh
from models import ApBillCreate, ApPay
from models_p49 import BillPayWithholding

router = APIRouter(prefix="/finance/ap", tags=["finance-ap"])


@router.get("/bills")
async def list_bills(status: str = None, skip: int = 0, limit: int = 50,
                     user: dict = Depends(require_permission("finance", "view"))):
    org = user.get("org_id", ORG_ID)
    skip, limit = parse_pagination(skip, limit)
    q = {"org_id": org}
    if status:
        q["status"] = status
    total = await db.ap_invoices.count_documents(q)
    rows = await db.ap_invoices.find(q, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    return {"data": serialize_doc(rows), "total": total}


@router.get("/aging")
async def ap_aging(user: dict = Depends(require_permission("finance", "view"))):
    return {"data": await fe.ap_aging(user.get("org_id", ORG_ID))}


@router.post("/bills")
async def create_bill(payload: ApBillCreate,
                      user: dict = Depends(require_permission("finance", "create"))):
    if payload.claimed <= 0:
        raise HTTPException(status_code=400, detail="Nilai klaim harus lebih dari 0")
    bill = await fe.create_ap_bill(payload.vendor, payload.project_id, payload.claimed,
                                   payload.retention_pct, payload.due_date, payload.note,
                                   user.get("email"), user.get("org_id", ORG_ID))
    return {"data": serialize_doc(bill)}


@router.post("/bills/{bill_id}/approve")
async def approve_bill(bill_id: str,
                       user: dict = Depends(require_permission("finance", "approve"))):
    try:
        bill = await fe.approve_ap_bill(bill_id, user.get("email"), user.get("org_id", ORG_ID))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"data": serialize_doc(bill)}


@router.post("/bills/{bill_id}/pay")
async def pay_bill(bill_id: str, payload: ApPay,
                   user: dict = Depends(require_permission("finance", "approve"))):
    if payload.amount <= 0:
        raise HTTPException(status_code=400, detail="Jumlah bayar harus lebih dari 0")
    try:
        bill = await fe.pay_ap_bill(bill_id, payload.amount, payload.note,
                                    user.get("email"), user.get("org_id", ORG_ID),
                                    cash_account_id=payload.cash_account_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"data": serialize_doc(bill)}


@router.post("/bills/{bill_id}/pay-withholding")
async def pay_bill_with_withholding(bill_id: str, payload: BillPayWithholding,
                                    user: dict = Depends(require_permission("finance", "approve"))):
    """Bayar tagihan DENGAN MEMOTONG PPh (Fase 49F): vendor menerima NET, potongan menjadi
    utang pajak, dan bukti potong bernomor terbit otomatis.

    Cacat yang ditutup: sebelum ini pembayaran selalu bruto. Kalau perusahaan sebenarnya
    memotong PPh jasa konstruksi/PPh 23, angka di sistem berbeda dengan uang yang benar-benar
    keluar dari bank, dan potongan yang menjadi kewajiban setor tidak pernah tercatat —
    bukti potong pun tidak bisa diterbitkan karena tidak ada pasangannya di pembukuan.

    Jurnalnya: `Dr 2-1100 Utang Usaha (bruto) / Cr 1-1200 Bank (neto) / Cr 2-1300 Utang Pajak`.
    Nilai potongan dihitung DI SINI (tarif × dasar) supaya angkanya terbaca sebelum uang keluar.
    """
    org = user.get("org_id", ORG_ID)
    bill = await db.ap_invoices.find_one({"id": bill_id, "org_id": org}, {"_id": 0})
    if not bill:
        raise HTTPException(status_code=404, detail="Tagihan AP tidak ditemukan.")
    base = int(payload.base or payload.amount)
    withheld = wh.tax_of(base, payload.rate)
    if withheld <= 0:
        raise HTTPException(status_code=400, detail=(
            f"Potongan hasil hitungan Rp 0 (dasar Rp {base:,} × {payload.rate}%). "
            "Pakai pembayaran biasa bila memang tidak ada potongan PPh."))
    memo = (f"PPh {payload.kind} {payload.rate}% atas "
            f"{bill.get('vendor')} (dasar Rp {base:,})")
    try:
        updated, payment = await fe.pay_ap_bill(
            bill_id, payload.amount, payload.note, user.get("email"), org,
            withhold={"kind": payload.kind, "base": base, "rate": payload.rate,
                      "amount": withheld, "memo": memo},
            return_payment=True, cash_account_id=payload.cash_account_id)
        doc = await wh.issue_for_bill_payment(
            org, user.get("email"), bill=bill, payment=payment, kind=payload.kind,
            base=base, rate=payload.rate, object_code=payload.object_code,
            note=payload.note)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit_log(user, "pay_withholding", "ap_invoices", bill_id,
                    {"amount": payload.amount, "withheld": withheld,
                     "bupot": doc.get("number")})
    return {"data": {"bill": serialize_doc(updated), "payment": serialize_doc(payment),
                     "withholding": serialize_doc(doc),
                     "cash_out": int(payload.amount) - withheld, "withheld": withheld,
                     "detail": (f"Kas keluar Rp {int(payload.amount) - withheld:,} ke "
                                f"{bill.get('vendor')}; PPh Rp {withheld:,} menjadi utang pajak "
                                f"dan dibuktikan bukti potong {doc.get('number')}.")}}


@router.get("/payments")
async def list_payments(bill_id: str = None, skip: int = 0, limit: int = 50,
                        user: dict = Depends(require_permission("finance", "view"))):
    """Riwayat pembayaran keluar. Sebelum audit koleksi `payments_out` DITULIS tapi tidak
    punya endpoint baca sama sekali, jadi bukti pembayaran tidak bisa ditelusuri."""
    skip, limit = parse_pagination(skip, limit)
    q = {"org_id": user.get("org_id", ORG_ID)}
    if bill_id:
        q["bill_id"] = bill_id
    total = await db.payments_out.count_documents(q)
    rows = await db.payments_out.find(q, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    paid_total = 0
    async for r in db.payments_out.aggregate([{"$match": q}, {"$group": {"_id": None, "s": {"$sum": "$amount"}}}]):
        paid_total = int(r.get("s") or 0)
    return {"data": serialize_doc(rows), "total": total, "summary": {"paid_total": paid_total}}
