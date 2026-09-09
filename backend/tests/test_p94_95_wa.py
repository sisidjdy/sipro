"""Fase 94–95 — gateway WA tunggal, webhook Meta, antrean kontak → lead (dedup)."""
import json
import os
import uuid

import pytest
import requests

fe = {}
with open("/app/frontend/.env") as f:
    for line in f:
        if "=" in line:
            k, v = line.strip().split("=", 1)
            fe[k] = v.strip('"')
BASE = (os.environ.get("REACT_APP_BACKEND_URL") or fe.get("REACT_APP_BACKEND_URL")).rstrip("/")
API = f"{BASE}/api"


def _login(email, password="Sipro#2026"):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
    r.raise_for_status()
    d = r.json()
    return d.get("token") or d.get("access_token") or d.get("data", {}).get("token")


@pytest.fixture(scope="module")
def hdr():
    return {"Authorization": f"Bearer {_login('superadmin@sipro.co.id')}"}


@pytest.fixture(scope="module", autouse=True)
def _purge_after():
    """Lead/kontak uji (nomor +62813 acak) tidak boleh tersisa sebagai data yatim (forensic_audit).
    Kredensial WA nyata dijaga `wa_channel_guard` (mode dipaksa simulasi, dipulihkan di akhir)."""
    import sys
    sys.path.insert(0, "/app/scripts")
    import _wa_common as w
    guard = w.wa_channel_guard()
    guard.__enter__()
    yield
    guard.__exit__(None, None, None)
    try:
        from pymongo import MongoClient
        env = dict(line.strip().split("=", 1) for line in open("/app/backend/.env") if "=" in line)
        dbn = MongoClient(env["MONGO_URL"].strip('"'))[env["DB_NAME"].strip('"')]
        names = ["Tes Webhook", "Legacy", "Budi", "Simulasi", "Uji"]
        phones = {d["phone"] for d in dbn.leads.find({"name": {"$in": names}, "source": "whatsapp",
                                                       "phone": {"$regex": "^\\+62813"}}, {"phone": 1})}
        phones |= {d["phone"] for d in dbn.wa_contacts.find({"phone": {"$regex": "^\\+62813"}, "source": {"$in": ["webhook", "import"]},
                                                              "lead_id": None}, {"phone": 1}) if not dbn.leads.find_one({"phone": d["phone"]})}
        w.purge_phones(dbn, phones)
    except Exception:  # noqa: BLE001
        pass


def _phone():
    return "+62813" + str(uuid.uuid4().int)[:8]


def _meta_payload(phone, text, wamid=None, name=None):
    return {"object": "whatsapp_business_account", "entry": [{"id": "1", "changes": [{"field": "messages", "value": {
        "messaging_product": "whatsapp",
        "contacts": [{"profile": {"name": name}, "wa_id": phone.lstrip("+")}] if name else [],
        "messages": [{"from": phone.lstrip("+"), "id": wamid or f"wamid.T{uuid.uuid4().hex}",
                      "timestamp": "1757000000", "type": "text", "text": {"body": text}}]}}]}]}


def test_config_masked_and_verify_handshake(hdr):
    r = requests.put(f"{API}/wa/config", json={"verify_token": "pytest-verify-1"}, headers=hdr, timeout=30)
    assert r.status_code == 200
    d = r.json()["data"]
    assert d["credentials"]["verify_token"]["set"] is True
    assert "pytest-verify-1" not in json.dumps(d)  # tersamar
    ok = requests.get(f"{API}/webhooks/wa", params={"hub.mode": "subscribe", "hub.verify_token": "pytest-verify-1",
                                                     "hub.challenge": "CH1"}, timeout=30)
    assert ok.status_code == 200 and ok.text == "CH1"
    bad = requests.get(f"{API}/webhooks/wa", params={"hub.mode": "subscribe", "hub.verify_token": "salah",
                                                      "hub.challenge": "CH1"}, timeout=30)
    assert bad.status_code == 403


def test_live_mode_requires_creds(hdr):
    # kosongkan token sementara (guard modul memulihkan kredensial asli di akhir)
    requests.put(f"{API}/wa/config", json={"token": "__clear__", "phone_id": "__clear__"}, headers=hdr, timeout=30)
    r = requests.put(f"{API}/wa/config", json={"mode": "live"}, headers=hdr, timeout=30)
    assert r.status_code == 400


def test_webhook_meta_inbound_queue_and_idempotent(hdr):
    phone = _phone()
    wamid = f"wamid.T{uuid.uuid4().hex}"
    r = requests.post(f"{API}/webhooks/wa", json=_meta_payload(phone, "Halo info harga", wamid, "Tes Webhook"), timeout=30)
    assert r.status_code == 200
    assert r.json()["data"]["messages"] == 1
    r2 = requests.post(f"{API}/webhooks/wa", json=_meta_payload(phone, "Halo info harga", wamid), timeout=30)
    assert r2.json()["data"]["duplicates"] == 1
    lst = requests.get(f"{API}/wa/contacts", params={"status": "new", "q": phone}, headers=hdr, timeout=30).json()
    row = next(x for x in lst["data"] if x["phone"] == phone)
    assert row["status"] == "new" and row["name"] == "Tes Webhook" and row["match_lead_id"] is None
    assert row["conversation_id"]
    # kontak → lead
    cap = requests.post(f"{API}/wa/contacts/capture", json={"ids": [row["id"]], "policy_lead": "skip"},
                        headers=hdr, timeout=30).json()["data"]
    assert cap["created"] == 1 and cap["lead_ids"]
    lead = requests.get(f"{API}/leads/{cap['lead_ids'][0]}", headers=hdr, timeout=30).json()["data"]
    assert lead["phone"] == phone and lead["source"] == "whatsapp"
    conv = requests.get(f"{API}/inbox/{row['conversation_id']}", headers=hdr, timeout=30).json()["data"]
    assert conv["conversation"]["lead_id"] == lead["id"]  # percakapan lama dipakai ulang, bukan kembar


