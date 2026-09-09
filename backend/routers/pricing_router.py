"""ROUTER MESIN HARGA (Fase 69) — prefix `/pricing`.

Skema diskon, promo, dan kupon DIKONFIGURASI oleh manajer sales/keuangan (`pricing:create/
update`); sales hanya MEMILIH dari yang berlaku (`pricing:view`). Tidak ada endpoint yang
menerima nominal diskon bebas.
"""
from fastapi import APIRouter, Depends, HTTPException

import pricing_engine as pe
from core_utils import serialize_doc
from db import ORG_ID, db
from models_p69 import (CouponIn, CouponValidateIn, DiscountSchemeIn, PricingRulePatch,
                       PromoIn)
from rbac import audit_log, require_permission

router = APIRouter(prefix="/pricing", tags=["pricing"])
KIND_OF = {"discount-schemes": "discount_scheme", "promos": "promo", "coupons": "coupon"}
MODEL_OF = {"discount-schemes": DiscountSchemeIn, "promos": PromoIn, "coupons": CouponIn}


def _org(user: dict) -> str:
    return user.get("org_id", ORG_ID)


def _kind(slug: str) -> str:
    if slug not in KIND_OF:
        raise HTTPException(status_code=404, detail="Jenis aturan harga tidak dikenal.")
    return KIND_OF[slug]


@router.get("/options")
async def options(unit_id: str, lead_id: str = None,
                  user: dict = Depends(require_permission("pricing", "view"))):
    """Skema diskon & promo yang BERLAKU untuk unit ini — bahan dropdown penawaran/reservasi."""
    org = _org(user)
    unit = await db.units.find_one({"id": unit_id, "org_id": org}, {"_id": 0})
    if not unit:
        raise HTTPException(status_code=404, detail="Unit tidak ditemukan.")
    return {"data": serialize_doc(await pe.options_for_unit(org, unit, lead_id))}


@router.post("/coupons/validate")
async def validate_coupon(payload: CouponValidateIn,
                          user: dict = Depends(require_permission("pricing", "view"))):
    org = _org(user)
    unit = await db.units.find_one({"id": payload.unit_id, "org_id": org}, {"_id": 0})
    if not unit:
        raise HTTPException(status_code=404, detail="Unit tidak ditemukan.")
    try:
        c = await pe.validate_coupon(org, payload.code, unit=unit, lead_id=payload.lead_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    calc = await pe.compute_discounts(org, unit=unit, gross=int(unit.get("price") or 0),
                                      coupon_code=payload.code, lead_id=payload.lead_id)
    return {"data": serialize_doc({"coupon": c, "line": calc["lines"][0]}),
            "message": f"Kupon {c['code']} berlaku."}


@router.get("/coupons/{coupon_id}/redemptions")
async def coupon_redemptions(coupon_id: str,
                             user: dict = Depends(require_permission("pricing", "view"))):
    org = _org(user)
    try:
        c = await pe.get_rule("coupon", coupon_id, org)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"data": {"coupon": serialize_doc(c),
                     "rows": serialize_doc(await pe.redemptions(org, coupon_id))}}


@router.get("/{slug}")
async def listing(slug: str, active: bool = None,
                  user: dict = Depends(require_permission("pricing", "view"))):
    return {"data": serialize_doc(await pe.listing(_kind(slug), _org(user), active))}


@router.post("/{slug}")
async def create(slug: str, payload: dict,
                 user: dict = Depends(require_permission("pricing", "create"))):
    kind = _kind(slug)
    try:
        body = MODEL_OF[slug](**payload).model_dump()
        row = await pe.create(kind, body, user.get("email"), _org(user))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit_log(user, "create", "pricing", row["id"], {"kind": kind, "code": row["code"]})
    return {"data": serialize_doc(row), "message": f"{pe.LABEL[kind]} disimpan."}


@router.put("/{slug}/{rule_id}")
async def update(slug: str, rule_id: str, payload: PricingRulePatch,
                 user: dict = Depends(require_permission("pricing", "update"))):
    kind = _kind(slug)
    try:
        row = await pe.update(kind, rule_id, payload.model_dump(), user.get("email"),
                              _org(user))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit_log(user, "update", "pricing", rule_id, {"kind": kind})
    return {"data": serialize_doc(row), "message": f"{pe.LABEL[kind]} diperbarui."}
