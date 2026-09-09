#!/usr/bin/env python3
"""_fixture50.py — bahan uji BUATAN SENDIRI untuk POC & gate Fase 50.

Mengulang pelajaran `_fixture47/48/49`:

1. **Jangan menumpang data demo.** Serah terima MENGUBAH keadaan global rumah
   (`units.status = handed_over`) dan memulai masa garansi. Kalau POC menumpang unit demo,
   gate berikutnya merah bukan karena kode salah tetapi karena rumahnya sudah diserahkan.
   Karena itu POC membuat proyek + rumah sendiri (bertanda `gate50`) lalu membuangnya.
2. **Buang dokumen berarti buang anaknya.** BAST melahirkan klaim, klaim melahirkan punch
   item + tugas. `purge()` mengumpulkan id lebih dulu, lalu membuang turunannya;
   `orphans()` MEMBUKTIKAN tidak ada sisa menggantung.
3. **Bukti foto harus foto sungguhan.** Bukti perbaikan diunggah lewat `POST /files/upload`
   (PNG 1×1 asli), bukan id karangan — kalau tidak, "wajib ada bukti" hanya berlaku di
   pengujian dan bocor di kenyataan.
"""
import io
import os
import pathlib
import struct
import uuid
import zlib
from datetime import datetime, timedelta, timezone

import requests
from dotenv import load_dotenv
from pymongo import MongoClient

import _purge_cascade as _cascade

ROOT = pathlib.Path(__file__).resolve().parent.parent
load_dotenv(ROOT / "backend" / ".env")
BASE = "http://localhost:8001/api"
PW = "Sipro#2026"
TAG = "gate50"
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
ORG = os.environ.get("DEFAULT_ORG_ID", "org-sipro")
STAFF = ("pm@sipro.co.id", "site@sipro.co.id", "finance@sipro.co.id",
         "finlead@sipro.co.id", "owner@sipro.co.id", "superadmin@sipro.co.id",
         "manager@sipro.co.id", "marketing@sipro.co.id", "sales@sipro.co.id")


# --------------------------------------------------------------------- dasar
def login(email: str) -> dict:
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": PW}, timeout=25)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def new_id() -> str:
    return str(uuid.uuid4())


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def days_ago(n: int) -> str:
    return (datetime.now(timezone.utc).date() - timedelta(days=n)).isoformat()


def api(method: str, path: str, headers: dict, **kw):
    return requests.request(method, f"{BASE}{path}", headers=headers, timeout=60, **kw)


def png_bytes() -> bytes:
    """PNG 1×1 yang sah (dibangun manual supaya tidak butuh Pillow di sisi penguji)."""
    def chunk(kind: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + kind + data
                + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF))
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    raw = zlib.compress(b"\x00\xff\xff\xff")
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", raw)
            + chunk(b"IEND", b""))


def upload_photo(headers: dict, name: str = "bukti-gate50.png") -> str:
    """Unggah foto NYATA dan kembalikan file_id (bukti perbaikan garansi)."""
    files = {"file": (name, io.BytesIO(png_bytes()), "image/png")}
    r = requests.post(f"{BASE}/files/upload", headers=headers, files=files,
                      data={"owner_type": "build", "optimize": "false"}, timeout=60)
    r.raise_for_status()
    return r.json()["data"]["id"]


# ------------------------------------------------------------ bahan uji utama
def make_project(name: str = "Proyek Uji Fase 50", code: str = "GATE50") -> dict:
    ts = now_iso()
    proj = {"id": new_id(), "org_id": ORG, "name": name, "code": code,
            "location": "Lokasi uji Fase 50", "status": "active", "members": list(STAFF),
            "construction_progress": 0, TAG: True, "created_by": TAG,
            "created_at": ts, "updated_at": ts}
    db.projects.insert_one(dict(proj))
    proj.pop("_id", None)
    return proj


def make_unit(project: dict, code: str, *, progress: int = 0,
              construction_status: str = "in_progress", price: int = 700_000_000) -> dict:
    ts = now_iso()
    unit = {"id": new_id(), "org_id": ORG, "project_id": project["id"], "code": code,
            "type": "Tipe Uji 45/90", "price": price, "status": "sold",
            "construction_status": construction_status, "construction_progress": progress,
            "payment_status": "none", "reserved_by_deal": None, "booked_by_deal": None,
            TAG: True, "created_at": ts, "updated_at": ts}
    db.units.insert_one(dict(unit))
    unit.pop("_id", None)
    return unit


