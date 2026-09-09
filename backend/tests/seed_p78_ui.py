"""Seed data UJI untuk pengujian UI Fase 76–78 (unit khusus UJI78-*, tidak memakai unit demo).

Mencetak: customer_id + contract_id kontrak KPR "EXCLUDE" yang sudah akad + skema pencairan 80/20
(tahap T1 belum dicairkan) dan kontrak "ALLIN_STD" cash. Jalankan:
  export REACT_APP_BACKEND_URL=... && python tests/seed_p78_ui.py
"""
import os
import time

import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
TAG = str(int(time.time()))[-5:]
s = requests.Session()
tok = s.post(f"{BASE}/api/auth/login", json={"email": "superadmin@sipro.co.id", "password": "Sipro#2026"}).json()["access_token"]
s.headers.update({"Authorization": f"Bearer {tok}"})
proj = s.get(f"{BASE}/api/projects", params={"limit": 1}).json()["data"][0]
schemes = {x["code"]: x for x in s.get(f"{BASE}/api/allin-schemes").json()["data"]}


def unit(prefix):
    code = s.post(f"{BASE}/api/projects/{proj['id']}/units", json={
        "prefix": prefix, "start_index": 1, "count": 1, "type": "Tipe Uji 45", "price": 650_000_000}).json()["data"]["created"][0]
    return next(u for u in s.get(f"{BASE}/api/units", params={"project_id": proj["id"], "limit": 500}).json()["data"] if u["code"] == code)


def contract(prefix, scheme_code, pay_scheme, name):
    u = unit(prefix)
    lead = s.post(f"{BASE}/api/leads", json={"name": name, "phone": f"0817{TAG}{ord(prefix[5])}", "source": "walk_in"}).json()["data"]
    d = s.post(f"{BASE}/api/deals/reserve", json={"unit_id": u["id"], "lead_id": lead["id"], "booking_fee": 5_000_000,
                                                  "allin_scheme_id": schemes[scheme_code]["id"]}).json()["data"]
    s.post(f"{BASE}/api/booking-fee/deals/{d['id']}/pay", json={"amount": 5_000_000, "method": "transfer"})
    s.post(f"{BASE}/api/deals/{d['id']}/book", json={"note": "seed uji"})
    r = s.post(f"{BASE}/api/deals/{d['id']}/convert", json={"scheme": pay_scheme}).json()["data"]
    return r["customer"]["id"], r["contract"]["id"], d["id"]


cust, cid, did = contract(f"UJI78K{TAG}", "EXCLUDE", "kpr", f"Uji KPR Exclude {TAG}")
out = int(s.get(f"{BASE}/api/finance/ar/{did}").json()["data"]["outstanding"])
fid = s.post(f"{BASE}/api/files/upload", files={"file": ("sp3k.pdf", b"%PDF-1.4 uji", "application/pdf")},
             data={"owner_type": "contract", "owner_id": cid, "doc_type": "sp3k"}).json()["data"]["id"]
bodies = {"berkas_lengkap": {}, "diajukan_ke_bank": {"bank": "Bank Uji"}, "appraisal": {"date": "2026-08-30", "amount": out},
          "sp3k": {"file_id": fid, "plafon": out, "number": f"SP3K-{TAG}", "date": "2026-09-01"},
          "akad_kredit": {"date": "2026-09-02", "notary": "Notaris Uji"}}
for _ in range(6):
    nxt = s.get(f"{BASE}/api/contracts/{cid}/kpr").json()["data"].get("next_stage")
    if nxt in (None, "pencairan"):
        break
    s.post(f"{BASE}/api/contracts/{cid}/kpr/stage/{nxt}", json=bodies[nxt])
ks = s.get(f"{BASE}/api/kpr-disbursement-schemes").json()["data"]
sch = next((x for x in ks if "80" in x["name"] and x.get("is_active")), None) or s.post(f"{BASE}/api/kpr-disbursement-schemes", json={
    "name": f"Uji 80-20 {TAG}", "bank": "Bank Uji", "tolerance_pct": 1, "is_active": True,
    "tranches": [{"code": "T1", "name": "Akad", "pct": 80, "condition": "akad"},
                 {"code": "T2", "name": "Retensi", "pct": 20, "condition": "akad"}]}).json()["data"]
s.post(f"{BASE}/api/contracts/{cid}/kpr/disbursement-scheme", json={"scheme_id": sch["id"]})
print("KPR_EXCLUDE customer_id", cust, "contract_id", cid, "url", f"/customers/{cust}?tab=kontrak53")
cust2, cid2, _ = contract(f"UJI78A{TAG}", "ALLIN_STD", "cash_keras", f"Uji Allin Cash {TAG}")
print("ALLIN_CASH customer_id", cust2, "contract_id", cid2, "url", f"/customers/{cust2}?tab=kontrak53")
