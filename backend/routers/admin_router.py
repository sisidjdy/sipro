"""Admin routes: users management + RBAC permission matrix (SSOT) + peran dinamis."""
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Optional

from db import db, ORG_ID
from core_utils import new_id, now_iso, serialize_doc, parse_pagination
from security import hash_password
from rbac import (require_permission, get_matrix, DEFAULT_PERMISSIONS, ALL_ROLES, audit_log,
                  effective_matrix, validate_matrix, KNOWN_ACTIONS, FULL_ACCESS_ROLES,
                  ROLE_INHERITS, ROLE_DENY, ROLE_GRANTS, ROLE_SCOPES, all_roles, is_known_role,
                  custom_roles, load_custom_roles, role_scope, role_label, inherits_of,
                  default_role_scope, scope_overrides, SCOPE_OVERRIDES_KEY)
from models import UserCreate, UserUpdate, PermissionUpdate
from rbac_labels import resource_meta, action_meta, GROUP_ORDER

router = APIRouter(prefix="/admin", tags=["admin"])

_CODE_RE = re.compile(r"^[a-z][a-z0-9_]{2,31}$")
SCOPE_META = {
    "all": ("Seluruh data organisasi", "Melihat baris milik siapa pun (seperti Manajer Sales/Finance)."),
    "own": ("Hanya miliknya sendiri", "Hanya baris yang ditugaskan kepadanya (seperti Sales)."),
    "project": ("Hanya proyek yang ditugaskan", "Hanya proyek yang ia jadi anggotanya (seperti Manajer Proyek)."),
}


class RoleCreate(BaseModel):
    code: str = Field(min_length=3, max_length=32)
    label: str = Field(min_length=3, max_length=60)
    description: Optional[str] = Field(default=None, max_length=300)
    inherits: Optional[str] = None
    scope: str = "all"
    copy_from: Optional[str] = None  # salin seluruh izin EFEKTIF peran ini ke baris matriks peran baru


class RoleUpdate(BaseModel):
    label: Optional[str] = Field(default=None, min_length=3, max_length=60)
    description: Optional[str] = Field(default=None, max_length=300)
    inherits: Optional[str] = None
    scope: Optional[str] = None
    is_active: Optional[bool] = None


def _role_meta() -> dict:
    """{code: {label, custom, inherits, scope, full_access}} untuk SEMUA peran (bawaan + kustom)."""
    out = {}
    for r in all_roles():
        c = custom_roles().get(r)
        out[r] = {"label": role_label(r), "custom": bool(c), "inherits": inherits_of(r),
                  "scope": role_scope(r), "full_access": r in FULL_ACCESS_ROLES,
                  "description": (c or {}).get("description"),
                  "scope_default": default_role_scope(r) if r in ALL_ROLES else None,
                  "scope_overridden": bool(r in ALL_ROLES and scope_overrides().get(r))}
    return out


def _validate_role_fields(inherits, scope):
    if inherits is not None and inherits != "" and (inherits not in ALL_ROLES or inherits in FULL_ACCESS_ROLES):
        raise HTTPException(status_code=400, detail=(
            "Peran induk harus salah satu peran bawaan (bukan Direksi/Super Admin, bukan peran kustom)."))
    if scope is not None and scope not in ROLE_SCOPES:
        raise HTTPException(status_code=400, detail="Lingkup data harus all, own, atau project.")


@router.get("/roles")
async def list_roles(user: dict = Depends(require_permission("permissions", "view"))):
    """Semua peran: bawaan (dari kode) + kustom (koleksi `roles`), beserta jumlah pemakainya."""
    await load_custom_roles(force=True)
    org = user.get("org_id", ORG_ID)
    counts = {r["_id"]: r["n"] for r in await db.users.aggregate([
        {"$match": {"org_id": org}}, {"$group": {"_id": "$role", "n": {"$sum": 1}}}]).to_list(200)}
    rows = []
    for code, meta in _role_meta().items():
        c = custom_roles().get(code) or {}
        rows.append({**meta, "code": code, "users": counts.get(code, 0),
                     "created_at": c.get("created_at"), "created_by": c.get("created_by"),
                     "updated_at": c.get("updated_at")})
    return {"data": rows, "total": len(rows),
            "base_options": [r for r in ALL_ROLES if r not in FULL_ACCESS_ROLES],
            "scope_meta": {k: {"label": v[0], "help": v[1]} for k, v in SCOPE_META.items()}}


