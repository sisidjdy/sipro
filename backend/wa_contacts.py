"""wa_contacts — antrean kontak WhatsApp → lead (lead capture dengan deteksi duplikat).

Sumber kontak: webhook (pesan masuk), impor manual (tempel teks / CSV / VCF ekspor kontak
HP), atau satu nomor dari Inbox. Setiap kontak dicocokkan ke `leads` & `customers` per
nomor E.164; keputusan duplikat ada di tangan pemakai (lewati / tautkan / buat lead ulang
untuk customer lama). Nomor lead UNIK per organisasi (`uq_leads_phone`), jadi "paksa buat
baru" untuk nomor yang sudah jadi LEAD tidak mungkin — dijelaskan jujur di UI.
"""
import csv
import io
import re

import wa_gateway as gw
from core_utils import new_id, now_iso
from db import db, ORG_ID
from engine import add_activity, process_lead_capture

COLL = "wa_contacts"
STATUSES = ("new", "captured", "linked", "skipped", "invalid")
PHONE_TOKEN = re.compile(r"(?:\+?62|0)[\s\-.()]*8(?:[\s\-.()]*\d){7,12}")
NAME_COLS = ("nama", "name", "kontak", "contact", "first name", "display name", "fn")
PHONE_COLS = ("phone", "telp", "telepon", "nomor", "no hp", "hp", "wa", "whatsapp", "mobile", "tel", "number")


# ------------------------------------------------------------------ parsing impor
def _clean_phone(tok: str) -> str:
    return gw.valid_phone(re.sub(r"[^\d+]", "", tok))


def _parse_vcf(text: str) -> list:
    rows, cur = [], None
    for line in text.splitlines():
        l = line.strip()
        if l.upper() == "BEGIN:VCARD":
            cur = {"name": "", "phones": []}
        elif l.upper() == "END:VCARD" and cur is not None:
            for p in cur["phones"] or [""]:
                rows.append({"name": cur["name"], "phone": p, "raw": l})
            cur = None
        elif cur is not None:
            key, _, val = l.partition(":")
            k = key.split(";")[0].upper()
            if k == "FN" and val:
                cur["name"] = val.strip()
            elif k == "TEL" and val:
                cur["phones"].append(val.strip())
    return rows


def _parse_csv(text: str) -> list:
    sample = text[:2048]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    reader = csv.reader(io.StringIO(text), dialect)
    rows = list(reader)
    if not rows:
        return []
    header = [c.strip().lower() for c in rows[0]]
    ni = next((i for i, h in enumerate(header) if any(h == c or h.startswith(c) for c in NAME_COLS)), None)
    pi = next((i for i, h in enumerate(header) if any(c in h for c in PHONE_COLS)), None)
    out = []
    if pi is not None:
        for r in rows[1:]:
            if len(r) > pi:
                out.append({"name": (r[ni].strip() if ni is not None and len(r) > ni else ""),
                            "phone": r[pi].strip(), "raw": ",".join(r)})
        return out
    for r in rows:
        line = " ".join(r).strip()
        m = PHONE_TOKEN.search(line)
        if m:
            name = re.sub(r"[\s,;:\-|]+$", "", line[:m.start()]).strip() or \
                re.sub(r"^[\s,;:\-|]+", "", line[m.end():]).strip()
            out.append({"name": name, "phone": m.group(0), "raw": line, "message": ""})
        elif line and out:
            # baris tanpa nomor setelah sebuah kontak = isi pesan pertama kontak tersebut
            out[-1]["message"] = (out[-1]["message"] + " " + line).strip()[:300]
    return out


def parse_import(text: str) -> list:
    """Teks bebas / CSV / VCF -> [{name, phone(raw), raw}]."""
    text = (text or "").strip().lstrip("\ufeff")
    if not text:
        return []
    if "BEGIN:VCARD" in text.upper():
        return _parse_vcf(text)
    return _parse_csv(text)


