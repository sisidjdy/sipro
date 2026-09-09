"""Phase 13 EPIC 3.4 — General Ledger / CoA Backend Test Suite

Tests:
1. AUTH: Staff login for all roles
2. CoA: GET /api/gl/accounts (19 seeded), POST new account, duplicate/invalid tests
3. JOURNALS: GET /api/gl/journals (4 seed), POST balanced/unbalanced, GET by ID
4. LEDGER: GET /api/gl/ledger?account_code=1-1200
5. TRIAL BALANCE: GET /api/gl/trial-balance (balanced:true)
6. STATEMENTS: GET /api/gl/income-statement, GET /api/gl/balance-sheet
7. RBAC: sales/pm/site get 403, finance/owner get 200
8. AUTO-POSTING: Approve pending AP bill, wait ~10s, verify new journal + TB still balanced
"""
import requests
import sys
import time
from datetime import datetime

BASE_URL = "https://sipro-verify.preview.emergentagent.com/api"
PASSWORD = "Sipro#2026"

class GLTester:
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
        token = r.json()["access_token"]
        self.tokens[email] = token
        return token

    def get(self, endpoint, email, expected_status=200):
        """GET request with auth"""
        token = self.login(email)
        r = requests.get(f"{BASE_URL}{endpoint}", headers={"Authorization": f"Bearer {token}"})
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

    # ============================= TEST CASES =============================

    def test_auth_all_roles(self):
        """Test 1: AUTH - Login all roles"""
        roles = [
            "finance@sipro.co.id", "owner@sipro.co.id", "superadmin@sipro.co.id",
            "pm@sipro.co.id", "sales@sipro.co.id", "site@sipro.co.id"
        ]
        for email in roles:
            token = self.login(email)
            assert len(token) > 20, f"Invalid token for {email}"
        self.log(f"All {len(roles)} roles logged in successfully")

    def test_coa_list_19_accounts(self):
        """Test 2: CoA - GET /api/gl/accounts returns 19 seeded accounts"""
        r = self.get("/gl/accounts", "finance@sipro.co.id")
        data = r.json()["data"]
        assert len(data) == 19, f"Expected 19 accounts, got {len(data)}"
        # Check a few key accounts
        codes = [a["code"] for a in data]
        assert "1-1200" in codes, "Bank account missing"
        assert "2-1400" in codes, "Uang Muka Penjualan missing"
        assert "4-1100" in codes, "Pendapatan missing"
        # Check balances are present
        assert all("balance" in a for a in data), "Some accounts missing balance"
        self.log(f"Found 19 accounts with balances")

    def test_coa_create_new_account(self):
        """Test 3: CoA - POST /api/gl/accounts creates new account"""
        new_code = f"9-TEST-{int(time.time()) % 10000}"
        r = self.post("/gl/accounts", "finance@sipro.co.id", {
            "code": new_code,
            "name": "Test Account",
            "type": "expense",
            "parent_code": None
        }, expected_status=200)
        data = r.json()["data"]
        assert data["code"] == new_code
        assert data["name"] == "Test Account"
        self.log(f"Created new account: {new_code}")

    def test_coa_duplicate_code_400(self):
        """Test 4: CoA - POST duplicate code returns 400"""
        r = self.post("/gl/accounts", "finance@sipro.co.id", {
            "code": "1-1200",  # Bank (already exists)
            "name": "Duplicate Bank",
            "type": "asset",
            "parent_code": None
        }, expected_status=400)
        assert "sudah dipakai" in r.json()["detail"].lower() or "duplicate" in r.json()["detail"].lower()
        self.log("Duplicate code correctly rejected with 400")

    def test_coa_invalid_type_400(self):
        """Test 5: CoA - POST invalid type returns 400"""
        r = self.post("/gl/accounts", "finance@sipro.co.id", {
            "code": "9-INVALID",
            "name": "Invalid Type",
            "type": "invalid_type",
            "parent_code": None
        }, expected_status=400)
        assert "tidak valid" in r.json()["detail"].lower() or "invalid" in r.json()["detail"].lower()
        self.log("Invalid type correctly rejected with 400")

    def test_journals_list_seed(self):
        """Test 6: JOURNALS - GET /api/gl/journals lists seed entries"""
        r = self.get("/gl/journals", "finance@sipro.co.id")
        data = r.json()["data"]
        assert len(data) >= 4, f"Expected at least 4 seed journals, got {len(data)}"
        # Check for opening balance journal
        opening = [j for j in data if "opening" in j.get("source_type", "").lower() or "saldo awal" in j.get("memo", "").lower()]
        assert len(opening) > 0, "Opening balance journal not found"
        # Check for auto-posted journals
        auto = [j for j in data if j.get("auto") == True]
        assert len(auto) >= 3, f"Expected at least 3 auto-posted journals, got {len(auto)}"
        self.log(f"Found {len(data)} journals ({len(auto)} auto-posted)")

    def test_journals_post_balanced(self):
        """Test 7: JOURNALS - POST balanced entry succeeds"""
        r = self.post("/gl/journals", "finance@sipro.co.id", {
            "memo": f"Test balanced journal {int(time.time())}",
            "date": None,
            "lines": [
                {"account_code": "6-1300", "debit": 1000000, "credit": 0},
                {"account_code": "1-1200", "debit": 0, "credit": 1000000}
            ]
        }, expected_status=200)
        data = r.json()["data"]
        assert data["total_debit"] == 1000000
        assert data["total_credit"] == 1000000
        assert data["auto"] == False
        self.log(f"Balanced journal posted: {data['entry_no']}")

    def test_journals_post_unbalanced_400(self):
        """Test 8: JOURNALS - POST unbalanced entry returns 400"""
        r = self.post("/gl/journals", "finance@sipro.co.id", {
            "memo": "Test unbalanced journal",
            "date": None,
            "lines": [
                {"account_code": "6-1300", "debit": 1000000, "credit": 0},
                {"account_code": "1-1200", "debit": 0, "credit": 500000}  # Unbalanced!
            ]
        }, expected_status=400)
        detail = r.json()["detail"].lower()
        assert "tidak seimbang" in detail or "unbalanced" in detail or "balance" in detail
        self.log("Unbalanced journal correctly rejected with 400")

    def test_journals_get_by_id(self):
        """Test 9: JOURNALS - GET /api/gl/journals/{id} returns detail"""
        # First get a journal ID
        r = self.get("/gl/journals?limit=1", "finance@sipro.co.id")
        journals = r.json()["data"]
        assert len(journals) > 0, "No journals found"
        jid = journals[0]["id"]
        # Get detail
        r = self.get(f"/gl/journals/{jid}", "finance@sipro.co.id")
        data = r.json()["data"]
        assert data["id"] == jid
        assert "lines" in data
        assert len(data["lines"]) >= 2
        assert "total_debit" in data
        assert "total_credit" in data
        self.log(f"Journal detail retrieved: {data['entry_no']}")

    def test_ledger_account_1_1200(self):
        """Test 10: LEDGER - GET /api/gl/ledger?account_code=1-1200"""
        r = self.get("/gl/ledger?account_code=1-1200", "finance@sipro.co.id")
        data = r.json()["data"]
        assert data["account"] is not None
        assert data["account"]["code"] == "1-1200"
        assert data["account"]["name"] == "Bank"
        assert "lines" in data
        assert len(data["lines"]) > 0, "Bank ledger should have transactions"
        # Check running balance
        for line in data["lines"]:
            assert "balance" in line, "Ledger line missing running balance"
        assert "balance" in data, "Ending balance missing"
        self.log(f"Bank ledger: {len(data['lines'])} transactions, ending balance: Rp {data['balance']:,}")

    def test_trial_balance_balanced(self):
        """Test 11: TRIAL BALANCE - GET /api/gl/trial-balance is balanced"""
        r = self.get("/gl/trial-balance", "finance@sipro.co.id")
        data = r.json()["data"]
        assert data["balanced"] == True, f"Trial balance NOT balanced: Dr={data['total_debit']:,} Cr={data['total_credit']:,}"
        assert data["total_debit"] == data["total_credit"]
        assert data["total_debit"] > 0, "Trial balance totals are zero"
        assert len(data["rows"]) > 0, "No accounts in trial balance"
        self.log(f"Trial balance BALANCED: Dr=Cr=Rp {data['total_debit']:,} ({len(data['rows'])} accounts)")

    def test_income_statement(self):
        """Test 12: STATEMENTS - GET /api/gl/income-statement"""
        r = self.get("/gl/income-statement", "finance@sipro.co.id")
        data = r.json()["data"]
        assert "revenue" in data
        assert "expenses" in data
        assert "total_revenue" in data
        assert "total_expense" in data
        assert "net_income" in data
        net = data["net_income"]
        self.log(f"Income statement: Revenue={data['total_revenue']:,}, Expense={data['total_expense']:,}, Net={net:,}")

    def test_balance_sheet_balanced(self):
        """Test 13: STATEMENTS - GET /api/gl/balance-sheet is balanced"""
        r = self.get("/gl/balance-sheet", "finance@sipro.co.id")
        data = r.json()["data"]
        assert data["balanced"] == True, f"Balance sheet NOT balanced: Assets={data['total_assets']:,} vs Liab+Equity+NI={data['total_liab_equity']:,}"
        assert data["total_assets"] == data["total_liab_equity"]
        assert "assets" in data
        assert "liabilities" in data
        assert "equity" in data
        assert "net_income" in data
        self.log(f"Balance sheet BALANCED: Assets=Liab+Equity+NI=Rp {data['total_assets']:,}")

    def test_rbac_sales_denied(self):
        """Test 14: RBAC - sales@sipro.co.id gets 403 on GL endpoints"""
        r = self.get("/gl/accounts", "sales@sipro.co.id", expected_status=403)
        assert "akses ditolak" in r.json()["detail"].lower() or "forbidden" in r.json()["detail"].lower()
        r = self.get("/gl/trial-balance", "sales@sipro.co.id", expected_status=403)
        self.log("Sales correctly denied access (403)")

    def test_rbac_pm_denied(self):
        """Test 15: RBAC - pm@sipro.co.id gets 403 on GL endpoints"""
        r = self.get("/gl/accounts", "pm@sipro.co.id", expected_status=403)
        r = self.get("/gl/trial-balance", "pm@sipro.co.id", expected_status=403)
        self.log("PM correctly denied access (403)")

    def test_rbac_site_denied(self):
        """Test 16: RBAC - site@sipro.co.id gets 403 on GL endpoints"""
        r = self.get("/gl/accounts", "site@sipro.co.id", expected_status=403)
        r = self.get("/gl/trial-balance", "site@sipro.co.id", expected_status=403)
        self.log("Site engineer correctly denied access (403)")

    def test_rbac_owner_allowed(self):
        """Test 17: RBAC - owner@sipro.co.id gets 200 on GL endpoints"""
        r = self.get("/gl/accounts", "owner@sipro.co.id", expected_status=200)
        r = self.get("/gl/trial-balance", "owner@sipro.co.id", expected_status=200)
        self.log("Owner correctly allowed access (200)")

    def test_auto_posting_integration(self):
        """Test 18: AUTO-POSTING - Approve pending AP bill, verify new journal + TB still balanced"""
        # Get pending AP bills
        r = self.get("/finance/ap/bills?status=pending", "finance@sipro.co.id")
        bills = r.json()["data"]
        if len(bills) == 0:
            self.log("⚠️  No pending AP bills found, skipping auto-posting test", "INFO")
            return
        
        # Get initial journal count and TB
        r1 = self.get("/gl/journals", "finance@sipro.co.id")
        initial_count = r1.json()["total"]
        r2 = self.get("/gl/trial-balance", "finance@sipro.co.id")
        initial_tb = r2.json()["data"]
        assert initial_tb["balanced"] == True, "TB not balanced before test"
        
        # Approve first pending bill
        bill_id = bills[0]["id"]
        self.log(f"Approving AP bill {bill_id} (vendor: {bills[0].get('vendor', 'N/A')})...", "INFO")
        r = self.post(f"/finance/ap/bills/{bill_id}/approve", "finance@sipro.co.id", {}, expected_status=200)
        
        # Wait for scheduler to dispatch event (~10s)
        self.log("Waiting 12s for auto-posting scheduler...", "INFO")
        time.sleep(12)
        
        # Check new journal created
        r3 = self.get("/gl/journals", "finance@sipro.co.id")
        new_count = r3.json()["total"]
        assert new_count > initial_count, f"No new journal created (before={initial_count}, after={new_count})"
        self.log(f"New journal created: count increased from {initial_count} to {new_count}")
        
        # Check TB still balanced
        r4 = self.get("/gl/trial-balance", "finance@sipro.co.id")
        final_tb = r4.json()["data"]
        assert final_tb["balanced"] == True, f"TB NOT balanced after auto-posting: Dr={final_tb['total_debit']:,} Cr={final_tb['total_credit']:,}"
        self.log(f"Trial balance still BALANCED after auto-posting: Rp {final_tb['total_debit']:,}")

    def run_all(self):
        """Run all tests"""
        print("\n" + "="*70)
        print("Phase 13 EPIC 3.4 — General Ledger Backend Test Suite")
        print("="*70 + "\n")
        
        # AUTH
        self.test("AUTH: All roles login", self.test_auth_all_roles)
        
        # CoA
        self.test("CoA: List 19 seeded accounts", self.test_coa_list_19_accounts)
        self.test("CoA: Create new account", self.test_coa_create_new_account)
        self.test("CoA: Duplicate code returns 400", self.test_coa_duplicate_code_400)
        self.test("CoA: Invalid type returns 400", self.test_coa_invalid_type_400)
        
        # Journals
        self.test("Journals: List seed entries", self.test_journals_list_seed)
        self.test("Journals: Post balanced entry", self.test_journals_post_balanced)
        self.test("Journals: Post unbalanced returns 400", self.test_journals_post_unbalanced_400)
        self.test("Journals: Get by ID", self.test_journals_get_by_id)
        
        # Ledger
        self.test("Ledger: Get Bank account ledger", self.test_ledger_account_1_1200)
        
        # Trial Balance
        self.test("Trial Balance: Balanced", self.test_trial_balance_balanced)
        
        # Statements
        self.test("Income Statement: Returns data", self.test_income_statement)
        self.test("Balance Sheet: Balanced", self.test_balance_sheet_balanced)
        
        # RBAC
        self.test("RBAC: Sales denied (403)", self.test_rbac_sales_denied)
        self.test("RBAC: PM denied (403)", self.test_rbac_pm_denied)
        self.test("RBAC: Site denied (403)", self.test_rbac_site_denied)
        self.test("RBAC: Owner allowed (200)", self.test_rbac_owner_allowed)
        
        # Auto-posting integration
        self.test("Auto-posting: Approve AP bill → new journal + TB balanced", self.test_auto_posting_integration)
        
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
    tester = GLTester()
    sys.exit(tester.run_all())
