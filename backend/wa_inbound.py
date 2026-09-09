"""wa_inbound — webhook Meta WhatsApp Cloud API (Fase 95): pesan masuk & status.

- Idempoten per `wamid` (indeks unik parsial `messages.provider_message_id`).
- Setiap pengirim yang belum menjadi lead masuk ANTREAN `wa_contacts` (status `new`) supaya
  bisa dijadikan lead lewat layar "Kontak WA → Lead" dengan pemeriksaan duplikat; bila setting
  `wa.auto_capture_lead` menyala, lead dibuat otomatis.
- Payload yang tidak dikenali TIDAK dibuang: masuk `lead_capture_failures` untuk diaudit.
"""
import hashlib
import hmac
import logging
from datetime import datetime, timezone

import capture_failures as cf
import settings_store
import wa_compliance as wcomp
import wa_contacts
import wa_gateway as gw
from core_utils import due_in, new_id, now_iso
from db import db, ORG_ID
from engine import add_activity, dispatch_pending, emit

logger = logging.getLogger("sipro.wa_inbound")

OPT_OUT_CONFIRM = ("Baik, Anda tidak akan menerima pesan promosi dari kami lagi. Informasi transaksi "
                   "(tagihan, dokumen) tetap kami kirim bila diperlukan.")
ACCOUNT_FIELDS = ("message_template_status_update", "phone_number_quality_update", "account_update",
                  "message_template_quality_update", "phone_number_name_update", "account_alerts")
MEDIA_TYPES = ("image", "document", "audio", "video", "sticker")


def is_meta_payload(raw) -> bool:
    return isinstance(raw, dict) and raw.get("object") == "whatsapp_business_account"