# ------------------------------------------------------------------ analisis duplikat
async def analyze(org_id: str, rows: list) -> list:
    """Normalisasi + cocokkan ke leads/customers/antrean; tandai duplikat dalam berkas."""
    seen = set()
    out = []
    phones = [p for p in {_clean_phone(r.get("phone") or "") for r in rows} if p]
    leads = {l["phone"]: l for l in await db.leads.find(
        {"org_id": org_id, "phone": {"$in": phones}},
        {"_id": 0, "id": 1, "name": 1, "phone": 1, "stage": 1, "assigned_to": 1}).to_list(5000)}
    custs = {c["phone"]: c for c in await db.customers.find(
        {"org_id": org_id, "phone": {"$in": phones}},
        {"_id": 0, "id": 1, "name": 1, "phone": 1}).to_list(5000)}
    queue = {q["phone"]: q for q in await db[COLL].find(
        {"org_id": org_id, "phone": {"$in": phones}}, {"_id": 0, "id": 1, "phone": 1, "status": 1}).to_list(5000)}
    for r in rows:
        phone = _clean_phone(r.get("phone") or "")
        item = {"name": (r.get("name") or "").strip(), "phone_raw": r.get("phone"), "phone": phone,
                "message": (r.get("message") or "").strip() or None,
                "valid": bool(phone), "dup_in_batch": False, "match_lead": None, "match_customer": None,
                "in_queue": None}
        if phone:
            if phone in seen:
                item["dup_in_batch"] = True
            seen.add(phone)
            item["match_lead"] = leads.get(phone)
            item["match_customer"] = custs.get(phone)
            item["in_queue"] = (queue.get(phone) or {}).get("status")
        item["dup_kind"] = ("lead" if item["match_lead"] else "customer" if item["match_customer"] else None)
        out.append(item)
    return out


def summarize(items: list) -> dict:
    return {"total": len(items), "valid": sum(1 for i in items if i["valid"]),
            "invalid": sum(1 for i in items if not i["valid"]),
            "dup_in_batch": sum(1 for i in items if i["dup_in_batch"]),
            "dup_lead": sum(1 for i in items if i["match_lead"]),
            "dup_customer": sum(1 for i in items if i["match_customer"] and not i["match_lead"]),
            "in_queue": sum(1 for i in items if i["in_queue"]),
            "fresh": sum(1 for i in items if i["valid"] and not i["dup_in_batch"] and not i["dup_kind"] and not i["in_queue"])}


# ------------------------------------------------------------------ antrean
def _match_fields(item: dict) -> dict:
    ml, mc = item.get("match_lead"), item.get("match_customer")
    return {"match_lead_id": (ml or {}).get("id"), "match_lead_name": (ml or {}).get("name"),
            "match_lead_stage": (ml or {}).get("stage"), "match_lead_owner": (ml or {}).get("assigned_to"),
            "match_customer_id": (mc or {}).get("id"), "match_customer_name": (mc or {}).get("name")}


async def import_rows(org_id: str, rows: list, *, actor: str, label: str = "") -> dict:
    items = await analyze(org_id, rows)
    ts = now_iso()
    batch = {"id": new_id(), "label": label or f"Impor {ts[:16]}", "by": actor, "at": ts}
    added = updated = 0
    for it in items:
        if it["dup_in_batch"]:
            continue
        phone = it["phone"] or (it["phone_raw"] or "").strip()
        if not phone:
            continue
        existing = await db[COLL].find_one({"org_id": org_id, "phone": phone}, {"_id": 0})
        if existing:
            upd = {"updated_at": ts, "import_batch": batch, **_match_fields(it)}
            if it["name"] and not existing.get("name"):
                upd["name"] = it["name"]
            if it.get("message") and not existing.get("first_message"):
                upd["first_message"] = it["message"]
            await db[COLL].update_one({"id": existing["id"]}, {"$set": upd})
            updated += 1
            continue
        doc = {"id": new_id(), "org_id": org_id, "phone": phone, "name": it["name"] or None,
               "source": "import", "status": "new" if it["valid"] else "invalid",
               "invalid_reason": None if it["valid"] else "Nomor tidak valid / bukan +62",
               "first_message": it.get("message"), "last_message_at": None, "message_count": 0, "conversation_id": None,
               "lead_id": None, "customer_id": None, "opt_out": False, "import_batch": batch,
               "created_by": actor, "created_at": ts, "updated_at": ts, **_match_fields(it)}
        await db[COLL].insert_one(doc)
        added += 1
    return {"batch": batch, "added": added, "updated": updated, "summary": summarize(items)}


async def upsert_from_inbound(org_id: str, *, phone: str, name: str, body: str, conversation_id: str,
                              lead: dict, at: str, opt_out: bool = False) -> dict:
    ex = await db[COLL].find_one({"org_id": org_id, "phone": phone}, {"_id": 0})
    if ex:
        upd = {"last_message_at": at, "conversation_id": conversation_id, "updated_at": at}
        if name and not ex.get("name"):
            upd["name"] = name
        if lead and not ex.get("lead_id"):
            upd.update({"lead_id": lead["id"], "status": "linked" if ex.get("status") in ("new", "skipped") else ex.get("status"),
                        "match_lead_id": lead["id"], "match_lead_name": lead.get("name")})
        if opt_out:
            upd["opt_out"] = True
        if not ex.get("first_message") and body:
            upd["first_message"] = body[:300]
        await db[COLL].update_one({"id": ex["id"]}, {"$set": upd, "$inc": {"message_count": 1}})
        ex.update(upd)
        return ex
    cust = await db.customers.find_one({"org_id": org_id, "phone": phone}, {"_id": 0, "id": 1, "name": 1})
    doc = {"id": new_id(), "org_id": org_id, "phone": phone, "name": name or None, "source": "webhook",
           "status": "linked" if lead else "new", "first_message": (body or "")[:300] or None,
           "last_message_at": at, "message_count": 1, "conversation_id": conversation_id,
           "lead_id": (lead or {}).get("id"), "customer_id": None, "opt_out": opt_out,
           "match_lead_id": (lead or {}).get("id"), "match_lead_name": (lead or {}).get("name"),
           "match_lead_stage": (lead or {}).get("stage"), "match_lead_owner": (lead or {}).get("assigned_to"),
           "match_customer_id": (cust or {}).get("id"), "match_customer_name": (cust or {}).get("name"),
           "created_by": "webhook", "created_at": at, "updated_at": at}
    await db[COLL].insert_one(dict(doc))
    return doc


