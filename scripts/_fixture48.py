#!/usr/bin/env python3
"""_fixture48.py — bahan uji BUATAN SENDIRI untuk POC & gate Fase 48.

Mengulang dua pelajaran mahal yang sudah dikodekan di `_fixture47.py`:

  1. **Jangan menumpang data seed.** Sekali gate memesan kekurangan permintaan material milik
     demo, bahan itu habis dan gate berikutnya MERAH karena kehabisan data — bukan karena
     kode salah. Semua bahan di sini dibuat sendiri lewat API/DB dan bertanda `gate48`.
  2. **Buang dokumen berarti buang jurnalnya.** Uang muka, tagihan termin, dan pencairan
     retensi SEMUANYA berjurnal. `purge()` mengumpulkan id-nya lebih dulu lalu menghapus
     jurnal yang menunjuknya; `orphans()` membuktikan tidak ada sisa menggantung.
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
TAG = "gate48"
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


def api(method: str, path: str, headers: dict, **kw):
    return requests.request(method, f"{BASE}{path}", headers=headers, timeout=40, **kw)


def make_project(name: str, code: str) -> dict:
    """Proyek uji dengan SEMUA peran demo sebagai anggota (supaya RBAC proyek tidak menghalangi)."""
    ts = now_iso()
    proj = {"id": new_id(), "org_id": ORG, "name": name, "code": code,
            "location": "Lokasi uji", "status": "active", "members": list(STAFF),
            "construction_progress": 0, TAG: True, "created_by": "gate48",
            "created_at": ts, "updated_at": ts}
    db.projects.insert_one(dict(proj))
    proj.pop("_id", None)
    return proj


def make_material(project_id: str, code: str, name: str, uom: str = "sak") -> dict:
    ts = now_iso()
    mat = {"id": new_id(), "org_id": ORG, "project_id": project_id, "code": code,
           "name": name, "uom": uom, "boq_item_id": None, "budget_qty": 0,
           "consumed_qty": 0, "over_budget": False, TAG: True,
           "created_at": ts, "updated_at": ts}
    db.materials.insert_one(dict(mat))
    mat.pop("_id", None)
    return mat


def make_requisition(project_id: str, project_name: str, items: list) -> dict:
    """Permintaan material berstatus DISETUJUI (bahan uji jalur permintaan→PO)."""
    ts = now_iso()
    doc = {"id": new_id(), "org_id": ORG, TAG: True,
           "req_number": f"PR/GATE48/{str(uuid.uuid4())[:6]}",
           "project_id": project_id, "project_name": project_name,
           "phase_id": None, "phase_name": None, "task_id": None,
           "purpose": "Bahan uji Fase 48", "items": items, "status": "approved",
           "requested_by": "site@sipro.co.id", "approved_by": "pm@sipro.co.id",
           "approved_at": ts, "issued_by": None, "issued_at": None,
           "rejected_by": None, "rejected_at": None, "note": None,
           "po_ids": [], "po_numbers": [], "created_at": ts, "updated_at": ts}
    db.material_requisitions.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


def req_item(mat: dict, qty: float) -> dict:
    return {"material_id": mat["id"], "code": mat["code"], "name": mat["name"],
            "uom": mat["uom"], "qty_requested": float(qty), "qty_issued": 0.0, "qty_po": 0.0}


def make_subcontractor(code: str, name: str) -> dict:
    ts = now_iso()
    doc = {"id": new_id(), "org_id": ORG, "code": code, "name": name,
           "specialty": "struktur", "phone": "+628123400048", "email": None,
           "npwp": None, "address": None, "pic_name": "Uji", "rating": None,
           "is_active": True, "notes": "bahan uji", TAG: True,
           "created_by": "gate48", "created_at": ts, "updated_at": ts}
    db.subcontractors.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


def make_spk(project: dict, sub: dict, value: int, *, retention_pct: float = 5,
             maintenance_days: int = 0, end_offset: int = -1) -> dict:
    ts = now_iso()
    doc = {"id": new_id(), "org_id": ORG, TAG: True,
           "spk_number": f"SPK/GATE48/{str(uuid.uuid4())[:6]}",
           "subcontractor_id": sub["id"], "subcontractor_name": sub["name"],
           "project_id": project["id"], "project_name": project["name"],
           "title": "Pekerjaan uji Fase 48", "scope": "struktur",
           "contract_value": int(value), "retention_pct": float(retention_pct),
           "maintenance_days": int(maintenance_days),
           "start_date": day(-30), "end_date": day(end_offset),
           "status": "active", "progress_pct": 0, "billed_pct": 0, "scope_mode": "lumpsum",
           "notes": "bahan uji", "created_by": "pm@sipro.co.id",
           "created_at": ts, "updated_at": ts}
    db.spk.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


def make_punch(project_id: str, unit_id: str = None, title: str = "Temuan uji") -> dict:
    ts = now_iso()
    doc = {"id": new_id(), "org_id": ORG, TAG: True, "project_id": project_id,
           "unit_id": unit_id, "title": title, "description": "bahan uji gerbang retensi",
           "category": "finishing", "severity": "medium", "status": "open",
           "location": "uji", "opened_by": "site@sipro.co.id", "assigned_to": None,
           "due_date": day(3), "closed_at": None, "created_at": ts, "updated_at": ts}
    db.punch_items.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


def settle(timeout: int = 45) -> bool:
    """Tunggu antrean event kosong — jurnal lahir dari event, bukan seketika."""
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


def purge():
    """Buang seluruh bahan uji Fase 48 beserta jejak keuangannya."""
    settle()
    projects = [p["id"] for p in db.projects.find({TAG: True}, {"_id": 0, "id": 1})]
    spks = [s["id"] for s in db.spk.find(
        {"$or": [{TAG: True}, {"project_id": {"$in": projects}}]}, {"_id": 0, "id": 1})]
    pos = [p["id"] for p in db.purchase_orders.find(
        {"$or": [{TAG: True}, {"project_id": {"$in": projects}}, {"spk_id": {"$in": spks}}]},
        {"_id": 0, "id": 1})]
    vendors = [v["id"] for v in db.vendors.find({TAG: True}, {"_id": 0, "id": 1})]
    subs = [s["id"] for s in db.subcontractors.find({TAG: True}, {"_id": 0, "id": 1})]
    claims = [c["id"] for c in db.progress_claims.find({"spk_id": {"$in": spks}},
                                                       {"_id": 0, "id": 1})]
    rets = [r["id"] for r in db.subcon_retentions.find({"spk_id": {"$in": spks}},
                                                       {"_id": 0, "id": 1})]
    advs = [a["id"] for a in db.subcon_advances.find({"spk_id": {"$in": spks}},
                                                     {"_id": 0, "id": 1})]
    bills = [b["id"] for b in db.ap_invoices.find(
        {"$or": [{"po_id": {"$in": pos}}, {"project_id": {"$in": projects}},
                 {"spk_id": {"$in": spks}}, {"retention_id": {"$in": rets}}]},
        {"_id": 0, "id": 1})]
    for coll, q in (
        ("grn_returns", {"po_id": {"$in": pos}}),
        ("grns", {"po_id": {"$in": pos}}),
        ("purchase_orders", {"id": {"$in": pos}}),
        ("vendor_prices", {"vendor_id": {"$in": vendors}}),
        ("vendor_assessments", {"target_id": {"$in": vendors + subs}}),
        ("vendors", {"id": {"$in": vendors}}),
        ("payments_out", {"$or": [{"bill_id": {"$in": bills}}, {"advance_id": {"$in": advs}}]}),
        ("ap_invoices", {"id": {"$in": bills}}),
        ("subcon_retentions", {"id": {"$in": rets}}),
        ("subcon_deductions", {"spk_id": {"$in": spks}}),
        ("subcon_advances", {"id": {"$in": advs}}),
        ("progress_claims", {"id": {"$in": claims}}),
        ("spk_scope_items", {"spk_id": {"$in": spks}}),
        ("spk", {"id": {"$in": spks}}),
        ("subcontractors", {"id": {"$in": subs}}),
        ("material_transfers", {"$or": [{"from_project_id": {"$in": projects}},
                                        {"to_project_id": {"$in": projects}}]}),
        ("material_txns", {"project_id": {"$in": projects}}),
        ("material_requisitions", {"$or": [{TAG: True}, {"project_id": {"$in": projects}}]}),
        ("materials", {"$or": [{TAG: True}, {"project_id": {"$in": projects}}]}),
        ("punch_items", {"$or": [{TAG: True}, {"project_id": {"$in": projects}}]}),
        ("journal_entries", {"source_id": {"$in": bills + advs + rets + pos}}),
        ("activities", {"$or": [{"entity_id": {"$in": projects}},
                                {"actor": {"$regex": "^(poc4|gate4)"}}]}),
        ("notifications", {"$or": [{"related_entity_id": {"$in": projects}},
                                   {"user_email": {"$regex": "^(poc4|gate4)"}}]}),
        ("tasks", {"related_entity_id": {"$in": bills + projects}}),
        ("events", {"entity_id": {"$in": bills + advs + rets}}),
        ("audit_logs", {"entity_id": {"$in": bills + advs + rets + pos + vendors}}),
        ("blocks", {"project_id": {"$in": projects}}),
        ("clusters", {"project_id": {"$in": projects}}),
        ("projects", {"id": {"$in": projects}}),
    ):
        db[coll].delete_many(q)


def orphans() -> dict:
    """Sisa menggantung — diukur dari kenyataan, bukan dari tanda gate."""
    po_ids = {p["id"] for p in db.purchase_orders.find({}, {"_id": 0, "id": 1})}
    bill_ids = {b["id"] for b in db.ap_invoices.find({}, {"_id": 0, "id": 1})}
    spk_ids = {s["id"] for s in db.spk.find({}, {"_id": 0, "id": 1})}
    proj_ids = {p["id"] for p in db.projects.find({}, {"_id": 0, "id": 1})}
    return {
        "projects": db.projects.count_documents({TAG: True}),
        "vendors": db.vendors.count_documents({TAG: True}),
        "grn_tanpa_po": sum(1 for g in db.grns.find({}, {"_id": 0, "po_id": 1})
                            if g.get("po_id") not in po_ids),
        "retur_tanpa_po": sum(1 for r in db.grn_returns.find({}, {"_id": 0, "po_id": 1})
                              if r.get("po_id") not in po_ids),
        "retensi_tanpa_tagihan": sum(
            1 for r in db.subcon_retentions.find({}, {"_id": 0, "ap_bill_id": 1})
            if r.get("ap_bill_id") not in bill_ids),
        "potongan_tanpa_spk": sum(
            1 for d in db.subcon_deductions.find({}, {"_id": 0, "spk_id": 1})
            if d.get("spk_id") not in spk_ids),
        "mutasi_stok_tanpa_proyek": sum(
            1 for t in db.material_txns.find({}, {"_id": 0, "project_id": 1})
            if t.get("project_id") not in proj_ids),
        "jurnal_uangmuka_tanpa_dokumen": sum(
            1 for j in db.journal_entries.find({"source_type": "subcon_advance"},
                                               {"_id": 0, "source_id": 1})
            if not db.subcon_advances.count_documents({"id": j.get("source_id")})),
        "jurnal_retensi_tanpa_dokumen": sum(
            1 for j in db.journal_entries.find({"source_type": "subcon_retention"},
                                               {"_id": 0, "source_id": 1})
            if not db.subcon_retentions.count_documents({"id": j.get("source_id")})),
    }
