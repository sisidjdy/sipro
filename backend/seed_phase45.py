"""seed_phase45.py — data demo TARGET & MASTER ANGGARAN (idempoten).

Kenapa seed ini ada: dua layar baru Fase 45 (Target & Budget, Realisasi RAB) tidak bisa
dibuktikan pada database bersih tanpa satu target aktif dan beberapa item anggaran. Tanpa
data, yang terlihat hanyalah keadaan kosong — dan keadaan kosong tidak bisa membuktikan
drill 3 lapis, status waspada/overbudget, maupun jejak revisi.

Yang ditulis di sini (semua BERSANDAR pada data yang sudah ada, bukan angka karangan):

  * satu **item anggaran konstruksi** yang MENAUT SELURUH item RAB proyek. Rencananya TIDAK
    disimpan — ia dihitung dari Σ `boq_items`, jadi tidak ada dua angka anggaran konstruksi.
  * beberapa **item anggaran operasional** ber-aturan `by_gl_account` yang menunjuk akun beban
    yang BENAR-BENAR ada di bagan akun (komisi, pemasaran, umum & administrasi, pajak, bunga).
    Realisasinya otomatis muncul dari jurnal yang sudah terbit — bukan diisi tangan.
  * satu item **overhead ber-aturan `manual`** dengan rencana kecil + satu pencatatan manual
    yang MELEWATI rencananya, sehingga keadaan **overbudget** dan peringatannya benar-benar
    bisa dilihat & diuji (bukan hanya "kalau nanti melewati").
  * satu item **marketing ber-aturan `by_cost_ref`** yang SENGAJA belum ditaut dokumen apa pun,
    supaya keadaan jujur "belum ada dokumen biaya yang menaut item ini" ikut terlihat.
  * satu **target proyek aktif** dengan metode bawaan `linear_remaining` dan horizon tahun
    berjalan; realisasinya dibaca dari `deals` (tidak pernah diinput).

Ditandai `demo_batch="fase45"` sehingga bisa dikenali, tidak pernah dobel, dan mudah dibuang.
"""
import logging
from datetime import datetime, timezone

import budget_reports as br
import target_store as tstore
from core_utils import new_id, now_iso
from db import ORG_ID, db

logger = logging.getLogger("sipro.seed")
BATCH = "fase45"

# (kode, kategori, aturan, akun GL, rencana, penanggung jawab, keterangan)
OPEX_ITEMS = [
    ("OPS-KOMISI", "komisi_fee", "by_gl_account", "6-1100", 60_000_000, "finance_manager",
     "Komisi sales & fee mitra yang dibukukan pada akun Beban Komisi."),
    ("OPS-MARKETING", "marketing", "by_gl_account", "6-1200", 40_000_000, "dm_supervisor",
     "Biaya pemasaran (iklan, materi, aktivasi) pada akun Beban Pemasaran."),
    ("OPS-UMUM", "operasional", "by_gl_account", "6-1300", 25_000_000, "project_manager",
     "Biaya umum & administrasi proyek (ATK, retribusi, operasional lapangan)."),
    ("OPS-PAJAK", "pajak", "by_gl_account", "6-1400", 120_000_000, "finance_manager",
     "Beban pajak yang diakrualkan atas transaksi penjualan."),
    ("OPS-BUNGA", "pembiayaan", "by_gl_account", "6-1600", 150_000_000, "finance_manager",
     "Bunga & provisi fasilitas pembangunan (akun Beban Bunga & Provisi Bank)."),
]


