"""Kepatuhan pajak (Fase 49E/49F/49G) — faktur pengganti/batal, ekspor berkas, bukti potong
(e-Bupot), dan rekap SPT Masa PPN.

Kenapa router terpisah dari `tax_router.py`: modul lama hanya MENERBITKAN faktur dan
menampilkan worksheet. Yang ditambahkan di sini adalah kewajiban kepatuhan yang bisa
mengubah/menghapus dampak dokumen pajak (pengganti, pembatalan, pembetulan) dan mengeluarkan
BERKAS untuk diunggah ke DJP. Aksinya dipisah supaya izinnya bisa berbeda:

* melihat        → `tax:view`
* mengubah jejak → `tax:update`   (pengganti/batal faktur, pembetulan/pembatalan bukti potong)
* menerbitkan    → `tax:withholding_issue`
* mengeluarkan berkas → `tax:export`

`finance` memegang `tax:manage` sehingga lulus semuanya; peran lain (sales/pm/site) dijawab
403 — memang begitu, sebab berkas pajak adalah pernyataan resmi perusahaan.

Semua ekspor MENAHAN diri bila data wajib belum lengkap (`ExportHold` → HTTP 409) dan
menyebut dokumen mana yang harus dilengkapi. Tidak ada berkas berkolom kosong.
"""
import io

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

import tax_engine as te
import tax_faktur_export as tfx
import withholding_engine as wh
from core_utils import serialize_doc
from db import db, ORG_ID
from models_p49 import (FakturCancel, FakturReplace, WithholdingCancel, WithholdingCorrect,
                        WithholdingIssue)
from rbac import audit_log, require_permission

router = APIRouter(prefix="/tax/compliance", tags=["tax-compliance"])


def _hold(exc: tfx.ExportHold) -> HTTPException:
    """409 + pesan yang menyebut sebabnya satu per satu (bukan 'ekspor gagal')."""
    return HTTPException(status_code=409, detail=("Ekspor ditahan — " + " | ".join(exc.reasons)))


def _period(value: str) -> str:
    """Masa pajak opsional; default masa berjalan supaya endpoint sweep tetap 200."""
    if not value:
        from core_utils import now_iso
        return now_iso()[:7]
    if len(value) != 7 or value[4] != "-":
        raise HTTPException(status_code=400, detail="Format masa pajak harus YYYY-MM (mis. 2026-08).")
    return value


# ============================================================ 49E faktur pajak keluaran
@router.get("/faktur")
async def list_faktur(period: str = None, status: str = None,
                      user: dict = Depends(require_permission("tax", "view"))):
    org = user.get("org_id", ORG_ID)
    data = await tfx.list_faktur(org, period=period or None, status=status or None)
    return {"data": serialize_doc(data["rows"]), "summary": data["summary"],
            "total": len(data["rows"])}


@router.get("/faktur/periods")
async def faktur_periods(user: dict = Depends(require_permission("tax", "view"))):
    rows = await db.faktur_pajak.distinct("period", {"org_id": user.get("org_id", ORG_ID)})
    return {"data": sorted((p for p in rows if p), reverse=True)}


@router.post("/faktur/{faktur_id}/replace")
async def replace_faktur(faktur_id: str, payload: FakturReplace,
                         user: dict = Depends(require_permission("tax", "update"))):
    org = user.get("org_id", ORG_ID)
    try:
        doc = await tfx.replace_faktur(org, faktur_id, user.get("email"), payload.reason,
                                       buyer_npwp=payload.buyer_npwp,
                                       buyer_name=payload.buyer_name, dpp=payload.dpp)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit_log(user, "replace", "faktur_pajak", faktur_id,
                    {"new_number": doc.get("number"), "reason": payload.reason})
    return {"data": serialize_doc(doc)}


