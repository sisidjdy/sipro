"""Master dokumen syarat + dokumen yang diserahkan (Fase 39).

Keputusan owner (D3): syarat dokumen adalah MASTER yang bisa ditambah admin, lalu diunggah
per tahap. Verifikasi selalu mencatat AKTOR + waktu, dan berkas wajib benar-benar ada di
penyimpanan (tidak bisa mengaku punya bukti).
"""
from fastapi import APIRouter, Depends, HTTPException

import doc_registry as docreg
from core_utils import serialize_doc
from db import ORG_ID
from models_v2 import (DocRejectPayload, DocRequirementCreate, DocRequirementUpdate,
                       DocSubmissionCreate, DocVerifyPayload)
from rbac import audit_log, require_permission

router = APIRouter(prefix="/doc", tags=["documents"])


def _org(user: dict) -> str:
    return user.get("org_id", ORG_ID)


# ------------------------------------------------------------------ master syarat
@router.get("/requirements")
async def list_requirements(context: str = None, group: str = None, active: bool = None,
                            user: dict = Depends(require_permission("doc_requirements", "view"))):
    rows = await docreg.list_requirements(_org(user), context, group, active)
    return {"data": serialize_doc(rows), "total": len(rows)}


@router.post("/requirements")
async def create_requirement(payload: DocRequirementCreate,
                             user: dict = Depends(
                                 require_permission("doc_requirements", "create"))):
    try:
        row = await docreg.create_requirement(payload, user.get("email"), _org(user))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit_log(user, "create", "doc_requirements", row["id"], {"code": row["code"]})
    return {"data": serialize_doc(row)}


@router.put("/requirements/{req_id}")
async def update_requirement(req_id: str, payload: DocRequirementUpdate,
                             user: dict = Depends(
                                 require_permission("doc_requirements", "update"))):
    try:
        row = await docreg.update_requirement(req_id, payload, user.get("email"), _org(user))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit_log(user, "update", "doc_requirements", req_id, {})
    return {"data": serialize_doc(row)}


# ------------------------------------------------------------------ penyerahan
@router.get("/submissions")
async def list_submissions(entity_type: str, entity_id: str,
                           user: dict = Depends(require_permission("documents", "view"))):
    rows = await docreg.submissions_for(entity_type, entity_id, _org(user))
    return {"data": serialize_doc(rows), "total": len(rows)}


@router.get("/matrix")
async def doc_matrix(entity_type: str, entity_id: str, contexts: str = "",
                     user: dict = Depends(require_permission("documents", "view"))):
    """Matriks syarat × status untuk satu entitas (dipakai checklist & gerbang bukti).

    `contexts` boleh dikosongkan: backend menurunkannya sendiri dari data entitas
    (tahap lead, pengajuan KPR pelanggan, onboarding mitra) — lihat
    `doc_registry.contexts_for`. Dengan begitu frontend tidak menyimpan salinan aturan.
    """
    ctx = [c.strip() for c in (contexts or "").split(",") if c.strip()]
    if not ctx:
        ctx = await docreg.contexts_for(entity_type, entity_id, _org(user))
    res = await docreg.matrix(entity_type, entity_id, ctx, _org(user))
    return {"data": serialize_doc(res)}


@router.post("/submissions")
async def create_submission(payload: DocSubmissionCreate,
                            user: dict = Depends(require_permission("documents", "create"))):
    try:
        row = await docreg.create_submission(payload, user.get("email"), _org(user))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"data": serialize_doc(row)}


@router.post("/submissions/{sub_id}/verify")
async def verify_submission(sub_id: str, payload: DocVerifyPayload = None,
                            user: dict = Depends(require_permission("documents", "verify"))):
    try:
        row = await docreg.verify_submission(sub_id, user.get("email"),
                                             (payload.note if payload else None), _org(user))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    await audit_log(user, "update", "documents", sub_id, {"verified": True})
    return {"data": serialize_doc(row)}


@router.post("/submissions/{sub_id}/reject")
async def reject_submission(sub_id: str, payload: DocRejectPayload,
                            user: dict = Depends(require_permission("documents", "verify"))):
    try:
        row = await docreg.reject_submission(sub_id, user.get("email"), payload.reason,
                                            _org(user))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    await audit_log(user, "update", "documents", sub_id, {"rejected": payload.reason})
    return {"data": serialize_doc(row)}
