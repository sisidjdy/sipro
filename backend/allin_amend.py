"""Fase 79 — AMANDEMEN skema all-in (jejak permintaan → persetujuan), PDF invoice/kuitansi biaya,
dan pengingat tahap pencairan KPR yang syaratnya sudah terpenuhi.

Skema all-in kontrak yang sudah terbit adalah SNAPSHOT: tidak boleh diedit langsung. Perubahan
hanya lewat amandemen: finance mengajukan (alasan), finance_manager/superadmin LAIN memutuskan,
dan kontrak menyimpan riwayat sebelum/sesudah.
"""
import logging

import allin_engine as ae
import finance_engine as fe
import kpr_disburse as kd
from core_utils import new_id, now_iso
from db import ORG_ID, db
from engine import add_activity, create_notification
from rbac import has_role

logger = logging.getLogger("sipro.p79")

DECIDER_ROLES = ("finance_manager", "super_admin", "owner")


def _rp(v):
    return f"Rp {int(v or 0):,}".replace(",", ".")


# ============================================================ amandemen skema all-in
async def list_amendments(org: str, contract_id: str) -> list:
    return await db.allin_amendments.find({"org_id": org, "contract_id": contract_id}, {"_id": 0}) \
        .sort("created_at", -1).to_list(50)


async def request_amendment(org: str, contract: dict, payload: dict, user: dict) -> dict:
    if contract.get("state") == "cancelled":
        raise ValueError("Kontrak sudah dibatalkan.")
    reason = (payload.get("reason") or "").strip()
    if len(reason) < 10:
        raise ValueError("Alasan amandemen wajib (minimal 10 huruf).")
    if await db.allin_amendments.find_one({"org_id": org, "contract_id": contract["id"], "status": "pending"}):
        raise ValueError("Masih ada amandemen skema yang menunggu keputusan.")
    if await db.cost_receipts.find_one({"org_id": org, "contract_id": contract["id"], "status": {"$ne": "void"}}):
        raise ValueError("Sudah ada kuitansi biaya yang diterima — skema tidak bisa diamandemen; "
                         "batalkan kuitansi dulu lewat finance.")
    deal = await db.deals.find_one({"id": contract.get("deal_id")}, {"_id": 0, "project_id": 1, "price": 1}) or {}
    price = int(contract.get("price") or deal.get("price") or 0)
    if payload.get("scheme_id"):
        new_costs = await ae.resolve_scheme(org, payload["scheme_id"], price, deal.get("project_id"),
                                            contract.get("scheme"))
    elif payload.get("items") is not None:
        if not await ae.may_manual(user):
            raise PermissionError("Komponen manual hanya finance_manager/superadmin.")
        new_costs = ae.manual_components(payload["items"], reason, user.get("email"))
    else:
        raise ValueError("Pilih skema all-in atau isi komponen manual.")
    old = contract.get("costs") or {}
    ts = now_iso()
    doc = {"id": new_id(), "org_id": org, "contract_id": contract["id"], "contract_no": contract.get("number"),
           "deal_id": contract.get("deal_id"), "customer_id": contract.get("customer_id"),
           "status": "pending", "reason": reason,
           "from": {"scheme_code": old.get("scheme_code"), "scheme_name": old.get("scheme_name"),
                    "components": old.get("components") or []},
           "to": {"scheme_code": new_costs.get("scheme_code"), "scheme_name": new_costs.get("scheme_name"),
                  "components": new_costs.get("components") or []},
           "new_costs": new_costs,
           "requested_by": user.get("email"), "requested_at": ts, "created_at": ts}
    await db.allin_amendments.insert_one(dict(doc))
    doc.pop("_id", None)
    await fe.notify_finance(org, f"Amandemen skema biaya kontrak {contract.get('number')} menunggu keputusan",
                            f"{old.get('scheme_name') or 'Legacy'} → {new_costs.get('scheme_name')} · {reason}",
                            ntype="approval", related_entity_type="allin_amendment", related_entity_id=doc["id"])
    await add_activity(entity_type="customer", entity_id=contract.get("customer_id"), type="finance",
                       actor=user.get("email"), org_id=org,
                       body=f"Amandemen skema biaya diajukan: {old.get('scheme_name') or 'Legacy'} → "
                            f"{new_costs.get('scheme_name')} ({reason}).")
    return doc


