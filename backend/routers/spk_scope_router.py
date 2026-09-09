"""LINGKUP SPK & OPNAME BERBUKTI (Fase 33) — endpoint.

Menghubungkan tiga hal yang dulu terpisah: **RAB/BoQ** (anggaran), **item jadwal
pembangunan** (Fase 31/32: bukti foto + verifikasi supervisor), dan **termin subkon**
(uang keluar). Semua penolakan memakai bahasa yang bisa dipahami orang lapangan dan
menyebut jalan keluarnya.

RBAC: baca = `subcon:view`; ubah lingkup = `subcon:update` (PM). Persetujuan uang tetap
di `progress_claims:approve` (finance/owner) pada `subcon_claims_router`.
"""
from fastapi import APIRouter, Depends, HTTPException

import opname as op
from core_utils import serialize_doc
from db import db, ORG_ID
from engine import add_activity
from models_p33 import ScopeAddIn
from rbac import require_permission, assert_project_access, audit_log

router = APIRouter(prefix="/subcon", tags=["subcon-scope"])


async def _spk(org: str, sid: str, user: dict) -> dict:
    doc = await db.spk.find_one({"id": sid, "org_id": org}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="SPK tidak ditemukan")
    await assert_project_access(doc["project_id"], user)
    return doc


@router.get("/spk/{sid}/scope")
async def get_scope(sid: str, user: dict = Depends(require_permission("subcon", "view"))):
    org = user.get("org_id", ORG_ID)
    spk = await _spk(org, sid, user)
    rows = await op.scope_rows(org, sid)
    # Angka ringkas pada dokumen SPK ditulis ulang di sini supaya kopi tidak pernah basi
    # (SSOT tetap baris lingkup + status item pekerjaan).
    s = await op.sync_spk(org, sid)
    spk = await db.spk.find_one({"id": sid, "org_id": org}, {"_id": 0}) or spk
    contract = int(spk.get("contract_value") or 0)
    return {
        "data": serialize_doc(rows), "summary": s,
        "spk": serialize_doc({k: spk.get(k) for k in (
            "id", "spk_number", "subcontractor_name", "project_id", "project_name", "title",
            "contract_value", "retention_pct", "status", "scope_mode", "progress_pct",
            "billed_pct")}),
        "contract": {
            "contract_value": contract, "allocated": s["scope_value"],
            "unallocated": contract - s["scope_value"],
            "fully_allocated": bool(contract and s["scope_value"] == contract),
        },
        "blockers": op._blockers(rows),
    }


@router.get("/spk/{sid}/scope/candidates")
async def scope_candidates(sid: str, unit_id: str = None,
                           user: dict = Depends(require_permission("subcon", "view"))):
    org = user.get("org_id", ORG_ID)
    spk = await _spk(org, sid, user)
    return {"data": serialize_doc(await op.candidates(org, spk, unit_id))}


@router.post("/spk/{sid}/scope")
async def add_scope(sid: str, payload: ScopeAddIn,
                    user: dict = Depends(require_permission("subcon", "update"))):
    org = user.get("org_id", ORG_ID)
    spk = await _spk(org, sid, user)
    try:
        out = await op.add_lines(org, spk, payload.lines, user.get("email"))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit_log(user, "update", "spk_scope", sid,
                    {"added": out["added"], "scope_value": out["summary"]["scope_value"]})
    await add_activity(entity_type="project", entity_id=spk["project_id"], type="system",
                       body=(f"Lingkup SPK {spk.get('spk_number')} ditambah {out['added']} item "
                             f"pekerjaan (total {op.rp(out['summary']['scope_value'])}). "
                             "Termin selanjutnya dihitung dari pekerjaan terverifikasi."),
                       actor=user.get("email"), org_id=org)
    return {"data": out}


@router.delete("/spk/{sid}/scope/{scope_id}")
async def remove_scope(sid: str, scope_id: str,
                       user: dict = Depends(require_permission("subcon", "update"))):
    org = user.get("org_id", ORG_ID)
    await _spk(org, sid, user)
    try:
        out = await op.remove_line(org, sid, scope_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit_log(user, "delete", "spk_scope", scope_id, {"spk_id": sid})
    return {"data": out}


@router.get("/spk/{sid}/opname")
async def opname(sid: str, user: dict = Depends(require_permission("subcon", "view"))):
    """Pratinjau opname: pekerjaan terverifikasi yang BELUM ditagih + estimasi retensi."""
    org = user.get("org_id", ORG_ID)
    spk = await _spk(org, sid, user)
    return {"data": serialize_doc(await op.opname_preview(org, spk))}