def make_schedule(unit: dict, progress: int) -> dict:
    ts = now_iso()
    doc = {"id": new_id(), "org_id": ORG, "unit_id": unit["id"], "unit_code": unit["code"],
           "project_id": unit["project_id"], "template_code": None, "progress": progress,
           "status": "done" if progress >= 100 else "in_progress", TAG: True,
           "created_at": ts, "updated_at": ts}
    db.build_schedules.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


def make_buyer(unit: dict, name: str, *, outstanding: int = 0) -> dict:
    """Lead + deal + customer + tagihan AR (lunas bila outstanding=0)."""
    ts = now_iso()
    lead = {"id": new_id(), "org_id": ORG, "name": name,
            "phone": f"+6281{str(uuid.uuid4().int)[:9]}", "source": "walk_in",
            "stage": "booking", TAG: True, "created_at": ts, "updated_at": ts}
    db.leads.insert_one(dict(lead))
    deal = {"id": new_id(), "org_id": ORG, "lead_id": lead["id"], "unit_id": unit["id"],
            "project_id": unit["project_id"], "assigned_to": "sales@sipro.co.id",
            "status": "sold", "price": unit["price"], "booking_fee": 5_000_000,
            "booked_at": ts, TAG: True, "created_by": TAG, "created_at": ts, "updated_at": ts}
    db.deals.insert_one(dict(deal))
    cust = {"id": new_id(), "org_id": ORG, "lead_id": lead["id"], "deal_id": deal["id"],
            "name": name, "phone": lead["phone"], "nik": None, TAG: True,
            "created_at": ts, "updated_at": ts}
    db.customers.insert_one(dict(cust))
    total = unit["price"]
    paid = total - int(outstanding)
    inv = {"id": new_id(), "org_id": ORG, "deal_id": deal["id"], "unit_id": unit["id"],
           "price": total, "total": total, "paid": paid, "outstanding": int(outstanding),
           "status": "paid" if outstanding <= 0 else "partial",
           "items": [{"label": "Uji Fase 50", "amount": total, "paid": paid,
                      "due_date": today()}],
           TAG: True, "created_at": ts, "updated_at": ts}
    db.ar_invoices.insert_one(dict(inv))
    db.units.update_one({"id": unit["id"]}, {"$set": {
        "sold_by_deal": deal["id"], "deal_id": deal["id"], "lead_id": lead["id"],
        "customer_id": cust["id"], "payment_status": "lunas" if outstanding <= 0 else "cicil",
        "updated_at": ts}})
    for k in ("_id",):
        lead.pop(k, None); deal.pop(k, None); cust.pop(k, None); inv.pop(k, None)
    return {"lead": lead, "deal": deal, "customer": cust, "invoice": inv}


def make_punch(unit: dict, title: str, status: str = "open") -> dict:
    ts = now_iso()
    doc = {"id": new_id(), "org_id": ORG, "project_id": unit["project_id"],
           "unit_id": unit["id"], "title": title, "description": "Temuan uji Fase 50",
           "category": "lainnya", "severity": "medium", "status": status,
           "assigned_to": "site@sipro.co.id", "photos": [], "fix_photos": [],
           "opened_by": TAG, TAG: True, "created_at": ts, "updated_at": ts}
    db.punch_items.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


def make_inspection(unit: dict, status: str = "passed") -> dict:
    """Inspeksi kategori `handover` yang sudah difinalisasi (lulus/gagal)."""
    ts = now_iso()
    doc = {"id": new_id(), "org_id": ORG, "project_id": unit["project_id"],
           "unit_id": unit["id"], "inspection_number": f"QC/GATE50/{str(uuid.uuid4())[:4]}",
           "category": "handover", "title": "Inspeksi serah terima (uji)",
           "items": [{"key": "atap", "label": "Atap tidak bocor",
                      "result": "pass" if status == "passed" else "fail", "note": None}],
           "status": status, "pass_count": 1 if status == "passed" else 0,
           "fail_count": 0 if status == "passed" else 1, "punch_ids": [],
           "punch_created": False, "finalized_by": TAG, "finalized_at": ts,
           TAG: True, "created_at": ts, "updated_at": ts}
    db.inspections.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


