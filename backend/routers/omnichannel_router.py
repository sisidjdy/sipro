"""EPIC 1.7 Omnichannel config + insights.

Manages the Conversational Automation engine's building blocks:
- automation_rules  (trigger -> actions; consumed by engine._h_message_received / _h_lead_captured / no_response_sweeper)
- wa_templates      (pre-approved WhatsApp templates used to (re)open the 24h session window)
- channels          (channel_accounts — SIMULATION mode by default)
- capture-events    (audit of inbound lead captures) + ads attribution funnel

All GET endpoints keep every query param optional (owner endpoint-sweep must return 200).
"""
import re

from fastapi import APIRouter, Depends, HTTPException

import reference as ref
import settings_store as cfg
import wa_gateway as gw
import wa_template_governance as gov
from db import db, ORG_ID
from core_utils import new_id, now_iso, serialize_doc, parse_pagination
from rbac import require_permission
from models import (AutomationRuleCreate, AutomationRuleUpdate, WaTemplateCreate,
                    WaReminderMappingIn,
                    WaTemplateUpdate, ChannelCreate, ChannelUpdate)

router = APIRouter(tags=["omnichannel"])

# SSOT: pemicu & aksi automasi dari reference.py (grup automation_trigger/action).
VALID_EVENTS = set(ref.values("automation_trigger"))
VALID_ACTIONS = set(ref.values("automation_action"))


def _slug(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "_", (name or "").strip()).strip("_").lower()
    return s or f"tmpl_{new_id()[:6]}"


# =============================== Automation Rules ===============================
@router.get("/automation-rules")
async def list_rules(event: str = "", active: str = "",
                     user: dict = Depends(require_permission("automation_rules", "view"))):
    org = user.get("org_id", ORG_ID)
    q = {"org_id": org}
    if event:
        q["trigger.event"] = event
    if active in ("true", "false"):
        q["is_active"] = active == "true"
    rows = await db.automation_rules.find(q, {"_id": 0}).sort("created_at", -1).to_list(200)
    return {"data": serialize_doc(rows), "total": len(rows)}


@router.post("/automation-rules")
async def create_rule(p: AutomationRuleCreate,
                      user: dict = Depends(require_permission("automation_rules", "manage"))):
    if p.trigger_event not in VALID_EVENTS:
        raise HTTPException(400, f"trigger_event tidak valid ({', '.join(sorted(VALID_EVENTS))})")
    for a in p.actions:
        if a.get("type") not in VALID_ACTIONS:
            raise HTTPException(400, f"action type tidak valid: {a.get('type')}")
    ts = now_iso()
    doc = {
        "id": new_id(), "org_id": user.get("org_id", ORG_ID), "name": p.name,
        "trigger": {"event": p.trigger_event, "keywords": [k.lower() for k in p.keywords],
                    "no_response_days": p.no_response_days},
        "actions": p.actions, "is_active": p.is_active,
        "require_confirmation": p.require_confirmation, "executions": 0,
        "created_by": user.get("email"), "created_at": ts, "updated_at": ts,
    }
    await db.automation_rules.insert_one(doc)
    doc.pop("_id", None)
    return {"data": serialize_doc(doc)}


@router.put("/automation-rules/{rule_id}")
async def update_rule(rule_id: str, p: AutomationRuleUpdate,
                      user: dict = Depends(require_permission("automation_rules", "manage"))):
    org = user.get("org_id", ORG_ID)
    if not await db.automation_rules.find_one({"id": rule_id, "org_id": org}):
        raise HTTPException(404, "Rule tidak ditemukan")
    s = {"updated_at": now_iso()}
    if p.name is not None:
        s["name"] = p.name
    if p.trigger_event is not None:
        if p.trigger_event not in VALID_EVENTS:
            raise HTTPException(400, "trigger_event tidak valid")
        s["trigger.event"] = p.trigger_event
    if p.keywords is not None:
        s["trigger.keywords"] = [k.lower() for k in p.keywords]
    if p.no_response_days is not None:
        s["trigger.no_response_days"] = p.no_response_days
    if p.actions is not None:
        for a in p.actions:
            if a.get("type") not in VALID_ACTIONS:
                raise HTTPException(400, f"action type tidak valid: {a.get('type')}")
        s["actions"] = p.actions
    if p.is_active is not None:
        s["is_active"] = p.is_active
    if p.require_confirmation is not None:
        s["require_confirmation"] = p.require_confirmation
    await db.automation_rules.update_one({"id": rule_id, "org_id": org}, {"$set": s})
    fresh = await db.automation_rules.find_one({"id": rule_id, "org_id": org}, {"_id": 0})
    return {"data": serialize_doc(fresh)}


