#!/usr/bin/env python3
"""_fixture47.py — bahan uji BUATAN SENDIRI untuk gate Fase 47 (dipakai 3 gate + uji-mutasi).

Pelajaran mahal Fase 46 & 47 yang dikodekan di sini:

  1. **Gate tidak boleh menumpang data seed.** Begitu satu gate mencocokkan termin milik
     pelanggan demo, data itu habis dan gate berikutnya MERAH karena kehabisan bahan — bukan
     karena kodenya salah (dulu ini membuat hasil uji-mutasi hijau/merah palsu).
  2. **Membuang dokumen tanpa membuang jurnalnya = buku besar berisi angka tanpa dokumen.**
     Itu yang dulu membuat tie-out 2-1400 (Uang Muka) merah dan penyebabnya tampak seperti
     cacat aplikasi. Karena itu `purge` mengumpulkan id kuitansi/rekap LEBIH DULU lalu
     menghapus jurnal yang menunjuknya, dan `orphans` MEMBUKTIKAN tidak ada sisa menggantung.

Semua dokumen bertanda `gate47=True` sehingga bisa dikenali dan dibuang kapan saja.
"""
import os
import pathlib
import uuid

import requests
from dotenv import load_dotenv
from pymongo import MongoClient

import _purge_cascade as _cascade

ROOT = pathlib.Path(__file__).resolve().parent.parent
load_dotenv(ROOT / "backend" / ".env")
BASE = "http://localhost:8001/api"
PW = "Sipro#2026"
TAG = "gate47"
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
ORG = os.environ.get("DEFAULT_ORG_ID", "org-sipro")


def login(email: str) -> dict:
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": PW}, timeout=25)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def new_id() -> str:
    return str(uuid.uuid4())


def now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def make_unit(code: str, price: int = 500_000_000) -> dict:
    """Unit sementara yang MEWARISI atribut unit nyata (blok/cluster/tipe) agar sah dipakai."""
    src = db.units.find_one({"org_id": ORG, "block_id": {"$ne": None}}, {"_id": 0})
    project = db.projects.find_one({"org_id": ORG}, {"_id": 0})
    ts = now_iso()
    unit = {"id": new_id(), "org_id": ORG, "project_id": project["id"], "code": code,
            "type": src.get("type"), "unit_type_code": src.get("unit_type_code"),
            "unit_type_id": src.get("unit_type_id"), "price": price,
            "status": "available", "construction_status": "not_started",
            "construction_progress": 0, "payment_status": "none",
            "block": src.get("block"), "block_id": src.get("block_id"),
            "cluster_code": src.get("cluster_code"), "cluster_id": src.get("cluster_id"),
            TAG: True, "created_at": ts, "updated_at": ts}
    db.units.insert_one(dict(unit))
    unit.pop("_id", None)
    return {"unit": unit, "project": project}


def make_lead(name: str, phone: str) -> dict:
    ts = now_iso()
    lead = {"id": new_id(), "org_id": ORG, "name": name, "phone": phone,
            "email": f"{phone.strip('+')}@example.test", "status": "hot",
            "stage": "negotiation", "source": "walk_in",
            "assigned_to": "sales@sipro.co.id", TAG: True,
            "created_at": ts, "updated_at": ts}
    db.leads.insert_one(dict(lead))
    lead.pop("_id", None)
    return lead


def make_customer(lead: dict) -> dict:
    ts = now_iso()
    cust = {"id": new_id(), "org_id": ORG, "lead_id": lead["id"], "name": lead["name"],
            "phone": lead["phone"], "email": lead["email"], "kyc_status": "verified",
            TAG: True, "created_at": ts, "updated_at": ts}
    db.customers.insert_one(dict(cust))
    cust.pop("_id", None)
    return cust