def make_worker(project: dict, name: str = "Tukang Uji Fase 50") -> dict:
    """Tenaga kerja harian untuk menguji absensi lewat antrean perangkat (Fase 50B)."""
    ts = now_iso()
    doc = {"id": new_id(), "org_id": ORG, "name": f"{name} {str(uuid.uuid4())[:4]}",
           "role": "tukang", "role_label": "Tukang", "daily_wage": 180_000,
           "phone": None, "subcon_id": None, "project_ids": [project["id"]],
           "note": "Tenaga kerja uji Fase 50.", "is_active": True, "created_by": TAG,
           TAG: True, "created_at": ts, "updated_at": ts}
    db.workers.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


def ready_unit(project: dict, code: str, buyer_name: str) -> dict:
    """Rumah yang BENAR-BENAR siap diserahterimakan (semua pemeriksaan bersih)."""
    unit = make_unit(project, code, progress=100, construction_status="done")
    make_schedule(unit, 100)
    make_punch(unit, "Cat tembok belakang (sudah diperbaiki)", status="closed")
    make_inspection(unit, "passed")
    buyer = make_buyer(unit, buyer_name, outstanding=0)
    return {"unit": unit, "buyer": buyer}


def blocked_unit(project: dict, code: str, buyer_name: str) -> dict:
    """Rumah yang MASIH ada pekerjaan & kewajiban — serah terima harus ditahan."""
    unit = make_unit(project, code, progress=70, construction_status="in_progress")
    make_schedule(unit, 70)
    make_punch(unit, "Keramik kamar mandi pecah", status="open")
    make_punch(unit, "Kusen jendela belum dipasang", status="in_progress")
    buyer = make_buyer(unit, buyer_name, outstanding=120_000_000)
    return {"unit": unit, "buyer": buyer}


# ---------------------------------------------------------------- pembersihan
def _ids(coll: str, q: dict) -> list:
    return [d["id"] for d in db[coll].find(q, {"_id": 0, "id": 1})]