@router.post("/automation-rules/{rule_id}/toggle")
async def toggle_rule(rule_id: str,
                      user: dict = Depends(require_permission("automation_rules", "manage"))):
    org = user.get("org_id", ORG_ID)
    rule = await db.automation_rules.find_one({"id": rule_id, "org_id": org}, {"_id": 0})
    if not rule:
        raise HTTPException(404, "Rule tidak ditemukan")
    new_state = not rule.get("is_active", True)
    await db.automation_rules.update_one({"id": rule_id, "org_id": org},
                                         {"$set": {"is_active": new_state, "updated_at": now_iso()}})
    return {"data": {"id": rule_id, "is_active": new_state}}


@router.delete("/automation-rules/{rule_id}")
async def delete_rule(rule_id: str,
                      user: dict = Depends(require_permission("automation_rules", "manage"))):
    org = user.get("org_id", ORG_ID)
    res = await db.automation_rules.delete_one({"id": rule_id, "org_id": org})
    if not res.deleted_count:
        raise HTTPException(404, "Rule tidak ditemukan")
    return {"data": {"id": rule_id, "deleted": True}}


# =============================== WA Templates ===============================
@router.get("/wa-templates")
async def list_templates(category: str = "",
                         user: dict = Depends(require_permission("wa_templates", "view"))):
    org = user.get("org_id", ORG_ID)
    q = {"org_id": org}
    if category:
        q["category"] = category
    rows = await db.wa_templates.find(q, {"_id": 0}).sort("created_at", -1).to_list(200)
    usage = await gov.usage_map(org)
    for r in rows:
        r["used_by"] = usage.get(r.get("code"), [])
        r["hints"] = gov.category_hints(r.get("body"), r.get("category"))
    return {"data": serialize_doc(rows), "total": len(rows)}


@router.get("/wa-templates/reminder-mapping")
async def get_reminder_mapping(user: dict = Depends(require_permission("wa_templates", "view"))):
    """Template mana untuk pengingat apa — satu tempat (WA-14)."""
    org = user.get("org_id", ORG_ID)
    mapping = await gov.reminder_mapping(org)
    codes = {t["code"]: t for t in await db.wa_templates.find({"org_id": org}, {"_id": 0, "code": 1, "name": 1, "status": 1, "meta_status": 1}).to_list(300)}
    rows = []
    for kind, code in mapping.items():
        t = codes.get(code)
        rows.append({"kind": kind, "label": gov.REMINDER_KIND_META[kind][0], "help": gov.REMINDER_KIND_META[kind][1],
                     "setting_key": gov.TEMPLATE_KEYS[kind], "template_code": code,
                     "template_name": (t or {}).get("name"), "template_status": (t or {}).get("status"),
                     "meta_status": (t or {}).get("meta_status"), "missing": t is None})
    return {"data": rows}


@router.put("/wa-templates/reminder-mapping")
async def put_reminder_mapping(p: WaReminderMappingIn,
                               user: dict = Depends(require_permission("wa_templates", "manage"))):
    org = user.get("org_id", ORG_ID)
    live = (await gw.get_config(org))["effective_mode"] == "live"
    changed = []
    for kind, code in p.mapping.items():
        if kind not in gov.TEMPLATE_KEYS:
            raise HTTPException(400, f"Jenis pengingat '{kind}' tidak dikenal.")
        t = await db.wa_templates.find_one({"org_id": org, "code": code}, {"_id": 0})
        if not t:
            raise HTTPException(400, f"Template '{code}' tidak ada.")
        if t.get("status") != "approved":
            raise HTTPException(400, f"Template '{t['name']}' belum disetujui ({t.get('status')}); pengingat hanya boleh memakai template APPROVED.")
        if live and t.get("meta_status") != "APPROVED":
            raise HTTPException(400, f"Mode LIVE: template '{t['name']}' belum APPROVED di Meta ({t.get('meta_status')}).")
        await cfg.set_value(gov.TEMPLATE_KEYS[kind], code, actor=user.get("email"), org_id=org,
                            reason="Pemetaan pengingat dari layar Template WA")
        changed.append(kind)
    return {"data": await gov.reminder_mapping(org), "changed": changed}