@router.post("/roles")
async def create_role(payload: RoleCreate,
                      user: dict = Depends(require_permission("permissions", "manage"))):
    code = payload.code.strip().lower()
    if not _CODE_RE.match(code):
        raise HTTPException(status_code=400, detail=(
            "Kode peran: huruf kecil, angka, garis bawah; diawali huruf; 3–32 karakter (mis. `admin_gudang`)."))
    await load_custom_roles(force=True)
    if is_known_role(code) or await db.roles.find_one({"code": code}):
        raise HTTPException(status_code=400, detail=f"Kode peran '{code}' sudah dipakai.")
    _validate_role_fields(payload.inherits, payload.scope)
    src = (payload.copy_from or "").strip() or None
    if src and (not is_known_role(src) or src in FULL_ACCESS_ROLES):
        raise HTTPException(status_code=400, detail=(
            "Peran yang disalin harus peran yang ada dan bukan Direksi/Super Admin."))
    ts = now_iso()
    doc = {"id": new_id(), "org_id": user.get("org_id", ORG_ID), "code": code,
           "label": payload.label.strip(), "description": (payload.description or "").strip() or None,
           "inherits": payload.inherits or None, "scope": payload.scope, "is_active": True,
           "created_at": ts, "updated_at": ts, "created_by": user.get("email"), "copied_from": src}
    await db.roles.insert_one(doc)
    await load_custom_roles(force=True)
    copied = 0
    if src:
        # Salin izin EFEKTIF sumber (matriks + warisan + tambahan kode) sebagai baris matriks
        # eksplisit peran baru, sehingga centangnya identik dan bisa diubah bebas sesudahnya.
        matrix = await get_matrix()
        eff = effective_matrix(matrix)
        for res in DEFAULT_PERMISSIONS:
            perms = sorted((eff.get(res) or {}).get(src, {}).get("perms") or [])
            matrix.setdefault(res, {})[code] = perms
            copied += len(perms)
        await db.permission_settings.update_one(
            {"key": "rbac_matrix"},
            {"$set": {"key": "rbac_matrix", "matrix": matrix, "updated_at": ts, "updated_by": user.get("email")}},
            upsert=True)
    await audit_log(user, "create", "permissions", code,
                    {"role": code, "label": doc["label"], "inherits": doc["inherits"], "scope": doc["scope"],
                     "copied_from": src, "copied_perms": copied})
    return {"data": {**_role_meta()[code], "code": code, "users": 0, "copied_from": src, "copied_perms": copied}}


async def _update_builtin_scope(code: str, payload: RoleUpdate, user: dict) -> dict:
    """Peran bawaan: hanya LINGKUP DATA yang boleh ditimpa (label/kode/izin tetap dari kode & matriks).
    `scope` = null/"" → kembali ke bawaan."""
    if code in FULL_ACCESS_ROLES:
        raise HTTPException(status_code=400, detail="Direksi/Super Admin selalu melihat seluruh data.")
    fields = payload.model_dump(exclude_unset=True)
    if any(k != "scope" for k in fields):
        raise HTTPException(status_code=400, detail=(
            "Peran bawaan hanya bisa diubah lingkup datanya; nama & izin diatur lewat matriks."))
    if "scope" not in fields:
        raise HTTPException(status_code=400, detail="Tidak ada perubahan lingkup data.")
    scope = fields["scope"] or None
    if scope is not None and scope not in ROLE_SCOPES:
        raise HTTPException(status_code=400, detail="Lingkup data harus all, own, atau project.")
    await load_custom_roles(force=True)
    scopes = dict(scope_overrides())
    before = role_scope(code)
    if scope is None or scope == default_role_scope(code):
        scopes.pop(code, None)
    else:
        scopes[code] = scope
    await db.permission_settings.update_one(
        {"key": SCOPE_OVERRIDES_KEY},
        {"$set": {"key": SCOPE_OVERRIDES_KEY, "scopes": scopes, "updated_at": now_iso(),
                  "updated_by": user.get("email")}}, upsert=True)
    await load_custom_roles(force=True)
    await audit_log(user, "update", "permissions", code,
                    {"role": code, "scope_before": before, "scope_after": role_scope(code)})
    meta = _role_meta()[code]
    return {"data": {**meta, "code": code, "is_active": True,
                     "users": await db.users.count_documents({"role": code})},
            "note": ("Lingkup berlaku pada permintaan berikutnya — pengguna dengan peran ini tidak "
                     "perlu masuk ulang.")}


