#!/usr/bin/env python3
"""_fixture49.py — bahan uji BUATAN SENDIRI untuk POC & gate Fase 49.

Mengulang pelajaran `_fixture47/_fixture48`:

1. **Jangan menumpang data seed.** Penutupan buku & pajak MENGUBAH keadaan global (periode
   tertutup, tahun buku, nomor faktur/bukti potong). Kalau POC menumpang bulan berjalan milik
   demo, gate berikutnya merah bukan karena kode salah tetapi karena bulannya sudah tertutup.
   Karena itu seluruh uji penutupan memakai **tahun 2024** yang di database demo TIDAK punya
   satu jurnal pun (jurnal demo hidup di 2026-05..2026-08).
2. **Buang dokumen berarti buang jurnalnya.** Tutup tahun, pembayaran, dan potongan pajak
   semuanya berjurnal. `purge()` mengumpulkan id lebih dulu, lalu menghapus jurnal yang
   menunjuknya; `orphans()` MEMBUKTIKAN tidak ada sisa menggantung.
3. **Setelan yang diubah harus dipulihkan.** POC mengisi NPWP perusahaan supaya ekspor bisa
   diuji; nilai lamanya disimpan dan dikembalikan pada saat pembersihan.
"""
import os
import pathlib
import time
import uuid
from datetime import datetime, timedelta, timezone

import requests
from dotenv import load_dotenv
from pymongo import MongoClient

ROOT = pathlib.Path(__file__).resolve().parent.parent
load_dotenv(ROOT / "backend" / ".env")
BASE = "http://localhost:8001/api"
PW = "Sipro#2026"
TAG = "gate49"
MEMO_TAG = "POC49"
# Tahun & bulan uji: kosong di data demo, jadi penutupan tidak menyentuh bulan berjalan.
YEAR = "2024"
PERIOD = "2024-05"
JE_DATE = f"{PERIOD}-10T03:00:00+00:00"
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
ORG = os.environ.get("DEFAULT_ORG_ID", "org-sipro")
STAFF = ("pm@sipro.co.id", "site@sipro.co.id", "finance@sipro.co.id",
         "finlead@sipro.co.id", "owner@sipro.co.id", "superadmin@sipro.co.id")


def login(email: str) -> dict:
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": PW}, timeout=25)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def new_id() -> str:
    return str(uuid.uuid4())


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def day(offset: int) -> str:
    return (datetime.now(timezone.utc).date() + timedelta(days=offset)).isoformat()


def this_period() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def api(method: str, path: str, headers: dict, **kw):
    return requests.request(method, f"{BASE}{path}", headers=headers, timeout=60, **kw)


def make_project(name: str, code: str) -> dict:
    ts = now_iso()
    proj = {"id": new_id(), "org_id": ORG, "name": name, "code": code,
            "location": "Lokasi uji Fase 49", "status": "active", "members": list(STAFF),
            "construction_progress": 0, TAG: True, "created_by": "gate49",
            "created_at": ts, "updated_at": ts}
    db.projects.insert_one(dict(proj))
    proj.pop("_id", None)
    return proj


def make_bank_txn(date: str, amount: int, description: str) -> dict:
    """Mutasi bank BELUM dicocokkan — bahan uji "daftar periksa MENAHAN penutupan"."""
    account = db.bank_accounts.find_one({"org_id": ORG}, {"_id": 0, "id": 1}) or {}
    ts = now_iso()
    doc = {"id": new_id(), "org_id": ORG, "account_id": account.get("id"),
           "date": date, "amount": int(amount), "direction": "in" if amount > 0 else "out",
           "description": description, "reference": f"POC49/{str(uuid.uuid4())[:6]}",
           "balance_after": None, "match_state": "unmatched", "matched_ref_type": None,
           "matched_ref_id": None, "import_batch": "poc49", TAG: True,
           "created_at": ts, "updated_at": ts}
    db.bank_transactions.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


def journal(headers: dict, memo: str, lines: list, date: str = JE_DATE):
    """Jurnal manual lewat API resmi (menuntut seimbang & periode terbuka)."""
    return api("POST", "/gl/journals", headers,
               json={"memo": f"{MEMO_TAG} {memo}", "date": date, "lines": lines})


def account_balance(code: str) -> int:
    """Saldo (kredit − debit) satu akun dari jurnal NYATA di database."""
    dr = cr = 0
    for je in db.journal_entries.find({"org_id": ORG, "lines.account_code": code},
                                      {"_id": 0, "lines": 1}):
        for ln in je.get("lines", []):
            if ln.get("account_code") == code:
                dr += int(ln.get("debit", 0) or 0)
                cr += int(ln.get("credit", 0) or 0)
    return cr - dr


def settle(timeout: int = 45) -> bool:
    """Tunggu antrean event kosong — jurnal AP lahir dari event, bukan seketika."""
    for _ in range(timeout):
        if db.events.count_documents({"status": "pending"}) == 0:
            time.sleep(1.5)
            if db.events.count_documents({"status": "pending"}) == 0:
                return True
        time.sleep(1)
    return False


def wait_journal(source_id: str, source_type: str = None, timeout: int = 40) -> dict:
    q = {"source_id": source_id}
    if source_type:
        q["source_type"] = source_type
    for _ in range(timeout):
        je = db.journal_entries.find_one(q, {"_id": 0})
        if je:
            return je
        time.sleep(1)
    return None