def booked_deal(code: str, phone: str, name: str, headers: dict) -> dict:
    """Unit + lead + customer + deal BOOKED lewat API resmi (jadwal AR ikut terbentuk).

    Memakai jalur resmi (`/deals/reserve` + `/deals/{id}/book`) penting: jadwal AR yang diuji
    harus lahir dari mesin yang sama dengan produksi, bukan dokumen karangan gate.
    """
    made = make_unit(code)
    lead = make_lead(name, phone)
    cust = make_customer(lead)
    r = requests.post(f"{BASE}/deals/reserve", headers=headers, timeout=30, json={
        "lead_id": lead["id"], "unit_id": made["unit"]["id"], "booking_fee": 1_000_000,
        "notes": f"{TAG} — bahan uji gate Fase 47"})
    if not r.ok:
        raise RuntimeError(f"reserve gagal: {r.status_code} {r.text[:200]}")
    deal = r.json()["data"]
    requests.post(f"{BASE}/booking-fee/deals/{deal['id']}/pay", headers=login("superadmin@sipro.co.id"),
                  timeout=30, json={"amount": 1_000_000, "method": "transfer"})
    b = requests.post(f"{BASE}/deals/{deal['id']}/book", headers=headers, timeout=30,
                      json={"note": f"{TAG} book"})
    if not b.ok:
        raise RuntimeError(f"book gagal: {b.status_code} {b.text[:200]}")
    inv = requests.get(f"{BASE}/finance/ar/{deal['id']}", headers=headers, timeout=30)
    return {"unit": made["unit"], "project": made["project"], "lead": lead,
            "customer": cust, "deal": deal,
            "invoice": inv.json().get("data") if inv.ok else None}


def outstanding(deal_id: str, headers: dict) -> int:
    r = requests.get(f"{BASE}/finance/ar/{deal_id}", headers=headers, timeout=25)
    return int((r.json().get("data") or {}).get("outstanding") or 0) if r.ok else -1


def first_unpaid(invoice: dict) -> dict:
    items = [i for i in (invoice or {}).get("items", []) if i.get("status") != "paid"]
    return sorted(items, key=lambda x: x.get("due_date") or "")[0] if items else {}


def settle(timeout: int = 45) -> bool:
    """Tunggu sampai TIDAK ada event tertunda \u2014 jurnal GL lahir dari event, bukan seketika.

    Cacat nyata yang ditutup: `emit()` hanya MENITIPKAN event ke koleksi `events`; jurnal
    baru terbentuk saat penjadwal (tiap ~8 detik) memanggil `dispatch_pending`. Gate yang
    langsung memeriksa jurnal setelah panggilan API karena itu bisa MERAH tanpa sebab, dan
    gate yang langsung membuang bahan ujinya meninggalkan JURNAL MENGGANTUNG (jurnal lahir
    setelah dokumennya dihapus) — tepat penyebab tie-out 2-1400 merah pada Fase 47.
    """
    import time
    for _ in range(timeout):
        if db.events.count_documents({"status": "pending"}) == 0:
            time.sleep(1.5)
            if db.events.count_documents({"status": "pending"}) == 0:
                return True
        time.sleep(1)
    return False


def wait_journal(source_id: str, source_type: str = None, timeout: int = 40) -> dict:
    """Jurnal yang menunjuk dokumen tertentu, setelah event-nya benar-benar diproses."""
    import time
    q = {"source_id": source_id}
    if source_type:
        q["source_type"] = source_type
    for _ in range(timeout):
        je = db.journal_entries.find_one(q, {"_id": 0})
        if je:
            return je
        time.sleep(1)
    return None