@router.post("/faktur/{faktur_id}/cancel")
async def cancel_faktur(faktur_id: str, payload: FakturCancel,
                        user: dict = Depends(require_permission("tax", "update"))):
    org = user.get("org_id", ORG_ID)
    try:
        doc = await tfx.cancel_faktur(org, faktur_id, user.get("email"), payload.reason)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit_log(user, "cancel", "faktur_pajak", faktur_id, {"reason": payload.reason})
    return {"data": serialize_doc(doc)}


@router.get("/faktur-export/check")
async def faktur_export_check(period: str = None,
                              user: dict = Depends(require_permission("tax", "view"))):
    return {"data": serialize_doc(
        await tfx.export_check(user.get("org_id", ORG_ID), _period(period)))}


@router.get("/faktur-export/file")
async def faktur_export_file(period: str = None, format: str = "coretax_xml",
                             user: dict = Depends(require_permission("tax", "export"))):
    org = user.get("org_id", ORG_ID)
    try:
        name, media, blob = await tfx.export_file(org, _period(period), format)
    except tfx.ExportHold as e:
        raise _hold(e)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit_log(user, "export", "faktur_pajak", _period(period), {"format": format})
    return StreamingResponse(io.BytesIO(blob), media_type=media,
                             headers={"Content-Disposition": f"attachment; filename={name}"})


# ============================================================ 49G rekap SPT Masa PPN
@router.get("/vat-return")
async def vat_return(period: str = None,
                     user: dict = Depends(require_permission("tax", "view"))):
    org = user.get("org_id", ORG_ID)
    return {"data": serialize_doc(await tfx.vat_return(org, _period(period)))}


@router.get("/periods")
async def periods(user: dict = Depends(require_permission("tax", "view"))):
    """Masa pajak yang punya data (faktur, catatan pajak, tagihan, bukti potong)."""
    org = user.get("org_id", ORG_ID)
    out = set(await te.list_periods(org))
    out |= set(await db.faktur_pajak.distinct("period", {"org_id": org}) or [])
    out |= set(await wh.periods(org))
    return {"data": sorted((p for p in out if p), reverse=True)}


# ============================================================ 49F bukti potong (e-Bupot)
@router.get("/withholding")
async def list_withholding(period: str = None, kind: str = None, state: str = None,
                           user: dict = Depends(require_permission("tax", "view"))):
    org = user.get("org_id", ORG_ID)
    data = await wh.list_docs(org, period=period or None, kind=kind or None,
                              state=state or None)
    return {"data": serialize_doc(data["rows"]), "summary": data["summary"],
            "tie_out": data["tie_out"], "missing": data["missing"],
            "detail": data["detail"], "note": data["note"], "total": len(data["rows"])}


@router.get("/withholding/summary")
async def withholding_summary(period: str = None,
                              user: dict = Depends(require_permission("tax", "view"))):
    return {"data": serialize_doc(
        await wh.summary(user.get("org_id", ORG_ID), _period(period)))}


@router.get("/withholding/candidates")
async def withholding_candidates(period: str = None,
                                 user: dict = Depends(require_permission("tax", "view"))):
    """Potongan PPh NYATA yang belum punya bukti potong (daftar kerja, bukan angka karangan)."""
    return {"data": serialize_doc(
        await wh.candidates(user.get("org_id", ORG_ID), period or None))}


@router.get("/withholding/config")
async def withholding_config(user: dict = Depends(require_permission("tax", "view"))):
    """Tarif bawaan + identitas pemotong — layar TIDAK menghitung ulang tarif sendiri."""
    return {"data": serialize_doc(await wh.config(user.get("org_id", ORG_ID)))}


@router.get("/withholding-export/check")
async def withholding_export_check(period: str = None,
                                   user: dict = Depends(require_permission("tax", "view"))):
    return {"data": serialize_doc(
        await wh.export_check(user.get("org_id", ORG_ID), _period(period)))}