@router.put("/roles/{code}")
async def update_role(code: str, payload: RoleUpdate,
                      user: dict = Depends(require_permission("permissions", "manage"))):
    if code in ALL_ROLES:
        return await _update_builtin_scope(code, payload, user)
    cur = await db.roles.find_one({"code": code}, {"_id": 0})
    if not cur:
        raise HTTPException(status_code=404, detail="Peran tidak ditemukan.")
    _validate_role_fields(payload.inherits, payload.scope)
    upd = {k: v for k, v in payload.model_dump(exclude_unset=True).items()}
    if "label" in upd and upd["label"]:
        upd["label"] = upd["label"].strip()
    if "inherits" in upd:
        upd["inherits"] = upd["inherits"] or None
    if upd.get("is_active") is False and await db.users.count_documents({"role": code, "is_active": True}):
        raise HTTPException(status_code=400, detail=(
            "Peran masih dipakai pengguna aktif — pindahkan mereka ke peran lain dulu."))
    upd["updated_at"] = now_iso()
    await db.roles.update_one({"code": code}, {"$set": upd})
    await load_custom_roles(force=True)
    await audit_log(user, "update", "permissions", code, {"role": code, **{k: v for k, v in upd.items()}})
    fresh = await db.roles.find_one({"code": code}, {"_id": 0})
    meta = _role_meta().get(code) or {"label": fresh.get("label"), "custom": True,
                                      "inherits": fresh.get("inherits"), "scope": fresh.get("scope"),
                                      "full_access": False, "description": fresh.get("description")}
    return {"data": {**meta, "code": code, "is_active": fresh.get("is_active", True),
                     "users": await db.users.count_documents({"role": code})}}


@router.delete("/roles/{code}")
async def delete_role(code: str, user: dict = Depends(require_permission("permissions", "manage"))):
    if code in ALL_ROLES:
        raise HTTPException(status_code=400, detail="Peran bawaan tidak bisa dihapus.")
    if not await db.roles.find_one({"code": code}):
        raise HTTPException(status_code=404, detail="Peran tidak ditemukan.")
    n = await db.users.count_documents({"role": code})
    if n:
        raise HTTPException(status_code=400, detail=(
            f"Peran masih dipakai {n} pengguna — pindahkan mereka ke peran lain dulu."))
    await db.roles.delete_one({"code": code})
    # Baris matriks milik peran ini ikut dibuang supaya tidak menjadi baris mati.
    doc = await db.permission_settings.find_one({"key": "rbac_matrix"}, {"_id": 0})
    if doc:
        matrix = {res: {r: p for r, p in (roles or {}).items() if r != code}
                  for res, roles in (doc.get("matrix") or {}).items()}
        await db.permission_settings.update_one({"key": "rbac_matrix"}, {"$set": {"matrix": matrix}})
    await load_custom_roles(force=True)
    await audit_log(user, "delete", "permissions", code, {"role": code})
    return {"data": {"deleted": code}}


@router.get("/users")
async def list_users(skip: int = 0, limit: int = 50,
                     user: dict = Depends(require_permission("users", "view"))):
    skip, limit = parse_pagination(skip, limit)
    q = {"org_id": user.get("org_id", ORG_ID)}
    total = await db.users.count_documents(q)
    rows = await db.users.find(q, {"_id": 0, "password_hash": 0}).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    return {"data": serialize_doc(rows), "total": total}


@router.post("/users")
async def create_user(payload: UserCreate,
                      user: dict = Depends(require_permission("users", "create"))):
    email = payload.email.lower()
    await load_custom_roles(force=True)
    if not is_known_role(payload.role):
        raise HTTPException(status_code=400, detail="Peran tidak valid")
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=400, detail="Email sudah terdaftar")
    ts = now_iso()
    doc = {
        "id": new_id(), "org_id": user.get("org_id", ORG_ID), "name": payload.name,
        "email": email, "role": payload.role, "phone": payload.phone,
        "password_hash": hash_password(payload.password), "is_active": True,
        "created_at": ts, "updated_at": ts,
    }
    await db.users.insert_one(doc)
    await audit_log(user, "create", "users", doc["id"], {"email": email, "role": payload.role})
    doc.pop("password_hash", None)
    return {"data": serialize_doc(doc)}


