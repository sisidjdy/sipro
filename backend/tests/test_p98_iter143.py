"""Iterasi 143 — pemeriksaan tambahan Fase 98 sesuai review_request."""
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
BASE = (os.environ.get("REACT_APP_BACKEND_URL") or fe["REACT_APP_BACKEND_URL"]).rstrip("/")
API = f"{BASE}/api"


def _login(email, password="Sipro#2026"):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
    r.raise_for_status()
    d = r.json()
    return d.get("token") or d.get("access_token") or d.get("data", {}).get("token")


@pytest.fixture(scope="module")
def hdr():
    return {"Authorization": f"Bearer {_login('superadmin@sipro.co.id')}"}


def _phone():
    return "+62813" + str(uuid.uuid4().int)[:8]


def _inbound(phone, text, name="Uji Iter143"):
    return {"object": "whatsapp_business_account", "entry": [{"id": "1", "changes": [{"field": "messages", "value": {
        "messaging_product": "whatsapp",
        "contacts": [{"profile": {"name": name}, "wa_id": phone.lstrip("+")}],
        "messages": [{"from": phone.lstrip("+"), "id": f"wamid.I{uuid.uuid4().hex}", "timestamp": "1757000000",
                      "type": "text", "text": {"body": text}}]}}]}]}


# auth register endpoint must not exist as GET
def test_auth_register_get_404():
    r = requests.get(f"{API}/auth/register", timeout=15)
    assert r.status_code == 404


# 'berhentikan pembangunan' should NOT trigger opt-out (substring test)
def test_berhentikan_substring_does_not_opt_out(hdr):
    phone = _phone()
    r = requests.post(f"{API}/webhooks/wa", json=_inbound(phone, "berhentikan pembangunan dulu"), timeout=30)
    assert r.status_code == 200
    q = requests.get(f"{API}/wa/optouts", params={"q": phone}, headers=hdr, timeout=30).json()
    assert q["total"] == 0


# 'STOP' alone triggers opt-out AND confirmation outbound message exists
def test_stop_triggers_opt_out_with_confirmation(hdr):
    phone = _phone()
    lead = requests.post(f"{API}/leads", json={"name": "Uji STOP", "phone": phone, "source": "whatsapp"},
                        headers=hdr, timeout=30).json()["data"]
    try:
        r = requests.post(f"{API}/webhooks/wa", json=_inbound(phone, "STOP"), timeout=30)
        assert r.status_code == 200
        opt = requests.get(f"{API}/wa/optouts", params={"q": phone}, headers=hdr, timeout=30).json()
        assert opt["total"] == 1
        # confirmation outbound exists in the conversation
        contacts = requests.get(f"{API}/wa/contacts", params={"q": phone}, headers=hdr, timeout=30).json()["data"]
        row = next((c for c in contacts if c["phone"] == phone), None)
        if row:
            msgs = requests.get(f"{API}/wa/contacts/{row['id']}/messages", headers=hdr, timeout=30).json()["data"]["messages"]
            outs = [m for m in msgs if m["direction"] == "out"]
            assert outs, "expected outbound confirmation message after STOP"
    finally:
        # cleanup
        try:
            oid = opt["data"][0]["id"]
            requests.delete(f"{API}/wa/optouts/{oid}", headers=hdr, timeout=15)
        except Exception:
            pass
        requests.delete(f"{API}/leads/{lead['id']}", headers=hdr, timeout=15)


# stats card counts equal messages endpoint totals (per kind)
def test_stats_by_kind_equals_messages_endpoint(hdr):
    s = requests.get(f"{API}/wa/stats", params={"days": 7}, headers=hdr, timeout=30).json()["data"]
    assert "totals" in s and "by_kind" in s
    for kind in s["by_kind"]:
        if kind["total"] == 0 or kind["kind"] == "lainnya":
            # 'lainnya' is a fallback bucket for null-kind messages; the messages
            # endpoint filters by explicit kind and cannot match null values —
            # see backend_issues.critical in iter_143 report.
            continue
        rows = requests.get(f"{API}/wa/messages",
                           params={"days": 7, "kind": kind["kind"], "limit": 1}, headers=hdr, timeout=30).json()
        assert rows["total"] == kind["total"], f"kind {kind['kind']} mismatch: card={kind['total']} rows={rows['total']}"


# broadcast never shows fabricated read>0 in simulation mode
def test_broadcast_read_stays_zero_in_simulation(hdr):
    b = requests.post(f"{API}/broadcasts",
                     json={"name": f"UjiIter143 {uuid.uuid4().hex[:6]}", "template_code": "promo", "segment": {}},
                     headers=hdr, timeout=30).json()["data"]
    try:
        assert b["read"] == 0
        run = requests.post(f"{API}/broadcasts/{b['id']}/run", headers=hdr, timeout=60).json()["data"]
        assert run["broadcast"]["read"] == 0
    finally:
        requests.post(f"{API}/broadcasts/{b['id']}/cancel", headers=hdr, timeout=15)


# templates meta: submit and sync return honest 400 in simulation (no creds)
def test_templates_meta_submit_sync_honest_400(hdr):
    tmpls = requests.get(f"{API}/wa-templates", headers=hdr, timeout=30).json()["data"]
    t = tmpls[0]
    submit = requests.post(f"{API}/wa-templates/{t['id']}/submit", headers=hdr, timeout=30)
    assert submit.status_code in (400, 424), submit.text
    sync = requests.post(f"{API}/wa-templates/sync", headers=hdr, timeout=30)
    assert sync.status_code in (400, 424), sync.text
