"""Phase 20 EPIC 1.4 — Legal Milestone Tracker (PPJB → AJB) Backend Test Suite

Tests:
1. AUTH: Login sales_manager, owner, sales
2. DEALS: GET /api/deals -> verify 1 booked deal (unit A-01)
3. LEGAL STATUS: GET /api/deals/{deal_id}/legal -> verify legal_stage null, payment, financing
4. GUARD: POST /api/deals/{deal_id}/ajb BEFORE ppjb -> 400 (AJB requires PPJB)
5. PPJB: POST /api/deals/{deal_id}/ppjb -> verify legal_stage='ppjb', ppjb.number, ppjb.dp_pct
6. GUARD: POST /api/deals/{deal_id}/ppjb again -> 400 (already signed)
7. AJB: POST /api/deals/{deal_id}/ajb -> verify status='completed', legal_stage='ajb', ajb.number, sold_at
8. SOLD UNIT: GET /api/units?status=sold -> verify A-01 present
9. LEGAL RECORDS: GET /api/deals/{deal_id}/legal -> verify ppjb+ajb records
10. REGRESSION: POST /api/deals/reserve, POST /api/deals/{id}/book, /api/work/home
"""
import requests
import sys
import time
from datetime import datetime

BASE_URL = "https://sleepy-sammet-6.preview.emergentagent.com/api"
PASSWORD = "Sipro#2026"

