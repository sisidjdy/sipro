"""Field ops (Phase 11 — EPIC 2.8): Site Diary (buku harian) + Punch List (daftar cacat).

Both are construction-domain and reuse the `construction` RBAC resource. Read is
org+project scoped (PM/site only see their assigned projects). Creating a punch item
raises a corrective task in the Work Hub (assigned to the responsible party).
"""
from fastapi import APIRouter, Depends, HTTPException, Response

import docgen_p62 as p62
from db import db, ORG_ID
from core_utils import new_id, now_iso, serialize_doc, due_in
import offline_intake as oi
from rbac import has_role, require_permission, assert_project_access, project_query
from engine import auto_create_task, add_activity, emit, dispatch_pending

from models import SiteDiaryCreate, PunchCreate, PunchUpdate, PunchStatusUpdate  # noqa: F401
from models_p28 import DiaryCreateP28, PunchCreateP28, PunchStatusP28, PunchUpdateP28

router = APIRouter(prefix="/field", tags=["field"])
MAX_PHOTO = 2_200_000  # ~1.6MB base64
PUNCH_STATUS = ("open", "in_progress", "verified", "closed")
PROJECT_SCOPED = ("project_manager", "site_engineer")


def _check_photo(photo):
    if photo and len(photo) > MAX_PHOTO:
        raise HTTPException(status_code=400, detail="Foto terlalu besar (maks ~1.5MB). Kompres dulu.")


def _photo_list(payload) -> list:
    """Satukan kontrak foto lama & baru.

    Klien baru mengunggah berkas ke object storage lalu mengirim `photos` = daftar
    **file_id** (dokumen Mongo tetap ringan & gambar bisa di-cache browser). Klien lama
    yang masih mengirim `photo` base64 tetap diterima agar tidak ada regresi.
    """
    if payload.photos:
        return list(payload.photos)
    return [payload.photo] if payload.photo else []


async def _intake(org: str, kind: str, client_ref: str):
    """Penjaga antrean perangkat (Fase 50B).

    Kembalikan JAWABAN SIAP PAKAI bila kiriman ini sudah pernah diterima (`replay`), atau
    None bila memang kiriman baru. Dipakai buku harian & punch list karena keduanya
    dikerjakan di lokasi yang sering tanpa sinyal: tanpa penjaga ini, satu kiriman yang
    terputus di tengah jalan berubah menjadi DUA catatan begitu pemakai menekan ulang.
    """
    if not client_ref:
        return None
    intake = await oi.begin(org, kind, client_ref)
    if intake["state"] == "replay":
        return {"data": serialize_doc(intake.get("doc") or {}), "replay": True,
                "message": "Kiriman ini sudah pernah diterima server \u2014 catatan lamanya dipakai."}
    if intake["state"] == "inflight":
        raise HTTPException(status_code=409,
                            detail="Kiriman dengan penanda yang sama sedang diproses.")
    return None


async def _project_map(user: dict) -> dict:
    projs = await db.projects.find(project_query(user, {}), {"_id": 0, "id": 1, "name": 1}).to_list(500)
    return {p["id"]: p["name"] for p in projs}


def _scope(user: dict, pmap: dict, project_id: str = None) -> dict:
    fq = {"org_id": user.get("org_id", ORG_ID)}
    if has_role(user, *PROJECT_SCOPED):
        fq["project_id"] = {"$in": list(pmap.keys())}
    if project_id:
        fq["project_id"] = project_id
    return fq


# ------------------------------- Site Diary -------------------------------
@router.get("/diary")
async def list_diary(project_id: str = None,
                     user: dict = Depends(require_permission("construction", "view"))):
    pmap = await _project_map(user)
    rows = await db.site_diaries.find(_scope(user, pmap, project_id), {"_id": 0}).sort("log_date", -1).to_list(200)
    for r in rows:
        r["project_name"] = pmap.get(r.get("project_id"), r.get("project_name"))
    return {"data": serialize_doc(rows), "total": len(rows)}