@router.post("/wa-templates")
async def create_template(p: WaTemplateCreate,
                          user: dict = Depends(require_permission("wa_templates", "manage"))):
    org = user.get("org_id", ORG_ID)
    code = _slug(p.code) if (p.code or "").strip() else _slug(p.name)
    ts = now_iso()
    import wa_gateway as gw
    import wa_templates_meta as wtm
    live = (await gw.get_config(org))["effective_mode"] == "live"
    if (p.header_type or "none") not in ref.values("wa_template_header"):
        raise HTTPException(400, "header_type tidak valid.")
    salah = wtm.validate_variables(p.body, p.variables, p.header_text)
    if salah:
        raise HTTPException(400, salah)
    dup = await db.wa_templates.find_one({"org_id": org, "code": code}, {"_id": 0, "name": 1})
    if dup:
        # WA-09: dulu diam-diam jadi `promo_a1b2`; sekarang jujur.
        raise HTTPException(409, f"Kode '{code}' sudah dipakai template '{dup['name']}'. Pilih nama lain "
                                 "yang lebih spesifik (mis. tambahkan tujuan atau bulan).")
    doc = {
        "id": new_id(), "org_id": org, "code": code, "name": p.name, "category": p.category,
        "language": p.language, "body": p.body, "variables": p.variables,
        "examples": p.examples or {},
        "header_type": p.header_type or "none", "header_text": p.header_text,
        "header_sample_handle": p.header_sample_handle,
        **wtm.initial_fields(code, live),  # Fase 97A — status ikut Meta bila live; simulasi jujur
        "created_by": user.get("email"), "created_at": ts, "updated_at": ts,
    }
    if p.meta_name:
        doc["meta_name"] = p.meta_name
    if p.components:
        doc["components"] = p.components
    await db.wa_templates.insert_one(doc)
    doc.pop("_id", None)
    return {"data": serialize_doc(doc), "warnings": gov.category_hints(doc.get("body"), doc.get("category"))}


@router.put("/wa-templates/{tmpl_id}")
async def update_template(tmpl_id: str, p: WaTemplateUpdate,
                          user: dict = Depends(require_permission("wa_templates", "manage"))):
    org = user.get("org_id", ORG_ID)
    cur = await db.wa_templates.find_one({"id": tmpl_id, "org_id": org}, {"_id": 0})
    if not cur:
        raise HTTPException(404, "Template tidak ditemukan")
    s = {"updated_at": now_iso()}
    for f in ("name", "category", "language", "body", "variables", "examples", "status", "meta_name", "components",
              "header_type", "header_text", "header_sample_handle"):
        v = getattr(p, f)
        if v is not None:
            s[f] = v
    # WA-05: `approved` hanya boleh datang dari Meta (sync/webhook) atau pembuatan di mode simulasi.
    if s.get("status") == "approved" and cur.get("status") != "approved":
        raise HTTPException(400, "Status 'approved' tidak bisa diberikan dari layar. Ajukan template ke Meta "
                                 "lalu tarik statusnya; di mode simulasi template baru sudah otomatis approved.")
    # WA-06: setelah Meta menyetujui, isi & struktur parameter beku — perubahan = versi/template baru.
    if cur.get("meta_status") == "APPROVED":
        beku = gov.frozen_fields_changed(cur, s)
        if beku:
            raise HTTPException(400, "Template sudah APPROVED di Meta; %s tidak boleh diubah karena parameter "
                                     "yang dikirim harus sama dengan yang disetujui. Buat template baru (versi "
                                     "berikutnya) lalu ajukan ke Meta." % ", ".join(beku))
    if s.get("header_type") and s["header_type"] not in ref.values("wa_template_header"):
        raise HTTPException(400, "header_type tidak valid.")
    if any(k in s for k in ("body", "variables", "header_text")):
        import wa_templates_meta as wtm
        salah = wtm.validate_variables(s.get("body", cur.get("body")), s.get("variables", cur.get("variables")),
                                       s.get("header_text", cur.get("header_text")))
        if salah:
            raise HTTPException(400, salah)
    await db.wa_templates.update_one({"id": tmpl_id, "org_id": org}, {"$set": s})
    fresh = await db.wa_templates.find_one({"id": tmpl_id, "org_id": org}, {"_id": 0})
    return {"data": serialize_doc(fresh), "warnings": gov.category_hints(fresh.get("body"), fresh.get("category"))}


