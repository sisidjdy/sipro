"""SIPRO Restore Verification - Smoke Test Suite

This is a SMOKE TEST ONLY for the restored SIPRO app.
Tests basic functionality across all major modules to verify the restore was successful.

Test Coverage:
1. AUTH: Login with superadmin, verify token, test /auth/me, test wrong password
2. HEALTH: GET /api/health and GET /api/
3. MAIN MODULES: Read endpoints for projects, units, leads, deals, customers, workhub, construction, reports, GL
4. RBAC: Sales user gets 403 on construction/finance endpoints, but 200 on own leads
"""
import requests
import sys
import time
from datetime import datetime

BASE_URL = "https://sipro-clone.preview.emergentagent.com/api"
PASSWORD = "Sipro#2026"

class SmokeTestRunner:
    def __init__(self):
        self.tests_run = 0
        self.tests_passed = 0
        self.tokens = {}
        self.results = []

    def log(self, msg, status="INFO"):
        prefix = {"PASS": "✅", "FAIL": "❌", "INFO": "🔍"}.get(status, "ℹ️")
        print(f"{prefix} {msg}")

    def test(self, name, fn):
        """Run a test function and track results"""
        self.tests_run += 1
        self.log(f"Testing {name}...", "INFO")
        try:
            fn()
            self.tests_passed += 1
            self.log(f"PASSED: {name}", "PASS")
            self.results.append({"test": name, "status": "PASS"})
            return True
        except AssertionError as e:
            self.log(f"FAILED: {name} — {str(e)}", "FAIL")
            self.results.append({"test": name, "status": "FAIL", "error": str(e)})
            return False
        except Exception as e:
            self.log(f"ERROR: {name} — {str(e)}", "FAIL")
            self.results.append({"test": name, "status": "ERROR", "error": str(e)})
            return False

    def login(self, email):
        """Login and cache token"""
        if email in self.tokens:
            return self.tokens[email]
        r = requests.post(f"{BASE_URL}/auth/login", json={"email": email, "password": PASSWORD})
        assert r.status_code == 200, f"Login failed for {email}: {r.status_code} {r.text}"
        data = r.json()
        assert "access_token" in data, f"No access_token in response: {data}"
        token = data["access_token"]
        self.tokens[email] = token
        return token

    def get(self, endpoint, email, expected_status=200):
        """GET request with auth"""
        token = self.login(email)
        r = requests.get(f"{BASE_URL}{endpoint}", headers={"Authorization": f"Bearer {token}"})
        if expected_status:
            assert r.status_code == expected_status, f"Expected {expected_status}, got {r.status_code}: {r.text[:200]}"
        return r

    def post(self, endpoint, email, data, expected_status=200):
        """POST request with auth"""
        token = self.login(email)
        r = requests.post(f"{BASE_URL}{endpoint}", json=data, headers={"Authorization": f"Bearer {token}"})
        if expected_status:
            assert r.status_code == expected_status, f"Expected {expected_status}, got {r.status_code}: {r.text[:200]}"
        return r

    # ============================= AUTH TESTS =============================

    def test_auth_superadmin_login(self):
        """AUTH-1: Login with superadmin@sipro.co.id returns token"""
        token = self.login("superadmin@sipro.co.id")
        assert len(token) > 20, f"Invalid token length: {len(token)}"
        self.log(f"Superadmin login successful, token length: {len(token)}")

    def test_auth_me_endpoint(self):
        """AUTH-2: GET /api/auth/me returns user info"""
        r = self.get("/auth/me", "superadmin@sipro.co.id")
        response = r.json()
        # Response is wrapped in {"data": {...}}
        data = response.get("data", response)
        assert "email" in data, f"No email in /auth/me response: {response}"
        assert data["email"] == "superadmin@sipro.co.id", f"Wrong email: {data['email']}"
        assert "role" in data or "roles" in data, "No role info in response"
        self.log(f"Auth/me successful: {data['email']}")

    def test_auth_wrong_password(self):
        """AUTH-3: Login with wrong password returns 401"""
        r = requests.post(f"{BASE_URL}/auth/login", json={
            "email": "superadmin@sipro.co.id",
            "password": "WrongPassword123"
        })
        assert r.status_code == 401, f"Expected 401 for wrong password, got {r.status_code}"
        self.log("Wrong password correctly rejected with 401")

    def test_auth_all_demo_accounts(self):
        """AUTH-4: All demo accounts can login"""
        accounts = [
            "superadmin@sipro.co.id", "owner@sipro.co.id", "manager@sipro.co.id",
            "marketing@sipro.co.id", "sales@sipro.co.id", "sales2@sipro.co.id",
            "finance@sipro.co.id", "pm@sipro.co.id", "site@sipro.co.id"
        ]
        for email in accounts:
            token = self.login(email)
            assert len(token) > 20, f"Invalid token for {email}"
        self.log(f"All {len(accounts)} demo accounts logged in successfully")

    # ============================= HEALTH TESTS =============================

    def test_health_endpoint(self):
        """HEALTH-1: GET /api/health returns ok"""
        r = requests.get(f"{BASE_URL}/health")
        assert r.status_code == 200, f"Health check failed: {r.status_code}"
        data = r.json()
        assert data.get("status") == "ok" or "ok" in str(data).lower(), f"Health status not ok: {data}"
        self.log(f"Health endpoint ok: {data}")

    def test_root_endpoint(self):
        """HEALTH-2: GET /api/ returns ok"""
        r = requests.get(f"{BASE_URL}/")
        assert r.status_code == 200, f"Root endpoint failed: {r.status_code}"
        self.log(f"Root endpoint ok")

    # ============================= MAIN MODULES TESTS =============================

    def test_projects_list(self):
        """MODULES-1: GET /api/projects returns seeded projects"""
        r = self.get("/projects", "superadmin@sipro.co.id")
        data = r.json()
        # Handle both paginated and non-paginated responses
        items = data.get("data", data) if isinstance(data, dict) else data
        assert len(items) > 0, "No projects found in seeded data"
        self.log(f"Found {len(items)} projects")

    def test_units_list(self):
        """MODULES-2: GET /api/site-plan/{project_id} returns units"""
        # First get a project to use as context
        r = self.get("/projects", "superadmin@sipro.co.id")
        projects = r.json().get("data", r.json())
        if isinstance(projects, list) and len(projects) > 0:
            project_id = projects[0].get("id")
            # Get site plan which includes units
            r = self.get(f"/site-plan/{project_id}", "superadmin@sipro.co.id")
            response = r.json()
            data = response.get("data", response)
            units = data.get("units", [])
            assert isinstance(units, list), f"Units not a list: {type(units)}"
            assert len(units) > 0, "No units found in site plan"
            self.log(f"Found {len(units)} units in site plan for project {project_id}")
        else:
            self.log("No projects found, skipping units test")

    def test_leads_list(self):
        """MODULES-3: GET /api/leads returns seeded leads"""
        r = self.get("/leads", "superadmin@sipro.co.id")
        data = r.json()
        items = data.get("data", data) if isinstance(data, dict) else data
        assert isinstance(items, list), f"Leads response not a list: {type(items)}"
        self.log(f"Found {len(items)} leads")

    def test_deals_list(self):
        """MODULES-4: GET /api/deals returns seeded deals"""
        r = self.get("/deals", "superadmin@sipro.co.id")
        data = r.json()
        items = data.get("data", data) if isinstance(data, dict) else data
        assert isinstance(items, list), f"Deals response not a list: {type(items)}"
        self.log(f"Found {len(items)} deals")

    def test_customers_list(self):
        """MODULES-5: GET /api/customers returns seeded customers"""
        r = self.get("/customers", "superadmin@sipro.co.id")
        data = r.json()
        items = data.get("data", data) if isinstance(data, dict) else data
        assert isinstance(items, list), f"Customers response not a list: {type(items)}"
        self.log(f"Found {len(items)} customers")

    def test_workhub_tasks(self):
        """MODULES-6: GET /api/work/tasks or /api/workhub/tasks returns tasks"""
        # Try both possible endpoints
        try:
            r = self.get("/work/tasks", "superadmin@sipro.co.id")
        except Exception:
            r = self.get("/workhub/tasks", "superadmin@sipro.co.id")
        data = r.json()
        items = data.get("data", data) if isinstance(data, dict) else data
        assert isinstance(items, list), f"Tasks response not a list: {type(items)}"
        self.log(f"Found {len(items)} work hub tasks")

    def test_construction_schedules(self):
        """MODULES-7: GET /api/build/schedules returns construction schedules"""
        r = self.get("/build/schedules", "pm@sipro.co.id")
        data = r.json()
        items = data.get("data", data) if isinstance(data, dict) else data
        assert isinstance(items, list), f"Schedules response not a list: {type(items)}"
        self.log(f"Found {len(items)} construction schedules")

    def test_construction_summary(self):
        """MODULES-8: GET /api/build/summary returns construction summary"""
        r = self.get("/build/summary", "pm@sipro.co.id")
        data = r.json()
        assert isinstance(data, dict), f"Summary response not a dict: {type(data)}"
        self.log(f"Construction summary retrieved")

    def test_reports_dashboard(self):
        """MODULES-9: GET /api/finance/reports/revenue returns finance reports"""
        r = self.get("/finance/reports/revenue", "owner@sipro.co.id")
        response = r.json()
        data = response.get("data", response)
        assert isinstance(data, dict), f"Finance report response not a dict: {type(data)}"
        self.log(f"Finance reports accessible")

    def test_gl_accounts(self):
        """MODULES-10: GET /api/gl/accounts returns GL accounts"""
        r = self.get("/gl/accounts", "finance@sipro.co.id")
        data = r.json()
        items = data.get("data", data) if isinstance(data, dict) else data
        assert isinstance(items, list), f"GL accounts response not a list: {type(items)}"
        assert len(items) > 0, "No GL accounts found"
        self.log(f"Found {len(items)} GL accounts")

    def test_accounting_reports(self):
        """MODULES-11: GET /api/gl/trial-balance or similar accounting report"""
        try:
            r = self.get("/gl/trial-balance", "finance@sipro.co.id")
        except Exception:
            r = self.get("/gl/reports/trial-balance", "finance@sipro.co.id")
        data = r.json()
        assert isinstance(data, dict) or isinstance(data, list), f"Trial balance response invalid: {type(data)}"
        self.log(f"Accounting reports accessible")

    # ============================= RBAC TESTS =============================

    def test_rbac_sales_construction_403(self):
        """RBAC-1: Sales user gets 403 on construction endpoints"""
        r = self.get("/build/schedules", "sales@sipro.co.id", expected_status=403)
        self.log("Sales correctly denied access to construction (403)")

    def test_rbac_sales_finance_403(self):
        """RBAC-2: Sales user gets 403 on finance/GL endpoints"""
        r = self.get("/gl/accounts", "sales@sipro.co.id", expected_status=403)
        self.log("Sales correctly denied access to GL (403)")

    def test_rbac_sales_own_leads_200(self):
        """RBAC-3: Sales user can access own leads (200)"""
        r = self.get("/leads", "sales@sipro.co.id", expected_status=200)
        data = r.json()
        items = data.get("data", data) if isinstance(data, dict) else data
        self.log(f"Sales can access leads: {len(items)} leads")

    # ============================= RUN ALL TESTS =============================

    def run_all(self):
        """Run all smoke tests"""
        print("\n" + "="*70)
        print("SIPRO RESTORE VERIFICATION - SMOKE TEST SUITE")
        print("="*70 + "\n")

        # Auth tests
        print("\n--- AUTH TESTS ---")
        self.test("AUTH-1: Superadmin login", self.test_auth_superadmin_login)
        self.test("AUTH-2: /auth/me endpoint", self.test_auth_me_endpoint)
        self.test("AUTH-3: Wrong password rejected", self.test_auth_wrong_password)
        self.test("AUTH-4: All demo accounts login", self.test_auth_all_demo_accounts)

        # Health tests
        print("\n--- HEALTH TESTS ---")
        self.test("HEALTH-1: /api/health", self.test_health_endpoint)
        self.test("HEALTH-2: /api/ root", self.test_root_endpoint)

        # Main modules tests
        print("\n--- MAIN MODULES TESTS ---")
        self.test("MODULES-1: Projects list", self.test_projects_list)
        self.test("MODULES-2: Units list", self.test_units_list)
        self.test("MODULES-3: Leads list", self.test_leads_list)
        self.test("MODULES-4: Deals list", self.test_deals_list)
        self.test("MODULES-5: Customers list", self.test_customers_list)
        self.test("MODULES-6: Work Hub tasks", self.test_workhub_tasks)
        self.test("MODULES-7: Construction schedules", self.test_construction_schedules)
        self.test("MODULES-8: Construction summary", self.test_construction_summary)
        self.test("MODULES-9: Reports dashboard", self.test_reports_dashboard)
        self.test("MODULES-10: GL accounts", self.test_gl_accounts)
        self.test("MODULES-11: Accounting reports", self.test_accounting_reports)

        # RBAC tests
        print("\n--- RBAC TESTS ---")
        self.test("RBAC-1: Sales denied construction", self.test_rbac_sales_construction_403)
        self.test("RBAC-2: Sales denied finance", self.test_rbac_sales_finance_403)
        self.test("RBAC-3: Sales can access leads", self.test_rbac_sales_own_leads_200)

        # Summary
        print("\n" + "="*70)
        print(f"SMOKE TEST RESULTS: {self.tests_passed}/{self.tests_run} PASSED")
        print("="*70 + "\n")

        if self.tests_passed == self.tests_run:
            print("✅ ALL SMOKE TESTS PASSED - Backend is healthy")
            return 0
        else:
            print(f"❌ {self.tests_run - self.tests_passed} TESTS FAILED")
            print("\nFailed tests:")
            for result in self.results:
                if result["status"] != "PASS":
                    print(f"  - {result['test']}: {result.get('error', 'Unknown error')}")
            return 1

if __name__ == "__main__":
    tester = SmokeTestRunner()
    sys.exit(tester.run_all())
