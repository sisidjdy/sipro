"""ROUTER BOOKING FEE (Fase 69B) — prefix `/booking-fee`.

Tagihan & kwitansi booking fee: dibaca oleh siapa pun yang boleh melihat deal, pembayaran
dicatat oleh keuangan (`finance:create`) — sama seperti kwitansi termin.
"""
from fastapi import APIRouter, Depends, HTTPException, Response

import booking_fee as bf
from core_utils import serialize_doc
from db import ORG_ID, ORG_NAME, db
from models_p69 import BookingFeePayIn, BookingFeeRefundIn, BookingFeeRejectIn
from pdf_utils import build_document_pdf
from rbac import audit_log, is_scoped_sales, require_permission

router = APIRouter(prefix="/booking-fee", tags=["booking_fee"])


def _org(user: dict) -> str:
    return user.get("org_id", ORG_ID)


async def _deal_visible(org: str, deal_id: str, user: dict) -> dict:
    d = await db.deals.find_one({"id": deal_id, "org_id": org}, {"_id": 0})
    if not d:
        raise HTTPException(status_code=404, detail="Deal tidak ditemukan")
    if is_scoped_sales(user) and d.get("assigned_to") != user.get("email"):
        raise HTTPException(status_code=403, detail="Akses ditolak: bukan deal Anda")
    return d


@router.get("")
async def listing(status: str = None,
                  user: dict = Depends(require_permission("finance", "view"))):
    rows = await bf.listing(_org(user), status)
    return {"data": serialize_doc(rows), "total": len(rows),
            "summary": {s: sum(1 for r in rows if r["status"] == s)
                        for s in ("unpaid", "partial", "paid", "cancelled")}}


@router.get("/deals/{deal_id}")
async def detail(deal_id: str, user: dict = Depends(require_permission("deals", "view"))):
    org = _org(user)
    await _deal_visible(org, deal_id, user)
    return {"data": serialize_doc(await bf.detail(org, deal_id))}


@router.post("/deals/{deal_id}/pay")
async def pay(deal_id: str, payload: BookingFeePayIn,
              user: dict = Depends(require_permission("finance", "create"))):
    org = _org(user)
    await _deal_visible(org, deal_id, user)
    try:
        out = await bf.pay(org, deal_id, amount=payload.amount, method=payload.method,
                           note=payload.note, actor=user.get("email"))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit_log(user, "pay_booking_fee", "finance", deal_id,
                    {"amount": payload.amount, "receipt_no": out["receipt"]["receipt_no"]})
    return {"data": serialize_doc(out),
            "message": ("Booking fee LUNAS." if out["invoice"]["status"] == "paid"
                        else "Pembayaran booking fee sebagian dicatat.")}


@router.post("/deals/{deal_id}/proofs/{intake_id}/verify")
async def verify_proof(deal_id: str, intake_id: str, payload: dict = None,
                       user: dict = Depends(require_permission("finance", "create"))):
    """Satu klik: bukti transfer pembeli → kwitansi + LUNAS."""
    org = _org(user)
    await _deal_visible(org, deal_id, user)
    try:
        out = await bf.verify_proof(org, intake_id, user.get("email"), (payload or {}).get("note"))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit_log(user, "verify_booking_fee_proof", "finance", deal_id, {"intake_id": intake_id})
    return {"data": serialize_doc(out), "message": "Bukti diverifikasi — booking fee tercatat."}


@router.post("/deals/{deal_id}/proofs/{intake_id}/reject")
async def reject_proof(deal_id: str, intake_id: str, payload: BookingFeeRejectIn,
                       user: dict = Depends(require_permission("finance", "create"))):
    import payment_intake as intake
    org = _org(user)
    await _deal_visible(org, deal_id, user)
    try:
        out = await intake.reject(org, intake_id, user.get("email"), payload.reason)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"data": serialize_doc(out), "message": "Bukti ditolak dengan alasan."}


@router.post("/deals/{deal_id}/refund")
async def refund(deal_id: str, payload: BookingFeeRefundIn,
                 user: dict = Depends(require_permission("finance", "create"))):
    org = _org(user)
    await _deal_visible(org, deal_id, user)
    try:
        out = await bf.refund(org, deal_id, amount=payload.amount, method=payload.method,
                              note=payload.note, actor=user.get("email"),
                              finalize=payload.finalize)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit_log(user, "refund_booking_fee", "finance", deal_id,
                    {"amount": payload.amount, "receipt_no": out["refund"]["receipt_no"]})
    return {"data": serialize_doc(out),
            "message": f"Refund {out['refund']['receipt_no']} dicatat."}


