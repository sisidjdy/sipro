"""Pusat Konfigurasi — endpoint registry setting bisnis (Fase 39).

Semua aturan bisnis (masa keep unit, DP, potongan pembatalan, toleransi cicilan, tarif PPh,
penomoran dokumen, dst) dibaca & diubah lewat sini — tidak ada angka mati di kode.
Perubahan setting sensitif WAJIB beralasan dan selalu meninggalkan jejak.
"""
from fastapi import APIRouter, Depends, HTTPException

import settings_store as cfg
import stage_clock as clock
from core_utils import serialize_doc
from db import ORG_ID
from models_v2 import SettingBulk, SettingUpdate
from rbac import audit_log, require_permission

router = APIRouter(prefix="/settings", tags=["config"])


@router.get("")
async def list_settings(group: str = None, q: str = None, project_id: str = None,
                       user: dict = Depends(require_permission("settings", "view"))):
    """Daftar setting + nilai efektif + asal nilai (default/org/project) + jejak terakhir."""
    org = user.get("org_id", ORG_ID)
    rows = await cfg.listing(org_id=org, group=group, project_id=project_id, q=q)
    return {"data": serialize_doc(rows), "groups": await cfg.groups_summary(org_id=org),
            "total": len(rows)}


@router.get("/groups")
async def setting_groups(user: dict = Depends(require_permission("settings", "view"))):
    return {"data": await cfg.groups_summary(org_id=user.get("org_id", ORG_ID))}


@router.get("/effective")
async def effective(keys: str, project_id: str = None,
                    user: dict = Depends(require_permission("settings", "view"))):
    """Nilai efektif beberapa key sekaligus (dipakai UI & modul lain)."""
    wanted = [k.strip() for k in (keys or "").split(",") if k.strip()]
    unknown = [k for k in wanted if k not in cfg.DEFAULTS]
    if unknown:
        raise HTTPException(status_code=400,
                            detail=f"Setting tidak dikenal: {', '.join(unknown)}")
    return {"data": await cfg.get_many(wanted, org_id=user.get("org_id", ORG_ID),
                                       project_id=project_id)}


@router.get("/{key}/history")
async def setting_history(key: str,
                          user: dict = Depends(require_permission("settings", "view"))):
    if key not in cfg.DEFAULTS:
        raise HTTPException(status_code=404, detail="Setting tidak dikenal.")
    return {"data": await cfg.history(key, org_id=user.get("org_id", ORG_ID))}


@router.put("/{key}")
async def update_setting(key: str, payload: SettingUpdate,
                         user: dict = Depends(require_permission("settings", "manage"))):
    org = user.get("org_id", ORG_ID)
    try:
        res = await cfg.set_value(key, payload.value, actor=user.get("email"),
                                  reason=payload.reason, org_id=org, scope=payload.scope,
                                  scope_id=payload.scope_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit_log(user, "update", "settings", key,
                    {"value": payload.value, "reason": payload.reason,
                     "scope": payload.scope})
    # Fase 41: kebijakan SLA yang diubah WAJIB langsung berlaku pada baris yang sudah ada.
    # Tanpa ini, `stage_due_at` lama tetap dipakai daftar & laporan — setting hanya jadi
    # hiasan dan pemakai menyimpulkan "ubah SLA tidak berpengaruh".
    if key.endswith(".sla_hours"):
        res["resync"] = await clock.resync_for_setting(key, org_id=org)
    return {"data": serialize_doc(res)}


@router.post("/bulk")
async def bulk_update(payload: SettingBulk,
                      user: dict = Depends(require_permission("settings", "manage"))):
    org = user.get("org_id", ORG_ID)
    done, failed = [], []
    for item in payload.items:
        try:
            res = await cfg.set_value(item.key, item.value, actor=user.get("email"),
                                      reason=item.reason, org_id=org, scope=item.scope,
                                      scope_id=item.scope_id)
            done.append(res["key"])
        except ValueError as e:
            failed.append({"key": item.key, "reason": str(e)})
    await audit_log(user, "update", "settings", "bulk",
                    {"ok": done, "failed": [f["key"] for f in failed]})
    for key in done:
        if key.endswith(".sla_hours"):
            await clock.resync_for_setting(key, org_id=org)
    return {"data": {"updated": done, "failed": failed}}


@router.post("/{key}/reset")
async def reset_setting(key: str, scope: str = "org", scope_id: str = None,
                        user: dict = Depends(require_permission("settings", "manage"))):
    try:
        res = await cfg.reset(key, actor=user.get("email"), org_id=user.get("org_id", ORG_ID),
                              scope=scope, scope_id=scope_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit_log(user, "update", "settings", key, {"reset": True, "scope": scope})
    if key.endswith(".sla_hours"):
        res["resync"] = await clock.resync_for_setting(
            key, org_id=user.get("org_id", ORG_ID))
    return {"data": res}
