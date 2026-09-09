"""Fase 100 — wizard koneksi Cloud API: diagnosa, register (PIN), verifikasi ulang, langganan webhook, handshake.
Semua panggilan Graph di-mock (httpx.MockTransport); tidak ada panggilan nyata ke Meta."""
import asyncio
import json
import os
import sys

import httpx
import pytest

sys.path.insert(0, "/app/backend")
os.environ.setdefault("JWT_SECRET", "pytest-secret")

import wa_setup as ws  # noqa: E402

CREDS = {"token": "T", "phone_id": "PH", "waba_id": "WB", "app_secret": "S", "verify_token": "V"}


def _run(coro):
    return asyncio.run(coro)


def _cli(handler):
    return ws.MetaSetupClient(CREDS, transport=httpx.MockTransport(handler))


def test_register_ok_and_pin_validation():
    seen = {}

    def handler(req):
        seen["path"], seen["body"] = req.url.path, json.loads(req.content)
        return httpx.Response(200, json={"success": True})
    res = _run(_cli(handler).register("123456"))
    assert res["ok"] and seen["path"].endswith("/PH/register")
    assert seen["body"] == {"messaging_product": "whatsapp", "pin": "123456"}
    assert not ws.PIN_RE.match("12345") and not ws.PIN_RE.match("12345a")


def test_register_error_passthrough_with_hint():
    def handler(req):
        return httpx.Response(400, json={"error": {"code": 133005, "message": "Two step verification PIN mismatch"}})
    res = _run(_cli(handler).register("000000"))
    assert res["ok"] is False and res["error_code"] == "133005" and "PIN mismatch" in res["error_detail"]
    assert "PIN" in ws.REGISTER_HINT["133005"] and "verifikasi ulang" in ws.REGISTER_HINT["133006"]


def test_subscribe_and_list_subscribed_apps():
    def handler(req):
        assert req.url.path.endswith("/WB/subscribed_apps")
        if req.method == "POST":
            return httpx.Response(200, json={"success": True})
        return httpx.Response(200, json={"data": [{"whatsapp_business_api_data": {"name": "Sipro WA", "id": "1"}}]})
    cli = _cli(handler)
    assert _run(cli.subscribe())["ok"]
    subs = _run(cli.subscribed_apps())
    assert subs["ok"] and subs["data"]["data"][0]["whatsapp_business_api_data"]["name"] == "Sipro WA"


def test_phone_registered_rule():
    assert ws.phone_registered({"status": "CONNECTED"})
    assert ws.phone_registered({"status": "PENDING", "platform_type": "CLOUD_API"})
    assert not ws.phone_registered({"status": "PENDING", "platform_type": "NOT_APPLICABLE"})
    assert "belum terdaftar" in ws.PHONE_STATUS_HINT["PENDING"]


def test_request_and_verify_code_payloads():
    seen = []

    def handler(req):
        seen.append((req.url.path, json.loads(req.content)))
        return httpx.Response(200, json={"success": True})
    cli = _cli(handler)
    assert _run(cli.request_code("VOICE"))["ok"] and _run(cli.verify_code("482913"))["ok"]
    assert seen[0][0].endswith("/PH/request_code") and seen[0][1]["code_method"] == "VOICE"
    assert seen[1][0].endswith("/PH/verify_code") and seen[1][1] == {"code": "482913"}


def test_network_error_is_honest():
    def handler(req):
        raise httpx.ConnectError("boom")
    res = _run(_cli(handler).phone())
    assert res["ok"] is False and res["error_code"] == "network"


def test_public_base_validation():
    assert ws._public_base("https://sipro.co.id/") == "https://sipro.co.id"
    with pytest.raises(ValueError):
        ws._public_base("sipro.co.id")
    with pytest.raises(ValueError):
        ws._public_base("https://x.id/path?x=1")
