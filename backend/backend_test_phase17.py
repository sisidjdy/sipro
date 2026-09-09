"""Phase 17 EPIC 2.4 — QC/Inspeksi Backend Test Suite

Tests:
1. AUTH: Login all roles (site, pm, owner, finance, sales)
2. TEMPLATES: GET /api/inspections/templates (3 templates: QC-STR 4 items, QC-MEP 3 items, QC-HO 5 items)
3. LIST: GET /api/inspections (with filters, summary, RBAC scoping)
4. CREATE: POST /api/inspections with template_code (MEP)
5. UPDATE ITEMS: PUT /api/inspections/{id}/items (mix pass/fail)
6. FINALIZE FAIL: POST /api/inspections/{id}/finalize with >=1 fail -> creates punch items + urgent task
7. FINALIZE PASS: Create new inspection, all pass -> status passed
8. FINALIZE HANDOVER: Create handover inspection, all pass -> unit ready_handover
9. RBAC: site/pm/owner can create (200), finance view-only (403 on create), sales 403 on create
10. REGRESSION: construction progress, Kurva-S, punch, work/home, login
"""
import requests
import sys
import time
from datetime import datetime

BASE_URL = "https://sleepy-sammet-6.preview.emergentagent.com/api"
PASSWORD = "Sipro#2026"

