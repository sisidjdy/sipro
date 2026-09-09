"""Katalog master (Fase 39): tipe unit, spek tambahan (add-on), komponen biaya.

Dipakai oleh: Pusat Konfigurasi (UI), pembuatan unit, reservasi/SPR (Fase 42), kontrak &
rencana bayar (Fase 43), serta dokumen yang di-generate.
"""
from fastapi import APIRouter, Depends, HTTPException

import catalog as cat
from core_utils import serialize_doc
from db import ORG_ID, db
from models_v2 import (AddonCreate, AddonUpdate, PriceComponentCreate, PriceComponentUpdate,
                       UnitTypeCreate, UnitTypeUpdate)
from rbac import audit_log, require_permission

router = APIRouter(prefix="/catalog", tags=["catalog"])


def _org(user: dict) -> str:
    return user.get("org_id", ORG_ID)


# ------------------------------------------------------------------ tipe unit
@router.get("/unit-types")
async def list_unit_types(q: str = None, active: bool = None,
                          user: dict = Depends(require_permission("catalog", "view"))):
    return {"data": serialize_doc(await cat.list_unit_types(_org(user), q, active))}


@router.post("/unit-types")
async def create_unit_type(payload: UnitTypeCreate,
                           user: dict = Depends(require_permission("catalog", "create"))):
    try:
        row = await cat.create_unit_type(payload, user.get("email"), _org(user))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit_log(user, "create", "catalog", row["id"], {"unit_type": row["code"]})
    return {"data": serialize_doc(row)}


@router.put("/unit-types/{type_id}")
async def update_unit_type(type_id: str, payload: UnitTypeUpdate,
                           user: dict = Depends(require_permission("catalog", "update"))):
    try:
        row = await cat.update_unit_type(type_id, payload, user.get("email"), _org(user))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit_log(user, "update", "catalog", type_id, {})
    return {"data": serialize_doc(row)}


# ------------------------------------------------------------------ add-on
@router.get("/addons")
async def list_addons(category: str = None, active: bool = None, project_id: str = None,
                      user: dict = Depends(require_permission("catalog", "view"))):
    return {"data": serialize_doc(await cat.list_addons(_org(user), category, active,
                                                        project_id))}


@router.post("/addons")
async def create_addon(payload: AddonCreate,
                       user: dict = Depends(require_permission("catalog", "create"))):
    try:
        row = await cat.create_addon(payload, user.get("email"), _org(user))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit_log(user, "create", "catalog", row["id"], {"addon": row["code"]})
    return {"data": serialize_doc(row)}


@router.put("/addons/{addon_id}")
async def update_addon(addon_id: str, payload: AddonUpdate,
                       user: dict = Depends(require_permission("catalog", "update"))):
    try:
        row = await cat.update_addon(addon_id, payload, user.get("email"), _org(user))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit_log(user, "update", "catalog", addon_id, {})
    return {"data": serialize_doc(row)}


@router.get("/units/{unit_id}/suggested-addons")
async def suggested_addons(unit_id: str,
                           user: dict = Depends(require_permission("catalog", "view"))):
    """Usulan add-on dari atribut nyata unit (hook, kelebihan tanah) — bukan tebakan."""
    unit = await db.units.find_one({"id": unit_id, "org_id": _org(user)}, {"_id": 0})
    if not unit:
        raise HTTPException(status_code=404, detail="Unit tidak ditemukan")
    return {"data": serialize_doc(await cat.suggested_addons_for_unit(unit, _org(user)))}


# ------------------------------------------------------------------ komponen biaya
@router.get("/price-components")
async def list_components(scheme: str = None, active: bool = None,
                          user: dict = Depends(require_permission("catalog", "view"))):
    return {"data": serialize_doc(await cat.list_price_components(_org(user), scheme, active))}


@router.get("/price-components/matrix")
async def component_matrix(user: dict = Depends(require_permission("catalog", "view"))):
    """Matriks komponen × skema bayar: bukti bahwa tiap skema punya komponen berbeda."""
    return {"data": serialize_doc(await cat.scheme_matrix(_org(user)))}


@router.post("/price-components")
async def create_component(payload: PriceComponentCreate,
                           user: dict = Depends(require_permission("catalog", "create"))):
    try:
        row = await cat.create_price_component(payload, user.get("email"), _org(user))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit_log(user, "create", "catalog", row["id"], {"component": row["code"]})
    return {"data": serialize_doc(row)}


@router.put("/price-components/{comp_id}")
async def update_component(comp_id: str, payload: PriceComponentUpdate,
                           user: dict = Depends(require_permission("catalog", "update"))):
    try:
        row = await cat.update_price_component(comp_id, payload, user.get("email"), _org(user))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit_log(user, "update", "catalog", comp_id, {})
    return {"data": serialize_doc(row)}
