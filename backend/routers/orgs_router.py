"""EPIC M4 — Multi-tenant UI: organization management, onboarding & org-switch.

- List/detail/create/update organizations (tenants).
- Onboarding: create a new tenant + its initial owner user in one call.
- Org-switch: super_admin issues a fresh access token carrying the `active_org_id`
  claim so the whole app scopes to the target tenant (get_current_user injects the
  effective org_id). Switching back = switch to the super_admin's home org id.

Cross-tenant write/switch is super_admin-only; owner gets a read-only view of its
own tenant. All money/data stays isolated by org_id (existing tenant scoping).
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel

import reference as ref
from db import db, ORG_ID, COOKIE_SECURE, COOKIE_SAMESITE
from core_utils import new_id, now_iso, serialize_doc
from rbac import require_permission, require_super_admin
from security import hash_password, create_access_token

router = APIRouter(prefix="/admin/orgs", tags=["organizations"])


class OrgCreate(BaseModel):
    name: str
    owner_name: str
    owner_email: str
    owner_password: str


class OrgUpdate(BaseModel):
    name: Optional[str] = None
    status: ref.OrgStatus = None


async def _org_stats(org_id: str) -> dict:
    return {
        "users": await db.users.count_documents({"org_id": org_id}),
        "leads": await db.leads.count_documents({"org_id": org_id}),
        "deals": await db.deals.count_documents({"org_id": org_id}),
        "projects": await db.projects.count_documents({"org_id": org_id}),
    }


def _home(user: dict) -> str:
    return user.get("home_org_id", user.get("org_id", ORG_ID))


@router.get("")
async def list_orgs(user: dict = Depends(require_permission("organizations", "view"))):
    is_super = user.get("role") == "super_admin"
    q = {} if is_super else {"id": _home(user)}
    orgs = await db.orgs.find(q, {"_id": 0}).sort("created_at", 1).to_list(500)
    for o in orgs:
        o["stats"] = await _org_stats(o["id"])
        o.setdefault("status", "active")
    return {
        "data": serialize_doc(orgs),
        "active_org_id": user.get("org_id"),
        "home_org_id": _home(user),
        "is_super_admin": is_super,
    }


@router.post("")
async def create_org(payload: OrgCreate,
                     user: dict = Depends(require_super_admin())):
    email = payload.owner_email.strip().lower()
    if not email or "@" not in email:
        raise HTTPException(400, "Email owner tidak valid.")
    if await db.users.find_one({"email": email}):
        raise HTTPException(400, "Email owner sudah terdaftar.")
    if not payload.owner_password or len(payload.owner_password) < 6:
        raise HTTPException(400, "Kata sandi owner minimal 6 karakter.")
    ts = now_iso()
    oid = "org-" + new_id()[:8]
    org = {"id": oid, "name": payload.name.strip(), "status": "active",
           "created_at": ts, "updated_at": ts}
    await db.orgs.insert_one(org)
    owner = {
        "id": new_id(), "org_id": oid, "name": payload.owner_name.strip(), "email": email,
        "role": "owner", "password_hash": hash_password(payload.owner_password),
        "phone": None, "is_active": True, "created_at": ts, "updated_at": ts,
    }
    await db.users.insert_one(owner)
    org.pop("_id", None)
    return {"data": {**serialize_doc(org), "owner_email": email, "stats": await _org_stats(oid)}}


@router.get("/{org_id}")
async def get_org(org_id: str,
                  user: dict = Depends(require_permission("organizations", "view"))):
    if user.get("role") != "super_admin" and org_id != _home(user):
        raise HTTPException(403, "Akses ditolak: bukan organisasi Anda.")
    org = await db.orgs.find_one({"id": org_id}, {"_id": 0})
    if not org:
        raise HTTPException(404, "Organisasi tidak ditemukan.")
    org["stats"] = await _org_stats(org_id)
    org.setdefault("status", "active")
    users = await db.users.find(
        {"org_id": org_id}, {"_id": 0, "password_hash": 0}).sort("created_at", 1).to_list(200)
    return {"data": serialize_doc(org), "users": serialize_doc(users)}


@router.put("/{org_id}")
async def update_org(org_id: str, payload: OrgUpdate,
                     user: dict = Depends(require_super_admin())):
    upd = {"updated_at": now_iso()}
    if payload.name is not None:
        upd["name"] = payload.name.strip()
    if payload.status in ("active", "suspended"):
        upd["status"] = payload.status
    r = await db.orgs.update_one({"id": org_id}, {"$set": upd})
    if not r.matched_count:
        raise HTTPException(404, "Organisasi tidak ditemukan.")
    org = await db.orgs.find_one({"id": org_id}, {"_id": 0})
    org["stats"] = await _org_stats(org_id)
    return {"data": serialize_doc(org)}


@router.post("/{org_id}/switch")
async def switch_org(org_id: str, response: Response,
                     user: dict = Depends(require_super_admin())):
    """Super_admin acts-as another tenant. Switching to the home org id resets."""
    org = await db.orgs.find_one({"id": org_id}, {"_id": 0})
    if not org:
        raise HTTPException(404, "Organisasi tidak ditemukan.")
    home = _home(user)
    active_claim = None if org_id == home else org_id
    access = create_access_token(user["id"], user["email"], user["role"], active_org_id=active_claim)
    response.set_cookie("access_token", access, httponly=True, secure=COOKIE_SECURE,
                        samesite=COOKIE_SAMESITE, max_age=86400, path="/")
    return {
        "data": {"active_org_id": org_id, "org": serialize_doc(org), "is_home": org_id == home},
        "access_token": access, "token_type": "bearer",
    }
