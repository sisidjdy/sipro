"""seed_phase42.py — data demo MITRA & ATURAN FEE (idempoten).

Kenapa perlu seed: modul mitra tidak bisa dibuktikan (dan tidak bisa diuji UI-nya) pada
database yang hanya punya master agen tanpa kontrak, tanpa aturan fee, dan tanpa satu pun
lead beratribusi mitra. Semua yang ditulis di sini adalah data yang WAJAR untuk developer
properti — bukan angka fee karangan yang dipakai sebagai "bukti" fitur bekerja:
  * master agen Fase 27 DILENGKAPI field mitra (jenis, bentuk badan, kontrak, bank, portal),
  * satu mitra aggregator ditambahkan (jenis mitra yang paling berbeda perilakunya),
  * tiga aturan fee dengan dasar berbeda (persen, berjenjang, per lead) supaya mesin aturan
    benar-benar terpakai,
  * beberapa lead demo diberi atribusi mitra + `source=partner` agar analitik mitra punya
    angka nyata (dan gate bisa membandingkan hitungan API dengan isi database).
Ditandai `demo_batch="fase42"` sehingga bisa dikenali & tidak pernah dobel.
"""
import logging

import partner_fee as pfee
import partner_engine as pengine
import sequences as seq
from core_utils import new_id, now_iso, today_iso_date
from db import db, ORG_ID

logger = logging.getLogger("sipro.seed")

KIND_BY_AGENT_TYPE = {
    "agen_properti": ("agen_perorangan", "individual"),
    "broker_kantor": ("kantor_broker", "company"),
    "referral_pembeli": ("referral_pembeli", "individual"),
    "influencer": ("influencer", "individual"),
    "mitra_korporat": ("korporat", "company"),
    "lainnya": ("aggregator", "company"),
}


async def _upgrade_agents(org_id: str) -> int:
    """Lengkapi master agen lama menjadi master MITRA (tanpa menghapus apa pun)."""
    done = 0
    async for agent in db.agents.find({"org_id": org_id}, {"_id": 0}):
        if agent.get("partner_kind"):
            continue
        kind, entity = KIND_BY_AGENT_TYPE.get(agent.get("agent_type") or "lainnya",
                                              ("agen_perorangan", "individual"))
        year = today_iso_date()[:4]
        patch = {
            "partner_kind": kind, "entity_type": entity,
            "contract": {
                "number": f"PKS/{year}/{(agent.get('code') or 'AGN').split('/')[-1]}",
                "start_date": f"{year}-01-01", "end_date": f"{year}-12-31",
                "signed_by": agent.get("name"), "status": "active", "file_ids": [],
            },
            "pic_name": agent.get("pic_name") or agent.get("name"),
            "pic_phone": agent.get("pic_phone") or agent.get("phone"),
            "address": agent.get("address"), "nik": agent.get("nik"),
            "bank_account_name": agent.get("bank_account_name") or agent.get("name"),
            "settings": agent.get("settings") or {},
            "portal": agent.get("portal") or {"enabled": False, "user_id": None,
                                              "last_login_at": None},
            "updated_at": now_iso(),
        }
        await db.agents.update_one({"id": agent["id"]}, {"$set": patch})
        done += 1
    return done


async def _ensure_aggregator(org_id: str) -> dict:
    name = "Portal Properti Nusantara (aggregator)"
    existing = await db.agents.find_one({"org_id": org_id, "name": name}, {"_id": 0})
    if existing:
        return existing
    ts = now_iso()
    year = ts[:4]
    code = await seq.next_number("agent", org_id, prefix="AGN", width=4)
    doc = {
        "id": new_id(), "org_id": org_id, "code": code, "name": name,
        "agent_type": "lainnya", "partner_kind": "aggregator", "entity_type": "company",
        "company": "PT Portal Properti Nusantara", "phone": "+628121230004",
        "email": "partner@portalproperti.co.id", "npwp": "02.345.678.9-012.000",
        "nik": None, "address": "Jl. Gatot Subroto No. 12, Jakarta",
        "pic_name": "Rizky Pratama", "pic_phone": "+628121230005",
        "bank_name": "Mandiri", "bank_account": "1230004567",
        "bank_account_name": "PT Portal Properti Nusantara",
        "contract": {"number": f"PKS/{year}/0004", "start_date": f"{year}-01-01",
                     "end_date": f"{year}-12-31", "signed_by": "Rizky Pratama",
                     "status": "active", "file_ids": []},
        "note": "Mitra aggregator lead (demo Fase 42).", "status": "active",
        "settings": {}, "portal": {"enabled": False, "user_id": None, "last_login_at": None},
        "fee_total": 0, "fee_paid": 0, "deals_count": 0, "demo_batch": "fase42",
        "created_by": "seed", "created_at": ts, "updated_at": ts,
    }
    await db.agents.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


