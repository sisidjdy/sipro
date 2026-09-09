"""P115 — jenis izin kustom (setting permit.types_custom), reference dynamic permit_type,
notifikasi ringkasan lonceng, permit detail + status."""
import os

import pytest
import requests
from dotenv import dotenv_values

_env = dotenv_values("/app/frontend/.env")
BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL")
            or _env.get("REACT_APP_BACKEND_URL")).rstrip("/")
API = f"{BASE_URL}/api"
PASS = "Sipro#2026"
UNIT_ID = None  # diselesaikan dari API (unit demo pertama)


def _sess(email):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": PASS}, timeout=30)
    if r.status_code != 200:
        pytest.fail(f"login {email} failed {r.status_code}: {r.text[:300]}")
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {r.json()['access_token']}",
                      "Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def sa():
    s = _sess("superadmin@sipro.co.id")
    global UNIT_ID
    units = s.get(f"{API}/units", params={"limit": 5}, timeout=30).json().get("data") or []
    if not units:
        pytest.skip("tidak ada unit demo")
    UNIT_ID = units[0]["id"]
    return s


@pytest.fixture(scope="module")
def sales():
    return _sess("sales@sipro.co.id")


# --- notifikasi (dropdown lonceng) ---
class TestNotificationsSummary:
    def test_grouped_limit_summary(self, sa):
        r = sa.get(f"{API}/notifications", params={"limit": 6, "group": "true"}, timeout=30)
        assert r.status_code == 200, r.text[:300]
        j = r.json()
        assert isinstance(j.get("data"), list)
        assert len(j["data"]) <= 6
        s = j.get("summary")
        assert isinstance(s, dict), f"summary missing: {list(j)}"
        assert isinstance(s.get("unread"), int)
        assert isinstance(s.get("needs_action"), int)
        assert isinstance(s.get("per_category"), dict)
        for n in j["data"]:
            assert "id" in n and "title" in n and "category" in n
            assert "_id" not in n


# --- reference permit_type dinamis ---
class TestPermitTypeReference:
    def test_dynamic_custom_type_flow(self, sa):
        try:
            r = sa.put(f"{API}/settings/permit.types_custom",
                       json={"value": ["UJI_X"], "reason": "TEST_p115"}, timeout=30)
            assert r.status_code == 200, r.text[:300]

            g = sa.get(f"{API}/settings/effective",
                       params={"keys": "permit.types_custom"}, timeout=30)
            assert g.status_code == 200
            assert g.json()["data"]["permit.types_custom"] == ["UJI_X"]

            ref = sa.get(f"{API}/reference/permit_type", timeout=30)
            assert ref.json()["data"]["strict"] is False
            assert ref.json()["data"]["dynamic"] is True
            vals = [o["value"] for o in ref.json()["data"]["options"]]
            assert "UJI_X" in vals, f"custom type missing in reference: {vals}"
        finally:
            sa.put(f"{API}/settings/permit.types_custom",
                   json={"value": [], "reason": "TEST_p115 reset"}, timeout=30)

    def test_reset_removes_custom(self, sa):
        # reset lalu pastikan hilang (dijalankan dalam satu test agar tidak balapan
        # dengan test lain yang sengaja menyetel UJI_X)
        sa.put(f"{API}/settings/permit.types_custom",
               json={"value": ["UJI_RESET"], "reason": "TEST_p115"}, timeout=30)
        sa.put(f"{API}/settings/permit.types_custom",
               json={"value": [], "reason": "TEST_p115 reset"}, timeout=30)
        ref = sa.get(f"{API}/reference/permit_type", timeout=30)
        assert ref.status_code == 200
        vals = [o["value"] for o in ref.json()["data"]["options"]]
        assert "UJI_RESET" not in vals

    def test_sales_cannot_write_setting(self, sales):
        r = sales.put(f"{API}/settings/permit.types_custom",
                      json={"value": ["NOPE"]}, timeout=30)
        assert r.status_code in (401, 403), f"expected forbidden, got {r.status_code}"


# --- permits CRUD dengan type kustom + detail + status ---
class TestPermitCustomType:
    def test_create_with_custom_type_and_delete(self, sa):
        pid = None
        try:
            sa.put(f"{API}/settings/permit.types_custom",
                   json={"value": ["UJI_X"], "reason": "TEST_p115"}, timeout=30)
            cov = sa.get(f"{API}/permits/coverage", params={"unit_id": UNIT_ID}, timeout=30)
            assert cov.status_code == 200, cov.text[:300]
            project_id = cov.json()["data"]["chain"]["project_id"]

            c = sa.post(f"{API}/permits", json={
                "type": "UJI_X", "name": "TEST_p115 izin kustom",
                "project_id": project_id, "scope_type": "unit", "scope_id": UNIT_ID,
                "authority": "TEST DPMPTSP",
            }, timeout=30)
            assert c.status_code in (200, 201), c.text[:400]
            body = c.json()
            doc = body.get("data", body)
            pid = doc["id"]
            assert doc["type"] == "UJI_X"

            g = sa.get(f"{API}/permits/{pid}", timeout=30)
            assert g.status_code == 200
            gd = g.json().get("data", g.json())
            assert gd["type"] == "UJI_X"
            assert gd["name"] == "TEST_p115 izin kustom"
            assert "_id" not in gd

            # status change
            st = sa.post(f"{API}/permits/{pid}/status",
                         json={"status": "approved", "note": "TEST_p115"}, timeout=30)
            assert st.status_code == 200, st.text[:400]
            assert st.json().get("data", {}).get("status") == "approved"
            g2 = sa.get(f"{API}/permits/{pid}", timeout=30)
            assert g2.json().get("data", {})["status"] == "approved"
        finally:
            if pid:
                d = sa.delete(f"{API}/permits/{pid}", timeout=30)
                assert d.status_code in (200, 204, 404), d.text[:200]
            sa.put(f"{API}/settings/permit.types_custom",
                   json={"value": [], "reason": "TEST_p115 reset"}, timeout=30)
