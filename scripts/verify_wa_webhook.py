#!/usr/bin/env python3
"""verify_wa_webhook.py — GATE Fase 96: webhook Meta WhatsApp.

  H1  Handshake GET hub.challenge dibalas apa adanya bila verify token cocok; 403 bila tidak.
  H2  Tanda tangan X-Hub-Signature-256 palsu ditolak 403 saat app secret terpasang (raw body, compare_digest).
  H3  Idempoten: wamid ganda tidak menghasilkan pesan kedua.
  H4  Kontrak lama `WebhookLead` tetap hidup di POST /webhooks/wa.
  H5  Status `failed` dari Meta menyimpan errors[0].code/title pada pesan keluar.
  H6  Balas cepat: endpoint memakai task + batas waktu (< 5 detik), payload tak dikenal → capture_failures.
"""
import hashlib
import hmac
import json
import pathlib
import sys
import uuid

import requests

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _wa_common import BASE, BE, check, finish, hdr, meta_payload, phone, purge_leads, wa_channel_guard  # noqa: E402


def main():
    h = hdr()
    vt = f"gate-verify-{uuid.uuid4().hex[:6]}"
    secret = f"gate-secret-{uuid.uuid4().hex[:6]}"
    requests.put(f"{BASE}/wa/config", headers=h, json={"verify_token": vt, "app_secret": secret}, timeout=20)
    try:
        print("== H1 handshake ==")
        ok = requests.get(f"{BASE}/webhooks/wa", params={"hub.mode": "subscribe", "hub.verify_token": vt,
                                                          "hub.challenge": "CHALLENGE-123"}, timeout=15)
        check(ok.status_code == 200 and ok.text == "CHALLENGE-123", "H1 hub.challenge dibalas apa adanya", f"{ok.status_code} {ok.text[:40]}")
        bad = requests.get(f"{BASE}/webhooks/wa", params={"hub.mode": "subscribe", "hub.verify_token": "salah",
                                                           "hub.challenge": "X"}, timeout=15)
        check(bad.status_code == 403, "H1b verify token salah → 403", str(bad.status_code))

        print("== H2 tanda tangan ==")
        ph = phone()
        body = json.dumps(meta_payload(ph, "halo")).encode()
        r = requests.post(f"{BASE}/webhooks/wa", data=body, headers={"Content-Type": "application/json",
                                                                     "X-Hub-Signature-256": "sha256=deadbeef"}, timeout=15)
        check(r.status_code == 403, "H2 signature palsu → 403", str(r.status_code))
        r = requests.post(f"{BASE}/webhooks/wa", data=body, headers={"Content-Type": "application/json"}, timeout=15)
        check(r.status_code == 403, "H2b tanpa signature saat app secret ada → 403", str(r.status_code))
        sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        r = requests.post(f"{BASE}/webhooks/wa", data=body, headers={"Content-Type": "application/json",
                                                                     "X-Hub-Signature-256": sig}, timeout=15)
        check(r.status_code == 200 and r.json().get("signature_ok") is True, "H2c signature sah → 200", r.text[:120])
        src = (BE / "wa_inbound.py").read_text()
        check("hmac.compare_digest" in src and "await request.body()" in (BE / "routers/webhooks_router.py").read_text(),
              "H2d HMAC atas raw body + compare_digest")
    finally:
        requests.put(f"{BASE}/wa/config", headers=h, json={"app_secret": "__clear__"}, timeout=20)

    print("== H3 idempoten ==")
    ph, wamid = phone(), f"wamid.GATE{uuid.uuid4().hex}"
    r1 = requests.post(f"{BASE}/webhooks/wa", json=meta_payload(ph, "pesan 1", wamid), timeout=15).json()["data"]
    r2 = requests.post(f"{BASE}/webhooks/wa", json=meta_payload(ph, "pesan 1", wamid), timeout=15).json()["data"]
    check(r1.get("messages") == 1 and r2.get("duplicates") == 1, "H3 wamid ganda → duplicates=1", f"{r1} {r2}")

    print("== H4 kontrak lama ==")
    r = requests.post(f"{BASE}/webhooks/wa", json={"name": "Gate Lama", "phone": phone(), "message": "kontrak lama"}, timeout=15)
    check(r.status_code in (200, 202) and r.json()["data"].get("provider") == "whatsapp", "H4 WebhookLead lama diterima", r.text[:120])

    print("== H5 status failed ==")
    sent = requests.post(f"{BASE}/wa/config/test-message", headers=h, json={"to": phone()}, timeout=15).json()["data"]
    wid = sent["provider_message_id"]
    st = {"object": "whatsapp_business_account", "entry": [{"id": "G", "changes": [{"field": "messages", "value": {
        "messaging_product": "whatsapp", "statuses": [{"id": wid, "status": "failed", "timestamp": "1757000001",
                                                       "recipient_id": "62", "errors": [{"code": 131047, "title": "Re-engagement message"}]}]}}]}]}
    requests.post(f"{BASE}/webhooks/wa", json=st, timeout=15)
    rows = requests.get(f"{BASE}/wa/messages", headers=h, params={"kind": "test", "status": "failed", "code": "131047", "limit": 50}, timeout=15).json()["data"]
    check(any(r.get("provider_message_id") == wid and r.get("error_detail") == "Re-engagement message" for r in rows),
          "H5 status failed menyimpan errors[0].code/title", str(len(rows)))

    print("== H6 balas cepat & payload asing ==")
    wr = (BE / "routers/webhooks_router.py").read_text()
    check("asyncio.create_task" in wr and "asyncio.wait(" in wr and "timeout=4.0" in wr, "H6 proses sebagai task dengan batas 4 detik")
    r = requests.post(f"{BASE}/webhooks/wa", json={"object": "whatsapp_business_account", "entry": [{"id": "G", "changes": [
        {"field": "sesuatu_baru", "value": {"x": 1}}]}]}, timeout=15).json()["data"]
    check(r.get("unknown") == 1, "H6b field tak dikenal → capture_failures (unknown=1)", str(r))
    purge_leads(["Kontrak Lama", "Gate Lama"])


if __name__ == "__main__":
    with wa_channel_guard():
        main()
    finish("verify_wa_webhook")
