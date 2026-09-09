"""ROUTER Fase 34 — JADWAL MASSAL & GESER TANGGAL SERENTAK, prefix `/build/bulk`.

Kenapa router terpisah dari `build_router.py`? Supaya file itu tetap di bawah batas
gate compliance dan seluruh operasi MASSAL (yang berisiko tinggi: menyentuh banyak
rumah sekaligus) berada di satu tempat yang mudah diaudit.

RBAC (resource `construction`):
  * view   — melihat kandidat, blok, target geser, dan riwayat operasi massal
  * create — menjalankan jadwal massal (PM/direksi)
  * approve— menjalankan penggeseran tanggal (PM/direksi) karena mengubah tenggat,
             pengingat, dan eskalasi seluruh rumah
"""
from fastapi import APIRouter, Depends, HTTPException, Query

import build_bulk as bb
from core_utils import serialize_doc
from db import ORG_ID
from models_p34 import BulkScheduleIn, BulkShiftIn
from rbac import has_role, assert_project_access, audit_log, require_permission

router = APIRouter(prefix="/build/bulk", tags=["build-bulk"])
SUPERVISOR_ROLES = ("owner", "super_admin", "project_manager")
ONLY_PM = ("Hanya Manajer Proyek/direksi yang boleh menjalankan operasi massal jadwal "
           "(tanggal jadi dasar tenggat, pengingat, dan eskalasi seluruh rumah).")


def _org(user: dict) -> str:
    return user.get("org_id", ORG_ID)


def _guard(user: dict):
    if not has_role(user, *SUPERVISOR_ROLES):
        raise HTTPException(status_code=403, detail=ONLY_PM)


async def _scope(project_id: str, user: dict):
    if project_id:
        await assert_project_access(project_id, user)


@router.get("/blocks")
async def blocks(project_id: str = None,
                 user: dict = Depends(require_permission("construction", "view"))):
    """Ringkasan blok/cluster: berapa rumah sudah & belum terjadwal."""
    await _scope(project_id, user)
    rows = await bb.blocks(_org(user), project_id)
    return {"data": serialize_doc(rows), "total": len(rows),
            "can": {"run": has_role(user, *SUPERVISOR_ROLES)}}


@router.get("/candidates")
async def candidates(project_id: str = None, block: str = None, unit_type: str = None,
                     user: dict = Depends(require_permission("construction", "view"))):
    """Unit belum terjadwal + template yang akan dipakai / alasan tidak bisa dijadwalkan."""
    await _scope(project_id, user)
    rows = await bb.candidates(_org(user), project_id, block, unit_type)
    return {"data": serialize_doc(rows), "total": len(rows),
            "schedulable": len([r for r in rows if r.get("schedulable")]),
            "can": {"run": has_role(user, *SUPERVISOR_ROLES)}}


@router.post("/schedules/preview")
async def preview_schedules(payload: BulkScheduleIn,
                            user: dict = Depends(require_permission("construction", "view"))):
    """Pratinjau: tanggal & jumlah item per unit SEBELUM apa pun ditulis (INV-34-6)."""
    try:
        out = await bb.plan_create(_org(user), payload.unit_ids, payload.template_id,
                                   payload.start_date, payload.stagger_days, payload.wave)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"data": serialize_doc(out["rows"]), "summary": serialize_doc(out["summary"]),
            "can": {"run": has_role(user, *SUPERVISOR_ROLES)}}


@router.post("/schedules")
async def run_schedules(payload: BulkScheduleIn,
                        user: dict = Depends(require_permission("construction", "create"))):
    """Jalankan jadwal massal. Unit yang sudah punya jadwal DILEWATI, tidak ditimpa."""
    _guard(user)
    try:
        run = await bb.run_create(_org(user), payload.unit_ids, payload.template_id,
                                  payload.start_date, payload.stagger_days, payload.wave,
                                  user, payload.client_ref)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit_log(user, "bulk_create", "build_schedules", run["id"], run.get("summary"))
    return {"data": serialize_doc(run)}


@router.get("/shift/targets")
async def shift_targets(project_id: str = None, block: str = None,
                        user: dict = Depends(require_permission("construction", "view"))):
    """Jadwal yang bisa digeser + jumlah pekerjaan yang tanggalnya terkunci bukti."""
    await _scope(project_id, user)
    rows = await bb.shift_targets(_org(user), project_id, block)
    return {"data": serialize_doc(rows), "total": len(rows),
            "can": {"run": has_role(user, *SUPERVISOR_ROLES)}}


@router.post("/shift/preview")
async def preview_shift(payload: BulkShiftIn,
                        user: dict = Depends(require_permission("construction", "view"))):
    """Pratinjau dampak penggeseran: tanggal lama → baru, digeser vs dipertahankan."""
    try:
        out = await bb.plan_shift(_org(user), payload.schedule_ids, payload.shift_days)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    rows = [{k: v for k, v in r.items() if k != "moves"} for r in out["rows"]]
    return {"data": serialize_doc(rows), "summary": serialize_doc(out["summary"]),
            "can": {"run": has_role(user, *SUPERVISOR_ROLES)}}


@router.post("/shift")
async def run_shift(payload: BulkShiftIn,
                    user: dict = Depends(require_permission("construction", "approve"))):
    """Jalankan penggeseran serentak — wajib beralasan, bukti kerja tidak disentuh."""
    _guard(user)
    try:
        run = await bb.run_shift(_org(user), payload.schedule_ids, payload.shift_days,
                                 payload.cause, payload.note, user, payload.client_ref)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit_log(user, "bulk_shift", "build_schedules", run["id"], run.get("summary"))
    return {"data": serialize_doc(run)}


@router.get("/runs")
async def runs(kind: str = None, limit: int = Query(default=20, ge=1, le=100),
               user: dict = Depends(require_permission("construction", "view"))):
    """Riwayat operasi massal — transparansi: siapa mengubah jadwal banyak rumah, kapan."""
    rows = await bb.runs(_org(user), kind, limit)
    return {"data": serialize_doc(rows), "total": len(rows)}
