"""Materials (Slice B) + EPIC 2.6 deepening (Phase 18).

Bagian dasar: ledger (GRN in / issue out) + book stock + stock opname (variance).
Phase 18 menambah:
  - **Requisition (Permintaan Material)**: SoD — site MENGAJUKAN, PM MENYETUJUI,
    lalu material DIKELUARKAN (issue) tertaut ke requisition + fase/tugas.
  - **Issue-to-task**: transaksi `out` menyimpan requisition_id/phase_id/task_id.
  - **Anggaran (RAB) vs pemakaian**: material bisa ditaut ke item BoQ + budget_qty;
    saat pemakaian (out kumulatif) melampaui RAB -> flag `over_budget` + tugas urgent
    + notifikasi ke PM (idempotent) + event `material.overbudget`.
"""
from fastapi import APIRouter, Depends, HTTPException

import sequences as seq
from models_master import MaterialUpdate
from rbac import has_role, audit_log
from db import db, ORG_ID
from core_utils import new_id, now_iso, serialize_doc, due_in
from rbac import require_permission, assert_project_access, project_query
from engine import (add_activity, material_book_stock, auto_create_task,
                    create_notification, emit)
from models import (MaterialCreate, MaterialTxn, OpnameCreate,
                    RequisitionCreate, RequisitionIssue, MaterialBudgetSet)

router = APIRouter(prefix="/materials", tags=["materials"])
REQ_OPEN = ("submitted", "approved", "partially_issued")
REQ_STATUS = ("submitted", "approved", "partially_issued", "issued", "rejected")


# ------------------------------ helpers ------------------------------
async def _consumed_qty(project_id: str, material_id: str, org: str) -> float:
    txns = await db.material_txns.find(
        {"org_id": org, "project_id": project_id, "material_id": material_id, "type": "out"},
        {"_id": 0, "qty": 1}).to_list(5000)
    return round(sum(t.get("qty", 0) for t in txns), 2)


async def _pm_of_project(project_id: str, org: str):
    proj = await db.projects.find_one({"id": project_id, "org_id": org}, {"_id": 0}) or {}
    members = proj.get("members") or []
    if not members:
        return None
    u = await db.users.find_one(
        {"org_id": org, "email": {"$in": members}, "role": "project_manager"}, {"_id": 0, "email": 1})
    return u["email"] if u else members[0]


async def _check_material_budget(project_id: str, material_id: str, org: str, actor: str = "system"):
    """Recompute consumed vs RAB; raise alert (idempotent) when over budget."""
    mat = await db.materials.find_one({"id": material_id, "org_id": org}, {"_id": 0})
    if not mat:
        return None
    budget = float(mat.get("budget_qty") or 0)
    consumed = await _consumed_qty(project_id, material_id, org)
    over = budget > 0 and consumed > budget
    await db.materials.update_one(
        {"id": material_id, "org_id": org},
        {"$set": {"over_budget": bool(over), "consumed_qty": consumed, "updated_at": now_iso()}})
    if over:
        pm = await _pm_of_project(project_id, org)
        uom = mat.get("uom")
        await auto_create_task(
            source_event=f"material.overbudget:{material_id}", jobdesk_code="TK-06",
            title=f"Pemakaian {mat.get('name')} melebihi RAB ({consumed:g}/{budget:g} {uom})",
            type="review", related_entity_type="project", related_entity_id=project_id,
            assigned_to=pm, due_date=due_in(days=2), sla_due_at=due_in(days=2),
            priority="urgent", org_id=org,
            description=(f"Material {mat.get('code')} {mat.get('name')} terpakai {consumed:g} {uom} "
                         f"melampaui anggaran RAB {budget:g} {uom}."))
        await create_notification(
            user_email=pm, title="Material melebihi RAB",
            body=f"{mat.get('name')}: {consumed:g}/{budget:g} {uom}", type="material",
            related_entity_type="project", related_entity_id=project_id, org_id=org)
        await emit("material.overbudget", "project", project_id,
                   {"material_id": material_id, "consumed": consumed, "budget": budget}, org_id=org)
        await add_activity(entity_type="project", entity_id=project_id, type="system",
                           body=f"Material {mat.get('name')} melebihi RAB: {consumed:g}/{budget:g} {uom}.",
                           actor=actor, org_id=org)
    return over