async def listing(org_id: str, *, status: str = "", q: str = "", source: str = "", dup: str = "",
                  skip: int = 0, limit: int = 50) -> dict:
    query = {"org_id": org_id}
    if status:
        query["status"] = {"$in": [s for s in status.split(",") if s]}
    if source:
        query["source"] = source
    if dup == "lead":
        query["match_lead_id"] = {"$ne": None}
    elif dup == "customer":
        query.update({"match_customer_id": {"$ne": None}, "match_lead_id": None})
    elif dup == "none":
        query.update({"match_lead_id": None, "match_customer_id": None})
    if q:
        rx = {"$regex": re.escape(q), "$options": "i"}
        query["$or"] = [{"name": rx}, {"phone": rx}, {"first_message": rx}]
    total = await db[COLL].count_documents(query)
    rows = await db[COLL].find(query, {"_id": 0}).sort("updated_at", -1).skip(skip).limit(limit).to_list(limit)
    counts = {s: 0 for s in STATUSES}
    async for r in db[COLL].aggregate([{"$match": {"org_id": org_id}}, {"$group": {"_id": "$status", "n": {"$sum": 1}}}]):
        counts[r["_id"]] = r["n"]
    dup_new = await db[COLL].count_documents({"org_id": org_id, "status": "new", "match_lead_id": {"$ne": None}})
    return {"data": rows, "total": total, "counts": counts, "dup_new": dup_new}


# ------------------------------------------------------------------ capture
async def _link_conversation(org_id: str, contact: dict, lead: dict):
    conv_q = {"org_id": org_id, "channel": "whatsapp", "contact_phone": contact["phone"], "lead_id": None}
    await db.conversations.update_many(conv_q, {"$set": {"lead_id": lead["id"], "owner": lead.get("assigned_to"),
                                                         "contact_name": lead.get("name") or contact.get("name"),
                                                         "updated_at": now_iso()}})


async def _create_lead(org_id: str, contact: dict, *, actor: str, assigned_to: str = None,
                       campaign: str = None, customer: dict = None) -> tuple:
    payload = {"name": contact.get("name") or "Lead Baru", "phone": contact["phone"], "source": "whatsapp",
               "message": contact.get("first_message"), "campaign": campaign or "wa-capture"}
    lead_id, duplicate = await process_lead_capture("whatsapp", payload, org_id=org_id, dispatch=False)
    ts = now_iso()
    upd = {"created_by": actor, "wa_contact_id": contact["id"], "updated_at": ts}
    if assigned_to:
        upd["assigned_to"] = assigned_to
    if customer:
        upd.update({"repeat_customer_id": customer["id"], "notes": f"Pembeli lama: {customer.get('name')}"})
    await db.leads.update_one({"id": lead_id}, {"$set": upd})
    lead = await db.leads.find_one({"id": lead_id}, {"_id": 0})
    if assigned_to:
        await db.conversations.update_many({"org_id": org_id, "lead_id": lead_id}, {"$set": {"owner": assigned_to}})
    await add_activity(entity_type="lead", entity_id=lead_id, type="system", org_id=org_id, actor=actor,
                       body=f"Lead dibuat dari kontak WhatsApp ({contact.get('source')}) oleh {actor}.",
                       meta={"wa_contact_id": contact["id"]})
    return lead, duplicate


