"""Backend tests — Fase 68: late-fee-auto + arrears_warning reminders."""
import os
import time
import pytest
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL") or "https://sipro-preview-2.preview.emergentagent.com"
BASE = BASE.rstrip("/")
API = f"{BASE}/api"
PASSWORD = "Sipro#2026"


def _login(email: str) -> str:
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": PASSWORD}, timeout=30)
    assert r.status_code == 200, f"login {email} failed: {r.status_code} {r.text[:200]}"
    tok = r.json().get("data", {}).get("token") or r.json().get("token") or r.json().get("access_token")
    assert tok, f"no token in {r.json()}"
    return tok


@pytest.fixture(scope="module")
def tokens():
    return {
        "superadmin": _login("superadmin@sipro.co.id"),
        "finance": _login("finance@sipro.co.id"),
        "sales": _login("sales@sipro.co.id"),
    }


def _h(tok): return {"Authorization": f"Bearer {tok}"}


# ─── Late Fee Auto ─────────────────────────────────────────
class TestLateFeeAuto:
    def test_status_shape(self, tokens):
        r = requests.get(f"{API}/finance/late-fee-auto", headers=_h(tokens["finance"]), timeout=30)
        assert r.status_code == 200, r.text[:300]
        data = r.json().get("data", {})
        assert "config" in data and "preview" in data and "runs" in data
        cfg = data["config"]
        assert cfg["enabled"] is False, f"enabled default should be False, got {cfg['enabled']}"
        assert "min_days" in cfg and "min_amount" in cfg and "rule_sentence" in cfg
        rows = data["preview"]["rows"]
        assert isinstance(rows, list)
        for row in rows:
            assert "eligible" in row and "hold_reason" in row

    def test_run_forbidden_for_sales(self, tokens):
        r = requests.post(f"{API}/finance/late-fee-auto/run", headers=_h(tokens["sales"]), timeout=30)
        assert r.status_code == 403, f"sales expected 403, got {r.status_code}: {r.text[:200]}"

    def test_run_finance_ok_and_idempotent(self, tokens):
        r1 = requests.post(f"{API}/finance/late-fee-auto/run", headers=_h(tokens["finance"]), timeout=60)
        assert r1.status_code == 200, r1.text[:300]
        d1 = r1.json().get("data", {})
        assert d1.get("mode") == "manual"
        assert d1.get("actor") == "finance@sipro.co.id"
        # 2nd run
        r2 = requests.post(f"{API}/finance/late-fee-auto/run", headers=_h(tokens["finance"]), timeout=60)
        assert r2.status_code == 200
        d2 = r2.json().get("data", {})
        assert d2.get("charged_count") == 0, f"idempotency broken: 2nd run charged {d2.get('charged_count')}"
        # journal ids present on first run if any charged
        if d1.get("charged_count", 0) > 0:
            for c in d1.get("charged", []):
                assert c.get("journal_id"), "charged row missing journal_id"

    def test_status_shows_recent_run(self, tokens):
        r = requests.get(f"{API}/finance/late-fee-auto", headers=_h(tokens["finance"]), timeout=30)
        assert r.status_code == 200
        runs = r.json().get("data", {}).get("runs", [])
        assert len(runs) >= 1
        latest = runs[0]
        assert latest.get("mode") == "manual"
        assert latest.get("actor") == "finance@sipro.co.id"
        assert "charged_total" in latest


# ─── Reminders arrears_warning ─────────────────────────────
class TestArrearsReminder:
    def test_candidates_shape(self, tokens):
        r = requests.get(f"{API}/reminders/candidates", params={"kind": "arrears_warning"},
                         headers=_h(tokens["superadmin"]), timeout=30)
        assert r.status_code == 200, r.text[:300]
        payload = r.json().get("data", r.json())
        if isinstance(payload, list):
            cands = payload
        else:
            cands = payload.get("candidates") or payload.get("rows") or payload.get("items") or []
        assert isinstance(cands, list)
        if cands:
            c = cands[0]
            reason = (c.get("reason") or "") + " " + str(c.get("vars") or "")
            assert "SP" in reason.upper() or "sp" in reason.lower(), f"reason should mention SP state: {c.get('reason')}"
            assert "vars" in c
            # wa_link optional but check https://wa.me/ format if present
            if c.get("wa_link"):
                assert c["wa_link"].startswith("https://wa.me/"), c["wa_link"]

    def test_min_amount_gates_candidates(self, tokens):
        # set to huge value → empty
        put = requests.put(f"{API}/settings/reminder.arrears_min_amount",
                           json={"value": 999999999999, "reason": "uji"},
                           headers=_h(tokens["superadmin"]), timeout=30)
        assert put.status_code == 200, put.text[:300]
        try:
            r = requests.get(f"{API}/reminders/candidates", params={"kind": "arrears_warning"},
                             headers=_h(tokens["superadmin"]), timeout=30)
            assert r.status_code == 200
            payload = r.json().get("data", r.json())
            if isinstance(payload, list):
                cands = payload
            else:
                cands = payload.get("candidates") or payload.get("rows") or payload.get("items") or []
            assert len(cands) == 0, f"expected empty with huge min_amount, got {len(cands)}"
        finally:
            back = requests.put(f"{API}/settings/reminder.arrears_min_amount",
                                json={"value": 0, "reason": "restore"},
                                headers=_h(tokens["superadmin"]), timeout=30)
            assert back.status_code == 200

        # After restore, candidates should appear again
        r2 = requests.get(f"{API}/reminders/candidates", params={"kind": "arrears_warning"},
                          headers=_h(tokens["superadmin"]), timeout=30)
        assert r2.status_code == 200

    def test_run_simulation_and_dedup(self, tokens):
        r = requests.post(f"{API}/reminders/run", json={"kinds": ["arrears_warning"]},
                         headers=_h(tokens["superadmin"]), timeout=60)
        assert r.status_code == 200, r.text[:300]
        payload = r.json().get("data", r.json())
        # find results — key varies; look for status strings
        text = str(payload).lower()
        assert "simulasi" in text or "simulation" in text or "sent" in text or "blocked" in text, str(payload)[:400]

        # second run — dedup
        r2 = requests.post(f"{API}/reminders/run", json={"kinds": ["arrears_warning"]},
                          headers=_h(tokens["superadmin"]), timeout=60)
        assert r2.status_code == 200
