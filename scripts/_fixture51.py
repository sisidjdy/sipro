#!/usr/bin/env python3
"""_fixture51.py — bahan uji BUATAN SENDIRI untuk POC & gate Fase 51.

Fase 51 menyentuh tiga urusan yang semuanya MENGUBAH keadaan global bila menumpang data
demo:

1. **Retensi subkon** — pencairan menerbitkan tagihan AP + jurnal. Menumpang retensi demo
   berarti gate berikutnya melihat uang yang sudah keluar.
2. **Pengingat WhatsApp** — kandidat pengingat dihitung dari tagihan nyata; menumpang tagihan
   demo membuat riwayat pengingat bercampur dengan yang dibaca manusia di layar.
3. **Portal pembeli** — login OTP melahirkan `portal_users`; membuangnya harus ikut membuang
   akun portalnya (pelajaran Fase 50: akun portal YATIM = temuan CRITICAL audit forensik).

Karena itu seluruh bahan uji Fase 51 bertanda `gate51: True` dan dibuang lagi oleh
`purge()`; `orphans()` MEMBUKTIKAN tidak ada sisa menggantung.

Dunia uji yang dibangun `make()`:

* proyek + 1 rumah yang SUDAH diserahterimakan (BAST bertanggal 60 hari lalu) sehingga
  garansinya berjalan — dipakai klaim garansi, pengingat "hampir habis", dan portal;
* pembeli + akun portal + jadwal tagihan: satu termin jatuh tempo 3 hari ke depan dan satu
  termin TERLAMBAT 10 hari — bahan pengingat termin & tunggakan;
* subkontraktor + SPK dengan LINGKUP UNIT rumah itu + termin disetujui + retensi
  `held` yang masa pemeliharaannya SUDAH LEWAT dan tanpa punch terbuka, jadi satu-satunya
  hal yang boleh menahannya adalah KLAIM GARANSI yang masih berjalan (inti Fase 51A).
"""
import os
import pathlib
import sys
import uuid
from datetime import datetime, timedelta, timezone

import requests
from dotenv import load_dotenv
from pymongo import MongoClient

ROOT = pathlib.Path(__file__).resolve().parent.parent
load_dotenv(ROOT / "backend" / ".env")
sys.path.insert(0, str(ROOT / "backend"))
import reference as ref  # noqa: E402  (SSOT nama bagian garansi — jangan diketik ulang)

BASE = "http://localhost:8001/api"
PW = "Sipro#2026"
TAG = "gate51"
ORG = os.environ.get("DEFAULT_ORG_ID", "org-sipro")
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]

PHONE = "+628129990051"
UNIT_CODE = "G51-01"
PROJECT_NAME = "Proyek Uji Gate 51 (retensi, pengingat, portal)"

# Saat perangkat uji MULAI. Dipakai memulihkan "slot dedup" milik data demo: menjalankan
# `POST /reminders/run` mengunci satu pengingat per periode untuk SETIAP kandidat — termasuk
# pembeli demo yang bukan bahan uji. Kalau tidak dipulihkan, tombol "Jalankan sekarang" di
# layar selalu menjawab "dilewati (sudah diingatkan periode ini)" sehingga manusia (dan gate
# berikutnya) tidak pernah bisa melihat pengingat benar-benar terbentuk — kelas cacat yang
# sama dengan "gate menghabiskan bahan uji" pada Fase 46/47/49.
RUN_STARTED_AT = datetime.now(timezone.utc).isoformat()
# Status yang boleh dipulihkan: pesan SIMULASI/ DILEWATI tidak pernah pergi ke mana pun,
# jadi membuangnya memulihkan keadaan. Pesan "terkirim" adalah FAKTA — ia tidak boleh
# dihapus perangkat uji, dan kalau sampai ada, POC memang tidak boleh dijalankan di
# lingkungan berkredensial WhatsApp nyata.
RESTORABLE = ("simulasi", "dilewati")


# --------------------------------------------------------------------- dasar
def login(email: str) -> dict:
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": PW}, timeout=25)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def api(method: str, path: str, headers: dict, **kw):
    return requests.request(method, f"{BASE}{path}", headers=headers, timeout=60, **kw)


def new_id() -> str:
    return str(uuid.uuid4())


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def day(offset: int = 0) -> str:
    return (datetime.now(timezone.utc).date() + timedelta(days=offset)).isoformat()