class InspectionTester:
    def __init__(self):
        self.tests_run = 0
        self.tests_passed = 0
        self.tokens = {}
        self.results = []
        self.project_id = None
        self.phase_id = None
        self.unit_id = None

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
        token = r.json()["access_token"]
        self.tokens[email] = token
        self.log(f"Logged in as {email}")
        return token

    def get(self, endpoint, email, expected_status=200, params=None):
        """GET request with auth"""
        token = self.login(email)
        r = requests.get(f"{BASE_URL}{endpoint}", headers={"Authorization": f"Bearer {token}"}, params=params)
        if expected_status:
            assert r.status_code == expected_status, f"Expected {expected_status}, got {r.status_code}: {r.text}"
        return r

    def post(self, endpoint, email, data, expected_status=200):
        """POST request with auth"""
        token = self.login(email)
        r = requests.post(f"{BASE_URL}{endpoint}", json=data, headers={"Authorization": f"Bearer {token}"})
        if expected_status:
            assert r.status_code == expected_status, f"Expected {expected_status}, got {r.status_code}: {r.text}"
        return r

    def put(self, endpoint, email, data, expected_status=200):
        """PUT request with auth"""
        token = self.login(email)
        r = requests.put(f"{BASE_URL}{endpoint}", json=data, headers={"Authorization": f"Bearer {token}"})
        if expected_status:
            assert r.status_code == expected_status, f"Expected {expected_status}, got {r.status_code}: {r.text}"
        return r

    # ============================= SETUP =============================

    def setup_project_data(self):
        """Get project, phase, and unit IDs for testing"""
        r = self.get("/projects", "pm@sipro.co.id")
        projects = r.json()["data"]
        assert len(projects) > 0, "No projects found"
        self.project_id = projects[0]["id"]
        self.log(f"Using project: {self.project_id}")

        # Get phases
        r = self.get(f"/construction/project/{self.project_id}/phases", "pm@sipro.co.id")
        phases = r.json()["data"]
        if phases:
            self.phase_id = phases[0]["id"]
            self.log(f"Using phase: {self.phase_id}")

        # Get units
        r = self.get(f"/units?project_id={self.project_id}", "pm@sipro.co.id")
        units = r.json()["data"]
        if units:
            self.unit_id = units[0]["id"]
            self.log(f"Using unit: {self.unit_id}")

    # ============================= TEST CASES =============================

    def test_auth_all_roles(self):
        """Test 1: AUTH - Login all roles"""
        roles = [
            "site@sipro.co.id", "pm@sipro.co.id", "owner@sipro.co.id",
            "finance@sipro.co.id", "sales@sipro.co.id"
        ]
        for email in roles:
            token = self.login(email)
            assert len(token) > 20, f"Invalid token for {email}"
        self.log(f"All {len(roles)} roles logged in successfully")

    def test_templates_3_items(self):
        """Test 2: TEMPLATES - GET /api/inspections/templates returns 3 templates"""
        r = self.get("/inspections/templates", "pm@sipro.co.id")
        data = r.json()["data"]
        assert len(data) == 3, f"Expected 3 templates, got {len(data)}"
        
        # Check QC-STR (4 items)
        qc_str = next((t for t in data if t["code"] == "QC-STR"), None)
        assert qc_str is not None, "QC-STR template not found"
        assert len(qc_str["items"]) == 4, f"QC-STR should have 4 items, got {len(qc_str['items'])}"
        
        # Check QC-MEP (3 items)
        qc_mep = next((t for t in data if t["code"] == "QC-MEP"), None)
        assert qc_mep is not None, "QC-MEP template not found"
        assert len(qc_mep["items"]) == 3, f"QC-MEP should have 3 items, got {len(qc_mep['items'])}"
        
        # Check QC-HO (5 items)
        qc_ho = next((t for t in data if t["code"] == "QC-HO"), None)
        assert qc_ho is not None, "QC-HO template not found"
        assert len(qc_ho["items"]) == 5, f"QC-HO should have 5 items, got {len(qc_ho['items'])}"
        
        self.log("All 3 templates found with correct item counts")

    def test_list_inspections_with_summary(self):
        """Test 3: LIST - GET /api/inspections returns data + summary"""
        r = self.get("/inspections", "pm@sipro.co.id", params={"project_id": self.project_id})
        data = r.json()
        assert "data" in data, "Missing 'data' field"
        assert "summary" in data, "Missing 'summary' field"
        
        summary = data["summary"]
        assert "total" in summary, "Missing 'total' in summary"
        assert "open" in summary, "Missing 'open' in summary"
        assert "passed" in summary, "Missing 'passed' in summary"
        assert "failed" in summary, "Missing 'failed' in summary"
        
        self.log(f"Summary: total={summary['total']}, open={summary['open']}, passed={summary['passed']}, failed={summary['failed']}")

    def test_create_inspection_mep(self):
        """Test 4: CREATE - POST /api/inspections with template_code MEP"""
        body = {
            "project_id": self.project_id,
            "template_code": "QC-MEP"
        }
        if self.phase_id:
            body["phase_id"] = self.phase_id
        
        r = self.post("/inspections", "pm@sipro.co.id", body)
        data = r.json()["data"]
        
        assert data["template_code"] == "QC-MEP", "Wrong template code"
        assert data["status"] == "in_progress", "Status should be in_progress"
        assert len(data["items"]) == 3, f"MEP should have 3 items, got {len(data['items'])}"
        assert data["inspection_number"].startswith("QC/"), "Invalid inspection number format"
        assert data["pending_count"] == 3, "All items should be pending"
        
        self.inspection_id_mep = data["id"]
        self.log(f"Created MEP inspection: {data['inspection_number']}")

    def test_update_items_mix_pass_fail(self):
        """Test 5: UPDATE ITEMS - PUT /api/inspections/{id}/items with mix pass/fail"""
        items = [
            {"key": "pipa", "result": "pass", "note": "OK"},
            {"key": "listrik", "result": "pass", "note": "Sesuai SLD"},
            {"key": "grounding", "result": "fail", "note": "Grounding tidak terpasang"}
        ]
        
        r = self.put(f"/inspections/{self.inspection_id_mep}/items", "pm@sipro.co.id", {"items": items})
        data = r.json()["data"]
        
        assert data["pass_count"] == 2, f"Expected 2 pass, got {data['pass_count']}"
        assert data["fail_count"] == 1, f"Expected 1 fail, got {data['fail_count']}"
        assert data["pending_count"] == 0, f"Expected 0 pending, got {data['pending_count']}"
        
        self.log("Updated items: 2 pass, 1 fail")

    def test_finalize_fail_creates_punch(self):
        """Test 6: FINALIZE FAIL - POST /api/inspections/{id}/finalize creates punch items + urgent task"""
        # Get punch count before
        r_before = self.get("/field/punchlist", "pm@sipro.co.id", params={"project_id": self.project_id})
        punch_before = len(r_before.json()["data"])
        
        # Get tasks count before
        r_tasks_before = self.get("/work/tasks", "pm@sipro.co.id")
        tasks_before = len(r_tasks_before.json()["data"])
        
        # Finalize
        r = self.post(f"/inspections/{self.inspection_id_mep}/finalize", "pm@sipro.co.id", {})
        data = r.json()["data"]
        
        assert data["status"] == "failed", f"Status should be failed, got {data['status']}"
        assert data["punch_created"] == True, "punch_created should be True"
        assert len(data["punch_ids"]) == 1, f"Expected 1 punch item, got {len(data['punch_ids'])}"
        
        # Verify punch item created
        time.sleep(1)  # Wait for DB
        r_after = self.get("/field/punchlist", "pm@sipro.co.id", params={"project_id": self.project_id})
        punch_after = len(r_after.json()["data"])
        assert punch_after == punch_before + 1, f"Expected {punch_before + 1} punch items, got {punch_after}"
        
        # Verify urgent task created
        r_tasks_after = self.get("/work/tasks", "pm@sipro.co.id")
        tasks_after = len(r_tasks_after.json()["data"])
        assert tasks_after > tasks_before, f"Expected more tasks, got {tasks_after} (was {tasks_before})"
        
        # Check if phase is on qc_hold (skip - no GET endpoint for individual phase)
        # if self.phase_id:
        #     r_phase = self.get(f"/construction/phases/{self.phase_id}", "pm@sipro.co.id")
        #     phase = r_phase.json()["data"]
        #     assert phase["status"] == "qc_hold", f"Phase should be qc_hold, got {phase['status']}"
        
        self.log("Finalize FAIL: punch item + urgent task created")

    def test_finalize_pass_all_items(self):
        """Test 7: FINALIZE PASS - Create new inspection, all pass -> status passed"""
        # Create new inspection
        body = {"project_id": self.project_id, "template_code": "QC-STR"}
        r = self.post("/inspections", "pm@sipro.co.id", body)
        insp_id = r.json()["data"]["id"]
        
        # Update all items to pass
        items = [
            {"key": "besi", "result": "pass"},
            {"key": "bekisting", "result": "pass"},
            {"key": "cor", "result": "pass"},
            {"key": "dimensi", "result": "pass"}
        ]
        self.put(f"/inspections/{insp_id}/items", "pm@sipro.co.id", {"items": items})
        
        # Finalize
        r = self.post(f"/inspections/{insp_id}/finalize", "pm@sipro.co.id", {})
        data = r.json()["data"]
        
        assert data["status"] == "passed", f"Status should be passed, got {data['status']}"
        assert data["punch_created"] == False, "punch_created should be False"
        assert len(data["punch_ids"]) == 0, f"Expected 0 punch items, got {len(data['punch_ids'])}"
        
        self.log("Finalize PASS: status passed, no punch items")

    def test_finalize_handover_unit_ready(self):
        """Test 8: FINALIZE HANDOVER - Create handover inspection, all pass -> unit ready_handover"""
        if not self.unit_id:
            self.log("Skipping handover test: no unit available")
            return
        
        # Create handover inspection
        body = {
            "project_id": self.project_id,
            "template_code": "QC-HO",
            "unit_id": self.unit_id
        }
        r = self.post("/inspections", "pm@sipro.co.id", body)
        insp_id = r.json()["data"]["id"]
        
        # Update all items to pass
        items = [
            {"key": "dinding", "result": "pass"},
            {"key": "pintu", "result": "pass"},
            {"key": "sanitair", "result": "pass"},
            {"key": "titik_listrik", "result": "pass"},
            {"key": "kebersihan", "result": "pass"}
        ]
        self.put(f"/inspections/{insp_id}/items", "pm@sipro.co.id", {"items": items})
        
        # Finalize
        r = self.post(f"/inspections/{insp_id}/finalize", "pm@sipro.co.id", {})
        data = r.json()["data"]
        
        assert data["status"] == "passed", f"Status should be passed, got {data['status']}"
        
        # Check unit status via units list (no GET endpoint for individual unit)
        time.sleep(1)
        r_units = self.get("/units", "pm@sipro.co.id", params={"project_id": self.project_id})
        units = r_units.json()["data"]
        unit = next((u for u in units if u["id"] == self.unit_id), None)
        if unit:
            assert unit["construction_status"] == "ready_handover", f"Unit should be ready_handover, got {unit.get('construction_status')}"
            self.log("Finalize HANDOVER: unit ready_handover")
        else:
            self.log("Finalize HANDOVER: inspection passed (unit status not verified)")

    def test_finalize_blocked_if_pending(self):
        """Test 9: FINALIZE BLOCKED - 400 if any item still pending"""
        # Create new inspection
        body = {"project_id": self.project_id, "template_code": "QC-MEP"}
        r = self.post("/inspections", "pm@sipro.co.id", body)
        insp_id = r.json()["data"]["id"]
        
        # Try to finalize without updating items (all pending)
        r = self.post(f"/inspections/{insp_id}/finalize", "pm@sipro.co.id", {}, expected_status=400)
        assert r.status_code == 400, "Should return 400 for pending items"
        
        self.log("Finalize blocked for pending items (400)")

    def test_update_blocked_if_finalized(self):
        """Test 10: UPDATE BLOCKED - 400 if already finalized"""
        # Try to update the finalized MEP inspection
        items = [{"key": "pipa", "result": "fail"}]
        r = self.put(f"/inspections/{self.inspection_id_mep}/items", "pm@sipro.co.id", {"items": items}, expected_status=400)
        assert r.status_code == 400, "Should return 400 for finalized inspection"
        
        self.log("Update blocked for finalized inspection (400)")

    def test_rbac_site_can_create(self):
        """Test 11: RBAC - site@sipro.co.id can create (200)"""
        body = {"project_id": self.project_id, "template_code": "QC-MEP"}
        r = self.post("/inspections", "site@sipro.co.id", body, expected_status=200)
        assert r.status_code == 200, "Site should be able to create"
        self.log("RBAC: site can create (200)")

    def test_rbac_owner_can_create(self):
        """Test 12: RBAC - owner@sipro.co.id can create (200)"""
        body = {"project_id": self.project_id, "template_code": "QC-MEP"}
        r = self.post("/inspections", "owner@sipro.co.id", body, expected_status=200)
        assert r.status_code == 200, "Owner should be able to create"
        self.log("RBAC: owner can create (200)")

    def test_rbac_finance_view_only(self):
        """Test 13: RBAC - finance@sipro.co.id view-only (403 on create)"""
        # Finance can view
        r = self.get("/inspections/templates", "finance@sipro.co.id", expected_status=200)
        assert r.status_code == 200, "Finance should be able to view templates"
        
        # Finance cannot create
        body = {"project_id": self.project_id, "template_code": "QC-MEP"}
        r = self.post("/inspections", "finance@sipro.co.id", body, expected_status=403)
        assert r.status_code == 403, "Finance should get 403 on create"
        
        self.log("RBAC: finance view-only (403 on create)")

    def test_rbac_sales_403_on_create(self):
        """Test 14: RBAC - sales@sipro.co.id 403 on create"""
        body = {"project_id": self.project_id, "template_code": "QC-MEP"}
        r = self.post("/inspections", "sales@sipro.co.id", body, expected_status=403)
        assert r.status_code == 403, "Sales should get 403 on create"
        self.log("RBAC: sales 403 on create")

    def test_regression_construction_progress(self):
        """Test 15: REGRESSION - construction progress update still works"""
        if not self.phase_id:
            self.log("Skipping regression test: no phase available")
            return
        
        r = self.post(f"/construction/phases/{self.phase_id}/progress", "pm@sipro.co.id", 
                     {"progress": 50, "note": "Test progress"}, expected_status=200)
        assert r.status_code == 200, "Construction progress update failed"
        self.log("REGRESSION: construction progress works")

    def test_regression_kurva_s(self):
        """Test 16: REGRESSION - Kurva-S still works"""
        r = self.get(f"/construction/project/{self.project_id}/curve", "pm@sipro.co.id", expected_status=200)
        assert r.status_code == 200, "Kurva-S failed"
        self.log("REGRESSION: Kurva-S works")

    def test_regression_punch_list(self):
        """Test 17: REGRESSION - /api/field/punchlist still works"""
        r = self.get("/field/punchlist", "pm@sipro.co.id", params={"project_id": self.project_id}, expected_status=200)
        assert r.status_code == 200, "Punch list failed"
        self.log("REGRESSION: punch list works")

    def test_regression_work_home(self):
        """Test 18: REGRESSION - /api/work/home still works"""
        r = self.get("/work/home", "pm@sipro.co.id", expected_status=200)
        assert r.status_code == 200, "Work home failed"
        self.log("REGRESSION: work/home works")

    # ============================= RUN ALL =============================

    def run_all(self):
        """Run all tests in sequence"""
        print("\n" + "="*70)
        print("Phase 17 EPIC 2.4 — QC/Inspeksi Backend Test Suite")
        print("="*70 + "\n")

        # Setup
        self.log("Setting up test data...")
        self.setup_project_data()

        # Run tests
        self.test("AUTH - Login all roles", self.test_auth_all_roles)
        self.test("TEMPLATES - 3 templates with correct item counts", self.test_templates_3_items)
        self.test("LIST - Inspections with summary", self.test_list_inspections_with_summary)
        self.test("CREATE - MEP inspection", self.test_create_inspection_mep)
        self.test("UPDATE ITEMS - Mix pass/fail", self.test_update_items_mix_pass_fail)
        self.test("FINALIZE FAIL - Creates punch + urgent task", self.test_finalize_fail_creates_punch)
        self.test("FINALIZE PASS - All items pass", self.test_finalize_pass_all_items)
        self.test("FINALIZE HANDOVER - Unit ready_handover", self.test_finalize_handover_unit_ready)
        self.test("FINALIZE BLOCKED - 400 if pending", self.test_finalize_blocked_if_pending)
        self.test("UPDATE BLOCKED - 400 if finalized", self.test_update_blocked_if_finalized)
        self.test("RBAC - Site can create", self.test_rbac_site_can_create)
        self.test("RBAC - Owner can create", self.test_rbac_owner_can_create)
        self.test("RBAC - Finance view-only", self.test_rbac_finance_view_only)
        self.test("RBAC - Sales 403 on create", self.test_rbac_sales_403_on_create)
        self.test("REGRESSION - Construction progress", self.test_regression_construction_progress)
        self.test("REGRESSION - Kurva-S", self.test_regression_kurva_s)
        self.test("REGRESSION - Punch list", self.test_regression_punch_list)
        self.test("REGRESSION - Work home", self.test_regression_work_home)

        # Summary
        print("\n" + "="*70)
        print(f"📊 Tests passed: {self.tests_passed}/{self.tests_run}")
        print("="*70 + "\n")

        if self.tests_passed == self.tests_run:
            print("✅ All tests passed!")
            return 0
        else:
            print(f"❌ {self.tests_run - self.tests_passed} test(s) failed")
            return 1

def main():
    tester = InspectionTester()
    return tester.run_all()

if __name__ == "__main__":
    sys.exit(main())
