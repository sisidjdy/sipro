"""Reproduksi: SPR yang terbit ≠ skema yang dipilih sales saat reservasi.

Jalankan: python3 scripts/repro_spr_scheme_mismatch.py  (backend harus hidup di :8001)
Membuat lead + reservasi cash_bertahap + booking + konversi + SPR, lalu membandingkan
AR, breakdown deal, dan isi SPR. Deal uji dihapus paksa di akhir (kecuali --keep).
"""
import json
import re
import sys
import time

import requests

BASE = "http://localhost:8001/api"
PW = "Sipro#2026"


def login(email):
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": PW})
    r.raise_for_status()
    tok = r.json().get("access_token") or r.json().get("token") or (r.json().get("data") or {}).get("token")
    return {"Authorization": f"Bearer {tok}"}


def main(keep=False, kind="cash_bertahap"):
    H = login("superadmin@sipro.co.id")
    schemes = requests.get(f"{BASE}/finance/config/payment-schemes", headers=H).json()["data"]
    sch = next(s for s in schemes if s.get("kind") == kind and s.get("active", True))
    default = next((s for s in schemes if s.get("is_default")), None)
    print("skema dipilih :", sch["name"], "| bawaan finance:", (default or {}).get("name"))
    allin = requests.get(f"{BASE}/allin-schemes", headers=H).json()["data"]
    allin_id = next((a["id"] for a in allin if a.get("is_active", True)), None)
    units = requests.get(f"{BASE}/units", headers=H, params={"status": "available"}).json()["data"]
    unit = next(u for u in units if u.get("status") == "available" and int(u.get("price") or 0) > 0)
    lead = requests.post(f"{BASE}/leads", headers=H, json={
        "name": f"Repro SPR {int(time.time())}", "phone": f"08{int(time.time()) % 10**9:09d}",
        "source": "walk_in"}).json()["data"]
    deal = requests.post(f"{BASE}/deals/reserve", headers=H, json={
        "unit_id": unit["id"], "lead_id": lead["id"], "booking_fee": 5_000_000,
        "scheme_id": sch["id"], "allin_scheme_id": allin_id}).json()
    if "data" not in deal:
        print("RESERVE GAGAL:", deal)
        return 2
    deal = deal["data"]
    print("deal.scheme_id ==", deal.get("scheme_id") == sch["id"])
    # booking fee tercatat → booking
    requests.post(f"{BASE}/booking-fee/deals/{deal['id']}/pay", headers=H,
                  json={"amount": 5_000_000, "method": "transfer", "note": "repro"})
    b = requests.post(f"{BASE}/deals/{deal['id']}/book", headers=H, json={"note": "repro"}).json()
    if "data" not in b:
        print("BOOK GAGAL:", b)
    for _ in range(20):
        h = requests.get(f"{BASE}/health").json()
        if not h.get("events_pending"):
            break
        time.sleep(1)
    ar = requests.get(f"{BASE}/finance/ar", headers=H, params={"deal_id": deal["id"]}).json()
    ar = next((a for a in (ar.get("data") or []) if a.get("deal_id") == deal["id"]), None) or {}
    print("AR scheme      :", ar.get("scheme_name"), "| items:", [(i["label"], i["amount"]) for i in ar.get("items") or []])
    conv = requests.post(f"{BASE}/deals/{deal['id']}/convert", headers=H, json={}).json()
    contract = (conv.get("data") or {}).get("contract") or {}
    print("contract.scheme:", contract.get("scheme"), "| payment_scheme_id:", contract.get("payment_scheme_id"))
    avail = requests.get(f"{BASE}/contracts/{contract['id']}/documents/available", headers=H).json()
    for a in avail.get("data") or []:
        print("  template", a["code"], "can:", a["can_generate"], [b["code"] for b in a["blocks"]])
    code = {"cash_keras": "SPR_CASH", "cash_bertahap": "SPR_CASH_STAGED", "kpr": "SPR_KPR"}[kind]
    doc = requests.post(f"{BASE}/contracts/{contract['id']}/documents", headers=H,
                        json={"template_code": code}).json()
    if "data" in doc:
        content = doc["data"]["content"]
        m = re.search(r"Uang Muka : .*", content)
        print("SPR DP line    :", m.group(0) if m else None)
        i = content.find("3. Skema Pembayaran")
        print(content[i:i + 900])
        j = content.find("2. Rincian Harga")
        print(content[j:i])
    else:
        print("DOC GAGAL:", doc.get("detail"))
    print("deal.pricing.payment_breakdown:")
    for r in ((deal.get("pricing") or {}).get("payment_breakdown") or {}).get("rows") or []:
        print("  ", r["code"], r["amount"])
    print("deal.costs.components:", [(c["code"], c["amount"], c["treatment"]) for c in (deal.get("costs") or {}).get("components") or []])
    if not keep:
        r = requests.delete(f"{BASE}/deals/{deal['id']}", headers=H,
                            params={"reason": "repro selesai — deal uji dihapus paksa"})
        print("cleanup:", r.status_code)
    return 0


if __name__ == "__main__":
    sys.exit(main(keep="--keep" in sys.argv,
                  kind=next((a.split("=")[1] for a in sys.argv if a.startswith("--kind=")), "cash_bertahap")))