@router.put("/users/{user_id}")
async def update_user(user_id: str, payload: UserUpdate,
                      user: dict = Depends(require_permission("users", "update"))):
    target = await db.users.find_one({"id": user_id})
    if not target:
        raise HTTPException(status_code=404, detail="Pengguna tidak ditemukan")
    updates = {}
    if payload.name is not None:
        updates["name"] = payload.name
    if payload.role is not None:
        await load_custom_roles(force=True)
        if not is_known_role(payload.role):
            raise HTTPException(status_code=400, detail="Peran tidak valid")
        updates["role"] = payload.role
    if payload.phone is not None:
        updates["phone"] = payload.phone
    if payload.is_active is not None:
        updates["is_active"] = payload.is_active
    if payload.password:
        updates["password_hash"] = hash_password(payload.password)
    updates["updated_at"] = now_iso()
    await db.users.update_one({"id": user_id}, {"$set": updates})
    await audit_log(user, "update", "users", user_id, {k: v for k, v in updates.items() if k != "password_hash"})
    fresh = await db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0})
    return {"data": serialize_doc(fresh)}


@router.get("/permissions")
async def get_permissions(user: dict = Depends(require_permission("permissions", "view"))):
    """Matriks izin: yang TERTULIS (bisa disunting) + yang BENAR-BENAR BERLAKU.

    Dua-duanya dikirim karena berbeda, dan perbedaan itulah yang dulu membuat layar
    Hak Akses menyesatkan: peran turunan (dm_supervisor, dm_staff, finance_manager)
    tampil kosong padahal API-nya menjawab 200, karena izinnya datang dari warisan peran
    (`ROLE_INHERITS`) atau tambahan di kode (`ROLE_GRANTS`) — bukan dari baris matriks.
    """
    matrix = await get_matrix()
    inherits = {**ROLE_INHERITS, **{c: d.get("inherits") for c, d in custom_roles().items() if d.get("inherits")}}
    return {"data": {
        "matrix": matrix,
        "effective": effective_matrix(matrix),
        "roles": all_roles(),
        "role_meta": _role_meta(),
        "resources": list(DEFAULT_PERMISSIONS.keys()),
        "resource_meta": resource_meta(DEFAULT_PERMISSIONS.keys()),
        "action_meta": action_meta(KNOWN_ACTIONS),
        "group_order": GROUP_ORDER,
        "actions": KNOWN_ACTIONS,
        "defaults": DEFAULT_PERMISSIONS,
        "full_access_roles": sorted(FULL_ACCESS_ROLES),
        "inherits": inherits,
        "denied_actions": {r: sorted(a) for r, a in ROLE_DENY.items()},
        "code_grants": ROLE_GRANTS,
        "notes": {
            "revoke": ("Mencabut izin = simpan daftar aksi KOSONG untuk peran itu. "
                       "Kunci yang ada tetapi kosong berarti 'tidak boleh' dan "
                       "MENGALAHKAN warisan peran serta tambahan dari kode."),
            "full_access": ("Direksi & Super Admin selalu berakses penuh; keduanya tidak "
                            "bisa dibatasi dari layar ini agar tidak ada yang terkunci."),
            "enforced_by": "backend require_permission(resource, action)",
        },
    }}


