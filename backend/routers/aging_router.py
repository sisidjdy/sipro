"""Umur tahap & SLA (Fase 41) — endpoint kebijakan, laporan, dan pemeliharaan.

Kenapa endpoint ini ada, bukan sekadar kolom di tabel:
  * **Kebijakan** (`GET /aging/policy`): frontend TIDAK boleh lagi menulis ambang SLA sendiri.
    Sebelum Fase 41 ambang 72/48/168/336/720 jam ditulis di dalam komponen, sehingga
    kebijakan tidak bisa diubah tanpa deploy dan dua layar bisa memakai angka berbeda.
  * **Laporan** (`GET /aging/report`): "mana yang menganggur paling lama di tahapnya?"
    dihitung dengan agregasi database atas field tersimpan — bukan menarik semua dokumen
    lalu memindai riwayat di Python.
  * **Pemeliharaan** (`POST /aging/reconcile`): menyamakan jam tahap + memberlakukan
    kebijakan SLA terbaru ke baris yang sudah ada. Dijalankan otomatis (startup + sweeper
    tiap menit + saat setting SLA diubah); tombolnya tetap ada supaya admin bisa memaksa.
"""
from fastapi import APIRouter, Depends, HTTPException

import reference as ref
import stage_clock as clock
from core_utils import serialize_doc
from db import ORG_ID
from rbac import audit_log, require_permission

router = APIRouter(prefix="/aging", tags=["aging"])


@router.get("/policy")
async def aging_policy(project_id: str = None,
                       user: dict = Depends(require_permission("aging", "view"))):
    """Ambang SLA efektif per entitas & per tahap (SSOT Pusat Konfigurasi)."""
    org = user.get("org_id", ORG_ID)
    out = {}
    for entity, spec in clock.ENTITIES.items():
        out[entity] = {
            "label": spec["label"], "stage_field": spec["stage_field"],
            "vocab": spec["vocab"], "sla_key": spec["sla_key"],
            "list_path": spec["list_path"], "filter_param": spec["filter_param"],
            "sla_hours": await clock.policy(entity, org_id=org, project_id=project_id),
        }
    return {"data": out,
            "states": (ref.GROUPS.get("sla_state") or {}).get("options") or [],
            "entities": [{"value": k, "label": v["label"]} for k, v in out.items()]}


@router.get("/report")
async def aging_report(entity: str = "lead", project_id: str = None,
                       user: dict = Depends(require_permission("aging", "view"))):
    """Umur tahap per tahap: jumlah, lewat SLA, rata-rata/median/p90 umur, terlama."""
    if entity not in clock.ENTITIES:
        raise HTTPException(status_code=400,
                            detail=f"Objek umur tahap tidak dikenal: {entity}. "
                                   f"Pilihan: {', '.join(clock.ENTITIES)}")
    try:
        data = await clock.aging_report(entity, org_id=user.get("org_id", ORG_ID),
                                       project_id=project_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"data": serialize_doc(data)}


@router.get("/overview")
async def aging_overview(user: dict = Depends(require_permission("aging", "view"))):
    """Ringkasan lintas objek: berapa yang lewat SLA di setiap domain + tautan drill."""
    org = user.get("org_id", ORG_ID)
    rows = []
    for entity, spec in clock.ENTITIES.items():
        report = await clock.aging_report(entity, org_id=org)
        worst = max((r for r in report["rows"] if r["sla_hours"]),
                    key=lambda r: (r["over_sla"], r["p90_stage_age_hours"] or 0), default=None)
        rows.append({
            "entity": entity, "label": spec["label"], "vocab": spec["vocab"],
            "count": report["totals"]["count"], "over_sla": report["totals"]["over_sla"],
            "over2_sla": report["totals"]["over2_sla"],
            "clock_derived": report["totals"]["clock_derived"],
            "worst_stage": (worst or {}).get("stage"),
            "worst_over": (worst or {}).get("over_sla"),
            "drill": clock.drill_for(entity),
            "drill_over": clock.drill_for(entity, None, "over"),
        })
    totals = {
        "over_sla": sum(r["over_sla"] for r in rows),
        "over2_sla": sum(r["over2_sla"] for r in rows),
        "count": sum(r["count"] for r in rows),
        "clock_derived": sum(r["clock_derived"] for r in rows),
    }
    return {"data": rows, "totals": totals}


@router.post("/reconcile")
async def aging_reconcile(entity: str = None,
                          user: dict = Depends(require_permission("aging", "manage"))):
    """Samakan jam tahap + berlakukan kebijakan SLA terbaru (idempoten, aman diulang)."""
    if entity and entity not in clock.ENTITIES:
        raise HTTPException(status_code=400, detail=f"Objek tidak dikenal: {entity}")
    result = await clock.resync(entity, org_id=user.get("org_id", ORG_ID))
    await audit_log(user, "reconcile", "aging", entity or "all", {"result": result})
    return {"data": result}
