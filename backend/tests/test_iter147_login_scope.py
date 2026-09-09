"""Fase iterasi 147 — verifikasi hanya super_admin yang tersisa & login demo ditolak."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # fallback to frontend .env if not exported
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
                    break
    except Exception:
        pass

# Skenario ini memotret keadaan PRODUKSI (akun demo sudah dipurge). Di lingkungan dev/uji
# `SEED_DEMO_USERS=true` akun demo justru wajib ada (semua gate memakainya) — dilewati jujur.
from dotenv import dotenv_values  # noqa: E402
if (os.environ.get("SEED_DEMO_USERS") or dotenv_values("/app/backend/.env").get("SEED_DEMO_USERS") or "false").lower() == "true":
    pytest.skip("SEED_DEMO_USERS=true: akun demo memang di-seed di lingkungan ini", allow_module_level=True)

SUPERADMIN_EMAIL = "superadmin@sipro.co.id"
SUPERADMIN_PASSWORD = "Sipro#2026"

DEMO_EMAILS = [
    "owner@sipro.co.id", "sales@sipro.co.id", "finance@sipro.co.id",
    "pm@sipro.co.id", "dmlead@sipro.co.id", "finlead@sipro.co.id",
    "owner@nusaproperti.co.id", "manager@sipro.co.id", "marketing@sipro.co.id",
    "site@sipro.co.id", "dm@sipro.co.id",
]


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": SUPERADMIN_EMAIL, "password": SUPERADMIN_PASSWORD},
                      timeout=15)
    assert r.status_code == 200, f"superadmin login failed: {r.status_code} {r.text}"
    body = r.json()
    tok = body.get("access_token")
    assert tok
    return tok


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


def test_superadmin_login_ok():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": SUPERADMIN_EMAIL, "password": SUPERADMIN_PASSWORD},
                      timeout=15)
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["email"] == SUPERADMIN_EMAIL
    assert data["role"] == "super_admin"


@pytest.mark.parametrize("email", DEMO_EMAILS)
def test_demo_users_rejected(email):
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": email, "password": SUPERADMIN_PASSWORD},
                      timeout=15)
    # 401 (not found / wrong pass) or 403 (inactive). Must not be 200.
    assert r.status_code in (401, 403), f"{email} unexpectedly returned {r.status_code}: {r.text}"


def test_admin_users_only_superadmin(admin_headers):
    r = requests.get(f"{BASE_URL}/api/admin/users?limit=100",
                     headers=admin_headers, timeout=15)
    assert r.status_code == 200
    body = r.json()
    users = body.get("data", [])
    emails = sorted(u["email"] for u in users)
    assert emails == [SUPERADMIN_EMAIL], f"Extra users present: {emails}"
    assert body.get("total") == 1


def test_create_and_login_new_user_then_deactivate(admin_headers):
    payload = {
        "name": "TEST Iter147 Staff",
        "email": "test_iter147_staff@sipro.co.id",
        "role": "sales",
        "phone": None,
        "password": "TestPass#2026",
    }
    # cleanup previous run if any
    r_list = requests.get(f"{BASE_URL}/api/admin/users?limit=100", headers=admin_headers, timeout=15).json()
    for u in r_list.get("data", []):
        if u["email"] == payload["email"]:
            requests.put(f"{BASE_URL}/api/admin/users/{u['id']}", headers=admin_headers,
                         json={"is_active": False}, timeout=15)

    r = requests.post(f"{BASE_URL}/api/admin/users", headers=admin_headers,
                      json=payload, timeout=15)
    assert r.status_code in (200, 201), f"create user failed: {r.status_code} {r.text}"
    created = r.json()["data"]
    assert created["email"] == payload["email"]
    user_id = created["id"]

    # New user can login
    r2 = requests.post(f"{BASE_URL}/api/auth/login",
                       json={"email": payload["email"], "password": payload["password"]},
                       timeout=15)
    assert r2.status_code == 200, f"new user login failed: {r2.status_code} {r2.text}"
    assert r2.json()["data"]["role"] == "sales"

    # Deactivate so DB is clean
    r3 = requests.put(f"{BASE_URL}/api/admin/users/{user_id}", headers=admin_headers,
                     json={"is_active": False}, timeout=15)
    assert r3.status_code == 200

    # After deactivation, login must be blocked
    r4 = requests.post(f"{BASE_URL}/api/auth/login",
                       json={"email": payload["email"], "password": payload["password"]},
                       timeout=15)
    assert r4.status_code in (401, 403)
