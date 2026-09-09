"""PORTAL PEMBELI — BUKTI BAYAR BOOKING FEE (Fase 69B), prefix `/portal`.

Dipisah dari `portal_router.py` agar berkas itu tetap di bawah 800 baris. Memakai penolong
identitas yang sama (`_customer`, `_deals`) sehingga pembeli yang masih berstatus LEAD (belum
akad) pun bisa masuk dan melihat/mengirim bukti booking fee-nya.
"""
from fastapi import APIRouter, Depends, HTTPException

import booking_fee as bf
from core_utils import serialize_doc
from db import ORG_ID, db
from models_p69 import PortalBookingFeeProofIn
from routers.portal_router import _customer, _deals, get_portal_user

router = APIRouter(prefix="/portal", tags=["portal"])


@router.post("/booking-fee/proof")
async def submit_booking_fee_proof(payload: PortalBookingFeeProofIn,
                                   pu: dict = Depends(get_portal_user)):
    """Pembeli mengirim bukti transfer BOOKING FEE — klaim, bukan pelunasan. Keuangan
    memverifikasi satu klik dari rincian deal; barulah kwitansi & status LUNAS lahir."""
    org = pu.get("org_id", ORG_ID)
    cust = await _customer(pu)
    deals = await _deals(pu, cust)
    deal = next((d for d in deals if d["id"] == payload.deal_id), None)
    if not deal:
        raise HTTPException(status_code=404, detail="Transaksi tidak ditemukan pada akun Anda.")
    owned = await db.files.count_documents(
        {"org_id": org, "id": {"$in": payload.file_ids}, "owner_type": "payment_proof",
         "portal_customer_id": cust.get("id"), "is_deleted": False})
    if owned != len(payload.file_ids):
        raise HTTPException(status_code=400, detail=(
            "Berkas bukti tidak lengkap atau bukan milik akun Anda — unggah ulang fotonya."))
    try:
        doc = await bf.submit_proof(org, customer=cust, deal=deal, amount=payload.amount,
                                    transfer_date=payload.transfer_date,
                                    file_ids=payload.file_ids, bank_name=payload.bank_name,
                                    note=payload.note,
                                    actor=(pu.get("email") or pu.get("phone") or cust.get("name")))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"data": serialize_doc(doc),
            "message": ("Bukti booking fee terkirim — menunggu verifikasi keuangan. "
                        "Status berubah LUNAS setelah diverifikasi.")}