@router.post("/wa-templates/sync")
async def sync_templates(user: dict = Depends(require_permission("wa_templates", "manage"))):
    """Tarik status persetujuan dari Meta (butuh token + WABA ID). Di simulasi: 400 jujur."""
    import wa_templates_meta as wtm
    res = await wtm.sync(user.get("org_id", ORG_ID))
    if not res.get("ok"):
        raise HTTPException(400, f"{res.get('error_code')}: {res.get('detail')}")
    return {"data": {k: v for k, v in res.items() if k != "templates"}}


@router.post("/wa-templates/{tmpl_id}/submit")
async def submit_template(tmpl_id: str, user: dict = Depends(require_permission("wa_templates", "manage"))):
    """Ajukan template ke Meta. Di mode simulasi tidak ada yang dipalsukan → 400 dengan alasan."""
    import wa_templates_meta as wtm
    org = user.get("org_id", ORG_ID)
    tmpl = await db.wa_templates.find_one({"id": tmpl_id, "org_id": org}, {"_id": 0})
    if not tmpl:
        raise HTTPException(404, "Template tidak ditemukan")
    res = await wtm.submit(org, tmpl)
    if not res.get("ok"):
        raise HTTPException(400, f"{res.get('error_code')}: {res.get('detail')}")
    return {"data": serialize_doc(res["template"])}


@router.get("/wa-templates/{tmpl_id}/meta-preview")
async def template_meta_preview(tmpl_id: str, user: dict = Depends(require_permission("wa_templates", "view"))):
    import wa_templates_meta as wtm
    tmpl = await db.wa_templates.find_one({"id": tmpl_id, "org_id": user.get("org_id", ORG_ID)}, {"_id": 0})
    if not tmpl:
        raise HTTPException(404, "Template tidak ditemukan")
    return {"data": {"name": tmpl.get("meta_name") or tmpl["code"], "language": tmpl.get("language") or "id",
                     "category": (tmpl.get("category") or "utility").upper(), "components": wtm.meta_components(tmpl)}}


@router.delete("/wa-templates/{tmpl_id}")
async def delete_template(tmpl_id: str,
                          user: dict = Depends(require_permission("wa_templates", "manage"))):
    org = user.get("org_id", ORG_ID)
    cur = await db.wa_templates.find_one({"id": tmpl_id, "org_id": org}, {"_id": 0, "code": 1, "name": 1})
    if not cur:
        raise HTTPException(404, "Template tidak ditemukan")
    # WA-08: template yang masih dirujuk tidak boleh hilang diam-diam; sebutkan DI MANA ia dipakai.
    used = (await gov.usage_map(org)).get(cur.get("code"), [])
    if used:
        raise HTTPException(409, "Template '%s' masih dipakai oleh: %s. Ganti rujukannya dulu, baru hapus."
                            % (cur["name"], "; ".join(u["label"] for u in used[:6])))
    res = await db.wa_templates.delete_one({"id": tmpl_id, "org_id": org})
    if not res.deleted_count:
        raise HTTPException(404, "Template tidak ditemukan")
    return {"data": {"id": tmpl_id, "deleted": True}}


# =============================== Channels ===============================
@router.get("/channels")
async def list_channels(user: dict = Depends(require_permission("channels", "view"))):
    org = user.get("org_id", ORG_ID)
    rows = await db.channel_accounts.find({"org_id": org}, {"_id": 0}).sort("created_at", 1).to_list(100)
    return {"data": serialize_doc(rows), "total": len(rows)}


@router.post("/channels")
async def create_channel(p: ChannelCreate,
                         user: dict = Depends(require_permission("channels", "manage"))):
    org = user.get("org_id", ORG_ID)
    if await db.channel_accounts.find_one({"org_id": org, "code": p.code}):
        raise HTTPException(400, "Kode channel sudah dipakai")
    ts = now_iso()
    doc = {
        "id": new_id(), "org_id": org, "code": p.code, "channel": p.channel, "name": p.name,
        "mode": "simulation", "is_active": True, "created_by": user.get("email"), "created_at": ts,
    }
    await db.channel_accounts.insert_one(doc)
    doc.pop("_id", None)
    return {"data": serialize_doc(doc)}


