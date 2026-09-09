"""SEED Fase 53 — template dokumen owner, skema bayar `[DOC]`, dan contoh pembeli+kontrak.

Idempoten. Tiga hal yang dipasang:

1. **Empat template asli owner** (`SPR_CASH`, `SPR_CASH_STAGED`, `SPR_KPR`, `SPKT`) sebagai
   DATA di `document_templates` — sebelum Fase 53 hanya ada tiga teks pendek karangan seed.
2. **Tiga skema pembayaran menurut dokumen owner** (`cash_keras`, `cash_bertahap`, `kpr`)
   sehingga termin AR bisa mengikuti kontrak, bukan skema bawaan "Standar KPR (DP 20%)".
3. **Backfill pembeli demo**: deal demo yang sudah `booked` DAN sudah punya baris pembeli
   (hasil seed lama, tertaut lewat `customers.lead_id`) diberi KONTRAK, supaya layar
   Kontrak & Legal punya data nyata untuk dilihat/diuji tanpa mengarang apa pun.
   Deal lain TIDAK disentuh: konversi adalah keputusan manusia.
"""
import logging

import contracts_engine as ce
import docgen
from db import ORG_ID, db

logger = logging.getLogger("sipro.seed53")


async def seed_phase53(org: str = ORG_ID) -> dict:
    out = {"templates": {}, "schemes": [], "contracts": 0}
    out["templates"] = await docgen.ensure_templates(org)
    for scheme in ce.SCHEMES:
        doc = await ce.ensure_payment_scheme(org, scheme)
        out["schemes"].append(doc["code"])

    # --- backfill kontrak untuk pembeli demo yang SUDAH ada (tanpa membuat pembeli baru)
    for cust in await db.customers.find({"org_id": org, "lead_id": {"$ne": None}},
                                        {"_id": 0}).to_list(50):
        deal = await db.deals.find_one(
            {"org_id": org, "lead_id": cust["lead_id"],
             "status": {"$in": ["booked", "completed"]}}, {"_id": 0})
        if not deal:
            continue
        if await db.contracts.find_one({"org_id": org, "deal_id": deal["id"]}, {"_id": 0}):
            continue
        fin = await db.financing_apps.find_one({"org_id": org, "deal_id": deal["id"]},
                                              {"_id": 0, "id": 1, "plafon": 1})
        scheme = "kpr" if fin else "cash_bertahap"
        contract = await ce.ensure_contract(org, deal, cust, scheme, "seed")
        # Komponen biaya demo TIDAK dikarang: dibiarkan "belum diisi" supaya layar
        # memperlihatkan keadaan jujurnya (dan tombol "lengkapi biaya" punya alasan).
        if fin:
            await db.financing_apps.update_one(
                {"id": fin["id"]},
                {"$set": {"contract_id": contract["id"], "customer_id": cust["id"],
                          "kpr_stage": "berkas_lengkap"}})
            if fin.get("plafon"):
                await db.contracts.update_one(
                    {"id": contract["id"]},
                    {"$set": {"costs.plafon_kredit": int(fin["plafon"])}})
        out["contracts"] += 1
    logger.info("Seed Fase 53: template=%s skema=%s kontrak_backfill=%s",
                out["templates"], out["schemes"], out["contracts"])
    return out
