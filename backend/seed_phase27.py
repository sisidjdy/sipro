"""Seed demo Fase 27 — Kas Bon, Aset Tetap, Pembiayaan Korporat, Marketing Fee.

Dipisah dari `seed.py` (sudah menyentuh batas compliance 800 baris). IDEMPOTEN:
dikawal marker `finance_configs.key = "seed_phase27"`, sehingga restart backend tidak
menggandakan transaksi maupun jurnalnya.

Data demo dibuat MELALUI ENGINE yang sama dengan yang dipakai UI (bukan insert mentah),
jadi setiap angka punya jurnal seimbang dan lolos gate invarian — bukan data palsu.
"""
import logging

import fixed_assets as fa
import loans as ln
import marketing_fee as mfe
import petty_cash as pc
from core_utils import now_iso
from db import db, ORG_ID
from models_p27 import (AgentCreate, AssetCreate, CashAdvanceCreate, CashbonExpenseItem,
                        LoanCreate, MarketingFeeCreate)
from p27_utils import current_period, month_add, period_of

logger = logging.getLogger("sipro.seed")

FINANCE = "finance@sipro.co.id"
SITE = "site@sipro.co.id"
MANAGER = "manager@sipro.co.id"

# (name, category, tax_group, method, cost, salvage, funding, location)
DEMO_ASSETS = [
    ("Toyota Avanza operasional pemasaran", "kendaraan", "kelompok_2", "garis_lurus",
     245_000_000, 20_000_000, "bank", "Kantor pemasaran Cluster Asri"),
    ("Laptop & workstation tim desain (5 unit)", "komputer_it", "kelompok_1", "garis_lurus",
     72_500_000, 0, "bank", "Kantor pusat"),
    ("Bangunan kantor pemasaran & showroom", "bangunan", "bangunan_permanen", "garis_lurus",
     640_000_000, 0, "bank", "Cluster Asri Blok A"),
    ("Excavator mini sewa-beli proyek", "mesin_peralatan", "kelompok_3", "garis_lurus",
     385_000_000, 35_000_000, "utang_usaha", "Site Cluster Asri"),
]
# Vendor wajib untuk aset yang dibeli secara utang (tagihan AP otomatis terbentuk).
CREDIT_VENDOR = "CV Alat Berat Nusantara"

DEMO_AGENTS = [
    ("PT Griya Mitra Andalan", "broker_kantor", "PT Griya Mitra Andalan", "+628121230001",
     "griya@mitra.co.id", "01.234.567.8-901.000", "BCA", "5271234567"),
    ("Hendra Wijaya", "agen_properti", "Century 21 Bintaro", "+628121230002",
     "hendra.w@example.com", "12.345.678.9-012.000", "Mandiri", "1440009988"),
    ("Dewi Kartika (referral pembeli)", "referral_pembeli", None, "+628121111111",
     "dewi.kartika@example.com", None, "BNI", "0987654321"),
]


async def _already_seeded(org_id: str) -> bool:
    marker = await db.finance_configs.find_one({"org_id": org_id, "key": "seed_phase27"},
                                              {"_id": 0, "key": 1})
    if marker:
        return True
    # Jaring pengaman bila marker hilang tapi datanya sudah ada.
    return bool(await db.fixed_assets.count_documents({"org_id": org_id}))


async def _seed_petty_cash(org_id: str) -> int:
    """1 kas bon masih berjalan (belum dipertanggungjawabkan) + 1 sudah selesai."""
    made = 0
    a1 = await pc.create_advance(CashAdvanceCreate(
        purpose="Retribusi & material kecil pekerjaan drainase Blok A",
        amount=7_500_000, category="biaya_proyek",
        needed_date=month_add(now_iso(), 0), note="Kebutuhan lapangan mingguan"),
        SITE, "Eko Site", org_id)
    await pc.approve_advance(a1["id"], FINANCE, "Disetujui sesuai kebutuhan lapangan", org_id)
    await pc.disburse_advance(a1["id"], 7_500_000, "kas", "Tunai via kasir", FINANCE, org_id)
    made += 1

    a2 = await pc.create_advance(CashAdvanceCreate(
        purpose="Konsumsi open house & transport tim pemasaran",
        amount=3_000_000, category="pemasaran_promosi", note="Open house akhir pekan"),
        MANAGER, "Sinta Manajer", org_id)
    await pc.approve_advance(a2["id"], FINANCE, "Disetujui", org_id)
    await pc.disburse_advance(a2["id"], 3_000_000, "bank", "Transfer ke rekening pemohon",
                              FINANCE, org_id)
    await pc.settle_advance(a2["id"], [
        CashbonExpenseItem(category="pemasaran_promosi",
                           description="Snack & minuman open house", amount=1_450_000),
        CashbonExpenseItem(category="transport", description="BBM & tol tim pemasaran",
                           amount=850_000),
        CashbonExpenseItem(category="atk_kantor", description="Cetak brosur & spanduk kecil",
                           amount=420_000),
    ], "Sisa dikembalikan ke kas", MANAGER, org_id)
    made += 1
    return made


