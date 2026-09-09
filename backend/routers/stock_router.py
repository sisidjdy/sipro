"""stock_router.py — transfer antar proyek, batas stok minimum, nilai persediaan (Fase 48E).

Rute (prefix `/materials`, dipakai tab baru di halaman Material & Opname):
  GET  /transfers                    riwayat transfer
  POST /transfers                    pindah material antar proyek (alasan wajib)
  GET  /stock-alerts                 peringatan stok minimum / habis / batas belum diatur
  PUT  /{material_id}/min-stock      tetapkan batas minimum
  GET  /valuation                    nilai persediaan (harga rata-rata bergerak)

SoD: transfer antar proyek MENGGESER nilai antar pusat biaya, jadi butuh `materials:approve`
(PM/owner) — mandor tidak boleh memindahkan barang antar proyek sendirian.
"""
from fastapi import APIRouter, Depends, HTTPException

import stock_control as sc
from db import db, ORG_ID
from core_utils import serialize_doc
from engine import add_activity
from models_p48 import MinStockIn, TransferIn
from rbac import has_role, require_permission, assert_project_access, project_query, audit_log

router = APIRouter(prefix="/materials", tags=["materials-48"])


async def _project_ids(user: dict) -> list:
    projs = await db.projects.find(project_query(user, {}), {"_id": 0, "id": 1}).to_list(500)
    return [p["id"] for p in projs]


@router.get("/transfers")
async def list_transfers(project_id: str = None,
                         user: dict = Depends(require_permission("materials", "view"))):
    org = user.get("org_id", ORG_ID)
    if project_id:
        await assert_project_access(project_id, user)
    rows = await sc.list_transfers(org, project_id)
    if not project_id and has_role(user, "project_manager", "site_engineer"):
        allowed = set(await _project_ids(user))
        rows = [r for r in rows
                if r.get("from_project_id") in allowed or r.get("to_project_id") in allowed]
    return {"data": serialize_doc(rows), "total": len(rows), "summary": {
        "total": len(rows),
        "value": sum(int(r.get("value") or 0) for r in rows),
        "unpriced": sum(1 for r in rows if r.get("value") is None),
    }}


@router.post("/transfers")
async def create_transfer(payload: TransferIn,
                          user: dict = Depends(require_permission("materials", "approve"))):
    org = user.get("org_id", ORG_ID)
    await assert_project_access(payload.from_project_id, user)
    await assert_project_access(payload.to_project_id, user)
    try:
        doc = await sc.transfer(org, payload.model_dump(), user.get("email"))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit_log(user, "create", "material_transfer", doc["id"], {
        "material": doc["material_name"], "qty": doc["qty"],
        "from": payload.from_project_id, "to": payload.to_project_id})
    for pid, arah in ((payload.from_project_id, "keluar"), (payload.to_project_id, "masuk")):
        await add_activity(entity_type="project", entity_id=pid, type="system",
                           body=(f"Transfer {doc['transfer_number']}: {doc['qty']:g} "
                                 f"{doc.get('uom')} {doc['material_name']} {arah}. "
                                 f"{payload.reason}"),
                           actor=user.get("email"), org_id=org)
    return {"data": serialize_doc(doc)}


@router.get("/stock-alerts")
async def stock_alerts(project_id: str = None, only_problem: bool = False,
                       user: dict = Depends(require_permission("materials", "view"))):
    org = user.get("org_id", ORG_ID)
    if project_id:
        await assert_project_access(project_id, user)
        pids = [project_id]
    else:
        pids = await _project_ids(user)
    out = await sc.alerts(org, pids, only_problem)
    return {"data": serialize_doc(out["rows"]), "total": len(out["rows"]),
            "summary": out["summary"]}


@router.get("/valuation")
async def valuation(project_id: str = None,
                    user: dict = Depends(require_permission("materials", "view"))):
    if not project_id:
        # Tanpa proyek, jawabannya keadaan jujur \u2014 bukan galat: nilai persediaan selalu
        # dihitung PER PROYEK karena stok memang milik gudang proyek.
        return {"data": [], "summary": {
            "materials": 0, "priced": 0, "unpriced": 0, "total_value": 0,
            "priced_share_pct": None, "state": "missing_data",
            "detail": "Pilih proyek untuk melihat nilai persediaannya."}}
    await assert_project_access(project_id, user)
    org = user.get("org_id", ORG_ID)
    out = await sc.valuation(org, project_id)
    return {"data": serialize_doc(out["rows"]), "summary": out["summary"]}


@router.put("/{material_id}/min-stock")
async def set_min_stock(material_id: str, payload: MinStockIn,
                        user: dict = Depends(require_permission("materials", "update"))):
    org = user.get("org_id", ORG_ID)
    mat = await db.materials.find_one({"id": material_id, "org_id": org}, {"_id": 0})
    if not mat:
        raise HTTPException(status_code=404, detail="Material tidak ditemukan.")
    await assert_project_access(mat["project_id"], user)
    try:
        doc = await sc.set_min_qty(org, material_id, payload.min_qty)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit_log(user, "update", "material_min_stock", material_id,
                    {"min_qty": payload.min_qty})
    return {"data": serialize_doc(doc)}