def make_bill(headers: dict, vendor: str, project_id, claimed: int,
              retention_pct: float = 0) -> dict:
    """Tagihan AP lewat API + disetujui (jurnal lahir dari event yang sama dengan produksi)."""
    bill = api("POST", "/finance/ap/bills", headers, json={
        "vendor": vendor, "project_id": project_id, "claimed": int(claimed),
        "retention_pct": retention_pct, "due_date": day(30),
        "note": "Bahan uji Fase 49"}).json()["data"]
    db.ap_invoices.update_one({"id": bill["id"]}, {"$set": {TAG: True}})
    api("POST", f"/finance/ap/bills/{bill['id']}/approve", headers)
    wait_journal(bill["id"], "ap_bill")
    return bill


# ---------------------------------------------------------------- pembersihan
def purge():
    """Buang seluruh bahan uji Fase 49 beserta jejak keuangannya."""
    settle()
    projects = [p["id"] for p in db.projects.find({TAG: True}, {"_id": 0, "id": 1})]
    bills = [b["id"] for b in db.ap_invoices.find(
        {"$or": [{TAG: True}, {"project_id": {"$in": projects}}]}, {"_id": 0, "id": 1})]
    payments = [p["id"] for p in db.payments_out.find(
        {"bill_id": {"$in": bills}}, {"_id": 0, "id": 1})]
    bupots = [w["id"] for w in db.withholding_docs.find(
        {"$or": [{TAG: True}, {"ref_id": {"$in": payments + bills}},
                 {"issued_by": {"$regex": "@sipro"}}]}, {"_id": 0, "id": 1})]
    fakturs = [f["id"] for f in db.faktur_pajak.find({TAG: True}, {"_id": 0, "id": 1})]
    year_je = [j["id"] for j in db.journal_entries.find(
        {"org_id": ORG, "source_type": "year_closing", "source_id": YEAR},
        {"_id": 0, "id": 1})]
    for coll, q in (
        ("withholding_docs", {"id": {"$in": bupots}}),
        ("faktur_pajak", {"id": {"$in": fakturs}}),
        ("payments_out", {"id": {"$in": payments}}),
        ("ap_invoices", {"id": {"$in": bills}}),
        ("bank_transactions", {TAG: True}),
        ("journal_entries", {"$or": [{"id": {"$in": year_je}},
                                     {"source_id": {"$in": bills + payments}},
                                     {"memo": {"$regex": f"^{MEMO_TAG}"}},
                                     {"date": {"$gte": f"{YEAR}-01-01",
                                               "$lt": f"{int(YEAR) + 1}-01-01"}}]}),
        ("gl_year_closings", {"org_id": ORG, "year": YEAR}),
        ("accounting_periods", {"org_id": ORG, "period": PERIOD}),
        ("tasks", {"$or": [{"related_entity_id": {"$in": [PERIOD, YEAR] + bills}},
                           {"source_event": {"$regex": f":{PERIOD}$"}}]}),
        ("notifications", {"related_entity_id": {"$in": [PERIOD, YEAR] + bills}}),
        ("events", {"entity_id": {"$in": bills}}),
        ("audit_logs", {"entity_id": {"$in": [PERIOD, YEAR] + bills + bupots + fakturs}}),
        ("activities", {"entity_id": {"$in": projects + bills}}),
        ("projects", {"id": {"$in": projects}}),
    ):
        db[coll].delete_many(q)


def orphans() -> dict:
    """Sisa menggantung — diukur dari kenyataan, bukan dari tanda gate."""
    payment_ids = {p["id"] for p in db.payments_out.find({}, {"_id": 0, "id": 1})}
    fee_ids = {f["id"] for f in db.marketing_fees.find({}, {"_id": 0, "id": 1})}
    bill_ids = {b["id"] for b in db.ap_invoices.find({}, {"_id": 0, "id": 1})}
    return {
        "projects": db.projects.count_documents({TAG: True}),
        "tagihan_uji": db.ap_invoices.count_documents({TAG: True}),
        "mutasi_bank_uji": db.bank_transactions.count_documents({TAG: True}),
        "faktur_uji": db.faktur_pajak.count_documents({TAG: True}),
        "jurnal_poc": db.journal_entries.count_documents({"memo": {"$regex": f"^{MEMO_TAG}"}}),
        f"jurnal_{YEAR}": db.journal_entries.count_documents(
            {"org_id": ORG, "date": {"$gte": f"{YEAR}-01-01", "$lt": f"{int(YEAR) + 1}-01-01"}}),
        "tutup_tahun_uji": db.gl_year_closings.count_documents({"org_id": ORG, "year": YEAR}),
        "periode_uji": db.accounting_periods.count_documents({"org_id": ORG, "period": PERIOD}),
        "bupot_tanpa_sumber": sum(
            1 for w in db.withholding_docs.find({}, {"_id": 0, "basis": 1, "ref_id": 1})
            if w.get("basis") == "ap_payment" and w.get("ref_id") not in payment_ids
            or w.get("basis") == "partner_fee" and w.get("ref_id") not in fee_ids),
        "jurnal_ap_tanpa_tagihan": sum(
            1 for j in db.journal_entries.find({"source_type": "ap_bill"},
                                               {"_id": 0, "source_id": 1})
            if j.get("source_id") not in bill_ids),
    }
