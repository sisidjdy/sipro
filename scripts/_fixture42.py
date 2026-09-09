#!/usr/bin/env python3
"""_fixture42.py — bahan uji BUATAN SENDIRI untuk gate Mitra & Fee (`verify_partner.py`).

## Kenapa berkas ini lahir (cacat nyata yang diperbaikinya)

`verify_partner.py` dulu menguji rantai "pemicu nyata → fee otomatis" dengan cara
**menumpang data demo**:

1. mengambil satu lead demo yang kebetulan bertahap `nurturing`/`appointment`, lalu
   **mengubahnya secara permanen** menjadi `source="partner"` + `partner_id=<mitra>`;
2. mengambil satu unit demo yang kebetulan `available`, lalu **memesan (reserve) →
   booking → PPJB** atas unit itu;
3. membuat lead uji bernama "Gate 42 Lead Mitra";
4. **tidak pernah membuang apa pun.**

Akibatnya di layar manusia (bukan di layar penguji):

* `/leads` menampilkan baris "Gate 42 Lead Mitra" di urutan teratas — bahan uji dipajang
  seolah calon pembeli sungguhan;
* rumah nyata (mis. `A-03`) berubah menjadi **`booked`** oleh transaksi yang pembelinya
  tidak ada. Ini bukan kotoran kecil: unit yang ter-booking tidak bisa dijual, dan
  `seed_phase46` justru menyiapkan unit itu supaya manusia bisa mencoba dialog
  "Mulai Bangun";
* lahir **tagihan fee mitra Rp 17 juta** beserta jurnal, jadwal AR, dan komisi dari
  transaksi yang tidak pernah terjadi — angka yang ikut terhitung di analitik mitra,
  laporan keuangan, dan dasbor direksi;
* satu lead demo kehilangan sumber aslinya (berubah jadi "dari mitra") tanpa jejak.

Aturan repo sudah menyebutnya sejak Fase 46: *"bahan uji gate/POC dibuat & dibuang
otomatis; bila terlihat di layar berarti ada run yang mati di tengah."* Gate ini
satu-satunya yang belum mematuhinya.

## Cara kerja fixture ini

`make()` membangun **dunia kecil milik sendiri** (proyek + rumah + lead ber-atribusi
mitra, semuanya bertanda `gate42: True`) sehingga gate bisa menjalankan rantai pemicu
lewat API sungguhan tanpa menyentuh sebutir data demo. `purge()` membuang bahan uji
BESERTA TURUNANNYA (deal, fee, komisi, jadwal AR, jurnal, kewajiban kontrak, dokumen,
aktivitas, tugas, notifikasi, event). `orphans()` MEMBUKTIKAN tidak ada sisa menggantung.

Dipakai `scripts/verify_partner.py`; pola dan penamaannya mengikuti `_fixture47/48/49/50`.
"""
import os
import pathlib
import uuid
from datetime import datetime, timezone

from dotenv import load_dotenv
from pymongo import MongoClient

import _purge_cascade as _cascade

ROOT = pathlib.Path(__file__).resolve().parent.parent
load_dotenv(ROOT / "backend" / ".env")
TAG = "gate42"
ORG = os.environ.get("DEFAULT_ORG_ID", "org-sipro")
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]

# Nomor telepon bahan uji: sengaja di blok +62812999xxxx supaya mudah dikenali manusia
# maupun pemeriksaan anti-bocor (`forensic_audit.py`).
LEAD_PHONE = "+628129990042"
UNIT_CODE = "GATE42-01"
PROJECT_NAME = "Proyek Uji Gate 42 (mitra & fee)"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id() -> str:
    return str(uuid.uuid4())


# ------------------------------------------------------------------ pembuatan
def make_project() -> dict:
    ts = now_iso()
    doc = {"id": new_id(), "org_id": ORG, "name": PROJECT_NAME, "code": "GATE42",
           "location": "Lokasi uji", "status": "active", "total_units": 1,
           TAG: True, "created_by": TAG, "created_at": ts, "updated_at": ts}
    db.projects.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


def make_unit(project: dict, price: int = 850_000_000) -> dict:
    """Rumah `available` milik gate sendiri — supaya reservasi tidak mengunci stok nyata."""
    ts = now_iso()
    doc = {"id": new_id(), "org_id": ORG, "project_id": project["id"], "code": UNIT_CODE,
           "type": "Tipe Uji 42", "price": price, "status": "available",
           "construction_status": "not_started", "construction_progress": 0,
           "payment_status": "none", "reserved_by_deal": None, "booked_by_deal": None,
           TAG: True, "created_by": TAG, "created_at": ts, "updated_at": ts}
    db.units.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


