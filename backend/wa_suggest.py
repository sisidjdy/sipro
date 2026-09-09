"""wa_suggest — Balasan Cerdas (Fase 99): saran balasan cepat berbasis ATURAN, tanpa LLM.

Sumber saran, berurutan:
  1. Playbook tahap lead (`wa_playbooks`) yang menyasar tahap lead saat ini → template-nya.
  2. Kata kunci pesan masuk terakhir yang cocok dengan `automation_rules` (aksi send_template).
  3. Sapaan kontak pertama bila nomor belum menjadi lead.
Setiap saran membawa `body` yang SUDAH dirender dari data lead, `template_code`, `ready`
(template approved), dan `usable` sesuai sesi 24 jam (teks bebas hanya di dalam sesi).
"""
import re

from db import db
from engine import render_wa_body, wa_template_vars
import wa_playbooks as wp


async def _templates(org: str) -> dict:
    rows = await db.wa_templates.find({"org_id": org}, {"_id": 0}).to_list(200)
    return {t["code"]: t for t in rows}


def _item(source: str, title: str, tmpl: dict, body: str, window_open: bool, reason: str) -> dict:
    ready = bool(tmpl) and tmpl.get("status") == "approved"
    return {"source": source, "title": title, "template_code": (tmpl or {}).get("code"),
            "template_name": (tmpl or {}).get("name"), "ready": ready, "body": body, "reason": reason,
            "usable": ready or window_open,
            "hint": (None if ready else "Template belum approved — hanya bisa dikirim sebagai teks bebas di dalam sesi 24 jam.")}


async def suggestions(org: str, phone: str, name: str, lead: dict, window_open: bool, last_inbound: str) -> dict:
    tmpls = await _templates(org)
    vars_ = await wa_template_vars(lead) if lead else {"nama": name or "Bapak/Ibu", "name": name or "Bapak/Ibu"}
    out, seen = [], set()

    def push(item):
        key = item.get("template_code") or item["body"]
        if key in seen:
            return
        seen.add(key)
        out.append(item)

    stage = (lead or {}).get("stage")
    for p in await wp.playbooks(org):
        if not p.get("is_active", True) or (stage and stage not in (p.get("stages") or [])):
            continue
        if not stage and p.get("key") != "first_touch":
            continue
        t = tmpls.get(p.get("template_code"))
        if not t:
            continue
        push(_item("playbook", p.get("name"), t, render_wa_body(t.get("body", ""), vars_), window_open,
                   f"Playbook tahap '{stage or 'kontak baru'}'"))

    text = (last_inbound or "").lower()
    if text:
        rules = await db.automation_rules.find({"org_id": org, "is_active": True, "trigger.event": "message.received"},
                                               {"_id": 0}).to_list(50)
        for r in rules:
            kws = [k for k in (r.get("trigger") or {}).get("keywords") or [] if re.search(r"\b%s\b" % re.escape(k), text)]
            if not kws:
                continue
            for a in r.get("actions") or []:
                t = tmpls.get(a.get("template_code")) if a.get("type") == "send_template" else None
                if t:
                    push(_item("keyword", r.get("name"), t, render_wa_body(t.get("body", ""), vars_), window_open,
                               f"Pesan terakhir menyebut: {', '.join(kws)}"))

    if not lead and "welcome" in tmpls and "welcome" not in seen:
        t = tmpls["welcome"]
        push(_item("first_touch", "Sapaan kontak pertama", t, render_wa_body(t.get("body", ""), vars_), window_open,
                   "Nomor belum menjadi lead"))
    return {"stage": stage, "lead_id": (lead or {}).get("id"), "window_open": window_open, "items": out[:6]}
