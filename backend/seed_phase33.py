"""Seed Fase 33 — RAB dipetakan ke langkah jadwal + SPK borongan berbasis item.

Dua hal (IDEMPOTEN):

1. **Pemetaan RAB → langkah jadwal** untuk proyek demo. Tanpa pemetaan ini tidak ada
   "harga acuan" saat menyusun lingkup borongan, dan panel Kendali Biaya tidak bisa
   membandingkan anggaran dengan nilai yang dikontrakkan.

2. **SPK borongan berbasis item** (`scope_mode="items"`) untuk pekerjaan STRUKTUR dua unit
   yang sudah punya jadwal nyata. Nilainya diambil dari harga acuan RAB — bukan angka
   karangan — dan nilai kontrak = Σ lingkup, sehingga demo langsung memperlihatkan
   "uang mengikuti bukti": hanya pekerjaan terverifikasi yang bisa ditagih.

SPK lump-sum lama (SPK/0001 & SPK/0002) DIBIARKAN apa adanya supaya jalur lama tetap
terlihat dan tidak ada data historis yang ditulis ulang diam-diam.
"""
import logging

import opname as op
import sequences as seq
from core_utils import new_id, now_iso
from db import db, ORG_ID

logger = logging.getLogger("sipro.seed")

# Pemetaan RAB (kode biaya) → langkah template rumah tapak 9 minggu & ruko 15 minggu.
STEP_MAP = {
    "PREP-01": ["W1-01", "R-01"],
    "STR-01": ["W2-02", "W4-01", "R-04", "R-08"],
    "STR-02": ["W1-02", "W2-01", "R-02", "R-03", "R-07"],
    "ARS-01": ["W3-01", "W5-01", "W5-02", "R-06", "R-12"],
    "MEP-01": ["W3-02", "W8-01", "R-15"],
    "FIN-01": ["W8-02"],
}
SCOPE_CATEGORY = "struktur"


async def _map_boq(org: str) -> int:
    mapped = 0
    for code, steps in STEP_MAP.items():
        res = await db.boq_items.update_many(
            {"org_id": org, "cost_code": code,
             "$or": [{"step_codes": {"$exists": False}}, {"step_codes": []}]},
            {"$set": {"step_codes": steps, "updated_at": now_iso()}})
        mapped += res.modified_count
    return mapped


async def _demo_spk(org: str) -> dict:
    if await db.spk_scope_items.count_documents({"org_id": org}):
        return {"spk": 0, "lines": 0}
    sub = await db.subcontractors.find_one({"org_id": org, "specialty": SCOPE_CATEGORY},
                                           {"_id": 0}) or \
        await db.subcontractors.find_one({"org_id": org}, {"_id": 0})
    if not sub:
        return {"spk": 0, "lines": 0}
    scheds = await db.build_schedules.find({"org_id": org}, {"_id": 0}).sort(
        "unit_code", 1).to_list(4)
    if not scheds:
        return {"spk": 0, "lines": 0}
    scheds = scheds[:2]
    project_id = scheds[0]["project_id"]
    project = await db.projects.find_one({"id": project_id, "org_id": org},
                                         {"_id": 0, "name": 1}) or {}
    ref = await op.rab_reference(org, project_id)
    used = await op.used_item_ids(org)
    picks = []
    for s in scheds:
        items = await db.build_items.find(
            {"org_id": org, "schedule_id": s["id"], "work_category": SCOPE_CATEGORY},
            op.ITEM_FIELDS).sort("order", 1).to_list(50)
        for it in items:
            if it["id"] in used:
                continue
            hint = ref.get(it.get("step_code")) or {}
            value = int(hint.get("suggested_value") or 0) or int(float(it.get("weight") or 1) * 1_000_000)
            picks.append((it, value, hint))
    if not picks:
        return {"spk": 0, "lines": 0}
    total = sum(v for _i, v, _h in picks)
    ts = now_iso()
    spk_id = new_id()
    spk = {
        "id": spk_id, "org_id": org,
        "spk_number": await seq.next_number("spk", org, prefix="SPK"),
        "subcontractor_id": sub["id"], "subcontractor_name": sub.get("name"),
        "project_id": project_id, "project_name": project.get("name"),
        "title": "Borongan Struktur per Item Pekerjaan (berbukti)",
        "scope": ("Pembayaran mengikuti item jadwal yang sudah diverifikasi supervisor — "
                  "lihat tab Lingkup & Opname."),
        "contract_value": total, "retention_pct": 5.0,
        "start_date": scheds[0].get("start_date"), "end_date": scheds[-1].get("target_finish_date"),
        "status": "active", "progress_pct": 0, "billed_pct": 0,
        "scope_mode": "items", "notes": None,
        "created_by": "pm@sipro.co.id", "created_at": ts, "updated_at": ts,
    }
    await db.spk.insert_one(dict(spk))
    docs = []
    for it, value, hint in picks:
        docs.append({
            "id": new_id(), "org_id": org, "spk_id": spk_id, "spk_number": spk["spk_number"],
            "project_id": project_id, "subcontractor_id": sub["id"],
            "subcontractor_name": sub.get("name"),
            "unit_id": it.get("unit_id"), "unit_code": it.get("unit_code"),
            "schedule_id": it.get("schedule_id"), "build_item_id": it["id"],
            "step_code": it.get("step_code"), "step_name": it.get("name"),
            "week": it.get("week"), "weight": it.get("weight"), "order": it.get("order"),
            "value": value, "boq_item_id": hint.get("boq_item_id"),
            "cost_code": hint.get("cost_code"),
            "category": hint.get("category") or it.get("work_category") or "lainnya",
            "pending_claim_id": None, "claim_id": None, "claim_number": None,
            "claimed_at": None, "exclude_reason": None,
            "created_by": "pm@sipro.co.id", "created_at": ts, "updated_at": ts,
        })
    await db.spk_scope_items.insert_many(docs)
    await op.sync_spk(org, spk_id)
    return {"spk": 1, "lines": len(docs), "value": total, "spk_number": spk["spk_number"]}


async def seed_phase33(org_id: str = ORG_ID) -> dict:
    out = {"boq_mapped": await _map_boq(org_id)}
    out.update(await _demo_spk(org_id))
    if out.get("boq_mapped") or out.get("lines"):
        logger.info("Seed Fase 33: %s item RAB dipetakan ke langkah, SPK borongan berbasis "
                    "item %s (%s baris).", out["boq_mapped"], out.get("spk_number") or "-",
                    out.get("lines", 0))
    return out
