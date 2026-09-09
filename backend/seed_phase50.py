"""seed_phase50.py — data DEMO idempoten untuk Fase 50 (serah terima unit & garansi).

Kenapa seed ini membuat CERITANYA SENDIRI (bukan menumpang unit demo yang sudah ada):

1. **Serah terima mengubah keadaan rumah selamanya** (`units.status = handed_over`). Kalau
   seed menyerahkan rumah yang dipakai uji lain (mis. A-01 yang menjadi bahan uji progres,
   punch list, dan AR), uji itu kehilangan bahannya dan gate berikutnya merah bukan karena
   kode salah.
2. **Masa garansi butuh tanggal serah terima yang berbeda-beda** supaya semua keadaan bisa
   dicoba: garansi yang masih aktif, yang hampir habis, dan yang sudah lewat. Karena itu satu
   rumah diserahkan JAUH di masa lalu (400 hari) dan satu rumah lagi disiapkan bersih tetapi
   BELUM diserahkan — supaya tombol "Terbitkan BAST" benar-benar bisa dicoba di layar.
3. **Jalur uang memakai mesin yang sama dengan aplikasi** (`finance_engine`): AR dibuat lalu
   dilunasi lewat penerimaan sungguhan, jadi subledger tetap tie-out dengan buku besar. Angka
   demo yang "diketik langsung" akan membuat gate keuangan merah dengan benar.

Semua dokumen bertanda `demo_batch="fase50"` + `demo_marker` sebagai kunci idempotensi.
"""
import logging
from datetime import date, timedelta

import finance_engine as fe
import handover_engine as ho
import warranty_engine as we
from core_utils import new_id, now_iso, today_iso_date
from db import ORG_ID, db

logger = logging.getLogger("sipro.seed")

BATCH = "fase50"
READY_MARKER = "unit_siap_bast"          # rumah bersih, BAST belum terbit (dicoba di layar)
DONE_MARKER = "unit_sudah_bast"          # rumah sudah diserahterimakan 400 hari lalu
CLAIM_MARKER = "klaim_garansi_berjalan"


def _days_ago(n: int) -> str:
    return (date.fromisoformat(today_iso_date()) - timedelta(days=n)).isoformat()


async def _pick_unit(org: str, taken: set) -> dict:
    """Rumah yang MASIH tersedia dan belum dipakai uji/seed lain (urut kode)."""
    async for u in db.units.find(
            {"org_id": org, "status": "available"},
            {"_id": 0, "id": 1, "code": 1, "price": 1, "project_id": 1}).sort("code", 1):
        if u["id"] in taken:
            continue
        # Jangan pakai rumah yang sudah punya jadwal pembangunan: jadwal itu bahan uji
        # progres/kalibrasi milik fase lain, dan progresnya belum 100%.
        if await db.build_schedules.count_documents({"org_id": org, "unit_id": u["id"]}):
            continue
        return u
    return None


