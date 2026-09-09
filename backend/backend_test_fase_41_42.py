#!/usr/bin/env python3
"""Backend API Testing for Fase 41 (Aging & SLA) and Fase 42 (Partners & Fee)"""

import requests
import sys
import time
from datetime import datetime

class Fase41And42APITester:
    def __init__(self, base_url="https://sipro-dev-2.preview.emergentagent.com/api"):
        self.base_url = base_url
        self.tokens = {}
        self.tests_run = 0
        self.tests_passed = 0
        self.failed_tests = []
        self.password = "Sipro#2026"

    def run_test(self, name, method, endpoint, expected_status, data=None, headers=None, params=None, role="superadmin"):
        """Run a single API test"""
        url = f"{self.base_url}/{endpoint}"
        if headers is None:
            headers = self.get_headers(role)
        
        self.tests_run += 1
        print(f"\n🔍 Testing {name}...")
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, params=params, timeout=30)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=headers, params=params, timeout=30)
            elif method == 'PUT':
                response = requests.put(url, json=data, headers=headers, params=params, timeout=30)
            elif method == 'DELETE':
                response = requests.delete(url, headers=headers, params=params, timeout=30)

            success = response.status_code == expected_status
            if success:
                self.tests_passed += 1
                print(f"✅ Passed - Status: {response.status_code}")
                try:
                    return success, response.json() if response.text else {}
                except Exception:
                    return success, {}
            else:
                print(f"❌ Failed - Expected {expected_status}, got {response.status_code}")
                print(f"   Response: {response.text[:200]}")
                self.failed_tests.append({"name": name, "expected": expected_status, "got": response.status_code, "response": response.text[:200]})
                return False, {}

        except Exception as e:
            print(f"❌ Failed - Error: {str(e)}")
            self.failed_tests.append({"name": name, "error": str(e)})
            return False, {}

    def login(self, email):
        """Login and get token"""
        if email in self.tokens:
            return self.tokens[email]
        
        print(f"\n🔐 Logging in as {email}...")
        try:
            response = requests.post(
                f"{self.base_url}/auth/login",
                json={"email": email, "password": self.password},
                timeout=20
            )
            if response.status_code == 200:
                token = response.json().get('access_token')
                self.tokens[email] = token
                print(f"✅ Login successful for {email}")
                return token
            else:
                print(f"❌ Login failed for {email}: {response.status_code}")
                return None
        except Exception as e:
            print(f"❌ Login error for {email}: {str(e)}")
            return None

    def get_headers(self, role="superadmin"):
        """Get authorization headers for a role"""
        email_map = {
            "superadmin": "superadmin@sipro.co.id",
            "manager": "manager@sipro.co.id",
            "sales": "sales@sipro.co.id",
            "finance": "finance@sipro.co.id",
            "marketing": "marketing@sipro.co.id",
            "owner": "owner@sipro.co.id"
        }
        email = email_map.get(role, role)
        token = self.login(email)
        if token:
            return {
                'Authorization': f'Bearer {token}',
                'Content-Type': 'application/json'
            }
        return {'Content-Type': 'application/json'}

    def test_fase_41_aging_sla(self):
        """Test Fase 41: Aging & SLA endpoints"""
        print("\n" + "="*60)
        print("FASE 41: AGING & SLA TESTING")
        print("="*60)

        # Test 1: Aging Policy endpoint
        success, response = self.run_test(
            "US-41-1: GET /aging/policy (SLA thresholds from Config Center)",
            "GET",
            "aging/policy",
            200,
            role="superadmin"
        )
        if success:
            data = response.get("data", {})
            entities = response.get("entities", [])
            print(f"   Found {len(entities)} entities with SLA policies")
            if len(entities) >= 7:
                print(f"   ✓ All 7 entities present")
            else:
                print(f"   ⚠ Expected 7 entities, found {len(entities)}")

        # Test 2: Aging Report for leads
        success, response = self.run_test(
            "US-41-1: GET /aging/report?entity=lead",
            "GET",
            "aging/report",
            200,
            params={"entity": "lead"},
            role="superadmin"
        )
        if success:
            data = response.get("data", {})
            rows = data.get("rows", [])
            totals = data.get("totals", {})
            print(f"   Found {len(rows)} stages with aging data")
            print(f"   Totals: {totals.get('count')} total, {totals.get('over_sla')} over SLA, {totals.get('over2_sla')} over 2x SLA")

        # Test 3: Aging Overview (cross-domain panel)
        success, response = self.run_test(
            "US-41-1: GET /aging/overview (cross-domain panel)",
            "GET",
            "aging/overview",
            200,
            role="superadmin"
        )
        if success:
            data = response.get("data", [])
            print(f"   Found {len(data)} entities in overview")
            if len(data) == 7:
                print(f"   ✓ All 7 entities present in cross-domain panel")

        # Test 4: Filter leads by SLA state
        success, response = self.run_test(
            "US-41-4: GET /leads?sla=over (filter by SLA state)",
            "GET",
            "leads",
            200,
            params={"sla": "over", "limit": 5},
            role="superadmin"
        )
        if success:
            total = response.get("total", 0)
            data = response.get("data", [])
            print(f"   Found {total} leads over SLA")
            if data:
                print(f"   First lead SLA state: {data[0].get('sla_state')}")

        # Test 5: Filter leads by SLA state - over2
        success, response = self.run_test(
            "US-41-4: GET /leads?sla=over2 (filter by 2x SLA)",
            "GET",
            "leads",
            200,
            params={"sla": "over2", "limit": 5},
            role="superadmin"
        )

        # Test 6: Filter leads by SLA state - within
        success, response = self.run_test(
            "US-41-4: GET /leads?sla=within (filter within SLA)",
            "GET",
            "leads",
            200,
            params={"sla": "within", "limit": 5},
            role="superadmin"
        )

        # Test 7: RBAC - Sales can view aging report
        success, response = self.run_test(
            "US-41-5: Sales can VIEW aging report",
            "GET",
            "aging/report",
            200,
            params={"entity": "lead"},
            role="sales"
        )

        # Test 8: RBAC - Sales cannot reconcile
        success, response = self.run_test(
            "US-41-5: Sales CANNOT reconcile aging (403 expected)",
            "POST",
            "aging/reconcile",
            403,
            role="sales"
        )

        # Test 9: Admin can reconcile
        success, response = self.run_test(
            "US-41-5: Admin CAN reconcile aging",
            "POST",
            "aging/reconcile",
            200,
            role="superadmin"
        )

        # Test 10: Invalid entity returns 400
        success, response = self.run_test(
            "Aging report with invalid entity returns 400",
            "GET",
            "aging/report",
            400,
            params={"entity": "invalid_entity"},
            role="superadmin"
        )

    def test_fase_42_partners_fee(self):
        """Test Fase 42: Partners & Fee endpoints"""
        print("\n" + "="*60)
        print("FASE 42: PARTNERS & FEE TESTING")
        print("="*60)

        # Test 1: List partners
        success, response = self.run_test(
            "US-42-2: GET /partners (list partners)",
            "GET",
            "partners",
            200,
            role="superadmin"
        )
        partners = []
        if success:
            partners = response.get("data", [])
            total = response.get("total", 0)
            print(f"   Found {total} partners")
            if partners:
                print(f"   First partner: {partners[0].get('name')} ({partners[0].get('partner_kind')})")

        # Test 2: Get partner profile
        if partners:
            partner_id = partners[0].get("id")
            success, response = self.run_test(
                f"US-42-2: GET /partners/{partner_id} (partner profile)",
                "GET",
                f"partners/{partner_id}",
                200,
                role="superadmin"
            )
            if success:
                data = response.get("data", {})
                print(f"   Partner profile loaded with keys: {list(data.keys())}")

        # Test 3: Create partner with duplicate name (should fail)
        if partners:
            success, response = self.run_test(
                "US-42-3: POST /partners with duplicate name (400 expected)",
                "POST",
                "partners",
                400,
                data={
                    "name": partners[0].get("name"),
                    "partner_kind": "agen_perorangan",
                    "phone": "+628120000999"
                },
                role="manager"
            )

        # Test 4: List fee rules
        success, response = self.run_test(
            "US-42-4: GET /partners/rules (list fee rules)",
            "GET",
            "partners/rules",
            200,
            role="superadmin"
        )
        rules = []
        if success:
            rules = response.get("data", [])
            total = response.get("total", 0)
            print(f"   Found {len(rules)} fee rules")
            if rules:
                print(f"   First rule: {rules[0].get('name')} (basis: {rules[0].get('basis')})")

        # Test 5: Create invalid fee rule (splits != 100%)
        success, response = self.run_test(
            "US-42-4: POST /partners/rules with invalid splits (400 expected)",
            "POST",
            "partners/rules",
            400,
            data={
                "name": "Test Invalid Rule",
                "basis": "percent_price",
                "value": 2,
                "splits": [{"trigger": "ppjb_signed", "pct": 40}]
            },
            role="manager"
        )

        # Test 6: Fee preview
        if partners and rules:
            # First get a deal
            success_deal, deal_response = self.run_test(
                "Get deals for fee preview",
                "GET",
                "deals",
                200,
                params={"limit": 1},
                role="superadmin"
            )
            if success_deal:
                deals = deal_response.get("data", [])
                if deals:
                    success, response = self.run_test(
                        "US-42-4: POST /partners/rules/preview (fee calculation)",
                        "POST",
                        "partners/rules/preview",
                        200,
                        data={
                            "partner_id": partners[0].get("id"),
                            "deal_id": deals[0].get("id"),
                            "trigger": "ppjb_signed"
                        },
                        role="superadmin"
                    )
                    if success:
                        data = response.get("data", {})
                        print(f"   Fee preview: {data.get('ok')}, amount: {data.get('amount_gross')}")

        # Test 7: List marketing fees
        success, response = self.run_test(
            "US-42-5: GET /marketing/fees (list fee invoices)",
            "GET",
            "marketing/fees",
            200,
            role="finance"
        )
        fees = []
        if success:
            fees = response.get("data", [])
            total = response.get("total", 0)
            print(f"   Found {total} fee invoices")
            if fees:
                print(f"   First fee: {fees[0].get('code')} - {fees[0].get('status')} - Rp {fees[0].get('amount_gross')}")

        # Test 8: Partner analytics
        success, response = self.run_test(
            "US-42-7: GET /partners/analytics (partner analytics)",
            "GET",
            "partners/analytics",
            200,
            role="superadmin"
        )
        if success:
            data = response.get("data", [])
            totals = response.get("totals", {})
            print(f"   Analytics: {len(data)} partners")
            print(f"   Totals: {totals.get('leads')} leads, {totals.get('qualified')} qualified, {totals.get('closed')} closed")

        # Test 9: RBAC - Sales can view partners
        success, response = self.run_test(
            "US-42-8: Sales CAN view partners",
            "GET",
            "partners",
            200,
            role="sales"
        )

        # Test 10: RBAC - Sales cannot create partners
        success, response = self.run_test(
            "US-42-8: Sales CANNOT create partners (403 expected)",
            "POST",
            "partners",
            403,
            data={
                "name": "Test Partner by Sales",
                "partner_kind": "agen_perorangan",
                "phone": "+628120000998"
            },
            role="sales"
        )

        # Test 11: RBAC - Sales cannot create fee rules
        success, response = self.run_test(
            "US-42-8: Sales CANNOT create fee rules (403 expected)",
            "POST",
            "partners/rules",
            403,
            data={
                "name": "Test Rule by Sales",
                "basis": "fixed_per_deal",
                "value": 1000,
                "trigger": "ppjb_signed"
            },
            role="sales"
        )

        # Test 12: RBAC - Finance cannot issue fees (separation of duties)
        if partners:
            success_deal, deal_response = self.run_test(
                "Get deals for fee issue test",
                "GET",
                "deals",
                200,
                params={"limit": 1},
                role="finance"
            )
            if success_deal:
                deals = deal_response.get("data", [])
                if deals:
                    success, response = self.run_test(
                        "US-42-9: Finance CANNOT issue fees (403 expected - separation of duties)",
                        "POST",
                        "partners/rules/issue",
                        403,
                        data={
                            "partner_id": partners[0].get("id"),
                            "deal_id": deals[0].get("id"),
                            "trigger": "ppjb_signed"
                        },
                        role="finance"
                    )

        # Test 13: List conflicts
        success, response = self.run_test(
            "GET /partners/conflicts (attribution conflicts)",
            "GET",
            "partners/conflicts",
            200,
            role="superadmin"
        )

    def test_regression(self):
        """Test regression: old routes and all role logins"""
        print("\n" + "="*60)
        print("REGRESSION TESTING")
        print("="*60)

        # Test old alias routes
        old_routes = [
            ("GET", "marketing/fees", "Old /marketing-fee route"),
            ("GET", "deals", "Old /deals route"),
            ("GET", "construction/projects", "Old /construction route"),
        ]

        for method, endpoint, name in old_routes:
            self.run_test(
                f"REGRESI-1: {name}",
                method,
                endpoint,
                200,
                role="superadmin"
            )

        # Test login for all roles
        roles = [
            "superadmin@sipro.co.id",
            "owner@sipro.co.id",
            "manager@sipro.co.id",
            "marketing@sipro.co.id",
            "sales@sipro.co.id",
            "sales2@sipro.co.id",
            "finance@sipro.co.id",
            "pm@sipro.co.id",
            "site@sipro.co.id",
            "finlead@sipro.co.id",
            "dmlead@sipro.co.id",
            "dm@sipro.co.id"
        ]

        print("\n🔐 Testing login for all 12 roles...")
        login_success = 0
        for email in roles:
            token = self.login(email)
            if token:
                login_success += 1
                self.tests_run += 1
                self.tests_passed += 1
            else:
                self.tests_run += 1
                self.failed_tests.append({"name": f"Login {email}", "error": "Login failed"})

        print(f"\n✅ {login_success}/{len(roles)} roles can login successfully")

