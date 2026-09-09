"""RBAC smoke for Fase 85-87: sales 403, finance 403 on lock/approve."""
import os, requests, pytest

BASE = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE:
    # fallback to reading from frontend/.env
    import pathlib
    envp = pathlib.Path("/app/frontend/.env").read_text()
    for line in envp.splitlines():
        if line.startswith("REACT_APP_BACKEND_URL="):
            BASE = line.split("=", 1)[1].strip().rstrip("/")


def _login(email, pw):
    r = requests.post(f"{BASE}/api/auth/login", json={"email": email, "password": pw}, timeout=15)
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def sales_hdr():
    return {"Authorization": f"Bearer {_login('sales@sipro.co.id', 'Sipro#2026')}"}


@pytest.fixture(scope="module")
def finance_hdr():
    return {"Authorization": f"Bearer {_login('finance@sipro.co.id', 'Sipro#2026')}"}


def test_sales_pdc_forbidden(sales_hdr):
    r = requests.get(f"{BASE}/api/pdc", headers=sales_hdr, timeout=15)
    assert r.status_code == 403


def test_sales_locks_forbidden(sales_hdr):
    r = requests.get(f"{BASE}/api/cash-bank/locks", headers=sales_hdr, timeout=15)
    assert r.status_code == 403


def test_finance_cannot_lock(finance_hdr):
    # Grab a valid account_id first via list
    r = requests.get(f"{BASE}/api/cash-bank/locks", headers=finance_hdr, timeout=15)
    # finance may be allowed to view or not; the write must be 403
    payload = {"account_id": "any-id", "period": "2025-12", "counted_balance": 0}
    r2 = requests.post(f"{BASE}/api/cash-bank/locks", json=payload, headers=finance_hdr, timeout=15)
    assert r2.status_code == 403