async def decide_amendment(org: str, amendment_id: str, approve: bool, note: str, user: dict) -> dict:
    if not has_role(user, *DECIDER_ROLES):
        raise PermissionError("Keputusan amandemen hanya finance_manager/superadmin.")
    am = await db.allin_amendments.find_one({"org_id": org, "id": amendment_id}, {"_id": 0})
    if not am:
        raise ValueError("Amandemen tidak ditemukan.")
    if am["status"] != "pending":
        raise ValueError("Amandemen ini sudah diputuskan.")
    if am["requested_by"] == user.get("email") and not has_role(user, "super_admin"):
        raise PermissionError("Pengaju tidak boleh menyetujui amandemennya sendiri.")
    if not approve and len((note or "").strip()) < 5:
        raise ValueError("Alasan penolakan wajib diisi.")
    ts = now_iso()
    status = "approved" if approve else "rejected"
    await db.allin_amendments.update_one({"id": amendment_id}, {"$set": {
        "status": status, "decided_by": user.get("email"), "decided_at": ts, "decision_note": note or ""}})
    contract = await db.contracts.find_one({"id": am["contract_id"]}, {"_id": 0})
    if approve and contract:
        old = contract.get("costs") or {}
        keep = {k: old[k] for k in ("pph_seller", "promo_discount", "plafon_kredit", "dp_percent") if k in old}
        new_costs = {**keep, **am["new_costs"], "amended_at": ts, "amendment_id": amendment_id}
        await db.contracts.update_one({"id": contract["id"]}, {
            "$set": {"costs": new_costs, "updated_at": ts, "costs_updated_by": user.get("email"), "costs_updated_at": ts},
            "$push": {"costs_history": {"amendment_id": amendment_id, "at": ts, "by": user.get("email"),
                                        "from": am["from"], "to": am["to"], "reason": am["reason"]}}})
        # invoice biaya yang belum dibayar ikut dibatalkan (nominal berubah); yang sudah dibayar diblokir di pengajuan
        await db.cost_invoices.update_many(
            {"org_id": org, "contract_id": contract["id"], "status": {"$in": ["unpaid"]}},
            {"$set": {"status": "void", "void_reason": f"amandemen skema {amendment_id}", "updated_at": ts}})
    await create_notification(user_email=am["requested_by"], org_id=org, type="finance",
                              title=f"Amandemen skema kontrak {am.get('contract_no')} {'DISETUJUI' if approve else 'DITOLAK'}",
                              body=note or am["reason"], related_entity_type="allin_amendment", related_entity_id=amendment_id)
    if contract:
        await add_activity(entity_type="customer", entity_id=contract.get("customer_id"), type="finance",
                           actor=user.get("email"), org_id=org,
                           body=f"Amandemen skema biaya {'DISETUJUI' if approve else 'DITOLAK'} oleh {user.get('email')}"
                                f"{' — ' + note if note else ''}.")
    return await db.allin_amendments.find_one({"id": amendment_id}, {"_id": 0})


# ============================================================ pengingat tahap pencairan
async def ready_tranches(org: str) -> list:
    """Tahap yang syaratnya SUDAH terpenuhi tetapi bank belum mencairkan (status open)."""
    out = []
    cur = db.financing_apps.find({"org_id": org, "tranches.status": "open",
                                  "status": {"$nin": ["rejected", "cancelled", "done"]}}, {"_id": 0})
    async for app in cur:
        c = await db.contracts.find_one({"deal_id": app["deal_id"], "org_id": org}, {"_id": 0})
        if not c or c.get("state") == "cancelled":
            continue
        for t in app.get("tranches") or []:
            if t.get("status") != "open" or not kd._condition_met(c, app, t.get("condition")):
                continue
            out.append({"app_id": app["id"], "contract_id": c["id"], "contract_no": c.get("number"),
                        "customer_id": c.get("customer_id"), "customer_name": c.get("customer_name"),
                        "unit_code": c.get("unit_code"), "bank": app.get("bank_name"),
                        "tranche_code": t["code"], "tranche_name": t["name"], "amount": int(t.get("amount") or 0),
                        "condition": t.get("condition"), "akad_date": (app.get("akad") or {}).get("date")})
    return out


async def run_tranche_reminders(org: str = ORG_ID) -> dict:
    """Satu notifikasi per (pengajuan, tahap) — tidak berulang selama tahap masih open."""
    items = await ready_tranches(org)
    sent = 0
    for it in items:
        key = f"{it['app_id']}:{it['tranche_code']}"
        if await db.notifications.find_one({"org_id": org, "type": "financing", "related_entity_type": "kpr_tranche",
                                            "related_entity_id": key}):
            continue
        await fe.notify_finance(org, f"Tahap {it['tranche_name']} KPR {it['contract_no']} siap dicairkan",
                                f"Syarat '{it['condition']}' terpenuhi, bank {it.get('bank') or '-'} belum mencairkan "
                                f"{_rp(it['amount'])} (unit {it.get('unit_code')}). Tagih bank / catat pencairan.",
                                ntype="financing", related_entity_type="kpr_tranche", related_entity_id=key)
        sent += 1
    return {"ready": len(items), "notified": sent, "items": items}


async def tranche_reminder_tick() -> dict:
    out = {}
    orgs = await db.orgs.distinct("id") or [ORG_ID]
    for org in orgs:
        try:
            res = await run_tranche_reminders(org)
            if res["notified"]:
                out[org] = res["notified"]
        except Exception:  # noqa: BLE001
            logger.exception("Pengingat tahap cair gagal untuk org %s", org)
    return out


def register(scheduler) -> list:
    jobs = [(tranche_reminder_tick, {"trigger": "cron", "hour": 1, "minute": 15, "id": "kpr_tranche_reminder_daily"})]
    for fn, kw in jobs:
        scheduler.add_job(fn, max_instances=1, coalesce=True, **kw)
    return [kw["id"] for _fn, kw in jobs]
