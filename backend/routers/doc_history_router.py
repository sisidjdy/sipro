"""Riwayat dokumen terbit per lead/customer (Fase 91)."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

import doc_history
import wa_docs
from db import ORG_ID
from rbac import audit_log, require_permission


class SendWaIn(BaseModel):
    entity_type: str
    entity_id: str
    pdf_url: str
    label: str
    number: Optional[str] = None
    caption: Optional[str] = None

router = APIRouter(prefix="/doc-history", tags=["doc-history"])


@router.post("/send-wa")
async def send_document_wa(p: SendWaIn, request: Request,
                           user: dict = Depends(require_permission("documents", "view"))):
    """Fase 98D — kirim PDF dokumen terbit ke WhatsApp pembeli (render lewat jalur tombol PDF yang sama)."""
    if p.entity_type not in ("lead", "customer"):
        raise HTTPException(status_code=400, detail="entity_type harus lead atau customer.")
    res = await wa_docs.send_document(user.get("org_id", ORG_ID), app=request.app, headers=dict(request.headers),
                                      entity_type=p.entity_type, entity_id=p.entity_id, pdf_url=p.pdf_url,
                                      label=p.label, number=p.number, caption=p.caption, actor=user.get("email"))
    await audit_log(user, "send_wa", "doc_share", res["share"]["id"], {"pdf_url": p.pdf_url, "status": res["message"]["status"]})
    if res["message"]["status"] == "failed":
        raise HTTPException(status_code=424, detail=f"Kirim WA gagal ({res['message'].get('error_code')}): "
                                                    f"{res['message'].get('error_detail')}")
    return {"data": res}


@router.get("/{entity_type}/{entity_id}")
async def issued_documents(entity_type: str, entity_id: str,
                           user: dict = Depends(require_permission("documents", "view"))):
    if entity_type not in ("lead", "customer"):
        raise HTTPException(status_code=400, detail="entity_type harus lead atau customer.")
    return {"data": await doc_history.history(user.get("org_id", ORG_ID), entity_type, entity_id)}