async def _ensure_rules(org_id: str, partners: dict) -> int:
    if await db.partner_fee_rules.count_documents({"org_id": org_id, "demo_batch": "fase42"}):
        return 0
    year = today_iso_date()[:4]
    plans = [
        {  # berlaku untuk SEMUA mitra yang tidak punya aturan khusus
            "name": "Fee standar mitra — 2% harga jual saat PPJB",
            "partner_id": None, "basis": "percent_price", "value": 2, "price_base": "gross",
            "trigger": "ppjb_signed", "tax": {"gross_up": False},
            "valid_from": f"{year}-01-01", "valid_to": f"{year}-12-31",
            "note": "Aturan bawaan bila mitra belum punya skema khusus.",
        },
        {  # kantor broker: berjenjang per jumlah closing bulanan, dibayar 2 tahap
            "name": "Kantor broker — berjenjang 1,5% / 2,5% (bayar 50% PPJB, 50% AJB)",
            "partner_id": (partners.get("kantor_broker") or {}).get("id"),
            "basis": "tier_volume", "period": "monthly", "price_base": "gross",
            "tiers": [{"min": 0, "max": 2, "value": 1.5, "mode": "percent"},
                      {"min": 3, "max": None, "value": 2.5, "mode": "percent"}],
            "splits": [{"trigger": "ppjb_signed", "pct": 50},
                       {"trigger": "ajb_signed", "pct": 50}],
            "tax": {"pph_type": "pph23", "gross_up": False},
            "note": "Makin banyak closing dalam satu bulan, makin tinggi persennya.",
        },
        {  # aggregator: dibayar per lead terkualifikasi (survey hadir)
            "name": "Aggregator — Rp150.000 per lead survey hadir",
            "partner_id": (partners.get("aggregator") or {}).get("id"),
            "basis": "per_lead_qualified", "value": 150000,
            "qualify_rule": "survey_attended", "trigger": "spr_signed",
            "tax": {"pph_type": "pph23", "gross_up": False},
            "note": "Dibayar atas lead yang benar-benar hadir survey (bukti dari agenda).",
        },
    ]
    made = 0
    for plan in plans:
        if plan.get("partner_id") is None and plan["name"].startswith("Kantor"):
            continue
        try:
            rule = await pfee.create_rule(plan, actor="seed", org_id=org_id)
        except ValueError as exc:
            logger.warning("Aturan fee demo dilewati (%s): %s", plan["name"], exc)
            continue
        await db.partner_fee_rules.update_one({"id": rule["id"]},
                                             {"$set": {"demo_batch": "fase42"}})
        made += 1
    return made


async def _attribute_demo_leads(org_id: str, partner_ids: list) -> int:
    """Beri atribusi mitra pada beberapa lead demo supaya analitik mitra punya angka nyata."""
    if not partner_ids:
        return 0
    if await db.leads.count_documents({"org_id": org_id, "partner_id": {"$ne": None}}):
        return 0
    leads = await db.leads.find(
        {"org_id": org_id, "demo_batch": "fase40",
         "$or": [{"partner_id": None}, {"partner_id": {"$exists": False}}]},
        {"_id": 0, "id": 1}).limit(9).to_list(9)
    ts = now_iso()
    for i, lead in enumerate(leads):
        await db.leads.update_one({"id": lead["id"]}, {"$set": {
            "source": "partner", "partner_id": partner_ids[i % len(partner_ids)],
            "partner_attributed_at": ts, "partner_attribution_model": "first_touch",
            "updated_at": ts}})
    for pid in partner_ids:
        await pengine.refresh_stats(pid, org_id=org_id)
    return len(leads)


async def seed_phase42(org_id: str = ORG_ID) -> dict:
    upgraded = await _upgrade_agents(org_id)
    aggregator = await _ensure_aggregator(org_id)
    partners = {}
    async for agent in db.agents.find({"org_id": org_id, "status": "active"}, {"_id": 0}):
        partners.setdefault(agent.get("partner_kind") or "agen_perorangan", agent)
    partners.setdefault("aggregator", aggregator)
    rules = await _ensure_rules(org_id, partners)
    attributed = await _attribute_demo_leads(
        org_id, [p["id"] for p in partners.values() if p.get("id")])
    out = {"agents_upgraded": upgraded, "rules": rules, "leads_attributed": attributed}
    if any(out.values()):
        logger.info("Seed Fase 42 (mitra & fee): %s", out)
    return out