class Phase20Tester:
    def __init__(self):
        self.tests_run = 0
        self.tests_passed = 0
        self.tokens = {}
        self.results = []
        self.deal_id = None
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
        roles = ["manager@sipro.co.id", "owner@sipro.co.id", "sales@sipro.co.id"]
        for email in roles:
            token = self.login(email)
            assert len(token) > 20, f"Invalid token for {email}"
        self.log(f"All {len(roles)} roles logged in successfully")

    def test_get_deals_one_booked(self):
        """Test 2: GET /api/deals -> verify 1 booked deal (unit A-01)"""
        r = self.get("/deals", "manager@sipro.co.id")
        data = r.json()["data"]
        assert len(data) >= 1, f"Expected at least 1 deal, got {len(data)}"
        
        # Find the booked deal with unit A-01
        booked_deals = [d for d in data if d.get("status") == "booked"]
        assert len(booked_deals) >= 1, f"Expected at least 1 booked deal, got {len(booked_deals)}"
        
        deal = booked_deals[0]
        self.deal_id = deal["id"]
        self.unit_id = deal.get("unit_id")
        
        assert deal.get("unit_code") == "A-01", f"Expected unit A-01, got {deal.get('unit_code')}"
        assert deal.get("status") == "booked", f"Expected status 'booked', got {deal.get('status')}"
        
        self.log(f"Found booked deal {self.deal_id} for unit A-01")

    def test_legal_status_initial(self):
        """Test 3: GET /api/deals/{deal_id}/legal -> verify legal_stage null, payment, financing"""
        assert self.deal_id, "deal_id not set"
        r = self.get(f"/deals/{self.deal_id}/legal", "manager@sipro.co.id")
        data = r.json()["data"]
        
        assert data.get("legal_stage") is None, f"Expected legal_stage null, got {data.get('legal_stage')}"
        assert data.get("status") == "booked", f"Expected status 'booked', got {data.get('status')}"
        
        # Verify payment object
        payment = data.get("payment")
        assert payment is not None, "payment object missing"
        assert "price" in payment, "payment.price missing"
        assert "paid" in payment, "payment.paid missing"
        assert "outstanding" in payment, "payment.outstanding missing"
        assert "paid_pct" in payment, "payment.paid_pct missing"
        
        self.log(f"Payment: {payment['paid']}/{payment['price']} ({payment['paid_pct']}%)")
        
        # Verify financing object (may be null)
        financing = data.get("financing")
        if financing:
            assert "bank" in financing, "financing.bank missing"
            assert "status" in financing, "financing.status missing"
            assert "plafon" in financing, "financing.plafon missing"
            self.log(f"Financing: {financing['bank']} - {financing['plafon']}")
        else:
            self.log("No financing (KPR) for this deal")

    def test_ajb_before_ppjb_guard(self):
        """Test 4: POST /api/deals/{deal_id}/ajb BEFORE ppjb -> 400 (AJB requires PPJB)"""
        assert self.deal_id, "deal_id not set"
        r = self.post(f"/deals/{self.deal_id}/ajb", "manager@sipro.co.id", 
                      {"notary": "Notaris Test"}, expected_status=400)
        
        error = r.json().get("detail", "")
        assert "AJB memerlukan PPJB" in error or "PPJB" in error, \
            f"Expected error about PPJB requirement, got: {error}"
        self.log("Guard working: AJB blocked before PPJB")

    def test_ppjb_sign(self):
        """Test 5: POST /api/deals/{deal_id}/ppjb -> verify legal_stage='ppjb', ppjb.number, ppjb.dp_pct"""
        assert self.deal_id, "deal_id not set"
        r = self.post(f"/deals/{self.deal_id}/ppjb", "manager@sipro.co.id", 
                      {"note": "Test PPJB signing"})
        
        data = r.json()["data"]
        assert data.get("legal_stage") == "ppjb", f"Expected legal_stage 'ppjb', got {data.get('legal_stage')}"
        
        ppjb = data.get("ppjb")
        assert ppjb is not None, "ppjb object missing"
        assert "number" in ppjb, "ppjb.number missing"
        assert "PPJB" in ppjb["number"], f"Expected PPJB number format, got {ppjb['number']}"
        assert "dp_pct" in ppjb, "ppjb.dp_pct missing"
        assert "signed_date" in ppjb, "ppjb.signed_date missing"
        
        self.log(f"PPJB signed: {ppjb['number']} (DP: {ppjb['dp_pct']}%)")

    def test_ppjb_double_sign_guard(self):
        """Test 6: POST /api/deals/{deal_id}/ppjb again -> 400 (already signed)"""
        assert self.deal_id, "deal_id not set"
        r = self.post(f"/deals/{self.deal_id}/ppjb", "manager@sipro.co.id", 
                      {"note": "Try to sign again"}, expected_status=400)
        
        error = r.json().get("detail", "")
        assert "sudah ditandatangani" in error or "already" in error.lower(), \
            f"Expected error about already signed, got: {error}"
        self.log("Guard working: Double PPJB signing blocked")

    def test_ajb_sign(self):
        """Test 7: POST /api/deals/{deal_id}/ajb -> verify status='completed', legal_stage='ajb', ajb.number, sold_at"""
        assert self.deal_id, "deal_id not set"
        r = self.post(f"/deals/{self.deal_id}/ajb", "manager@sipro.co.id", 
                      {"notary": "Notaris Budi, S.H.", "note": "Test AJB signing"})
        
        data = r.json()["data"]
        assert data.get("status") == "completed", f"Expected status 'completed', got {data.get('status')}"
        assert data.get("legal_stage") == "ajb", f"Expected legal_stage 'ajb', got {data.get('legal_stage')}"
        assert data.get("sold_at") is not None, "sold_at missing"
        
        ajb = data.get("ajb")
        assert ajb is not None, "ajb object missing"
        assert "number" in ajb, "ajb.number missing"
        assert "AJB" in ajb["number"], f"Expected AJB number format, got {ajb['number']}"
        assert "notary" in ajb, "ajb.notary missing"
        assert ajb["notary"] == "Notaris Budi, S.H.", f"Expected notary 'Notaris Budi, S.H.', got {ajb['notary']}"
        assert "signed_date" in ajb, "ajb.signed_date missing"
        
        self.log(f"AJB signed: {ajb['number']} (Notary: {ajb['notary']})")

    def test_unit_sold_status(self):
        """Test 8: GET /api/units?status=sold -> verify A-01 present"""
        r = self.get("/units?status=sold", "manager@sipro.co.id")
        data = r.json()["data"]
        
        assert len(data) >= 1, f"Expected at least 1 sold unit, got {len(data)}"
        
        unit_codes = [u.get("code") for u in data]
        assert "A-01" in unit_codes, f"Expected unit A-01 in sold units, got {unit_codes}"
        
        a01 = next(u for u in data if u.get("code") == "A-01")
        assert a01.get("status") == "sold", f"Expected unit A-01 status 'sold', got {a01.get('status')}"
        
        self.log(f"Unit A-01 marked as SOLD")

    def test_legal_records_complete(self):
        """Test 9: GET /api/deals/{deal_id}/legal -> verify ppjb+ajb records"""
        assert self.deal_id, "deal_id not set"
        r = self.get(f"/deals/{self.deal_id}/legal", "manager@sipro.co.id")
        data = r.json()["data"]
        
        assert data.get("legal_stage") == "ajb", f"Expected legal_stage 'ajb', got {data.get('legal_stage')}"
        assert data.get("status") == "completed", f"Expected status 'completed', got {data.get('status')}"
        
        ppjb = data.get("ppjb")
        assert ppjb is not None, "ppjb record missing"
        assert "number" in ppjb, "ppjb.number missing"
        
        ajb = data.get("ajb")
        assert ajb is not None, "ajb record missing"
        assert "number" in ajb, "ajb.number missing"
        
        self.log(f"Legal records complete: PPJB {ppjb['number']}, AJB {ajb['number']}")

    def test_regression_work_home(self):
        """Test 10a: Regression - GET /api/work/home"""
        r = self.get("/work/home", "manager@sipro.co.id")
        data = r.json()["data"]
        
        assert "tasks" in data, "tasks missing from work/home"
        assert "activities" in data, "activities missing from work/home"
        
        self.log("Regression: /api/work/home working")

    def test_regression_reserve_book(self):
        """Test 10b: Regression - POST /api/deals/reserve and book flow"""
        # Get an available unit
        r = self.get("/units?status=available", "manager@sipro.co.id")
        units = r.json()["data"]
        
        if len(units) == 0:
            self.log("No available units for reserve test (acceptable)")
            return
        
        unit = units[0]
        
        # Get a lead
        r = self.get("/leads", "manager@sipro.co.id")
        leads = r.json()["data"]
        assert len(leads) > 0, "No leads available for reserve test"
        lead = leads[0]
        
        # Reserve
        r = self.post("/deals/reserve", "manager@sipro.co.id", {
            "unit_id": unit["id"],
            "lead_id": lead["id"],
            "booking_fee": 5000000,
            "notes": "Test reserve"
        })
        
        deal = r.json()["data"]
        assert deal.get("status") == "reserved", f"Expected status 'reserved', got {deal.get('status')}"
        
        # Book
        r = self.post(f"/deals/{deal['id']}/book", "manager@sipro.co.id", {})
        booked = r.json()["data"]
        assert booked.get("status") == "booked", f"Expected status 'booked', got {booked.get('status')}"
        
        self.log(f"Regression: Reserve & Book flow working (deal {deal['id']})")

    def run_all(self):
        """Run all tests in sequence"""
        print("\n" + "="*70)
        print("Phase 20 EPIC 1.4 — Legal Milestone Tracker Backend Test")
        print("="*70 + "\n")
        
        # Run tests in order
        self.test("1. AUTH - Login all roles", self.test_auth_all_roles)
        self.test("2. GET /api/deals - Find booked deal A-01", self.test_get_deals_one_booked)
        
        if not self.deal_id:
            self.log("Cannot continue without deal_id", "FAIL")
            return self.print_summary()
        
        self.test("3. GET /api/deals/{id}/legal - Initial status", self.test_legal_status_initial)
        self.test("4. POST /api/deals/{id}/ajb BEFORE ppjb - Guard 400", self.test_ajb_before_ppjb_guard)
        self.test("5. POST /api/deals/{id}/ppjb - Sign PPJB", self.test_ppjb_sign)
        self.test("6. POST /api/deals/{id}/ppjb again - Guard 400", self.test_ppjb_double_sign_guard)
        self.test("7. POST /api/deals/{id}/ajb - Sign AJB", self.test_ajb_sign)
        self.test("8. GET /api/units?status=sold - Verify A-01 sold", self.test_unit_sold_status)
        self.test("9. GET /api/deals/{id}/legal - Complete records", self.test_legal_records_complete)
        self.test("10a. Regression - /api/work/home", self.test_regression_work_home)
        self.test("10b. Regression - Reserve & Book flow", self.test_regression_reserve_book)
        
        return self.print_summary()

    def print_summary(self):
        """Print test summary"""
        print("\n" + "="*70)
        print(f"Tests Run: {self.tests_run} | Passed: {self.tests_passed} | Failed: {self.tests_run - self.tests_passed}")
        print("="*70)
        
        if self.tests_passed == self.tests_run:
            print("✅ ALL TESTS PASSED")
            return 0
        else:
            print("❌ SOME TESTS FAILED")
            print("\nFailed tests:")
            for r in self.results:
                if r["status"] != "PASS":
                    print(f"  - {r['test']}: {r.get('error', 'Unknown error')}")
            return 1

if __name__ == "__main__":
    tester = Phase20Tester()
    sys.exit(tester.run_all())
