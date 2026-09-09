"""Serah terima unit, masa garansi & klaim garansi pasca-huni (Fase 50A).

Satu router untuk seluruh permukaan Fase 50A supaya aturannya tidak tersebar:
  * `/handover/check`               — daftar periksa sebelum kunci diserahkan
  * `/handover/issue`               — terbitkan BAST (ditahan bila belum bersih; idempoten)
  * `/handover/{id}/pdf`            — BAST sebagai PDF nyata
  * `/handover/{id}/cancel`         — pembatalan BAST salah terbit (beralasan, berjejak)
  * `/handover/warranty`            — masa garansi satu rumah (jujur bila belum ada datanya)
  * `/handover/warranty/board`      — papan pemantauan garansi seluruh proyek
  * `/handover/claims*`             — klaim garansi: ajukan, putuskan, selesaikan, periksa, tutup
  * `/handover/claims/report`       — rekap klaim yang bisa dijumlahkan (tie-out)

Kewenangan: `handover:create` menerbitkan BAST, `handover:override` menerobos daftar periksa,
`handover:cancel` membatalkan; `warranty:create` mengajukan klaim, `warranty:update`
mengerjakan, `warranty:approve` memeriksa & menutup. Tombol yang tidak berhak disembunyikan di
layar, tetapi endpoint tetap menjawab 403 supaya jalur API tidak bisa dipakai memutar aturan.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

import handover_engine as he
import warranty_engine as we
from core_utils import serialize_doc
from db import db, ORG_ID
from models_p50 import (HandoverCancel, HandoverIssue, WarrantyClaimClose,
                        WarrantyClaimComplete, WarrantyClaimCreate, WarrantyClaimDecision,
                        WarrantyClaimVerify)
import offline_intake as oi
from rbac import audit_log, can, require_permission

logger = logging.getLogger("sipro.handover")
router = APIRouter(prefix="/handover", tags=["handover"])


def _org(user: dict) -> str:
    return user.get("org_id", ORG_ID)


# ============================================================== serah terima unit
@router.get("/check")
async def check(unit_id: str = Query(...),
                user: dict = Depends(require_permission("handover", "view"))):
    try:
        return {"data": serialize_doc(await he.handover_check(_org(user), unit_id))}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("")
async def listing(project_id: str = None, unit_id: str = None, state: str = None,
                  user: dict = Depends(require_permission("handover", "view"))):
    out = await he.list_handovers(_org(user), project_id=project_id, unit_id=unit_id,
                                  state=state)
    return {"data": serialize_doc(out["rows"]), "total": out["summary"]["total"],
            "summary": out["summary"], "detail": out["detail"]}


@router.post("/issue")
async def issue(payload: HandoverIssue,
                user: dict = Depends(require_permission("handover", "create"))):
    """Terbitkan BAST. Ditahan 409 bila daftar periksa belum bersih (kecuali diterobos)."""
    org, actor = _org(user), user.get("email")
    if payload.override:
        if not await can(user.get("role"), "handover", "override"):
            raise HTTPException(
                status_code=403,
                detail=("Menerobos daftar periksa serah terima butuh kewenangan "
                        "Manajer Proyek/Keuangan atau Direksi. Tuntaskan pemeriksaan yang "
                        "menahan, atau mintakan terobosan ke atasan."))
    intake = await oi.begin(org, "handover_issue", payload.client_ref)
    if intake["state"] == "replay":
        return {"data": serialize_doc(intake["doc"]), "replay": True,
                "message": "Kiriman ini sudah pernah diterima — dokumen lamanya diputar ulang."}
    if intake["state"] == "inflight":
        raise HTTPException(status_code=409,
                            detail="Kiriman dengan penanda yang sama sedang diproses.")
    try:
        doc = await he.issue(
            org, payload.unit_id, actor, handed_over_at=payload.handed_over_at,
            received_by=payload.received_by, note=payload.note, meter_air=payload.meter_air,
            meter_listrik=payload.meter_listrik, keys_handed=payload.keys_handed,
            override=payload.override, override_reason=payload.override_reason,
            client_ref=payload.client_ref)
    except he.HandoverHold as hold:
        await oi.rollback(org, "handover_issue", payload.client_ref)
        raise HTTPException(status_code=409, detail={
            "message": (f"Serah terima DITAHAN: {len(hold.items)} pemeriksaan belum bersih. "
                        "Rumah tidak boleh diserahkan sebelum sebab di bawah dituntaskan."),
            "reasons": hold.reasons, "items": hold.items})
    except ValueError as e:
        await oi.rollback(org, "handover_issue", payload.client_ref)
        raise HTTPException(status_code=400, detail=str(e))
    await oi.commit(org, "handover_issue", payload.client_ref,
                    collection="unit_handovers", doc_id=doc["id"])
    await audit_log(user, "create", "unit_handover", doc["id"],
                    {"number": doc.get("number"), "unit_code": doc.get("unit_code"),
                     "override": bool(doc.get("override_by"))})
    replay = bool(doc.pop("replay", False))
    return {"data": serialize_doc(doc), "replay": replay,
            "message": (f"Rumah {doc.get('unit_code')} sudah diserahterimakan lewat "
                        f"{doc.get('number')}; masa garansi mulai {doc.get('handed_over_at')}."
                        if not replay else
                        f"{doc.get('number')} sudah ada — dokumen lamanya dipakai kembali.")}


# ==================================================================== masa garansi
@router.get("/warranty/unit")
async def warranty_unit(unit_id: str = Query(...), at: str = None,
                        user: dict = Depends(require_permission("warranty", "view"))):
    try:
        return {"data": serialize_doc(await he.warranty_status(_org(user), unit_id, at=at))}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/warranty/plan")
async def warranty_plan(user: dict = Depends(require_permission("warranty", "view"))):
    """Masa garansi per bagian yang sedang berlaku (dari Pusat Konfigurasi)."""
    return {"data": await he.warranty_plan(_org(user))}


@router.get("/warranty/for-complaint")
async def warranty_for_complaint(complaint_id: str = Query(...),
                                 user: dict = Depends(require_permission("warranty", "view"))):
    """Dari KELUHAN pembeli ke rumahnya + masa garansinya (Fase 50A).

    Kenapa endpoint ini ada: komplain menyimpan kode unit sebagai teks, jadi layar CS tidak
    punya cara pasti menemukan rumah yang dimaksud (apalagi masa garansinya). Tanpa jembatan
    ini, “jadikan klaim garansi” hanya bisa ditebak-tebak oleh petugas.
    """
    org = _org(user)
    comp = await db.complaints.find_one({"id": complaint_id, "org_id": org}, {"_id": 0})
    if not comp:
        raise HTTPException(status_code=404, detail="Komplain tidak ditemukan")
    unit_id = comp.get("unit_id")
    if not unit_id and comp.get("deal_id"):
        deal = await db.deals.find_one({"id": comp["deal_id"], "org_id": org},
                                       {"_id": 0, "unit_id": 1}) or {}
        unit_id = deal.get("unit_id")
    if not unit_id and comp.get("unit_code"):
        unit = await db.units.find_one({"org_id": org, "code": comp["unit_code"]},
                                       {"_id": 0, "id": 1}) or {}
        unit_id = unit.get("id")
    if not unit_id:
        return {"data": {"unit_id": None, "eligible": False,
                         "detail": ("Komplain ini tidak terikat rumah mana pun, jadi masa "
                                    "garansinya tidak bisa diperiksa \u2014 belum ada data.")}}
    status = await he.warranty_status(org, unit_id)
    return {"data": serialize_doc({
        "unit_id": unit_id,
        "unit_code": (status.get("unit") or {}).get("code"),
        "eligible": not status.get("missing"),
        "handover": status.get("handover"),
        "rows": status.get("rows"),
        "detail": status.get("detail"),
    })}


@router.get("/warranty/board")
async def warranty_board(project_id: str = None,
                         user: dict = Depends(require_permission("warranty", "view"))):
    out = await we.warranty_board(_org(user), project_id=project_id)
    return {"data": serialize_doc(out["rows"]), "total": out["total"], "detail": out["detail"]}


# =================================================================== klaim garansi
@router.get("/claims/report")
async def claims_report(project_id: str = None, period: str = None,
                        user: dict = Depends(require_permission("warranty", "view"))):
    return {"data": serialize_doc(await we.report(_org(user), project_id=project_id,
                                                  period=period))}


@router.get("/claims")
async def claims(unit_id: str = None, project_id: str = None, state: str = None,
                 category: str = None,
                 user: dict = Depends(require_permission("warranty", "view"))):
    out = await we.list_claims(_org(user), unit_id=unit_id, project_id=project_id,
                               state=state, category=category)
    return {"data": serialize_doc(out["rows"]), "total": out["total"],
            "summary": out["summary"], "detail": out["detail"]}


@router.post("/claims")
async def create_claim(payload: WarrantyClaimCreate,
                       user: dict = Depends(require_permission("warranty", "create"))):
    org = _org(user)
    intake = await oi.begin(org, "warranty_claim", payload.client_ref)
    if intake["state"] == "replay":
        return {"data": serialize_doc(intake["doc"]), "replay": True,
                "message": "Kiriman ini sudah pernah diterima — klaim lamanya diputar ulang."}
    if intake["state"] == "inflight":
        raise HTTPException(status_code=409,
                            detail="Kiriman dengan penanda yang sama sedang diproses.")
    try:
        doc = await we.create_claim(
            org, unit_id=payload.unit_id, category=payload.category, title=payload.title,
            description=payload.description, source=payload.source,
            complaint_id=payload.complaint_id, photo_file_ids=payload.photo_file_ids,
            actor=user.get("email"))
    except ValueError as e:
        await oi.rollback(org, "warranty_claim", payload.client_ref)
        raise HTTPException(status_code=400, detail=str(e))
    await oi.commit(org, "warranty_claim", payload.client_ref,
                    collection="warranty_claims", doc_id=doc["id"])
    await audit_log(user, "create", "warranty_claim", doc["id"],
                    {"number": doc.get("number"), "state": doc.get("state")})
    msg = (f"Klaim {doc['number']} diajukan dan masuk daftar kerja tim proyek."
           if doc["state"] == we.SUBMITTED else
           f"Klaim {doc['number']} DITOLAK: {doc.get('reject_detail')}")
    return {"data": serialize_doc(doc), "message": msg}


@router.get("/claims/{cid}")
async def claim_detail(cid: str, user: dict = Depends(require_permission("warranty", "view"))):
    doc = await db.warranty_claims.find_one({"id": cid, "org_id": _org(user)}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Klaim garansi tidak ditemukan")
    return {"data": serialize_doc(doc)}


@router.post("/claims/{cid}/decide")
async def decide(cid: str, payload: WarrantyClaimDecision,
                 user: dict = Depends(require_permission("warranty", "update"))):
    try:
        doc = await we.decide(_org(user), cid, accept=payload.accept, actor=user.get("email"),
                              reason=payload.reason, reject_reason=payload.reject_reason,
                              assigned_to=payload.assigned_to, due_date=payload.due_date)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit_log(user, "update", "warranty_claim", cid,
                    {"accept": payload.accept, "state": doc.get("state")})
    return {"data": serialize_doc(doc),
            "message": (f"Klaim {doc.get('number')} diterima — pekerjaan perbaikan dibuat "
                        f"untuk {doc.get('assigned_to') or 'tim proyek'}."
                        if payload.accept else
                        f"Klaim {doc.get('number')} ditolak beralasan; pembeli mendapat "
                        "jawaban tertulis.")}


@router.post("/claims/{cid}/complete")
async def complete(cid: str, payload: WarrantyClaimComplete,
                   user: dict = Depends(require_permission("warranty", "update"))):
    org = _org(user)
    intake = await oi.begin(org, "warranty_fix", payload.client_ref)
    if intake["state"] == "replay":
        return {"data": serialize_doc(intake["doc"]), "replay": True,
                "message": "Kiriman ini sudah pernah diterima."}
    if intake["state"] == "inflight":
        raise HTTPException(status_code=409,
                            detail="Kiriman dengan penanda yang sama sedang diproses.")
    try:
        doc = await we.complete(org, cid, actor=user.get("email"),
                                photo_file_ids=payload.photo_file_ids, note=payload.note)
    except ValueError as e:
        await oi.rollback(org, "warranty_fix", payload.client_ref)
        raise HTTPException(status_code=400, detail=str(e))
    await oi.commit(org, "warranty_fix", payload.client_ref,
                    collection="warranty_claims", doc_id=cid)
    return {"data": serialize_doc(doc),
            "message": (f"Perbaikan klaim {doc.get('number')} dinyatakan selesai dengan "
                        f"{len(payload.photo_file_ids)} bukti foto — menunggu pemeriksaan "
                        "orang lain.")}


@router.post("/claims/{cid}/verify")
async def verify(cid: str, payload: WarrantyClaimVerify,
                 user: dict = Depends(require_permission("warranty", "approve"))):
    try:
        doc = await we.verify(_org(user), cid, actor=user.get("email"), passed=payload.passed,
                              note=payload.note, reason=payload.reason)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit_log(user, "approve", "warranty_claim", cid, {"passed": payload.passed})
    return {"data": serialize_doc(doc),
            "message": (f"Perbaikan klaim {doc.get('number')} lolos pemeriksaan — menunggu "
                        "pengakuan pembeli." if payload.passed else
                        f"Perbaikan klaim {doc.get('number')} dikembalikan untuk diulang.")}


@router.post("/claims/{cid}/close")
async def close(cid: str, payload: WarrantyClaimClose,
                user: dict = Depends(require_permission("warranty", "approve"))):
    try:
        doc = await we.close(_org(user), cid, actor=user.get("email"), ack_by=payload.ack_by,
                             ack_note=payload.ack_note)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit_log(user, "update", "warranty_claim", cid, {"action": "close"})
    return {"data": serialize_doc(doc),
            "message": f"Klaim {doc.get('number')} ditutup dengan pengakuan pembeli."}


# ============================== rute ber-parameter DITARUH PALING BAWAH ==============================
# Kalau `/{hid}` didaftarkan sebelum `/claims` atau `/warranty/...`, FastAPI akan menangkap
# "claims" sebagai id berita acara dan seluruh permukaan klaim garansi menjawab 404.
@router.get("/{hid}")
async def detail(hid: str, user: dict = Depends(require_permission("handover", "view"))):
    doc = await db.unit_handovers.find_one({"id": hid, "org_id": _org(user)}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Berita acara serah terima tidak ditemukan")
    doc["warranty"] = he.warranty_rows(doc)
    return {"data": serialize_doc(doc)}


@router.get("/{hid}/pdf")
async def pdf(hid: str, user: dict = Depends(require_permission("handover", "view"))):
    try:
        blob, doc = await he.pdf_bytes(_org(user), hid)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    name = (doc.get("number") or "BAST").replace("/", "-")
    return Response(content=blob, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{name}.pdf"'})


@router.post("/{hid}/cancel")
async def cancel(hid: str, payload: HandoverCancel,
                 user: dict = Depends(require_permission("handover", "cancel"))):
    try:
        doc = await he.cancel(_org(user), hid, user.get("email"), payload.reason)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit_log(user, "update", "unit_handover", hid,
                    {"action": "cancel", "reason": payload.reason})
    return {"data": serialize_doc(doc),
            "message": (f"{doc.get('number')} dibatalkan; status rumah dikembalikan dan masa "
                        "garansi dari dokumen ini tidak berlaku lagi.")}
