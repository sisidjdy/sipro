"""ROUTER PEMBATALAN & REFUND (Fase 56C) — prefix `/cancellations`.

Pemisahan tugas yang dipaksakan di sini (dan diuji gate 47):
  * **mengajukan** pembatalan = `cancellation:create` (Manajer Sales / Marketing Admin);
  * **memutuskan** = `cancellation:approve` (Manajer Keuangan / Direksi) — dan pengaju
    tidak boleh memutuskan pengajuannya sendiri (dijaga mesin, bukan hanya layar);
  * **membayar refund** = `cancellation:update` (Keuangan);
  * **mengabaikan penahanan "menunggu unit terjual kembali"** = `cancellation:override`
    (hanya Manajer Keuangan), wajib alasan minimal 10 huruf.
"""
from fastapi import APIRouter, Depends, HTTPException

import cancellation_engine as cx
import contracts_engine as ce
from core_utils import parse_pagination, serialize_doc
from db import ORG_ID, db
from models_p56 import CancellationDecisionIn, CancellationRequestIn, RefundPayIn
from rbac import audit_log, can, is_scoped_sales, require_permission

router = APIRouter(prefix="/cancellations", tags=["cancellations"])


def _org(user: dict) -> str:
    return user.get("org_id", ORG_ID)


async def _contract_scoped(contract_id: str, user: dict) -> dict:
    try:
        c = await ce.get_raw(_org(user), contract_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    if is_scoped_sales(user) and c.get("assigned_to") != user.get("email"):
        raise HTTPException(status_code=403, detail="Akses ditolak: bukan kontrak Anda")
    return c


@router.get("/preview")
async def preview(contract_id: str,
                  user: dict = Depends(require_permission("cancellation", "view"))):
    """Hitungan pembatalan + SEBAB bila belum boleh diajukan (bukan tombol mati)."""
    contract = await _contract_scoped(contract_id, user)
    out = await cx.preview(_org(user), contract)
    return {"data": serialize_doc(out)}


@router.get("")
async def listing(state: str = None, contract_id: str = None, customer_id: str = None,
                  q: str = None, skip: int = 0, limit: int = 50,
                  user: dict = Depends(require_permission("cancellation", "view"))):
    skip, limit = parse_pagination(skip, limit)
    out = await cx.listing(_org(user), state=state, contract_id=contract_id,
                           customer_id=customer_id, q=q, skip=skip, limit=limit)
    tersembunyi = 0
    if is_scoped_sales(user):
        milik = [r for r in out["data"] if r.get("assigned_to") == user.get("email")]
        tersembunyi = len(out["data"]) - len(milik)
        out["data"], out["total"] = milik, len(milik)
    resp = {"data": serialize_doc(out["data"]), "total": out["total"],
            "counts": out["counts"]}
    if tersembunyi and not out["data"]:
        # Kejujuran lingkup data (pelajaran Fase 56A): "tidak ada" dan "bukan milik Anda"
        # tidak boleh diceritakan dengan kalimat yang sama.
        resp["reason_code"] = "di_luar_lingkup"
        resp["reason"] = (f"Ada {tersembunyi} pengajuan pembatalan, tetapi lead-nya dipegang "
                          "rekan lain sehingga di luar lingkup data Anda.")
    return resp


@router.get("/{cid}")
async def detail(cid: str,
                 user: dict = Depends(require_permission("cancellation", "view"))):
    try:
        row = await cx.get(_org(user), cid)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    if is_scoped_sales(user) and row.get("assigned_to") != user.get("email"):
        raise HTTPException(status_code=403, detail="Akses ditolak: bukan pengajuan Anda")
    return {"data": serialize_doc(row)}


@router.post("")
async def request_cancellation(payload: CancellationRequestIn,
                              user: dict = Depends(require_permission("cancellation",
                                                                     "create"))):
    contract = await _contract_scoped(payload.contract_id, user)
    try:
        doc = await cx.request(_org(user), contract, user.get("email"), payload.reason)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit_log(user, "create", "cancellation", doc["id"],
                    {"contract_id": payload.contract_id, "reason": payload.reason})
    return {"data": serialize_doc(await cx.enrich(_org(user), doc))}


@router.post("/{cid}/decision")
async def decide(cid: str, payload: CancellationDecisionIn,
                 user: dict = Depends(require_permission("cancellation", "approve"))):
    """Keputusan Manajer Keuangan — di sinilah jurnal potongan & utang refund lahir."""
    try:
        doc = await cx.decide(_org(user), cid, user.get("email"), payload.approved,
                              payload.note)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit_log(user, "approve" if payload.approved else "reject", "cancellation", cid,
                    {"note": payload.note})
    return {"data": serialize_doc(await cx.enrich(_org(user), doc))}


@router.post("/{cid}/refund")
async def pay_refund(cid: str, payload: RefundPayIn,
                     user: dict = Depends(require_permission("cancellation", "update"))):
    """Bayar refund (boleh bertahap). Idempoten lewat `client_ref`."""
    may_override = await can(user.get("role"), "cancellation", "override")
    try:
        out = await cx.pay_refund(_org(user), cid, user.get("email"),
                                  method=payload.method, amount=payload.amount,
                                  client_ref=payload.client_ref, note=payload.note,
                                  override=payload.override,
                                  override_reason=payload.override_reason,
                                  may_override=may_override,
                                  cash_account_id=payload.cash_account_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not out.get("replay"):
        await audit_log(user, "update", "cancellation", cid,
                        {"refund": out["payment"]["amount"], "method": payload.method,
                         "override": payload.override})
    return {"data": serialize_doc(await cx.enrich(_org(user), out["cancellation"])),
            "payment": serialize_doc(out["payment"]), "replay": out.get("replay", False)}


@router.get("/by-contract/{contract_id}/document")
async def document_of(contract_id: str,
                      user: dict = Depends(require_permission("cancellation", "view"))):
    """Berita Acara Pembatalan milik kontrak ini (bila sudah ada) — untuk tombol Cetak."""
    await _contract_scoped(contract_id, user)
    row = await db.cancellations.find_one(
        {"org_id": _org(user), "contract_id": contract_id,
         "document_id": {"$ne": None}}, {"_id": 0}, sort=[("created_at", -1)])
    if not row:
        return {"data": None,
                "reason": "Belum ada berita acara pembatalan pada kontrak ini."}
    doc = await db.documents.find_one({"id": row["document_id"]}, {"_id": 0, "content": 0})
    return {"data": serialize_doc(doc)}