@router.post("/diary")
async def create_diary(payload: DiaryCreateP28,
                       user: dict = Depends(require_permission("construction", "create"))):
    _check_photo(payload.photo)
    proj = await assert_project_access(payload.project_id, user)
    org = user.get("org_id", ORG_ID)
    replay = await _intake(org, "field_diary", payload.client_ref)
    if replay is not None:
        return replay
    ts = now_iso()
    photos = _photo_list(payload)
    doc = {
        "id": new_id(), "org_id": org, "project_id": payload.project_id, "project_name": proj.get("name"),
        "log_date": payload.log_date or ts, "weather": payload.weather,
        "workforce": payload.workforce or 0, "work_description": payload.work_description,
        "materials": payload.materials, "equipment": payload.equipment,
        "obstacles": payload.obstacles, "photo": photos[0] if photos else None,
        "photos": photos,
        "actor": user.get("email"), "created_at": ts,
    }
    await db.site_diaries.insert_one(dict(doc))
    doc.pop("_id", None)
    await oi.commit(org, "field_diary", payload.client_ref,
                    collection="site_diaries", doc_id=doc["id"])
    await add_activity(entity_type="project", entity_id=payload.project_id, type="system",
                       body=f"Buku harian {str(doc['log_date'])[:10]}: {payload.work_description[:60]}",
                       actor=user.get("email"), org_id=org)
    return {"data": serialize_doc(doc)}


# ------------------------------- Punch List -------------------------------
@router.get("/punchlist")
async def list_punch(project_id: str = None, status: str = None, unit_id: str = None,
                     user: dict = Depends(require_permission("construction", "view"))):
    pmap = await _project_map(user)
    fq = _scope(user, pmap, project_id)
    if status:
        fq["status"] = status
    # Fase 46 (unit-centric): tab Pembangunan di Unit 360 hanya menampilkan temuan rumah ini.
    if unit_id:
        fq["unit_id"] = unit_id
    rows = await db.punch_items.find(fq, {"_id": 0}).sort("created_at", -1).to_list(500)
    for r in rows:
        r["project_name"] = pmap.get(r.get("project_id"), r.get("project_name"))
    summary = {
        "total": len(rows),
        "open": sum(1 for r in rows if r.get("status") in ("open", "in_progress")),
        "verified": sum(1 for r in rows if r.get("status") == "verified"),
        "closed": sum(1 for r in rows if r.get("status") == "closed"),
        "high": sum(1 for r in rows if r.get("severity") == "high" and r.get("status") != "closed"),
    }
    return {"data": serialize_doc(rows), "total": len(rows), "summary": summary}


@router.get("/punchlist/pdf")
async def punch_pdf(project_id: str = None, status: str = None, unit_id: str = None,
                    user: dict = Depends(require_permission("construction", "view"))):
    """Cetak BERITA ACARA PEMERIKSAAN & PUNCH LIST berkop (Fase 62).

    Lingkupnya SAMA dengan daftar di layar (proyek/kavling/status yang sedang dilihat) supaya
    kertas yang ditandatangani di lapangan tidak pernah berbeda dari catatan sistem.
    """
    pmap = await _project_map(user)
    fq = _scope(user, pmap, project_id)
    if status:
        fq["status"] = status
    if unit_id:
        fq["unit_id"] = unit_id
    rows = await db.punch_items.find(fq, {"_id": 0}).sort("created_at", -1).to_list(500)
    unit = await db.units.find_one({"id": unit_id}, {"_id": 0, "code": 1}) if unit_id else None
    ctx = {"project_name": pmap.get(project_id) if project_id else None,
           "unit_code": (unit or {}).get("code"), "today": now_iso()}
    pdf = await p62.punch_pdf(user.get("org_id", ORG_ID), rows, ctx,
                              {"name": user.get("name"), "role": user.get("role")})
    return Response(content=pdf, media_type="application/pdf", headers={
        "Content-Disposition": 'inline; filename="berita-acara-punch-list.pdf"'})


@router.post("/punchlist")
async def create_punch(payload: PunchCreateP28,
                       user: dict = Depends(require_permission("construction", "create"))):
    _check_photo(payload.photo)
    proj = await assert_project_access(payload.project_id, user)
    org = user.get("org_id", ORG_ID)
    replay = await _intake(org, "punch_create", payload.client_ref)
    if replay is not None:
        return replay
    ts = now_iso()
    photos = _photo_list(payload)
    doc = {
        "id": new_id(), "org_id": org, "project_id": payload.project_id, "project_name": proj.get("name"),
        "unit_id": payload.unit_id, "title": payload.title, "description": payload.description,
        "location": payload.location, "category": payload.category or "lainnya",
        "severity": payload.severity or "medium", "status": "open",
        "assigned_to": payload.assigned_to, "due_date": payload.due_date,
        "photo": photos[0] if photos else None, "photos": photos, "fix_photos": [],
        "opened_by": user.get("email"), "closed_at": None, "created_at": ts, "updated_at": ts,
    }
    await db.punch_items.insert_one(dict(doc))
    doc.pop("_id", None)
    await oi.commit(org, "punch_create", payload.client_ref,
                    collection="punch_items", doc_id=doc["id"])
    await auto_create_task(
        source_event=f"punch:{doc['id']}",
        title=f"Punch: {payload.title} — {proj.get('code') or proj.get('name')}",
        jobdesk_code="TK-03",
        type="review", related_entity_type="punch_item", related_entity_id=doc["id"],
        assigned_to=payload.assigned_to, due_date=payload.due_date or due_in(days=3),
        sla_due_at=payload.due_date or due_in(days=3),
        priority="urgent" if payload.severity == "high" else "high", org_id=org,
        description=payload.description or payload.title)
    return {"data": serialize_doc(doc)}


