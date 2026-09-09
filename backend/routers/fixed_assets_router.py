"""Aset Tetap + Penyusutan + Pelepasan (Fase 27). Akses: finance + owner/super_admin."""
from fastapi import APIRouter, Depends, HTTPException

import fixed_assets as fa
from core_utils import parse_pagination, serialize_doc
from db import db, ORG_ID
from models_p27 import AssetCreate, AssetDispose, DepreciationRun
from rbac import audit_log, require_permission

router = APIRouter(prefix="/fixed-assets", tags=["fixed-assets"])


@router.get("/assets")
async def list_assets(status: str = None, category: str = None, skip: int = 0, limit: int = 100,
                      user: dict = Depends(require_permission("fixed_assets", "view"))):
    skip, limit = parse_pagination(skip, limit)
    q = {"org_id": user.get("org_id", ORG_ID)}
    if status:
        q["status"] = status
    if category:
        q["category"] = category
    total = await db.fixed_assets.count_documents(q)
    rows = await db.fixed_assets.find(q, {"_id": 0}).sort("code", 1) \
        .skip(skip).limit(limit).to_list(limit)
    for r in rows:
        r["monthly_depreciation"] = fa.monthly_amount(r)
    return {"data": serialize_doc(rows), "total": total}


@router.get("/summary")
async def summary(user: dict = Depends(require_permission("fixed_assets", "view"))):
    return {"data": await fa.summary(user.get("org_id", ORG_ID))}


@router.get("/depreciations")
async def list_depreciations(period: str = None, asset_id: str = None, skip: int = 0,
                             limit: int = 100,
                             user: dict = Depends(require_permission("fixed_assets", "view"))):
    skip, limit = parse_pagination(skip, limit)
    q = {"org_id": user.get("org_id", ORG_ID)}
    if period:
        q["period"] = period
    if asset_id:
        q["asset_id"] = asset_id
    total = await db.asset_depreciations.count_documents(q)
    rows = await db.asset_depreciations.find(q, {"_id": 0}) \
        .sort([("period", -1), ("asset_code", 1)]).skip(skip).limit(limit).to_list(limit)
    periods = sorted(await db.asset_depreciations.distinct(
        "period", {"org_id": user.get("org_id", ORG_ID)}), reverse=True)
    return {"data": serialize_doc(rows), "total": total, "periods": periods,
            "amount_total": sum(int(r.get("amount", 0)) for r in rows)}


@router.get("/assets/{asset_id}")
async def detail(asset_id: str,
                 user: dict = Depends(require_permission("fixed_assets", "view"))):
    org = user.get("org_id", ORG_ID)
    doc = await db.fixed_assets.find_one({"id": asset_id, "org_id": org}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Aset tetap tidak ditemukan.")
    history = await db.asset_depreciations.find(
        {"org_id": org, "asset_id": asset_id}, {"_id": 0}).sort("period", -1).to_list(600)
    return {"data": serialize_doc(doc), "schedule": fa.schedule(doc),
            "history": serialize_doc(history),
            "monthly_depreciation": fa.monthly_amount(doc)}


@router.post("/assets")
async def create(payload: AssetCreate,
                 user: dict = Depends(require_permission("fixed_assets", "create"))):
    try:
        doc = await fa.create_asset(payload, user.get("email"), user.get("org_id", ORG_ID))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit_log(user, "create", "fixed_assets", doc["id"], {"cost": doc["cost"]})
    return {"data": serialize_doc(doc)}


@router.post("/depreciation/run")
async def run_depreciation(payload: DepreciationRun,
                           user: dict = Depends(require_permission("fixed_assets", "approve"))):
    try:
        res = await fa.run_depreciation(payload.period, user.get("email"),
                                        user.get("org_id", ORG_ID))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit_log(user, "run_depreciation", "fixed_assets", payload.period,
                    {"posted": res["posted"], "total": res["total_amount"]})
    return {"data": res}


@router.post("/assets/{asset_id}/dispose")
async def dispose(asset_id: str, payload: AssetDispose,
                  user: dict = Depends(require_permission("fixed_assets", "approve"))):
    try:
        doc = await fa.dispose_asset(asset_id, payload.proceeds, payload.source, payload.date,
                                     payload.note, user.get("email"), user.get("org_id", ORG_ID))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit_log(user, "dispose", "fixed_assets", asset_id,
                    {"proceeds": payload.proceeds, "gain_loss": doc.get("disposal_gain_loss")})
    return {"data": serialize_doc(doc)}
