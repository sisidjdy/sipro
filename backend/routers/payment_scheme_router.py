"""Skema pembayaran yang bisa dikonfigurasi (Fase 57A).

Dipakai Pusat Konfigurasi › Skema Pembayaran, pratinjau jadwal sebelum disimpan, dan
penetapan skema pada satu kontrak.
"""
from fastapi import APIRouter, Depends, HTTPException

import payment_scheme_engine as psx
from core_utils import serialize_doc
from db import ORG_ID, db
from models_p57 import (ContractSchemeIn, InstallmentGenIn, SchemeIn, SchemeSimulateIn,
                        SchemeUpdate)
from rbac import audit_log, require_permission

router = APIRouter(prefix="/payment-schemes", tags=["payment-schemes"])


def _org(user: dict) -> str:
    return user.get("org_id", ORG_ID)


@router.get("")
async def list_schemes(kind: str = None, project_id: str = None, active: bool = None,
                       user: dict = Depends(require_permission("payment_scheme", "view"))):
    return await psx.listing(_org(user), kind=kind, project_id=project_id, active=active)


@router.post("/simulate")
async def simulate(payload: SchemeSimulateIn,
                   user: dict = Depends(require_permission("payment_scheme", "view"))):
    """Pratinjau jadwal — untuk rancangan yang BELUM disimpan sekalipun.

    Sengaja ada supaya pemakai melihat akibat konfigurasinya (nominal per termin, tanggal,
    dan selisih terhadap harga jual) SEBELUM skema itu menagih pembeli sungguhan.
    """
    org = _org(user)
    if payload.terms is not None:
        scheme = {"items": psx.normalize_terms([t.model_dump() for t in payload.terms])}
        halangan = psx.blocks([t.model_dump() for t in payload.terms])
    elif payload.scheme_id:
        try:
            scheme = await psx.get(org, payload.scheme_id)
        except LookupError as e:
            raise HTTPException(404, str(e))
        halangan = psx.blocks(scheme.get("items") or [])
    else:
        raise HTTPException(400, "Sebutkan skema yang disimpan (`scheme_id`) atau rancangan "
                                 "termin (`terms`) yang ingin dipratinjau.")
    out = psx.simulate(scheme, payload.price, payload.base_date)
    return {"data": serialize_doc({**out, "blocks": halangan})}


@router.post("/installments")
async def installments(payload: InstallmentGenIn,
                       user: dict = Depends(require_permission("payment_scheme", "view"))):
    """Pembantu 'buat N cicilan' — hasilnya baris termin biasa yang masih bisa diubah."""
    return {"data": psx.normalize_terms(psx.build_installments(
        payload.count, payload.percent_total, payload.start_month, payload.due_day,
        payload.grace_days, payload.label_prefix))}


@router.get("/{scheme_id}")
async def get_scheme(scheme_id: str,
                     user: dict = Depends(require_permission("payment_scheme", "view"))):
    try:
        return {"data": serialize_doc(await psx.get(_org(user), scheme_id))}
    except LookupError as e:
        raise HTTPException(404, str(e))


@router.post("")
async def create_scheme(payload: SchemeIn,
                        user: dict = Depends(require_permission("payment_scheme", "create"))):
    try:
        doc = await psx.save(_org(user), payload.model_dump(), user.get("email"))
    except ValueError as e:
        raise HTTPException(400, str(e))
    await audit_log(user, "create", "payment_scheme", doc["id"], {"name": doc["name"]})
    return {"data": serialize_doc(doc)}


@router.put("/{scheme_id}")
async def update_scheme(scheme_id: str, payload: SchemeUpdate,
                        user: dict = Depends(require_permission("payment_scheme", "update"))):
    try:
        doc = await psx.save(_org(user), payload.model_dump(), user.get("email"),
                             scheme_id=scheme_id)
    except LookupError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
    await audit_log(user, "update", "payment_scheme", scheme_id, {"name": doc["name"]})
    return {"data": serialize_doc(doc)}


@router.post("/contracts/{contract_id}")
async def set_for_contract(contract_id: str, payload: ContractSchemeIn,
                           user: dict = Depends(
                               require_permission("payment_scheme", "assign"))):
    org = _org(user)
    contract = await db.contracts.find_one({"id": contract_id, "org_id": org}, {"_id": 0})
    if not contract:
        raise HTTPException(404, "Kontrak tidak ditemukan.")
    try:
        doc = await psx.set_for_contract(org, contract, payload.scheme_id,
                                         user.get("email"), payload.reason)
    except LookupError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
    await audit_log(user, "update", "contract", contract_id,
                    {"payment_scheme_id": payload.scheme_id, "reason": payload.reason})
    return {"data": serialize_doc(doc)}