async def _buyer_and_payment(org: str, unit: dict, name: str, phone: str,
                             marker: str, booked_on: str) -> dict:
    """Lead + deal + customer + AR yang DILUNASI lewat mesin keuangan sungguhan."""
    deal = await db.deals.find_one({"org_id": org, "demo_marker": marker}, {"_id": 0})
    if deal:
        await _repair_legacy(org, unit, deal, phone)
        return deal
    ts = f"{booked_on}T09:00:00+00:00"
    lead = {"id": new_id(), "org_id": org, "name": name, "phone": phone,
            "source": "walk_in", "stage": "booking", "demo_batch": BATCH,
            "demo_marker": marker, "created_by": "seed", "created_at": ts, "updated_at": ts}
    await db.leads.insert_one(dict(lead))
    deal = {"id": new_id(), "org_id": org, "lead_id": lead["id"], "unit_id": unit["id"],
            "project_id": unit.get("project_id"), "assigned_to": "sales@sipro.co.id",
            # `completed` = transaksi tuntas menurut Kamus Data `deal_status`
            # (reserved/booked/completed/cancelled). Sempat tertulis "sold" — nilai di LUAR
            # kamus, sehingga unitnya tampak "terjual tanpa transaksi" di gate invarian
            # bisnis dan nilainya hilang dari metrik penjualan.
            "status": "completed", "price": int(unit.get("price") or 0),
            "booking_fee": 5_000_000,
            "reserved_at": ts, "reserved_until": ts, "booked_at": ts,
            "notes": ("Data DEMO — rumah lunas untuk mencoba serah terima (BAST) & masa "
                      "garansi."),
            "demo_batch": BATCH, "demo_marker": marker,
            "created_by": "seed", "created_at": ts, "updated_at": ts}
    await db.deals.insert_one(dict(deal))
    deal.pop("_id", None)
    cust = {"id": new_id(), "org_id": org, "lead_id": lead["id"], "deal_id": deal["id"],
            "name": name, "phone": phone,
            # NIK adalah natural key pelanggan (dijaga audit duplikasi). Pelanggan demo tanpa
            # NIK membuat dua baris bertabrakan pada kunci (org_id, nik=null) dan dilaporkan
            # sebagai duplikat — pembeli sungguhan selalu punya KTP di berkas legalnya.
            "nik": f"32760150{phone[-8:]}", "demo_batch": BATCH, "demo_marker": marker,
            # `kyc_status` adalah TAHAP pelanggan (Kamus Data `kyc_status`) yang dipakai
            # laporan umur tahap Fase 41. Pelanggan tanpa tahap tidak pernah ikut dihitung
            # jam tahapnya — barisnya hilang dari laporan tanpa ada yang sadar.
            "kyc_status": "verified", "kyc_files": [],
            "created_by": "seed", "created_at": ts, "updated_at": ts}
    await db.customers.insert_one(dict(cust))
    await db.units.update_one({"id": unit["id"], "org_id": org}, {"$set": {
        # `booked_by_deal` adalah tautan yang DIBACA seluruh aplikasi (site plan, build
        # engine, invarian bisnis) untuk menemukan transaksi milik rumah; `sold_by_deal`
        # saja membuat rumah tampak "terjual tanpa deal".
        "status": "sold", "sold_by_deal": deal["id"], "booked_by_deal": deal["id"],
        "deal_id": deal["id"],
        "lead_id": lead["id"], "customer_id": cust["id"], "payment_status": "lunas",
        "updated_at": ts}})
    await fe.create_ar_for_deal(deal, org_id=org, actor="seed")
    inv = await db.ar_invoices.find_one({"org_id": org, "deal_id": deal["id"]},
                                        {"_id": 0, "outstanding": 1})
    if inv and int(inv.get("outstanding") or 0) > 0:
        # Pelunasan memakai jalur resmi (jurnal kas & piutang ikut terbentuk) supaya
        # subledger tetap tie-out dengan buku besar.
        await fe.apply_receipt(deal["id"], int(inv["outstanding"]), "transfer",
                               "Pelunasan (data demo) — rumah siap serah terima",
                               "seed", org)
    await db.ar_invoices.update_one({"org_id": org, "deal_id": deal["id"]},
                                    {"$set": {"demo_batch": BATCH, "demo_marker": marker}})
    return deal


async def _repair_legacy(org: str, unit: dict, deal: dict, phone: str) -> None:
    """Perbaiki baris demo Fase 50 yang lahir dari versi seed lama (idempoten).

    Seed lama menulis `deals.status = "sold"` (di luar Kamus Data), tidak mengisi
    `units.booked_by_deal`, dan membuat pelanggan tanpa NIK. Ketiganya membuat gate invarian
    bisnis & audit duplikasi MERAH dengan benar. Karena seed bersifat idempoten lewat
    `demo_marker`, baris lama tidak akan pernah diperbaiki sendiri — jadi diperbaiki di sini
    alih-alih meminta orang menghapus database.
    """
    ts = now_iso()
    if deal.get("status") not in ("reserved", "booked", "completed", "cancelled"):
        await db.deals.update_one({"id": deal["id"], "org_id": org},
                                  {"$set": {"status": "completed", "updated_at": ts}})
        logger.info("Seed Fase 50: status deal demo %s dibetulkan ke 'completed'", deal["id"])
    u = await db.units.find_one({"id": unit["id"], "org_id": org},
                                {"_id": 0, "booked_by_deal": 1, "status": 1}) or {}
    # Deal yang DIBATALKAN tidak boleh ditautkan ulang ke unitnya. Perbaikan ini pernah
    # menempelkan kembali `booked_by_deal` pada unit yang sudah sengaja dilepas ke stok oleh
    # pembatalan Fase 56 — akibatnya penahanan refund "menunggu penjualan ulang" HILANG
    # (deal yang batal itu sendiri dibaca sebagai "pembeli baru"), dan uang pembeli bisa
    # dikembalikan tanpa keputusan yang diminta ketentuan SPR.
    if not u.get("booked_by_deal") and deal.get("status") != "cancelled" \
            and u.get("status") != "available":
        await db.units.update_one({"id": unit["id"], "org_id": org},
                                  {"$set": {"booked_by_deal": deal["id"], "updated_at": ts}})
    await db.customers.update_many(
        {"org_id": org, "deal_id": deal["id"], "nik": None},
        {"$set": {"nik": f"32760150{phone[-8:]}", "updated_at": ts}})
    await db.customers.update_many(
        {"org_id": org, "deal_id": deal["id"],
         "kyc_status": {"$in": [None, ""]}},
        {"$set": {"kyc_status": "verified", "kyc_files": [], "updated_at": ts}})


