"""PERIZINAN BERTINGKAT (Fase 10 → diperluas Fase 46) — prefix `/permits`.

Fase 10 hanya melacak izin PROYEK dengan tenggat pengurusan. Fase 46 (`docs/v2/29` §5)
menutup tiga cacat:

  1. **Izin menempel pada objek**: `scope` (proyek/cluster/blok/unit) + `scope_id`, sehingga
     Unit 360 bisa menjawab "izin apa yang berlaku untuk rumah ini" — termasuk izin warisan
     dari blok/cluster/proyek.
  2. **Masa berlaku dinilai**: `expiry_at` + `reminder_days` → kesehatan izin
     (aktif / menjelang kedaluwarsa / kedaluwarsa) dihitung SATU tempat (`permit_scope`).
     Sebelumnya izin `approved` yang sudah mati tetap tampak aman.
  3. **Bisa dipakai gerbang**: `requirement_code` menautkan izin ke master dokumen syarat,
     dan `permit.block_build_without` memakai daftar izin ini untuk memblokir mulai bangun.

RBAC resource `permits` (PM penuh; pelaksana lapangan lihat + ubah status).
"""
from fastapi import APIRouter, Depends, HTTPException

import permit_alerts as pa
import permit_scope as ps
import settings_store as cfg
from core_utils import new_id, now_iso, serialize_doc
from db import ORG_ID, db
from models import PermitCreate, PermitStatusUpdate, PermitUpdate
from models_p46 import PermitRenew
from rbac import has_role, assert_project_access, audit_log, project_query, require_permission
from reference_p46 import PERMIT_SCOPE_LABEL

router = APIRouter(prefix="/permits", tags=["permits"])

STATUSES = ("not_started", "in_progress", "submitted", "approved", "rejected", "expired")
DONE = ("approved", "rejected", "expired")
SCOPE_COLL = {"cluster": "clusters", "block": "blocks", "unit": "units"}


def _org(user: dict) -> str:
    return user.get("org_id", ORG_ID)


async def _resolve_scope(org: str, project_id: str, scope: str, scope_id: str) -> dict:
    """Pastikan izin menempel pada objek yang NYATA dan masih satu proyek."""
    scope = scope or "project"
    if scope == "project":
        return {"scope": "project", "scope_id": project_id, "scope_label": None}
    if not scope_id:
        raise HTTPException(status_code=400, detail=(
            f"Cakupan '{PERMIT_SCOPE_LABEL[scope]}' butuh objek yang dipilih — "
            "tentukan cluster/blok/unit-nya."))
    doc = await db[SCOPE_COLL[scope]].find_one({"id": scope_id, "org_id": org}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404,
                            detail=f"{PERMIT_SCOPE_LABEL[scope]} tidak ditemukan.")
    if doc.get("project_id") and project_id and doc["project_id"] != project_id:
        raise HTTPException(status_code=400, detail=(
            "Objek yang dipilih bukan milik proyek ini — izin tidak boleh melintas proyek."))
    return {"scope": scope, "scope_id": scope_id,
            "scope_label": doc.get("name") or doc.get("code")}


def _decorate(row: dict, pmap: dict, today: str = None) -> dict:
    row["project_name"] = pmap.get(row.get("project_id"), row.get("project_name"))
    scope = row.get("scope") or "project"
    row["scope"] = scope
    row["scope_id"] = row.get("scope_id") or row.get("project_id")
    row["scope_type_label"] = PERMIT_SCOPE_LABEL.get(scope, scope)
    row.update(ps.health(row, today))
    row["overdue"] = bool(row.get("status") not in DONE and row.get("deadline")
                          and str(row["deadline"]) < (today or now_iso()))
    return row