# ------------------------------ materials + ledger ------------------------------
@router.get("/project/{project_id}")
async def list_materials(project_id: str, user: dict = Depends(require_permission("materials", "view"))):
    await assert_project_access(project_id, user)
    org = user.get("org_id", ORG_ID)
    mats = await db.materials.find({"org_id": org, "project_id": project_id}, {"_id": 0}).sort("code", 1).to_list(500)
    for m in mats:
        m["stock"] = await material_book_stock(project_id, m["id"], org)
        last = await db.material_txns.find_one(
            {"org_id": org, "project_id": project_id, "material_id": m["id"], "type": "adjust"},
            {"_id": 0}, sort=[("created_at", -1)])
        m["last_opname"] = last.get("created_at") if last else None
    return {"data": serialize_doc(mats), "total": len(mats)}


@router.get("/project/{project_id}/txns")
async def list_txns(project_id: str, user: dict = Depends(require_permission("materials", "view"))):
    await assert_project_access(project_id, user)
    org = user.get("org_id", ORG_ID)
    txns = await db.material_txns.find({"org_id": org, "project_id": project_id}, {"_id": 0}).sort("created_at", -1).limit(200).to_list(200)
    mats = await db.materials.find({"org_id": org, "project_id": project_id}, {"_id": 0, "id": 1, "name": 1, "uom": 1}).to_list(500)
    mm = {m["id"]: m for m in mats}
    for t in txns:
        m = mm.get(t.get("material_id"), {})
        t["material_name"] = m.get("name")
        t["uom"] = m.get("uom")
    return {"data": serialize_doc(txns), "total": len(txns)}


@router.get("/project/{project_id}/budget")
async def project_budget(project_id: str, user: dict = Depends(require_permission("materials", "view"))):
    """Anggaran material (RAB) vs pemakaian kumulatif per material."""
    await assert_project_access(project_id, user)
    org = user.get("org_id", ORG_ID)
    mats = await db.materials.find({"org_id": org, "project_id": project_id}, {"_id": 0}).sort("code", 1).to_list(500)
    boq = {b["id"]: b for b in await db.boq_items.find(
        {"org_id": org, "project_id": project_id}, {"_id": 0, "id": 1, "cost_code": 1, "description": 1}).to_list(1000)}
    rows = []
    over = 0
    for m in mats:
        budget = float(m.get("budget_qty") or 0)
        consumed = await _consumed_qty(project_id, m["id"], org)
        is_over = budget > 0 and consumed > budget
        if is_over:
            over += 1
        link = boq.get(m.get("boq_item_id")) if m.get("boq_item_id") else None
        rows.append({
            "material_id": m["id"], "code": m["code"], "name": m["name"], "uom": m["uom"],
            "budget_qty": budget, "consumed_qty": consumed,
            "remaining_qty": round(budget - consumed, 2), "over_budget": is_over,
            "pct": round(consumed / budget * 100) if budget > 0 else None,
            "boq_item_id": m.get("boq_item_id"),
            "boq_cost_code": link.get("cost_code") if link else None,
            "boq_description": link.get("description") if link else None,
        })
    summary = {"materials": len(rows), "tracked": sum(1 for r in rows if r["budget_qty"] > 0), "over_budget": over}
    return {"data": rows, "total": len(rows), "summary": summary}


@router.post("")
async def create_material(payload: MaterialCreate, user: dict = Depends(require_permission("materials", "create"))):
    await assert_project_access(payload.project_id, user)
    org = user.get("org_id", ORG_ID)
    import numbering as nb
    code = payload.code or await nb.generate_unique(
        "master:material", org, "materials", {"org_id": org, "project_id": payload.project_id},
        context={"project_id": payload.project_id})
    if await db.materials.find_one({"org_id": org, "project_id": payload.project_id, "code": code}):
        raise HTTPException(status_code=400, detail="Kode material sudah ada di proyek ini")
    ts = now_iso()
    mat = {"id": new_id(), "org_id": org, "project_id": payload.project_id, "code": code,
           "name": payload.name, "uom": payload.uom,
           "boq_item_id": payload.boq_item_id, "budget_qty": float(payload.budget_qty or 0),
           "consumed_qty": 0.0, "over_budget": False,
           "created_at": ts, "created_by": user.get("email"), "updated_at": ts}
    await db.materials.insert_one(mat)
    mat.pop("_id", None)
    mat["stock"] = 0
    return {"data": serialize_doc(mat)}