def main():
    print("\n" + "="*60)
    print("SIPRO BACKEND API TESTING - FASE 41 & 42")
    print("="*60)
    
    tester = Fase41And42APITester()
    
    # Run all tests
    tester.test_fase_41_aging_sla()
    tester.test_fase_42_partners_fee()
    tester.test_regression()
    
    # Print summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    print(f"Total tests run: {tester.tests_run}")
    print(f"Tests passed: {tester.tests_passed}")
    print(f"Tests failed: {tester.tests_run - tester.tests_passed}")
    print(f"Success rate: {(tester.tests_passed / tester.tests_run * 100):.1f}%")
    
    if tester.failed_tests:
        print("\n❌ FAILED TESTS:")
        for i, test in enumerate(tester.failed_tests[:10], 1):
            print(f"\n{i}. {test.get('name', 'Unknown test')}")
            if 'error' in test:
                print(f"   Error: {test['error']}")
            else:
                print(f"   Expected: {test.get('expected')}, Got: {test.get('got')}")
                if test.get('response'):
                    print(f"   Response: {test['response']}")
    
    # Return exit code
    if tester.tests_passed == tester.tests_run:
        print("\n✅ ALL TESTS PASSED!")
        return 0
    else:
        print(f"\n⚠️  {tester.tests_run - tester.tests_passed} tests failed")
        return 1

if __name__ == "__main__":
    sys.exit(main())
