"""Fase 97/98 — template & kepatuhan: approved wajib, opt-out vs kategori, jam kirim, broadcast antrean,
balas cepat dari antrean, kirim dokumen via WA."""
import os
import sys
import uuid
from datetime import datetime, timezone

import pytest
import requests

sys.path.insert(0, "/app/backend")
sys.path.insert(0, "/app/scripts")
os.environ.setdefault("JWT_SECRET", "pytest-secret")

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


def _phone():
    return "+62813" + str(uuid.uuid4().int)[:8]


def _purge(*phones):
    """Bahan uji tidak boleh tersisa sebagai data yatim (forensic_audit) — hapus per nomor di semua koleksi WA."""
    try:
        import _wa_common as w
        from pymongo import MongoClient
        env = dict(line.strip().split("=", 1) for line in open("/app/backend/.env") if "=" in line)
        dbn = MongoClient(env["MONGO_URL"].strip('"'))[env["DB_NAME"].strip('"')]
        w.purge_phones(dbn, list(phones))
    except Exception:  # noqa: BLE001 — pembersihan opsional
        pass


def _inbound(phone, text, name=None):
    return {"object": "whatsapp_business_account", "entry": [{"id": "1", "changes": [{"field": "messages", "value": {
        "messaging_product": "whatsapp",
        "contacts": [{"profile": {"name": name}, "wa_id": phone.lstrip("+")}] if name else [],
        "messages": [{"from": phone.lstrip("+"), "id": f"wamid.C{uuid.uuid4().hex}", "timestamp": "1757000000",
                      "type": "text", "text": {"body": text}}]}}]}]}


def test_opt_out_whole_word_only():
    import wa_compliance as wc
    assert wc.detect_opt_out("STOP") and wc.detect_opt_out("mohon berhenti kirim") and wc.detect_opt_out("HENTIKAN")
    assert not wc.detect_opt_out("berhentikan pembangunan dulu") and not wc.detect_opt_out("stopkontak")


def test_send_window_respected():
    import wa_compliance as wc
    assert wc.in_send_window("08:00", "20:00", datetime(2026, 9, 5, 5, 0, tzinfo=timezone.utc))  # 12:00 WIB
    assert not wc.in_send_window("08:00", "20:00", datetime(2026, 9, 5, 16, 30, tzinfo=timezone.utc))  # 23:30 WIB
    assert wc.in_send_window("00:00", "00:00", datetime(2026, 9, 5, 16, 30, tzinfo=timezone.utc))  # tanpa batas


def test_unapproved_template_rejected_with_reason(hdr):
    t = requests.post(f"{API}/wa-templates", json={"name": f"Pending {uuid.uuid4().hex[:4]}", "category": "marketing",
                                                    "body": "Promo {{nama}}", "variables": ["nama"]}, headers=hdr, timeout=30).json()["data"]
    requests.put(f"{API}/wa-templates/{t['id']}", json={"status": "pending"}, headers=hdr, timeout=30)
    r = requests.post(f"{API}/broadcasts", json={"name": "x", "template_code": t["code"], "segment": {}}, headers=hdr, timeout=30)
    assert r.status_code == 400 and "belum disetujui" in r.json()["detail"]
    # gateway juga menolak: kirim template pending lewat balas cepat → 502 dengan alasan
    phone = _phone()
    requests.post(f"{API}/webhooks/wa", json=_inbound(phone, "halo"), timeout=30)
    row = next(x for x in requests.get(f"{API}/wa/contacts", params={"q": phone}, headers=hdr, timeout=30).json()["data"] if x["phone"] == phone)
    r = requests.post(f"{API}/wa/contacts/{row['id']}/reply", json={"template_code": t["code"]}, headers=hdr, timeout=30)
    assert r.status_code == 424 and "template_not_approved" in r.json()["detail"]
    requests.delete(f"{API}/wa-templates/{t['id']}", headers=hdr, timeout=30)
    _purge(phone)


def test_opt_out_blocks_marketing_not_utility(hdr):
    phone = _phone()
    lead = requests.post(f"{API}/leads", json={"name": "Opt Out Test", "phone": phone, "source": "whatsapp"}, headers=hdr, timeout=30).json()["data"]
    requests.post(f"{API}/webhooks/wa", json=_inbound(phone, "STOP"), timeout=30)
    opt = requests.get(f"{API}/wa/optouts", params={"q": phone}, headers=hdr, timeout=30).json()
    assert opt["total"] == 1 and opt["data"][0]["source"] == "inbound_keyword"
    mk = requests.post(f"{API}/broadcasts", json={"name": "mk", "template_code": "promo", "segment": {"sources": ["whatsapp"]}},
                       headers=hdr, timeout=30).json()["data"]
    det = requests.get(f"{API}/broadcasts/{mk['id']}", headers=hdr, timeout=30).json()["data"]
    me = next(x for x in det["recipients"] if x["phone"] == phone)
    assert me["status"] == "skipped" and me["skip_reason"] == "opt_out"
    ut = requests.post(f"{API}/broadcasts", json={"name": "ut", "template_code": "payment_reminder", "segment": {"sources": ["whatsapp"]}},
                       headers=hdr, timeout=30).json()["data"]
    det2 = requests.get(f"{API}/broadcasts/{ut['id']}", headers=hdr, timeout=30).json()["data"]
    me2 = next(x for x in det2["recipients"] if x["phone"] == phone)
    assert me2["status"] == "queued"
    # jalankan antrean → status jujur (simulated), bukan karangan "read"
    run = requests.post(f"{API}/broadcasts/{ut['id']}/run", headers=hdr, timeout=60).json()["data"]
    assert run["broadcast"]["read"] == 0
    if run["run"].get("skipped_window"):
        # di luar jam kirim: antrean JUJUR menunggu (tidak dikirim diam-diam, tidak dikarang terkirim)
        assert run["broadcast"]["queued"] >= 1 and run["broadcast"]["sent"] + run["broadcast"]["simulated"] == 0
        assert any("jam kirim" in n.lower() for n in run["run"]["notes"])
    else:
        assert run["broadcast"]["simulated"] + run["broadcast"]["sent"] >= 1
    for bid in (mk["id"], ut["id"]):
        requests.post(f"{API}/broadcasts/{bid}/cancel", headers=hdr, timeout=30)
    requests.delete(f"{API}/wa/optouts/{opt['data'][0]['id']}", headers=hdr, timeout=30)
    requests.delete(f"{API}/leads/{lead['id']}", headers=hdr, timeout=30)
    _purge(phone)