def make_lead(partner_id: str) -> dict:
    """Lead ber-atribusi mitra milik gate sendiri (bukan lead demo yang dibajak)."""
    ts = now_iso()
    doc = {"id": new_id(), "org_id": ORG, "name": "Gate 42 Lead Mitra",
           "phone": LEAD_PHONE, "source": "partner", "partner_id": partner_id,
           "stage": "nurturing", "score": 60, "assigned_to": "manager@sipro.co.id",
           "notes": "Bahan uji gate mitra & fee — dibuang otomatis setelah gate selesai.",
           TAG: True, "created_by": TAG, "created_at": ts, "updated_at": ts}
    db.leads.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


def make(partner_id: str) -> dict:
    """Bangun dunia uji yang bersih (membuang sisa run sebelumnya lebih dulu)."""
    purge()
    project = make_project()
    unit = make_unit(project)
    lead = make_lead(partner_id)
    return {"project": project, "unit": unit, "lead": lead}


# ---------------------------------------------------------------- pembersihan
def _ids(coll: str, q: dict) -> list:
    return [d["id"] for d in db[coll].find(q, {"_id": 0, "id": 1}) if d.get("id")]


def purge() -> dict:
    """Buang bahan uji + SELURUH turunan yang lahir dari rantai pemicu."""
    projects = _ids("projects", {TAG: True})
    units = _ids("units", {"$or": [{TAG: True}, {"code": UNIT_CODE},
                                   {"project_id": {"$in": projects}}]})
    leads = _ids("leads", {"$or": [{TAG: True}, {"phone": LEAD_PHONE}]})
    # Deal uji dikenali dari tiga arah: penanda fixture, lead uji, dan unit uji. Run lama
    # (sebelum fixture ini ada) tidak punya penanda, jadi jalur unit/lead tetap diperlukan
    # supaya kotoran warisan ikut terangkat.
    deals = _ids("deals", {"$or": [{TAG: True}, {"lead_id": {"$in": leads}},
                                   {"unit_id": {"$in": units}},
                                   {"notes": {"$regex": "^GATE 42"}}]})
    # Rumah NYATA yang sempat dikunci oleh transaksi uji (kotoran warisan run lama, saat
    # gate masih memesan unit demo) harus DILEPAS kembali — kalau tidak, rumah itu tetap
    # `booked` oleh transaksi yang sudah dibuang: tidak bisa dijual, dan papan pembangunan
    # menampilkan pembeli hantu. Unit milik fixture sendiri tidak perlu dilepas (dibuang).
    ts = now_iso()
    # Dua jenis kotoran ditangani sekaligus:
    #   (a) unit yang menunjuk deal uji yang BARU SAJA dibuang, dan
    #   (b) unit yang menunjuk deal yang SUDAH TIDAK ADA lagi (rujukan menggantung dari run
    #       lama yang mati di tengah, atau dari purge versi awal yang belum melepas unit).
    hidup = set(_ids("deals", {}))
    hantu = [u["id"] for u in db.units.find(
        {"id": {"$nin": units}},
        {"_id": 0, "id": 1, "reserved_by_deal": 1, "booked_by_deal": 1, "sold_by_deal": 1,
         "deal_id": 1})
        if any((u.get(k) and (u[k] in deals or u[k] not in hidup))
               for k in ("reserved_by_deal", "booked_by_deal", "sold_by_deal", "deal_id"))]
    lepas = db.units.update_many(
        {"id": {"$in": hantu}},
        {"$set": {"status": "available", "reserved_by_deal": None, "booked_by_deal": None,
                  "sold_by_deal": None, "deal_id": None, "lead_id": None,
                  "customer_id": None, "payment_status": "none", "updated_at": ts}})
    counts = {
        "turunan_deal": sum(_cascade.purge_deal_children(db, deals, leads).values()),
        "unit_demo_dilepas": lepas.modified_count,
        # PPJB melahirkan catatan pajak (PPN/BPHTB/PPh final) yang menunjuk deal. Purge versi
        # pertama melupakannya, sehingga audit forensik menemukan `tax_records -> deal_id
        # tidak ada di deals` — angka pajak dari transaksi yang tidak pernah terjadi.
        "tax_records": db.tax_records.delete_many({"deal_id": {"$in": deals}}).deleted_count,
        "marketing_fees": db.marketing_fees.delete_many(
            {"$or": [{"deal_id": {"$in": deals}}, {"lead_id": {"$in": leads}}]}).deleted_count,
        "commissions": db.commissions.delete_many({"deal_id": {"$in": deals}}).deleted_count,
        "ar_invoices": db.ar_invoices.delete_many(
            {"$or": [{"deal_id": {"$in": deals}}, {"unit_id": {"$in": units}}]}).deleted_count,
        "receipts": db.receipts.delete_many({"deal_id": {"$in": deals}}).deleted_count,
        "contract_liabilities": db.contract_liabilities.delete_many(
            {"deal_id": {"$in": deals}}).deleted_count,
        "journal_entries": db.journal_entries.delete_many(
            {"source_id": {"$in": deals + units + leads}}).deleted_count,
        "documents": db.documents.delete_many(
            {"$or": [{"deal_id": {"$in": deals}}, {"entity_id": {"$in": deals + leads}}]}
        ).deleted_count,
        "quotations": db.quotations.delete_many({"deal_id": {"$in": deals}}).deleted_count,
        "activities": db.activities.delete_many(
            {"entity_id": {"$in": deals + leads + units}}).deleted_count,
        "tasks": db.tasks.delete_many(
            {"related_entity_id": {"$in": deals + leads + units}}).deleted_count,
        "notifications": db.notifications.delete_many(
            {"entity_id": {"$in": deals + leads + units}}).deleted_count,
        "events": db.events.delete_many(
            {"entity_id": {"$in": deals + leads + units}}).deleted_count,
        "deals": db.deals.delete_many({"id": {"$in": deals}}).deleted_count,
        "leads": db.leads.delete_many({"id": {"$in": leads}}).deleted_count,
        "units": db.units.delete_many({"id": {"$in": units}}).deleted_count,
        "projects": db.projects.delete_many({"id": {"$in": projects}}).deleted_count,
        "build_schedules": db.build_schedules.delete_many(
            {"unit_id": {"$in": units}}).deleted_count,
        "surveys": db.surveys.delete_many({"lead_id": {"$in": leads}}).deleted_count,
        "appointments": db.appointments.delete_many({"lead_id": {"$in": leads}}).deleted_count,
        # Jadwal pembangunan milik RUMAH NYATA tidak boleh dibuang (itu data seed), tetapi
        # rujukan `deal_id`-nya harus dibersihkan supaya tidak menunjuk transaksi hantu —
        # termasuk rujukan menggantung warisan run lama (deal-nya sudah tidak ada).
        "jadwal_dilepas_dari_deal": db.build_schedules.update_many(
            {"unit_id": {"$nin": units},
             "deal_id": {"$nin": list(hidup - set(deals)) + [None]}},
            {"$unset": {"deal_id": "", "lead_id": "", "customer_id": ""}}).modified_count,
    }
    # Sengketa atribusi menyimpan nomor telepon, bukan id lead.
    counts["partner_conflicts"] = db.partner_conflicts.delete_many(
        {"phone": LEAD_PHONE}).deleted_count if "partner_conflicts" \
        in db.list_collection_names() else 0
    return {k: v for k, v in counts.items() if v}