@router.get("")
async def list_permits(project_id: str = None, status: str = None, scope: str = None,
                       scope_id: str = None, health: str = None, type: str = None,
                       q: str = None,
                       user: dict = Depends(require_permission("permits", "view"))):
    """Daftar izin global/proyek + kesehatan masa berlaku (dipakai tab Dokumen & Izin)."""
    org = _org(user)
    projs = await db.projects.find(project_query(user, {}),
                                   {"_id": 0, "id": 1, "name": 1}).to_list(500)
    pmap = {p["id"]: p["name"] for p in projs}
    fq = {"org_id": org}
    if has_role(user, "project_manager", "site_engineer"):
        fq["project_id"] = {"$in": list(pmap.keys())}
    if project_id:
        fq["project_id"] = project_id
    for field, val in (("status", status), ("scope", scope), ("scope_id", scope_id),
                       ("type", type)):
        if val:
            fq[field] = val
    if q:
        fq["$or"] = [{"name": {"$regex": q, "$options": "i"}},
                     {"reference_no": {"$regex": q, "$options": "i"}},
                     {"authority": {"$regex": q, "$options": "i"}}]
    rows = await db.permits.find(fq, {"_id": 0}).sort("deadline", 1).to_list(500)
    rows = [_decorate(r, pmap) for r in rows]
    if health:
        rows = [r for r in rows if r["health"] == health]
    summary = {
        "total": len(rows),
        "approved": sum(1 for r in rows if r.get("status") == "approved"),
        "in_progress": sum(1 for r in rows if r.get("status") in
                           ("not_started", "in_progress", "submitted")),
        "overdue": sum(1 for r in rows if r.get("overdue")),
        "expiring": sum(1 for r in rows if r["health"] == "expiring"),
        "expired": sum(1 for r in rows if r["health"] == "expired"),
        # JUJUR: izin tanpa tanggal berlaku bukan "aman" — disebut apa adanya.
        "no_expiry_data": sum(1 for r in rows if not r["expiry_known"]),
        "by_scope": {s: sum(1 for r in rows if r["scope"] == s)
                     for s in PERMIT_SCOPE_LABEL},
    }
    return {"data": serialize_doc(rows), "total": len(rows), "summary": summary}


@router.get("/coverage")
async def permit_coverage(project_id: str = None, cluster_id: str = None,
                          block_id: str = None, unit_id: str = None,
                          user: dict = Depends(require_permission("permits", "view"))):
    """Izin yang BERLAKU untuk satu objek (termasuk warisan) + izin wajib yang belum ada."""
    org = _org(user)
    if not any([project_id, cluster_id, block_id, unit_id]):
        raise HTTPException(status_code=400, detail=(
            "Sebutkan objeknya: unit_id, block_id, cluster_id, atau project_id."))
    required = list(await cfg.get("permit.block_build_without", org_id=org) or [])
    try:
        cov = await ps.coverage(org, unit_id=unit_id, block_id=block_id,
                                cluster_id=cluster_id, project_id=project_id,
                                required_codes=required)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    if cov["chain"].get("project_id"):
        await assert_project_access(cov["chain"]["project_id"], user)
    cov["blocking_policy"] = required
    return {"data": serialize_doc(cov)}


@router.post("")
async def create_permit(payload: PermitCreate,
                        user: dict = Depends(require_permission("permits", "create"))):
    proj = await assert_project_access(payload.project_id, user)
    org = _org(user)
    sc = await _resolve_scope(org, payload.project_id, payload.scope, payload.scope_id)
    ts = now_iso()
    doc = {
        "id": new_id(), "org_id": org, "project_id": payload.project_id,
        "project_name": proj.get("name"), "type": payload.type,
        "name": payload.name or payload.type, "reference_no": payload.reference_no,
        "authority": payload.authority, "status": "not_started",
        "deadline": payload.deadline, "reminder_days": payload.reminder_days,
        "expiry_at": payload.expiry_at, "requirement_code": payload.requirement_code,
        "scope": sc["scope"], "scope_id": sc["scope_id"], "scope_object": sc["scope_label"],
        "submitted_at": None, "approved_at": None, "notes": payload.notes,
        "created_by": user.get("email"), "created_at": ts, "updated_at": ts,
    }
    await db.permits.insert_one(dict(doc))
    doc.pop("_id", None)
    await audit_log(user, "permit.create", "permit", doc["id"],
                    {"type": doc["type"], "scope": doc["scope"], "scope_id": doc["scope_id"]})
    return {"data": serialize_doc(_decorate(doc, {payload.project_id: proj.get("name")}))}


