"""Drill-down KPI lintas modul (Fase 92)."""
from fastapi import APIRouter, Depends, HTTPException, Request

import kpi_drilldown as kd
from security import get_current_user

router = APIRouter(prefix="/drilldown", tags=["drilldown"])


# Kartu = PARTISI pipeline: Aktif + Menang + Daur ulang + Hilang = Total (tidak tumpang tindih).
LEAD_KPIS = [
    {"key": "total", "label": "Total lead", "tone": "primary", "params": {}},
    {"key": "active", "label": "Aktif (akuisisi → booking)", "tone": "sky",
     "params": {"stage": "acquisition,nurturing,appointment,booking"}},
    {"key": "won", "label": "Menang (won)", "tone": "emerald", "params": {"stage": "won"}},
    {"key": "recycle", "label": "Daur ulang", "tone": "amber", "params": {"stage": "recycle"}},
    {"key": "lost", "label": "Hilang (lost)", "tone": "rose", "params": {"stage": "lost"}},
]


@router.get("/_summary/leads")
async def leads_summary(user: dict = Depends(get_current_user)):
    """Angka kartu KPI Pipeline Lead — dihitung dengan definisi yang SAMA dengan rinciannya."""
    if not await kd.allowed(user, "leads"):
        raise HTTPException(status_code=403, detail="Peran Anda tidak boleh membaca lead.")
    out = []
    for k in LEAD_KPIS:
        d = await kd.drilldown(user, "leads", k["params"])
        out.append({**k, "value": d["count"], "drill": d["href_all"]})
    return {"data": out}


@router.get("/{key}")
async def drilldown(key: str, request: Request, user: dict = Depends(get_current_user)):
    """Baris penyusun satu angka KPI (Beranda/Lead/Pembangunan/Keuangan) + tautan terfilter."""
    if not await kd.allowed(user, key):
        raise HTTPException(status_code=403, detail="Peran Anda tidak boleh membuka rincian angka ini.")
    try:
        return {"data": await kd.drilldown(user, key, dict(request.query_params))}
    except KeyError:
        raise HTTPException(status_code=404, detail="Kunci KPI tidak dikenal.")
