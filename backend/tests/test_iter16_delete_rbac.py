"""Iteration 16 — Delete API + RBAC + Appointment default location follows project."""
import os
import time
import requests
import pytest

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE}/api"
PWD = "Sipro#2026"

# ---------- helpers ----------

def login(email):
    r = requests.post(f"{API}/auth/login",
                      json={"email": email, "password": PWD}, timeout=30)
    assert r.status_code == 200, f"login {email}: {r.status_code} {r.text}"
    return r.json()["access_token"]

def h(tok):
    return {"Authorization": f"Bearer {tok}"}

@pytest.fixture(scope="module")
def sa_tok():
    return login("superadmin@sipro.co.id")

@pytest.fixture(scope="module")
def sales_tok():
    return login("sales@sipro.co.id")

@pytest.fixture(scope="module")
def mgr_tok():
    return login("manager@sipro.co.id")

@pytest.fixture(scope="module")
def pm_tok():
    return login("pm@sipro.co.id")


# ---------- Leads delete ----------

class TestLeadDelete:
    def test_a_positive_delete_flow(self, sa_tok):
        r = requests.post(f"{API}/leads", headers=h(sa_tok),
                          json={"name": "QA Hapus Lead",
                                "phone": "+6281299900011",
                                "source": "manual"}, timeout=30)
        assert r.status_code in (200, 201), r.text
        lead = r.json().get("data") or r.json()
        lid = lead["id"]

        r = requests.get(f"{API}/leads/{lid}/delete-check",
                         headers=h(sa_tok), timeout=30)
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["can_delete"] is True, d

        r = requests.delete(f"{API}/leads/{lid}", headers=h(sa_tok), timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("data", {}).get("deleted") is True, body

        r = requests.get(f"{API}/leads/{lid}", headers=h(sa_tok), timeout=30)
        assert r.status_code == 404

    def test_b_lead_with_deal_blocked(self, sa_tok):
        r = requests.get(f"{API}/deals?limit=20", headers=h(sa_tok), timeout=30)
        assert r.status_code == 200
        items = r.json().get("data") or r.json().get("items") or r.json()
        if isinstance(items, dict):
            items = items.get("items", [])
        lead_id = None
        for d in items:
            if d.get("lead_id"):
                lead_id = d["lead_id"]; break
        if not lead_id:
            pytest.skip("no deal with lead_id present")

        r = requests.get(f"{API}/leads/{lead_id}/delete-check",
                         headers=h(sa_tok), timeout=30)
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["can_delete"] is False, d
        # blockers keys should mention deal
        assert any("deal" in k.lower() for k in d["blockers"].keys()), d

        r = requests.delete(f"{API}/leads/{lead_id}",
                            headers=h(sa_tok), timeout=30)
        assert r.status_code == 400, r.text

    def test_rbac_sales_cannot_delete_lead(self, sales_tok, sa_tok):
        # create throwaway lead as sa
        r = requests.post(f"{API}/leads", headers=h(sa_tok),
                          json={"name": "QA RBAC Lead",
                                "phone": "+6281299900012",
                                "source": "manual"}, timeout=30)
        lid = (r.json().get("data") or r.json())["id"]
        r = requests.delete(f"{API}/leads/{lid}", headers=h(sales_tok), timeout=30)
        assert r.status_code == 403, r.text
        # cleanup
        requests.delete(f"{API}/leads/{lid}", headers=h(sa_tok), timeout=30)


# ---------- Project + Unit delete ----------

class TestProjectUnitDelete:
    def test_project_and_unit_lifecycle(self, sa_tok):
        # create project
        r = requests.post(f"{API}/projects", headers=h(sa_tok),
                          json={"name": "QA Hapus Proyek",
                                "code": f"QAHP{int(time.time())%1000}",
                                "location": "Jl. Uji 1"}, timeout=30)
        assert r.status_code in (200, 201), r.text
        proj = r.json()["data"]
        pid = proj["id"]

        # generate 2 units
        r = requests.post(f"{API}/projects/{pid}/units",
                          headers=h(sa_tok),
                          json={"prefix": "Q", "type": "Tipe 45/90",
                                "price": 500000000, "count": 2}, timeout=30)
        assert r.status_code == 200, r.text
        # fetch units via project detail
        r = requests.get(f"{API}/projects/{pid}",
                         headers=h(sa_tok), timeout=30)
        assert r.status_code == 200, r.text
        data = r.json().get("data", r.json())
        units = data.get("units") or []
        assert len(units) >= 2
        u1 = units[0]["id"]

        # unit delete-check
        r = requests.get(f"{API}/projects/{pid}/units/{u1}/delete-check",
                         headers=h(sa_tok), timeout=30)
        assert r.status_code == 200
        assert r.json()["data"]["can_delete"] is True

        # delete unit
        r = requests.delete(f"{API}/projects/{pid}/units/{u1}",
                            headers=h(sa_tok), timeout=30)
        assert r.status_code == 200, r.text

        # project delete-check
        r = requests.get(f"{API}/projects/{pid}/delete-check",
                         headers=h(sa_tok), timeout=30)
        assert r.status_code == 200
        assert r.json()["data"]["can_delete"] is True

        # delete project (cascades remaining unit)
        r = requests.delete(f"{API}/projects/{pid}",
                            headers=h(sa_tok), timeout=30)
        assert r.status_code == 200, r.text

        # verify gone
        r = requests.get(f"{API}/projects/{pid}",
                         headers=h(sa_tok), timeout=30)
        assert r.status_code == 404

    def test_demo_project_blocked(self, sa_tok):
        r = requests.get(f"{API}/projects", headers=h(sa_tok), timeout=30)
        assert r.status_code == 200
        items = r.json().get("data") or r.json().get("items") or r.json()
        if isinstance(items, dict):
            items = items.get("items", [])
        # find any project with real transactional data (demo)
        target = None
        for p in items:
            dc = requests.get(f"{API}/projects/{p['id']}/delete-check",
                              headers=h(sa_tok), timeout=30).json()["data"]
            if not dc["can_delete"]:
                target = (p, dc); break
        assert target is not None, "no demo project with blockers found"
        p, dc = target
        assert len(dc["blockers"]) > 0
        # expect Indonesian blocker labels
        keys = " ".join(dc["blockers"].keys()).lower()
        assert any(k in keys for k in ["unit", "deal", "kontrak", "invoice", "spk"]), dc
        r = requests.delete(f"{API}/projects/{p['id']}",
                            headers=h(sa_tok), timeout=30)
        assert r.status_code == 400, r.text

    def test_rbac_sales_cannot_delete_project(self, sales_tok, sa_tok):
        r = requests.get(f"{API}/projects", headers=h(sa_tok), timeout=30)
        items = r.json().get("data") or r.json().get("items") or r.json()
        if isinstance(items, dict):
            items = items.get("items", [])
        pid = items[0]["id"]
        r = requests.delete(f"{API}/projects/{pid}",
                            headers=h(sales_tok), timeout=30)
        assert r.status_code == 403, r.text


# ---------- Customer delete ----------

class TestCustomerDelete:
    def test_customer_lifecycle(self, sa_tok):
        r = requests.post(f"{API}/customers", headers=h(sa_tok),
                          json={"name": "QA Hapus Customer",
                                "phone": "+6281299900021",
                                "nik": "3200000000000021"}, timeout=30)
        assert r.status_code in (200, 201), r.text
        cust = r.json().get("data") or r.json()
        cid = cust["id"]

        r = requests.get(f"{API}/customers/{cid}/delete-check",
                         headers=h(sa_tok), timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["data"]["can_delete"] is True

        r = requests.delete(f"{API}/customers/{cid}",
                            headers=h(sa_tok), timeout=30)
        assert r.status_code == 200, r.text

    def test_customer_with_deal_blocked(self, sa_tok):
        r = requests.get(f"{API}/deals?limit=20", headers=h(sa_tok), timeout=30)
        items = r.json().get("data") or r.json().get("items") or r.json()
        if isinstance(items, dict):
            items = items.get("items", [])
        cid = None
        for d in items:
            if d.get("customer_id"):
                cid = d["customer_id"]; break
        if not cid:
            pytest.skip("no deal with customer_id present")
        r = requests.get(f"{API}/customers/{cid}/delete-check",
                         headers=h(sa_tok), timeout=30)
        assert r.status_code == 200
        assert r.json()["data"]["can_delete"] is False
        r = requests.delete(f"{API}/customers/{cid}",
                            headers=h(sa_tok), timeout=30)
        assert r.status_code == 400


# ---------- RBAC admin permissions matrix ----------

class TestPermissionsMatrix:
    def test_matrix_shows_delete_for_pm_and_sm(self, sa_tok):
        """CRITICAL: The DB-stored (enforced) permission matrix must include
        `delete` for projects/units (project_manager) and customers (sales_manager).
        If DEFAULT_PERMISSIONS was updated but DB matrix wasn't migrated, PM/SM
        cannot delete despite the code changes."""
        r = requests.get(f"{API}/admin/permissions",
                         headers=h(sa_tok), timeout=30)
        assert r.status_code == 200, r.text
        data = r.json().get("data", r.json())
        matrix = data.get("matrix", data)
        effective = data.get("effective", {})

        def eff(res, role):
            e = (effective.get(res) or {}).get(role) or {}
            return set(e.get("perms") or [])

        problems = []
        if "delete" not in eff("projects", "project_manager"):
            problems.append("projects/project_manager missing delete")
        if "delete" not in eff("units", "project_manager"):
            problems.append("units/project_manager missing delete")
        if "delete" not in eff("customers", "sales_manager"):
            problems.append("customers/sales_manager missing delete")
        if "delete" not in eff("leads", "sales_manager"):
            problems.append("leads/sales_manager missing delete")
        assert not problems, (
            "Enforced RBAC matrix does not grant delete as required: "
            + "; ".join(problems)
            + f"  matrix.projects.pm={matrix.get('projects', {}).get('project_manager')}"
            + f"  matrix.units.pm={matrix.get('units', {}).get('project_manager')}"
            + f"  matrix.customers.sm={matrix.get('customers', {}).get('sales_manager')}"
        )


# ---------- Appointment default location follows project ----------

class TestAppointmentLocation:
    def test_appointment_stores_project_and_location(self, sa_tok):
        # find a lead (any)
        r = requests.get(f"{API}/leads?limit=5", headers=h(sa_tok), timeout=30)
        items = r.json().get("data") or r.json().get("items") or r.json()
        if isinstance(items, dict):
            items = items.get("items", [])
        assert len(items) > 0
        lead = items[0]
        lid = lead["id"]

        # pick a project
        r = requests.get(f"{API}/projects", headers=h(sa_tok), timeout=30)
        pitems = r.json().get("data") or r.json().get("items") or r.json()
        if isinstance(pitems, dict):
            pitems = pitems.get("items", [])
        proj = pitems[0]
        pid = proj["id"]
        expected_loc = f"Kantor pemasaran {proj['name']}"
        if proj.get("location"):
            expected_loc = f"{expected_loc} — {proj['location']}"

        # create appointment (survey)
        import datetime
        when = (datetime.datetime.utcnow() +
                datetime.timedelta(days=2)).replace(microsecond=0).isoformat()
        payload = {
            "lead_id": lid, "type": "survey",
            "title": "QA Survey",
            "scheduled_at": when, "location": expected_loc,
            "project_id": pid,
        }
        r = requests.post(f"{API}/appointments", headers=h(sa_tok),
                          json=payload, timeout=30)
        assert r.status_code in (200, 201), r.text
        appt = r.json().get("data") or r.json()
        assert appt.get("project_id") == pid, appt
        assert appt.get("location") == expected_loc, appt
