"""_wa_common — helper bersama gate WhatsApp (Fase 94–98): login, base URL, cek."""
import pathlib
import sys
import uuid

import requests

ROOT = pathlib.Path(__file__).resolve().parent.parent
BE = ROOT / "backend"
FE = ROOT / "frontend" / "src"
BASE = "http://localhost:8001/api"
PW = "Sipro#2026"
FAIL = []
PASSED = [0]


def check(ok, label, detail=""):
    if ok:
        PASSED[0] += 1
        print(f"  OK    {label}")
    else:
        FAIL.append(label)
        print(f"  MERAH {label} — {detail}")
    return bool(ok)


def hdr(email="superadmin@sipro.co.id"):
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": PW}, timeout=25)
    r.raise_for_status()
    d = r.json()
    tok = d.get("token") or d.get("access_token") or (d.get("data") or {}).get("token")
    return {"Authorization": f"Bearer {tok}"}


def phone():
    return "+62813" + str(uuid.uuid4().int)[:8]


def meta_payload(ph, text, wamid=None, name=None):
    return {"object": "whatsapp_business_account", "entry": [{"id": "GATE", "changes": [{"field": "messages", "value": {
        "messaging_product": "whatsapp",
        "contacts": [{"profile": {"name": name}, "wa_id": ph.lstrip("+")}] if name else [],
        "messages": [{"from": ph.lstrip("+"), "id": wamid or f"wamid.G{uuid.uuid4().hex}",
                      "timestamp": "1757000000", "type": "text", "text": {"body": text}}]}}]}]}


def wa_db():
    """Koneksi Mongo dari backend/.env (dipakai purge & penjaga kredensial)."""
    import os
    from pymongo import MongoClient
    env = {}
    for line in (BE / ".env").read_text().splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"')
    return MongoClient(env.get("MONGO_URL") or os.environ["MONGO_URL"])[env.get("DB_NAME") or os.environ["DB_NAME"]]


class wa_channel_guard:
    """Gate/pytest TIDAK boleh merusak kredensial WhatsApp nyata atau mengirim pesan sungguhan:
    simpan `channel_accounts.wa_main`, paksa mode simulasi selama uji, pulihkan apa adanya di akhir."""

    def __init__(self, org_id="org-sipro"):
        self.dbn, self.org_id, self.snap = wa_db(), org_id, None

    def __enter__(self):
        self.snap = self.dbn.channel_accounts.find_one({"org_id": self.org_id, "code": "wa_main"}, {"_id": 0})
        if self.snap:
            # mode simulasi + tanpa app secret: payload Meta buatan gate tidak bertanda tangan
            self.dbn.channel_accounts.update_one({"id": self.snap["id"]}, {
                "$set": {"mode": "simulation"}, "$unset": {"credentials_enc.app_secret": ""}})
        return self

    def __exit__(self, *exc):
        if not self.snap:
            return False
        keep = {k: self.snap.get(k) for k in ("credentials_enc", "mode", "last_probe", "last_diagnose",
                                                "webhook_last_received_at", "webhook_last_signature_ok", "webhook_last_kind")}
        self.dbn.channel_accounts.update_one({"id": self.snap["id"]}, {"$set": keep})
        return False


def purge_leads(names):
    """Bahan uji gate tidak boleh tersisa (forensic_audit): hapus per NOMOR di semua koleksi WA."""
    dbn = wa_db()
    names = list(names)
    phones = set()
    for coll, f in (("leads", "phone"), ("conversations", "contact_phone"), ("wa_contacts", "phone")):
        nf = "contact_name" if coll == "conversations" else "name"
        phones |= {d.get(f) for d in dbn[coll].find({nf: {"$in": names}}, {f: 1}) if d.get(f)}
    purge_phones(dbn, phones)


def purge_phones(dbn, phones):
    phones = [p for p in phones if p]
    if not phones:
        return
    conv_ids = [c["id"] for c in dbn.conversations.find({"contact_phone": {"$in": phones}}, {"id": 1})]
    lead_ids = [l["id"] for l in dbn.leads.find({"phone": {"$in": phones}}, {"id": 1})]
    ent_ids = conv_ids + lead_ids
    dbn.tasks.delete_many({"related_entity_id": {"$in": ent_ids}})
    dbn.activities.delete_many({"entity_id": {"$in": ent_ids}})
    dbn.appointments.delete_many({"lead_id": {"$in": lead_ids}})
    dbn.notifications.delete_many({"related_entity_id": {"$in": ent_ids}})
    dbn.conversion_events.delete_many({"lead_id": {"$in": lead_ids}})
    dbn.lead_capture_events.delete_many({"lead_id": {"$in": lead_ids}})
    dbn.wa_doc_shares.delete_many({"to": {"$in": phones}})
    dbn.leads.delete_many({"phone": {"$in": phones}})
    dbn.wa_contacts.delete_many({"phone": {"$in": phones}})
    dbn.wa_optouts.delete_many({"phone": {"$in": phones}})
    dbn.messages.delete_many({"conversation_id": {"$in": conv_ids}})
    dbn.conversations.delete_many({"id": {"$in": conv_ids}})
    dbn.wa_outbox.delete_many({"to": {"$in": phones}})
    dbn.broadcast_recipients.delete_many({"phone": {"$in": phones}})


def finish(name):
    print(f"\n{name}: {PASSED[0]} OK, {len(FAIL)} MERAH")
    for f in FAIL:
        print(f"   - {f}")
    sys.exit(1 if FAIL else 0)
