"""legal_router — `/api/legal/*`: halaman legal publik (privasi, S&K, penghapusan data) + pengaturan admin.

Rute `/legal/public/*` TANPA login (dibaca Meta App Review & calon pembeli). Rute lainnya dijaga RBAC
resource `legal` (Admin Legal & Kepatuhan / owner / super_admin).
"""
import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

import legal_pages as lp
from db import ORG_ID
from rbac import audit_log, require_permission

router = APIRouter(prefix="/legal", tags=["legal"])

_HITS: dict = {}
RATE_MAX, RATE_WINDOW = 5, 3600


def _rate_ok(key: str) -> bool:
    now = time.time()
    hits = [t for t in _HITS.get(key, []) if now - t < RATE_WINDOW]
    if len(hits) >= RATE_MAX:
        _HITS[key] = hits
        return False
    hits.append(now)
    _HITS[key] = hits
    return True


class DeletionRequestIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    contact: str = Field(min_length=5, max_length=160)
    reason: Optional[str] = Field(default="", max_length=1000)
    lang: str = "id"
    website: Optional[str] = ""  # honeypot


class SettingsIn(BaseModel):
    identity: dict = {}
    texts: dict = {}


class DeletionUpdateIn(BaseModel):
    status: str
    note: Optional[str] = ""


def _org(user: dict) -> str:
    return user.get("org_id", ORG_ID)


def legal_urls(public_base: str) -> dict:
    base = (public_base or "").strip().rstrip("/")
    return {"privacy": f"{base}/privacy", "terms": f"{base}/terms", "deletion": f"{base}/data-deletion",
            "privacy_en": f"{base}/privacy?lang=en", "terms_en": f"{base}/terms?lang=en",
            "deletion_en": f"{base}/data-deletion?lang=en"}


# ---------------------------------------------------------------- publik (tanpa login)
@router.get("/public")
async def public_pages(lang: str = "id", public_base: str = ""):
    return {"data": await lp.render(ORG_ID, lang, public_base)}


@router.post("/public/deletion-requests")
async def public_deletion_request(payload: DeletionRequestIn, request: Request):
    if payload.website:
        raise HTTPException(400, "Pengiriman ditolak.")
    ip = request.client.host if request.client else "?"
    if not _rate_ok(ip):
        raise HTTPException(429, "Terlalu banyak permintaan dari perangkat ini. Coba lagi nanti atau kirim email.")
    doc = await lp.create_deletion_request(ORG_ID, payload.model_dump())
    return {"data": {"ticket": doc["ticket"], "created_at": doc["created_at"], "status": doc["status"]}}


# ---------------------------------------------------------------- admin (RBAC `legal`)
@router.get("/settings")
async def get_settings(user: dict = Depends(require_permission("legal", "view"))):
    return {"data": await lp.get_settings(_org(user))}


@router.put("/settings")
async def put_settings(p: SettingsIn, user: dict = Depends(require_permission("legal", "manage"))):
    out = await lp.save_settings(_org(user), p.identity or {}, p.texts or {}, user.get("email"))
    await audit_log(user, "update", "legal", "settings", {"identity": out["identity"],
                                                          "custom_pages": {k: list(v) for k, v in out["texts"].items()}})
    return {"data": out}


@router.get("/preview")
async def preview(lang: str = "id", public_base: str = "", user: dict = Depends(require_permission("legal", "view"))):
    return {"data": await lp.render(_org(user), lang, public_base)}


@router.get("/urls")
async def urls(public_base: str = "", user: dict = Depends(require_permission("legal", "view"))):
    return {"data": legal_urls(public_base)}


@router.get("/deletion-requests")
async def list_requests(user: dict = Depends(require_permission("legal", "view"))):
    return {"data": await lp.list_deletion_requests(_org(user))}


@router.patch("/deletion-requests/{rid}")
async def update_request(rid: str, p: DeletionUpdateIn, user: dict = Depends(require_permission("legal", "update"))):
    try:
        doc = await lp.update_deletion_request(_org(user), rid, p.status, p.note or "", user.get("email"))
    except ValueError as e:
        raise HTTPException(400, str(e))
    except LookupError as e:
        raise HTTPException(404, str(e))
    await audit_log(user, "update", "legal", rid, {"status": p.status, "ticket": doc.get("ticket")})
    return {"data": doc}
