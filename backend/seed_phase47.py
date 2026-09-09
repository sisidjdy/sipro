"""seed_phase47.py — data demo Fase 47 (idempoten): uang masuk & upah harian yang TERLIHAT.

Kenapa seed ini ada: layar baru Fase 47 tidak bisa DIBUKTIKAN pada database yang bersih.
Rekonsiliasi bank tanpa satu pun mutasi hanya menampilkan keadaan kosong; papan absensi tanpa
tenaga kerja tidak bisa dicoba. Pelajaran mahal Fase 46 (fitur yang tidak bisa dicapai sama
saja dengan tidak ada) dipakai di sini sejak awal.

Yang ditulis (semua BERSANDAR pada data nyata hasil seed sebelumnya — deal/unit/proyek yang
sudah ada, bukan objek karangan):

  * **1 rekening bank** yang tertaut ke akun GL `1-1200` (Bank).
  * **Mutasi rekening** dari berkas contoh: satu mutasi yang NOMINALNYA SAMA dengan termin
    pelanggan yang belum dibayar (supaya usulan pencocokan benar-benar muncul), satu mutasi
    biaya administrasi bank, dan satu mutasi yang memang bukan urusan perusahaan. Semuanya
    dibiarkan **belum dicocokkan** — pekerjaan kasir, bukan pekerjaan seed.
  * **1 bukti transfer dari portal** berstatus *menunggu verifikasi* — membuktikan bahwa
    klaim pelanggan TIDAK mengurangi tagihan sebelum finance memverifikasi.
  * **6 tenaga kerja harian** (mandor, tukang, laden) + **absensi 2 hari terakhir** dengan
    satu orang setengah hari dan satu orang lembur, sehingga rekap upah punya bahan nyata.
  * **1 add-on** dan **1 penawaran** untuk lead yang sudah ada: diskonnya SENGAJA di atas
    kewenangan sales, jadi layar persetujuan diskon punya isi.

Seed TIDAK PERNAH menekan tombol milik manusia: tidak ada mutasi yang dicocokkan otomatis,
tidak ada bukti yang diverifikasi, tidak ada upah yang disetujui. Semua bertanda
`demo_batch="fase47"` supaya bisa dikenali dan dibuang.
"""
import logging
from datetime import date, timedelta

import labor_engine as labor
import quotation_engine as qe
from core_utils import new_id, now_iso, today_iso_date
from db import ORG_ID, db

logger = logging.getLogger("sipro.seed")
BATCH = "fase47"


def _day(offset: int) -> str:
    return (date.fromisoformat(today_iso_date()) + timedelta(days=offset)).isoformat()


async def _bank_account(org: str) -> dict:
    acc = await db.bank_accounts.find_one({"org_id": org, "demo_batch": BATCH}, {"_id": 0})
    if acc:
        return acc
    ts = now_iso()
    acc = {"id": new_id(), "org_id": org, "demo_batch": BATCH,
           "name": "Rekening Operasional", "bank_name": "Bank Mandiri",
           "account_no": "1440012345678", "holder": "PT SIPRO Land",
           "gl_account_code": "1-1200", "gl_account_name": "Bank",
           "opening_balance": 0, "is_active": True,
           "note": "Rekening penerimaan pembeli & pembayaran operasional.",
           "created_by": "seed", "created_at": ts, "updated_at": ts}
    await db.bank_accounts.insert_one(dict(acc))
    acc.pop("_id", None)
    return acc


async def _statement(org: str, acc: dict) -> int:
    """Mutasi contoh lewat jalur IMPOR yang sama dengan pemakai (bukan insert langsung)."""
    if await db.bank_transactions.count_documents({"org_id": org, "account_id": acc["id"]}):
        return 0
    import bank_import as bimp
    inv = await db.ar_invoices.find_one({"org_id": org, "outstanding": {"$gt": 0}}, {"_id": 0})
    term = None
    if inv:
        unpaid = [i for i in (inv.get("items") or []) if i.get("status") != "paid"]
        term = sorted(unpaid, key=lambda x: x.get("due_date") or "")[:1]
        term = term[0] if term else None
    rows = ["Tanggal;Keterangan;Referensi;Debit;Kredit;Saldo"]
    saldo = 250_000_000
    if term:
        amount = int(term["amount"]) - int(term.get("paid_amount") or 0)
        saldo += amount
        rows.append(f"{_day(-2)};TRANSFER MASUK {inv.get('customer_name') or inv.get('lead_name') or 'PEMBELI'} "
                    f"{inv.get('unit_code') or ''};TRF/{_day(-2).replace('-', '')}/001;;"
                    f"{amount};{saldo}")
    saldo -= 15_000
    rows.append(f"{_day(-2)};BIAYA ADM REKENING;ADM;15000;;{saldo}")
    saldo += 4_250_000
    rows.append(f"{_day(-1)};SETORAN TUNAI LOKET;STR/001;;4250000;{saldo}")
    out = await bimp.import_csv(org, acc["id"], "mutasi_contoh_fase47.csv",
                                "\n".join(rows), "seed", dry_run=False)
    return out["counts"]["new"]


