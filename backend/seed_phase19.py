"""Seed EPIC 3.3 (Phase 19) — contoh setoran pajak -> jurnal GL.

Menandai satu catatan pajak sebagai 'paid' + NTPN, lalu memposting jurnal
akrual (Dr Beban Pajak / Cr Utang Pajak) & setoran (Dr Utang Pajak / Cr Bank)
agar alur pajak->GL terlihat langsung di Buku Besar. Idempotent.
"""
from db import db, ORG_ID
import tax_engine as tx
import gl_engine as gl


async def seed_tax_setoran(org_id, ts):
    rec = await db.tax_records.find_one(
        {"org_id": org_id, "type": "pph", "status": {"$ne": "paid"}}, {"_id": 0})
    if not rec:
        rec = await db.tax_records.find_one({"org_id": org_id, "status": {"$ne": "paid"}}, {"_id": 0})
    if not rec:
        return
    if await db.journal_entries.find_one({"org_id": org_id, "source_event": f"tax.setor:{rec['id']}"}):
        return
    ntpn = "SIPRO" + str(rec["id"]).replace("-", "")[:11].upper()
    await db.tax_records.update_one(
        {"id": rec["id"], "org_id": org_id},
        {"$set": {"status": "paid", "report_date": ts, "paid_date": ts[:10],
                  "ntpn": ntpn, "updated_at": ts}})
    fresh = await db.tax_records.find_one({"id": rec["id"], "org_id": org_id}, {"_id": 0})
    enriched = (await tx.enrich_records(org_id, [fresh]))[0]
    je_a = await gl.post_tax_accrual(org_id, enriched)
    je_p = await gl.post_tax_payment(org_id, enriched)
    refs = {}
    if je_a:
        refs["gl_accrual_entry_no"] = je_a["entry_no"]
    if je_p:
        refs["gl_setor_entry_no"] = je_p["entry_no"]
        refs["gl_setor_entry_id"] = je_p["id"]
    if refs:
        await db.tax_records.update_one({"id": rec["id"], "org_id": org_id}, {"$set": refs})
