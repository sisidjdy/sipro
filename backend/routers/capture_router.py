"""Antrean lead gagal masuk (Fase 30c) — lihat, perbaiki, ulangi, atau buang.

Endpoint staf (RBAC `leads`) untuk mengelola dead-letter queue webhook iklan. Webhook
publik sendiri tetap di `webhooks_router` (tanpa auth) dan sekarang TIDAK PERNAH membuang
payload cacat: semuanya berlabuh di sini.
"""
from fastapi import APIRouter, Depends, HTTPException

import capture_failures as cf
from core_utils import parse_pagination, serialize_doc
from db import ORG_ID
from models_p30 import CaptureDiscard, CaptureRetry
from rbac import require_permission

router = APIRouter(prefix="/capture", tags=["omnichannel"])


@router.get("/failures")
async def list_failures(status: str = None, provider: str = None, skip: int = 0,
                        limit: int = 20,
                        user: dict = Depends(require_permission("leads", "view_all"))):
    """Daftar kegagalan (default semua status, terbaru dulu) + total untuk paginasi."""
    skip, limit = parse_pagination(skip, limit)
    org = user.get("org_id", ORG_ID)
    rows, total = await cf.listing(org, status=status, provider=provider, skip=skip, limit=limit)
    return {"data": serialize_doc(rows), "total": total,
            "summary": await cf.summary(org), "editable_fields": list(cf.EDITABLE)}


@router.get("/failures/summary")
async def failures_summary(user: dict = Depends(require_permission("leads", "view_all"))):
    """Ringkasan untuk lencana navigasi (berapa lead tertahan & perlu koreksi)."""
    return {"data": await cf.summary(user.get("org_id", ORG_ID))}


@router.post("/failures/{fid}/retry")
async def retry_failure(fid: str, payload: CaptureRetry = None,
                        user: dict = Depends(require_permission("leads", "create"))):
    """Ulangi pemasukan lead — boleh sekaligus mengoreksi nomor/nama/sumber."""
    fixes = (payload.fixes if payload else None) or {}
    try:
        res = await cf.retry(fid, user.get("org_id", ORG_ID), actor=user.get("email"),
                             fixes=fixes)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"data": serialize_doc(res["failure"]), "lead_id": res["lead_id"],
            "duplicate": res["duplicate"]}


@router.post("/failures/{fid}/discard")
async def discard_failure(fid: str, payload: CaptureDiscard,
                          user: dict = Depends(require_permission("leads", "update"))):
    """Buang antrean dengan alasan (spam/uji coba) — tetap tercatat untuk audit."""
    try:
        row = await cf.discard(fid, user.get("org_id", ORG_ID), actor=user.get("email"),
                               reason=payload.reason)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"data": serialize_doc(row)}
