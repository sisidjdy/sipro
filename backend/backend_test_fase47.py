"""
Backend API Test for Phase 47 (Fase 47)
Tests: 47A Bank Reconciliation, 47B Payment Proof Portal, 47C Quotations, 47D Labor & Wages
"""
import requests
import sys
from datetime import datetime, date

BASE_URL = "https://labor-tracker-87.preview.emergentagent.com/api"

class Phase47Tester:
    def __init__(self):
        self.base_url = BASE_URL
        self.tokens = {}
        self.tests_run = 0
        self.tests_passed = 0
        self.test_data = {}

    def login(self, email, password="Sipro#2026"):
        """Login and store token"""
        try:
            response = requests.post(
                f"{self.base_url}/auth/login",
                json={"email": email, "password": password},
                timeout=10
            )
            if response.status_code == 200:
                data = response.json()
                self.tokens[email] = data.get("access_token")
                print(f"✅ Login berhasil: {email}")
                return True
            else:
                print(f"❌ Login gagal {email}: {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ Login error {email}: {str(e)}")
            return False

    def get_headers(self, email):
        """Get authorization headers"""
        return {
            "Authorization": f"Bearer {self.tokens.get(email)}",
            "Content-Type": "application/json"
        }

    def test_api(self, name, method, endpoint, expected_status, email=None, data=None, check_response=None):
        """Run a single API test"""
        self.tests_run += 1
        url = f"{self.base_url}/{endpoint}"
        headers = self.get_headers(email) if email else {"Content-Type": "application/json"}

        try:
            if method == "GET":
                response = requests.get(url, headers=headers, timeout=10)
            elif method == "POST":
                response = requests.post(url, json=data, headers=headers, timeout=10)
            elif method == "PUT":
                response = requests.put(url, json=data, headers=headers, timeout=10)
            elif method == "DELETE":
                response = requests.delete(url, headers=headers, timeout=10)

            success = response.status_code == expected_status
            if success:
                self.tests_passed += 1
                result_data = response.json() if response.status_code < 400 else {}
                
                # Additional response checks
                if check_response and result_data:
                    check_result = check_response(result_data)
                    if not check_result:
                        success = False
                        self.tests_passed -= 1
                        print(f"❌ {name} - Response check failed")
                    else:
                        print(f"✅ {name} - Status {response.status_code}")
                else:
                    print(f"✅ {name} - Status {response.status_code}")
                
                return success, result_data
            else:
                print(f"❌ {name} - Expected {expected_status}, got {response.status_code}")
                if response.status_code >= 400:
                    try:
                        print(f"   Error: {response.json().get('detail', 'No detail')}")
                    except Exception:
                        pass
                return False, {}

        except Exception as e:
            print(f"❌ {name} - Error: {str(e)}")
            return False, {}

    def run_tests(self):
        """Run all Phase 47 tests"""
        print("\n" + "="*80)
        print("FASE 47 BACKEND API TESTS")
        print("="*80)

        # Login all users
        print("\n--- LOGIN USERS ---")
        users = [
            "finance@sipro.co.id",
            "finlead@sipro.co.id", 
            "sales@sipro.co.id",
            "manager@sipro.co.id",
            "pm@sipro.co.id",
            "site@sipro.co.id"
        ]
        
        for user in users:
            if not self.login(user):
                print(f"⚠️  Cannot proceed without {user}")
                return

        # ===== 47A: BANK RECONCILIATION =====
        print("\n--- 47A: BANK RECONCILIATION ---")
        
        # Get bank accounts
        success, data = self.test_api(
            "Get bank accounts",
            "GET",
            "bank/accounts",
            200,
            "finance@sipro.co.id"
        )
        if success and data.get("accounts"):
            account_id = data["accounts"][0]["id"]
            self.test_data["account_id"] = account_id
            print(f"   Using account: {account_id}")

        # Get reconciliation summary
        if "account_id" in self.test_data:
            success, data = self.test_api(
                "Get reconciliation summary",
                "GET",
                f"bank/reconciliation?account_id={self.test_data['account_id']}",
                200,
                "finance@sipro.co.id",
                check_response=lambda d: "book_balance" in d and "bank_balance" in d
            )

        # Get unmatched transactions
        success, data = self.test_api(
            "Get unmatched transactions",
            "GET",
            "bank/transactions?match_state=unmatched&limit=10",
            200,
            "finance@sipro.co.id"
        )
        if success and data.get("transactions"):
            unmatched_txn = data["transactions"][0]
            self.test_data["unmatched_txn_id"] = unmatched_txn["id"]
            print(f"   Found unmatched transaction: {unmatched_txn.get('description', 'N/A')}")

        # Get matching suggestions
        if "unmatched_txn_id" in self.test_data:
            success, data = self.test_api(
                "Get matching suggestions",
                "GET",
                f"bank/transactions/{self.test_data['unmatched_txn_id']}/suggest",
                200,
                "finance@sipro.co.id",
                check_response=lambda d: "candidates" in d
            )
            if success and data.get("candidates"):
                print(f"   Found {len(data['candidates'])} matching candidates")

        # Test RBAC: sales should get 403
        self.test_api(
            "RBAC: Sales cannot access bank transactions",
            "GET",
            "bank/transactions",
            403,
            "sales@sipro.co.id"
        )

        # ===== 47B: PAYMENT PROOF PORTAL =====
        print("\n--- 47B: PAYMENT PROOF PORTAL ---")
        
        # Get payment intakes (finance)
        success, data = self.test_api(
            "Get payment intakes",
            "GET",
            "payment-intakes?limit=10",
            200,
            "finance@sipro.co.id"
        )
        if success and data.get("intakes"):
            pending_intakes = [i for i in data["intakes"] if i.get("state") == "pending"]
            if pending_intakes:
                self.test_data["pending_intake_id"] = pending_intakes[0]["id"]
                print(f"   Found pending intake: {self.test_data['pending_intake_id']}")

        # Test RBAC: sales should get 403
        self.test_api(
            "RBAC: Sales cannot access payment intakes",
            "GET",
            "payment-intakes",
            403,
            "sales@sipro.co.id"
        )

        # ===== 47C: QUOTATIONS =====
        print("\n--- 47C: QUOTATIONS & MORTGAGE SIMULATION ---")
        
        # Get leads (sales)
        success, data = self.test_api(
            "Get leads for quotation",
            "GET",
            "leads?limit=5",
            200,
            "sales@sipro.co.id"
        )
        if success and data.get("leads"):
            lead_id = data["leads"][0]["id"]
            self.test_data["lead_id"] = lead_id
            print(f"   Using lead: {lead_id}")

        # Get units for quotation
        success, data = self.test_api(
            "Get available units",
            "GET",
            "units?status=available&limit=5",
            200,
            "sales@sipro.co.id"
        )
        if success and data.get("units"):
            unit_id = data["units"][0]["id"]
            self.test_data["unit_id"] = unit_id
            print(f"   Using unit: {unit_id}")

        # Simulate quotation (without discount)
        if "unit_id" in self.test_data:
            success, data = self.test_api(
                "Simulate quotation without discount",
                "POST",
                "quotations/simulate",
                200,
                "sales@sipro.co.id",
                data={
                    "unit_id": self.test_data["unit_id"],
                    "discount_pct": 0,
                    "discount_reason": ""
                },
                check_response=lambda d: "gross" in d and "net" in d and "terms" in d
            )
            if success:
                print(f"   Gross: Rp {data.get('gross', 0):,}, Net: Rp {data.get('net', 0):,}")
                print(f"   Terms count: {len(data.get('terms', []))}")

        # Simulate with mortgage (KPR)
        if "unit_id" in self.test_data:
            success, data = self.test_api(
                "Simulate with mortgage (KPR)",
                "POST",
                "quotations/simulate",
                200,
                "sales@sipro.co.id",
                data={
                    "unit_id": self.test_data["unit_id"],
                    "discount_pct": 0,
                    "mortgage_tenor_months": 180,
                    "mortgage_interest_pct": 9.5,
                    "mortgage_dp_pct": 20
                },
                check_response=lambda d: "mortgage" in d and d["mortgage"].get("monthly_payment")
            )
            if success and data.get("mortgage"):
                print(f"   Monthly payment: Rp {data['mortgage'].get('monthly_payment', 0):,}")

        # Test RBAC: pm should get 403 for quotations
        self.test_api(
            "RBAC: PM cannot access quotations",
            "GET",
            "quotations",
            403,
            "pm@sipro.co.id"
        )

        # ===== 47D: LABOR & WAGES =====
        print("\n--- 47D: LABOR ATTENDANCE & WAGES ---")
        
        # Get workers
        success, data = self.test_api(
            "Get workers",
            "GET",
            "labor/workers?limit=10",
            200,
            "site@sipro.co.id"
        )
        if success and data.get("workers"):
            print(f"   Found {len(data['workers'])} workers")
            if data["workers"]:
                self.test_data["worker_id"] = data["workers"][0]["id"]

        # Get attendance for today
        today = date.today().isoformat()
        success, data = self.test_api(
            "Get attendance for today",
            "GET",
            f"labor/attendance?work_date={today}",
            200,
            "site@sipro.co.id"
        )

        # Get payroll recaps
        success, data = self.test_api(
            "Get payroll recaps",
            "GET",
            "labor/payrolls?limit=10",
            200,
            "pm@sipro.co.id"
        )
        if success and data.get("payrolls"):
            print(f"   Found {len(data['payrolls'])} payroll recaps")
            submitted_payrolls = [p for p in data["payrolls"] if p.get("state") == "submitted"]
            if submitted_payrolls:
                self.test_data["submitted_payroll_id"] = submitted_payrolls[0]["id"]
                print(f"   Found submitted payroll: {self.test_data['submitted_payroll_id']}")

        # Test RBAC: sales should get 403 for labor
        self.test_api(
            "RBAC: Sales cannot access labor",
            "GET",
            "labor/workers",
            403,
            "sales@sipro.co.id"
        )

        # Test RBAC: site cannot approve payroll
        if "submitted_payroll_id" in self.test_data:
            self.test_api(
                "RBAC: Site engineer cannot approve payroll",
                "POST",
                f"labor/payrolls/{self.test_data['submitted_payroll_id']}/approve",
                403,
                "site@sipro.co.id"
            )

        # ===== SUMMARY =====
        print("\n" + "="*80)
        print(f"TESTS COMPLETED: {self.tests_passed}/{self.tests_run} PASSED")
        print("="*80)
        
        return 0 if self.tests_passed == self.tests_run else 1


def main():
    tester = Phase47Tester()
    return tester.run_tests()


if __name__ == "__main__":
    sys.exit(main())
