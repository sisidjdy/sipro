"""Perpajakan (EPIC 3.3) — ringkasan PPN/PPh/BPHTB + SPT Masa PPN, lifecycle
catatan pajak (pending→reported→paid), dan Faktur Pajak Keluaran (+ PDF).

Phase 19: transisi status catatan pajak memicu jurnal GL — akrual saat
'reported'/'paid' (Dr Beban Pajak / Cr Utang Pajak) & setoran saat 'paid'
(Dr Utang Pajak / Cr Kas-Bank) + tautan NTPN.

RBAC resource `tax` (finance + owner/super_admin). Semua query ber-scope `org_id`.
"""
import io

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from db import db, ORG_ID
from core_utils import serialize_doc, now_iso, parse_pagination
from rbac import require_permission
import tax_engine as tx
import gl_engine as gl
from models import TaxRecordUpdate, FakturIssue

router = APIRouter(prefix="/tax", tags=["tax"])


@router.get("/summary")
async def summary(period: str = None, user: dict = Depends(require_permission("tax", "view"))):
    return {"data": await tx.tax_summary(user.get("org_id", ORG_ID), period)}


@router.get("/periods")
async def periods(user: dict = Depends(require_permission("tax", "view"))):
    return {"data": await tx.list_periods(user.get("org_id", ORG_ID))}


@router.get("/ppn-input")
async def ppn_input(period: str = None, user: dict = Depends(require_permission("tax", "view"))):
    return {"data": await tx.ppn_input(user.get("org_id", ORG_ID), period)}


@router.get("/records")
async def records(type: str = None, status: str = None, period: str = None,
                  skip: int = 0, limit: int = 100,
                  user: dict = Depends(require_permission("tax", "view"))):
    org = user.get("org_id", ORG_ID)
    skip, limit = parse_pagination(skip, limit)
    q = {"org_id": org}
    if type:
        q["type"] = type
    if status:
        q["status"] = status
    rows = await db.tax_records.find(q, {"_id": 0}).sort("created_at", -1).to_list(5000)
    if period:
        rows = [r for r in rows if tx.period_of(r.get("created_at")) == period]
    total = len(rows)
    page = rows[skip:skip + limit]
    return {"data": serialize_doc(await tx.enrich_records(org, page)), "total": total}


@router.put("/records/{record_id}")
async def update_record(record_id: str, payload: TaxRecordUpdate,
                        user: dict = Depends(require_permission("tax", "update"))):
    org = user.get("org_id", ORG_ID)
    rec = await db.tax_records.find_one({"id": record_id, "org_id": org}, {"_id": 0})
    if not rec:
        raise HTTPException(status_code=404, detail="Catatan pajak tidak ditemukan")
    updates = {"updated_at": now_iso()}
    for f in ("status", "report_date", "paid_date", "ntpn", "note", "cash_account_id"):
        v = getattr(payload, f)
        if v is not None:
            updates[f] = v
    # Setoran wajib menyertakan NTPN (Nomor Transaksi Penerimaan Negara).
    new_status = updates.get("status", rec.get("status"))
    if new_status == "paid" and not (updates.get("ntpn") or rec.get("ntpn")):
        raise HTTPException(status_code=400, detail="NTPN wajib diisi untuk menandai pajak sudah disetor.")
    if updates.get("cash_account_id"):
        import cash_bank as _cb
        try:
            await _cb.resolve_code(org, updates["cash_account_id"])
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    await db.tax_records.update_one({"id": record_id, "org_id": org}, {"$set": updates})
    fresh = await db.tax_records.find_one({"id": record_id, "org_id": org}, {"_id": 0})

    # Phase 19 — posting GL: akrual saat 'reported'/'paid', setoran saat 'paid'.
    enriched = (await tx.enrich_records(org, [fresh]))[0]
    gl_refs = {}
    if new_status in ("reported", "paid"):
        je = await gl.post_tax_accrual(org, enriched)
        if je:
            gl_refs["gl_accrual_entry_no"] = je["entry_no"]
    if new_status == "paid":
        je2 = await gl.post_tax_payment(org, enriched)
        if je2:
            gl_refs["gl_setor_entry_no"] = je2["entry_no"]
            gl_refs["gl_setor_entry_id"] = je2["id"]
    if gl_refs:
        await db.tax_records.update_one({"id": record_id, "org_id": org},
                                        {"$set": {**gl_refs, "updated_at": now_iso()}})
        fresh = await db.tax_records.find_one({"id": record_id, "org_id": org}, {"_id": 0})
    return {"data": serialize_doc(fresh)}


# ----------------------------- Faktur Pajak -----------------------------
@router.get("/faktur")
async def list_faktur(user: dict = Depends(require_permission("tax", "view"))):
    org = user.get("org_id", ORG_ID)
    rows = await db.faktur_pajak.find({"org_id": org}, {"_id": 0}).sort("issued_at", -1).to_list(2000)
    return {"data": serialize_doc(rows), "total": len(rows)}


@router.get("/faktur-candidates")
async def faktur_candidates(user: dict = Depends(require_permission("tax", "view"))):
    cands = await tx.faktur_candidates(user.get("org_id", ORG_ID))
    return {"data": cands, "total": len(cands)}


@router.post("/faktur")
async def create_faktur(payload: FakturIssue,
                        user: dict = Depends(require_permission("tax", "create"))):
    try:
        doc = await tx.issue_faktur(
            user.get("org_id", ORG_ID), payload.deal_id, user.get("email"),
            buyer_npwp=payload.buyer_npwp, transaction_code=payload.transaction_code or "010")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"data": serialize_doc(doc)}


@router.get("/faktur/{faktur_id}")
async def get_faktur(faktur_id: str, user: dict = Depends(require_permission("tax", "view"))):
    doc = await db.faktur_pajak.find_one({"id": faktur_id, "org_id": user.get("org_id", ORG_ID)}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Faktur pajak tidak ditemukan")
    return {"data": serialize_doc(doc)}


@router.get("/faktur/{faktur_id}/pdf")
async def faktur_pdf(faktur_id: str, user: dict = Depends(require_permission("tax", "view"))):
    org = user.get("org_id", ORG_ID)
    doc = await db.faktur_pajak.find_one({"id": faktur_id, "org_id": org}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Faktur pajak tidak ditemukan")
    org_doc = await db.orgs.find_one({"id": org}, {"_id": 0, "name": 1}) or {}
    import doc_layout as dl
    layout = await dl.get_layout(user.get("org_id", ORG_ID), "FAKTUR")
    pdf = tx.faktur_pdf_bytes(doc, org_name=org_doc.get("name", "PT SIPRO Land"),
                              layout=layout, images=await dl.images(user.get("org_id", ORG_ID), layout))
    return StreamingResponse(
        io.BytesIO(pdf), media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename=faktur-{doc.get('number', 'fp')}.pdf"})