async def _get(pid: str, user: dict) -> dict:
    doc = await db.permits.find_one({"id": pid, "org_id": _org(user)}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Perizinan tidak ditemukan")
    await assert_project_access(doc["project_id"], user)
    return doc


@router.get("/{pid}")
async def get_permit(pid: str, user: dict = Depends(require_permission("permits", "view"))):
    doc = await _get(pid, user)
    return {"data": serialize_doc(_decorate(doc, {}))}


@router.put("/{pid}")
async def update_permit(pid: str, payload: PermitUpdate,
                        user: dict = Depends(require_permission("permits", "update"))):
    doc = await _get(pid, user)
    upd = {k: v for k, v in payload.dict(exclude_unset=True).items() if v is not None}
    if "scope" in upd or "scope_id" in upd:
        sc = await _resolve_scope(doc["org_id"], doc["project_id"],
                                  upd.get("scope", doc.get("scope")),
                                  upd.get("scope_id", doc.get("scope_id")))
        upd.update({"scope": sc["scope"], "scope_id": sc["scope_id"],
                    "scope_object": sc["scope_label"]})
    upd["updated_at"] = now_iso()
    await db.permits.update_one({"id": pid, "org_id": doc["org_id"]}, {"$set": upd})
    await audit_log(user, "permit.update", "permit", pid, upd)
    return {"data": serialize_doc(_decorate(
        await db.permits.find_one({"id": pid}, {"_id": 0}), {}))}


@router.post("/{pid}/status")
async def permit_status(pid: str, payload: PermitStatusUpdate,
                        user: dict = Depends(require_permission("permits", "update"))):
    if payload.status not in STATUSES:
        raise HTTPException(status_code=400, detail="Status tidak valid.")
    doc = await _get(pid, user)
    ts = now_iso()
    setter = {"status": payload.status, "updated_at": ts}
    if payload.status == "submitted" and not doc.get("submitted_at"):
        setter["submitted_at"] = ts
    if payload.status == "approved":
        setter["approved_at"] = ts
    if payload.note:
        setter["notes"] = ((doc.get("notes") or "") + f"\n[{ts[:10]}] {payload.note}").strip()
    await db.permits.update_one({"id": pid, "org_id": doc["org_id"]}, {"$set": setter})
    await audit_log(user, "permit.status", "permit", pid, {"status": payload.status})
    return {"data": serialize_doc(_decorate(
        await db.permits.find_one({"id": pid}, {"_id": 0}), {}))}


@router.post("/{pid}/renew")
async def renew_permit(pid: str, payload: PermitRenew,
                       user: dict = Depends(require_permission("permits", "update"))):
    """Perpanjangan izin: masa berlaku baru tercatat berikut riwayatnya (bukan ditimpa)."""
    doc = await _get(pid, user)
    ts = now_iso()
    entry = {"at": ts, "by": user.get("email"), "from": doc.get("expiry_at"),
             "to": payload.expiry_at, "reference_no": payload.reference_no,
             "note": payload.note}
    setter = {"expiry_at": payload.expiry_at, "status": "approved", "updated_at": ts,
              "expiry_notified_on": None, "expiry_health": None}
    if payload.reference_no:
        setter["reference_no"] = payload.reference_no
    await db.permits.update_one({"id": pid, "org_id": doc["org_id"]},
                                {"$set": setter,
                                 "$push": {"renewals": {"$each": [entry], "$slice": -20}}})
    await audit_log(user, "permit.renew", "permit", pid, entry)
    return {"data": serialize_doc(_decorate(
        await db.permits.find_one({"id": pid}, {"_id": 0}), {})),
        "message": f"Masa berlaku izin diperpanjang sampai {str(payload.expiry_at)[:10]}."}


@router.post("/alerts/scan")
async def scan_expiry(user: dict = Depends(require_permission("permits", "update"))):
    """Jalankan pemeriksaan masa berlaku sekarang (job harian yang sama, agar bisa diuji)."""
    made = await pa.expiry_tick(_org(user))
    return {"data": {"alerts": made},
            "message": (f"{made} peringatan izin dikirim (notifikasi + tugas)." if made
                        else "Tidak ada izin yang kedaluwarsa atau menjelang kedaluwarsa "
                             "hari ini.")}


@router.delete("/{pid}")
async def delete_permit(pid: str,
                        user: dict = Depends(require_permission("permits", "update"))):
    doc = await _get(pid, user)
    await db.permits.delete_one({"id": pid, "org_id": doc["org_id"]})
    await audit_log(user, "permit.delete", "permit", pid, {"type": doc.get("type")})
    return {"data": {"deleted": True}}