@router.put("/channels/{ch_id}")
async def update_channel(ch_id: str, p: ChannelUpdate,
                         user: dict = Depends(require_permission("channels", "manage"))):
    org = user.get("org_id", ORG_ID)
    if not await db.channel_accounts.find_one({"id": ch_id, "org_id": org}):
        raise HTTPException(404, "Channel tidak ditemukan")
    s = {}
    if p.name is not None:
        s["name"] = p.name
    if p.is_active is not None:
        s["is_active"] = p.is_active
    if s:
        await db.channel_accounts.update_one({"id": ch_id, "org_id": org}, {"$set": s})
    fresh = await db.channel_accounts.find_one({"id": ch_id, "org_id": org}, {"_id": 0})
    return {"data": serialize_doc(fresh)}


# =============================== Capture events + attribution ===============================
@router.get("/capture-events")
async def list_capture_events(provider: str = "", status: str = "", skip: int = 0, limit: int = 50,
                              user: dict = Depends(require_permission("leads", "view"))):
    org = user.get("org_id", ORG_ID)
    skip, limit = parse_pagination(skip, limit)
    q = {"org_id": org}
    if provider:
        q["provider"] = provider
    if status:
        q["status"] = status
    total = await db.lead_capture_events.count_documents(q)
    rows = await db.lead_capture_events.find(q, {"_id": 0, "raw_payload": 0}).sort(
        "created_at", -1).skip(skip).limit(limit).to_list(limit)
    return {"data": serialize_doc(rows), "total": total}


@router.get("/capture-events/attribution")
async def attribution(user: dict = Depends(require_permission("leads", "view"))):
    """Ads/source attribution funnel: leads grouped by (source, campaign) with
    qualified/booked/won conversion.

    Fase 43: definisi "qualified"/"booked" TIDAK lagi ditulis ulang di sini — diambil dari
    `ads_report.FUNNEL_*` yang juga dipakai halaman Kampanye & Atribusi. Dulu dua layar bisa
    menjawab pertanyaan yang sama dengan angka berbeda karena masing-masing punya daftar
    tahapnya sendiri. Biaya iklan & CPL hidup di halaman Atribusi (`/attribution`).
    """
    import ads_report as adsrep
    org = user.get("org_id", ORG_ID)
    leads = await db.leads.find(
        {"org_id": org}, {"_id": 0, "source": 1, "campaign": 1, "stage": 1, "score_band": 1}).to_list(5000)
    groups = {}
    QUALIFIED = set(adsrep.FUNNEL_QUALIFIED)
    BOOKED = set(adsrep.FUNNEL_BOOKED)
    for l in leads:
        key = (l.get("source") or "unknown", l.get("campaign") or "-")
        g = groups.setdefault(key, {"source": key[0], "campaign": key[1], "leads": 0,
                                     "hot": 0, "qualified": 0, "booked": 0, "won": 0})
        g["leads"] += 1
        if l.get("score_band") == "hot":
            g["hot"] += 1
        st = l.get("stage")
        if st in QUALIFIED:
            g["qualified"] += 1
        if st in BOOKED:
            g["booked"] += 1
        if st == "won":
            g["won"] += 1
    rows = sorted(groups.values(), key=lambda x: x["leads"], reverse=True)
    # Merge CAPI conversion feedback (grouped by source+campaign).
    conv_rows = await db.conversion_events.find(
        {"org_id": org}, {"_id": 0, "source": 1, "campaign": 1, "value": 1}).to_list(20000)
    conv_by_key = {}
    for c in conv_rows:
        key = (c.get("source") or "unknown", c.get("campaign") or "-")
        cg = conv_by_key.setdefault(key, {"conversions": 0, "conversion_value": 0})
        cg["conversions"] += 1
        cg["conversion_value"] += int(c.get("value") or 0)
    for g in rows:
        cg = conv_by_key.get((g["source"], g["campaign"]), {"conversions": 0, "conversion_value": 0})
        g["conversions"] = cg["conversions"]
        g["conversion_value"] = cg["conversion_value"]
        g["conversion_pct"] = round(g["booked"] / g["leads"] * 100) if g["leads"] else 0
    totals = {
        "leads": sum(g["leads"] for g in rows), "hot": sum(g["hot"] for g in rows),
        "qualified": sum(g["qualified"] for g in rows), "booked": sum(g["booked"] for g in rows),
        "won": sum(g["won"] for g in rows),
        "conversions": sum(g["conversions"] for g in rows),
        "conversion_value": sum(g["conversion_value"] for g in rows),
    }
    return {"data": {"rows": rows, "totals": totals}}


