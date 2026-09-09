"""partner_report.py — Fase 42 §7: ANALITIK MITRA dari data, bukan dari klaim mitra.

Setiap metrik di sini punya rumus yang tertulis di `docs/v2/25_PARTNER_SPEC.md` §7 dan
dihitung dari koleksi nyata (`leads`, `deals`, `marketing_fees`, `appointments`). Tautan
`drill` dibentuk DI SINI supaya definisi angka = definisi filter daftar (aturan Fase 40:
angka yang tidak bisa ditelusuri sampai barisnya dianggap belum selesai).
"""
import logging

from core_utils import now_iso
from db import db, ORG_ID

logger = logging.getLogger("sipro.partner_report")


def _median(values: list):
    if not values:
        return None
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return round((ordered[mid - 1] + ordered[mid]) / 2, 2)


def _days_between(start, end):
    from listing import parse_iso
    a, b = parse_iso(start), parse_iso(end)
    if not a or not b:
        return None
    return round(max(0.0, (b - a).total_seconds() / 86400.0), 2)


async def partner_rows(*, org_id: str = ORG_ID, created_from: str = None,
                       created_to: str = None) -> list:
    """Satu baris per mitra: kualitas lead, biaya akuisisi, kontribusi, ROI."""
    partners = await db.agents.find({"org_id": org_id}, {"_id": 0}).to_list(500)
    if not partners:
        return []
    lead_query = {"org_id": org_id, "partner_id": {"$ne": None}}
    if created_from or created_to:
        cond = {}
        if created_from:
            cond["$gte"] = created_from
        if created_to:
            cond["$lte"] = f"{created_to}T23:59:59.999999+00:00"
        lead_query["created_at"] = cond
    leads = await db.leads.find(lead_query, {
        "_id": 0, "id": 1, "partner_id": 1, "stage": 1, "created_at": 1, "won_at": 1,
        "first_contact_at": 1}).to_list(20000)
    by_partner = {}
    for lead in leads:
        by_partner.setdefault(lead["partner_id"], []).append(lead)
    lead_ids = [l["id"] for l in leads]
    attended = set(await db.appointments.distinct(
        "lead_id", {"org_id": org_id, "lead_id": {"$in": lead_ids}, "status": "done"}))
    deals = await db.deals.find(
        {"org_id": org_id, "$or": [{"partner_id": {"$ne": None}},
                                   {"lead_id": {"$in": lead_ids}}]},
        {"_id": 0, "lead_id": 1, "partner_id": 1, "status": 1, "price": 1}).to_list(20000)
    lead_owner = {l["id"]: l["partner_id"] for l in leads}
    deals_by_partner = {}
    for deal in deals:
        owner = deal.get("partner_id") or lead_owner.get(deal.get("lead_id"))
        if owner:
            deals_by_partner.setdefault(owner, []).append(deal)
    fees = await db.marketing_fees.find({"org_id": org_id}, {
        "_id": 0, "agent_id": 1, "status": 1, "amount_net": 1, "amount_gross": 1,
        "paid_amount": 1}).to_list(20000)
    fees_by_partner = {}
    for fee in fees:
        fees_by_partner.setdefault(fee.get("agent_id"), []).append(fee)

    rows = []
    for partner in partners:
        pid = partner["id"]
        plist = by_partner.get(pid, [])
        dlist = deals_by_partner.get(pid, [])
        flist = fees_by_partner.get(pid, [])
        approved = [f for f in flist if f.get("status") in ("approved", "paid")]
        won = [l for l in plist if l.get("stage") == "won"]
        booked = [d for d in dlist if d.get("status") in ("booked", "completed")]
        revenue = sum(int(d.get("price") or 0) for d in booked)
        fee_expense = sum(int(f.get("amount_gross") or 0) for f in approved)
        fee_net = sum(int(f.get("amount_net") or 0) for f in approved)
        fee_paid = sum(int(f.get("paid_amount") or 0) for f in approved)
        cycles = [d for d in (_days_between(l.get("created_at"), l.get("won_at"))
                              for l in won if l.get("won_at")) if d is not None]
        qualified = [l for l in plist if l["id"] in attended]
        rows.append({
            "partner_id": pid, "code": partner.get("code"), "name": partner.get("name"),
            "partner_kind": partner.get("partner_kind"), "status": partner.get("status"),
            "leads": len(plist),
            "contacted": sum(1 for l in plist if l.get("first_contact_at")),
            "survey_attended": len(qualified),
            "qualified_pct": round(len(qualified) * 100.0 / len(plist), 1) if plist else None,
            "booked": len(booked), "won": len(won),
            "win_rate_pct": round(len(won) * 100.0 / len(plist), 1) if plist else None,
            "revenue": revenue,
            "fee_expense": fee_expense, "fee_net": fee_net, "fee_paid": fee_paid,
            "fee_outstanding": fee_net - fee_paid,
            "fee_waiting": sum(int(f.get("amount_gross") or 0) for f in flist
                               if f.get("status") == "submitted"),
            "cost_per_won": round(fee_expense / len(won)) if won and fee_expense else None,
            "roi_pct": (round((revenue - fee_expense) * 100.0 / fee_expense, 1)
                        if fee_expense else None),
            "median_days_to_won": _median(cycles),
            "last_lead_at": max([l.get("created_at") for l in plist], default=None),
            "drill_leads": f"/leads?partner_id={pid}",
            "drill_fees": f"/partners/{pid}?tab=fee",
        })
    rows.sort(key=lambda r: (-(r["revenue"] or 0), -(r["leads"] or 0)))
    return rows


