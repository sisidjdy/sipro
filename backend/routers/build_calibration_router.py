"""ROUTER Fase 37 — KALIBRASI SEKALI KLIK, prefix `/build/calibration`.

Kenapa router terpisah? Sama seperti Fase 34/36: `build_router.py` harus tetap di bawah
batas gate compliance, dan seluruh hal yang menyangkut KALIBRASI template (usulan, pratinjau,
eksekusi, riwayat, pembatalan) berada di satu tempat yang mudah diaudit.

RBAC (resource `construction`):
  * lihat usulan & riwayat — `construction.view` (PM, direksi, pelaksana, keuangan)
  * mengubah template (apply/rollback) — HANYA admin/direksi/Manajer Proyek, karena durasi
    & waktu tunggu template menjadi dasar SELURUH tenggat, pengingat, dan eskalasi.
    Setiap perubahan ditulis ke `audit_logs` (siapa, kapan, apa, alasannya).

Yang TIDAK dilakukan router ini (dijaga gate `verify_37`): ia tidak pernah menyentuh
`build_items` / `build_schedules`. Jadwal unit yang sudah berjalan tidak boleh bergeser oleh
kalibrasi template — itu tetap urusan Fase 34 (`POST /build/bulk/shift`, wajib penyebab).
"""
from fastapi import APIRouter, Depends, HTTPException, Query

import build_calibration as bcx
from core_utils import serialize_doc
from db import ORG_ID
from models_p37 import CalibrationApplyIn, CalibrationIn, CalibrationRollbackIn
from rbac import has_role, assert_project_access, audit_log, require_permission

router = APIRouter(prefix="/build/calibration", tags=["build-calibration"])
CONFIG_ROLES = ("owner", "super_admin", "project_manager")
ONLY_ADMIN = ("Hanya admin/direksi/Manajer Proyek yang boleh mengalibrasi template — "
              "durasi & waktu tunggu template menjadi dasar seluruh tenggat, pengingat, "
              "dan eskalasi pekerjaan.")


def _org(user: dict) -> str:
    return user.get("org_id", ORG_ID)


def _can(user: dict) -> dict:
    return {"calibrate": has_role(user, *CONFIG_ROLES)}


def _guard(user: dict):
    if not has_role(user, *CONFIG_ROLES):
        raise HTTPException(status_code=403, detail=ONLY_ADMIN)


@router.get("/candidates")
async def list_candidates(project_id: str = None,
                          user: dict = Depends(require_permission("construction", "view"))):
    """Usulan kalibrasi dari Analitik Telat + langkah template yang bisa dikalibrasi."""
    if project_id:
        await assert_project_access(project_id, user)
    out = await bcx.candidates(_org(user), user, project_id)
    return {"data": serialize_doc(out), "can": _can(user)}


@router.post("/preview")
async def preview(payload: CalibrationIn,
                  user: dict = Depends(require_permission("construction", "view"))):
    """Pratinjau dampak kalibrasi. Fungsi hitungnya SAMA dengan yang dipakai eksekusi."""
    try:
        out = await bcx.preview(_org(user), payload.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"data": serialize_doc(out), "can": _can(user)}


@router.post("/apply")
async def apply(payload: CalibrationApplyIn,
                user: dict = Depends(require_permission("construction", "update"))):
    """Terapkan kalibrasi ke template (wajib alasan + catatan; idempoten via client_ref)."""
    _guard(user)
    try:
        out = await bcx.apply(_org(user), user.get("email"), payload.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    cal = out["calibration"]
    if not out.get("replayed"):
        await audit_log(user, "calibration_apply", "build_templates", cal["template_id"],
                        {"step": cal["step_code"], "kind": cal["kind"],
                         "delta_days": cal["delta_days"], "cause": cal.get("cause"),
                         "total_days": [cal["total_days_before"], cal["total_days_after"]]})
    return {"data": serialize_doc(cal), "template": serialize_doc(out.get("template")),
            "impact": serialize_doc(out.get("impact")), "replayed": out.get("replayed"),
            "can": _can(user),
            "message": (cal["explain"] + (
                f" {cal['schedules_running_at_apply']} jadwal unit yang sudah dibuat tidak "
                "diubah." if cal.get("schedules_running_at_apply") else ""))}


@router.get("/history")
async def history(template_id: str = None, limit: int = Query(default=50, ge=1, le=200),
                  user: dict = Depends(require_permission("construction", "view"))):
    """Riwayat kalibrasi: sebelum→sesudah, pelaku, alasan, dan apakah sudah dikembalikan."""
    rows = await bcx.history(_org(user), template_id, limit)
    return {"data": serialize_doc(rows), "total": len(rows), "can": _can(user)}


@router.post("/{calibration_id}/rollback")
async def rollback(calibration_id: str, payload: CalibrationRollbackIn,
                   user: dict = Depends(require_permission("construction", "update"))):
    """Kembalikan template ke nilai sebelum kalibrasi itu (tetap wajib beralasan)."""
    _guard(user)
    try:
        out = await bcx.rollback(_org(user), user.get("email"), calibration_id,
                                payload.note, payload.client_ref)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit_log(user, "calibration_rollback", "build_templates",
                    out["calibration"]["template_id"],
                    {"calibration_id": calibration_id, "note": payload.note[:120]})
    return {"data": serialize_doc(out["calibration"]),
            "template": serialize_doc(out.get("template")),
            "reverted": out["reverted"], "can": _can(user),
            "message": out["calibration"]["explain"]}
