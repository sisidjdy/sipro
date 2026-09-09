"""seed_phase56.py — data DEMO idempoten untuk Fase 56C (pembatalan & refund berjurnal).

## Kenapa seed ini perlu

Tab **Keuangan → Pembatalan & Refund** dan kartu keputusan pada profil pembeli TIDAK BISA
DICOBA manusia pada basis data demo, karena `cancellations` kosong: pengajuan hanya lahir
dari tombol Manajer Sales. Akibatnya fitur terpenting fase ini hanya bisa dibuktikan lewat
gate/POC — sementara orang yang membuka aplikasinya melihat halaman kosong dan menyimpulkan
fiturnya tidak ada (pelajaran yang sama dengan `seed_phase51`).

## Yang dibuat: SATU pengajuan MENUNGGU KEPUTUSAN

Sengaja berhenti di keadaan `diajukan`, karena di situlah keputusan MANUSIA berada:
Manajer Keuangan (`finlead@`) bisa benar-benar menekan Setujui/Tolak di layar, dan barisnya
terlihat di tab Keuangan. Seed **tidak** memutuskan, **tidak** menjurnal, dan **tidak**
melepas unit — menekan tombol milik manusia akan membuat data demo berbohong tentang siapa
yang memutuskan apa.

## Aturan yang dipatuhi

* **Memakai mesin sungguhan** (`cancellation_engine.request`), jadi nomor, hitungan, dan
  gerbangnya sama dengan yang dipakai pengguna.
* **Idempoten**: kalau sudah ada pengajuan (keadaan apa pun) di organisasi ini, seed berhenti.
* **Tidak merebut bahan uji fase lain**: kontrak dipilih yang masih berjalan, tanpa BAST/AJB,
  dan bukan bahan uji gate (nama pembeli berawalan `POC`/`GATE` dilewati).
"""
import logging

import cancellation_engine as cx
from db import ORG_ID, db

logger = logging.getLogger("sipro.seed")

REQUESTER = "manager@sipro.co.id"
# Penanda idempotensi: satu pengajuan demo saja, sekali seumur basis data — restart ulang
# tidak boleh menumpuk pengajuan palsu.
MARKER = "fase56"
REASON = ("Pembeli mengundurkan diri karena pengajuan KPR-nya ditolak bank dan tidak "
          "sanggup melanjutkan pembayaran tunai (contoh data demo)")


async def repair_stale_sold_links(org: str = ORG_ID) -> int:
    """Bersihkan tautan penjualan BASI pada unit yang sudah kembali ke stok (idempoten).

    Versi lama `cancellation_engine._release_unit` mengosongkan `booked_by_deal` tetapi
    membiarkan `sold_by_deal`/`sold_at`. Unit seperti itu berstatus `available` namun tetap
    mengaku "terjual" kepada setiap pembaca data (gate integritas menandainya "unit terjual
    tanpa ikatan lead/deal"). Basis data yang sudah pernah menjalankan pembatalan tidak akan
    pernah memperbaiki dirinya sendiri, jadi diperbaiki di sini.
    """
    res = await db.units.update_many(
        {"org_id": org, "status": "available",
         "$or": [{"sold_by_deal": {"$nin": [None, ""]}}, {"sold_at": {"$nin": [None, ""]}},
                 {"deal_id": {"$nin": [None, ""]}}, {"lead_id": {"$nin": [None, ""]}},
                 {"customer_id": {"$nin": [None, ""]}},
                 {"contract_id": {"$nin": [None, ""]}}]},
        {"$set": {"sold_by_deal": None, "sold_at": None, "deal_id": None, "lead_id": None,
                  "lead_name": None, "customer_id": None, "contract_id": None}})
    if res.modified_count:
        logger.info("Seed Fase 56: %s unit di stok dibersihkan dari tautan penjualan basi.",
                    res.modified_count)
    return res.modified_count


async def seed_phase56(org: str = ORG_ID) -> dict:
    await repair_stale_sold_links(org)
    if await db.cancellations.find_one({"org_id": org, "demo_seed": MARKER},
                                       {"_id": 0, "id": 1}):
        return {"pengajuan": 0, "alasan": "pengajuan demo sudah ada"}
    for contract in await db.contracts.find(
            {"org_id": org, "state": {"$nin": ["cancelled"]}}, {"_id": 0}).sort(
            "created_at", 1).to_list(50):
        nama = str(contract.get("customer_name") or "")
        if nama.upper().startswith(("POC", "GATE", "QA")):
            continue
        if await cx.blocks(org, contract):
            continue
        doc = await cx.request(org, contract, REQUESTER, REASON)
        await db.cancellations.update_one({"id": doc["id"]},
                                          {"$set": {"demo_seed": MARKER}})
        logger.info("Seed Fase 56: pengajuan pembatalan demo %s (kontrak %s) menunggu "
                    "keputusan Manajer Keuangan.", doc["number"], contract.get("number"))
        return {"pengajuan": 1, "number": doc["number"],
                "contract": contract.get("number")}
    return {"pengajuan": 0, "alasan": "tidak ada kontrak demo yang memenuhi syarat"}