def purge() -> dict:
    """Buang SELURUH bahan uji beserta turunannya (BAST, klaim, punch, tugas, berkas)."""
    units = _ids("units", {TAG: True})
    projects = _ids("projects", {TAG: True})
    # Pembeli uji dikumpulkan LEBIH DULU: login portal (OTP) melahirkan baris `portal_users`
    # yang menunjuk pelanggan itu. Kalau pelanggannya dibuang tanpa membuang akun portalnya,
    # yang tertinggal adalah akun portal YATIM — dan audit forensik menandainya CRITICAL
    # ("portal_users -> customer_id tidak ada di customers"). Cacat ini nyata: POC Fase 50
    # sempat mengaku "bahan uji dibuang bersih" padahal meninggalkan satu akun portal.
    customers = _ids("customers", {TAG: True})
    # Transaksi uji dikumpulkan LEBIH DULU supaya turunannya (catatan pajak, komisi, fee)
    # bisa dibuang sebelum induknya hilang. `_fixture47` sudah memakai pola ini; `_fixture50`
    # melupakannya sehingga setiap run gate 39/40 meninggalkan `tax_records` yatim —
    # angka PPN/BPHTB dari rumah uji yang sudah dibuang, dan audit forensik menandainya
    # CRITICAL begitu ia dijalankan SESUDAH gate 39/40 (di run_all_gates ia jalan lebih awal,
    # jadi cacat ini selalu lolos).
    deals = _ids("deals", {TAG: True})
    _cascade.purge_deal_children(db, deals, _ids("leads", {TAG: True}))
    handovers = _ids("unit_handovers", {"$or": [{"unit_id": {"$in": units}},
                                                {"project_id": {"$in": projects}}]})
    claims = _ids("warranty_claims", {"$or": [{"unit_id": {"$in": units}},
                                              {"handover_id": {"$in": handovers}}]})
    punches = _ids("punch_items", {"$or": [{TAG: True}, {"unit_id": {"$in": units}},
                                           {"warranty_claim_id": {"$in": claims}}]})
    counts = {
        "unit_handovers": db.unit_handovers.delete_many({"id": {"$in": handovers}}).deleted_count,
        "warranty_claims": db.warranty_claims.delete_many({"id": {"$in": claims}}).deleted_count,
        "punch_items": db.punch_items.delete_many({"id": {"$in": punches}}).deleted_count,
        "tasks": db.tasks.delete_many({"$or": [
            {"related_entity_type": "unit_handover", "related_entity_id": {"$in": handovers}},
            {"related_entity_type": "warranty_claim", "related_entity_id": {"$in": claims}},
            {"related_entity_type": "punch_item", "related_entity_id": {"$in": punches}},
        ]}).deleted_count,
        "inspections": db.inspections.delete_many({TAG: True}).deleted_count,
        "build_schedules": db.build_schedules.delete_many({TAG: True}).deleted_count,
        "ar_invoices": db.ar_invoices.delete_many({TAG: True}).deleted_count,
        "site_diaries": db.site_diaries.delete_many({"project_id": {"$in": projects}}).deleted_count,
        "labor_attendance": db.labor_attendance.delete_many(
            {"project_id": {"$in": projects}}).deleted_count,
        "workers": db.workers.delete_many({TAG: True}).deleted_count,
        "portal_users": db.portal_users.delete_many(
            {"customer_id": {"$in": customers}}).deleted_count,
        "portal_otps": db.portal_otps.delete_many(
            {"customer_id": {"$in": customers}}).deleted_count,
        "customers": db.customers.delete_many({TAG: True}).deleted_count,
        "deals": db.deals.delete_many({TAG: True}).deleted_count,
        "tax_records": db.tax_records.delete_many({"deal_id": {"$in": deals}}).deleted_count,
        "commissions": db.commissions.delete_many({"deal_id": {"$in": deals}}).deleted_count,
        "marketing_fees": db.marketing_fees.delete_many(
            {"deal_id": {"$in": deals}}).deleted_count,
        "contract_liabilities": db.contract_liabilities.delete_many(
            {"deal_id": {"$in": deals}}).deleted_count,
        "receipts": db.receipts.delete_many({"deal_id": {"$in": deals}}).deleted_count,
        "leads": db.leads.delete_many({TAG: True}).deleted_count,
        "units": db.units.delete_many({TAG: True}).deleted_count,
        "projects": db.projects.delete_many({TAG: True}).deleted_count,
        "activities": db.activities.delete_many(
            {"$or": [{"entity_id": {"$in": units}}, {"entity_id": {"$in": projects}}]}).deleted_count,
        "offline_intake": db.offline_intake.delete_many(
            {"client_ref": {"$regex": f"^{TAG}"}}).deleted_count,
        "counters": 0,
    }
    return counts


def orphans() -> dict:
    """Buktikan tidak ada sisa menggantung setelah pembersihan."""
    units = set(_ids("units", {}))
    handovers = {d["id"]: d for d in db.unit_handovers.find({}, {"_id": 0, "id": 1,
                                                                "unit_id": 1})}
    return {
        "bast_tanpa_unit": sum(1 for h in handovers.values()
                               if h.get("unit_id") not in units),
        "klaim_tanpa_bast": db.warranty_claims.count_documents(
            {"handover_id": {"$nin": list(handovers.keys())}}),
        "punch_garansi_tanpa_klaim": sum(
            1 for p in db.punch_items.find({"source": "warranty_claim"},
                                            {"_id": 0, "warranty_claim_id": 1})
            if not db.warranty_claims.count_documents({"id": p.get("warranty_claim_id")})),
        "unit_uji_tersisa": db.units.count_documents({TAG: True}),
        "proyek_uji_tersisa": db.projects.count_documents({TAG: True}),
        # Akun portal YATIM = pelanggan uji sudah dibuang tetapi akun portalnya tertinggal.
        # Dulu tidak diperiksa, sehingga POC bisa mengaku bersih sambil meninggalkan temuan
        # CRITICAL di `forensic_audit.py` (integritas referensial portal_users → customers).
        "akun_portal_yatim": sum(
            1 for p in db.portal_users.find({}, {"_id": 0, "customer_id": 1})
            if p.get("customer_id")
            and not db.customers.count_documents({"id": p["customer_id"]})),
    }