async def _handover_inspection(org: str, unit: dict, marker: str) -> dict:
    """Inspeksi serah terima yang LULUS — sama seperti hasil finalisasi di aplikasi.

    Finalisasi inspeksi kategori `handover` di `inspection_router` menuliskan
    `construction_status = ready_handover`; seed meniru hasil akhirnya (bukan mengarang
    status baru) supaya daftar periksa serah terima punya bukti mutu yang sah.
    """
    existing = await db.inspections.find_one({"org_id": org, "demo_marker": marker},
                                             {"_id": 0})
    if existing:
        return existing
    ts = now_iso()
    doc = {
        "id": new_id(), "org_id": org, "project_id": unit.get("project_id"),
        "unit_id": unit["id"], "phase_id": None,
        "inspection_number": f"QC/DEMO50/{str(unit.get('code') or '')[-4:]}",
        "category": "handover", "title": "Inspeksi serah terima (data demo)",
        "items": [
            {"key": "atap", "label": "Atap & plafon tidak bocor", "result": "pass",
             "note": "Diperiksa saat hujan buatan."},
            {"key": "listrik", "label": "Semua titik lampu & saklar menyala", "result": "pass",
             "note": None},
            {"key": "air", "label": "Air bersih & saluran kotor lancar", "result": "pass",
             "note": None},
        ],
        "status": "passed", "pass_count": 3, "fail_count": 0, "punch_ids": [],
        "punch_created": False, "result_note": "Lulus tanpa temuan.",
        "finalized_by": "seed", "finalized_at": ts, "scheduled_date": None,
        "scheduled_by": None, "scheduled_note": None,
        "demo_batch": BATCH, "demo_marker": marker,
        "created_by": "seed", "created_at": ts, "updated_at": ts,
    }
    await db.inspections.insert_one(dict(doc))
    doc.pop("_id", None)
    await db.units.update_one({"id": unit["id"], "org_id": org}, {"$set": {
        "qc_status": "passed", "construction_status": "ready_handover", "updated_at": ts}})
    return doc


async def _ready_unit(org: str, taken: set) -> dict:
    """Rumah BERSIH yang belum diserahterimakan — supaya tombol BAST bisa dicoba di layar."""
    prior = await db.units.find_one({"org_id": org, "demo_marker": READY_MARKER},
                                    {"_id": 0, "id": 1, "code": 1, "price": 1,
                                     "project_id": 1})
    unit = prior or await _pick_unit(org, taken)
    if not unit:
        return {}
    if not prior:
        await db.units.update_one({"id": unit["id"], "org_id": org},
                                  {"$set": {"demo_batch": BATCH, "demo_marker": READY_MARKER}})
    await _buyer_and_payment(org, unit, "Ibu Ratna Demo", "+6281250000501",
                             READY_MARKER, _days_ago(120))
    await _handover_inspection(org, unit, f"{READY_MARKER}_qc")
    return {"unit_id": unit["id"], "code": unit.get("code")}


