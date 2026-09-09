"""Helper QA: buat transfer pending (finance) untuk diuji approve/reject di UI owner."""
import os
import sys

import requests

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
PASS = "Sipro#2026"


def tok(email):
    return requests.post(f"{BASE}/api/auth/login", json={"email": email, "password": PASS},
                         timeout=20).json()["access_token"]


def main(n=2):
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {tok('finance@sipro.co.id')}"})
    rows = s.get(f"{BASE}/api/cash-bank/accounts").json()["data"]
    bank = next(r for r in rows if r["kind"] == "bank" and r["is_default"])
    kas = next(r for r in rows if r["kind"] == "cash" and r["is_default"])
    for _ in range(n):
        r = s.post(f"{BASE}/api/cash-bank/transfers", json={
            "kind": "tarik_tunai", "from_account_id": bank["id"], "to_account_id": kas["id"],
            "amount": 1_000_000, "fee": 2_500, "note": "QA UI fase 82"})
        print(r.status_code, r.json().get("data", r.json()).get("no"))
    pos = s.get(f"{BASE}/api/cash-bank/position").json()["data"]
    print("bank", next(a["balance"] for a in pos["accounts"] if a["id"] == bank["id"]),
          "kas", next(a["balance"] for a in pos["accounts"] if a["id"] == kas["id"]))


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 2)
