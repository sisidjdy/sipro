"""seed_phase43.py — data demo KAMPANYE & BIAYA IKLAN (idempoten).

Kenapa seed ini ada: lead demo sudah membawa nama kampanye ('cluster-a-meta',
'harmony-google-brand', 'tiktok-awareness') sejak Fase 40, tetapi kampanyenya sendiri tidak
pernah terdaftar. Akibatnya seluruh layar kinerja pemasaran akan kosong pada database bersih
dan tidak ada yang bisa dibuktikan — padahal datanya SUDAH ada di lead.

Yang ditulis di sini:
  * `campaigns` untuk setiap nama kampanye yang BENAR-BENAR dipakai lead demo (jadi angka
    atribusi bukan karangan: pembilangnya lead nyata di database);
  * `ad_spend` demo untuk DUA kampanye saja, berlabel `source="manual"` — kampanye ketiga
    SENGAJA dibiarkan tanpa biaya supaya keadaan jujur "data biaya belum lengkap" benar-benar
    terlihat di layar dan bisa diuji gate. Satu kampanye juga hanya terisi sebagian hari
    supaya keadaan `partial` ikut terbukti;
  * tidak ada satu pun baris `ad_spend` bertanda `source="api"` — tidak ada tarikan API yang
    pernah terjadi, jadi menandainya begitu akan menipu pembaca laporan.

Ditandai `demo_batch="fase43"` sehingga bisa dikenali, tidak pernah dobel, dan mudah dibuang.
"""
import logging
from datetime import datetime, timedelta, timezone

import ads_engine as eng
from db import db, ORG_ID

logger = logging.getLogger("sipro.seed")

# (nama kampanye seperti tercatat pada lead, platform, tujuan, id platform, anggaran)
CAMPAIGNS = [
    {"name": "cluster-a-meta", "platform": "meta", "objective": "leads",
     "external_id": "23851000000001", "budget_daily": 1_500_000, "budget_total": 45_000_000,
     "audience_note": "Radius 15 km dari lokasi proyek, usia 27-45, minat KPR & rumah pertama.",
     "spend_days": 8, "spend_base": 1_450_000},
    {"name": "harmony-google-brand", "platform": "google", "objective": "traffic",
     "external_id": "9911002233", "budget_daily": 750_000, "budget_total": 22_500_000,
     "audience_note": "Kata kunci merek + 'perumahan syariah' + 'rumah subsidi' area kota.",
     # Sengaja hanya sebagian hari: keadaan `partial` harus bisa dilihat pemakai.
     "spend_days": 4, "spend_base": 810_000},
    {"name": "tiktok-awareness", "platform": "tiktok", "objective": "awareness",
     "external_id": None, "budget_daily": 0, "budget_total": 12_000_000,
     "audience_note": "Konten walkthrough unit contoh; belum ada rekap biaya dari tim.",
     # TANPA biaya: bukti bahwa CPL/CAC/ROAS ditampilkan sebagai 'belum lengkap', bukan 0.
     "spend_days": 0, "spend_base": 0},
]


def _date(days_ago: int) -> str:
    return (datetime.now(timezone.utc).date() - timedelta(days=days_ago)).isoformat()


async def seed_phase43(org_id: str = ORG_ID) -> dict:
    out = {"campaigns": 0, "spend_rows": 0, "skipped": 0}
    used = await db.leads.distinct("campaign", {"org_id": org_id})
    known = {str(c).strip().lower() for c in used if c}
    for spec in CAMPAIGNS:
        existing = await db.campaigns.find_one(
            {"org_id": org_id, "platform": spec["platform"], "name": spec["name"]},
            {"_id": 0, "id": 1})
        if existing:
            campaign = existing
            out["skipped"] += 1
        else:
            campaign = await eng.create_campaign({
                "platform": spec["platform"], "name": spec["name"],
                "external_id": spec["external_id"], "objective": spec["objective"],
                "status": "active", "budget_daily": spec["budget_daily"],
                "budget_total": spec["budget_total"], "audience_note": spec["audience_note"],
                "start_date": _date(20), "end_date": None, "source": "manual",
                "note": ("Kampanye demo Fase 43 — namanya sama dengan nilai `campaign` pada "
                         "lead demo supaya atribusi menyambung ke data nyata."),
            }, org_id=org_id, actor="seed")
            await db.campaigns.update_one({"id": campaign["id"]},
                                          {"$set": {"demo_batch": "fase43"}})
            out["campaigns"] += 1
            if spec["name"].lower() not in known:
                logger.info("Kampanye demo %s belum dipakai lead mana pun (atribusinya akan "
                            "kosong sampai ada lead dari kampanye ini).", spec["name"])
        for i in range(spec["spend_days"]):
            date_iso = _date(i + 1)
            row = {
                "platform": spec["platform"], "campaign_id": campaign["id"],
                "campaign_external_id": spec["external_id"], "campaign_name": spec["name"],
                "adset_id": "", "adset_name": None, "ad_id": "", "ad_name": None,
                "date": date_iso,
                # Variasi kecil per hari (bukan angka rata yang mustahil di kehidupan nyata),
                # tetap deterministik supaya seed idempoten & gate bisa menghitung ulang.
                "spend": spec["spend_base"] + (i % 4) * 55_000,
                "impressions": 12_000 + (i % 5) * 900, "clicks": 260 + (i % 7) * 11,
                "leads_platform": 3 + (i % 3), "currency": eng.CURRENCY,
            }
            status, doc = await eng.upsert_spend(row, org_id=org_id, source="manual",
                                                actor="seed")
            if status == "inserted":
                await db.ad_spend.update_one({"id": doc["id"]},
                                             {"$set": {"demo_batch": "fase43"}})
                out["spend_rows"] += 1
    if out["campaigns"] or out["spend_rows"]:
        logger.info("Seed Fase 43: %s kampanye, %s baris biaya iklan demo (source=manual).",
                    out["campaigns"], out["spend_rows"])
    return out
