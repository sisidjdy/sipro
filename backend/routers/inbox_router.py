"""Inbox (WA conversations — SIMULATION mode) + messages.

EPIC 1.7: adds the WhatsApp **24h session window** rule (a free-form outbound reply
is only allowed while the window is open — i.e. within 24h of the last customer
message; otherwise a pre-approved template must be used), inbox filters, and the
`window_open` flag consumed by the composer UI.
"""
from fastapi import APIRouter, Depends, HTTPException

from db import db, ORG_ID
from core_utils import new_id, now_iso, serialize_doc, parse_pagination, due_in
from rbac import require_permission, scope_query, is_scoped_sales
from engine import emit, dispatch_pending, add_activity
from models import MessageCreate

router = APIRouter(prefix="/inbox", tags=["inbox"])


def _window_open(conv: dict) -> bool:
    import wa_gateway as gw  # SATU kebenaran aturan sesi 24 jam (dipakai gateway & outbox juga)
    return gw.window_open(conv)


def _decorate(conv: dict) -> dict:
    conv = serialize_doc(conv)
    conv["window_open"] = _window_open(conv)
    exp = conv.get("window_expires_at")
    conv["window_remaining_minutes"] = None
    if conv["window_open"] and exp:
        from datetime import datetime
        try:
            delta = datetime.fromisoformat(str(exp)) - datetime.fromisoformat(now_iso())
            conv["window_remaining_minutes"] = max(0, int(delta.total_seconds() // 60))
        except ValueError:
            pass
    return conv


async def _get_conv_scoped(conv_id: str, user: dict) -> dict:
    conv = await db.conversations.find_one({"id": conv_id}, {"_id": 0})
    if not conv:
        raise HTTPException(status_code=404, detail="Percakapan tidak ditemukan")
    if is_scoped_sales(user) and conv.get("owner") != user.get("email"):
        raise HTTPException(status_code=403, detail="Akses ditolak: bukan percakapan Anda")
    return conv


@router.get("")
async def list_conversations(skip: int = 0, limit: int = 50, filter: str = "all",
                             status: str = "", channel: str = "",
                             user: dict = Depends(require_permission("inbox", "view"))):
    """filter: all | mine | unanswered (last message from customer)."""
    skip, limit = parse_pagination(skip, limit)
    query = scope_query(user, {}, own_field="owner")
    if filter == "mine":
        query["owner"] = user.get("email")
    elif filter == "unanswered":
        query["last_direction"] = "in"
    if status:
        query["status"] = status
    if channel:
        query["channel"] = channel
    total = await db.conversations.count_documents(query)
    rows = await db.conversations.find(query, {"_id": 0}).sort(
        "last_message_at", -1).skip(skip).limit(limit).to_list(limit)
    return {"data": [_decorate(r) for r in rows], "total": total}


@router.get("/stats")
async def inbox_stats(user: dict = Depends(require_permission("inbox", "view"))):
    base = scope_query(user, {}, own_field="owner")
    total = await db.conversations.count_documents(base)
    mine = await db.conversations.count_documents({**base, "owner": user.get("email")})
    unanswered = await db.conversations.count_documents({**base, "last_direction": "in"})
    return {"data": {"all": total, "mine": mine, "unanswered": unanswered}}


@router.get("/{conv_id}")
async def get_conversation(conv_id: str, user: dict = Depends(require_permission("inbox", "view"))):
    conv = await _get_conv_scoped(conv_id, user)
    msgs = await db.messages.find({"conversation_id": conv_id}, {"_id": 0}).sort("created_at", 1).to_list(500)
    await db.conversations.update_one({"id": conv_id}, {"$set": {"unread": 0}})
    return {"data": {"conversation": _decorate(conv), "messages": serialize_doc(msgs)}}


@router.post("/{conv_id}/messages")
async def send_message(conv_id: str, payload: MessageCreate,
                       user: dict = Depends(require_permission("inbox", "create"))):
    conv = await _get_conv_scoped(conv_id, user)
    org = user.get("org_id", ORG_ID)
    ts = now_iso()
    direction = "in" if payload.direction == "in" else "out"

    template = None
    if direction == "out" and (payload.template_id or payload.template_code):
        q = {"org_id": org}
        q.update({"id": payload.template_id} if payload.template_id else {"code": payload.template_code})
        template = await db.wa_templates.find_one(q, {"_id": 0})
        if not template:
            raise HTTPException(status_code=404, detail="Template WA tidak ditemukan")

    # 24h session window: a free-form outbound reply requires an open window.
    if direction == "out" and template is None and not _window_open(conv):
        raise HTTPException(
            status_code=400,
            detail="Sesi 24 jam tertutup. Gunakan template WA (pra-approved) untuk memulai percakapan.")

    body = template["body"] if template else payload.body
    if template and conv.get("lead_id"):
        from engine import render_wa_body, wa_template_vars
        _lead_tpl = await db.leads.find_one({"id": conv["lead_id"]}, {"_id": 0})
        if _lead_tpl:
            body = render_wa_body(body, await wa_template_vars(_lead_tpl))
    if direction == "out":
        # Fase 94 — SEMUA pesan keluar lewat gateway tunggal (simulasi / Meta live), tercatat
        # dengan status jujur (simulated/sent/failed + alasan).
        import wa_gateway as gw
        msg = await gw.send(org, conv.get("contact_phone"), kind="inbox", body=body,
                            template=(template if template else None),
                            conversation_id=conv_id, actor=user.get("email"))
        if template:
            await db.messages.update_one({"id": msg["id"]}, {"$set": {"body": body}})
            msg["body"] = body
        if msg.get("status") == "failed":
            raise HTTPException(status_code=424, detail=f"Kirim WA gagal ({msg.get('error_code')}): {msg.get('error_detail')}")
    else:
        msg = {
            "id": new_id(), "org_id": org, "conversation_id": conv_id, "direction": "in",
            "body": body, "sender": "contact", "is_template": False, "template_id": None,
            "template_code": None, "kind": "inbox", "mode": "simulation", "status": "received",
            "created_at": ts,
        }
        await db.messages.insert_one(msg)

    # Only an INBOUND (customer) message (re)opens the 24h session window.
    conv_set = {"last_message_at": ts, "status": "active", "updated_at": ts, "last_direction": direction}
    if direction == "in":
        conv_set["window_expires_at"] = due_in(hours=24)
    await db.conversations.update_one({"id": conv_id}, {"$set": conv_set})

    # Fase 29b: percakapan WA kini BERPENGARUH pada lifecycle lead (dulu terputus:
    # kirim/terima pesan tidak mencatat kontak pertama, tidak muncul di timeline lead).
    lead_id = conv.get("lead_id")
    if lead_id:
        import lead_lifecycle as lc
        lead = await db.leads.find_one({"id": lead_id}, {"_id": 0})
        if lead:
            arah = "terkirim" if direction == "out" else "masuk"
            mode_lbl = "LIVE" if msg.get("mode") == "live" else "SIMULASI"
            await add_activity(entity_type="lead", entity_id=lead_id, type="system",
                               body=f"WhatsApp {arah} ({mode_lbl}): {body[:120]}",
                               actor=msg["sender"], org_id=org,
                               meta={"conversation_id": conv_id})
            if direction == "out":
                await lc.mark_first_contact(lead, actor=user.get("email"), channel="whatsapp",
                                            note=f"WA: {body[:80]}")

    if direction == "in":
        await emit("message.received", "conversation", conv_id, {"body": payload.body}, org_id=org)
        await dispatch_pending()

    msg.pop("_id", None)
    return {"data": serialize_doc(msg)}


# ----------------------------- EPIC 1.7 — Keyword-intent -> NBA -----------------------------
# Fase 29b: `booking -> won` DIHAPUS dari usulan chat. Tahap 'won' hanya lahir dari
# bukti legal deal (AJB/serah terima), tidak boleh diusulkan dari percakapan.
NEXT_STAGE = {
    "acquisition": "nurturing", "nurturing": "appointment", "appointment": "booking",
}
# Fallback intent lexicon (Indonesian) used when no automation rule matches.
INTENT_LEXICON = {
    "harga": "harga", "biaya": "harga", "cicilan": "harga", "dp": "harga",
    "kpr": "kpr", "kredit": "kpr", "bunga": "kpr", "bank": "kpr",
    "survey": "survey", "lihat": "survey", "kunjungan": "survey", "datang": "survey",
    "booking": "booking", "pesan": "booking", "bayar": "booking", "unit": "booking",
}


@router.get("/{conv_id}/nba")
async def conversation_nba(conv_id: str,
                           user: dict = Depends(require_permission("inbox", "view"))):
    """Analyse the last inbound message → detected intents + Next-Best-Action suggestions.

    Suggestions are built from (1) matching automation_rules (message.received) actions
    that reference real templates, and (2) a fallback intent lexicon + conversation state
    (window closed → recommend a template to reopen the 24h session).
    """
    conv = await _get_conv_scoped(conv_id, user)
    org = user.get("org_id", ORG_ID)
    last_in = await db.messages.find_one(
        {"conversation_id": conv_id, "direction": "in"}, {"_id": 0}, sort=[("created_at", -1)])
    body = ((last_in or {}).get("body") or "").lower()

    intents, suggestions = set(), []
    seen_templates = set()

    async def _add_template_suggestion(code, label):
        if not code or code in seen_templates:
            return
        tmpl = await db.wa_templates.find_one({"org_id": org, "code": code}, {"_id": 0})
        if tmpl:
            seen_templates.add(code)
            suggestions.append({"type": "send_template", "template_code": code,
                                "template_name": tmpl.get("name"), "label": label or f"Kirim: {tmpl.get('name')}"})

    # (1) automation rules keyword match
    rules = await db.automation_rules.find(
        {"org_id": org, "trigger.event": "message.received"}).to_list(100)
    for r in rules:
        for kw in r.get("trigger", {}).get("keywords", []):
            if kw and kw in body:
                intents.add(kw)
                for a in r.get("actions", []):
                    if a.get("type") == "send_template":
                        await _add_template_suggestion(
                            a.get("template_code"), f"Balas intent '{kw}' via template")
                        intents.add(f"rule:{r.get('name')}")

    # (2) fallback lexicon
    for kw, intent in INTENT_LEXICON.items():
        if kw in body:
            intents.add(intent)

    # window state → recommend a template to (re)open the session
    if not _window_open(conv):
        first = await db.wa_templates.find_one({"org_id": org, "status": "approved"}, {"_id": 0},
                                               sort=[("created_at", 1)])
        if first:
            await _add_template_suggestion(first.get("code"),
                                           "Sesi 24 jam tertutup — kirim template untuk membuka")

    # stage advancement suggestion (needs the linked lead)
    lead = None
    if conv.get("lead_id"):
        lead = await db.leads.find_one({"id": conv["lead_id"]}, {"_id": 0, "stage": 1, "name": 1})
    if lead:
        nxt = NEXT_STAGE.get(lead.get("stage"))
        if nxt:
            suggestions.append({"type": "advance_stage", "stage": nxt,
                                "label": f"Majukan stage lead ke '{nxt}'"})

    return {"data": {
        "intents": sorted(i for i in intents if not i.startswith("rule:")),
        "window_open": _window_open(conv),
        "last_inbound": (last_in or {}).get("body"),
        "suggestions": suggestions,
    }}