async def analytics(*, org_id: str = ORG_ID, created_from: str = None,
                    created_to: str = None) -> dict:
    rows = await partner_rows(org_id=org_id, created_from=created_from, created_to=created_to)
    totals = {
        "partners": len(rows),
        "active_partners": sum(1 for r in rows if r["status"] == "active"),
        "leads": sum(r["leads"] for r in rows),
        "booked": sum(r["booked"] for r in rows),
        "won": sum(r["won"] for r in rows),
        "revenue": sum(r["revenue"] for r in rows),
        "fee_expense": sum(r["fee_expense"] for r in rows),
        "fee_outstanding": sum(r["fee_outstanding"] for r in rows),
        "fee_waiting": sum(r["fee_waiting"] for r in rows),
        "conflicts_pending": await db.partner_attribution_conflicts.count_documents(
            {"org_id": org_id, "status": "pending_review"}),
    }
    totals["roi_pct"] = (round((totals["revenue"] - totals["fee_expense"]) * 100.0
                               / totals["fee_expense"], 1)
                        if totals["fee_expense"] else None)
    totals["cost_per_won"] = (round(totals["fee_expense"] / totals["won"])
                              if totals["won"] and totals["fee_expense"] else None)
    return {"rows": rows, "totals": totals, "generated_at": now_iso()}


async def overview(partner_id: str, *, org_id: str = ORG_ID) -> dict:
    """Ringkasan satu mitra + fee & lead terkini (dipakai halaman profil mitra)."""
    partner = await db.agents.find_one({"id": partner_id, "org_id": org_id}, {"_id": 0})
    if not partner:
        raise ValueError("Mitra tidak ditemukan.")
    rows = await partner_rows(org_id=org_id)
    metrics = next((r for r in rows if r["partner_id"] == partner_id), None)
    fees = await db.marketing_fees.find({"org_id": org_id, "agent_id": partner_id},
                                       {"_id": 0}).sort("created_at", -1).to_list(200)
    leads = await db.leads.find({"org_id": org_id, "partner_id": partner_id},
                               {"_id": 0}).sort("created_at", -1).to_list(200)
    rules = await db.partner_fee_rules.find(
        {"org_id": org_id, "$or": [{"partner_id": partner_id}, {"partner_id": None}]},
        {"_id": 0}).sort("created_at", -1).to_list(100)
    conflicts = await db.partner_attribution_conflicts.find(
        {"org_id": org_id, "$or": [{"claimed_by": partner_id}, {"held_by": partner_id}]},
        {"_id": 0}).sort("created_at", -1).to_list(100)
    return {"partner": partner, "metrics": metrics, "fees": fees, "leads": leads,
            "rules": rules, "conflicts": conflicts,
            "fee_counts": {
                "submitted": sum(1 for f in fees if f.get("status") == "submitted"),
                "approved": sum(1 for f in fees if f.get("status") == "approved"),
                "paid": sum(1 for f in fees if f.get("status") == "paid"),
                "rejected": sum(1 for f in fees if f.get("status") == "rejected")}}
