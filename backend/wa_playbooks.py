"""PLAYBOOK WHATSAPP per TAHAP LEAD (Fase 29b) — reminder, follow-up, blasting promo.

Permintaan owner: "task harus terintegrasi dengan WA … blasting PROMO, reminder ke lead
tergantung stage-nya, follow-up, dll." Sebelumnya WA hanya punya `automation_rules`
berbasis KEYWORD pesan masuk; tidak ada apa pun yang bekerja berdasarkan TAHAP lead.

Playbook = konfigurasi (bisa diubah supervisor) yang menyatakan:
  * lead pada tahap/kondisi apa yang disasar,
  * template WA mana yang dipakai (pra-approved),
  * jeda antar pengiriman (cooldown) agar tidak spam,
  * apakah dikirim OTOMATIS oleh sistem atau hanya jadi TUGAS bagi staf (human-in-the-loop).

Pengiriman memakai lapisan yang sama dengan Inbox (mode SIMULASI selama kredensial Meta
belum ada) dan SELALU menghasilkan aktivitas pada lead + tugas tindak lanjut bila perlu.
"""
import logging

from core_utils import due_in, new_id, now_iso
from db import db, ORG_ID
from engine import add_activity, dispatch_pending, send_template_message

logger = logging.getLogger("sipro.wa_playbook")

DEFAULTS = [
    {"key": "first_touch", "name": "Sapaan kontak pertama",
     "stages": ["acquisition"], "template_code": "welcome", "cooldown_days": 1,
     "auto_send": False, "create_task": True, "jobdesk_code": "SM-01",
     "desc": "Lead baru belum dikontak. Default: dibuat sebagai TUGAS (kontak pertama "
             "sebaiknya dilakukan manusia); bisa diubah menjadi kirim otomatis."},
    {"key": "followup_nurturing", "name": "Follow-up lead menimbang",
     "stages": ["nurturing"], "template_code": "reengage", "cooldown_days": 3,
     "auto_send": True, "create_task": True, "jobdesk_code": "SM-10", "idle_days": 3,
     "desc": "Lead nurturing tanpa aktivitas 3 hari: kirim template + tugas follow-up."},
    {"key": "survey_reminder", "name": "Pengingat survey H-1",
     "stages": ["appointment"], "template_code": "appointment_reminder", "cooldown_days": 1,
     "auto_send": True, "create_task": False, "jobdesk_code": "SM-03",
     "desc": "Lead dengan jadwal survey besok: kirim pengingat agar tidak batal."},
    {"key": "payment_reminder", "name": "Pengingat pembayaran",
     "stages": ["booking", "won"], "template_code": "payment_reminder", "cooldown_days": 3,
     "auto_send": False, "create_task": True, "jobdesk_code": "SM-11",
     "desc": "Pembeli punya tagihan jatuh tempo: pengingat angsuran/DP."},
    {"key": "promo_blast", "name": "Blasting promo tersegmentasi",
     "stages": ["acquisition", "nurturing", "recycle"], "template_code": "promo",
     "cooldown_days": 14, "auto_send": False, "create_task": True, "jobdesk_code": "DM-04",
     "desc": "Kirim promo ke segmen lead (default: manual, dijalankan Digital Marketing)."},
]

BY_KEY = {p["key"]: p for p in DEFAULTS}


async def ensure_playbooks(org: str = ORG_ID) -> int:
    made = 0
    for p in DEFAULTS:
        meta = {k: p[k] for k in ("name", "stages", "desc", "jobdesk_code")}
        meta["updated_at"] = now_iso()
        existing = await db.wa_playbooks.find_one({"org_id": org, "key": p["key"]}, {"_id": 0})
        if existing:
            await db.wa_playbooks.update_one({"org_id": org, "key": p["key"]}, {"$set": meta})
            continue
        await db.wa_playbooks.insert_one({
            "id": new_id(), "org_id": org, **p, "sent": 0, "tasks": 0,
            "is_active": True, "created_at": now_iso(), "updated_at": now_iso()})
        made += 1
    return made


async def playbook(org: str, key: str) -> dict:
    base = dict(BY_KEY.get(key) or {})
    row = await db.wa_playbooks.find_one({"org_id": org, "key": key}, {"_id": 0})
    if row:
        base.update({k: v for k, v in row.items() if v is not None})
    return base


async def playbooks(org: str) -> list:
    out = []
    for key in BY_KEY:
        p = await playbook(org, key)
        tmpl = await db.wa_templates.find_one({"org_id": org, "code": p.get("template_code")},
                                              {"_id": 0, "name": 1, "status": 1})
        p["template_name"] = (tmpl or {}).get("name")
        p["template_ready"] = bool(tmpl) and (tmpl or {}).get("status") == "approved"
        out.append(p)
    return out