def orphans() -> dict:
    """Buktikan tidak ada sisa menggantung sesudah pembersihan."""
    unit_ids = set(_ids("units", {}))
    deal_ids = set(_ids("deals", {}))
    lead_ids = set(_ids("leads", {}))
    return {
        "lead_uji_tersisa": db.leads.count_documents(
            {"$or": [{TAG: True}, {"phone": LEAD_PHONE}]}),
        "unit_uji_tersisa": db.units.count_documents({"$or": [{TAG: True},
                                                              {"code": UNIT_CODE}]}),
        "proyek_uji_tersisa": db.projects.count_documents({TAG: True}),
        "deal_uji_tersisa": db.deals.count_documents(
            {"$or": [{TAG: True}, {"notes": {"$regex": "^GATE 42"}}]}),
        # Turunan yang menggantung = bukti purge belum lengkap.
        "fee_tanpa_deal": sum(1 for f in db.marketing_fees.find(
            {"deal_id": {"$ne": None}}, {"_id": 0, "deal_id": 1})
            if f["deal_id"] not in deal_ids),
        "fee_tanpa_lead": sum(1 for f in db.marketing_fees.find(
            {"lead_id": {"$ne": None}}, {"_id": 0, "lead_id": 1})
            if f["lead_id"] not in lead_ids),
        "komisi_tanpa_deal": sum(1 for c in db.commissions.find(
            {}, {"_id": 0, "deal_id": 1}) if c.get("deal_id") not in deal_ids),
        "tagihan_ar_tanpa_unit": sum(1 for i in db.ar_invoices.find(
            {"unit_id": {"$ne": None}}, {"_id": 0, "unit_id": 1})
            if i["unit_id"] not in unit_ids),
        # Rumah nyata yang masih terkunci oleh transaksi yang sudah dibuang.
        "unit_terkunci_deal_hantu": db.units.count_documents(
            {"$or": [{"booked_by_deal": {"$nin": list(deal_ids) + [None]}},
                     {"reserved_by_deal": {"$nin": list(deal_ids) + [None]}}]}),
    }


if __name__ == "__main__":
    import json
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "purge":
        print("purge:", json.dumps(purge(), ensure_ascii=False))
    print("orphans:", json.dumps(orphans(), ensure_ascii=False))
