"""Backend test for Phase 18 — Material Requisition + Budget Alert.

Tests:
- GET /api/materials/requisitions (with summary)
- POST /api/materials/requisitions (create as site)
- POST /api/materials/requisitions/{id}/approve (PM can, site cannot - SoD)
- POST /api/materials/requisitions/{id}/issue (creates txn, checks budget)
- GET /api/materials/project/{project_id}/budget (over_budget flag)
- Over-budget alert: auto-created task for PM
- RBAC: sales/finance cannot create requisitions
- Regression: material txn, opname still work
"""
import requests
import sys
from datetime import datetime

BASE_URL = "https://sleepy-sammet-6.preview.emergentagent.com/api"
PASSWORD = "Sipro#2026"

class Phase18Tester:
    def __init__(self):
        self.tests_run = 0
        self.tests_passed = 0
        self.tokens = {}
        self.project_id = None
        self.material_ids = {}
        self.req_id = None

    def log(self, msg, status="info"):
        prefix = {"info": "ℹ️", "pass": "✅", "fail": "❌", "warn": "⚠️"}
        print(f"{prefix.get(status, 'ℹ️')} {msg}")

    def test(self, name, method, endpoint, expected_status, user="pm", data=None, params=None):
        """Run a single API test."""
        url = f"{BASE_URL}/{endpoint}"
        headers = {"Content-Type": "application/json"}
        if user and user in self.tokens:
            headers["Authorization"] = f"Bearer {self.tokens[user]}"

        self.tests_run += 1
        self.log(f"Testing {name}...", "info")

        try:
            if method == "GET":
                response = requests.get(url, headers=headers, params=params, timeout=10)
            elif method == "POST":
                response = requests.post(url, json=data, headers=headers, timeout=10)
            elif method == "PUT":
                response = requests.put(url, json=data, headers=headers, timeout=10)

            success = response.status_code == expected_status
            if success:
                self.tests_passed += 1
                self.log(f"PASSED - {name} (status {response.status_code})", "pass")
                return True, response.json() if response.text else {}
            else:
                self.log(f"FAILED - {name} (expected {expected_status}, got {response.status_code})", "fail")
                if response.text:
                    self.log(f"Response: {response.text[:200]}", "warn")
                return False, {}

        except Exception as e:
            self.log(f"FAILED - {name} (error: {str(e)})", "fail")
            return False, {}

    def login(self, email, role_name):
        """Login and store token."""
        self.log(f"Logging in as {email}...", "info")
        success, resp = self.test(
            f"Login {role_name}",
            "POST",
            "auth/login",
            200,
            user=None,
            data={"email": email, "password": PASSWORD}
        )
        if success and "access_token" in resp:
            self.tokens[role_name] = resp["access_token"]
            return True
        return False

    def setup(self):
        """Login all users and get project/material IDs."""
        self.log("=== SETUP: Login & Get IDs ===", "info")
        
        # Login all users
        users = [
            ("pm@sipro.co.id", "pm"),
            ("site@sipro.co.id", "site"),
            ("finance@sipro.co.id", "finance"),
            ("sales@sipro.co.id", "sales"),
            ("owner@sipro.co.id", "owner"),
        ]
        for email, role in users:
            if not self.login(email, role):
                self.log(f"Failed to login {email}", "fail")
                return False

        # Get first project
        success, resp = self.test("Get projects", "GET", "projects", 200, user="pm")
        if success and resp.get("data"):
            self.project_id = resp["data"][0]["id"]
            self.log(f"Using project: {self.project_id}", "info")
        else:
            self.log("No projects found", "fail")
            return False

        # Get materials
        success, resp = self.test(
            "Get materials",
            "GET",
            f"materials/project/{self.project_id}",
            200,
            user="pm"
        )
        if success and resp.get("data"):
            for mat in resp["data"]:
                self.material_ids[mat["code"]] = mat["id"]
            self.log(f"Found {len(self.material_ids)} materials", "info")
        else:
            self.log("No materials found", "fail")
            return False

        return True

    def test_requisitions_list(self):
        """Test GET /api/materials/requisitions with summary."""
        self.log("\n=== TEST: List Requisitions ===", "info")
        
        success, resp = self.test(
            "List requisitions",
            "GET",
            "materials/requisitions",
            200,
            user="pm",
            params={"project_id": self.project_id}
        )
        
        if success:
            data = resp.get("data", [])
            summary = resp.get("summary", {})
            self.log(f"Found {len(data)} requisitions", "info")
            self.log(f"Summary: total={summary.get('total')}, submitted={summary.get('submitted')}, approved={summary.get('approved')}, issued={summary.get('issued')}", "info")
            
            # Check seeded requisitions
            req_numbers = [r.get("req_number") for r in data]
            if "PR/2026/0001" in req_numbers:
                self.log("Found seeded PR/2026/0001", "pass")
            else:
                self.log("Missing seeded PR/2026/0001", "warn")
            
            if "PR/2026/0002" in req_numbers:
                self.log("Found seeded PR/2026/0002", "pass")
            else:
                self.log("Missing seeded PR/2026/0002", "warn")
            
            return True
        return False

    def test_create_requisition(self):
        """Test POST /api/materials/requisitions as site engineer."""
        self.log("\n=== TEST: Create Requisition (Site) ===", "info")
        
        # Get a material ID
        mat_id = list(self.material_ids.values())[0] if self.material_ids else None
        if not mat_id:
            self.log("No materials available", "fail")
            return False
        
        success, resp = self.test(
            "Create requisition (site)",
            "POST",
            "materials/requisitions",
            200,
            user="site",
            data={
                "project_id": self.project_id,
                "purpose": "Test requisition from automated test",
                "items": [{"material_id": mat_id, "qty": 10}]
            }
        )
        
        if success:
            req = resp.get("data", {})
            self.req_id = req.get("id")
            req_number = req.get("req_number")
            status = req.get("status")
            self.log(f"Created requisition {req_number} with status '{status}'", "pass")
            
            if status == "submitted":
                self.log("Status is 'submitted' as expected", "pass")
                return True
            else:
                self.log(f"Unexpected status: {status}", "fail")
        return False

    def test_rbac_create(self):
        """Test RBAC: sales/finance cannot create requisitions."""
        self.log("\n=== TEST: RBAC - Create Requisition ===", "info")
        
        mat_id = list(self.material_ids.values())[0] if self.material_ids else None
        if not mat_id:
            return False
        
        # Sales should get 403
        success, _ = self.test(
            "Create requisition (sales) - should fail",
            "POST",
            "materials/requisitions",
            403,
            user="sales",
            data={
                "project_id": self.project_id,
                "purpose": "Test",
                "items": [{"material_id": mat_id, "qty": 5}]
            }
        )
        
        # Finance should get 403
        success2, _ = self.test(
            "Create requisition (finance) - should fail",
            "POST",
            "materials/requisitions",
            403,
            user="finance",
            data={
                "project_id": self.project_id,
                "purpose": "Test",
                "items": [{"material_id": mat_id, "qty": 5}]
            }
        )
        
        return success and success2

    def test_approve_sod(self):
        """Test SoD: PM can approve, site cannot."""
        self.log("\n=== TEST: Approve Requisition (SoD) ===", "info")
        
        if not self.req_id:
            self.log("No requisition ID available", "fail")
            return False
        
        # Site should NOT be able to approve (403)
        success_fail, _ = self.test(
            "Approve as site (should fail - SoD)",
            "POST",
            f"materials/requisitions/{self.req_id}/approve",
            403,
            user="site"
        )
        
        # PM should be able to approve
        success_pass, resp = self.test(
            "Approve as PM (should succeed)",
            "POST",
            f"materials/requisitions/{self.req_id}/approve",
            200,
            user="pm"
        )
        
        if success_pass:
            status = resp.get("data", {}).get("status")
            if status == "approved":
                self.log("Status changed to 'approved'", "pass")
                return success_fail and True
            else:
                self.log(f"Unexpected status after approve: {status}", "fail")
        
        return False

    def test_issue_unapproved(self):
        """Test issuing an unapproved requisition (should fail)."""
        self.log("\n=== TEST: Issue Unapproved Requisition ===", "info")
        
        # Create a new requisition
        mat_id = list(self.material_ids.values())[0] if self.material_ids else None
        if not mat_id:
            return False
        
        success, resp = self.test(
            "Create requisition for issue test",
            "POST",
            "materials/requisitions",
            200,
            user="site",
            data={
                "project_id": self.project_id,
                "purpose": "Test unapproved issue",
                "items": [{"material_id": mat_id, "qty": 1}]
            }
        )
        
        if not success:
            return False
        
        unapproved_id = resp.get("data", {}).get("id")
        
        # Try to issue without approval (should fail with 400)
        success_fail, _ = self.test(
            "Issue unapproved requisition (should fail)",
            "POST",
            f"materials/requisitions/{unapproved_id}/issue",
            400,
            user="site",
            data={}  # Empty body required by RequisitionIssue model
        )
        
        return success_fail

    def test_issue_requisition(self):
        """Test POST /api/materials/requisitions/{id}/issue."""
        self.log("\n=== TEST: Issue Requisition ===", "info")
        
        if not self.req_id:
            self.log("No approved requisition ID available", "fail")
            return False
        
        success, resp = self.test(
            "Issue requisition",
            "POST",
            f"materials/requisitions/{self.req_id}/issue",
            200,
            user="site",
            data={}  # Empty body required by RequisitionIssue model
        )
        
        if success:
            status = resp.get("data", {}).get("status")
            over_budget = resp.get("over_budget_materials", 0)
            self.log(f"Issued requisition, status: {status}, over_budget_materials: {over_budget}", "pass")
            
            if status in ["issued", "partially_issued"]:
                self.log("Status is issued/partially_issued as expected", "pass")
                return True
            else:
                self.log(f"Unexpected status: {status}", "fail")
        
        return False

    def test_budget_endpoint(self):
        """Test GET /api/materials/project/{project_id}/budget."""
        self.log("\n=== TEST: Material Budget ===", "info")
        
        success, resp = self.test(
            "Get material budget",
            "GET",
            f"materials/project/{self.project_id}/budget",
            200,
            user="pm"
        )
        
        if success:
            data = resp.get("data", [])
            summary = resp.get("summary", {})
            self.log(f"Budget summary: materials={summary.get('materials')}, tracked={summary.get('tracked')}, over_budget={summary.get('over_budget')}", "info")
            
            # Check for BTA over budget
            bta_found = False
            for row in data:
                if row.get("code") == "BTA":
                    bta_found = True
                    is_over = row.get("over_budget", False)
                    consumed = row.get("consumed_qty", 0)
                    budget = row.get("budget_qty", 0)
                    self.log(f"BTA: consumed={consumed}, budget={budget}, over_budget={is_over}", "info")
                    
                    if is_over and consumed > budget:
                        self.log("BTA is over budget as expected (5000 > 4000)", "pass")
                        return True
                    else:
                        self.log("BTA should be over budget", "fail")
                        return False
            
            if not bta_found:
                self.log("BTA material not found in budget", "warn")
        
        return False

    def test_over_budget_alert(self):
        """Test over-budget alert creates task for PM."""
        self.log("\n=== TEST: Over-Budget Alert Task ===", "info")
        
        success, resp = self.test(
            "Get PM home tasks",
            "GET",
            "work/home",
            200,
            user="pm"
        )
        
        if success:
            tasks = resp.get("data", {}).get("tasks", [])
            self.log(f"Found {len(tasks)} tasks for PM", "info")
            
            # Look for over-budget task
            for task in tasks:
                # Handle both dict and string task formats
                if isinstance(task, str):
                    title = task
                else:
                    title = task.get("title", "")
                
                if "Bata Merah" in title and "melebihi RAB" in title:
                    self.log(f"Found over-budget alert task: {title}", "pass")
                    if isinstance(task, dict):
                        priority = task.get("priority")
                        if priority == "urgent":
                            self.log("Task priority is 'urgent' as expected", "pass")
                            return True
                        else:
                            self.log(f"Task priority is '{priority}', expected 'urgent'", "warn")
                            return True
                    else:
                        # String format, can't check priority but task exists
                        return True
            
            self.log("Over-budget alert task not found", "fail")
        
        return False

    def test_rbac_view(self):
        """Test RBAC: finance can view budget."""
        self.log("\n=== TEST: RBAC - View Budget ===", "info")
        
        success, _ = self.test(
            "Finance view budget (should succeed)",
            "GET",
            f"materials/project/{self.project_id}/budget",
            200,
            user="finance"
        )
        
        return success

    def test_regression_txn(self):
        """Test regression: material txn still works."""
        self.log("\n=== TEST: Regression - Material Transaction ===", "info")
        
        mat_id = list(self.material_ids.values())[0] if self.material_ids else None
        if not mat_id:
            return False
        
        success, resp = self.test(
            "Create material transaction (in)",
            "POST",
            "materials/txn",
            200,
            user="pm",
            data={
                "project_id": self.project_id,
                "material_id": mat_id,
                "type": "in",
                "qty": 100,
                "note": "Test GRN"
            }
        )
        
        if success:
            stock = resp.get("stock")
            self.log(f"Transaction created, new stock: {stock}", "pass")
            return True
        
        return False

    def test_regression_opname(self):
        """Test regression: opname still works."""
        self.log("\n=== TEST: Regression - Stock Opname ===", "info")
        
        mat_id = list(self.material_ids.values())[0] if self.material_ids else None
        if not mat_id:
            return False
        
        success, resp = self.test(
            "Stock opname",
            "POST",
            "materials/opname",
            200,
            user="site",
            data={
                "project_id": self.project_id,
                "material_id": mat_id,
                "physical_qty": 50,
                "note": "Test opname"
            }
        )
        
        if success:
            variance = resp.get("data", {}).get("variance")
            self.log(f"Opname completed, variance: {variance}", "pass")
            return True
        
        return False

    def run_all(self):
        """Run all tests."""
        self.log("=" * 60, "info")
        self.log("Phase 18 Backend Testing - Material Requisition + Budget", "info")
        self.log("=" * 60, "info")
        
        if not self.setup():
            self.log("Setup failed, aborting tests", "fail")
            return 1
        
        # Run all tests
        self.test_requisitions_list()
        self.test_create_requisition()
        self.test_rbac_create()
        self.test_approve_sod()
        self.test_issue_unapproved()
        self.test_issue_requisition()
        self.test_budget_endpoint()
        self.test_over_budget_alert()
        self.test_rbac_view()
        self.test_regression_txn()
        self.test_regression_opname()
        
        # Print summary
        self.log("=" * 60, "info")
        self.log(f"Tests passed: {self.tests_passed}/{self.tests_run}", "info")
        success_rate = (self.tests_passed / self.tests_run * 100) if self.tests_run > 0 else 0
        self.log(f"Success rate: {success_rate:.1f}%", "info")
        self.log("=" * 60, "info")
        
        return 0 if self.tests_passed == self.tests_run else 1


if __name__ == "__main__":
    tester = Phase18Tester()
    sys.exit(tester.run_all())
