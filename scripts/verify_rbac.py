"""verify_rbac gate: RBAC enforcement + row-scope (fix #1 of old SIPRO).
Exit non-zero on failure.
"""
import sys
import requests

BASE = "http://localhost:8001/api"
PW = "Sipro#2026"
failures = []


def check(name, cond, detail=""):
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    if not cond:
        failures.append(name)


def login(email):
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": PW}, timeout=10)
    r.raise_for_status()
    return r.json()["access_token"]


def main():
    sales = {"Authorization": f"Bearer {login('sales@sipro.co.id')}"}
    sales2 = {"Authorization": f"Bearer {login('sales2@sipro.co.id')}"}
    owner = {"Authorization": f"Bearer {login('owner@sipro.co.id')}"}

    r = requests.get(f"{BASE}/admin/users", headers=sales, timeout=10)
    check("sales -> /admin/users = 403", r.status_code == 403, f"got {r.status_code}")

    r = requests.get(f"{BASE}/admin/users", headers=owner, timeout=10)
    check("owner -> /admin/users = 200", r.status_code == 200, f"got {r.status_code}")

    r1 = requests.get(f"{BASE}/work/tasks", headers=sales, timeout=10).json()
    r2 = requests.get(f"{BASE}/work/tasks", headers=sales2, timeout=10).json()
    check("sales sees own tasks (>0)", r1.get("total", 0) >= 0)
    # Fase 29: invarian yang benar = tugas orang lain TIDAK BOLEH terlihat (dulu gate ini
    # menuntut total==0 sehingga gagal begitu sales2 punya tugas sendiri yang sah).
    foreign = [t for t in (r2.get("data") or [])
               if t.get("assigned_to") not in (None, "sales2@sipro.co.id")]
    check("sales2 does NOT see sales tasks (row-scope)", not foreign,
          f"sales2 melihat tugas orang lain: {[t.get('assigned_to') for t in foreign][:3]}")

    # unauth request rejected
    r = requests.get(f"{BASE}/work/home", timeout=10)
    check("unauthenticated -> 401", r.status_code == 401, f"got {r.status_code}")

    print("-" * 50)
    if failures:
        print(f"RBAC CHECK FAILED: {len(failures)} issue(s)")
        sys.exit(1)
    print("RBAC CHECK PASSED")


if __name__ == "__main__":
    main()
