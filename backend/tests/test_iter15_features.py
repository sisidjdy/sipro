"""Tests for iteration 15 features:
A) Lingkup Peran Bawaan - admin can change scope of built-in roles
B) Langkah Tanpa RAB - RAB list shows steps without rab rows
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"


def _login(email, password="Sipro#2026"):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login failed {r.status_code}: {r.text}"
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def admin_token():
    return _login("superadmin@sipro.co.id")


@pytest.fixture(scope="module")
def sales_token():
    return _login("sales@sipro.co.id")


def _h(tok):
    return {"Authorization": f"Bearer {tok}"}


# ============ Feature A: Built-in role scope ============

class TestBuiltinRoleScope:
    def test_get_roles_has_scope_fields(self, admin_token):
        r = requests.get(f"{API}/admin/roles", headers=_h(admin_token))
        assert r.status_code == 200, r.text
        roles = r.json().get("data") or r.json()
        # Find sales
        sales = None
        for item in roles:
            if item.get("code") == "sales":
                sales = item; break
        assert sales is not None, f"sales role not found in: {[r.get('code') for r in roles]}"
        assert "scope_default" in sales
        assert "scope_overridden" in sales
        assert sales["scope_default"] == "own"
        # After clean state
        # scope may be own initially
        print("initial sales:", sales.get("scope"), sales.get("scope_default"), sales.get("scope_overridden"))

    def test_update_scope_to_all(self, admin_token):
        r = requests.put(f"{API}/admin/roles/sales", json={"scope": "all"}, headers=_h(admin_token))
        assert r.status_code == 200, r.text
        data = r.json().get("data") or r.json()
        # unwrap if wrapped
        role = data.get("data", data)
        assert role.get("scope") == "all"
        assert role.get("scope_overridden") is True
        body = r.json()
        assert "note" in body or "note" in role or "message" in body, f"expected note: {body}"

    def test_get_roles_shows_updated_scope(self, admin_token):
        r = requests.get(f"{API}/admin/roles", headers=_h(admin_token))
        assert r.status_code == 200
        roles = r.json().get("data") or r.json()
        sales = next((x for x in roles if x.get("code") == "sales"), None)
        assert sales["scope"] == "all"
        assert sales["scope_overridden"] is True

    def test_update_label_rejected_for_builtin(self, admin_token):
        r = requests.put(f"{API}/admin/roles/sales", json={"label": "Xyz"}, headers=_h(admin_token))
        assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text}"

    def test_update_full_access_role_rejected(self, admin_token):
        r = requests.put(f"{API}/admin/roles/owner", json={"scope": "own"}, headers=_h(admin_token))
        assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text}"

    def test_invalid_scope_rejected(self, admin_token):
        r = requests.put(f"{API}/admin/roles/sales", json={"scope": "bogus"}, headers=_h(admin_token))
        assert r.status_code == 400

    def test_restore_default_scope(self, admin_token):
        r = requests.put(f"{API}/admin/roles/sales", json={"scope": "own"}, headers=_h(admin_token))
        assert r.status_code == 200, r.text
        body = r.json()
        role = body.get("data", body)
        assert role.get("scope") == "own"
        assert role.get("scope_overridden") is False


# ============ Feature A enforcement ============

class TestScopeEnforcement:
    def test_scope_enforcement_flow(self, admin_token, sales_token):
        # Ensure sales default = own
        requests.put(f"{API}/admin/roles/sales", json={"scope": "own"}, headers=_h(admin_token))
        time.sleep(0.5)

        # sales leads under 'own'
        r1 = requests.get(f"{API}/leads?limit=500", headers=_h(sales_token))
        assert r1.status_code == 200, r1.text
        j1 = r1.json()
        own_leads = j1.get("data") or j1.get("items") or (j1 if isinstance(j1, list) else [])
        own_count = len(own_leads) if isinstance(own_leads, list) else j1.get("total", 0)
        print(f"sales own leads count: {own_count}")

        # Admin view for reference
        ra = requests.get(f"{API}/leads?limit=500", headers=_h(admin_token))
        admin_j = ra.json()
        admin_leads = admin_j.get("data") or admin_j.get("items") or (admin_j if isinstance(admin_j, list) else [])
        admin_count = len(admin_leads) if isinstance(admin_leads, list) else admin_j.get("total", 0)
        print(f"admin leads count: {admin_count}")

        # Switch sales to all
        r = requests.put(f"{API}/admin/roles/sales", json={"scope": "all"}, headers=_h(admin_token))
        assert r.status_code == 200
        time.sleep(1.2)

        r2 = requests.get(f"{API}/leads?limit=500", headers=_h(sales_token))
        assert r2.status_code == 200
        j2 = r2.json()
        all_leads = j2.get("data") or j2.get("items") or (j2 if isinstance(j2, list) else [])
        all_count = len(all_leads) if isinstance(all_leads, list) else j2.get("total", 0)
        print(f"sales all-scope leads count: {all_count}")
        assert all_count >= own_count, f"expected >= {own_count}, got {all_count}"

        # /auth/me reflects role_scope
        me = requests.get(f"{API}/auth/me", headers=_h(sales_token))
        assert me.status_code == 200
        me_j = me.json()
        me_data = me_j.get("data", me_j)
        assert me_data.get("role_scope") == "all", f"expected role_scope=all, got {me_data.get('role_scope')} in {me_j}"

        # Restore
        rr = requests.put(f"{API}/admin/roles/sales", json={"scope": "own"}, headers=_h(admin_token))
        assert rr.status_code == 200
        time.sleep(0.8)

        r3 = requests.get(f"{API}/leads?limit=500", headers=_h(sales_token))
        j3 = r3.json()
        restored_leads = j3.get("data") or j3.get("items") or (j3 if isinstance(j3, list) else [])
        restored_count = len(restored_leads) if isinstance(restored_leads, list) else j3.get("total", 0)
        print(f"sales restored own count: {restored_count}")
        assert restored_count == own_count


# ============ Feature B: Steps without RAB ============

class TestStepsWithoutRab:
    def test_list_has_steps_without_rab(self, admin_token):
        r = requests.get(f"{API}/rab/templates/unit_type", headers=_h(admin_token))
        assert r.status_code == 200, r.text
        j = r.json()
        rows = j.get("data") or j
        assert isinstance(rows, list) and len(rows) > 0
        codes = {row.get("ref_code"): row for row in rows}
        for row in rows:
            assert "steps_without_rab" in row, f"row missing field: {row}"
            assert isinstance(row["steps_without_rab"], int)
        print("codes seen:", list(codes.keys()))

    def test_sync_check_tipe_36_72(self, admin_token):
        r = requests.get(f"{API}/rab/templates/unit_type/TIPE-36-72/sync-check", headers=_h(admin_token))
        assert r.status_code == 200, r.text
        body = r.json()
        data = body.get("data", body)
        assert data.get("has_template") is True
        assert isinstance(data.get("steps_without_rab"), list)
        assert isinstance(data.get("unknown_steps"), list)
        assert len(data["steps_without_rab"]) >= 1
        item = data["steps_without_rab"][0]
        assert "code" in item and "name" in item
        print(f"TIPE-36-72 has {len(data['steps_without_rab'])} steps without RAB")

    def test_add_rab_row_decrements_and_cleanup(self, admin_token):
        # Baseline
        r0 = requests.get(f"{API}/rab/templates/unit_type/TIPE-36-72/sync-check", headers=_h(admin_token))
        baseline = len(r0.json().get("data", r0.json())["steps_without_rab"])

        # Add a row for W1-01
        put_body = {"items": [{
            "code": "W1-01",
            "description": "Persiapan",
            "category": "persiapan",
            "uom": "unit",
            "qty": 1,
            "unit_price": 1000000,
            "step_code": "W1-01",
        }]}
        rp = requests.put(f"{API}/rab/templates/unit_type/TIPE-36-72", json=put_body, headers=_h(admin_token))
        assert rp.status_code == 200, rp.text

        # List should show baseline-1 for that type
        rl = requests.get(f"{API}/rab/templates/unit_type", headers=_h(admin_token))
        rows = rl.json().get("data") or rl.json()
        target = next((x for x in rows if x.get("ref_code") == "TIPE-36-72"), None)
        assert target is not None
        assert target["steps_without_rab"] == baseline - 1, f"expected {baseline-1}, got {target['steps_without_rab']}"

        rs = requests.get(f"{API}/rab/templates/unit_type/TIPE-36-72/sync-check", headers=_h(admin_token))
        codes = [x["code"] for x in rs.json().get("data", rs.json())["steps_without_rab"]]
        assert "W1-01" not in codes

        # Cleanup
        rc = requests.put(f"{API}/rab/templates/unit_type/TIPE-36-72", json={"items": []}, headers=_h(admin_token))
        assert rc.status_code == 200
