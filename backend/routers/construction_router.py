"""Construction: weighted progress + Kurva-S + QC + site logs (base64 photos). Slice B."""
from fastapi import APIRouter, Depends, HTTPException

from db import db, ORG_ID
from core_utils import new_id, now_iso, serialize_doc, due_in
from rbac import require_permission, assert_project_access
from engine import (emit, add_activity, auto_create_task, recompute_project_progress,
                    build_s_curve)
from models_master import PhaseUpdate
from denorm import cascade_master_change
from rbac import audit_log
from models import PhaseCreate, ProgressUpdate, QCCreate

router = APIRouter(prefix="/construction", tags=["construction"])
MAX_PHOTO = 2_200_000  # ~1.6MB base64


def _check_photo(photo):
    if photo and len(photo) > MAX_PHOTO:
        raise HTTPException(status_code=400, detail="Foto terlalu besar (maks ~1.5MB). Kompres dulu.")


async def _project_pm(project: dict, org: str):
    members = project.get("members") or []
    if members:
        pm = await db.users.find_one(
            {"org_id": org, "email": {"$in": members}, "role": "project_manager"}, {"_id": 0, "email": 1})
        return pm["email"] if pm else members[0]
    return None


@router.get("/project/{project_id}/phases")
async def list_phases(project_id: str, user: dict = Depends(require_permission("construction", "view"))):
    proj = await assert_project_access(project_id, user)
    org = user.get("org_id", ORG_ID)
    phases = await db.construction_phases.find({"org_id": org, "project_id": project_id}, {"_id": 0}).sort("order", 1).to_list(300)
    return {"data": serialize_doc(phases), "overall": proj.get("construction_progress", 0),
            "curve": build_s_curve(phases)}


@router.get("/project/{project_id}/curve")
async def kurva_s(project_id: str, user: dict = Depends(require_permission("construction", "view"))):
    await assert_project_access(project_id, user)
    org = user.get("org_id", ORG_ID)
    phases = await db.construction_phases.find({"org_id": org, "project_id": project_id}, {"_id": 0}).to_list(300)
    return {"data": build_s_curve(phases)}


@router.get("/project/{project_id}/logs")
async def list_logs(project_id: str, user: dict = Depends(require_permission("construction", "view"))):
    await assert_project_access(project_id, user)
    org = user.get("org_id", ORG_ID)
    logs = await db.construction_logs.find({"org_id": org, "project_id": project_id}, {"_id": 0}).sort("created_at", -1).limit(100).to_list(100)
    return {"data": serialize_doc(logs), "total": len(logs)}


@router.post("/phases")
async def create_phase(payload: PhaseCreate, user: dict = Depends(require_permission("construction", "create"))):
    await assert_project_access(payload.project_id, user)
    org = user.get("org_id", ORG_ID)
    ts = now_iso()
    phase = {
        "id": new_id(), "org_id": org, "project_id": payload.project_id, "name": payload.name,
        "weight": payload.weight, "planned_pct": payload.planned_pct, "progress": 0,
        "work_category": (payload.work_category or "").strip().lower() or None,
        "status": "not_started", "order": payload.order, "created_at": ts, "updated_at": ts,
    }
    await db.construction_phases.insert_one(phase)
    await recompute_project_progress(payload.project_id, org)
    phase.pop("_id", None)
    return {"data": serialize_doc(phase)}


@router.post("/phases/{phase_id}/progress")
async def update_progress(phase_id: str, payload: ProgressUpdate,
                          user: dict = Depends(require_permission("construction", "update"))):
    _check_photo(payload.photo)
    phase = await db.construction_phases.find_one({"id": phase_id}, {"_id": 0})
    if not phase:
        raise HTTPException(status_code=404, detail="Fase tidak ditemukan")
    proj = await assert_project_access(phase["project_id"], user)
    org = user.get("org_id", ORG_ID)
    if phase.get("work_category"):
        raise HTTPException(status_code=409, detail=(
            f"Progres fase '{phase['name']}' dihitung otomatis dari langkah jadwal unit berkategori "
            f"'{phase['work_category']}' — verifikasi item pekerjaan unit, bukan mengetik angka. "
            "Kosongkan kategori pekerjaan fase bila ingin mengisi manual."))
    prog = max(0, min(100, int(payload.progress)))
    ts = now_iso()
    status = "not_started" if prog == 0 else ("done" if prog >= 100 else "in_progress")
    if phase.get("status") == "qc_hold" and prog < 100:
        status = "qc_hold"
    await db.construction_phases.update_one({"id": phase_id}, {"$set": {
        "progress": prog, "status": status, "updated_at": ts}})
    await db.construction_logs.insert_one({
        "id": new_id(), "org_id": org, "project_id": phase["project_id"], "phase_id": phase_id,
        "unit_id": None, "type": "progress", "progress": prog, "note": payload.note,
        "photo": payload.photo, "result": None, "actor": user.get("email"), "created_at": ts})
    overall = await recompute_project_progress(phase["project_id"], org)
    # Kurva-S deviation -> corrective task (idempotent per project+day)
    phases = await db.construction_phases.find({"org_id": org, "project_id": phase["project_id"]}, {"_id": 0}).to_list(300)
    curve = build_s_curve(phases)
    if curve["behind"]:
        await auto_create_task(
            source_event=f"deviation:{phase['project_id']}:{ts[:10]}",
            title=f"Deviasi Kurva-S {curve['deviation']}% — proyek {proj.get('code')}",
            type="review", related_entity_type="project", related_entity_id=phase["project_id"],
            assigned_to=await _project_pm(proj, org), due_date=due_in(days=1), priority="high", org_id=org)
    await add_activity(entity_type="project", entity_id=phase["project_id"], type="system",
                       body=f"Progres '{phase['name']}' → {prog}%. Overall proyek {overall}%.",
                       actor=user.get("email"), org_id=org)
    fresh = await db.construction_phases.find_one({"id": phase_id}, {"_id": 0})
    return {"data": serialize_doc(fresh), "overall": overall, "curve": curve}


