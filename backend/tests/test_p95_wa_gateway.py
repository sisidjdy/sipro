"""Fase 95 — gateway WA: adapter simulasi, adapter Meta dengan HTTP mock (200/400/429/5xx), outbox retry."""
import asyncio
import json
import os
import sys

import httpx
import pytest

sys.path.insert(0, "/app/backend")
os.environ.setdefault("JWT_SECRET", "pytest-secret")

import wa_gateway as gw  # noqa: E402
import wa_outbox as ob  # noqa: E402
from meta_api import GRAPH_BASE  # noqa: E402

CREDS = {"token": "T", "phone_id": "PH", "waba_id": "WB", "app_secret": "S", "verify_token": "V"}


def _adapter(handler):
    return gw.MetaCloudAdapter(CREDS, transport=httpx.MockTransport(handler))


def _run(coro):
    return asyncio.run(coro)


def test_graph_base_single_source():
    assert gw.GRAPH == GRAPH_BASE and GRAPH_BASE.startswith("https://graph.facebook.com/v")


def test_simulation_adapter_is_honest():
    res = _run(gw.SimulationAdapter().send({"to": "62812", "type": "text"}))
    assert res["status"] == "simulated" and res["provider_message_id"].startswith("sim-")


def test_meta_adapter_200_returns_wamid():
    def handler(req):
        assert req.url.path == "/v26.0/PH/messages" or req.url.path.endswith("/PH/messages")
        body = json.loads(req.content)
        assert body["messaging_product"] == "whatsapp" and body["to"] == "6281234567890"
        return httpx.Response(200, json={"messages": [{"id": "wamid.OK1"}]})
    res = _run(_adapter(handler).send({"messaging_product": "whatsapp", "to": "6281234567890", "type": "text"}))
    assert res["status"] == "sent" and res["provider_message_id"] == "wamid.OK1"


def test_meta_adapter_400_is_failed_not_simulated():
    def handler(req):
        return httpx.Response(400, json={"error": {"code": 131047, "message": "Re-engagement message"}})
    res = _run(_adapter(handler).send({"to": "62", "type": "text"}))
    assert res["status"] == "failed" and res["error_code"] == "131047" and "Re-engagement" in res["error_detail"]
    assert res["status"] != "simulated"


def test_meta_adapter_retries_on_429_then_succeeds(monkeypatch):
    calls = {"n": 0}
    monkeypatch.setattr(gw, "RETRY_DELAYS", (0, 0, 0))

    def handler(req):
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(429, json={"error": {"code": 130429, "message": "Rate limit hit"}})
        return httpx.Response(200, json={"messages": [{"id": "wamid.RETRY"}]})
    res = _run(_adapter(handler).send({"to": "62", "type": "text"}))
    assert calls["n"] == 3 and res["status"] == "sent" and res["provider_message_id"] == "wamid.RETRY"


def test_meta_adapter_5xx_exhausts_retries_failed(monkeypatch):
    monkeypatch.setattr(gw, "RETRY_DELAYS", (0, 0, 0))
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        return httpx.Response(503, json={"error": {"code": 2, "message": "Service temporarily unavailable"}})
    res = _run(_adapter(handler).send({"to": "62", "type": "text"}))
    assert calls["n"] == 4 and res["status"] == "failed" and res["error_code"] == "2"


def test_template_payload_and_params_order():
    tmpl = {"code": "payment_reminder", "meta_name": "payment_reminder_v2", "language": "id",
            "variables": ["nama", "jumlah", "jatuh_tempo"]}
    params = gw.template_params(tmpl, {"jumlah": "Rp 1.000", "nama": "Budi", "jatuh_tempo": "2026-09-10"})
    assert params == ["Budi", "Rp 1.000", "2026-09-10"]
    payload = gw._template_payload("62812", tmpl, params)
    assert payload["type"] == "template" and payload["template"]["name"] == "payment_reminder_v2"
    assert [p["text"] for p in payload["template"]["components"][0]["parameters"]] == params


def test_outbox_transient_vs_permanent_codes():
    assert ob.is_transient("429") and ob.is_transient("503") and ob.is_transient("network") and ob.is_transient("130429")
    assert not ob.is_transient("131047") and not ob.is_transient("132000") and not ob.is_transient("opt_out")
    assert not ob.is_transient("template_not_approved") and not ob.is_transient("131026")


def test_window_open_single_truth():
    assert gw.window_open({"window_expires_at": "2999-01-01T00:00:00+00:00"}) is True
    assert gw.window_open({"window_expires_at": "2000-01-01T00:00:00+00:00"}) is False
    assert gw.window_open(None) is False
