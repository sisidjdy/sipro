"""Fase 96 — webhook Meta dengan FIXTURE payload asli: teks, gambar, status delivered/failed, tanda tangan salah."""
import hashlib
import hmac
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
    import sys
    sys.path.insert(0, "/app/scripts")
    import _wa_common as w
    guard = w.wa_channel_guard()
    guard.__enter__()
    yield
    guard.__exit__(None, None, None)
    try:
        w.purge_leads(["Pembeli Fixture", "Fixture Gambar", "Kontrak Lama"])
    except Exception:  # noqa: BLE001
        pass


def _phone():
    return "+62813" + str(uuid.uuid4().int)[:8]


def _entry(value):
    return {"object": "whatsapp_business_account", "entry": [{"id": "102290129340398", "changes": [
        {"field": "messages", "value": {"messaging_product": "whatsapp",
                                        "metadata": {"display_phone_number": "6281100000000", "phone_number_id": "PHONE_ID"},
                                        **value}}]}]}


def _text(phone, body, wamid=None, name="Pembeli Fixture"):
    return _entry({"contacts": [{"profile": {"name": name}, "wa_id": phone.lstrip("+")}],
                   "messages": [{"from": phone.lstrip("+"), "id": wamid or f"wamid.HBgN{uuid.uuid4().hex[:20]}",
                                 "timestamp": "1757000000", "type": "text", "text": {"body": body}}]})


def _image(phone):
    return _entry({"contacts": [{"profile": {"name": "Fixture Gambar"}, "wa_id": phone.lstrip("+")}],
                   "messages": [{"from": phone.lstrip("+"), "id": f"wamid.IMG{uuid.uuid4().hex[:20]}", "timestamp": "1757000000",
                                 "type": "image", "image": {"caption": "Bukti transfer", "mime_type": "image/jpeg",
                                                            "sha256": "abc", "id": "1234567890"}}]})


def _status(wamid, status, errors=None):
    st = {"id": wamid, "status": status, "timestamp": "1757000100", "recipient_id": "6281234567890",
          "conversation": {"id": "CONV", "origin": {"type": "utility"}}, "pricing": {"billable": True, "category": "utility"}}
    if errors:
        st["errors"] = errors
    return _entry({"statuses": [st]})


def test_text_fixture_creates_conversation_and_contact(hdr):
    phone = _phone()
    r = requests.post(f"{API}/webhooks/wa", json=_text(phone, "Halo, ada unit tipe 45?"), timeout=30)
    assert r.status_code == 200 and r.json()["data"]["messages"] == 1
    lst = requests.get(f"{API}/wa/contacts", params={"status": "new", "q": phone}, headers=hdr, timeout=30).json()
    row = next(x for x in lst["data"] if x["phone"] == phone)
    assert row["name"] == "Pembeli Fixture" and row["conversation_id"]
    msgs = requests.get(f"{API}/wa/contacts/{row['id']}/messages", headers=hdr, timeout=30).json()["data"]
    assert msgs["window_open"] is True and msgs["messages"][-1]["body"] == "Halo, ada unit tipe 45?"


def test_image_fixture_recorded_with_media(hdr):
    phone = _phone()
    r = requests.post(f"{API}/webhooks/wa", json=_image(phone), timeout=30)
    assert r.status_code == 200 and r.json()["data"]["messages"] == 1
    lst = requests.get(f"{API}/wa/contacts", params={"status": "new", "q": phone}, headers=hdr, timeout=30).json()
    row = next(x for x in lst["data"] if x["phone"] == phone)
    msgs = requests.get(f"{API}/wa/contacts/{row['id']}/messages", headers=hdr, timeout=30).json()["data"]["messages"]
    m = msgs[-1]
    assert m["mtype"] == "image" and m["media"]["media_id"] == "1234567890" and m["body"] == "Bukti transfer"