@router.put("/{material_id}/budget")
async def set_material_budget(material_id: str, payload: MaterialBudgetSet,
                             user: dict = Depends(require_permission("materials", "update"))):
    org = user.get("org_id", ORG_ID)
    mat = await db.materials.find_one({"id": material_id, "org_id": org}, {"_id": 0})
    if not mat:
        raise HTTPException(status_code=404, detail="Material tidak ditemukan")
    await assert_project_access(mat["project_id"], user)
    if payload.boq_item_id:
        b = await db.boq_items.find_one({"id": payload.boq_item_id, "org_id": org}, {"_id": 0, "id": 1})
        if not b:
            raise HTTPException(status_code=404, detail="Item BoQ tidak ditemukan")
    await db.materials.update_one({"id": material_id, "org_id": org}, {"$set": {
        "boq_item_id": payload.boq_item_id, "budget_qty": float(payload.budget_qty or 0),
        "updated_at": now_iso()}})
    await _check_material_budget(mat["project_id"], material_id, org, user.get("email"))
    return {"data": serialize_doc(await db.materials.find_one({"id": material_id}, {"_id": 0}))}


@router.post("/txn")
async def create_txn(payload: MaterialTxn, user: dict = Depends(require_permission("materials", "update"))):
    await assert_project_access(payload.project_id, user)
    org = user.get("org_id", ORG_ID)
    if payload.qty <= 0:
        raise HTTPException(status_code=400, detail="Qty harus > 0")
    mat = await db.materials.find_one({"id": payload.material_id, "org_id": org}, {"_id": 0})
    if not mat:
        raise HTTPException(status_code=404, detail="Material tidak ditemukan")
    if payload.type == "out":
        stock = await material_book_stock(payload.project_id, payload.material_id, org)
        if payload.qty > stock:
            raise HTTPException(status_code=400, detail=f"Stok tidak cukup (tersedia {stock} {mat.get('uom')})")
    ts = now_iso()
    txn = {"id": new_id(), "org_id": org, "project_id": payload.project_id, "material_id": payload.material_id,
           "type": payload.type, "qty": payload.qty, "note": payload.note, "ref": payload.ref,
           "requisition_id": None, "phase_id": None, "task_id": None,
           "actor": user.get("email"), "created_at": ts}
    await db.material_txns.insert_one(txn)
    if payload.type == "out":
        await _check_material_budget(payload.project_id, payload.material_id, org, user.get("email"))
    stock = await material_book_stock(payload.project_id, payload.material_id, org)
    txn.pop("_id", None)
    return {"data": serialize_doc(txn), "stock": stock}


@router.post("/opname")
async def stock_opname(payload: OpnameCreate, user: dict = Depends(require_permission("materials", "update"))):
    await assert_project_access(payload.project_id, user)
    org = user.get("org_id", ORG_ID)
    mat = await db.materials.find_one({"id": payload.material_id, "org_id": org}, {"_id": 0})
    if not mat:
        raise HTTPException(status_code=404, detail="Material tidak ditemukan")
    book = await material_book_stock(payload.project_id, payload.material_id, org)
    variance = round(payload.physical_qty - book, 2)
    ts = now_iso()
    await db.material_txns.insert_one({
        "id": new_id(), "org_id": org, "project_id": payload.project_id, "material_id": payload.material_id,
        "type": "adjust", "qty": variance, "note": (payload.note or "Stock opname"),
        "ref": "OPNAME", "book_qty": book, "physical_qty": payload.physical_qty,
        "actor": user.get("email"), "created_at": ts})
    await add_activity(entity_type="project", entity_id=payload.project_id, type="system",
                       body=f"Opname {mat.get('name')}: buku {book}, fisik {payload.physical_qty}, selisih {variance} {mat.get('uom')}.",
                       actor=user.get("email"), org_id=org)
    return {"data": {"material_id": payload.material_id, "book_qty": book,
                     "physical_qty": payload.physical_qty, "variance": variance,
                     "new_stock": payload.physical_qty}}


# ------------------------------ requisitions (EPIC 2.6) ------------------------------
async def _req_number(org: str, project_id: str = None) -> str:
    """Nomor atomik (dulu count_documents+1 -> bisa duplikat)."""
    return await seq.next_number("requisition", org, prefix="PR", context={"project_id": project_id})


async def _get_req(org: str, rid: str, user: dict) -> dict:
    req = await db.material_requisitions.find_one({"id": rid, "org_id": org}, {"_id": 0})
    if not req:
        raise HTTPException(status_code=404, detail="Permintaan material tidak ditemukan")
    await assert_project_access(req["project_id"], user)
    return req


def _req_summary(rows):
    return {
        "total": len(rows),
        "submitted": sum(1 for r in rows if r.get("status") == "submitted"),
        "approved": sum(1 for r in rows if r.get("status") in ("approved", "partially_issued")),
        "issued": sum(1 for r in rows if r.get("status") == "issued"),
    }