def test_broadcast_pause_resume_cancel(hdr):
    b = requests.post(f"{API}/broadcasts", json={"name": "ctrl", "template_code": "promo", "segment": {}}, headers=hdr, timeout=30).json()["data"]
    assert b["status"] == "queued" and b["read"] == 0 and b["delivered"] == 0 and "cost_estimate" in b
    p = requests.post(f"{API}/broadcasts/{b['id']}/pause", headers=hdr, timeout=30).json()["data"]
    assert p["status"] == "paused"
    r = requests.post(f"{API}/broadcasts/{b['id']}/resume", headers=hdr, timeout=30).json()["data"]
    assert r["status"] in ("sending", "queued", "completed")
    c = requests.post(f"{API}/broadcasts/{b['id']}/cancel", headers=hdr, timeout=30).json()["data"]
    assert c["status"] == "cancelled" and c["queued"] == 0


def test_quick_reply_from_queue(hdr):
    phone = _phone()
    requests.post(f"{API}/webhooks/wa", json=_inbound(phone, "Info harga dong", "Balas Cepat"), timeout=30)
    row = next(x for x in requests.get(f"{API}/wa/contacts", params={"q": phone}, headers=hdr, timeout=30).json()["data"] if x["phone"] == phone)
    r = requests.post(f"{API}/wa/contacts/{row['id']}/reply", json={"body": "Halo kak, harga mulai 850 juta."}, headers=hdr, timeout=30)
    assert r.status_code == 200
    d = r.json()["data"]
    assert d["message"]["status"] in ("simulated", "sent") and d["message"]["kind"] == "inbox" and d["conversation_id"] == row["conversation_id"]
    msgs = requests.get(f"{API}/wa/contacts/{row['id']}/messages", headers=hdr, timeout=30).json()["data"]["messages"]
    assert msgs[-1]["direction"] == "out" and msgs[-1]["body"].startswith("Halo kak")
    _purge(phone)


def test_send_document_via_wa(hdr):
    deals = requests.get(f"{API}/deals", params={"limit": 5}, headers=hdr, timeout=30).json()["data"]
    lead_id = next(d["lead_id"] for d in deals if d.get("lead_id"))
    hist = requests.get(f"{API}/doc-history/lead/{lead_id}", headers=hdr, timeout=30).json()["data"]
    assert "wa_send" in hist and "wa_shares" in hist
    docs = [x for dl in hist["deals"] for s in dl["stages"] for x in s["docs"] if x.get("pdf_url")]
    if not hist["wa_send"]["enabled"] or not docs:
        pytest.skip("lead demo tanpa nomor valid / dokumen")
    r = requests.post(f"{API}/doc-history/send-wa", json={"entity_type": "lead", "entity_id": lead_id, "pdf_url": docs[0]["pdf_url"],
                                                          "label": docs[0]["label"], "number": docs[0].get("number")}, headers=hdr, timeout=60)
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["message"]["kind"] == "document" and d["message"]["category"] == "utility" and d["share"]["file_id"]
    assert d["message"]["document"]["filename"].endswith(".pdf")
    hist2 = requests.get(f"{API}/doc-history/lead/{lead_id}", headers=hdr, timeout=30).json()["data"]
    assert any(s["id"] == d["share"]["id"] for s in hist2["wa_shares"])
    bad = requests.post(f"{API}/doc-history/send-wa", json={"entity_type": "lead", "entity_id": lead_id, "pdf_url": "/etc/passwd",
                                                            "label": "x"}, headers=hdr, timeout=30)
    assert bad.status_code == 400


def test_stats_card_equals_rows(hdr):
    s = requests.get(f"{API}/wa/stats", params={"days": 7}, headers=hdr, timeout=30).json()["data"]
    kind = next((k for k in s["by_kind"] if k["total"]), None)
    if not kind:
        pytest.skip("belum ada pesan keluar")
    rows = requests.get(f"{API}/wa/messages", params={"days": 7, "kind": kind["kind"], "limit": 1}, headers=hdr, timeout=30).json()
    assert rows["total"] == kind["total"]