def test_status_delivered_then_failed_with_error(hdr):
    phone = _phone()
    sent = requests.post(f"{API}/wa/config/test-message", json={"to": phone}, headers=hdr, timeout=30).json()["data"]
    wamid = sent["provider_message_id"]
    requests.post(f"{API}/webhooks/wa", json=_status(wamid, "delivered"), timeout=30)
    rows = requests.get(f"{API}/wa/messages", params={"kind": "test", "status": "delivered", "limit": 100}, headers=hdr, timeout=30).json()["data"]
    assert any(r["provider_message_id"] == wamid for r in rows)
    requests.post(f"{API}/webhooks/wa", json=_status(wamid, "failed", [{"code": 131026, "title": "Message Undeliverable",
                                                                       "error_data": {"details": "Recipient cannot receive"}}]), timeout=30)
    rows = requests.get(f"{API}/wa/messages", params={"kind": "test", "status": "failed", "code": "131026", "limit": 100}, headers=hdr, timeout=30).json()["data"]
    m = next(r for r in rows if r["provider_message_id"] == wamid)
    assert m["error_code"] == "131026" and m["error_detail"] == "Message Undeliverable"


def test_bad_signature_rejected_and_good_accepted(hdr):
    secret = f"sec-{uuid.uuid4().hex[:8]}"
    requests.put(f"{API}/wa/config", json={"app_secret": secret}, headers=hdr, timeout=30)
    try:
        body = json.dumps(_text(_phone(), "signature test")).encode()
        bad = requests.post(f"{API}/webhooks/wa", data=body, headers={"Content-Type": "application/json",
                                                                      "X-Hub-Signature-256": "sha256=00ff"}, timeout=30)
        assert bad.status_code == 403
        sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        good = requests.post(f"{API}/webhooks/wa", data=body, headers={"Content-Type": "application/json",
                                                                       "X-Hub-Signature-256": sig}, timeout=30)
        assert good.status_code == 200 and good.json()["signature_ok"] is True
    finally:
        requests.put(f"{API}/wa/config", json={"app_secret": "__clear__"}, headers=hdr, timeout=30)


def test_duplicate_wamid_idempotent(hdr):
    phone, wamid = _phone(), f"wamid.DUP{uuid.uuid4().hex[:20]}"
    a = requests.post(f"{API}/webhooks/wa", json=_text(phone, "sekali", wamid), timeout=30).json()["data"]
    b = requests.post(f"{API}/webhooks/wa", json=_text(phone, "sekali", wamid), timeout=30).json()["data"]
    assert a["messages"] == 1 and b["duplicates"] == 1 and b["messages"] == 0


def test_template_status_update_webhook_marks_rejected(hdr):
    t = requests.post(f"{API}/wa-templates", json={"name": f"Fixture Tmpl {uuid.uuid4().hex[:4]}", "category": "marketing",
                                                    "body": "Promo {{nama}}", "variables": ["nama"]}, headers=hdr, timeout=30).json()["data"]
    payload = {"object": "whatsapp_business_account", "entry": [{"id": "WABA", "changes": [{
        "field": "message_template_status_update",
        "value": {"event": "REJECTED", "message_template_id": 998877, "message_template_name": t["meta_name"],
                  "message_template_language": "id", "reason": "INVALID_FORMAT"}}]}]}
    r = requests.post(f"{API}/webhooks/wa", json=payload, timeout=30)
    assert r.status_code == 200 and r.json()["data"].get("account_events") == 1
    rows = requests.get(f"{API}/wa-templates", headers=hdr, timeout=30).json()["data"]
    fresh = next(x for x in rows if x["id"] == t["id"])
    assert fresh["status"] == "rejected" and fresh["meta_status"] == "REJECTED" and fresh["meta_reason"] == "INVALID_FORMAT"
    requests.delete(f"{API}/wa-templates/{t['id']}", headers=hdr, timeout=30)


def test_legacy_webhook_lead_contract_alive():
    r = requests.post(f"{API}/webhooks/wa", json={"name": "Kontrak Lama", "phone": _phone(), "message": "halo"}, timeout=30)
    assert r.status_code in (200, 202) and r.json()["data"]["provider"] == "whatsapp"