@router.get("/requisitions")
async def list_requisitions(project_id: str = None, status: str = None,
                            user: dict = Depends(require_permission("materials", "view"))):
    org = user.get("org_id", ORG_ID)
    q = {"org_id": org}
    if has_role(user, "project_manager", "site_engineer"):
        projs = await db.projects.find(project_query(user, {}), {"_id": 0, "id": 1}).to_list(500)
        q["project_id"] = {"$in": [p["id"] for p in projs]}
    if project_id:
        await assert_project_access(project_id, user)
        q["project_id"] = project_id
    if status:
        q["status"] = status
    rows = await db.material_requisitions.find(q, {"_id": 0}).sort("created_at", -1).to_list(500)
    return {"data": serialize_doc(rows), "total": len(rows), "summary": _req_summary(rows)}


@router.post("/requisitions")
async def create_requisition(payload: RequisitionCreate,
                             user: dict = Depends(require_permission("materials", "create"))):
    proj = await assert_project_access(payload.project_id, user)
    org = user.get("org_id", ORG_ID)
    if not payload.items:
        raise HTTPException(status_code=400, detail="Permintaan butuh minimal 1 item material.")
    items = []
    for it in payload.items:
        if it.qty <= 0:
            raise HTTPException(status_code=400, detail="Jumlah setiap item harus > 0.")
        mat = await db.materials.find_one(
            {"id": it.material_id, "org_id": org, "project_id": payload.project_id}, {"_id": 0})
        if not mat:
            raise HTTPException(status_code=404, detail="Material tidak ditemukan di proyek ini.")
        items.append({"material_id": mat["id"], "code": mat["code"], "name": mat["name"],
                      "uom": mat["uom"], "qty_requested": float(it.qty), "qty_issued": 0.0})
    phase_name = None
    if payload.phase_id:
        ph = await db.construction_phases.find_one(
            {"id": payload.phase_id, "org_id": org, "project_id": payload.project_id}, {"_id": 0, "name": 1})
        phase_name = ph.get("name") if ph else None
    ts = now_iso()
    doc = {
        "id": new_id(), "org_id": org, "req_number": await _req_number(org, payload.project_id),
        "project_id": payload.project_id, "project_name": proj.get("name"),
        "phase_id": payload.phase_id, "phase_name": phase_name, "task_id": payload.task_id,
        "purpose": payload.purpose, "items": items, "status": "submitted",
        "requested_by": user.get("email"), "approved_by": None, "approved_at": None,
        "issued_by": None, "issued_at": None, "rejected_by": None, "rejected_at": None,
        "note": payload.note, "created_at": ts, "updated_at": ts,
    }
    await db.material_requisitions.insert_one(dict(doc))
    await add_activity(entity_type="project", entity_id=payload.project_id, type="system",
                       body=f"Permintaan material {doc['req_number']} diajukan ({len(items)} item).",
                       actor=user.get("email"), org_id=org)
    doc.pop("_id", None)
    return {"data": serialize_doc(doc)}


@router.get("/requisitions/{rid}")
async def get_requisition(rid: str, user: dict = Depends(require_permission("materials", "view"))):
    return {"data": serialize_doc(await _get_req(user.get("org_id", ORG_ID), rid, user))}


@router.post("/requisitions/{rid}/approve")
async def approve_requisition(rid: str, user: dict = Depends(require_permission("materials", "approve"))):
    org = user.get("org_id", ORG_ID)
    req = await _get_req(org, rid, user)
    if req.get("status") != "submitted":
        raise HTTPException(status_code=400, detail="Hanya permintaan berstatus 'diajukan' yang bisa disetujui.")
    ts = now_iso()
    await db.material_requisitions.update_one({"id": rid, "org_id": org}, {"$set": {
        "status": "approved", "approved_by": user.get("email"), "approved_at": ts, "updated_at": ts}})
    await create_notification(user_email=req.get("requested_by"), title="Permintaan material disetujui",
                              body=f"{req.get('req_number')} disetujui, siap dikeluarkan.", type="material",
                              related_entity_type="project", related_entity_id=req["project_id"], org_id=org)
    return {"data": serialize_doc(await db.material_requisitions.find_one({"id": rid}, {"_id": 0}))}