def add_months(d: str, months: int) -> str:
    y, m, dd = (int(x) for x in str(d)[:10].split("-"))
    total = y * 12 + (m - 1) + months
    ny, nm = divmod(total, 12)
    nm += 1
    last = [31, 29 if ny % 4 == 0 and (ny % 100 != 0 or ny % 400 == 0) else 28,
            31, 30, 31, 30, 31, 31, 30, 31, 30, 31][nm - 1]
    return f"{ny:04d}-{nm:02d}-{min(dd, last):02d}"


# ---------------------------------------------------------------- pembuatan
def make_project() -> dict:
    ts = now_iso()
    doc = {"id": new_id(), "org_id": ORG, "name": PROJECT_NAME, "code": "G51",
           "location": "Lokasi uji", "status": "active", "total_units": 1,
           # Peran ber-lingkup proyek (PM & pelaksana lapangan) HARUS terdaftar sebagai
           # anggota; tanpa ini setiap aksi mereka dijawab 403 "bukan anggota proyek ini"
           # dan uji pemisahan tugas tidak pernah benar-benar teruji.
           "members": ["pm@sipro.co.id", "site@sipro.co.id", "finlead@sipro.co.id",
                       "finance@sipro.co.id", "owner@sipro.co.id",
                       "superadmin@sipro.co.id"],
           "pm_email": "pm@sipro.co.id",
           TAG: True, "created_by": TAG, "created_at": ts, "updated_at": ts}
    db.projects.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


def make_unit(project: dict, price: int = 900_000_000) -> dict:
    ts = now_iso()
    doc = {"id": new_id(), "org_id": ORG, "project_id": project["id"], "code": UNIT_CODE,
           "type": "Tipe Uji 51", "price": price, "status": "sold",
           "construction_status": "handed_over", "construction_progress": 100,
           "payment_status": "cicil", TAG: True, "created_by": TAG,
           "created_at": ts, "updated_at": ts}
    db.units.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


def make_buyer(unit: dict) -> dict:
    """Lead + deal + pelanggan + jadwal tagihan (satu termin H+3, satu TERLAMBAT 10 hari)."""
    ts = now_iso()
    nama = "Uji Pembeli Gate 51"
    lead = {"id": new_id(), "org_id": ORG, "name": nama, "phone": PHONE,
            "source": "walk_in", "stage": "won", "assigned_to": "sales@sipro.co.id",
            TAG: True, "created_at": ts, "updated_at": ts}
    db.leads.insert_one(dict(lead))
    deal = {"id": new_id(), "org_id": ORG, "lead_id": lead["id"], "unit_id": unit["id"],
            "project_id": unit["project_id"], "assigned_to": "sales@sipro.co.id",
            "status": "completed", "price": unit["price"], "booking_fee": 5_000_000,
            "booked_at": ts, TAG: True, "created_by": TAG,
            "created_at": ts, "updated_at": ts}
    db.deals.insert_one(dict(deal))
    cust = {"id": new_id(), "org_id": ORG, "lead_id": lead["id"], "deal_id": deal["id"],
            "name": nama, "phone": PHONE, "nik": "3276015051000051",
            "kyc_status": "verified", TAG: True, "created_at": ts, "updated_at": ts}
    db.customers.insert_one(dict(cust))
    total = unit["price"]
    dp = int(total * 0.2)
    termin_lewat = int(total * 0.3)
    termin_dekat = int(total * 0.5)
    inv = {
        "id": new_id(), "org_id": ORG, "deal_id": deal["id"], "unit_id": unit["id"],
        "lead_id": lead["id"], "project_id": unit["project_id"], "unit_code": unit["code"],
        "lead_name": nama, "assigned_to": "sales@sipro.co.id",
        "price": total, "total": total, "paid": dp, "outstanding": total - dp,
        "status": "partial",
        "items": [
            {"item_id": new_id(), "label": "DP 20%", "amount": dp, "paid": dp,
             "due_date": day(-40), "status": "paid"},
            {"item_id": new_id(), "label": "Termin I 30%", "amount": termin_lewat, "paid": 0,
             "due_date": day(-10), "status": "overdue"},
            {"item_id": new_id(), "label": "Pelunasan 50%", "amount": termin_dekat, "paid": 0,
             "due_date": day(3), "status": "unpaid"},
        ],
        TAG: True, "created_at": ts, "updated_at": ts,
    }
    db.ar_invoices.insert_one(dict(inv))
    db.units.update_one({"id": unit["id"]}, {"$set": {
        "sold_by_deal": deal["id"], "deal_id": deal["id"], "lead_id": lead["id"],
        "customer_id": cust["id"], "updated_at": ts}})
    for d in (lead, deal, cust, inv):
        d.pop("_id", None)
    return {"lead": lead, "deal": deal, "customer": cust, "invoice": inv}