def test_import_dedup_policies(hdr):
    fresh, fresh2 = _phone(), _phone()
    leads = requests.get(f"{API}/leads", params={"limit": 50}, headers=hdr, timeout=30).json()["data"]
    lead_phone = next(l["phone"] for l in leads if l.get("phone") and not requests.get(
        f"{API}/wa/contacts", params={"q": l["phone"]}, headers=hdr, timeout=30).json()["data"])
    text = f"Budi, {fresh}\nSiti, {fresh2}\n{fresh}\nLama, {lead_phone}\nabc\n0812"
    pv = requests.post(f"{API}/wa/contacts/preview", json={"text": text}, headers=hdr, timeout=30).json()["data"]
    s = pv["summary"]
    assert s["dup_in_batch"] == 1 and s["dup_lead"] == 1 and s["fresh"] == 2
    imp = requests.post(f"{API}/wa/contacts/import", json={"text": text, "label": "pytest"}, headers=hdr, timeout=30).json()["data"]
    assert imp["added"] >= 2
    lst = requests.get(f"{API}/wa/contacts", params={"status": "new", "q": lead_phone}, headers=hdr, timeout=30).json()["data"]
    dup = next(x for x in lst if x["phone"] == lead_phone)
    assert dup["match_lead_id"]
    # lewati duplikat lead
    cap = requests.post(f"{API}/wa/contacts/capture", json={"ids": [dup["id"]], "policy_lead": "skip"},
                        headers=hdr, timeout=30).json()["data"]
    assert cap["skipped"] == 1 and cap["created"] == 0
    # kembalikan lalu tautkan
    requests.post(f"{API}/wa/contacts/{dup['id']}/restore", headers=hdr, timeout=30)
    cap2 = requests.post(f"{API}/wa/contacts/capture", json={"ids": [dup["id"]], "policy_lead": "link"},
                         headers=hdr, timeout=30).json()["data"]
    assert cap2["linked"] == 1 and cap2["lead_ids"] == [dup["match_lead_id"]]
    # nomor baru → lead baru
    ids = [x["id"] for x in requests.get(f"{API}/wa/contacts", params={"status": "new", "q": fresh},
                                         headers=hdr, timeout=30).json()["data"]]
    cap3 = requests.post(f"{API}/wa/contacts/capture", json={"ids": ids}, headers=hdr, timeout=30).json()["data"]
    assert cap3["created"] == 1
    # setelah jadi lead, nomor yang sama masuk webhook → langsung tertaut (bukan antrean)
    r = requests.post(f"{API}/webhooks/wa", json=_meta_payload(fresh, "Pesan kedua"), timeout=30).json()["data"]
    assert r["leads_linked"] == 1


def test_outbound_gateway_status_and_status_webhook(hdr):
    phone = _phone()
    requests.post(f"{API}/wa/simulate/inbound", json={"phone": phone, "name": "Sim", "message": "hai"}, headers=hdr, timeout=30)
    conv = next(c for c in requests.get(f"{API}/inbox", params={"limit": 50}, headers=hdr, timeout=30).json()["data"]
                if c["contact_phone"] == phone)
    assert conv["window_open"] and conv["window_remaining_minutes"] > 1400
    m = requests.post(f"{API}/inbox/{conv['id']}/messages", json={"body": "Balasan uji", "direction": "out"},
                      headers=hdr, timeout=30).json()["data"]
    assert m["status"] == "simulated" and m["mode"] == "simulation" and m["provider_message_id"].startswith("sim-")
    st = {"object": "whatsapp_business_account", "entry": [{"id": "1", "changes": [{"field": "messages", "value": {
        "statuses": [{"id": m["provider_message_id"], "status": "delivered", "timestamp": "1757000100"}]}}]}]}
    assert requests.post(f"{API}/webhooks/wa", json=st, timeout=30).json()["data"]["statuses"] == 1
    msgs = requests.get(f"{API}/inbox/{conv['id']}", headers=hdr, timeout=30).json()["data"]["messages"]
    assert next(x for x in msgs if x["id"] == m["id"])["status"] == "delivered"


def test_test_message_invalid_phone_is_failed(hdr):
    r = requests.post(f"{API}/wa/config/test-message", json={"to": "12345"}, headers=hdr, timeout=30).json()["data"]
    assert r["status"] == "failed" and r["error_code"] == "invalid_phone"


def test_legacy_contract_still_accepted():
    r = requests.post(f"{API}/webhooks/wa", json={"name": "Legacy", "phone": _phone(), "message": "hi"}, timeout=30)
    assert r.status_code == 200 and r.json()["data"]["captured"] is True


def test_rbac_sales_cannot_list_queue():
    h = {"Authorization": f"Bearer {_login('sales@sipro.co.id')}"}
    assert requests.get(f"{API}/wa/contacts", headers=h, timeout=30).status_code == 403
    assert requests.put(f"{API}/wa/config", json={"mode": "simulation"}, headers=h, timeout=30).status_code == 403