@router.get("/withholding-export/file")
async def withholding_export_file(period: str = None, format: str = "coretax_xml",
                                  user: dict = Depends(require_permission("tax", "export"))):
    org = user.get("org_id", ORG_ID)
    try:
        name, media, blob = await wh.export_file(org, _period(period), format)
    except tfx.ExportHold as e:
        raise _hold(e)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit_log(user, "export", "withholding_docs", _period(period), {"format": format})
    return StreamingResponse(io.BytesIO(blob), media_type=media,
                             headers={"Content-Disposition": f"attachment; filename={name}"})


@router.post("/withholding/issue")
async def issue_withholding(payload: WithholdingIssue,
                            user: dict = Depends(require_permission("tax", "withholding_issue"))):
    org = user.get("org_id", ORG_ID)
    try:
        doc = await wh.issue(org, user.get("email"), payload.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not doc.get("idempotent"):
        await audit_log(user, "issue", "withholding_docs", doc["id"],
                        {"number": doc.get("number"), "amount": doc.get("amount")})
    return {"data": serialize_doc(doc)}


@router.post("/withholding/from-fee/{fee_id}")
async def issue_withholding_for_fee(fee_id: str, object_code: str = None,
                                    user: dict = Depends(
                                        require_permission("tax", "withholding_issue"))):
    """Terbitkan bukti potong atas PPh fee mitra yang SUDAH dipotong saat fee disetujui."""
    org = user.get("org_id", ORG_ID)
    try:
        doc = await wh.issue_for_fee(org, user.get("email"), fee_id, object_code)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not doc.get("idempotent"):
        await audit_log(user, "issue", "withholding_docs", doc["id"],
                        {"number": doc.get("number"), "fee_id": fee_id})
    return {"data": serialize_doc(doc)}


@router.post("/withholding/{doc_id}/correct")
async def correct_withholding(doc_id: str, payload: WithholdingCorrect,
                              user: dict = Depends(require_permission("tax", "update"))):
    org = user.get("org_id", ORG_ID)
    try:
        doc = await wh.correct(org, doc_id, user.get("email"), payload.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit_log(user, "correct", "withholding_docs", doc_id,
                    {"number": doc.get("number"), "version": doc.get("version"),
                     "reason": payload.reason})
    return {"data": serialize_doc(doc)}


@router.post("/withholding/{doc_id}/cancel")
async def cancel_withholding(doc_id: str, payload: WithholdingCancel,
                             user: dict = Depends(require_permission("tax", "update"))):
    org = user.get("org_id", ORG_ID)
    try:
        doc = await wh.cancel(org, doc_id, user.get("email"), payload.reason)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit_log(user, "cancel", "withholding_docs", doc_id, {"reason": payload.reason})
    return {"data": serialize_doc(doc)}


@router.get("/withholding/{doc_id}")
async def get_withholding(doc_id: str, user: dict = Depends(require_permission("tax", "view"))):
    doc = await db.withholding_docs.find_one(
        {"id": doc_id, "org_id": user.get("org_id", ORG_ID)}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Bukti potong tidak ditemukan.")
    return {"data": serialize_doc(doc)}


@router.get("/withholding/{doc_id}/pdf")
async def withholding_pdf(doc_id: str, user: dict = Depends(require_permission("tax", "view"))):
    org = user.get("org_id", ORG_ID)
    doc = await db.withholding_docs.find_one({"id": doc_id, "org_id": org}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Bukti potong tidak ditemukan.")
    cfg = await wh.config(org)
    import doc_layout as dl
    layout = await dl.get_layout(user.get("org_id", ORG_ID), "BUPOT")
    pdf = wh.pdf_bytes(doc, org_name=cfg["company_name"], company_npwp=cfg["company_npwp"],
                      layout=layout, images=await dl.images(user.get("org_id", ORG_ID), layout))
    return StreamingResponse(
        io.BytesIO(pdf), media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename=bupot-{doc.get('number', 'bp')}.pdf"})
