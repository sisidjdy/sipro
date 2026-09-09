"""health_check gate: verify key endpoints return correct CONTENT (not just 200).
Exit non-zero on failure. Adopted pattern from `kn`.
"""
import sys
import requests

BASE = "http://localhost:8001/api"
PW = "Sipro#2026"
failures = []


def check(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {name}" + (f" — {detail}" if detail else ""))
    if not cond:
        failures.append(name)


def login(email):
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": PW}, timeout=10)
    r.raise_for_status()
    return r.json()["access_token"]


def main():
    r = requests.get(f"{BASE}/health", timeout=10)
    check("GET /health", r.status_code == 200 and r.json().get("status") == "ok")

    tok = login("sales@sipro.co.id")
    h = {"Authorization": f"Bearer {tok}"}

    r = requests.get(f"{BASE}/auth/me", headers=h, timeout=10)
    check("GET /auth/me returns user", r.status_code == 200 and r.json()["data"]["email"] == "sales@sipro.co.id")

    r = requests.get(f"{BASE}/work/home", headers=h, timeout=10)
    d = r.json().get("data", {}) if r.status_code == 200 else {}
    check("GET /work/home has title+kpis+tasks", bool(d.get("title")) and "kpis" in d and "tasks" in d,
          f"title={d.get('title')}")

    r = requests.get(f"{BASE}/work/tasks", headers=h, timeout=10)
    check("GET /work/tasks returns data+counts", r.status_code == 200 and "counts" in r.json())

    r = requests.get(f"{BASE}/notifications", headers=h, timeout=10)
    check("GET /notifications returns data", r.status_code == 200 and "data" in r.json())

    print("-" * 50)
    if failures:
        print(f"HEALTH CHECK FAILED: {len(failures)} issue(s)")
        sys.exit(1)
    print("HEALTH CHECK PASSED")


if __name__ == "__main__":
    main()