def make_handover(unit: dict, buyer: dict, *, days_ago: int = 85) -> dict:
    """BAST bertanggal lampau supaya masa garansi BERJALAN (bukan baru mulai).

    `days_ago=85` dipilih sengaja: masa `finishing` bawaan 3 bulan (±92 hari) sehingga pada
    hari uji sisanya ±7 hari — di bawah ambang "hampir habis" (30 hari). Dengan begitu
    kandidat pengingat Fase 51B lahir dari DATA, tanpa memanipulasi jam sistem. Kalau
    tanggalnya terlalu muda (mis. 60 hari), sisanya 32 hari dan kandidatnya tidak pernah
    muncul — cacat perangkat uji yang mudah disalahartikan sebagai cacat mesin.
    """
    ts = now_iso()
    ho_day = day(-days_ago)
    plan = [("struktur", 120), ("atap_plafon", 12), ("dinding_lantai", 12),
            ("plumbing", 6), ("listrik", 6), ("kusen", 6), ("finishing", 3)]
    doc = {
        "id": new_id(), "org_id": ORG, "number": f"BAST/G51/{str(uuid.uuid4())[:4]}",
        "unit_id": unit["id"], "unit_code": unit["code"], "project_id": unit["project_id"],
        "project_name": PROJECT_NAME, "deal_id": buyer["deal"]["id"],
        "customer_id": buyer["customer"]["id"], "buyer_name": buyer["customer"]["name"],
        "received_by": buyer["customer"]["name"], "handed_over_at": ho_day,
        "state": "aktif", "status": "aktif", "issued_by": TAG,
        "keys_handed": 2, "meter_air": "A-51", "meter_listrik": "L-51",
        "warranties": [{"category": c, "label": ref.label_of("warranty_category", c),
                        "months": m, "starts_at": ho_day,
                        "expires_at": add_months(ho_day, m)} for c, m in plan],
        TAG: True, "created_at": ts, "updated_at": ts,
    }
    db.unit_handovers.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


def make_receipt(buyer: dict, unit: dict) -> dict:
    """Kwitansi penerimaan uang — bahan uji unduhan kwitansi di portal (Fase 51C)."""
    ts = now_iso()
    item = buyer["invoice"]["items"][0]
    doc = {"id": new_id(), "org_id": ORG, "deal_id": buyer["deal"]["id"],
           "unit_id": unit["id"], "unit_code": unit["code"],
           "receipt_no": f"KWT/G51/{str(uuid.uuid4())[:4]}",
           "amount": item["amount"], "applied": item["amount"], "deposit_amount": 0,
           "funding": "cash", "method": "transfer", "note": "DP uji Fase 51",
           "allocations": [{"item_id": item["item_id"], "label": item["label"],
                            "amount": item["amount"]}],
           "actor": "finance@sipro.co.id", TAG: True, "created_at": ts}
    db.receipts.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


