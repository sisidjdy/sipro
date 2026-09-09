"""Verifikasi jurnal kuitansi UI (Fase 82): debit harus di sub-akun rekening terpilih."""
import os
import sys
import time

import requests

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
PASS = "Sipro#2026"
RID = sys.argv[1]
CODE = sys.argv[2] if len(sys.argv) > 2 else "1-1202"

tok = requests.post(f"{BASE}/api/auth/login",
                    json={"email": "finance@sipro.co.id", "password": PASS}).json()["access_token"]
s = requests.Session()
s.headers.update({"Authorization": f"Bearer {tok}"})

je = None
for _ in range(12):
    rows = s.get(f"{BASE}/api/gl/journals",
                 params={"source_type": "receipt", "source_id": RID}).json().get("data") or []
    if rows:
        je = rows[0]
        break
    time.sleep(2)
print("journal:", (je or {}).get("entry_no"))
assert je, "jurnal kuitansi tidak terbit dalam 24s"
for ln in je["lines"]:
    print("  ", ln["account_code"], ln["account_name"], ln.get("debit"), ln.get("credit"))
debits = {ln["account_code"] for ln in je["lines"] if int(ln.get("debit") or 0) > 0}
assert CODE in debits, f"debit tidak di {CODE}: {debits}"
assert not (debits & {"1-1100", "1-1200"}), "masih memakai akun induk"

acc = next(a for a in s.get(f"{BASE}/api/cash-bank/accounts").json()["data"]
           if a["gl_account_code"] == CODE)
book = s.get(f"{BASE}/api/cash-bank/book", params={
    "account_id": acc["id"], "date_from": "2026-01-01", "date_to": "2026-12-31"}).json()["data"]
hit = [ln for ln in book["lines"] if ln["journal_id"] == je["id"]]
print("baris di buku", acc["name"], ":", hit)
assert hit, "jurnal kuitansi tidak muncul di Buku Kas & Bank rekening"
print("OK")
