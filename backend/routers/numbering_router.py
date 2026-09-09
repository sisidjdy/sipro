"""ROUTER PENOMORAN TERKONFIGURASI (Fase 71) — prefix `/numbering`.

Aturan penomoran (pola + token) untuk semua nomor dokumen & kode master. MEMBACA =
`settings:view`; MENGUBAH/RESET = `settings:update` (sekelas aturan bisnis organisasi).
Nomor yang sudah terbit TIDAK berubah — aturan hanya berlaku untuk nomor berikutnya.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

import numbering as nb
from core_utils import serialize_doc
from db import ORG_ID
from numbering_registry import (CONTEXT_TOKENS, GLOBAL_TOKENS, GROUP_LABELS, REGISTRY_BY_KEY,
                                RESET_OPTIONS, SEQ_SCOPE_OPTIONS)
from rbac import audit_log, require_permission

router = APIRouter(prefix="/numbering", tags=["numbering"])


class RuleSave(BaseModel):
    pattern: Optional[str] = None
    prefix: Optional[str] = None
    width: Optional[int] = Field(None, ge=1, le=8)
    reset: Optional[str] = None
    seq_scope: Optional[str] = None
    start: Optional[int] = Field(None, ge=1)


class PreviewIn(RuleSave):
    sample: dict = {}
    project_id: Optional[str] = None


def _org(user: dict) -> str:
    return user.get("org_id", ORG_ID)


def _key(key: str) -> str:
    if key not in REGISTRY_BY_KEY:
        raise HTTPException(status_code=404, detail="Aturan penomoran tidak dikenal.")
    return key


@router.get("")
async def list_rules(project_id: str = None,
                     user: dict = Depends(require_permission("settings", "view"))):
    """`project_id` opsional: contoh & urut berikutnya dihitung dari counter proyek itu."""
    ctx = {"project_id": project_id} if project_id else None
    return {"data": serialize_doc(await nb.list_rules(_org(user), ctx)),
            "groups": [{"key": k, "label": v} for k, v in GROUP_LABELS.items()],
            "reset_options": [{"value": k, "label": v} for k, v in RESET_OPTIONS.items()],
            "seq_scope_options": [{"value": k, "label": v} for k, v in SEQ_SCOPE_OPTIONS.items()],
            "global_tokens": [{"token": t, "desc": d, "example": ex} for t, d, ex in GLOBAL_TOKENS],
            "context_tokens": [{"token": t, "desc": d, "example": ex}
                               for t, (d, ex) in CONTEXT_TOKENS.items()]}


@router.get("/{key:path}/tokens")
async def tokens(key: str, user: dict = Depends(require_permission("settings", "view"))):
    return {"data": nb.token_catalog(_key(key))}


@router.post("/{key:path}/preview")
async def preview(key: str, payload: PreviewIn,
                  user: dict = Depends(require_permission("settings", "view"))):
    """Contoh nomor dari rancangan yang BELUM disimpan (counter tidak naik)."""
    org = _org(user)
    base = REGISTRY_BY_KEY[_key(key)]
    rule = await nb.effective_rule(org, key)
    patch = payload.model_dump(exclude_none=True)
    sample = patch.pop("sample", {})
    project_id = patch.pop("project_id", None)
    rule.update({k: v for k, v in patch.items() if k in nb.EDITABLE})
    errs = nb.validate_pattern(rule["pattern"], base["tokens"])
    if errs:
        raise HTTPException(status_code=400, detail=" ".join(errs))
    if project_id:
        pv, n = await nb.preview_in_context(org, rule, {"project_id": project_id})
        return {"data": {"preview": pv, "next_seq": n, "errors": []}}
    return {"data": {"preview": await nb.preview(org, rule, sample), "errors": []}}


@router.put("/{key:path}")
async def save_rule(key: str, payload: RuleSave,
                    user: dict = Depends(require_permission("settings", "update"))):
    org = _org(user)
    try:
        out = await nb.save_rule(org, _key(key), payload.model_dump(exclude_none=True),
                                 user.get("email"))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit_log(user, "update", "numbering_rules", key,
                    {"pattern": out["pattern"], "reset": out["reset"]})
    out["preview"] = await nb.preview(org, out)
    return {"data": serialize_doc(out), "message": "Aturan penomoran disimpan."}


@router.delete("/{key:path}")
async def reset_rule(key: str, user: dict = Depends(require_permission("settings", "update"))):
    org = _org(user)
    out = await nb.reset_rule(org, _key(key))
    await audit_log(user, "delete", "numbering_rules", key)
    out["preview"] = await nb.preview(org, out)
    return {"data": serialize_doc(out), "message": "Aturan dikembalikan ke bawaan."}
