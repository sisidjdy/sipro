"""BoQ / RAB — Bill of Quantities / Rencana Anggaran Biaya (Phase 12 — EPIC 2.1).

Per-project budget line items (cost_code + category + qty × unit_price = amount).
Provides a cost-control summary: budget (BoQ) vs committed (approved POs) vs actual
(AP bills), so overruns surface early. Read is org+project scoped; project-scoped
roles only see their assigned projects.
"""
from fastapi import APIRouter, Depends, HTTPException

import opname as op
from db import db, ORG_ID
from core_utils import new_id, now_iso, serialize_doc
from rbac import has_role, require_permission, assert_project_access, project_query
from models import BoQItemCreate, BoQItemUpdate
from models_p33 import BoQStepMapIn

router = APIRouter(prefix="/boq", tags=["boq"])
PROJECT_SCOPED = ("project_manager", "site_engineer")


async def _accessible_project_ids(user: dict):
    projs = await db.projects.find(project_query(user, {}), {"_id": 0, "id": 1, "name": 1}).to_list(500)
    return {p["id"]: p["name"] for p in projs}


def _amount(qty, unit_price) -> int:
    return int(round(float(qty or 0) * int(unit_price or 0)))


@router.get("/items")
async def list_items(project_id: str = None, category: str = None, scope: str = None,
                     user: dict = Depends(require_permission("boq", "view"))):
    org = user.get("org_id", ORG_ID)
    pmap = await _accessible_project_ids(user)
    fq = {"org_id": org}
    if has_role(user, *PROJECT_SCOPED):
        fq["project_id"] = {"$in": list(pmap.keys())}
    if project_id:
        fq["project_id"] = project_id
    if category:
        fq["category"] = category
    if scope:  # Fase 80: item lama tanpa scope dianggap lingkup unit (legacy)
        fq["$or" if scope == "unit" else "scope"] = (
            [{"scope": "unit"}, {"scope": {"$exists": False}}, {"scope": None}] if scope == "unit" else scope)
    rows = await db.boq_items.find(fq, {"_id": 0}).sort([("cost_code", 1), ("created_at", 1)]).to_list(1000)
    for r in rows:
        r["project_name"] = pmap.get(r.get("project_id"), r.get("project_name"))
    total_budget = sum(int(r.get("amount", 0)) for r in rows)
    return {"data": serialize_doc(rows), "total": len(rows), "total_budget": total_budget}


async def _project_cost_summary(org: str, project_id: str, pname: str = None) -> dict:
    boq = await db.boq_items.find({"org_id": org, "project_id": project_id}, {"_id": 0}).to_list(2000)
    budget = sum(int(b.get("amount", 0)) for b in boq)
    # committed = approved / received / closed POs (not draft/cancelled)
    pos = await db.purchase_orders.find(
        {"org_id": org, "project_id": project_id,
         "status": {"$in": ["approved", "partially_received", "received", "closed"]}},
        {"_id": 0, "total": 1}).to_list(2000)
    committed = sum(int(p.get("total", 0)) for p in pos)
    # actual = AP bills for this project (net claimed)
    bills = await db.ap_invoices.find({"org_id": org, "project_id": project_id}, {"_id": 0, "claimed": 1}).to_list(2000)
    actual = sum(int(b.get("claimed", 0)) for b in bills)
    cats = {}
    for b in boq:
        c = b.get("category") or "umum"
        cats[c] = cats.get(c, 0) + int(b.get("amount", 0))
    return {
        "project_id": project_id, "project_name": pname, "items": len(boq),
        "budget": budget, "committed": committed, "actual": actual,
        "remaining": budget - committed, "over_budget": committed > budget and budget > 0,
        "categories": [{"category": k, "amount": v} for k, v in sorted(cats.items())],
    }


@router.get("/summary")
async def summary(project_id: str = None, user: dict = Depends(require_permission("boq", "view"))):
    org = user.get("org_id", ORG_ID)
    pmap = await _accessible_project_ids(user)
    if project_id:
        if project_id not in pmap and has_role(user, *PROJECT_SCOPED):
            raise HTTPException(status_code=403, detail="Akses ditolak untuk proyek ini")
        return {"data": await _project_cost_summary(org, project_id, pmap.get(project_id))}
    out = []
    for pid, pname in pmap.items():
        out.append(await _project_cost_summary(org, pid, pname))
    return {"data": out, "total": len(out)}


@router.get("/steps")
async def project_steps(project_id: str = None,
                       user: dict = Depends(require_permission("boq", "view"))):
    """Langkah jadwal NYATA pada proyek — untuk memetakan item RAB ke pekerjaan.

    Tanpa pemetaan ini, harga borongan per pekerjaan tidak punya acuan dan panel Kendali
    Biaya tidak bisa membandingkan anggaran dengan nilai yang dikontrakkan. Tanpa
    `project_id`, yang dikembalikan adalah langkah dari seluruh proyek yang boleh diakses.
    """
    org = user.get("org_id", ORG_ID)
    if project_id:
        await assert_project_access(project_id, user)
        return {"data": await op.project_steps(org, project_id)}
    pmap = await _accessible_project_ids(user)
    return {"data": await op.project_steps(org, list(pmap.keys()))}


