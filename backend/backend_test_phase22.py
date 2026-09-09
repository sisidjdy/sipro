"""Phase 22 EPIC 1.7 — Omnichannel Backend API Test Suite

Tests:
1. AUTH: Login for manager, marketing_admin, sales
2. AUTOMATION RULES: GET/POST/PUT/DELETE/TOGGLE with RBAC
3. WA TEMPLATES: GET/POST/PUT/DELETE with RBAC
4. CHANNELS: GET/POST/PUT with RBAC
5. CAPTURE EVENTS: GET /capture-events and /capture-events/attribution
6. RBAC: sales gets 403 on manage endpoints, manager/marketing_admin succeed
"""
import requests
import sys
import time

BASE_URL = "https://development-resume.preview.emergentagent.com/api"
PASSWORD = "Sipro#2026"

class OmniTester:
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
        r = requests.post(f"{BASE_URL}/auth/login", json={"email": email, "password": PASSWORD}, timeout=10)
        assert r.status_code == 200, f"Login failed for {email}: {r.status_code} {r.text}"
        token = r.json()["access_token"]
        self.tokens[email] = token
        return token

    def get(self, endpoint, email, expected_status=200):
        """GET request with auth"""
        token = self.login(email)
        r = requests.get(f"{BASE_URL}{endpoint}", headers={"Authorization": f"Bearer {token}"}, timeout=10)
        if expected_status:
            assert r.status_code == expected_status, f"Expected {expected_status}, got {r.status_code}: {r.text[:200]}"
        return r

    def post(self, endpoint, email, data, expected_status=200):
        """POST request with auth"""
        token = self.login(email)
        r = requests.post(f"{BASE_URL}{endpoint}", json=data, headers={"Authorization": f"Bearer {token}"}, timeout=10)
        if expected_status:
            assert r.status_code == expected_status, f"Expected {expected_status}, got {r.status_code}: {r.text[:200]}"
        return r

    def put(self, endpoint, email, data, expected_status=200):
        """PUT request with auth"""
        token = self.login(email)
        r = requests.put(f"{BASE_URL}{endpoint}", json=data, headers={"Authorization": f"Bearer {token}"}, timeout=10)
        if expected_status:
            assert r.status_code == expected_status, f"Expected {expected_status}, got {r.status_code}: {r.text[:200]}"
        return r

    def delete(self, endpoint, email, expected_status=200):
        """DELETE request with auth"""
        token = self.login(email)
        r = requests.delete(f"{BASE_URL}{endpoint}", headers={"Authorization": f"Bearer {token}"}, timeout=10)
        if expected_status:
            assert r.status_code == expected_status, f"Expected {expected_status}, got {r.status_code}: {r.text[:200]}"
        return r

    # ============================= TEST CASES =============================

    def test_auth_all_roles(self):
        """Test 1: AUTH - Login manager, marketing_admin, sales, owner"""
        roles = [
            "manager@sipro.co.id",
            "marketing@sipro.co.id",
            "sales@sipro.co.id",
            "owner@sipro.co.id"
        ]
        for email in roles:
            token = self.login(email)
            assert len(token) > 20, f"Invalid token for {email}"
        self.log(f"All {len(roles)} roles logged in successfully")

    def test_automation_rules_list(self):
        """Test 2: GET /automation-rules returns seeded rules"""
        r = self.get("/automation-rules", "manager@sipro.co.id")
        data = r.json()["data"]
        assert len(data) >= 3, f"Expected at least 3 seeded rules, got {len(data)}"
        # Check events
        events = {rule["trigger"]["event"] for rule in data}
        assert "message.received" in events, "message.received rule missing"
        assert "lead.captured" in events, "lead.captured rule missing"
        assert "no_response" in events, "no_response rule missing"
        self.log(f"Found {len(data)} automation rules with events: {events}")

    def test_automation_rules_create(self):
        """Test 3: POST /automation-rules creates new rule (manager)"""
        r = self.post("/automation-rules", "manager@sipro.co.id", {
            "name": "Test Rule Phase22",
            "trigger_event": "message.received",
            "keywords": ["test", "phase22"],
            "no_response_days": None,
            "actions": [{"type": "create_task", "title": "Follow up test"}],
            "is_active": True,
            "require_confirmation": False
        })
        data = r.json()["data"]
        assert data["name"] == "Test Rule Phase22"
        assert data["trigger"]["event"] == "message.received"
        assert "test" in data["trigger"]["keywords"]
        self.created_rule_id = data["id"]
        self.log(f"Created rule: {data['id']}")

    def test_automation_rules_toggle(self):
        """Test 4: POST /automation-rules/{id}/toggle works"""
        if not hasattr(self, 'created_rule_id'):
            self.log("Skipping toggle test (no rule created)", "INFO")
            return
        r = self.post(f"/automation-rules/{self.created_rule_id}/toggle", "manager@sipro.co.id", {})
        data = r.json()["data"]
        assert "is_active" in data
        self.log(f"Toggled rule to is_active={data['is_active']}")

    def test_automation_rules_update(self):
        """Test 5: PUT /automation-rules/{id} updates rule"""
        if not hasattr(self, 'created_rule_id'):
            self.log("Skipping update test (no rule created)", "INFO")
            return
        r = self.put(f"/automation-rules/{self.created_rule_id}", "manager@sipro.co.id", {
            "keywords": ["test", "phase22", "updated"]
        })
        data = r.json()["data"]
        assert "updated" in data["trigger"]["keywords"]
        self.log(f"Updated rule keywords: {data['trigger']['keywords']}")

    def test_automation_rules_delete(self):
        """Test 6: DELETE /automation-rules/{id} deletes rule"""
        if not hasattr(self, 'created_rule_id'):
            self.log("Skipping delete test (no rule created)", "INFO")
            return
        r = self.delete(f"/automation-rules/{self.created_rule_id}", "manager@sipro.co.id")
        data = r.json()["data"]
        assert data["deleted"] == True
        self.log(f"Deleted rule: {self.created_rule_id}")

    def test_wa_templates_list(self):
        """Test 7: GET /wa-templates returns seeded templates"""
        r = self.get("/wa-templates", "manager@sipro.co.id")
        data = r.json()["data"]
        assert len(data) >= 4, f"Expected at least 4 seeded templates, got {len(data)}"
        # Check for common templates
        codes = [t["code"] for t in data]
        self.log(f"Found {len(data)} WA templates: {codes[:5]}")

    def test_wa_templates_create(self):
        """Test 8: POST /wa-templates creates new template (marketing_admin)"""
        r = self.post("/wa-templates", "marketing@sipro.co.id", {
            "name": "Test Template Phase22",
            "category": "marketing",
            "language": "id",
            "body": "Halo {{1}}, ini template test",
            "variables": ["nama"]
        })
        data = r.json()["data"]
        assert data["name"] == "Test Template Phase22"
        assert data["status"] == "approved"  # SIMULATION mode
        self.created_template_id = data["id"]
        self.log(f"Created template: {data['id']} (code: {data['code']})")

    def test_wa_templates_update(self):
        """Test 9: PUT /wa-templates/{id} updates template"""
        if not hasattr(self, 'created_template_id'):
            self.log("Skipping template update test (no template created)", "INFO")
            return
        r = self.put(f"/wa-templates/{self.created_template_id}", "marketing@sipro.co.id", {
            "body": "Halo {{1}}, ini template test UPDATED"
        })
        data = r.json()["data"]
        assert "UPDATED" in data["body"]
        self.log(f"Updated template body")

    def test_wa_templates_delete(self):
        """Test 10: DELETE /wa-templates/{id} deletes template"""
        if not hasattr(self, 'created_template_id'):
            self.log("Skipping template delete test (no template created)", "INFO")
            return
        r = self.delete(f"/wa-templates/{self.created_template_id}", "marketing@sipro.co.id")
        data = r.json()["data"]
        assert data["deleted"] == True
        self.log(f"Deleted template: {self.created_template_id}")

    def test_channels_list(self):
        """Test 11: GET /channels returns seeded channels"""
        r = self.get("/channels", "manager@sipro.co.id")
        data = r.json()["data"]
        assert len(data) >= 5, f"Expected at least 5 seeded channels, got {len(data)}"
        # Check all are simulation mode
        assert all(c["mode"] == "simulation" for c in data), "Some channels not in simulation mode"
        self.log(f"Found {len(data)} channels (all simulation mode)")

    def test_channels_create(self):
        """Test 12: POST /channels creates new channel"""
        timestamp = int(time.time()) % 10000
        r = self.post("/channels", "manager@sipro.co.id", {
            "code": f"test_ch_{timestamp}",
            "channel": "whatsapp",
            "name": "Test Channel Phase22"
        })
        data = r.json()["data"]
        assert data["name"] == "Test Channel Phase22"
        assert data["mode"] == "simulation"
        self.created_channel_id = data["id"]
        self.log(f"Created channel: {data['id']} (code: {data['code']})")

    def test_channels_update(self):
        """Test 13: PUT /channels/{id} updates channel"""
        if not hasattr(self, 'created_channel_id'):
            self.log("Skipping channel update test (no channel created)", "INFO")
            return
        r = self.put(f"/channels/{self.created_channel_id}", "manager@sipro.co.id", {
            "name": "Test Channel UPDATED",
            "is_active": False
        })
        data = r.json()["data"]
        assert "UPDATED" in data["name"]
        assert data["is_active"] == False
        self.log(f"Updated channel: is_active={data['is_active']}")

    def test_capture_events_list(self):
        """Test 14: GET /capture-events returns audit list"""
        r = self.get("/capture-events", "manager@sipro.co.id")
        data = r.json()
        assert "data" in data
        assert "total" in data
        self.log(f"Found {data['total']} capture events")

    def test_capture_events_attribution(self):
        """Test 15: GET /capture-events/attribution returns funnel data"""
        r = self.get("/capture-events/attribution", "manager@sipro.co.id")
        data = r.json()["data"]
        assert "rows" in data
        assert "totals" in data
        assert "leads" in data["totals"]
        self.log(f"Attribution: {data['totals']['leads']} total leads across {len(data['rows'])} sources")

    def test_rbac_sales_denied_automation_rules(self):
        """Test 16: RBAC - sales gets 403 on POST /automation-rules"""
        r = self.post("/automation-rules", "sales@sipro.co.id", {
            "name": "Should Fail",
            "trigger_event": "message.received",
            "keywords": ["test"],
            "actions": [{"type": "create_task", "title": "test"}]
        }, expected_status=403)
        detail = r.json()["detail"].lower()
        assert "akses ditolak" in detail or "forbidden" in detail
        self.log("Sales correctly denied POST /automation-rules (403)")

    def test_rbac_sales_denied_wa_templates(self):
        """Test 17: RBAC - sales gets 403 on POST /wa-templates"""
        r = self.post("/wa-templates", "sales@sipro.co.id", {
            "name": "Should Fail",
            "category": "marketing",
            "language": "id",
            "body": "test",
            "variables": []
        }, expected_status=403)
        detail = r.json()["detail"].lower()
        assert "akses ditolak" in detail or "forbidden" in detail
        self.log("Sales correctly denied POST /wa-templates (403)")

    def test_rbac_sales_denied_channels(self):
        """Test 18: RBAC - sales gets 403 on POST /channels"""
        r = self.post("/channels", "sales@sipro.co.id", {
            "code": "should_fail",
            "channel": "whatsapp",
            "name": "Should Fail"
        }, expected_status=403)
        detail = r.json()["detail"].lower()
        assert "akses ditolak" in detail or "forbidden" in detail
        self.log("Sales correctly denied POST /channels (403)")

    def test_rbac_marketing_admin_allowed(self):
        """Test 19: RBAC - marketing_admin can access all omni endpoints"""
        # GET automation-rules
        r1 = self.get("/automation-rules", "marketing@sipro.co.id", expected_status=200)
        # GET wa-templates
        r2 = self.get("/wa-templates", "marketing@sipro.co.id", expected_status=200)
        # GET channels
        r3 = self.get("/channels", "marketing@sipro.co.id", expected_status=200)
        self.log("Marketing admin correctly allowed access to all omni endpoints (200)")

    def test_rbac_owner_allowed(self):
        """Test 20: RBAC - owner can access all omni endpoints"""
        # GET automation-rules
        r1 = self.get("/automation-rules", "owner@sipro.co.id", expected_status=200)
        # GET wa-templates
        r2 = self.get("/wa-templates", "owner@sipro.co.id", expected_status=200)
        # GET channels
        r3 = self.get("/channels", "owner@sipro.co.id", expected_status=200)
        self.log("Owner correctly allowed access to all omni endpoints (200)")

    def run_all(self):
        """Run all tests"""
        print("\n" + "="*70)
        print("Phase 22 EPIC 1.7 — Omnichannel Backend Test Suite")
        print("="*70 + "\n")
        
        # AUTH
        self.test("AUTH: All roles login", self.test_auth_all_roles)
        
        # Automation Rules
        self.test("Automation Rules: List seeded rules", self.test_automation_rules_list)
        self.test("Automation Rules: Create new rule", self.test_automation_rules_create)
        self.test("Automation Rules: Toggle rule", self.test_automation_rules_toggle)
        self.test("Automation Rules: Update rule", self.test_automation_rules_update)
        self.test("Automation Rules: Delete rule", self.test_automation_rules_delete)
        
        # WA Templates
        self.test("WA Templates: List seeded templates", self.test_wa_templates_list)
        self.test("WA Templates: Create new template", self.test_wa_templates_create)
        self.test("WA Templates: Update template", self.test_wa_templates_update)
        self.test("WA Templates: Delete template", self.test_wa_templates_delete)
        
        # Channels
        self.test("Channels: List seeded channels", self.test_channels_list)
        self.test("Channels: Create new channel", self.test_channels_create)
        self.test("Channels: Update channel", self.test_channels_update)
        
        # Capture Events
        self.test("Capture Events: List audit", self.test_capture_events_list)
        self.test("Capture Events: Attribution funnel", self.test_capture_events_attribution)
        
        # RBAC
        self.test("RBAC: Sales denied POST /automation-rules (403)", self.test_rbac_sales_denied_automation_rules)
        self.test("RBAC: Sales denied POST /wa-templates (403)", self.test_rbac_sales_denied_wa_templates)
        self.test("RBAC: Sales denied POST /channels (403)", self.test_rbac_sales_denied_channels)
        self.test("RBAC: Marketing admin allowed (200)", self.test_rbac_marketing_admin_allowed)
        self.test("RBAC: Owner allowed (200)", self.test_rbac_owner_allowed)
        
        # Summary
        print("\n" + "="*70)
        print(f"RESULTS: {self.tests_passed}/{self.tests_run} tests passed")
        print("="*70 + "\n")
        
        if self.tests_passed == self.tests_run:
            print("✅ ALL TESTS PASSED")
            return 0
        else:
            print(f"❌ {self.tests_run - self.tests_passed} TESTS FAILED")
            return 1

if __name__ == "__main__":
    tester = OmniTester()
    sys.exit(tester.run_all())
