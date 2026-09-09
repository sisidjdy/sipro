"""seed_phase57.py — skema pembayaran BAWAAN menjadi data yang bisa disunting (Fase 57A).

Sebelum fase ini termin cash keras / cash bertahap / KPR hanya ada di dalam kode; barisnya
di `payment_schemes` baru lahir saat ada kontrak yang diaktifkan. Akibatnya layar Pusat
Konfigurasi › Skema Pembayaran akan KOSONG pada organisasi baru — pemakai tidak punya
contoh untuk disalin, dan menyimpulkan fiturnya tidak ada.

Seed ini menuliskan ketiga skema bawaan (nilainya tetap dibaca dari Pusat Konfigurasi,
bukan angka mati) sebagai baris biasa: bisa disunting, dinonaktifkan, atau disalin. Idempoten
per kode — skema yang sudah ada TIDAK PERNAH ditimpa, supaya penyuntingan pemakai tidak
hilang saat aplikasi dinyalakan ulang.
"""
import logging

import contracts_engine as cx
import payment_scheme_engine as psx
from core_utils import new_id, now_iso
from db import ORG_ID, db

logger = logging.getLogger("sipro.seed")

KINDS = ("cash_keras", "cash_bertahap", "kpr")


async def seed_phase57(org: str = ORG_ID) -> dict:
    dibuat, dilewati = [], []
    for kind in KINDS:
        ada = await db.payment_schemes.find_one({"org_id": org, "code": kind},
                                               {"_id": 0, "id": 1})
        if ada:
            dilewati.append(kind)
            continue
        spec = await cx._builtin_spec(org, kind)
        ts = now_iso()
        await db.payment_schemes.insert_one({
            "id": new_id(), "org_id": org, "code": kind, "name": spec["name"], "kind": kind,
            "items": psx.normalize_terms(spec["items"]), "active": True,
            "is_default": kind == "kpr", "applies_project_ids": [], "source": "DOC",
            "note": ("Skema bawaan menurut dokumen owner. Boleh disunting, disalin, atau "
                     "dinonaktifkan — nilainya tidak lagi terkunci di dalam kode."),
            "created_by": "seed", "created_at": ts, "updated_at": ts})
        dibuat.append(kind)
    # Baris lama (Fase 16 & 53) belum punya `kind`; tanpa itu ia tidak akan pernah cocok
    # dengan kontrak mana pun dan hanya menjadi baris bingung di layar. Yang berkode sama
    # dengan jenis (`cash_keras`/`cash_bertahap`/`kpr`) mengambil jenis dari kodenya —
    # menebak jenisnya akan membuat skema KPR tampil sebagai cash bertahap.
    n = 0
    for kind in KINDS:
        r = await db.payment_schemes.update_many(
            {"org_id": org, "code": kind, "kind": {"$nin": [kind]}},
            {"$set": {"kind": kind, "active": True}})
        n += r.modified_count
    r = await db.payment_schemes.update_many(
        {"org_id": org, "code": {"$in": [None, ""]}, "kind": {"$in": [None, ""]}},
        {"$set": {"kind": "cash_bertahap", "active": True, "applies_project_ids": [],
                  "source": "warisan"}})
    n += r.modified_count
    if dibuat:
        logger.info("Seed Fase 57: skema pembayaran bawaan dibuat: %s", ", ".join(dibuat))
    return {"dibuat": dibuat, "dilewati": dilewati,
            "warisan_dilengkapi": n}
