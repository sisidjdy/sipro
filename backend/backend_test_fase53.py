"""Fase 53 Backend Test — Auth Permissions Bug Fix

BUG-1d: POST /api/auth/login and GET /api/auth/me must return the SAME profile structure
with `permissions`, `active_org`, `home_org_id`, `is_switched`, `level`, `role` fields.

Tests:
1. Login superadmin → verify response has permissions field with {"*": ["*"]}
2. Login owner → verify response has permissions field (full access)
3. Login sales → verify response has permissions field (limited)
4. Login finance → verify response has permissions field
5. GET /auth/me for each role → verify same structure as login response
6. Verify permissions field is NOT null/undefined for any role
"""
import requests
import sys
import json

BASE_URL = "https://permission-audit-16.preview.emergentagent.com/api"
PASSWORD = "Sipro#2026"

class AuthPermissionsTester:
    def __init__(self):
        self.tests_run = 0
        self.tests_passed = 0
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

    def verify_profile_structure(self, profile, email, source):
        """Verify profile has all required fields"""
        required_fields = ["permissions", "active_org", "home_org_id", "is_switched", "role", "email"]
        missing = [f for f in required_fields if f not in profile]
        assert not missing, f"{source} for {email} missing fields: {missing}"
        
        # Permissions must be a dict, not null/undefined
        assert profile["permissions"] is not None, f"{source} for {email} has null permissions"
        assert isinstance(profile["permissions"], dict), f"{source} for {email} permissions is not a dict"
        
        self.log(f"  ✓ {source} profile structure valid for {email}")
        return profile

    def test_login_response_structure(self, email, expected_role):
        """Test that login response contains permissions"""
        self.log(f"Testing login response for {email}...", "INFO")
        r = requests.post(f"{BASE_URL}/auth/login", json={"email": email, "password": PASSWORD})
        assert r.status_code == 200, f"Login failed: {r.status_code} {r.text}"
        
        data = r.json()
        assert "data" in data, "Login response missing 'data' field"
        assert "access_token" in data, "Login response missing 'access_token' field"
        
        profile = data["data"]
        self.verify_profile_structure(profile, email, "POST /auth/login")
        
        # Verify role matches
        assert profile["role"] == expected_role, f"Expected role {expected_role}, got {profile['role']}"
        
        return data["access_token"], profile

    def test_me_response_structure(self, token, email):
        """Test that /auth/me returns same structure"""
        self.log(f"Testing /auth/me for {email}...", "INFO")
        r = requests.get(f"{BASE_URL}/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200, f"/auth/me failed: {r.status_code} {r.text}"
        
        data = r.json()
        assert "data" in data, "/auth/me response missing 'data' field"
        
        profile = data["data"]
        self.verify_profile_structure(profile, email, "GET /auth/me")
        
        return profile

    def test_permissions_consistency(self, login_profile, me_profile, email):
        """Verify login and /me return same permissions"""
        self.log(f"Comparing permissions for {email}...", "INFO")
        
        login_perms = json.dumps(login_profile["permissions"], sort_keys=True)
        me_perms = json.dumps(me_profile["permissions"], sort_keys=True)
        
        assert login_perms == me_perms, f"Permissions mismatch for {email}:\nLogin: {login_perms}\n/me: {me_perms}"
        self.log(f"  ✓ Permissions consistent for {email}")

    def test_superadmin_permissions(self):
        """Test 1: superadmin has {"*": ["*"]} permissions"""
        email = "superadmin@sipro.co.id"
        token, login_profile = self.test_login_response_structure(email, "super_admin")
        me_profile = self.test_me_response_structure(token, email)
        self.test_permissions_consistency(login_profile, me_profile, email)
        
        # Verify superadmin has wildcard permissions
        perms = login_profile["permissions"]
        assert "*" in perms, f"superadmin missing wildcard resource"
        assert "*" in perms["*"], f"superadmin missing wildcard action"
        self.log(f"  ✓ superadmin has wildcard permissions: {perms}")

    def test_owner_permissions(self):
        """Test 2: owner has full access permissions"""
        email = "owner@sipro.co.id"
        token, login_profile = self.test_login_response_structure(email, "owner")
        me_profile = self.test_me_response_structure(token, email)
        self.test_permissions_consistency(login_profile, me_profile, email)
        
        # Owner should have many permissions
        perms = login_profile["permissions"]
        assert len(perms) > 5, f"owner has too few permissions: {len(perms)}"
        self.log(f"  ✓ owner has {len(perms)} resource permissions")

    def test_sales_permissions(self):
        """Test 3: sales has limited permissions"""
        email = "sales@sipro.co.id"
        token, login_profile = self.test_login_response_structure(email, "sales")
        me_profile = self.test_me_response_structure(token, email)
        self.test_permissions_consistency(login_profile, me_profile, email)
        
        # Sales should have limited permissions
        perms = login_profile["permissions"]
        assert len(perms) > 0, f"sales has no permissions"
        # Sales should NOT have tax access
        assert "tax" not in perms or "view" not in perms.get("tax", []), \
            f"sales should not have tax:view permission"
        self.log(f"  ✓ sales has {len(perms)} resource permissions (limited)")

    def test_finance_permissions(self):
        """Test 4: finance has finance-related permissions"""
        email = "finance@sipro.co.id"
        token, login_profile = self.test_login_response_structure(email, "finance")
        me_profile = self.test_me_response_structure(token, email)
        self.test_permissions_consistency(login_profile, me_profile, email)
        
        # Finance should have tax access
        perms = login_profile["permissions"]
        assert "tax" in perms, f"finance missing tax permissions"
        self.log(f"  ✓ finance has {len(perms)} resource permissions including tax")

    def run_all_tests(self):
        """Run all auth permission tests"""
        print("\n" + "="*70)
        print("FASE 53 AUTH PERMISSIONS BACKEND TEST")
        print("="*70 + "\n")

        self.test("1. Superadmin login & /me permissions", self.test_superadmin_permissions)
        self.test("2. Owner login & /me permissions", self.test_owner_permissions)
        self.test("3. Sales login & /me permissions", self.test_sales_permissions)
        self.test("4. Finance login & /me permissions", self.test_finance_permissions)

        print("\n" + "="*70)
        print(f"RESULTS: {self.tests_passed}/{self.tests_run} tests passed")
        print("="*70 + "\n")

        return 0 if self.tests_passed == self.tests_run else 1

def main():
    tester = AuthPermissionsTester()
    return tester.run_all_tests()

if __name__ == "__main__":
    sys.exit(main())
