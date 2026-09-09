"""Finance config + dashboard summary (Slice Finance).

Routes: /finance/summary, /finance/config/tax (GET/PUT),
/finance/config/payment-schemes (GET/POST/DELETE),
/finance/config/commission-schemes (GET/POST/DELETE).
"""
from fastapi import APIRouter, Depends, HTTPException

from db import db, ORG_ID
from core_utils import new_id, now_iso, serialize_doc
from rbac import require_permission
import finance_engine as fe
import finance_reports as fr
from models_master import SchemeUpdate
from denorm import cascade_master_change
from rbac import audit_log
from models import TaxConfigUpdate, PaymentSchemeCreate, CommissionSchemeCreate, CollectionConfigUpdate

router = APIRouter(prefix="/finance", tags=["finance"])


@router.get("/summary")
async def summary(user: dict = Depends(require_permission("finance", "view"))):
    return {"data": await fe.finance_summary(user.get("org_id", ORG_ID))}


@router.get("/drilldown/{key}")
async def drilldown(key: str, bucket: str = None,
                    user: dict = Depends(require_permission("finance", "view"))):
    """Baris-baris penyusun satu angka KPI dashboard + tautan ke tabel terfilter (Fase 91)."""
    import finance_drilldown as fd
    try:
        return {"data": await fd.drilldown(user.get("org_id", ORG_ID), key, bucket)}
    except KeyError:
        raise HTTPException(status_code=404, detail="Kunci KPI tidak dikenal.")


@router.get("/config/tax")
async def get_tax(user: dict = Depends(require_permission("finance", "view"))):
    return {"data": serialize_doc(await fe.get_finance_config(user.get("org_id", ORG_ID)))}


@router.put("/config/tax")
async def put_tax(payload: TaxConfigUpdate,
                  user: dict = Depends(require_permission("finance", "update"))):
    org = user.get("org_id", ORG_ID)
    doc = await fe.set_finance_config(org, payload.ppn_rate, payload.bphtb_rate,
                                      payload.pph_rate, payload.npoptkp)
    return {"data": serialize_doc(doc)}


@router.get("/config/payment-schemes")
async def list_payment_schemes(user: dict = Depends(require_permission("finance", "view"))):
    org = user.get("org_id", ORG_ID)
    rows = await db.payment_schemes.find({"org_id": org}, {"_id": 0}).sort("created_at", 1).to_list(200)
    return {"data": serialize_doc(rows), "total": len(rows)}


@router.post("/config/payment-schemes")
async def create_payment_scheme(payload: PaymentSchemeCreate,
                                user: dict = Depends(require_permission("finance", "create"))):
    org = user.get("org_id", ORG_ID)
    ts = now_iso()
    if payload.is_default:
        await db.payment_schemes.update_many({"org_id": org}, {"$set": {"is_default": False}})
    doc = {"id": new_id(), "org_id": org, "name": payload.name,
           "items": [i.model_dump() for i in payload.items],
           "is_default": payload.is_default, "created_by": user.get("email"), "created_at": ts}
    await db.payment_schemes.insert_one(doc)
    doc.pop("_id", None)
    return {"data": serialize_doc(doc)}


@router.delete("/config/payment-schemes/{scheme_id}")
async def delete_payment_scheme(scheme_id: str,
                                user: dict = Depends(require_permission("finance", "update"))):
    res = await db.payment_schemes.delete_one({"id": scheme_id, "org_id": user.get("org_id", ORG_ID)})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Skema pembayaran tidak ditemukan")
    return {"message": "Skema pembayaran dihapus"}


@router.get("/config/commission-schemes")
async def list_commission_schemes(user: dict = Depends(require_permission("finance", "view"))):
    org = user.get("org_id", ORG_ID)
    rows = await db.commission_schemes.find({"org_id": org}, {"_id": 0}).sort("created_at", 1).to_list(200)
    return {"data": serialize_doc(rows), "total": len(rows)}


@router.post("/config/commission-schemes")
async def create_commission_scheme(payload: CommissionSchemeCreate,
                                   user: dict = Depends(require_permission("finance", "create"))):
    org = user.get("org_id", ORG_ID)
    ts = now_iso()
    if payload.is_default:
        await db.commission_schemes.update_many({"org_id": org}, {"$set": {"is_default": False}})
    doc = {"id": new_id(), "org_id": org, "name": payload.name, "basis": payload.basis,
           "trigger": payload.trigger, "tiers": [t.model_dump() for t in payload.tiers],
           "is_default": payload.is_default, "created_by": user.get("email"), "created_at": ts}
    await db.commission_schemes.insert_one(doc)
    doc.pop("_id", None)
    return {"data": serialize_doc(doc)}


