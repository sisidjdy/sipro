#!/usr/bin/env python3
"""
Backend API Testing for SIPRO Fase 52 Bug Fixes
Tests BUG-1 (appointments permissions) and BUG-2 (lead profile 403 handling)
"""
import requests
import sys
from typing import Dict, Optional

BASE_URL = "https://lead-panel-repair.preview.emergentagent.com/api"
PASSWORD = "Sipro#2026"

# Test lead ID (Ibu Dewi Kartika, assigned to sales@sipro.co.id)
TEST_LEAD_ID = "aee3d957-4e91-4c54-b132-4b40d20b3559"

class APITester:
    def __init__(self):
        self.tests_run = 0
        self.tests_passed = 0
        self.tokens = {}
        
    def login(self, email: str) -> Optional[str]:
        """Login and get token"""
        print(f"\n🔐 Login sebagai {email}...")
        try:
            response = requests.post(
                f"{BASE_URL}/auth/login",
                json={"email": email, "password": PASSWORD},
                timeout=10
            )
            if response.status_code == 200:
                data = response.json()
                token = data.get("access_token") or data.get("data", {}).get("token") or data.get("token")
                if token:
                    self.tokens[email] = token
                    print(f"   ✅ Login berhasil")
                    return token
                else:
                    print(f"   ❌ Token tidak ditemukan dalam respons")
                    return None
            else:
                print(f"   ❌ Login gagal: {response.status_code}")
                return None
        except Exception as e:
            print(f"   ❌ Error: {str(e)}")
            return None
    
    def test(self, name: str, method: str, endpoint: str, 
             expected_status: int, token: str = None, 
             json_data: dict = None) -> bool:
        """Run a single API test"""
        self.tests_run += 1
        url = f"{BASE_URL}{endpoint}"
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        
        print(f"\n🔍 Test: {name}")
        print(f"   {method} {endpoint}")
        
        try:
            if method == "GET":
                response = requests.get(url, headers=headers, timeout=10)
            elif method == "POST":
                response = requests.post(url, headers=headers, json=json_data, timeout=10)
            elif method == "PUT":
                response = requests.put(url, headers=headers, json=json_data, timeout=10)
            elif method == "DELETE":
                response = requests.delete(url, headers=headers, timeout=10)
            else:
                print(f"   ❌ Method tidak didukung: {method}")
                return False
            
            success = response.status_code == expected_status
            if success:
                self.tests_passed += 1
                print(f"   ✅ PASS - Status: {response.status_code}")
                return True
            else:
                print(f"   ❌ FAIL - Expected {expected_status}, got {response.status_code}")
                if response.status_code >= 400:
                    try:
                        detail = response.json().get("detail", "")
                        print(f"   Detail: {detail}")
                    except Exception:
                        pass
                return False
        except Exception as e:
            print(f"   ❌ FAIL - Error: {str(e)}")
            return False
    
    def print_summary(self):
        """Print test summary"""
        print("\n" + "="*70)
        print(f"📊 HASIL PENGUJIAN: {self.tests_passed}/{self.tests_run} PASS")
        if self.tests_passed == self.tests_run:
            print("✅ SEMUA TEST LULUS")
        else:
            print(f"❌ {self.tests_run - self.tests_passed} TEST GAGAL")
        print("="*70)
        return 0 if self.tests_passed == self.tests_run else 1


