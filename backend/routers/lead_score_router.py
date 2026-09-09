"""Router skor lead (Fase 88B/89) — rincian "kenapa angkanya begini", nilai ulang, dan
KONFIGURASI EVENT (daftar event, poin +/−, parameter, aktif, event kustom) + pencatatan
event kustom oleh sales."""
import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

import lead_scoring as ls
import settings_store as cfg
from core_utils import now_iso, serialize_doc
from db import ORG_ID, db
from engine import add_activity
from rbac import audit_log, is_scoped_sales, require_permission

router = APIRouter(tags=["leads"])


class ScoreEventIn(BaseModel):
    key: str = Field(min_length=2, max_length=40)
    label: str = Field(min_length=2, max_length=80)
    points: int = Field(ge=-100, le=100)
    active: bool = True
    desc: Optional[str] = None
    params: dict = Field(default_factory=dict)


class ScoreEventsIn(BaseModel):
    events: list[ScoreEventIn]
    reason: Optional[str] = None


class LogEventIn(BaseModel):
    event_key: str
    note: Optional[str] = None


async def _lead(lead_id: str, user: dict) -> dict:
    org = user.get("org_id", ORG_ID)
    lead = await db.leads.find_one({"id": lead_id, "org_id": org}, {"_id": 0})
    if not lead:
        raise HTTPException(status_code=404, detail="Lead tidak ditemukan")
    if is_scoped_sales(user) and lead.get("assigned_to") != user.get("email"):
        raise HTTPException(status_code=403, detail="Akses ditolak: bukan lead Anda")
    return lead


@router.get("/leads/{lead_id}/score")
async def lead_score(lead_id: str, user: dict = Depends(require_permission("leads", "view"))):
    """Skor TERKINI (dihitung saat dibaca) beserta rincian event & fakta keterlibatan."""
    lead = await _lead(lead_id, user)
    org = lead.get("org_id", ORG_ID)
    out = await ls.rescore(org, lead)
    custom = [e for e in await ls.events_for(org) if e["kind"] == "custom" and e.get("active", True)]
    return {"data": serialize_doc({**out, "stored_score": lead.get("score"),
                                   "stored_band": lead.get("score_band"), "custom_events": custom})}


@router.post("/leads/{lead_id}/rescore")
async def lead_rescore(lead_id: str, user: dict = Depends(require_permission("leads", "update"))):
    lead = await _lead(lead_id, user)
    out = await ls.rescore(lead.get("org_id", ORG_ID), lead)
    await db.leads.update_one({"id": lead_id}, {"$set": {**out, "updated_at_score": now_iso()}})
    return {"data": serialize_doc(out), "message": f"Skor dinilai ulang: {out['score']}."}


@router.post("/leads/{lead_id}/score-events")
async def log_score_event(lead_id: str, payload: LogEventIn,
                          user: dict = Depends(require_permission("leads", "update"))):
    """Sales mencatat event kustom (mis. hadir open house) → skor langsung dihitung ulang."""
    lead = await _lead(lead_id, user)
    org = lead.get("org_id", ORG_ID)
    ev = next((e for e in await ls.events_for(org) if e["key"] == payload.event_key), None)
    if not ev or ev["kind"] != "custom":
        raise HTTPException(status_code=400, detail="Event kustom tidak dikenal.")
    if not ev.get("active", True):
        raise HTTPException(status_code=400, detail=f"Event '{ev['label']}' sedang nonaktif.")
    sign = "+" if ev["points"] >= 0 else ""
    await add_activity(entity_type="lead", entity_id=lead_id, type="score_event",
                       body=f"Event skor: {ev['label']} ({sign}{ev['points']})"
                            + (f" — {payload.note}" if payload.note else ""),
                       actor=user.get("email", "system"), org_id=org,
                       meta={"event_key": ev["key"], "points": ev["points"]})
    out = await ls.rescore(org, lead)
    await db.leads.update_one({"id": lead_id}, {"$set": {**out, "updated_at_score": now_iso()}})
    return {"data": serialize_doc(out), "message": f"Event '{ev['label']}' dicatat. Skor: {out['score']}."}


# ------------------------------------------------ konfigurasi event (admin)
@router.get("/lead-score/events")
async def list_events(user: dict = Depends(require_permission("settings", "view"))):
    org = user.get("org_id", ORG_ID)
    return {"data": {"events": await ls.events_for(org),
                     "bands": await cfg.get("lead.score.bands", org_id=org),
                     "defaults": ls.default_events()}}


@router.put("/lead-score/events")
async def save_events(payload: ScoreEventsIn,
                      user: dict = Depends(require_permission("settings", "manage"))):
    org = user.get("org_id", ORG_ID)
    keys = [e.key for e in payload.events]
    if len(set(keys)) != len(keys):
        raise HTTPException(status_code=400, detail="Kunci event tidak boleh ganda.")
    rows = []
    for e in payload.events:
        if e.key not in ls.SYSTEM_KEYS and not re.fullmatch(r"[a-z0-9_]+", e.key):
            raise HTTPException(status_code=400, detail=f"Kunci event kustom '{e.key}' harus huruf kecil/angka/garis bawah.")
        rows.append({"key": e.key, "label": e.label.strip(), "points": e.points, "active": e.active,
                     "desc": (e.desc or "").strip(),
                     "params": {k: int(v) for k, v in (e.params or {}).items() if v is not None}})
    try:
        await cfg.set_value("lead.score.events", rows, actor=user.get("email", "system"),
                            reason=payload.reason or "Konfigurasi event skor lead", org_id=org)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit_log(user, "update", "settings", "lead.score.events")
    return {"data": {"events": await ls.events_for(org)}, "message": "Event skor lead disimpan."}


@router.post("/lead-score/events/reset")
async def reset_events(user: dict = Depends(require_permission("settings", "manage"))):
    org = user.get("org_id", ORG_ID)
    await cfg.reset("lead.score.events", actor=user.get("email", "system"), org_id=org)
    return {"data": {"events": await ls.events_for(org)}, "message": "Event skor lead dikembalikan ke bawaan."}


@router.post("/lead-score/rescore-all")
async def rescore_all(user: dict = Depends(require_permission("settings", "manage"))):
    out = await ls.rescore_all(user.get("org_id", ORG_ID))
    return {"data": out, "message": f"{out['total']} lead dinilai ulang, {out['changed']} berubah."}