@router.post("/requisitions/{rid}/reject")
async def reject_requisition(rid: str, payload: RequisitionIssue,
                             user: dict = Depends(require_permission("materials", "approve"))):
    org = user.get("org_id", ORG_ID)
    req = await _get_req(org, rid, user)
    if req.get("status") not in ("submitted", "approved"):
        raise HTTPException(status_code=400, detail="Permintaan ini tidak bisa ditolak.")
    ts = now_iso()
    setter = {"status": "rejected", "rejected_by": user.get("email"), "rejected_at": ts, "updated_at": ts}
    if payload.note:
        setter["note"] = ((req.get("note") or "") + f"\n[tolak {ts[:10]}] {payload.note}").strip()
    await db.material_requisitions.update_one({"id": rid, "org_id": org}, {"$set": setter})
    return {"data": serialize_doc(await db.material_requisitions.find_one({"id": rid}, {"_id": 0}))}


@router.post("/requisitions/{rid}/issue")
async def issue_requisition(rid: str, payload: RequisitionIssue,
                            user: dict = Depends(require_permission("materials", "update"))):
    org = user.get("org_id", ORG_ID)
    req = await _get_req(org, rid, user)
    if req.get("status") not in ("approved", "partially_issued"):
        raise HTTPException(status_code=400, detail="Hanya permintaan disetujui yang bisa dikeluarkan.")
    override = {i.material_id: float(i.qty) for i in (payload.items or [])}
    ts = now_iso()
    items = req["items"]
    affected, issued_any = set(), False
    for it in items:
        remaining = round(float(it["qty_requested"]) - float(it.get("qty_issued", 0)), 2)
        if remaining <= 0:
            continue
        qty = override.get(it["material_id"], remaining) if override else remaining
        qty = round(min(qty, remaining), 2)
        if qty <= 0:
            continue
        stock = await material_book_stock(req["project_id"], it["material_id"], org)
        if qty > stock:
            raise HTTPException(status_code=400,
                                detail=f"Stok {it['name']} tidak cukup (tersedia {stock} {it['uom']})")
        await db.material_txns.insert_one({
            "id": new_id(), "org_id": org, "project_id": req["project_id"], "material_id": it["material_id"],
            "type": "out", "qty": qty, "note": (payload.note or f"Pengeluaran {req['req_number']}"),
            "ref": req["req_number"], "requisition_id": rid, "phase_id": req.get("phase_id"),
            "task_id": req.get("task_id"), "actor": user.get("email"), "created_at": ts})
        it["qty_issued"] = round(float(it.get("qty_issued", 0)) + qty, 2)
        affected.add(it["material_id"])
        issued_any = True
    if not issued_any:
        raise HTTPException(status_code=400, detail="Tidak ada item yang bisa dikeluarkan.")
    fully = all(float(it.get("qty_issued", 0)) >= float(it["qty_requested"]) for it in items)
    new_status = "issued" if fully else "partially_issued"
    await db.material_requisitions.update_one({"id": rid, "org_id": org}, {"$set": {
        "items": items, "status": new_status, "issued_by": user.get("email"),
        "issued_at": ts, "updated_at": ts}})
    alerts = 0
    for mid in affected:
        if await _check_material_budget(req["project_id"], mid, org, user.get("email")):
            alerts += 1
    await add_activity(entity_type="project", entity_id=req["project_id"], type="system",
                       body=f"Material dikeluarkan untuk {req['req_number']} ({len(affected)} item).",
                       actor=user.get("email"), org_id=org)
    return {"data": serialize_doc(await db.material_requisitions.find_one({"id": rid}, {"_id": 0})),
            "over_budget_materials": alerts}


@router.put("/{material_id}")
async def update_material(material_id: str, payload: MaterialUpdate,
                          user: dict = Depends(require_permission("materials", "update"))):
    """Koreksi nama/satuan material + arsip (sebelumnya master material tak bisa diubah)."""
    org = user.get("org_id", ORG_ID)
    mat = await db.materials.find_one({"id": material_id, "org_id": org}, {"_id": 0})
    if not mat:
        raise HTTPException(status_code=404, detail="Material tidak ditemukan")
    await assert_project_access(mat["project_id"], user)
    upd = {k: v for k, v in payload.model_dump(exclude_unset=True).items() if v is not None}
    if not upd:
        return {"data": serialize_doc(mat)}
    if upd.get("is_active") is False:
        moved = await db.material_txns.count_documents({"org_id": org, "material_id": material_id})
        if moved:
            raise HTTPException(status_code=400, detail=(
                f"Material tidak bisa diarsipkan: sudah ada {moved} transaksi stok. "
                "Ubah nama/satuan saja agar riwayat tetap konsisten."))
    upd["updated_at"] = now_iso()
    await db.materials.update_one({"id": material_id, "org_id": org}, {"$set": upd})
    await audit_log(user, "update", "materials", material_id, {"fields": sorted(upd)})
    return {"data": serialize_doc(await db.materials.find_one({"id": material_id}, {"_id": 0}))}