def make_subcon_retention(project: dict, unit: dict) -> dict:
    """Subkon + SPK berlingkup unit + termin disetujui + retensi `held` yang SIAP cair.

    Masa pemeliharaan dibuat sudah lewat & tanpa punch terbuka: kalau nanti pencairannya
    tetap ditahan, satu-satunya sebab yang sah adalah klaim garansi yang masih berjalan.
    """
    ts = now_iso()
    sub = {"id": new_id(), "org_id": ORG, "name": f"CV Uji Retensi Gate 51 {uuid.uuid4().hex[:4]}",
           # `subcontractors` dijaga index unik (org_id, code): dua baris tanpa kode langsung
           # bentrok. Kode uji dibuat unik supaya fixture bisa membuat retensi kedua.
           "code": f"SUB-G51-{uuid.uuid4().hex[:5]}",
           "trade": "struktur", "phone": "+628129990052", "is_active": True,
           TAG: True, "created_at": ts, "updated_at": ts}
    db.subcontractors.insert_one(dict(sub))
    spk = {"id": new_id(), "org_id": ORG, "spk_number": f"SPK/G51/{str(uuid.uuid4())[:4]}",
           "subcontractor_id": sub["id"], "subcontractor_name": sub["name"],
           "project_id": project["id"], "project_name": PROJECT_NAME,
           "title": "Pekerjaan uji Fase 51", "scope": "Lingkup satu rumah uji.",
           "contract_value": 200_000_000, "retention_pct": 5,
           "start_date": day(-200), "end_date": day(-120),
           "maintenance_days": 90, "status": "active", "progress_pct": 100,
           "created_by": TAG, TAG: True, "created_at": ts, "updated_at": ts}
    db.spk.insert_one(dict(spk))
    db.spk_scope_items.insert_one({
        "id": new_id(), "org_id": ORG, "spk_id": spk["id"], "unit_id": unit["id"],
        "unit_code": unit["code"], "description": "Struktur rumah uji",
        # `spk_scope_items` dijaga index unik (org_id, build_item_id): baris kedua tanpa
        # penunjuk item pekerjaan akan bentrok, jadi bahan uji memakai penanda sendiri.
        "build_item_id": f"G51-ITEM-{uuid.uuid4().hex[:6]}",
        "amount": 200_000_000, TAG: True, "created_at": ts, "updated_at": ts})
    claim = {"id": new_id(), "org_id": ORG,
             "claim_number": f"TRM/G51/{str(uuid.uuid4())[:4]}",
             "spk_id": spk["id"], "spk_number": spk["spk_number"],
             "subcontractor_id": sub["id"], "subcontractor_name": sub["name"],
             "project_id": project["id"], "project_name": PROJECT_NAME,
             "period": "Termin akhir (100%)", "prev_pct": 0, "claimed_pct": 100,
             "verified_pct": 100, "effective_pct": 100,
             "contract_value_at_submit": 200_000_000,
             "gross": 200_000_000, "retention_pct": 5, "retention_held": 10_000_000,
             "net": 190_000_000, "status": "approved",
             "approved_by": "finlead@sipro.co.id", "approved_at": day(-100),
             "created_by": TAG, TAG: True, "created_at": ts, "updated_at": ts}
    db.progress_claims.insert_one(dict(claim))
    bill = {"id": new_id(), "org_id": ORG, "vendor": sub["name"],
            "project_id": project["id"], "claimed": 200_000_000, "retention_pct": 5,
            "retention_held": 10_000_000, "net": 190_000_000, "paid": 190_000_000,
            "outstanding": 0, "status": "paid", "bill_kind": "progress_claim",
            "spk_id": spk["id"], "subcontractor_id": sub["id"],
            "created_by": TAG, TAG: True, "created_at": ts, "updated_at": ts}
    db.ap_invoices.insert_one(dict(bill))
    ret = {"id": new_id(), "org_id": ORG,
           "retention_number": f"RET/G51/{str(uuid.uuid4())[:4]}",
           "spk_id": spk["id"], "spk_number": spk["spk_number"],
           "project_id": project["id"], "subcontractor_id": sub["id"],
           "subcontractor_name": sub["name"], "claim_id": claim["id"],
           "claim_number": claim["claim_number"], "ap_bill_id": bill["id"],
           "amount": 10_000_000, "retention_pct": 5, "state": "held",
           "maintenance_days": 90, "maintenance_until": day(-10),
           "requested_by": None, "requested_at": None, "request_reason": None,
           "released_by": None, "released_at": None, "release_reason": None,
           "release_bill_id": None, "journal_no": None,
           "created_by": TAG, TAG: True, "created_at": ts, "updated_at": ts}
    db.subcon_retentions.insert_one(dict(ret))
    for d in (sub, spk, claim, bill, ret):
        d.pop("_id", None)
    return {"subcontractor": sub, "spk": spk, "claim": claim, "bill": bill,
            "retention": ret}


