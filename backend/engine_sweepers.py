"""Sweeper terjadwal milik engine (dipisah dari engine.py demi batas NFR 800 baris):
kedaluwarsa reservasi, jam tahap, SLA tugas, tenggat izin, percakapan tanpa balasan.
Diimpor lazily oleh `engine.start_scheduler`.
"""
import logging

from db import db, ORG_ID
from core_utils import now_iso, due_in

logger = logging.getLogger("sipro.engine")


async def reservation_expiry_sweeper() -> int:
    from engine import emit
    swept = 0
    cur = await db.deals.find({"status": {"$in": ["draft", "reserved"]}}).to_list(1000)
    for d in cur:
        ru = d.get("reserved_until")
        if ru and ru < now_iso():
            await db.deals.update_one({"id": d["id"]}, {"$set": {"status": "expired", "updated_at": now_iso()}})
            if d.get("unit_id"):
                await db.units.update_one({"id": d["unit_id"]}, {"$set": {"status": "available", "updated_at": now_iso()}})
            await emit("deal.expired", "deal", d["id"], {"unit_id": d.get("unit_id")}, org_id=d.get("org_id", ORG_ID))
            await __import__("booking_fee").cancel(d.get("org_id", ORG_ID), d["id"], "scheduler")
            swept += 1
    return swept


async def stage_clock_tick() -> int:
    """Fase 41 — JARING PENGAMAN jam tahap.

    Transisi yang lewat pintu resmi (lead lifecycle, deal, komplain) menulis
    `stage_entered_at` seketika. Sisa jalur penulisan status (tugas, dokumen, AR, impor)
    masih banyak dan tersebar; daripada menambal tiga puluh tempat sekaligus (risiko regresi
    lebih besar daripada manfaatnya), sweeper ini menyamakan jam tahap setiap menit dari
    FAKTA yang tercatat (`updated_at`) dan menandai asalnya `reconcile:updated_at` supaya
    tingkat kepastiannya terlihat di data & laporan, tidak disembunyikan.
    """
    import stage_clock as clock
    filled = await clock.reconcile()
    total = sum(filled.values())
    if total:
        logger.info("Jam tahap disamakan: %s", {k: v for k, v in filled.items() if v})
    return total


async def sla_breach_check() -> int:
    from engine import create_notification
    breached = await db.tasks.find({
        "status": {"$in": ["open", "in_progress"]},
        "sla_due_at": {"$ne": None, "$lt": now_iso()}, "sla_breached": {"$ne": True},
    }).to_list(1000)
    for t in breached:
        await db.tasks.update_one({"id": t["id"]}, {"$set": {"sla_breached": True, "updated_at": now_iso()}})
        await create_notification(
            user_email=t.get("assigned_to"), title="SLA task terlampaui",
            body=f"Task '{t.get('title')}' telah melewati batas SLA.", type="sla",
            related_entity_type=t.get("related_entity_type"), related_entity_id=t.get("related_entity_id"),
            org_id=t.get("org_id", ORG_ID),
        )
    return len(breached)


async def permit_deadline_sweeper() -> int:
    """Corrective task + PM notification for permits due-soon or overdue (EPIC 2.7)."""
    from engine import auto_create_task, create_notification
    now = now_iso()
    remind_horizon = due_in(days=14)
    pending = await db.permits.find({
        "status": {"$nin": ["approved", "rejected", "expired"]},
        "deadline": {"$ne": None},
    }).to_list(1000)
    made = 0
    for p in pending:
        deadline = p.get("deadline")
        overdue = deadline < now
        # remind window uses each permit's own reminder_days (fallback 14d horizon)
        horizon = due_in(days=p.get("reminder_days", 14)) if p.get("reminder_days") else remind_horizon
        if not overdue and deadline > horizon:
            continue
        org = p.get("org_id", ORG_ID)
        proj = await db.projects.find_one({"id": p.get("project_id")}, {"_id": 0}) or {}
        members = proj.get("members") or []
        assignee = None
        if members:
            pm = await db.users.find_one(
                {"org_id": org, "email": {"$in": members}, "role": "project_manager"},
                {"_id": 0, "email": 1})
            assignee = pm["email"] if pm else members[0]
        label = "TERLAMBAT" if overdue else "segera jatuh tempo"
        t = await auto_create_task(
            source_event=f"permit:{p['id']}:{now[:10]}", jobdesk_code="TK-08",
            title=f"Izin {p.get('type')} {label} — {proj.get('code') or p.get('project_name')}",
            type="review", related_entity_type="project", related_entity_id=p.get("project_id"),
            assigned_to=assignee, due_date=deadline, sla_due_at=deadline,
            priority="urgent" if overdue else "high", org_id=org,
            description=f"Perizinan {p.get('name')} ({p.get('type')}) {label} pada {str(deadline)[:10]}.")
        if t:
            made += 1
            await create_notification(
                user_email=assignee, title=f"Izin {p.get('type')} {label}",
                body=f"{p.get('name')} — {proj.get('name')}", type="permit",
                related_entity_type="project", related_entity_id=p.get("project_id"), org_id=org)
    return made


async def no_response_sweeper() -> int:
    """EPIC 1.7: re-engage stalled conversations per 'no_response' automation rules.
    Stalled = last message older than the rule's N days AND linked lead not advanced
    past nurturing. A per-conversation cooldown (last_reengage_at) prevents template spam."""
    from engine import run_rule_actions
    made = 0
    orgs = await db.automation_rules.distinct(
        "org_id", {"is_active": True, "trigger.event": "no_response"})
    for org in orgs:
        rules = await db.automation_rules.find({
            "org_id": org, "is_active": True, "trigger.event": "no_response"}).to_list(100)
        for r in rules:
            days = r.get("trigger", {}).get("no_response_days") or 3
            cutoff = due_in(days=-days)
            convs = await db.conversations.find({
                "org_id": org, "status": {"$in": ["new", "active"]},
                "last_message_at": {"$ne": None, "$lt": cutoff}}).to_list(500)
            for c in convs:
                if c.get("last_reengage_at") and c["last_reengage_at"] > cutoff:
                    continue  # cooldown: already re-engaged within the window
                lead = await db.leads.find_one({"id": c.get("lead_id")}, {"_id": 0, "stage": 1})
                if lead and lead.get("stage") in ("booking", "won", "lost"):
                    continue
                n = await run_rule_actions(r, org, conv=c, intent="no_response")
                if n:
                    await db.conversations.update_one(
                        {"id": c["id"]}, {"$set": {"last_reengage_at": now_iso()}})
                    made += 1
    return made