@router.get("/deals/{deal_id}/refunds/{refund_id}/pdf")
async def refund_pdf(deal_id: str, refund_id: str,
                     user: dict = Depends(require_permission("deals", "view"))):
    org = _org(user)
    await _deal_visible(org, deal_id, user)
    rec = await db.receipts.find_one({"id": refund_id, "org_id": org, "deal_id": deal_id,
                                      "kind": "booking_fee_refund"}, {"_id": 0})
    if not rec:
        raise HTTPException(status_code=404, detail="Bukti refund tidak ditemukan.")

    def rp(v):
        return "Rp " + f"{int(v or 0):,}".replace(",", ".")

    lines = [f"Diterima oleh : {rec.get('lead_name') or '-'}", f"Unit : {rec.get('unit_code') or '-'}",
             f"Tagihan booking fee : {rec.get('invoice_no')}",
             f"Jumlah dikembalikan : {rp(rec['amount'])}",
             f"Metode : {rec.get('method')}",
             f"Sisa yang hangus : {rp(rec.get('forfeited'))}",
             f"Tanggal : {str(rec.get('created_at'))[:10]}",
             f"Catatan : {rec.get('note') or '-'}"]
    import doc_layout as dl
    lay = await dl.get_layout(org, "KWITANSI")
    body = build_document_pdf(layout=lay, images=await dl.images(org, lay),
                              title="BUKTI PENGEMBALIAN BOOKING FEE", doc_number=rec["receipt_no"],
                              script_context={"date": str(rec.get("created_at") or "")[:10]},
                              content="\n".join(lines),
                              signatures=[{"role": "Keuangan", "name": None, "signed_at": None},
                                          {"role": "Penerima", "name": rec.get("lead_name"),
                                           "signed_at": None}])
    return Response(content=body, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{rec["receipt_no"]}.pdf"'})


@router.get("/deals/{deal_id}/invoice/pdf")
async def invoice_pdf(deal_id: str, user: dict = Depends(require_permission("deals", "view"))):
    org = _org(user)
    await _deal_visible(org, deal_id, user)
    inv = await bf.get_invoice(org, deal_id)
    if not inv:
        raise HTTPException(status_code=404, detail="Tagihan booking fee tidak ada.")

    def rp(v):
        return "Rp " + f"{int(v or 0):,}".replace(",", ".")

    status_label = {"unpaid": "BELUM DIBAYAR", "partial": "DIBAYAR SEBAGIAN", "paid": "LUNAS",
                    "cancelled": "DIBATALKAN"}.get(inv["status"], inv["status"])
    import doc_layout as dl
    import doc_script as ds
    from datetime import datetime as _dt
    deal = await db.deals.find_one({"id": deal_id}, {"_id": 0, "project_name": 1, "project_id": 1}) or {}
    project = await db.projects.find_one({"id": deal.get("project_id")}, {"_id": 0, "name": 1}) or {}
    intro = await ds.intro_for(org, "INVOICE_BF", {
        "doc_number": inv["no"], "date": _dt.now().strftime("%d-%m-%Y"), "org_name": ORG_NAME,
        "customer_name": inv.get("lead_name") or "-", "unit_code": inv.get("unit_code") or "-",
        "project_name": deal.get("project_name") or project.get("name") or "",
        "booking_fee": rp(inv["amount"]), "paid": rp(inv["paid"]), "outstanding": rp(inv["outstanding"]),
        "due_date": str(inv.get("due_date") or "-")[:10], "status": status_label}, use_default=True)
    lines = [f"Calon pembeli : {inv.get('lead_name') or '-'}", f"Unit : {inv.get('unit_code') or '-'}",
             f"Booking fee : {rp(inv['amount'])}", f"Sudah dibayar : {rp(inv['paid'])}",
             f"Sisa : {rp(inv['outstanding'])}", f"Status : {status_label}",
             f"Jatuh tempo : {str(inv.get('due_date') or '-')[:10]}", intro]
    lay = await dl.get_layout(org, "INVOICE_BF")
    body = build_document_pdf(layout=lay, images=await dl.images(org, lay),
                              title="TAGIHAN BOOKING FEE", doc_number=inv["no"],
                              content="\n".join(lines),
                              signatures=[{"role": "Keuangan", "name": None, "signed_at": None}])
    return Response(content=body, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{inv["no"]}.pdf"'})