def make_warranty_claim(unit: dict, buyer: dict, handover: dict, *,
                        state: str = "dikerjakan") -> dict:
    """Klaim garansi yang MASIH BERJALAN pada rumah lingkup SPK."""
    ts = now_iso()
    doc = {"id": new_id(), "org_id": ORG, "number": f"KG/G51/{str(uuid.uuid4())[:4]}",
           "unit_id": unit["id"], "unit_code": unit["code"],
           "project_id": unit["project_id"], "handover_id": handover["id"],
           "customer_id": buyer["customer"]["id"], "category": "struktur",
           "title": "Retak rambut kolom (uji Fase 51)",
           "description": "Bahan uji: klaim garansi berjalan yang harus menahan retensi.",
           "source": "internal", "state": state, "photos": [], "fix_photos": [],
           "assigned_to": "site@sipro.co.id", "created_by": TAG,
           TAG: True, "created_at": ts, "updated_at": ts}
    db.warranty_claims.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


def make(*, with_active_claim: bool = True) -> dict:
    purge()
    project = make_project()
    unit = make_unit(project)
    buyer = make_buyer(unit)
    handover = make_handover(unit, buyer)
    receipt = make_receipt(buyer, unit)
    subcon = make_subcon_retention(project, unit)
    claim = make_warranty_claim(unit, buyer, handover) if with_active_claim else None
    return {"project": project, "unit": unit, "buyer": buyer, "handover": handover,
            "receipt": receipt, "subcon": subcon, "claim": claim}


# ---------------------------------------------------------------- pembersihan
def _ids(coll: str, q: dict) -> list:
    return [d["id"] for d in db[coll].find(q, {"_id": 0, "id": 1}) if d.get("id")]