@router.get("/capture-events/conversions")
async def list_conversions(platform: str = "", event: str = "", skip: int = 0, limit: int = 50,
                           user: dict = Depends(require_permission("leads", "view"))):
    """CAPI feedback audit: conversion events fed back to ad platforms (Lead / InitiateCheckout / Purchase)."""
    org = user.get("org_id", ORG_ID)
    skip, limit = parse_pagination(skip, limit)
    q = {"org_id": org}
    if platform:
        q["platform"] = platform
    if event:
        q["event_name"] = event
    total = await db.conversion_events.count_documents(q)
    rows = await db.conversion_events.find(q, {"_id": 0}).sort(
        "created_at", -1).skip(skip).limit(limit).to_list(limit)
    agg = {}
    for r in rows:
        agg[r.get("event_name", "?")] = agg.get(r.get("event_name", "?"), 0) + 1
    return {"data": rows, "total": total, "by_event": agg}


# ----------------------------- Fase 29b — Playbook WA per tahap lead -----------------------------
@router.get("/wa-playbooks")
async def list_playbooks(user: dict = Depends(require_permission("automation_rules", "view"))):
    """Playbook WA berbasis TAHAP lead (reminder, follow-up, blasting promo)."""
    import wa_playbooks as wp
    org = user.get("org_id", ORG_ID)
    await wp.ensure_playbooks(org)
    rows = await wp.playbooks(org)
    import wa_gateway as gw
    return {"data": serialize_doc(rows), "total": len(rows), "mode": (await gw.get_config(org))["effective_mode"]}


@router.put("/wa-playbooks/{key}")
async def update_playbook(key: str, payload: dict,
                          user: dict = Depends(require_permission("automation_rules", "manage"))):
    import wa_playbooks as wp
    org = user.get("org_id", ORG_ID)
    if key not in wp.BY_KEY:
        raise HTTPException(status_code=404, detail="Playbook tidak dikenal")
    allowed = {"is_active", "auto_send", "create_task", "cooldown_days", "template_code",
               "idle_days"}
    upd = {k: v for k, v in (payload or {}).items() if k in allowed}
    if not upd:
        raise HTTPException(status_code=400, detail=(
            "Tidak ada perubahan yang sah. Field: " + ", ".join(sorted(allowed))))
    if "cooldown_days" in upd and not (0 < float(upd["cooldown_days"]) <= 90):
        raise HTTPException(status_code=400, detail="Jeda kirim harus 1–90 hari.")
    if upd.get("template_code"):
        t = await db.wa_templates.find_one({"org_id": org, "code": upd["template_code"]})
        if not t:
            raise HTTPException(status_code=400, detail="Template WA tidak ditemukan.")
    upd["updated_at"] = now_iso()
    upd["updated_by"] = user.get("email")
    await wp.ensure_playbooks(org)
    await db.wa_playbooks.update_one({"org_id": org, "key": key}, {"$set": upd})
    return {"data": serialize_doc(await wp.playbook(org, key))}


@router.post("/wa-playbooks/{key}/run")
async def run_playbook_now(key: str, payload: dict = None,
                           user: dict = Depends(require_permission("automation_rules", "manage"))):
    """Jalankan playbook sekarang (mis. blasting promo) — hasil dilaporkan jujur."""
    import wa_playbooks as wp
    org = user.get("org_id", ORG_ID)
    if key not in wp.BY_KEY:
        raise HTTPException(status_code=404, detail="Playbook tidak dikenal")
    body = payload or {}
    res = await wp.run_playbook(org, key, actor=user.get("email"),
                                limit=int(body.get("limit") or 50),
                                force_send=bool(body.get("send")))
    return {"data": res}
