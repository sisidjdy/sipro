"""Template tahapan progres proyek (Pusat Konfigurasi › Tahapan Pembangunan) + terapkan ke proyek."""
from fastapi import APIRouter, Depends, HTTPException

import phase_templates as pt
from core_utils import new_id, now_iso, serialize_doc
from db import ORG_ID, db
from models import PhaseTemplateApply, PhaseTemplateIn
from rbac import has_role, assert_project_access, audit_log, require_permission

router = APIRouter(prefix="/construction", tags=["construction-phase-templates"])
SUPERVISOR_ROLES = ("owner", "super_admin", "project_manager")


def _org(user: dict) -> str:
    return user.get("org_id", ORG_ID)


def _guard(user: dict):
    if not has_role(user, *SUPERVISOR_ROLES):
        raise HTTPException(status_code=403,
                            detail="Hanya Manajer Proyek/direksi yang boleh mengatur tahapan.")


@router.get("/phase-templates")
async def list_phase_templates(user: dict = Depends(require_permission("construction", "view"))):
    await pt.ensure_default(_org(user))
    rows = await pt.list_templates(_org(user))
    return {"data": serialize_doc(rows), "total": len(rows)}


@router.post("/phase-templates")
async def create_phase_template(payload: PhaseTemplateIn,
                                user: dict = Depends(require_permission("construction", "update"))):
    _guard(user)
    org, ts = _org(user), now_iso()
    code = payload.code.strip().upper()
    if await db[pt.COLL].find_one({"org_id": org, "code": code}):
        raise HTTPException(status_code=409, detail=f"Kode template '{code}' sudah ada.")
    rows = pt.normalize_rows([r.model_dump() for r in payload.phases])
    doc = {"id": new_id(), "org_id": org, "code": code, "name": payload.name.strip(),
           "description": payload.description, "phases": rows, "is_default": False,
           "version": 1, "created_by": user.get("email"), "created_at": ts, "updated_at": ts}
    await db[pt.COLL].insert_one(dict(doc))
    await audit_log(user, "create", pt.COLL, doc["id"], {"code": code})
    return {"data": serialize_doc(doc), "warnings": pt.validate_rows(rows)}


@router.put("/phase-templates/{template_id}")
async def update_phase_template(template_id: str, payload: PhaseTemplateIn,
                                user: dict = Depends(require_permission("construction", "update"))):
    _guard(user)
    org = _org(user)
    tpl = await db[pt.COLL].find_one({"id": template_id, "org_id": org}, {"_id": 0})
    if not tpl:
        raise HTTPException(status_code=404, detail="Template tahapan tidak ditemukan")
    rows = pt.normalize_rows([r.model_dump() for r in payload.phases])
    upd = {"name": payload.name.strip(), "description": payload.description, "phases": rows,
           "version": int(tpl.get("version") or 1) + 1, "updated_at": now_iso(),
           "updated_by": user.get("email")}
    await db[pt.COLL].update_one({"id": template_id, "org_id": org}, {"$set": upd})
    await audit_log(user, "update", pt.COLL, template_id, {"phases": len(rows)})
    fresh = await db[pt.COLL].find_one({"id": template_id}, {"_id": 0})
    return {"data": serialize_doc(fresh), "warnings": pt.validate_rows(rows),
            "note": "Fase proyek yang sudah diterapkan TIDAK berubah; template berlaku untuk "
                    "penerapan berikutnya."}


@router.delete("/phase-templates/{template_id}")
async def delete_phase_template(template_id: str,
                                user: dict = Depends(require_permission("construction", "update"))):
    _guard(user)
    org = _org(user)
    tpl = await db[pt.COLL].find_one({"id": template_id, "org_id": org}, {"_id": 0})
    if not tpl:
        raise HTTPException(status_code=404, detail="Template tahapan tidak ditemukan")
    if tpl.get("is_default") and await db[pt.COLL].count_documents({"org_id": org}) == 1:
        raise HTTPException(status_code=400, detail="Template terakhir tidak bisa dihapus.")
    await db[pt.COLL].delete_one({"id": template_id, "org_id": org})
    await audit_log(user, "delete", pt.COLL, template_id, {"code": tpl.get("code")})
    return {"data": {"id": template_id, "deleted": True}}


@router.post("/project/{project_id}/phases/apply")
async def apply_phase_template(project_id: str, payload: PhaseTemplateApply,
                               user: dict = Depends(require_permission("construction", "create"))):
    """Buat fase proyek dari template. Nama yang sudah ada dilewati (idempoten)."""
    await assert_project_access(project_id, user)
    org = _org(user)
    tpl = await db[pt.COLL].find_one({"id": payload.template_id, "org_id": org}, {"_id": 0})
    if not tpl:
        raise HTTPException(status_code=404, detail="Template tahapan tidak ditemukan")
    res = await pt.apply_to_project(org, project_id, tpl, user.get("email"))
    await audit_log(user, "apply_phase_template", "construction_phases", project_id,
                    {"template": tpl.get("code"), "created": len(res["created"]),
                     "skipped": res["skipped"]})
    return {"data": serialize_doc(res["created"]), "skipped": res["skipped"],
            "overall": res["overall"],
            "note": (f"{len(res['created'])} fase dibuat"
                     + (f", {len(res['skipped'])} dilewati karena namanya sudah ada."
                        if res["skipped"] else "."))}
