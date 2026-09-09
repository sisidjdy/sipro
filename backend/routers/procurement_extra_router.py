"""procurement_extra_router.py — retur barang & permintaan→PO (Fase 48B).

Rute (menempel pada prefix `/procurement` & `/materials` yang sudah ada):
  GET  /api/procurement/returns                        daftar retur
  POST /api/procurement/returns                        retur barang (alasan wajib)
  GET  /api/materials/requisitions/{rid}/shortage      kekurangan yang perlu dibeli
  POST /api/materials/requisitions/{rid}/to-po         buat PO dari kekurangan (idempoten)

SoD: lapangan/PM MENCATAT retur & mengusulkan PO (`procurement:create`); persetujuan PO tetap
lewat `POST /procurement/pos/{id}/approve` milik finance/owner. Retur tidak boleh membuat
nilai diterima jatuh di bawah nilai yang sudah ditagih (dijaga `procurement_extra`).
"""
from fastapi import APIRouter, Depends, HTTPException

import procurement_extra as pe
import vendor_engine as ve
from db import db, ORG_ID
from core_utils import serialize_doc
from engine import add_activity, create_notification
from models_p48 import ReqToPoIn, ReturnIn
from rbac import has_role, require_permission, assert_project_access, project_query, audit_log

router = APIRouter(tags=["procurement-48"])


async def _project_ids(user: dict) -> list:
    projs = await db.projects.find(project_query(user, {}), {"_id": 0, "id": 1}).to_list(500)
    return [p["id"] for p in projs]


@router.get("/procurement/returns")
async def list_returns(po_id: str = None, project_id: str = None,
                       user: dict = Depends(require_permission("procurement", "view"))):
    org = user.get("org_id", ORG_ID)
    if project_id:
        await assert_project_access(project_id, user)
    rows = await pe.list_returns(org, po_id=po_id, project_id=project_id)
    if not project_id and has_role(user, "project_manager", "site_engineer"):
        allowed = set(await _project_ids(user))
        rows = [r for r in rows if r.get("project_id") in allowed]
    return {"data": serialize_doc(rows), "total": len(rows), "summary": {
        "total": len(rows),
        "value": sum(int(r.get("returned_value", 0)) for r in rows),
    }}


@router.post("/procurement/returns")
async def create_return(payload: ReturnIn,
                        user: dict = Depends(require_permission("procurement", "create"))):
    org = user.get("org_id", ORG_ID)
    grn = await db.grns.find_one({"id": payload.grn_id, "org_id": org}, {"_id": 0})
    if not grn:
        raise HTTPException(status_code=404, detail="Penerimaan barang (GRN) tidak ditemukan.")
    po = await db.purchase_orders.find_one({"id": grn["po_id"], "org_id": org}, {"_id": 0})
    if not po:
        raise HTTPException(status_code=404, detail="PO penerimaan ini tidak ditemukan.")
    await assert_project_access(po["project_id"], user)
    try:
        doc = await pe.create_return(org, grn, po, payload.kind,
                                     payload.items, payload.reason, user.get("email"))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit_log(user, "create", "grn_return", doc["id"], {
        "grn": grn.get("grn_number"), "value": doc["returned_value"], "kind": payload.kind})
    await add_activity(entity_type="project", entity_id=po["project_id"], type="system",
                       body=(f"Retur {doc['return_number']} ke {po.get('vendor')}: "
                             f"Rp {doc['returned_value']:,} ({payload.kind}). {payload.reason}"),
                       actor=user.get("email"), org_id=org)
    await create_notification(
        user_email=po.get("created_by"), title="Barang diretur ke vendor",
        body=(f"{doc['return_number']} atas {grn.get('grn_number')} — "
              f"Rp {doc['returned_value']:,}. Nilai barang diterima PO {po.get('po_number')} "
              "ikut turun."),
        type="procurement", related_entity_type="project",
        related_entity_id=po["project_id"], org_id=org)
    fresh = await db.purchase_orders.find_one({"id": po["id"]}, {"_id": 0})
    return {"data": serialize_doc(doc), "po": serialize_doc(fresh)}


@router.get("/materials/requisitions/{rid}/shortage")
async def requisition_shortage(rid: str,
                               user: dict = Depends(require_permission("materials", "view"))):
    org = user.get("org_id", ORG_ID)
    req = await db.material_requisitions.find_one({"id": rid, "org_id": org}, {"_id": 0})
    if not req:
        raise HTTPException(status_code=404, detail="Permintaan material tidak ditemukan.")
    await assert_project_access(req["project_id"], user)
    data = await pe.shortage(org, req)
    # Harga acuan per item supaya layar bisa mengusulkan harga (tanpa mengarang).
    for row in data["rows"]:
        if row["shortage"] > 0:
            ref = await ve.reference_price(org, row["material_id"])
            row["reference_price"] = ref.get("unit_price")
            row["reference_basis"] = ref.get("basis")
    return {"data": data, "requisition": serialize_doc(req)}


@router.post("/materials/requisitions/{rid}/to-po")
async def requisition_to_po(rid: str, payload: ReqToPoIn,
                            user: dict = Depends(require_permission("procurement", "create"))):
    org = user.get("org_id", ORG_ID)
    req = await db.material_requisitions.find_one({"id": rid, "org_id": org}, {"_id": 0})
    if not req:
        raise HTTPException(status_code=404, detail="Permintaan material tidak ditemukan.")
    await assert_project_access(req["project_id"], user)
    vendor = await ve.get_vendor(org, payload.vendor_id)
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor tidak ditemukan — daftarkan vendor "
                                                   "dulu di Vendor & Harga.")
    if not vendor.get("is_active", True):
        raise HTTPException(status_code=400, detail="Vendor ini sudah tidak aktif.")
    items = [i.model_dump() for i in (payload.items or [])] or None
    if items:
        for it in items:
            if not it.get("unit_price"):
                ref = await ve.reference_price(org, it["material_id"], vendor["id"])
                it["unit_price"] = ref.get("unit_price")
    try:
        out = await pe.to_po(org, req, vendor, items, due_date=payload.due_date,
                            note=payload.note, actor=user.get("email"),
                            price_checker=ve.price_check)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    po = out["po"]
    await audit_log(user, "create", "purchase_order", po["id"], {
        "po": po["po_number"], "from_requisition": req.get("req_number"), "total": po["total"]})
    await add_activity(entity_type="project", entity_id=req["project_id"], type="system",
                       body=(f"PO {po['po_number']} dibuat dari permintaan "
                             f"{req.get('req_number')} ke {vendor.get('name')} "
                             f"(Rp {po['total']:,}) — menunggu persetujuan."),
                       actor=user.get("email"), org_id=org)
    return {"data": serialize_doc(po), "price_checks": serialize_doc(out["price_checks"])}