async def _conv_for_lead(org: str, lead: dict) -> dict:
    conv = await db.conversations.find_one({"org_id": org, "lead_id": lead["id"]}, {"_id": 0},
                                          sort=[("last_message_at", -1)])
    if conv:
        return conv
    ts = now_iso()
    conv = {"id": new_id(), "org_id": org, "channel": "whatsapp",
            "contact_phone": lead.get("phone"), "contact_name": lead.get("name"),
            "lead_id": lead["id"], "owner": lead.get("assigned_to"), "status": "active",
            "mode": "simulation", "unread": 0, "last_message_at": None,
            "last_direction": None, "window_expires_at": None,
            "created_at": ts, "updated_at": ts}
    await db.conversations.insert_one(dict(conv))
    return conv


async def _targets(org: str, p: dict, limit: int = 100) -> list:
    """Lead yang layak disasar playbook ini (dengan syarat kondisi + cooldown)."""
    q = {"org_id": org, "stage": {"$in": p.get("stages") or []}}
    if p.get("key") == "first_touch":
        q["first_contact_at"] = None
    if p.get("idle_days"):
        q["updated_at"] = {"$lt": due_in(days=-int(p["idle_days"]))}
    leads = await db.leads.find(q, {"_id": 0}).sort("created_at", -1).to_list(limit * 3)
    cool = due_in(days=-int(p.get("cooldown_days") or 1))
    out = []
    for l in leads:
        last = (l.get("playbook_sent") or {}).get(p["key"])
        if last and last > cool:
            continue
        if p["key"] == "survey_reminder":
            soon = await db.appointments.count_documents({
                "org_id": org, "lead_id": l["id"], "status": "scheduled",
                "scheduled_at": {"$gte": now_iso(), "$lte": due_in(days=1)}})
            if not soon:
                continue
        if p["key"] == "payment_reminder":
            due = await db.ar_invoices.count_documents({
                "org_id": org, "lead_id": l["id"], "status": {"$ne": "paid"},
                "due_date": {"$lte": due_in(days=3)}})
            if not due:
                continue
        out.append(l)
        if len(out) >= limit:
            break
    return out


async def run_playbook(org: str, key: str, *, actor: str = "system", limit: int = 50,
                       force_send: bool = False) -> dict:
    """Jalankan satu playbook. Kembalikan ringkasan JUJUR (terkirim/tugas/dilewati)."""
    from workhub import spawn
    p = await playbook(org, key)
    if not p:
        return {"error": "playbook tidak dikenal"}
    if not p.get("is_active", True):
        return {"sent": 0, "tasks": 0, "skipped": 0, "note": "Playbook nonaktif."}
    tmpl = await db.wa_templates.find_one({"org_id": org, "code": p.get("template_code")},
                                          {"_id": 0})
    leads = await _targets(org, p, limit=limit)
    sent = tasks = 0
    for l in leads:
        do_send = bool(tmpl) and (force_send or p.get("auto_send"))
        if do_send:
            conv = await _conv_for_lead(org, l)
            await send_template_message(conv, tmpl, org, variables={
                "nama": l.get("name") or "", "name": l.get("name") or ""}, actor=f"playbook:{key}")
            await db.leads.update_one({"id": l["id"]}, {"$set": {
                f"playbook_sent.{key}": now_iso(), "updated_at": now_iso()}})
            await add_activity(entity_type="lead", entity_id=l["id"], type="system",
                               body=f"Playbook WA '{p.get('name')}' terkirim (SIMULASI) "
                                    f"memakai template '{tmpl.get('name')}'.",
                               actor=actor, org_id=org)
            sent += 1
        if p.get("create_task") and p.get("jobdesk_code"):
            rows = await spawn(org, p["jobdesk_code"],
                               source_event=f"playbook:{key}:{l['id']}:{now_iso()[:10]}",
                               record_owner=l.get("assigned_to"), entity_type="lead",
                               entity_id=l["id"],
                               title=f"{p.get('name')}: {l.get('name')}",
                               description=p.get("desc"))
            tasks += len(rows)
    if sent or tasks:
        await db.wa_playbooks.update_one({"org_id": org, "key": key},
                                        {"$inc": {"sent": sent, "tasks": tasks},
                                         "$set": {"last_run_at": now_iso()}}, upsert=False)
        await dispatch_pending()
    note = None
    if not tmpl:
        note = (f"Template '{p.get('template_code')}' belum ada/disetujui — hanya tugas yang "
                "dibuat, tidak ada pesan terkirim.")
    return {"sent": sent, "tasks": tasks, "targets": len(leads), "note": note,
            "mode": "simulation"}


async def playbook_tick() -> dict:
    """Scheduler: jalankan playbook yang diizinkan mengirim otomatis."""
    out = {}
    orgs = await db.wa_playbooks.distinct("org_id", {"is_active": True})
    for org in orgs:
        for key in BY_KEY:
            p = await playbook(org, key)
            if not p.get("is_active", True) or not p.get("auto_send"):
                continue
            try:
                res = await run_playbook(org, key, actor="scheduler", limit=25)
                if res.get("sent") or res.get("tasks"):
                    out[f"{org}:{key}"] = res
            except Exception:  # noqa: BLE001
                logger.exception("Playbook %s gagal", key)
    return out