def purge() -> dict:
    projects = _ids("projects", {TAG: True})
    units = _ids("units", {"$or": [{TAG: True}, {"code": UNIT_CODE},
                                   {"project_id": {"$in": projects}}]})
    leads = _ids("leads", {"$or": [{TAG: True}, {"phone": PHONE}]})
    deals = _ids("deals", {"$or": [{TAG: True}, {"unit_id": {"$in": units}},
                                   {"lead_id": {"$in": leads}}]})
    customers = _ids("customers", {"$or": [{TAG: True}, {"phone": PHONE}]})
    handovers = _ids("unit_handovers", {"$or": [{TAG: True}, {"unit_id": {"$in": units}}]})
    claims = _ids("warranty_claims", {"$or": [{TAG: True}, {"unit_id": {"$in": units}},
                                              {"handover_id": {"$in": handovers}}]})
    spks = _ids("spk", {"$or": [{TAG: True}, {"project_id": {"$in": projects}}]})
    rets = _ids("subcon_retentions", {"$or": [{TAG: True}, {"spk_id": {"$in": spks}}]})
    # Tagihan AR dikumpulkan SEBELUM dihapus: pengingat termin/tunggakan menyimpan
    # `entity_id` = id tagihan AR, jadi tanpa daftar ini pengingatnya jadi YATIM (temuan
    # CRITICAL audit forensik pada run pertama Fase 51 — pelajaran yang sama dengan akun
    # portal yatim di Fase 50).
    invoices = _ids("ar_invoices", {"$or": [{TAG: True}, {"deal_id": {"$in": deals}}]})
    counts = {
        "warranty_claims": db.warranty_claims.delete_many(
            {"id": {"$in": claims}}).deleted_count,
        "unit_handovers": db.unit_handovers.delete_many(
            {"id": {"$in": handovers}}).deleted_count,
        "punch_items": db.punch_items.delete_many(
            {"$or": [{TAG: True}, {"unit_id": {"$in": units}},
                     {"warranty_claim_id": {"$in": claims}}]}).deleted_count,
        "subcon_retentions": db.subcon_retentions.delete_many(
            {"id": {"$in": rets}}).deleted_count,
        "progress_claims": db.progress_claims.delete_many(
            {"$or": [{TAG: True}, {"spk_id": {"$in": spks}}]}).deleted_count,
        "ap_invoices": db.ap_invoices.delete_many(
            {"$or": [{TAG: True}, {"spk_id": {"$in": spks}},
                     {"retention_id": {"$in": rets}}]}).deleted_count,
        "payments_out": db.payments_out.delete_many({TAG: True}).deleted_count,
        "spk_scope_items": db.spk_scope_items.delete_many(
            {"$or": [{TAG: True}, {"spk_id": {"$in": spks}}]}).deleted_count,
        "spk": db.spk.delete_many({"id": {"$in": spks}}).deleted_count,
        "subcontractors": db.subcontractors.delete_many({TAG: True}).deleted_count,
        "journal_entries": db.journal_entries.delete_many(
            {"source_id": {"$in": rets + deals + units + spks}}).deleted_count,
        "receipts": db.receipts.delete_many(
            {"$or": [{TAG: True}, {"deal_id": {"$in": deals}}]}).deleted_count,
        "ar_invoices": db.ar_invoices.delete_many(
            {"$or": [{TAG: True}, {"deal_id": {"$in": deals}}]}).deleted_count,
        "tax_records": db.tax_records.delete_many({"deal_id": {"$in": deals}}).deleted_count,
        "contract_liabilities": db.contract_liabilities.delete_many(
            {"deal_id": {"$in": deals}}).deleted_count,
        "marketing_fees": db.marketing_fees.delete_many(
            {"deal_id": {"$in": deals}}).deleted_count,
        "commissions": db.commissions.delete_many({"deal_id": {"$in": deals}}).deleted_count,
        "complaints": db.complaints.delete_many(
            {"customer_id": {"$in": customers}}).deleted_count,
        # Akun portal WAJIB ikut dibuang bersama pelanggannya (pelajaran Fase 50: akun
        # portal yatim = temuan CRITICAL pada audit forensik).
        "portal_users": db.portal_users.delete_many(
            {"customer_id": {"$in": customers}}).deleted_count,
        "portal_otps": db.portal_otps.delete_many(
            {"$or": [{"customer_id": {"$in": customers}}, {"phone": PHONE}]}).deleted_count,
        "wa_reminders": db.wa_reminders.delete_many(
            {"$or": [{TAG: True}, {"phone": PHONE},
                     {"entity_id": {"$in": units + deals + handovers + invoices}},
                     {"unit_id": {"$in": units}},
                     {"customer_id": {"$in": customers}}]}).deleted_count,
        "customers": db.customers.delete_many({"id": {"$in": customers}}).deleted_count,
        "deals": db.deals.delete_many({"id": {"$in": deals}}).deleted_count,
        "leads": db.leads.delete_many({"id": {"$in": leads}}).deleted_count,
        "units": db.units.delete_many({"id": {"$in": units}}).deleted_count,
        "projects": db.projects.delete_many({"id": {"$in": projects}}).deleted_count,
        "tasks": db.tasks.delete_many(
            {"related_entity_id": {"$in": units + claims + rets + deals}}).deleted_count,
        "activities": db.activities.delete_many(
            {"entity_id": {"$in": units + claims + rets + deals + projects}}).deleted_count,
        "notifications": db.notifications.delete_many(
            {"entity_id": {"$in": units + claims + rets + projects}}).deleted_count,
        "events": db.events.delete_many(
            {"entity_id": {"$in": units + claims + rets + deals}}).deleted_count,
        "messages": db.messages.delete_many({TAG: True}).deleted_count,
        # Kunci idempotensi milik bahan uji: kalau ditinggalkan, run berikutnya bisa dijawab
        # "sedang diproses" (409) oleh kunci yang pemiliknya sudah mati — cacat perangkat uji
        # yang mudah disalahartikan sebagai cacat mesin idempotensi.
        "offline_intake": db.offline_intake.delete_many(
            {"client_ref": {"$regex": "^(poc51|gate51)"}}).deleted_count,
        "conversations": db.conversations.delete_many(
            {"$or": [{TAG: True}, {"contact_phone": PHONE}]}).deleted_count,
        # Slot dedup pengingat milik data DEMO dipulihkan (lihat RUN_STARTED_AT): pesan
        # simulasi/dilewati tidak pernah pergi, jadi membuangnya mengembalikan bahan uji
        # manusia — bukan menghapus jejak pengiriman nyata.
        "slot_dedup_demo_dipulihkan": db.wa_reminders.delete_many(
            {"org_id": ORG, "created_at": {"$gte": RUN_STARTED_AT},
             "status": {"$in": list(RESTORABLE)}}).deleted_count,
    }
    return {k: v for k, v in counts.items() if v}


def send_mode() -> str:
    """Mode kirim pengingat yang sedang berlaku (`simulasi` / `nyata`).

    Perangkat uji WAJIB memeriksanya sebelum menekan `POST /reminders/run`: di lingkungan
    berkredensial WhatsApp nyata, menjalankan pengingat berarti mengirim pesan sungguhan ke
    pelanggan demo. Itu bukan uji, itu insiden.
    """
    try:
        r = api("GET", "/reminders/settings", login("finlead@sipro.co.id"))
        return ((r.json().get("data") or {}).get("mode") or "?") if r.ok else "?"
    except Exception:                                     # noqa: BLE001
        return "?"


