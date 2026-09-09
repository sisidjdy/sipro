"""Reproduksi cacat: unit yang DILEPAS ke stok karena pembatalan masih menyimpan
`sold_by_deal`/`sold_at` — sehingga gate integritas data membacanya sebagai "unit terjual
tanpa ikatan lead/deal". Jalankan: python3 scripts/repro_stale_sold_link.py
"""
import os
import sys

import requests
from dotenv import load_dotenv
from pymongo import MongoClient

BASE = "http://localhost:8001/api"
PW = "Sipro#2026"
load_dotenv("/app/backend/.env")
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def tok(email):
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": PW}, timeout=15)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def main():
    unit = db.units.find_one({"sold_by_deal": {"$nin": [None, ""]},
                              "status": {"$in": ["sold", "booked"]}}, {"_id": 0})
    if not unit:
        print("tidak ada unit sold untuk diuji"); return 1
    contract = db.contracts.find_one({"unit_id": unit["id"]}, {"_id": 0})
    if not contract:
        print("unit sold tanpa kontrak:", unit["code"]); return 1
    print("unit uji:", unit["code"], "deal", unit.get("sold_by_deal"))

    open_doc = db.cancellations.find_one(
        {"contract_id": contract["id"], "state": {"$in": ["diajukan", "ditinjau"]}}, {"_id": 0})
    if open_doc:
        cid = open_doc["id"]
        print("memakai pengajuan yang sudah menunggu:", open_doc.get("number"))
    else:
        sales = tok("manager@sipro.co.id")
        r = requests.post(f"{BASE}/cancellations", headers=sales, timeout=30, json={
            "contract_id": contract["id"],
            "reason": "Repro cacat tautan penjualan basi sesudah unit dilepas ke stok."})
        if r.status_code >= 400:
            print("pengajuan ditolak:", r.status_code, r.text[:300]); return 1
        cid = r.json()["data"]["id"]

    fin = tok("finlead@sipro.co.id")
    r = requests.post(f"{BASE}/cancellations/{cid}/decision", headers=fin, timeout=60,
                      json={"approved": True, "note": "Disetujui untuk reproduksi cacat."})
    print("keputusan:", r.status_code, r.text[:200])

    u = db.units.find_one({"id": unit["id"]},
                          {"_id": 0, "code": 1, "status": 1, "sold_by_deal": 1, "sold_at": 1,
                           "booked_by_deal": 1, "deal_id": 1, "lead_id": 1})
    print("unit sesudah pembatalan:", u)
    stale = bool(u.get("sold_by_deal") or u.get("sold_at")) and u.get("status") == "available"
    print("STALE LINK:", stale)
    return 0 if not stale else 2


if __name__ == "__main__":
    sys.exit(main())