@router.put("/items/{iid}/steps")
async def map_steps(iid: str, payload: BoQStepMapIn,
                    user: dict = Depends(require_permission("boq", "update"))):
    doc = await _get_item(iid, user)
    steps = await op.project_steps(doc["org_id"], doc["project_id"])
    valid = {s["step_code"] for s in steps}
    unknown = [c for c in payload.step_codes if c not in valid]
    if unknown:
        raise HTTPException(status_code=400, detail=(
            f"Langkah tidak dikenal pada proyek ini: {', '.join(unknown)}. Pilih dari daftar "
            "langkah jadwal yang benar-benar ada."))
    await db.boq_items.update_one({"id": iid, "org_id": doc["org_id"]}, {"$set": {
        "step_codes": list(dict.fromkeys(payload.step_codes)), "updated_at": now_iso()}})
    return {"data": serialize_doc(await db.boq_items.find_one({"id": iid}, {"_id": 0}))}


@router.get("/control")
async def cost_control(project_id: str = None,
                       user: dict = Depends(require_permission("boq", "view"))):
    """Kendali biaya: anggaran RAB vs dikontrakkan (lingkup SPK) vs terverifikasi vs ditagih."""
    org = user.get("org_id", ORG_ID)
    pmap = await _accessible_project_ids(user)
    if project_id:
        if project_id not in pmap and has_role(user, *PROJECT_SCOPED):
            raise HTTPException(status_code=403, detail="Akses ditolak untuk proyek ini")
        return {"data": await op.cost_control(org, project_id, pmap.get(project_id))}
    out = [await op.cost_control(org, pid, pname) for pid, pname in pmap.items()]
    return {"data": out, "total": len(out)}


@router.post("/items")
async def create_item(payload: BoQItemCreate,
                      user: dict = Depends(require_permission("boq", "create"))):
    proj = await assert_project_access(payload.project_id, user)
    org = user.get("org_id", ORG_ID)
    if payload.scope not in ("unit", "fasum", "umum"):
        raise HTTPException(status_code=400, detail="Lingkup RAB harus unit, fasum, atau umum.")
    if payload.scope == "fasum" and not payload.facility:
        raise HTTPException(status_code=400, detail="Item fasum/fasos wajib memilih fasilitas.")
    if payload.phase_id and not await db.construction_phases.find_one(
            {"org_id": org, "id": payload.phase_id, "project_id": payload.project_id}, {"_id": 0, "id": 1}):
        raise HTTPException(status_code=400, detail="Fase konstruksi tidak ditemukan pada proyek ini.")
    if payload.cost_code and await db.boq_items.find_one(
            {"org_id": org, "project_id": payload.project_id, "cost_code": payload.cost_code}, {"_id": 0, "id": 1}):
        raise HTTPException(status_code=409, detail=f"Kode biaya '{payload.cost_code}' sudah dipakai item RAB lain di proyek ini.")
    ts = now_iso()
    doc = {
        "id": new_id(), "org_id": org, "project_id": payload.project_id,
        "project_name": proj.get("name"), "cost_code": payload.cost_code,
        "category": payload.category or "umum", "description": payload.description,
        "uom": payload.uom, "quantity": float(payload.quantity or 0),
        "unit_price": int(payload.unit_price or 0),
        "amount": _amount(payload.quantity, payload.unit_price), "notes": payload.notes,
        "scope": payload.scope, "facility": payload.facility, "phase_id": payload.phase_id,
        "created_by": user.get("email"), "created_at": ts, "updated_at": ts,
    }
    await db.boq_items.insert_one(dict(doc))
    doc.pop("_id", None)
    return {"data": serialize_doc(doc)}


async def _get_item(iid: str, user: dict) -> dict:
    doc = await db.boq_items.find_one({"id": iid, "org_id": user.get("org_id", ORG_ID)}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Item BoQ tidak ditemukan")
    await assert_project_access(doc["project_id"], user)
    return doc


@router.put("/items/{iid}")
async def update_item(iid: str, payload: BoQItemUpdate,
                      user: dict = Depends(require_permission("boq", "update"))):
    doc = await _get_item(iid, user)
    upd = {k: v for k, v in payload.dict(exclude_unset=True).items() if v is not None}
    if "unit_price" in upd:
        upd["unit_price"] = int(upd["unit_price"])
    if "quantity" in upd:
        upd["quantity"] = float(upd["quantity"])
    qty = upd.get("quantity", doc.get("quantity"))
    price = upd.get("unit_price", doc.get("unit_price"))
    upd["amount"] = _amount(qty, price)
    upd["updated_at"] = now_iso()
    await db.boq_items.update_one({"id": iid, "org_id": doc["org_id"]}, {"$set": upd})
    return {"data": serialize_doc(await db.boq_items.find_one({"id": iid}, {"_id": 0}))}


@router.delete("/items/{iid}")
async def delete_item(iid: str, user: dict = Depends(require_permission("boq", "delete"))):
    doc = await _get_item(iid, user)
    await db.boq_items.delete_one({"id": iid, "org_id": doc["org_id"]})
    return {"data": {"deleted": True}}
