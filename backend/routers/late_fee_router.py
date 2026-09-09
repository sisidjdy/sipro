"""ROUTER DENDA & TOLERANSI KETERLAMBATAN (Fase 58) — prefix `/finance/late-fees`.

Pemisahan tugas yang dipaksakan di sini (dan diuji gate 49):
  * **melihat** keadaan termin & denda berjalan = `late_fee:view`;
  * **menagihkan** denda (berjurnal) = `late_fee:create` (Keuangan);
  * **meringankan** denda = `late_fee:override` (Manajer Keuangan) — bukan orang yang
    menagihkannya, dan wajib alasan tertulis minimal 10 huruf.
"""
from fastapi import APIRouter, Depends, HTTPException

import late_fee_engine as lf
from core_utils import serialize_doc
from db import ORG_ID, db
from models_p58 import LateFeeApplyIn, LateFeeWaiveIn
from rbac import audit_log, can, is_scoped_sales, require_permission

router = APIRouter(prefix="/finance/late-fees", tags=["finance-late-fees"])


def _org(user: dict) -> str:
    return user.get("org_id", ORG_ID)


async def _deal_scoped(deal_id: str, user: dict) -> dict:
    deal = await db.deals.find_one({"id": deal_id, "org_id": _org(user)}, {"_id": 0})
    if not deal:
        raise HTTPException(status_code=404, detail="Transaksi tidak ditemukan")
    if is_scoped_sales(user) and deal.get("assigned_to") != user.get("email"):
        raise HTTPException(status_code=403, detail="Akses ditolak: bukan transaksi Anda")
    return deal


@router.get("/policy")
async def get_policy(user: dict = Depends(require_permission("late_fee", "view"))):
    """Kebijakan toleransi & denda dari Pusat Konfigurasi + kalimat aturannya."""
    pol = await lf.policy(_org(user))
    return {"data": {"policy": pol, "policy_sentence": lf.policy_sentence(pol)}}


@router.get("/{deal_id}")
async def assess(deal_id: str, user: dict = Depends(require_permission("late_fee", "view"))):
    """Keadaan setiap termin terhadap jatuh tempo + TOLERANSI, denda berjalan & tertagih."""
    await _deal_scoped(deal_id, user)
    out = await lf.assess(_org(user), deal_id)
    return {"data": serialize_doc(out),
            "may_apply": await can(user.get("role"), "late_fee", "create"),
            "may_waive": await can(user.get("role"), "late_fee", "override")}


@router.post("/{deal_id}/apply")
async def apply(deal_id: str, payload: LateFeeApplyIn,
                user: dict = Depends(require_permission("late_fee", "create"))):
    """Tagihkan denda yang berlaku — satu jurnal per (termin, bulan), tidak pernah dobel."""
    await _deal_scoped(deal_id, user)
    try:
        out = await lf.apply(_org(user), deal_id, user.get("email"),
                             item_id=payload.item_id, client_ref=payload.client_ref)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if out["created"]:
        await audit_log(user, "update", "late_fee", deal_id,
                        {"charged": sum(c["amount"] for c in out["created"])})
    return {"data": serialize_doc(out["assessment"]),
            "created": serialize_doc(out["created"]), "replay": out.get("replay", False)}


@router.post("/{deal_id}/waive/{penalty_id}")
async def waive(deal_id: str, penalty_id: str, payload: LateFeeWaiveIn,
                user: dict = Depends(require_permission("late_fee", "override"))):
    """Keringanan denda: membalik jurnalnya, wajib beralasan, hanya Manajer Keuangan."""
    await _deal_scoped(deal_id, user)
    may_waive = await can(user.get("role"), "late_fee", "override")
    try:
        out = await lf.waive(_org(user), deal_id, penalty_id, user.get("email"),
                             reason=payload.reason, may_waive=may_waive)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not out.get("replay"):
        await audit_log(user, "approve", "late_fee", penalty_id,
                        {"waived": out["waived"].get("waived_amount"),
                         "reason": payload.reason})
    return {"data": serialize_doc(out.get("assessment")
                                  or await lf.assess(_org(user), deal_id)),
            "waived": serialize_doc(out["waived"]), "replay": out.get("replay", False)}