def main():
    tester = APITester()
    
    print("="*70)
    print("BACKEND API TESTING - SIPRO FASE 52")
    print("BUG-1: Appointments permissions for finance/finlead")
    print("BUG-2: Lead profile 403 handling")
    print("="*70)
    
    # ========================================================================
    # BACKEND-1: GET /api/appointments permissions
    # ========================================================================
    print("\n" + "="*70)
    print("BACKEND-1: Appointments Endpoint Permissions")
    print("="*70)
    
    # Login all test users
    finance_token = tester.login("finance@sipro.co.id")
    finlead_token = tester.login("finlead@sipro.co.id")
    pm_token = tester.login("pm@sipro.co.id")
    site_token = tester.login("site@sipro.co.id")
    sales_token = tester.login("sales@sipro.co.id")
    
    if not all([finance_token, finlead_token, pm_token, site_token, sales_token]):
        print("\n❌ CRITICAL: Tidak semua login berhasil")
        return 1
    
    # Test 1: finance@ should be able to READ appointments
    tester.test(
        "finance@ GET /appointments (should be 200)",
        "GET", "/appointments",
        expected_status=200,
        token=finance_token
    )
    
    # Test 2: finlead@ should be able to READ appointments
    tester.test(
        "finlead@ GET /appointments (should be 200)",
        "GET", "/appointments",
        expected_status=200,
        token=finlead_token
    )
    
    # Test 3: finance@ should NOT be able to CREATE appointments
    tester.test(
        "finance@ POST /appointments (should be 403)",
        "POST", "/appointments",
        expected_status=403,
        token=finance_token,
        json_data={
            "lead_id": TEST_LEAD_ID,
            "type": "survey",
            "scheduled_at": "2026-09-01T10:00:00Z",
            "notes": "Test appointment"
        }
    )
    
    # Test 4: finlead@ should NOT be able to CREATE appointments
    tester.test(
        "finlead@ POST /appointments (should be 403)",
        "POST", "/appointments",
        expected_status=403,
        token=finlead_token,
        json_data={
            "lead_id": TEST_LEAD_ID,
            "type": "survey",
            "scheduled_at": "2026-09-01T10:00:00Z",
            "notes": "Test appointment"
        }
    )
    
    # Test 5: pm@ should NOT have access to appointments
    tester.test(
        "pm@ GET /appointments (should be 403)",
        "GET", "/appointments",
        expected_status=403,
        token=pm_token
    )
    
    # Test 6: site@ should NOT have access to appointments
    tester.test(
        "site@ GET /appointments (should be 403)",
        "GET", "/appointments",
        expected_status=403,
        token=site_token
    )
    
    # ========================================================================
    # BACKEND-2: Lead profile endpoints for different roles
    # ========================================================================
    print("\n" + "="*70)
    print("BACKEND-2: Lead Profile Endpoints")
    print("="*70)
    
    # Test 7: finance@ should be able to READ lead
    tester.test(
        "finance@ GET /leads/{id} (should be 200)",
        "GET", f"/leads/{TEST_LEAD_ID}",
        expected_status=200,
        token=finance_token
    )
    
    # Test 8: finlead@ should be able to READ lead
    tester.test(
        "finlead@ GET /leads/{id} (should be 200)",
        "GET", f"/leads/{TEST_LEAD_ID}",
        expected_status=200,
        token=finlead_token
    )
    
    # Test 9: finance@ should be able to READ lifecycle
    tester.test(
        "finance@ GET /leads/{id}/lifecycle (should be 200)",
        "GET", f"/leads/{TEST_LEAD_ID}/lifecycle",
        expected_status=200,
        token=finance_token
    )
    
    # Test 10: finance@ should be able to READ activities
    tester.test(
        "finance@ GET /activities?entity_type=lead (should be 200)",
        "GET", f"/activities?entity_type=lead&entity_id={TEST_LEAD_ID}",
        expected_status=200,
        token=finance_token
    )
    
    # Test 11: finance@ should be able to READ deals
    tester.test(
        "finance@ GET /deals?lead_id={id} (should be 200)",
        "GET", f"/deals?lead_id={TEST_LEAD_ID}",
        expected_status=200,
        token=finance_token
    )
    
    # Test 12: finance@ should be able to READ doc submissions
    tester.test(
        "finance@ GET /doc/submissions (should be 200)",
        "GET", f"/doc/submissions?entity_type=lead&entity_id={TEST_LEAD_ID}",
        expected_status=200,
        token=finance_token
    )
    
    # Test 13: finance@ should be able to READ quotations
    tester.test(
        "finance@ GET /quotations (should be 200)",
        "GET", f"/quotations?lead_id={TEST_LEAD_ID}",
        expected_status=200,
        token=finance_token
    )
    
    # Test 14: finance@ should be able to READ WA messages
    tester.test(
        "finance@ GET /leads/{id}/wa (should be 200)",
        "GET", f"/leads/{TEST_LEAD_ID}/wa",
        expected_status=200,
        token=finance_token
    )
    
    # Test 15: sales2@ should get 403 for lead owned by sales@
    sales2_token = tester.login("sales2@sipro.co.id")
    if sales2_token:
        tester.test(
            "sales2@ GET /leads/{id} owned by sales@ (should be 403 'bukan lead Anda')",
            "GET", f"/leads/{TEST_LEAD_ID}",
            expected_status=403,
            token=sales2_token
        )
    
    # Test 16: pm@ should get 403 for leads (no permission)
    tester.test(
        "pm@ GET /leads/{id} (should be 403 'tidak memiliki izin')",
        "GET", f"/leads/{TEST_LEAD_ID}",
        expected_status=403,
        token=pm_token
    )
    
    # Test 17: site@ should get 403 for leads (no permission)
    tester.test(
        "site@ GET /leads/{id} (should be 403 'tidak memiliki izin')",
        "GET", f"/leads/{TEST_LEAD_ID}",
        expected_status=403,
        token=site_token
    )
    
    # Print summary
    return tester.print_summary()


if __name__ == "__main__":
    sys.exit(main())