@router.post("/qc")
async def create_qc(payload: QCCreate, user: dict = Depends(require_permission("construction", "create"))):
    _check_photo(payload.photo)
    proj = await assert_project_access(payload.project_id, user)
    org = user.get("org_id", ORG_ID)
    ts = now_iso()
    log = {
        "id": new_id(), "org_id": org, "project_id": payload.project_id, "phase_id": payload.phase_id,
        "unit_id": payload.unit_id, "type": "qc", "progress": None, "note": payload.notes,
        "photo": payload.photo, "result": payload.result, "actor": user.get("email"), "created_at": ts}
    await db.construction_logs.insert_one(log)
    if payload.result == "fail":
        if payload.phase_id:
            await db.construction_phases.update_one({"id": payload.phase_id}, {"$set": {"status": "qc_hold", "updated_at": ts}})
        if payload.unit_id:
            await db.units.update_one({"id": payload.unit_id}, {"$set": {"construction_status": "qc_hold", "updated_at": ts}})
        await emit("qc.failed", "project", payload.project_id, {"phase_id": payload.phase_id}, org_id=org)
        await auto_create_task(
            source_event=f"qc.fail:{log['id']}",
            title=f"Perbaikan QC gagal — proyek {proj.get('code')}",
            type="review", related_entity_type="project", related_entity_id=payload.project_id,
            assigned_to=await _project_pm(proj, org), due_date=due_in(days=1), priority="urgent", org_id=org)
    await add_activity(entity_type="project", entity_id=payload.project_id, type="system",
                       body=f"QC {payload.result.upper()}" + (f": {payload.notes}" if payload.notes else ""),
                       actor=user.get("email"), org_id=org)
    log.pop("_id", None)
    return {"data": serialize_doc(log)}


@router.put("/phases/{phase_id}")
async def update_phase(phase_id: str, payload: PhaseUpdate,
                       user: dict = Depends(require_permission("construction", "update"))):
    """Koreksi nama/bobot fase. Nama baru disinkronkan ke dokumen anak (mis. permintaan material)."""
    phase = await db.construction_phases.find_one({"id": phase_id}, {"_id": 0})
    if not phase:
        raise HTTPException(status_code=404, detail="Fase tidak ditemukan")
    await assert_project_access(phase["project_id"], user)
    org = user.get("org_id", ORG_ID)
    upd = {k: v for k, v in payload.model_dump(exclude_unset=True).items()
           if v is not None or k == "work_category"}
    if "work_category" in upd:
        upd["work_category"] = (upd["work_category"] or "").strip().lower() or None
    if "name" in upd:
        dup = await db.construction_phases.find_one(
            {"org_id": org, "project_id": phase["project_id"], "name": upd["name"],
             "id": {"$ne": phase_id}})
        if dup:
            raise HTTPException(status_code=409, detail="Nama fase sudah dipakai di proyek ini.")
    if not upd:
        return {"data": serialize_doc(phase)}
    upd["updated_at"] = now_iso()
    await db.construction_phases.update_one({"id": phase_id, "org_id": org}, {"$set": upd})
    fresh = await db.construction_phases.find_one({"id": phase_id}, {"_id": 0})
    synced = await cascade_master_change("construction_phases", phase_id, fresh)
    if "weight" in upd or "work_category" in upd:
        await recompute_project_progress(phase["project_id"], org)
    await audit_log(user, "update", "construction_phases", phase_id, {"fields": sorted(upd)})
    return {"data": serialize_doc(fresh), "denorm_synced": synced}


@router.delete("/phases/{phase_id}")
async def delete_phase(phase_id: str,
                       user: dict = Depends(require_permission("construction", "update"))):
    """Hapus fase yang salah input. Ditolak bila sudah ada progres/inspeksi/permintaan material."""
    phase = await db.construction_phases.find_one({"id": phase_id}, {"_id": 0})
    if not phase:
        raise HTTPException(status_code=404, detail="Fase tidak ditemukan")
    await assert_project_access(phase["project_id"], user)
    org = user.get("org_id", ORG_ID)
    if int(phase.get("progress") or 0) > 0:
        raise HTTPException(status_code=400, detail=(
            "Fase sudah punya progres — tidak bisa dihapus. Ubah bobot/nama saja."))
    blockers = {
        "inspeksi": await db.inspections.count_documents({"org_id": org, "phase_id": phase_id}),
        "permintaan material": await db.material_requisitions.count_documents(
            {"org_id": org, "phase_id": phase_id}),
        "log konstruksi": await db.construction_logs.count_documents({"org_id": org, "phase_id": phase_id}),
    }
    used = {k: v for k, v in blockers.items() if v}
    if used:
        detail = ", ".join(f"{v} {k}" for k, v in used.items())
        raise HTTPException(status_code=400, detail=f"Fase dipakai oleh {detail} — tidak bisa dihapus.")
    await db.construction_phases.delete_one({"id": phase_id, "org_id": org})
    await recompute_project_progress(phase["project_id"], org)
    await audit_log(user, "delete", "construction_phases", phase_id, {"name": phase.get("name")})
    return {"data": {"id": phase_id, "deleted": True}}
