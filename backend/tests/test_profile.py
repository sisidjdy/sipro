"""Tests untuk endpoint Profil Saya: PUT /auth/me, POST /auth/me/password, GET /auth/me/activity."""
import os
import time
import pytest
import requests

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or "https://legal-pages-16.preview.emergentagent.com").rstrip("/")
PASSWORD = "Sipro#2026"
NEW_PASSWORD = "Sipro#2027"


def login(email, password=PASSWORD):
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password})
    return r


@pytest.fixture(scope="module")
def legal_token():
    r = login("legal@sipro.co.id")
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def super_token():
    r = login("superadmin@sipro.co.id")
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def H(token):
    return {"Authorization": f"Bearer {token}"}


# -------- PUT /auth/me
class TestUpdateMe:
    def test_no_token(self):
        r = requests.put(f"{BASE_URL}/api/auth/me", json={"name": "X"})
        assert r.status_code == 401

    def test_empty_body(self, legal_token):
        r = requests.put(f"{BASE_URL}/api/auth/me", json={}, headers=H(legal_token))
        assert r.status_code == 400

    def test_short_name(self, legal_token):
        r = requests.put(f"{BASE_URL}/api/auth/me", json={"name": "A"}, headers=H(legal_token))
        assert r.status_code == 400

    def test_update_name_and_phone(self, legal_token):
        r = requests.put(f"{BASE_URL}/api/auth/me",
                         json={"name": "Nama Baru Test", "phone": "+628111234567"},
                         headers=H(legal_token))
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        assert data["name"] == "Nama Baru Test"
        assert data["phone"] == "+628111234567"
        assert "permissions" in data
        assert "resource_labels" in data
        assert "legal" in data["resource_labels"]
        assert data["resource_labels"]["legal"] == "Legal & Privasi"

        # restore
        r2 = requests.put(f"{BASE_URL}/api/auth/me",
                          json={"name": "Lia Legal Putri"}, headers=H(legal_token))
        assert r2.status_code == 200

    def test_cannot_change_role_or_email(self, legal_token):
        # Send role/email, endpoint should ignore them (Pydantic model doesn't accept)
        r = requests.put(f"{BASE_URL}/api/auth/me",
                         json={"name": "Lia Legal Putri", "role": "owner", "email": "hacker@x.com"},
                         headers=H(legal_token))
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["role"] == "legal_admin"
        assert data["email"] == "legal@sipro.co.id"


# -------- GET /auth/me (resource_labels)
class TestMe:
    def test_legal_resource_labels(self, legal_token):
        r = requests.get(f"{BASE_URL}/api/auth/me", headers=H(legal_token))
        assert r.status_code == 200
        data = r.json()["data"]
        assert "resource_labels" in data
        for key in data["permissions"].keys():
            if key != "*":
                assert key in data["resource_labels"], f"missing label for {key}"

    def test_super_resource_labels_empty(self, super_token):
        r = requests.get(f"{BASE_URL}/api/auth/me", headers=H(super_token))
        data = r.json()["data"]
        assert data["permissions"] == {"*": ["*"]}
        assert data["resource_labels"] == {}


# -------- GET /auth/me/activity
class TestActivity:
    def test_activity_contains_self(self, legal_token):
        # trigger an update so we have at least one entry
        requests.put(f"{BASE_URL}/api/auth/me",
                     json={"name": "Lia Legal Putri"}, headers=H(legal_token))
        r = requests.get(f"{BASE_URL}/api/auth/me/activity", headers=H(legal_token))
        assert r.status_code == 200
        rows = r.json()["data"]
        assert isinstance(rows, list)
        assert len(rows) <= 20
        assert all(row.get("actor") == "legal@sipro.co.id" for row in rows)
        # at least one profile update
        assert any(row.get("resource") == "profile" and row.get("action") == "update" for row in rows)

    def test_no_token(self):
        r = requests.get(f"{BASE_URL}/api/auth/me/activity")
        assert r.status_code == 401


# -------- POST /auth/me/password  (gunakan finance)
class TestPasswordChange:
    def test_full_flow(self):
        # Login finance
        r = login("finance@sipro.co.id")
        assert r.status_code == 200
        tok = r.json()["access_token"]

        # wrong current
        r = requests.post(f"{BASE_URL}/api/auth/me/password",
                          json={"current_password": "salah", "new_password": NEW_PASSWORD},
                          headers=H(tok))
        assert r.status_code == 400
        assert "Kata sandi saat ini salah" in r.text

        # same as old
        r = requests.post(f"{BASE_URL}/api/auth/me/password",
                          json={"current_password": PASSWORD, "new_password": PASSWORD},
                          headers=H(tok))
        assert r.status_code == 400

        # too short - project uses custom handler converting pydantic 422 -> 400
        r = requests.post(f"{BASE_URL}/api/auth/me/password",
                          json={"current_password": PASSWORD, "new_password": "abc"},
                          headers=H(tok))
        assert r.status_code in (400, 422)

        # success
        r = requests.post(f"{BASE_URL}/api/auth/me/password",
                          json={"current_password": PASSWORD, "new_password": NEW_PASSWORD},
                          headers=H(tok))
        assert r.status_code == 200
        assert r.json()["data"]["ok"] is True

        # old password fails
        r = login("finance@sipro.co.id", PASSWORD)
        assert r.status_code == 401
        # new password works
        r = login("finance@sipro.co.id", NEW_PASSWORD)
        assert r.status_code == 200
        tok2 = r.json()["access_token"]

        # restore
        r = requests.post(f"{BASE_URL}/api/auth/me/password",
                          json={"current_password": NEW_PASSWORD, "new_password": PASSWORD},
                          headers=H(tok2))
        assert r.status_code == 200

        # verify restored
        r = login("finance@sipro.co.id", PASSWORD)
        assert r.status_code == 200