async def seed_phase45(org_id: str = ORG_ID) -> dict:
    proj = await db.projects.find_one({"org_id": org_id}, {"_id": 0, "id": 1, "name": 1})
    if not proj:
        return {"skipped": "belum ada proyek"}
    pid, pname = proj["id"], proj.get("name")
    made = {"budget_items": 0, "manual_entries": 0, "targets": 0}
    ts = now_iso()

    async def put(code: str, doc: dict) -> str:
        existing = await db.budget_items.find_one(
            {"org_id": org_id, "project_id": pid, "code": code}, {"_id": 0, "id": 1})
        if existing:
            return existing["id"]
        row = {"id": new_id(), "org_id": org_id, "project_id": pid, "project_name": pname,
               "cluster_id": None, "unit_id": None, "code": code, "currency": "IDR",
               "boq_item_ids": [], "gl_account": None, "period": "project", "revision": [],
               "alerts": [], "alert_level": "aman", "active": True, "order": 0,
               "demo_batch": BATCH, "created_by": "seed", "created_at": ts,
               "updated_at": ts, **doc}
        await db.budget_items.insert_one(row)
        made["budget_items"] += 1
        return row["id"]

    # 1) Konstruksi — rencananya DIHITUNG dari RAB (tidak disimpan di sini).
    boq = await db.boq_items.find({"org_id": org_id, "project_id": pid},
                                  {"_id": 0, "id": 1}).to_list(4000)
    if boq:
        await put("RAB-KONSTRUKSI", {
            "category": "konstruksi", "name": "Konstruksi (ringkasan RAB)",
            "description": "Meringkas seluruh item RAB proyek. Rencananya dihitung dari Σ item "
                           "RAB (read-only) supaya tidak ada dua angka anggaran konstruksi.",
            "planned_amount": 0, "match_rule": "by_boq_item",
            "boq_item_ids": [b["id"] for b in boq], "owner_role": "project_manager",
            "order": 1})

    # 2) Operasional & lain-lain — realisasi otomatis dari jurnal yang sudah terbit.
    for i, (code, cat, rule, acc, planned, role, desc) in enumerate(OPEX_ITEMS, start=2):
        await put(code, {"category": cat, "name": desc.split("(")[0].strip(),
                         "description": desc, "planned_amount": planned, "match_rule": rule,
                         "gl_account": acc, "owner_role": role, "order": i})

    # 3) Overhead manual yang SUDAH overbudget — supaya status merah & peringatannya nyata.
    over_id = await put("OPS-OVERHEAD", {
        "category": "overhead", "name": "Overhead kantor proyek",
        "description": "Biaya yang dibayar di luar sistem (sewa direksi keet, listrik "
                       "sementara). Dicocokkan manual, jadi setiap rupiah wajib beralasan.",
        "planned_amount": 8_000_000, "match_rule": "manual",
        "owner_role": "project_manager", "order": 8})
    if not await db.budget_manual_entries.find_one({"budget_item_id": over_id}, {"_id": 0}):
        await br.add_manual_entry(
            org_id, over_id, amount=11_500_000, actor="seed", ref_no="KWT/DK/2026/07",
            note="Sewa direksi keet + listrik sementara Jul-Ags 2026 (kuitansi manual)")
        made["manual_entries"] += 1

    # 4) Marketing ber-`cost_ref` yang SENGAJA belum ditaut dokumen apa pun.
    await put("MKT-BROSUR", {
        "category": "marketing", "name": "Materi promosi & brosur",
        "description": "Menunggu dokumen biaya (PO/kas bon) yang menaut item ini. Sengaja "
                       "dibiarkan kosong supaya keadaan 'belum ada dokumen' bisa dilihat.",
        "planned_amount": 15_000_000, "match_rule": "by_cost_ref",
        "owner_role": "dm_supervisor", "order": 9})

    # 5) Satu target proyek AKTIF dengan metode bawaan.
    year = datetime.now(timezone.utc).year
    name = f"Target {year}"
    existing = await db.project_targets.find_one(
        {"org_id": org_id, "project_id": pid, "name": name}, {"_id": 0, "id": 1})
    if not existing:
        price = await tstore.avg_price_of(org_id, project_id=pid)
        units = await db.units.count_documents({"org_id": org_id, "project_id": pid})
        target = await tstore.create_target(org_id, {
            "project_id": pid, "name": name, "scope": "project", "basis": "both",
            "method": "linear_remaining",
            "horizon": {"start": f"{year}-01", "end": f"{year}-12"},
            "unit_target": units or 12,
            "revenue_target": (units or 12) * price["avg_price"],
            "recalc_policy": {"mode": "monthly", "keep_total": True, "lock_past": True},
            "assumptions": {"avg_price": price["avg_price"], "opex_monthly": 0,
                            "growth_pct": 0},
            "note": "Target demo: unit = seluruh unit terdaftar pada proyek, pendapatan = "
                    "unit × harga rata-rata unit yang benar-benar berharga.",
        }, actor="seed")
        await db.project_targets.update_one(
            {"id": target["id"]},
            {"$set": {"status": "active", "activated_at": ts, "activated_by": "seed",
                      "demo_batch": BATCH}})
        made["targets"] += 1

    if any(made.values()):
        logger.info("Seed Fase 45 (target & anggaran): %s", made)
    return made
