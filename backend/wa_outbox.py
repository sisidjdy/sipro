"""wa_outbox — antrean kirim WhatsApp dengan batas laju & percobaan ulang (Fase 95F/97C/97D).

Broadcast dan pengiriman massal TIDAK memanggil Meta langsung: setiap penerima menjadi satu
baris `wa_outbox` (queued → sending → sent|simulated|failed). Galat sementara (429/5xx/jaringan/
130429/131048/131056) diulang maks 3× dengan backoff; galat permanen (132xxx, 131026, 131047,
opt_out, template_not_approved, invalid_phone) tidak diulang. Status akhir sent→delivered→read
hanya berubah lewat webhook `statuses[]` (wa_inbound), bukan dikarang.
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

import wa_compliance as wcomp
import wa_gateway as gw
from core_utils import new_id, now_iso
from db import db, ORG_ID

logger = logging.getLogger("sipro.wa_outbox")
COLL = "wa_outbox"
MAX_ATTEMPTS = 3
BACKOFF_SECONDS = (30, 120, 600)
TRANSIENT_CODES = {"network", "429", "130429", "131048", "131056", "500", "502", "503", "504"}


def is_transient(code) -> bool:
    c = str(code or "")
    return c in TRANSIENT_CODES or (c.isdigit() and 500 <= int(c) < 600)


def _later(seconds: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()


async def enqueue(org_id: str, *, to: str, kind: str, category: str, body: str = None, template: dict = None,
                  template_params: list = None, document: dict = None, conversation_id: str = None,
                  ref: dict = None, actor: str = "system", broadcast_id: str = None,
                  recipient_id: str = None, not_before: str = None) -> dict:
    ts = now_iso()
    doc = {"id": new_id(), "org_id": org_id, "to": to, "kind": kind, "category": category, "body": body,
           "template_id": (template or {}).get("id"), "template_code": (template or {}).get("code"),
           "template_params": template_params or [], "document": document, "conversation_id": conversation_id,
           "ref": ref or {}, "actor": actor, "broadcast_id": broadcast_id, "recipient_id": recipient_id,
           "status": "queued", "attempts": 0, "not_before": not_before or ts, "message_id": None,
           "provider_message_id": None, "error_code": None, "error_detail": None,
           "created_at": ts, "updated_at": ts}
    await db.wa_outbox.insert_one(dict(doc))
    return doc


async def _send_item(item: dict) -> dict:
    template = None
    if item.get("template_id") or item.get("template_code"):
        q = {"org_id": item["org_id"]}
        q.update({"id": item["template_id"]} if item.get("template_id") else {"code": item["template_code"]})
        template = await db.wa_templates.find_one(q, {"_id": 0})
        if not template:
            return {"status": "failed", "error_code": "template_missing", "error_detail": "Template WA sudah dihapus.",
                    "id": None, "provider_message_id": None}
    conv_id = item.get("conversation_id")
    if not conv_id:
        conv = await db.conversations.find_one({"org_id": item["org_id"], "channel": "whatsapp",
                                                "contact_phone": item["to"]}, {"_id": 0, "id": 1},
                                               sort=[("created_at", -1)])
        conv_id = (conv or {}).get("id")
    return await gw.send(item["org_id"], item["to"], kind=item["kind"], body=item.get("body"), template=template,
                         template_params=item.get("template_params"), document=item.get("document"),
                         conversation_id=conv_id, actor=item.get("actor") or "outbox", ref=item.get("ref"),
                         category=item.get("category"))


async def _finalize(item: dict, msg: dict) -> dict:
    ts = now_iso()
    attempts = int(item.get("attempts") or 0) + 1
    status = msg.get("status")
    upd = {"attempts": attempts, "updated_at": ts, "message_id": msg.get("id"),
           "provider_message_id": msg.get("provider_message_id"), "error_code": msg.get("error_code"),
           "error_detail": msg.get("error_detail"), "last_attempt_at": ts}
    if status == "failed" and is_transient(msg.get("error_code")) and attempts < MAX_ATTEMPTS:
        upd.update({"status": "queued", "not_before": _later(BACKOFF_SECONDS[min(attempts - 1, 2)])})
    else:
        upd["status"] = status
        upd["sent_at" if status in ("sent", "simulated") else "failed_at"] = ts
    await db.wa_outbox.update_one({"id": item["id"]}, {"$set": upd})
    if item.get("recipient_id"):
        await db.broadcast_recipients.update_one({"id": item["recipient_id"]}, {"$set": {
            "status": upd["status"], "message_id": msg.get("id"), "provider_message_id": msg.get("provider_message_id"),
            "error_code": msg.get("error_code"), "error_detail": msg.get("error_detail"), "status_at": ts,
            "attempts": attempts, "sent_at": ts if upd["status"] in ("sent", "simulated") else None}})
    return upd


async def _active_broadcasts(org_id: str) -> set:
    rows = await db.broadcasts.find({"org_id": org_id, "status": {"$in": ["paused", "cancelled"]}},
                                    {"_id": 0, "id": 1}).to_list(500)
    return {r["id"] for r in rows}


async def process(org_id: str = ORG_ID, *, limit: int = None, ignore_window: bool = False) -> dict:
    """Satu putaran: hormati jam kirim & batas laju, kirim yang jatuh tempo, perbarui broadcast."""
    win = await wcomp.send_window(org_id)
    out = {"processed": 0, "sent": 0, "simulated": 0, "failed": 0, "retry": 0, "skipped_window": False,
           "rate": win["rate"], "notes": []}
    if not ignore_window and not wcomp.in_send_window(win["start"], win["end"]):
        out["skipped_window"] = True
        out["notes"].append(f"Di luar jam kirim {win['start']}–{win['end']} WIB; antrean menunggu.")
        return out
    limit = limit or win["rate"] * 5
    halted = await _active_broadcasts(org_id)
    q = {"org_id": org_id, "status": "queued", "not_before": {"$lte": now_iso()}}
    items = await db.wa_outbox.find(q, {"_id": 0}).sort([("created_at", 1)]).limit(limit * 2).to_list(limit * 2)
    touched = set()
    for item in items:
        if out["processed"] >= limit:
            break
        if item.get("broadcast_id") in halted:
            continue
        claim = await db.wa_outbox.update_one({"id": item["id"], "status": "queued"},
                                          {"$set": {"status": "sending", "updated_at": now_iso()}})
        if not claim.modified_count:
            continue
        try:
            msg = await _send_item(item)
        except Exception as e:  # noqa: BLE001 — gangguan tak terduga = galat sementara
            msg = {"status": "failed", "error_code": "network", "error_detail": str(e)[:200], "id": None,
                   "provider_message_id": None}
        upd = await _finalize(item, msg)
        out["processed"] += 1
        key = "retry" if upd["status"] == "queued" else upd["status"]
        out[key] = out.get(key, 0) + 1
        if item.get("broadcast_id"):
            touched.add(item["broadcast_id"])
        await asyncio.sleep(1.0 / win["rate"])
    for bid in touched:
        await refresh_broadcast(org_id, bid)
    return out


async def refresh_broadcast(org_id: str, bid: str) -> dict:
    """Angka broadcast = jumlah baris penerima (aturan Fase 92: kartu = rinciannya)."""
    b = await db.broadcasts.find_one({"id": bid, "org_id": org_id}, {"_id": 0})
    if not b:
        return None
    counts = {}
    async for r in db.broadcast_recipients.find({"org_id": org_id, "broadcast_id": bid}, {"_id": 0, "status": 1}):
        counts[r.get("status")] = counts.get(r.get("status"), 0) + 1
    pending = counts.get("queued", 0) + counts.get("sending", 0)
    agg = {"queued": pending, "sent": counts.get("sent", 0), "simulated": counts.get("simulated", 0),
           "delivered": counts.get("delivered", 0), "read": counts.get("read", 0), "failed": counts.get("failed", 0),
           "skipped": counts.get("skipped", 0), "cancelled": counts.get("cancelled", 0)}
    status = b.get("status")
    if status not in ("paused", "cancelled"):
        status = "sending" if pending and pending < b.get("total", 0) else ("queued" if pending else "completed")
    upd = {**agg, "status": status, "updated_at": now_iso()}
    if status == "completed" and not b.get("completed_at"):
        upd["completed_at"] = now_iso()
    await db.broadcasts.update_one({"id": bid}, {"$set": upd})
    return upd


async def set_broadcast_state(org_id: str, bid: str, action: str, *, actor: str) -> dict:
    """pause | resume | cancel — hanya menyentuh baris yang masih antre."""
    b = await db.broadcasts.find_one({"id": bid, "org_id": org_id}, {"_id": 0})
    if not b:
        return None
    ts = now_iso()
    if action == "pause" and b["status"] in ("queued", "sending"):
        await db.broadcasts.update_one({"id": bid}, {"$set": {"status": "paused", "paused_at": ts, "paused_by": actor}})
    elif action == "resume" and b["status"] == "paused":
        await db.broadcasts.update_one({"id": bid}, {"$set": {"status": "sending", "resumed_at": ts}})
    elif action == "cancel" and b["status"] in ("queued", "sending", "paused"):
        await db.wa_outbox.update_many({"org_id": org_id, "broadcast_id": bid, "status": "queued"},
                                   {"$set": {"status": "cancelled", "updated_at": ts}})
        await db.broadcast_recipients.update_many({"org_id": org_id, "broadcast_id": bid, "status": "queued"},
                                                  {"$set": {"status": "cancelled", "status_at": ts}})
        await db.broadcasts.update_one({"id": bid}, {"$set": {"status": "cancelled", "cancelled_at": ts,
                                                              "cancelled_by": actor}})
    else:
        return {"error": f"Aksi '{action}' tidak berlaku untuk broadcast berstatus {b['status']}."}
    await refresh_broadcast(org_id, bid)
    return await db.broadcasts.find_one({"id": bid}, {"_id": 0})


async def tick() -> dict:
    out = {}
    for org in (await db.orgs.distinct("id") or [ORG_ID]):
        try:
            res = await process(org)
            if res["processed"]:
                out[org] = res
        except Exception:  # noqa: BLE001
            logger.exception("wa_outbox gagal untuk org %s", org)
    return out