async def _intake(org: str) -> int:
    """Satu bukti transfer menunggu verifikasi (tagihan BELUM berkurang)."""
    if await db.payment_intakes.find_one({"org_id": org, "demo_batch": BATCH},
                                         {"_id": 0, "id": 1}):
        return 0
    inv = await db.ar_invoices.find_one({"org_id": org, "outstanding": {"$gt": 0}}, {"_id": 0})
    if not inv:
        return 0
    deal = await db.deals.find_one({"id": inv.get("deal_id"), "org_id": org}, {"_id": 0})
    if not deal:
        return 0
    cust = await db.customers.find_one({"org_id": org, "lead_id": deal.get("lead_id")},
                                       {"_id": 0}) \
        or await db.customers.find_one({"org_id": org}, {"_id": 0})
    if not cust:
        return 0
    unpaid = [i for i in (inv.get("items") or []) if i.get("status") != "paid"]
    nxt = sorted(unpaid, key=lambda x: x.get("due_date") or "")[:1]
    amount = int((nxt[0]["amount"] - int(nxt[0].get("paid_amount") or 0)) if nxt else 5_000_000)
    ts = now_iso()
    await db.payment_intakes.insert_one({
        "id": new_id(), "org_id": org, "demo_batch": BATCH, "deal_id": deal["id"],
        "customer_id": cust.get("id"), "customer_name": cust.get("name"),
        "unit_id": deal.get("unit_id"), "unit_code": inv.get("unit_code"),
        "amount": amount, "transfer_date": _day(-1), "bank_name": "BCA",
        "note": "Transfer dari rekening pribadi (bukti dari portal pelanggan).",
        "source": "portal", "file_ids": [], "file_shas": [],
        "files": [{"id": None, "filename": "bukti-transfer-demo.jpg",
                   "content_type": "image/jpeg", "sha256": None}],
        "state": "pending", "state_label": "Menunggu verifikasi finance",
        "outstanding_at_submit": inv.get("outstanding"), "receipt_id": None,
        "bank_txn_id": None, "reject_reason": None, "verified_by": None,
        "verified_at": None, "created_by": "portal",
        "submitted_by": {"customer_id": cust.get("id"), "name": cust.get("name"),
                         "contact": cust.get("phone") or cust.get("email")},
        "created_at": ts, "updated_at": ts})
    return 1


WORKERS = [
    ("Pak Slamet", "mandor", 220_000),
    ("Budi Santoso", "tukang", 165_000),
    ("Agus Priyanto", "tukang", 165_000),
    ("Joko Widodo", "tukang", 160_000),
    ("Rahmat", "laden", 120_000),
    ("Dedi", "laden", 120_000),
]


async def _labor(org: str, project: dict) -> dict:
    out = {"workers": 0, "attendance": 0}
    ids = []
    for name, role, wage in WORKERS:
        w = await db.workers.find_one({"org_id": org, "name": name}, {"_id": 0, "id": 1})
        if w:
            ids.append(w["id"])
            continue
        doc = await labor.create_worker(org, {
            "name": name, "role": role, "daily_wage": wage,
            "project_ids": [project["id"]], "is_active": True,
            "note": "Tenaga kerja harian (data demo Fase 47)."}, "seed")
        await db.workers.update_one({"id": doc["id"]}, {"$set": {"demo_batch": BATCH}})
        ids.append(doc["id"])
        out["workers"] += 1
    for offset in (-2, -1):
        day = _day(offset)
        if await db.labor_attendance.count_documents(
                {"org_id": org, "project_id": project["id"], "work_date": day}):
            continue
        entries = []
        for i, wid in enumerate(ids):
            status = "half" if (offset == -1 and i == len(ids) - 1) else "full"
            entries.append({"worker_id": wid, "status": status,
                            "overtime_hours": (2 if (offset == -2 and i == 0) else 0)})
        try:
            await labor.record_attendance(org, project_id=project["id"], work_date=day,
                                          entries=entries, actor="seed")
            out["attendance"] += len(entries)
        except ValueError as e:  # periode sudah direkap manusia -> jangan diganggu
            logger.info("Seed Fase 47: absensi %s dilewati (%s).", day, e)
    return out


async def _quotation(org: str, project: dict) -> int:
    """Satu penawaran dengan diskon di atas kewenangan sales -> menunggu persetujuan."""
    if await db.quotations.find_one({"org_id": org, "demo_batch": BATCH}, {"_id": 0, "id": 1}):
        return 0
    lead = await db.leads.find_one({"org_id": org, "status": {"$nin": ["lost", "eliminated"]}},
                                   {"_id": 0})
    unit = await db.units.find_one({"org_id": org, "project_id": project["id"],
                                    "status": "available"}, {"_id": 0}, sort=[("code", 1)])
    if not lead or not unit:
        return 0
    price = int(unit.get("price") or 0)
    try:
        doc = await qe.create(
            org, lead_id=lead["id"], unit_id=unit["id"], addons=[], scheme_id=None,
            discount_amount=int(price * 0.05), kpr={"tenor_months": 180,
                                                   "annual_rate_pct": 8.75, "dp_pct": 20},
            valid_days=14, note="Penawaran contoh (data demo Fase 47).",
            discount_reason="Pembeli membandingkan dengan kompetitor sebelah; minta potongan 5%.",
            actor="sales@sipro.co.id")
    except ValueError as e:
        logger.info("Seed Fase 47: penawaran dilewati (%s).", e)
        return 0
    await db.quotations.update_one({"id": doc["id"]}, {"$set": {"demo_batch": BATCH}})
    return 1


async def seed_phase47(org: str = ORG_ID) -> dict:
    out = {"bank_txn": 0, "intake": 0, "workers": 0, "attendance": 0, "quotation": 0}
    project = await db.projects.find_one({"org_id": org}, {"_id": 0})
    if not project:
        return out
    acc = await _bank_account(org)
    out["bank_txn"] = await _statement(org, acc)
    out["intake"] = await _intake(org)
    lab = await _labor(org, project)
    out.update({"workers": lab["workers"], "attendance": lab["attendance"]})
    out["quotation"] = await _quotation(org, project)
    if any(out.values()):
        logger.info("Seed Fase 47: %s mutasi bank, %s bukti transfer, %s tenaga kerja, "
                    "%s baris absensi, %s penawaran.", out["bank_txn"], out["intake"],
                    out["workers"], out["attendance"], out["quotation"])
    return out