def orphans() -> dict:
    unit_ids = set(_ids("units", {}))
    deal_ids = set(_ids("deals", {}))
    cust_ids = set(_ids("customers", {}))
    lead_ids = set(_ids("leads", {}))
    ho_ids = set(_ids("unit_handovers", {}))
    spk_ids = set(_ids("spk", {}))
    return {
        "proyek_uji_tersisa": db.projects.count_documents({TAG: True}),
        "unit_uji_tersisa": db.units.count_documents({"$or": [{TAG: True},
                                                              {"code": UNIT_CODE}]}),
        "pelanggan_uji_tersisa": db.customers.count_documents({"$or": [{TAG: True},
                                                                       {"phone": PHONE}]}),
        "retensi_uji_tersisa": db.subcon_retentions.count_documents({TAG: True}),
        "pengingat_uji_tersisa": db.wa_reminders.count_documents(
            {"$or": [{TAG: True}, {"phone": PHONE}]}),
        # Pengingat YATIM: baris yang menunjuk rumah/pelanggan yang sudah tidak ada. Ini
        # pemeriksaan yang MENANGKAP cacat purge run pertama Fase 51 — pengingat termin
        # menyimpan `entity_id` tagihan AR, sehingga saringan lama (unit/deal/BAST saja)
        # melewatkannya dan POC mengaku "bahan uji dibuang bersih" padahal tidak.
        "pengingat_yatim": sum(1 for w in db.wa_reminders.find(
            {}, {"_id": 0, "unit_id": 1, "customer_id": 1, "lead_id": 1})
            if (w.get("unit_id") and w["unit_id"] not in unit_ids)
            or (w.get("customer_id") and w["customer_id"] not in cust_ids)
            or (w.get("lead_id") and w["lead_id"] not in lead_ids)),
        "bast_tanpa_unit": sum(1 for h in db.unit_handovers.find({}, {"_id": 0, "unit_id": 1})
                               if h.get("unit_id") not in unit_ids),
        "klaim_tanpa_bast": sum(1 for c in db.warranty_claims.find(
            {"handover_id": {"$ne": None}}, {"_id": 0, "handover_id": 1})
            if c["handover_id"] not in ho_ids),
        "retensi_tanpa_spk": sum(1 for r in db.subcon_retentions.find(
            {}, {"_id": 0, "spk_id": 1}) if r.get("spk_id") not in spk_ids),
        "tagihan_ar_tanpa_deal": sum(1 for i in db.ar_invoices.find(
            {"deal_id": {"$ne": None}}, {"_id": 0, "deal_id": 1})
            if i["deal_id"] not in deal_ids),
        "akun_portal_yatim": sum(1 for p in db.portal_users.find({}, {"_id": 0,
                                                                     "customer_id": 1})
                                 if p.get("customer_id")
                                 and p["customer_id"] not in cust_ids),
        "unit_terkunci_deal_hantu": db.units.count_documents(
            {"$or": [{"booked_by_deal": {"$nin": list(deal_ids) + [None]}},
                     {"sold_by_deal": {"$nin": list(deal_ids) + [None]}}]}),
        # Bahan uji MANUSIA ikut dibuktikan pulih: tidak boleh ada pengingat sisa yang lahir
        # selama perangkat uji berjalan, karena satu baris saja sudah membuat tombol
        # "Jalankan sekarang" menjawab "sudah diingatkan periode ini" untuk pembeli demo.
        "slot_dedup_demo_terpakai": db.wa_reminders.count_documents(
            {"org_id": ORG, "created_at": {"$gte": RUN_STARTED_AT}}),
    }


if __name__ == "__main__":
    import json
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "purge":
        print("purge:", json.dumps(purge(), ensure_ascii=False))
    elif len(sys.argv) > 1 and sys.argv[1] == "make":
        w = make()
        print("unit:", w["unit"]["code"], "retensi:", w["subcon"]["retention"]["id"],
              "klaim:", (w["claim"] or {}).get("number"))
    print("orphans:", json.dumps(orphans(), ensure_ascii=False))