async def capture(org_id: str, *, ids: list = None, all_new: bool = False, phones: list = None,
                  policy_lead: str = "skip", policy_customer: str = "create", assigned_to: str = None,
                  campaign: str = None, actor: str = "system") -> dict:
    """policy_lead: skip|link ; policy_customer: skip|create."""
    ts = now_iso()
    if phones:
        for p in phones:
            ph = gw.valid_phone(p)
            if ph and not await db[COLL].find_one({"org_id": org_id, "phone": ph}):
                await import_rows(org_id, [{"name": "", "phone": ph}], actor=actor, label="Dari Inbox")
        ids = [c["id"] for c in await db[COLL].find(
            {"org_id": org_id, "phone": {"$in": [gw.valid_phone(p) for p in phones]}}, {"_id": 0, "id": 1}).to_list(500)]
    q = {"org_id": org_id, "status": {"$in": ["new", "skipped"]}}
    if not all_new:
        q["id"] = {"$in": ids or []}
    rows = await db[COLL].find(q, {"_id": 0}).to_list(5000)
    out = {"created": 0, "linked": 0, "skipped": 0, "invalid": 0, "errors": [], "lead_ids": [], "details": []}
    for c in rows:
        phone = gw.valid_phone(c.get("phone"))
        if not phone:
            await db[COLL].update_one({"id": c["id"]}, {"$set": {"status": "invalid", "updated_at": ts,
                                                                 "invalid_reason": "Nomor tidak valid / bukan +62"}})
            out["invalid"] += 1
            out["details"].append({"id": c["id"], "phone": c.get("phone"), "result": "invalid"})
            continue
        lead = await db.leads.find_one({"org_id": org_id, "phone": phone}, {"_id": 0})
        cust = await db.customers.find_one({"org_id": org_id, "phone": phone}, {"_id": 0, "id": 1, "name": 1})
        try:
            if lead:
                if policy_lead == "link":
                    await _link_conversation(org_id, c, lead)
                    upd = {"last_touch": {"at": ts, "provider": "whatsapp", "source": "whatsapp", "campaign": campaign or "wa-capture"},
                           "updated_at": ts}
                    if c.get("name") and (lead.get("name") or "Lead Baru") == "Lead Baru":
                        upd["name"] = c["name"]
                    await db.leads.update_one({"id": lead["id"]}, {"$set": upd})
                    await add_activity(entity_type="lead", entity_id=lead["id"], type="system", org_id=org_id,
                                       actor=actor, body=f"Kontak WhatsApp ditautkan ulang oleh {actor} (nomor sama).",
                                       meta={"wa_contact_id": c["id"]})
                    await db[COLL].update_one({"id": c["id"]}, {"$set": {
                        "status": "linked", "lead_id": lead["id"], "match_lead_id": lead["id"],
                        "match_lead_name": lead.get("name"), "captured_by": actor, "captured_at": ts, "updated_at": ts}})
                    out["linked"] += 1
                    out["lead_ids"].append(lead["id"])
                    out["details"].append({"id": c["id"], "phone": phone, "result": "linked", "lead_id": lead["id"]})
                else:
                    await db[COLL].update_one({"id": c["id"]}, {"$set": {
                        "status": "skipped", "skip_reason": f"Duplikat lead: {lead.get('name')}",
                        "match_lead_id": lead["id"], "match_lead_name": lead.get("name"), "updated_at": ts}})
                    out["skipped"] += 1
                    out["details"].append({"id": c["id"], "phone": phone, "result": "skipped", "reason": "dup_lead"})
                continue
            if cust and policy_customer == "skip":
                await db[COLL].update_one({"id": c["id"]}, {"$set": {
                    "status": "skipped", "skip_reason": f"Sudah customer: {cust.get('name')}",
                    "match_customer_id": cust["id"], "match_customer_name": cust.get("name"), "updated_at": ts}})
                out["skipped"] += 1
                out["details"].append({"id": c["id"], "phone": phone, "result": "skipped", "reason": "dup_customer"})
                continue
            if not c.get("name") and cust:
                c["name"] = cust.get("name")
            new_lead, dup = await _create_lead(org_id, c, actor=actor, assigned_to=assigned_to,
                                               campaign=campaign, customer=cust)
            await _link_conversation(org_id, c, new_lead)
            await db[COLL].update_one({"id": c["id"]}, {"$set": {
                "status": "captured" if not dup else "linked", "lead_id": new_lead["id"], "captured_by": actor,
                "captured_at": ts, "updated_at": ts, "customer_id": (cust or {}).get("id")}})
            out["created" if not dup else "linked"] += 1
            out["lead_ids"].append(new_lead["id"])
            out["details"].append({"id": c["id"], "phone": phone, "result": "created" if not dup else "linked",
                                   "lead_id": new_lead["id"]})
        except Exception as e:  # noqa: BLE001
            out["errors"].append({"id": c["id"], "phone": phone, "error": str(e)[:200]})
    if out["created"] or out["linked"]:
        from engine import dispatch_pending
        await dispatch_pending()
    return out


async def set_status(org_id: str, cid: str, status: str, *, actor: str, reason: str = None) -> dict:
    ts = now_iso()
    upd = {"status": status, "updated_at": ts, "status_by": actor}
    if reason is not None:
        upd["skip_reason"] = reason
    r = await db[COLL].update_one({"id": cid, "org_id": org_id}, {"$set": upd})
    return {"matched": r.matched_count}