async def _seed_assets(org_id: str) -> int:
    """4 aset tetap dengan tanggal perolehan 3 bulan lalu + penyusutan 3 periode terposting."""
    acquired = month_add(now_iso(), -3)
    for (name, cat, tax_group, method, cost, salvage, funding, location) in DEMO_ASSETS:
        await fa.create_asset(AssetCreate(
            name=name, category=cat, tax_group=tax_group, method=method, cost=cost,
            salvage_value=salvage, acquired_date=acquired, funding=funding,
            vendor=CREDIT_VENDOR if funding == "utang_usaha" else None,
            location=location, note="Data demo Fase 27"), FINANCE, org_id)
    period = period_of(acquired)
    cur = current_period()
    posted = 0
    for _ in range(12):
        if period > cur:
            break
        res = await fa.run_depreciation(period, FINANCE, org_id)
        posted += res["posted"]
        y, m = int(period[:4]), int(period[5:7]) + 1
        if m > 12:
            y, m = y + 1, 1
        period = f"{y:04d}-{m:02d}"
    logger.info("Seed Fase 27: %s aset tetap, %s entri penyusutan terposting",
                len(DEMO_ASSETS), posted)
    return len(DEMO_ASSETS)


async def _seed_loan(org_id: str) -> int:
    """1 fasilitas kredit investasi aktif dengan 2 angsuran sudah dibayar."""
    start = month_add(now_iso(), -3)
    loan = await ln.create_loan(LoanCreate(
        lender="BCA", lender_type="bank", loan_type="kredit_investasi",
        principal=5_000_000_000, interest_rate_pct=11.5, tenor_months=36,
        amortization_method="anuitas", start_date=start, provision_fee=50_000_000,
        collateral="Sertifikat HGB induk Cluster Asri Blok A",
        note="Fasilitas pembangunan tahap 1"), FINANCE, org_id)
    active = await ln.activate_loan(loan["id"], "bank", start,
                                    "Pencairan penuh tahap 1", FINANCE, org_id)
    for item in (active.get("schedule") or [])[:2]:
        await ln.pay_installment(loan["id"], item["no"], item["total"], "bank",
                                 item["due_date"], "Autodebet rekening operasional",
                                 FINANCE, org_id)
    return 1


async def _seed_marketing_fee(org_id: str) -> int:
    """3 agen + 2 pengajuan fee (1 disetujui belum dibayar, 1 sudah dibayar)."""
    agents = []
    for (name, atype, company, phone, email, npwp, bank, acct) in DEMO_AGENTS:
        agents.append(await mfe.create_agent(AgentCreate(
            name=name, agent_type=atype, company=company, phone=phone, email=email,
            npwp=npwp, bank_name=bank, bank_account=acct,
            note="Mitra demo Fase 27"), MANAGER, org_id))
    deal = await db.deals.find_one({"org_id": org_id, "price": {"$gt": 0}}, {"_id": 0},
                                   sort=[("created_at", 1)])
    if not deal:
        return len(agents)
    fee1 = await mfe.create_fee(MarketingFeeCreate(
        agent_id=agents[0]["id"], deal_id=deal["id"], basis="percent", value=2.5,
        trigger="ppjb", pph_pct=2, note="Fee broker atas PPJB unit"), MANAGER, org_id)
    await mfe.approve_fee(fee1["id"], FINANCE, "Sesuai perjanjian kerja sama", org_id)

    fee2 = await mfe.create_fee(MarketingFeeCreate(
        agent_id=agents[2]["id"], deal_id=deal["id"], basis="fixed", value=2_500_000,
        trigger="booking", pph_pct=0, note="Referral pembeli (booking)"), MANAGER, org_id)
    await mfe.approve_fee(fee2["id"], FINANCE, "Disetujui", org_id)
    await mfe.pay_fee(fee2["id"], None, "bank", "Transfer referral", FINANCE, org_id)
    return len(agents)


async def seed_phase27(org_id: str = ORG_ID) -> dict:
    """Seed demo 4 modul Fase 27. Idempoten & aman dijalankan tiap startup."""
    if await _already_seeded(org_id):
        return {"skipped": True}
    if not await db.users.count_documents({"org_id": org_id, "email": FINANCE}):
        return {"skipped": True, "reason": "user demo belum ada"}
    try:
        advances = await _seed_petty_cash(org_id)
        assets = await _seed_assets(org_id)
        loans_made = await _seed_loan(org_id)
        agents = await _seed_marketing_fee(org_id)
    except Exception:  # noqa: BLE001
        logger.exception("Seed Fase 27 gagal (dibiarkan agar startup tetap jalan)")
        return {"skipped": False, "error": True}
    await db.finance_configs.update_one(
        {"org_id": org_id, "key": "seed_phase27"},
        {"$set": {"org_id": org_id, "key": "seed_phase27", "seeded_at": now_iso()}},
        upsert=True)
    result = {"cash_advances": advances, "fixed_assets": assets, "loans": loans_made,
              "agents": agents}
    logger.info("Seed Fase 27 selesai: %s", result)
    return result