async def _get_punch(pid: str, user: dict) -> dict:
    doc = await db.punch_items.find_one({"id": pid, "org_id": user.get("org_id", ORG_ID)}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Item punch tidak ditemukan")
    await assert_project_access(doc["project_id"], user)
    return doc


@router.get("/punchlist/{pid}")
async def get_punch(pid: str, user: dict = Depends(require_permission("construction", "view"))):
    return {"data": serialize_doc(await _get_punch(pid, user))}


@router.put("/punchlist/{pid}")
async def update_punch(pid: str, payload: PunchUpdateP28,
                       user: dict = Depends(require_permission("construction", "update"))):
    """Ubah temuan + TAMBAH foto temuan (foto lama tidak ditimpa)."""
    doc = await _get_punch(pid, user)
    upd = {k: v for k, v in payload.dict(exclude_unset=True).items() if v is not None}
    new_photos = upd.pop("photos", None)
    if new_photos:
        merged = list(doc.get("photos") or [])
        for f in new_photos:
            if f not in merged:
                merged.append(f)
        if len(merged) > 6:
            raise HTTPException(status_code=400, detail="Maksimal 6 foto temuan.")
        upd["photos"] = merged
        upd["photo"] = merged[0]
    upd["updated_at"] = now_iso()
    await db.punch_items.update_one({"id": pid, "org_id": doc["org_id"]}, {"$set": upd})
    return {"data": serialize_doc(await db.punch_items.find_one({"id": pid}, {"_id": 0}))}


@router.post("/punchlist/{pid}/status")
async def punch_status(pid: str, payload: PunchStatusP28,
                       user: dict = Depends(require_permission("construction", "update"))):
    """Ubah status temuan + lampirkan **foto bukti perbaikan** (foto 'sesudah').

    Foto perbaikan disimpan terpisah (`fix_photos`) supaya galeri kavling bisa
    menunjukkan pasangan sebelum→sesudah, bukan menimpa foto temuan aslinya.
    """
    if payload.status not in PUNCH_STATUS:
        raise HTTPException(status_code=400, detail="Status tidak valid.")
    doc = await _get_punch(pid, user)
    replay = await _intake(doc["org_id"], "punch_status", payload.client_ref)
    if replay is not None:
        return replay
    ts = now_iso()
    setter = {"status": payload.status, "updated_at": ts}
    if payload.status == "closed":
        setter["closed_at"] = ts
    new_photos = list(payload.photos or [])
    if new_photos:
        setter["fix_photos"] = list(doc.get("fix_photos") or []) + new_photos
    if payload.note:
        # Catatan perbaikan disimpan pada temuan (bukan hanya di log aktivitas) supaya
        # kartu bukti "sebelum → sesudah" bisa menjelaskan APA yang dikerjakan.
        setter["fix_note"] = payload.note.strip()[:400]
    await db.punch_items.update_one({"id": pid, "org_id": doc["org_id"]}, {"$set": setter})
    if new_photos or payload.note:
        detail = payload.note or f"{len(new_photos)} foto bukti perbaikan dilampirkan"
        await add_activity(
            entity_type="unit" if doc.get("unit_id") else "project",
            entity_id=doc.get("unit_id") or doc["project_id"], type="system",
            body=f"Punch '{doc.get('title')}' → {payload.status}: {detail}",
            actor=user.get("email"), org_id=doc["org_id"])
    await oi.commit(doc["org_id"], "punch_status", payload.client_ref,
                    collection="punch_items", doc_id=pid,
                    summary={"status": payload.status})
    return {"data": serialize_doc(await db.punch_items.find_one({"id": pid}, {"_id": 0}))}