@router.delete("/config/commission-schemes/{scheme_id}")
async def delete_commission_scheme(scheme_id: str,
                                   user: dict = Depends(require_permission("finance", "update"))):
    res = await db.commission_schemes.delete_one({"id": scheme_id, "org_id": user.get("org_id", ORG_ID)})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Skema komisi tidak ditemukan")
    return {"message": "Skema komisi dihapus"}


# ----------------------------- Collection config (denda / masa tenggang) -----------------------------
@router.get("/config/collection")
async def get_collection_cfg(user: dict = Depends(require_permission("finance", "view"))):
    return {"data": serialize_doc(await fr.get_collection_config(user.get("org_id", ORG_ID)))}


@router.put("/config/collection")
async def put_collection_cfg(payload: CollectionConfigUpdate,
                             user: dict = Depends(require_permission("finance", "update"))):
    doc = await fr.set_collection_config(user.get("org_id", ORG_ID),
                                         payload.denda_rate_pct_month, payload.grace_days)
    return {"data": serialize_doc(doc)}


async def _scheme_usage(coll: str, scheme_id: str, org: str) -> int:
    field_map = {"payment_schemes": ("ar_invoices", "scheme_id"),
                 "commission_schemes": ("commissions", "scheme_id")}
    child, field = field_map[coll]
    return await db[child].count_documents({"org_id": org, field: scheme_id})


async def _update_scheme(coll: str, scheme_id: str, payload: SchemeUpdate, user: dict,
                         items_field: str):
    org = user.get("org_id", ORG_ID)
    cur = await db[coll].find_one({"id": scheme_id, "org_id": org}, {"_id": 0})
    if not cur:
        raise HTTPException(status_code=404, detail="Skema tidak ditemukan.")
    data = payload.model_dump(exclude_unset=True)
    upd = {}
    if data.get("name"):
        dup = await db[coll].find_one({"org_id": org, "name": data["name"], "id": {"$ne": scheme_id}})
        if dup:
            raise HTTPException(status_code=409, detail="Nama skema sudah dipakai.")
        upd["name"] = data["name"]
    if data.get("is_default") is not None:
        upd["is_default"] = bool(data["is_default"])
        if upd["is_default"]:
            await db[coll].update_many({"org_id": org, "id": {"$ne": scheme_id}},
                                       {"$set": {"is_default": False}})
    new_items = data.get(items_field)
    if new_items is not None:
        used = await _scheme_usage(coll, scheme_id, org)
        if used:
            raise HTTPException(status_code=400, detail=(
                f"Skema sudah dipakai {used} transaksi — isi skema tidak boleh diubah. "
                "Buat skema baru, lalu jadikan default."))
        upd[items_field] = new_items
    if not upd:
        return {"data": serialize_doc(cur)}
    upd["updated_at"] = now_iso()
    await db[coll].update_one({"id": scheme_id, "org_id": org}, {"$set": upd})
    fresh = await db[coll].find_one({"id": scheme_id, "org_id": org}, {"_id": 0})
    synced = await cascade_master_change(coll, scheme_id, fresh)
    await audit_log(user, "update", coll, scheme_id, {"fields": sorted(upd)})
    return {"data": serialize_doc(fresh), "denorm_synced": synced}


@router.put("/config/payment-schemes/{scheme_id}")
async def update_payment_scheme(scheme_id: str, payload: SchemeUpdate,
                                user: dict = Depends(require_permission("finance", "update"))):
    """Ubah nama/default skema pembayaran (isi termin dikunci bila sudah dipakai tagihan)."""
    return await _update_scheme("payment_schemes", scheme_id, payload, user, "items")


@router.put("/config/commission-schemes/{scheme_id}")
async def update_commission_scheme(scheme_id: str, payload: SchemeUpdate,
                                   user: dict = Depends(require_permission("finance", "update"))):
    """Ubah nama/default skema komisi (tier dikunci bila sudah dipakai perhitungan komisi)."""
    return await _update_scheme("commission_schemes", scheme_id, payload, user, "tiers")
