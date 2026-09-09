"""Iteration 6 backend tests: health, login sweep, GL trial-balance, cancellations flow."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8001").rstrip("/")
API = f"{BASE_URL}/api"

ACCOUNTS = [
    "superadmin@sipro.co.id",
    "owner@sipro.co.id",
    "manager@sipro.co.id",
    "marketing@sipro.co.id",
    "sales@sipro.co.id",
    "sales2@sipro.co.id",
    "finance@sipro.co.id",
    "finlead@sipro.co.id",
    "pm@sipro.co.id",
    "site@sipro.co.id",
    "dmlead@sipro.co.id",
    "dm@sipro.co.id",
]
PASSWORD = "Sipro#2026"


def login(email, password=PASSWORD):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, f"login failed {email}: {r.status_code} {r.text}"
    data = r.json()
    token = data.get("access_token") or data.get("data", {}).get("access_token")
    assert token, f"no access_token for {email}: {data}"
    return token


def auth_header(token):
    return {"Authorization": f"Bearer {token}"}


def test_health_ok_with_events_pending():
    r = requests.get(f"{API}/health", timeout=10)
    assert r.status_code == 200
    j = r.json()
    assert j.get("status") == "ok"
    assert j.get("service") == "sipro-backend"
    assert "events_pending" in j
    assert isinstance(j["events_pending"], int)
    assert j["events_pending"] >= 0


@pytest.mark.parametrize("email", ACCOUNTS)
def test_login_all_seed_accounts(email):
    tok = login(email)
    assert len(tok) > 10


def test_trial_balance_superadmin():
    tok = login("superadmin@sipro.co.id")
    r = requests.get(f"{API}/gl/trial-balance", headers=auth_header(tok), timeout=20)
    assert r.status_code == 200, r.text
    body = r.json()
    # accept either list or {data:[...]}
    rows = body if isinstance(body, list) else body.get("data") or body.get("rows") or body.get("items")
    if isinstance(rows, dict):
        # maybe {"accounts":[...]}
        rows = rows.get("accounts") or rows.get("rows") or rows.get("items")
    assert rows, f"no trial balance rows: keys={list(body) if isinstance(body, dict) else type(body)}"
    assert len(rows) > 0


def test_cancellations_preview_manager_and_list_finance():
    # manager gets a contract, previews cancellation
    mgr = login("manager@sipro.co.id")
    r = requests.get(f"{API}/contracts", headers=auth_header(mgr), timeout=20)
    assert r.status_code == 200, r.text
    body = r.json()
    contracts = body if isinstance(body, list) else body.get("data") or body.get("items") or body.get("contracts")
    assert contracts, f"no contracts returned: {body}"
    # pick first active/non-cancelled
    contract_id = None
    for c in contracts:
        cid = c.get("id") or c.get("_id") or c.get("contract_id")
        state = (c.get("state") or c.get("status") or "").lower()
        if cid and "cancel" not in state:
            contract_id = cid
            break
    assert contract_id, f"no active contract; sample={contracts[0] if contracts else None}"

    r = requests.get(
        f"{API}/cancellations/preview",
        params={"contract_id": contract_id},
        headers=auth_header(mgr),
        timeout=20,
    )
    assert r.status_code == 200, r.text
    pv = r.json()
    data = pv.get("data") if isinstance(pv, dict) and "data" in pv else pv
    assert "can_request" in data, f"can_request missing: {pv}"
    assert isinstance(data["can_request"], bool)
    assert "blocks" in data, f"blocks missing: {pv}"
    assert isinstance(data["blocks"], list)

    # finance lists cancellations
    fin = login("finance@sipro.co.id")
    r = requests.get(f"{API}/cancellations", headers=auth_header(fin), timeout=20)
    assert r.status_code == 200, r.text
