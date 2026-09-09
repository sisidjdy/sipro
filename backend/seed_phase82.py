"""Seed demo Fase 82 — Kas & Bank: rekening escrow kedua, kas kecil site, dan transaksi internal
contoh (tarik tunai diposting supaya Kas Besar tidak negatif + satu pengajuan menunggu approve).
Idempoten lewat `demo_batch = "fase82"`.
"""
import cash_bank as cb
from core_utils import now_iso
from db import ORG_ID, db

BATCH = "fase82"


async def seed_phase82(org_id: str = ORG_ID):
    if await db.cash_transfers.find_one({"org_id": org_id, "demo_batch": BATCH}, {"_id": 0, "id": 1}):
        return
    await cb.ensure_setup(org_id)
    ts = now_iso()
    if not await db.bank_accounts.find_one({"org_id": org_id, "account_no": "8800123456"}):
        await cb.create_account(org_id, {
            "kind": "bank", "name": "Rekening Escrow", "bank_name": "Bank BCA",
            "account_no": "8800123456", "holder": "PT SIPRO Land", "opening_balance": 250_000_000,
            "opening_date": f"{ts[:4]}-01-01", "note": "Rekening penampungan pencairan KPR.",
            "demo_batch": BATCH}, "system")
    if not await db.bank_accounts.find_one({"org_id": org_id, "account_no": "KAS-02"}):
        await cb.create_account(org_id, {
            "kind": "cash", "name": "Kas Kecil Site", "account_no": "KAS-02", "opening_balance": 0,
            "note": "Kas kecil proyek untuk pengeluaran harian lapangan.", "demo_batch": BATCH}, "system")
    bank = await cb.default_account(org_id, "bank")
    kas = await cb.default_account(org_id, "cash")
    kas_kecil = await db.bank_accounts.find_one({"org_id": org_id, "account_no": "KAS-02"}, {"_id": 0})
    month = ts[:7]
    tr = await cb.create_transfer(org_id, {
        "kind": "tarik_tunai", "from_account_id": bank["id"], "to_account_id": kas["id"],
        "amount": 25_000_000, "fee": 0, "date": f"{month}-01",
        "reference": "TRX-DEMO-001", "note": "Tarik tunai untuk operasional kas kantor."},
        "finance@sipro.co.id")
    await cb.approve_transfer(org_id, tr["id"], "owner@sipro.co.id")
    pending = await cb.create_transfer(org_id, {
        "kind": "isi_kas_kecil", "from_account_id": bank["id"], "to_account_id": kas_kecil["id"],
        "amount": 5_000_000, "fee": 6_500, "date": ts[:10],
        "reference": "TRX-DEMO-002", "note": "Pengisian kas kecil site minggu ini."},
        "finance@sipro.co.id")
    await db.cash_transfers.update_many({"id": {"$in": [tr["id"], pending["id"]]}},
                                        {"$set": {"demo_batch": BATCH}})
