"""Seed UI Fase 75 — buat 2 kontrak KPR:
 A) fresh (next_stage=berkas_lengkap) untuk uji tombol 'Catat Berkas lengkap'
 B) siap pencairan untuk uji dialog nominal wajib + kartu akuntansi.
Cetak id kontrak agar dipakai skrip Playwright.
"""
import os
import time
import random

import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
TAG = str(int(time.time()))[-6:]

r = requests.post(f"{BASE}/api/auth/login",
                  json={"email": "superadmin@sipro.co.id", "password": "Sipro#2026"}, timeout=20)
s = requests.Session()
s.headers.update({"Authorization": f"Bearer {r.json()['access_token']}"})


def make_kpr_contract(name):
    opts = s.get(f"{BASE}/api/quotations/options").json()["data"]
    unit = opts["units"][0]
    lead = s.post(f"{BASE}/api/leads", json={"name": name, "phone": f"0819{TAG}{random.randint(10, 99)}",
                                             "source": "walk_in"}).json()["data"]
    d = s.post(f"{BASE}/api/deals/reserve", json={
        "unit_id": unit["id"], "lead_id": lead["id"], "booking_fee": 5_000_000,
        "costs": {"bphtb": 20_000_000, "all_in_by_developer": False}})
    d.raise_for_status()
    deal = d.json()["data"]
    s.post(f"{BASE}/api/booking-fee/deals/{deal['id']}/pay", json={"amount": 5_000_000, "method": "transfer"})
    s.post(f"{BASE}/api/deals/{deal['id']}/book", json={"note": "seed"})
    cid = s.post(f"{BASE}/api/deals/{deal['id']}/convert", json={}).json()["data"]["contract"]["id"]
    s.post(f"{BASE}/api/contracts/{cid}/scheme", json={"scheme": "kpr", "reason": "seed"})
    return deal, cid


deal_a, cid_a = make_kpr_contract(f"Uji UI KPR A {TAG}")
deal_b, cid_b = make_kpr_contract(f"Uji UI KPR B {TAG}")

out = 0
for _ in range(10):
    out = int(s.get(f"{BASE}/api/finance/ar/{deal_b['id']}").json()["data"].get("outstanding") or 0)
    if out:
        break
    time.sleep(1)
if not out:
    out = int((s.get(f"{BASE}/api/contracts/{cid_b}").json()["data"].get("contract") or {}).get("total_price") or 500_000_000)
up = s.post(f"{BASE}/api/files/upload", files={"file": ("sp3k.pdf", b"%PDF-1.4 seed", "application/pdf")},
            data={"owner_type": "contract", "owner_id": cid_b, "doc_type": "sp3k"})
fid = up.json()["data"]["id"]
bodies = {"berkas_lengkap": {}, "diajukan_ke_bank": {"bank": "Bank Seed"},
          "appraisal": {"date": "2026-08-30", "amount": out},
          "sp3k": {"file_id": fid, "plafon": out, "number": f"SP3K-UI-{TAG}", "date": "2026-09-01"},
          "akad_kredit": {"date": "2026-09-02", "notary": "Notaris Seed"}}
for _ in range(6):
    nxt = s.get(f"{BASE}/api/contracts/{cid_b}/kpr").json()["data"].get("next_stage")
    if nxt in (None, "pencairan"):
        break
    rr = s.post(f"{BASE}/api/contracts/{cid_b}/kpr/stage/{nxt}", json=bodies[nxt])
    if rr.status_code != 200:
        print("GAGAL", nxt, rr.text)
        break

print("CONTRACT_A(berkas_lengkap)=", cid_a)
print("CONTRACT_B(pencairan)=", cid_b, "outstanding=", out)
print("next_b=", s.get(f"{BASE}/api/contracts/{cid_b}/kpr").json()["data"].get("next_stage"))