@router.put("/permissions")
async def update_permissions(payload: PermissionUpdate,
                             user: dict = Depends(require_permission("permissions", "manage"))):
    """Simpan matriks izin. Kiriman yang tidak akan pernah berlaku DITOLAK, bukan disimpan.

    Menyimpan resource/peran/aksi asing hanya melahirkan baris mati di database dan membuat
    layar Hak Akses menjanjikan sesuatu yang tidak ditegakkan `require_permission`.
    """
    errors = validate_matrix(payload.matrix)
    if errors:
        raise HTTPException(status_code=400, detail="Matriks izin ditolak: " + " ".join(errors))
    sebelum = await get_matrix()
    await db.permission_settings.update_one(
        {"key": "rbac_matrix"},
        {"$set": {"key": "rbac_matrix", "matrix": payload.matrix, "updated_at": now_iso(),
                  "updated_by": user.get("email")}},
        upsert=True,
    )
    sesudah = await get_matrix()
    # Jejak audit menyebut APA yang berubah, bukan hanya "matriks diubah" — perubahan hak
    # akses adalah keputusan yang harus bisa ditinjau setelah kejadian.
    perubahan = []
    for res in sorted(set(sebelum) | set(sesudah)):
        for role in all_roles():
            if role in FULL_ACCESS_ROLES:
                continue
            a = sorted((sebelum.get(res) or {}).get(role) or [])
            b = sorted((sesudah.get(res) or {}).get(role) or [])
            if a != b:
                perubahan.append({"resource": res, "role": role, "dari": a, "menjadi": b})
    await audit_log(user, "update", "permissions", "rbac_matrix",
                    {"jumlah_perubahan": len(perubahan), "perubahan": perubahan[:50]})
    matrix = await get_matrix()
    return {"data": {"matrix": matrix, "effective": effective_matrix(matrix),
                     "changes": perubahan}}


@router.get("/audit-logs")
async def list_audit_logs(resource: str = None, action: str = None, actor: str = None,
                          skip: int = 0, limit: int = 50,
                          user: dict = Depends(require_permission("audit_logs", "view"))):
    """Jejak audit yang sebelumnya DITULIS tapi TIDAK BISA DILIHAT (tak ada endpoint)."""
    skip, limit = parse_pagination(skip, limit)
    q = {"org_id": user.get("org_id", ORG_ID)}
    if resource:
        q["resource"] = resource
    if action:
        q["action"] = action
    if actor:
        q["actor"] = actor
    total = await db.audit_logs.count_documents(q)
    rows = await db.audit_logs.find(q, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    resources = await db.audit_logs.distinct("resource", {"org_id": user.get("org_id", ORG_ID)})
    actions = await db.audit_logs.distinct("action", {"org_id": user.get("org_id", ORG_ID)})
    return {"data": serialize_doc(rows), "total": total,
            "filters": {"resources": sorted(r for r in resources if r),
                        "actions": sorted(a for a in actions if a)}}


@router.get("/migrations")
async def list_migrations(limit: int = 20,
                          user: dict = Depends(require_permission("audit_logs", "view"))):
    """Riwayat migrasi/backfill data (Fase 39) + KEADAAN SEKARANG — bukti US-39-5.

    Migrasi menulis ringkasannya ke `migration_runs` sejak Fase 39, tetapi tidak ada cara
    melihatnya: admin harus percaya begitu saja bahwa unit lama sudah mendapat cluster & blok.
    Karena migrasi idempoten, jalan KEDUA dan seterusnya wajar berangka 0 — angka 0 itu bisa
    disalahpahami sebagai "tidak pernah dibereskan". Maka endpoint ini juga mengembalikan
    `state`: hitungan nyata saat ini (berapa unit sudah punya cluster/blok/tipe, dan berapa
    yang belum) sehingga klaimnya bisa DIPERIKSA kapan pun, bukan hanya saat migrasi jalan.
    """
    _skip, limit = parse_pagination(0, limit)
    org = user.get("org_id", ORG_ID)
    q = {"org_id": org}
    rows = await db.migration_runs.find(q, {"_id": 0}).sort("at", -1).limit(limit).to_list(limit)
    units = await db.units.count_documents({"org_id": org})
    state = {
        "units_total": units,
        "units_with_cluster": await db.units.count_documents(
            {"org_id": org, "cluster_id": {"$nin": [None, ""]}}),
        "units_with_block": await db.units.count_documents(
            {"org_id": org, "block_id": {"$nin": [None, ""]}}),
        "units_with_type": await db.units.count_documents(
            {"org_id": org, "unit_type_code": {"$nin": [None, ""]}}),
        "clusters": await db.clusters.count_documents(q),
        "blocks": await db.blocks.count_documents(q),
        "unit_types": await db.unit_types.count_documents(q),
    }
    state["units_without_cluster"] = units - state["units_with_cluster"]
    state["units_without_block"] = units - state["units_with_block"]
    return {"data": serialize_doc(rows), "total": await db.migration_runs.count_documents(q),
            "state": state}