async def _handed_over_unit(org: str, taken: set) -> dict:
    """Rumah yang sudah diserahterimakan 400 hari lalu + dua klaim garansi demo."""
    prior = await db.units.find_one({"org_id": org, "demo_marker": DONE_MARKER},
                                    {"_id": 0, "id": 1, "code": 1, "price": 1,
                                     "project_id": 1})
    unit = prior or await _pick_unit(org, taken)
    if not unit:
        return {}
    if not prior:
        await db.units.update_one({"id": unit["id"], "org_id": org},
                                  {"$set": {"demo_batch": BATCH, "demo_marker": DONE_MARKER}})
    day = _days_ago(400)
    await _buyer_and_payment(org, unit, "Bapak Hendra Demo", "+6281250000502",
                             DONE_MARKER, _days_ago(430))
    await _handover_inspection(org, unit, f"{DONE_MARKER}_qc")

    handover = await ho.active_handover(org, unit["id"])
    if not handover:
        handover = await ho.issue(
            org, unit["id"], "seed", handed_over_at=day,
            received_by="Bapak Hendra Demo",
            note=("Data DEMO — rumah diserahkan 400 hari lalu supaya masa garansi "
                  "finishing sudah lewat sementara struktur masih aktif."),
            meter_air="0148", meter_listrik="7742", keys_handed=3)
        await db.unit_handovers.update_one({"id": handover["id"], "org_id": org}, {"$set": {
            "demo_batch": BATCH, "demo_marker": DONE_MARKER,
            "issued_at": f"{day}T09:00:00+00:00", "created_at": f"{day}T09:00:00+00:00"}})

    # Klaim 1 — bagian yang masa garansinya SUDAH LEWAT: dijawab jujur (tercatat & ditolak).
    if not await db.warranty_claims.count_documents(
            {"org_id": org, "demo_marker": f"{CLAIM_MARKER}_expired"}):
        expired = await we.create_claim(
            org, unit_id=unit["id"], category="finishing", title="Cat kamar mandi mengelupas",
            description=("Data DEMO — keluhan masuk setelah masa garansi finishing "
                         "berakhir, supaya jawaban 'lewat masa garansi' bisa dilihat."),
            source="komplain_cs", actor="seed")
        await db.warranty_claims.update_one({"id": expired["id"], "org_id": org},
                                            {"$set": {"demo_batch": BATCH,
                                                      "demo_marker": f"{CLAIM_MARKER}_expired"}})

    # Klaim 2 — bagian yang MASIH bergaransi: diterima & sedang dikerjakan (ada pekerjaannya).
    if not await db.warranty_claims.count_documents(
            {"org_id": org, "demo_marker": CLAIM_MARKER}):
        # Kategori STRUKTUR dipilih dengan sengaja: masa garansinya panjang (setelan bawaan
        # 120 bulan), jadi klaim ini PASTI masih aktif walau rumahnya diserahkan 400 hari lalu
        # — kalau memakai kategori pendek (plumbing 6 bulan), seed akan menghasilkan klaim
        # yang justru ditolak dan cerita "klaim berjalan" hilang dari demo.
        active = await we.create_claim(
            org, unit_id=unit["id"], category="struktur",
            title="Retak rambut pada kolom teras",
            description=("Data DEMO — klaim yang masih dalam masa garansi, sudah "
                         "diterima dan melahirkan pekerjaan perbaikan."),
            source="portal_pembeli", actor="seed")
        await db.warranty_claims.update_one({"id": active["id"], "org_id": org},
                                            {"$set": {"demo_batch": BATCH,
                                                      "demo_marker": CLAIM_MARKER}})
        if active.get("state") == "diajukan":
            await we.decide(org, active["id"], accept=True, actor="seed",
                            reason=("Masih dalam masa garansi struktur; dijadwalkan "
                                    "pemeriksaan & suntik epoxy."),
                            assigned_to="site@sipro.co.id")
    return {"unit_id": unit["id"], "code": unit.get("code"),
            "handover": (handover or {}).get("number")}


async def seed_phase50(org: str = ORG_ID) -> dict:
    """Idempoten: dijalankan berkali-kali tanpa menduplikasi cerita demo."""
    taken = set()
    ready = await _ready_unit(org, taken)
    if ready.get("unit_id"):
        taken.add(ready["unit_id"])
    done = await _handed_over_unit(org, taken)
    out = {"siap_bast": ready.get("code"), "sudah_bast": done.get("code"),
           "bast": done.get("handover"),
           "klaim": await db.warranty_claims.count_documents({"org_id": org,
                                                              "demo_batch": BATCH})}
    logger.info("Seed Fase 50: %s", out)
    return out