def verify_signature(app_secret: str, body: bytes, header: str) -> bool:
    if not app_secret:
        return None  # tidak bisa diverifikasi: tidak ada app secret
    if not header or not header.startswith("sha256="):
        return False
    digest = hmac.new(app_secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(digest, header.split("=", 1)[1])


def _ts(m: dict) -> str:
    try:
        return datetime.fromtimestamp(int(m.get("timestamp")), tz=timezone.utc).isoformat()
    except (TypeError, ValueError):
        return now_iso()


def describe_message(m: dict) -> dict:
    """-> {body, media, mtype} dari satu objek `messages[]` Meta."""
    mtype = m.get("type") or "unknown"
    media = None
    if mtype == "text":
        body = (m.get("text") or {}).get("body") or ""
    elif mtype in MEDIA_TYPES:
        obj = m.get(mtype) or {}
        media = {"type": mtype, "media_id": obj.get("id"), "mime_type": obj.get("mime_type"),
                 "sha256": obj.get("sha256"), "filename": obj.get("filename"),
                 "caption": obj.get("caption"), "url": None, "file_id": None}
        body = obj.get("caption") or f"[{mtype}]" + (f" {obj.get('filename')}" if obj.get("filename") else "")
    elif mtype == "location":
        loc = m.get("location") or {}
        body = f"Lokasi: {loc.get('name') or ''} {loc.get('latitude')},{loc.get('longitude')}".strip()
        media = {"type": "location", "latitude": loc.get("latitude"), "longitude": loc.get("longitude"),
                 "name": loc.get("name"), "address": loc.get("address")}
    elif mtype == "interactive":
        it = m.get("interactive") or {}
        pick = it.get("button_reply") or it.get("list_reply") or {}
        body = pick.get("title") or pick.get("id") or "[interaktif]"
    elif mtype == "button":
        body = (m.get("button") or {}).get("text") or "[tombol]"
    elif mtype == "reaction":
        body = (m.get("reaction") or {}).get("emoji") or "[reaksi]"
    elif mtype == "contacts":
        names = [((c.get("name") or {}).get("formatted_name") or "") for c in (m.get("contacts") or [])]
        body = "Kontak dibagikan: " + ", ".join(n for n in names if n)
    else:
        body = f"[{mtype} — jenis pesan belum didukung]"
    return {"body": body, "media": media, "mtype": mtype}


async def _store_media(org_id: str, adapter, media: dict, conv_id: str) -> dict:
    if not media or not media.get("media_id") or getattr(adapter, "mode", "") != "live":
        return media
    try:
        res = await adapter.download_media(media["media_id"])
        if not res.get("ok"):
            media["error"] = f"{res.get('error_code')}: {res.get('error_detail')}"
            return media
        import storage
        rec = await storage.save_file(
            data=res["data"], filename=media.get("filename") or f"wa-{media['media_id']}",
            content_type=res.get("mime_type") or "application/octet-stream", org_id=org_id,
            owner_type="conversation", owner_id=conv_id, uploaded_by="whatsapp", tag="wa_media",
            optimize=False)
        media["file_id"] = rec.get("id")
        media["url"] = f"/api/files/{rec.get('id')}/download" if rec.get("id") else None
    except Exception as e:  # noqa: BLE001
        media["error"] = str(e)[:160]
    return media


async def _conversation_for(org_id: str, phone: str, name: str, lead: dict) -> dict:
    conv = await db.conversations.find_one({"org_id": org_id, "channel": "whatsapp", "contact_phone": phone},
                                           {"_id": 0}, sort=[("created_at", -1)])
    ts = now_iso()
    if conv:
        upd = {}
        if name and (not conv.get("contact_name") or conv.get("contact_name") == "Lead Baru"):
            upd["contact_name"] = name
        if lead and not conv.get("lead_id"):
            upd.update({"lead_id": lead["id"], "owner": lead.get("assigned_to")})
        if upd:
            await db.conversations.update_one({"id": conv["id"]}, {"$set": upd})
            conv.update(upd)
        return conv
    conv = {"id": new_id(), "org_id": org_id, "channel": "whatsapp", "contact_phone": phone,
            "contact_name": name or (lead or {}).get("name") or phone, "lead_id": (lead or {}).get("id"),
            "owner": (lead or {}).get("assigned_to"), "status": "new", "mode": "simulation",
            "unread": 0, "last_message_at": None, "last_direction": None,
            "window_expires_at": None, "created_at": ts, "updated_at": ts}
    await db.conversations.insert_one(dict(conv))
    return conv


async def _handle_message(org_id: str, m: dict, profile_names: dict, adapter, mode: str) -> dict:
    wamid = m.get("id")
    if wamid and await db.messages.find_one({"provider_message_id": wamid}, {"_id": 1}):
        return {"skipped": "duplicate"}
    phone = gw.valid_phone("+" + str(m.get("from") or "").lstrip("+"))
    if not phone:
        return {"skipped": "invalid_phone", "from": m.get("from")}
    name = profile_names.get(str(m.get("from")))
    desc = describe_message(m)
    lead = await db.leads.find_one({"org_id": org_id, "phone": phone}, {"_id": 0})
    conv = await _conversation_for(org_id, phone, name, lead)
    ts = _ts(m)
    media = await _store_media(org_id, adapter, desc["media"], conv["id"])
    msg = {"id": new_id(), "org_id": org_id, "conversation_id": conv["id"], "direction": "in",
           "body": desc["body"], "sender": "contact", "kind": "inbox", "mtype": desc["mtype"],
           "media": media, "provider_message_id": wamid, "mode": mode, "status": "received",
           "context": (m.get("context") or {}).get("id"), "created_at": ts}
    await db.messages.insert_one(dict(msg))
    await db.conversations.update_one({"id": conv["id"]}, {
        "$set": {"last_message_at": ts, "last_direction": "in", "status": "active", "updated_at": ts,
                 "window_expires_at": due_in(hours=24), "mode": mode},
        "$inc": {"unread": 1}})
    opt_out = wcomp.detect_opt_out(desc["body"])
    contact = await wa_contacts.upsert_from_inbound(org_id, phone=phone, name=name, body=desc["body"],
                                                    conversation_id=conv["id"], lead=lead, at=ts,
                                                    opt_out=opt_out)
    out = {"conversation_id": conv["id"], "lead_id": (lead or {}).get("id"), "contact_id": contact["id"],
           "captured": False}
    if lead:
        await add_activity(entity_type="lead", entity_id=lead["id"], type="system",
                           body=f"WhatsApp masuk ({'LIVE' if mode == 'live' else 'SIMULASI'}): {desc['body'][:120]}",
                           actor="contact", org_id=org_id, meta={"conversation_id": conv["id"], "wamid": wamid})
    if opt_out:
        reg = await wcomp.register_opt_out(org_id, phone, source="inbound_keyword", conversation_id=conv["id"],
                                           note=desc["body"][:120])
        out["opt_out"] = True
        if reg["created"]:  # konfirmasi SATU kali saja
            await gw.send(org_id, phone, kind="notification", body=OPT_OUT_CONFIRM, conversation_id=conv["id"],
                          actor="system", category="service")
    if not lead and not opt_out and await settings_store.get("wa.auto_capture_lead", org_id=org_id):
        res = await wa_contacts.capture(org_id, ids=[contact["id"]], actor="webhook")
        out["captured"] = res["created"] > 0
        out["lead_id"] = (res["lead_ids"] or [None])[0]
    await emit("message.received", "conversation", conv["id"], {"body": desc["body"]}, org_id=org_id)
    return out


async def _handle_status(org_id: str, s: dict) -> dict:
    wamid, status = s.get("id"), s.get("status")
    if not wamid or not status:
        return {"skipped": "no_id"}
    err = (s.get("errors") or [{}])[0]
    upd = {"status": status, "status_at": _ts(s)}
    if status == "failed":
        upd["error_code"] = str(err.get("code") or "")
        upd["error_detail"] = err.get("title") or err.get("message") or (err.get("error_data") or {}).get("details")
    r = await db.messages.update_one({"provider_message_id": wamid, "org_id": org_id}, {"$set": upd})
    await db.broadcast_recipients.update_one({"provider_message_id": wamid}, {"$set": upd})
    return {"matched": r.matched_count, "status": status}


async def process_meta_payload(raw: dict, org_id: str = ORG_ID, *, mode: str = None) -> dict:
    """Satu pintu: dipakai webhook nyata & simulasi (payload berbentuk SAMA)."""
    adapter, cfg = await gw.adapter_for(org_id)
    mode = mode or cfg["effective_mode"]
    summary = {"messages": 0, "statuses": 0, "duplicates": 0, "leads_linked": 0, "captured": 0,
               "unknown": 0, "results": []}
    for entry in raw.get("entry") or []:
        for change in entry.get("changes") or []:
            value = change.get("value") or {}
            field = change.get("field")
            if field in ACCOUNT_FIELDS:
                summary["account_events"] = summary.get("account_events", 0) + 1
                summary["results"].append(await _handle_account_event(org_id, field, value))
                continue
            if field not in (None, "messages"):
                summary["unknown"] += 1
                await cf.record("whatsapp", {"field": change.get("field"), "value": value},
                                f"Field webhook '{change.get('field')}' belum ditangani", org_id=org_id)
                continue
            names = {c.get("wa_id"): (c.get("profile") or {}).get("name") for c in (value.get("contacts") or [])}
            for m in value.get("messages") or []:
                res = await _handle_message(org_id, m, names, adapter, mode)
                summary["results"].append(res)
                if res.get("skipped") == "duplicate":
                    summary["duplicates"] += 1
                elif "skipped" not in res:
                    summary["messages"] += 1
                    summary["leads_linked"] += 1 if res.get("lead_id") and not res.get("captured") else 0
                    summary["captured"] += 1 if res.get("captured") else 0
            for s in value.get("statuses") or []:
                await _handle_status(org_id, s)
                summary["statuses"] += 1
            for e in value.get("errors") or []:
                await cf.record("whatsapp", e, f"Meta melaporkan error: {e.get('title') or e.get('code')}",
                                org_id=org_id)
    if summary["messages"]:
        await dispatch_pending()
    return summary


async def _notify_admins(org_id: str, title: str, body: str) -> int:
    from engine import create_notification
    n = 0
    async for u in db.users.find({"org_id": org_id, "role": {"$in": ["super_admin", "owner"]}, "is_active": {"$ne": False}},
                                 {"_id": 0, "email": 1}):
        await create_notification(user_email=u["email"], title=title, body=body, type="info",
                                  related_entity_type="wa_channel", related_entity_id=gw.CHANNEL_CODE, org_id=org_id)
        n += 1
    return n


async def _handle_account_event(org_id: str, field: str, value: dict) -> dict:
    """97A/98C — status template, kualitas nomor, perubahan akun → catat + notifikasi super admin."""
    ts = now_iso()
    ch = await gw._channel(org_id)
    if field == "message_template_status_update":
        import wa_templates_meta as wtm
        res = await wtm.on_status_webhook(org_id, value)
        if res["status"] == "rejected":
            await _notify_admins(org_id, "Template WhatsApp ditolak Meta",
                                 f"{value.get('message_template_name')}: {value.get('reason') or res['meta_status']}")
        return {"event": field, **res}
    if field in ("phone_number_quality_update", "phone_number_name_update"):
        upd = {"quality_rating": value.get("current_limit") or value.get("event"), "quality_event": value.get("event"),
               "quality_updated_at": ts}
        await db.channel_accounts.update_one({"id": ch["id"]}, {"$set": {"last_quality": {**value, "at": ts}}})
        await _notify_admins(org_id, "Kualitas / tier nomor WhatsApp berubah",
                             f"{value.get('event')} · batas {value.get('current_limit')} (sebelumnya {value.get('old_limit')})")
        return {"event": field, **upd}
    await db.channel_accounts.update_one({"id": ch["id"]}, {"$set": {"last_account_event": {**value, "field": field, "at": ts}}})
    await _notify_admins(org_id, "Perubahan akun WhatsApp Business",
                         f"{field}: {value.get('event') or value.get('decision') or ''} {value.get('ban_info') or ''}".strip())
    return {"event": field, "recorded": True}


def build_meta_payload(*, phone: str, name: str = None, text: str = None, mtype: str = "text",
                       wamid: str = None, filename: str = None) -> dict:
    """Bentuk payload Meta asli untuk simulasi & pengujian."""
    wa_id = phone.lstrip("+")
    import time
    wamid = wamid or f"wamid.SIM{new_id().replace('-', '')[:24]}"
    msg = {"from": wa_id, "id": wamid, "timestamp": str(int(time.time())), "type": mtype}
    if mtype == "text":
        msg["text"] = {"body": text or ""}
    elif mtype in MEDIA_TYPES:
        msg[mtype] = {"id": f"media-{new_id()[:8]}", "mime_type": "image/jpeg" if mtype == "image" else "application/pdf",
                      "caption": text, "filename": filename}
    elif mtype == "location":
        msg["location"] = {"latitude": -6.2, "longitude": 106.8, "name": text or "Lokasi"}
    return {"object": "whatsapp_business_account", "entry": [{"id": "SIM-WABA", "changes": [{
        "field": "messages", "value": {"messaging_product": "whatsapp",
                                       "metadata": {"display_phone_number": "0", "phone_number_id": "SIM"},
                                       "contacts": [{"profile": {"name": name or ""}, "wa_id": wa_id}] if name else [],
                                       "messages": [msg]}}]}]}