def purge():
    """Buang SEMUA bahan uji gate 47 beserta jejak keuangannya."""
    settle()
    units = [u["id"] for u in db.units.find({TAG: True}, {"_id": 0, "id": 1})]
    leads = [x["id"] for x in db.leads.find({TAG: True}, {"_id": 0, "id": 1})]
    deals = [d["id"] for d in db.deals.find(
        {"$or": [{TAG: True}, {"lead_id": {"$in": leads}}, {"unit_id": {"$in": units}}]},
        {"_id": 0, "id": 1})]
    workers = [w["id"] for w in db.workers.find({TAG: True}, {"_id": 0, "id": 1})]
    _cascade.purge_deal_children(db, deals, leads)
    accounts = [a["id"] for a in db.bank_accounts.find({TAG: True}, {"_id": 0, "id": 1})]
    txns = [t["id"] for t in db.bank_transactions.find(
        {"$or": [{TAG: True}, {"account_id": {"$in": accounts}}]}, {"_id": 0, "id": 1})]
    receipts = [r["id"] for r in db.receipts.find({"deal_id": {"$in": deals}},
                                                  {"_id": 0, "id": 1})]
    payrolls = [p["id"] for p in db.labor_payrolls.find({TAG: True}, {"_id": 0, "id": 1})]
    intakes = [i["id"] for i in db.payment_intakes.find(
        {"$or": [{TAG: True}, {"deal_id": {"$in": deals}}]}, {"_id": 0, "id": 1})]
    for coll, q in (
        ("bank_matches", {"txn_id": {"$in": txns}}),
        ("bank_transactions", {"id": {"$in": txns}}),
        ("bank_statements", {"account_id": {"$in": accounts}}),
        ("bank_accounts", {"id": {"$in": accounts}}),
        ("payment_intakes", {"id": {"$in": intakes}}),
        ("files", {"owner_id": {"$in": deals}, "owner_type": "payment_proof"}),
        ("labor_attendance", {"worker_id": {"$in": workers}}),
        ("labor_payrolls", {"id": {"$in": payrolls}}),
        ("workers", {"id": {"$in": workers}}),
        ("quotations", {"$or": [{TAG: True}, {"lead_id": {"$in": leads}}]}),
        ("ar_invoices", {"deal_id": {"$in": deals}}),
        ("contracts", {"deal_id": {"$in": deals}}),
        ("receipts", {"deal_id": {"$in": deals}}),
        ("contract_liabilities", {"deal_id": {"$in": deals}}),
        ("customer_deposits", {"deal_id": {"$in": deals}}),
        ("tax_records", {"deal_id": {"$in": deals}}),
        ("marketing_fees", {"deal_id": {"$in": deals}}),
        ("commissions", {"deal_id": {"$in": deals}}),
        ("journal_entries", {"source_id": {"$in": receipts + payrolls + txns + deals}}),
        # Notifikasi milik bahan uji ikut dibuang: pemberitahuan yang menunjuk rekap upah
        # yang sudah tidak ada (atau ke pengguna semu POC) membuat gate integritas data
        # MERAH tanpa sebab nyata — cacat yang benar-benar terjadi setelah POC dijalankan.
        ("notifications", {"$or": [{"related_entity_id": {"$in": payrolls}},
                                   {"user_email": {"$in": ["poc_47", "gate47", "poc48"]}}]}),
        ("activities", {"$or": [{"entity_id": {"$in": deals + units + leads}},
                                # Jejak aktivitas milik pengguna semu POC ikut dibuang:
                                # audit forensik (benar) menuntut setiap aktor adalah
                                # pengguna terdaftar.
                                {"actor": {"$regex": "^(poc4|gate4)"}}]}),
        ("tasks", {"entity_id": {"$in": deals + leads}}),
        ("portal_users", {"customer_id": {"$in": [
            c["id"] for c in db.customers.find({TAG: True}, {"_id": 0, "id": 1})]}}),
        ("customers", {TAG: True}),
        ("deals", {"id": {"$in": deals}}),
        ("leads", {"id": {"$in": leads}}),
        ("units", {"id": {"$in": units}}),
    ):
        db[coll].delete_many(q)
    live = [p["id"] for p in db.labor_payrolls.find({}, {"_id": 0, "id": 1})]
    db.labor_attendance.update_many({"payroll_id": {"$nin": live + [None]}},
                                    {"$set": {"payroll_id": None}})


def orphans() -> dict:
    """Sisa yang MENGGANTUNG — diukur dari kenyataan, bukan dari tanda gate."""
    acc_ids = {a["id"] for a in db.bank_accounts.find({}, {"_id": 0, "id": 1})}
    rec_ids = {r["id"] for r in db.receipts.find({}, {"_id": 0, "id": 1})}
    return {
        "unit": db.units.count_documents({TAG: True}),
        "deal": db.deals.count_documents({TAG: True}),
        "worker": db.workers.count_documents({TAG: True}),
        "txn_tanpa_rekening": sum(
            1 for t in db.bank_transactions.find({}, {"_id": 0, "account_id": 1})
            if t.get("account_id") not in acc_ids),
        "jurnal_tanpa_kuitansi": sum(
            1 for j in db.journal_entries.find({"source_type": "receipt"},
                                               {"_id": 0, "source_id": 1})
            if j.get("source_id") not in rec_ids),
    }
