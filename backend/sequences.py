"""Nomor dokumen atomik (counters) — mengganti pola `count_documents() + 1`.

Masalah yang diperbaiki (audit forensik):
1. RACE CONDITION: 9 tempat memakai `count_documents(...) + 1`. Dua request bersamaan
   menghasilkan NOMOR DOKUMEN YANG SAMA (SPK/PO/JV/PPJB/Faktur duplikat).
2. NOMOR BERGESER: jika dokumen dibatalkan/dihapus, count mengecil -> nomor terpakai
   dipakai lagi.
3. BOCOR ANTAR TENANT: beberapa pemakaian menghitung `org_id=ORG_ID` (org default),
   bukan org milik user -> tenant kedua menghasilkan nomor yang sama dengan tenant pertama.

Solusi: koleksi `counters` dengan find_one_and_update($inc) — atomik di level MongoDB,
per (org, scope, tahun).
"""
from pymongo import ReturnDocument

from db import db
from core_utils import now_iso


def _key(scope: str, org_id: str, year: str = None) -> str:
    return f"{org_id}|{scope}|{year}" if year else f"{org_id}|{scope}"


async def next_seq(scope: str, org_id: str, year: str = None) -> int:
    """Naikkan counter secara atomik dan kembalikan nilai baru (mulai dari 1)."""
    doc = await db.counters.find_one_and_update(
        {"_id": _key(scope, org_id, year)},
        {"$inc": {"seq": 1}, "$set": {"updated_at": now_iso(), "scope": scope,
                                       "org_id": org_id, "year": year}},
        upsert=True, return_document=ReturnDocument.AFTER,
    )
    return int(doc["seq"])


async def next_number(scope: str, org_id: str, *, prefix: str, width: int = 4,
                      year: str = None, sep: str = "/", context: dict = None) -> str:
    """Nomor berikutnya. Bila `scope` terdaftar di `numbering_registry`, pola/awalan/reset
    diambil dari aturan penomoran organisasi (bawaan = PREFIX/TAHUN/URUT, mis. SPK/2026/0001).
    `context` (project_id, unit_id, vendor_id, level, …) mengisi token konteks pola."""
    import numbering  # impor lokal: numbering memakai next_seq dari modul ini
    return await numbering.generate(scope, org_id, prefix=prefix, width=width, year=year,
                                    sep=sep, context=context)


async def ensure_at_least(scope: str, org_id: str, value: int, year: str = None) -> int:
    """Naikkan counter ke `value` bila masih di bawahnya (dipakai migrasi data lama)."""
    cur = await db.counters.find_one({"_id": _key(scope, org_id, year)}, {"_id": 0, "seq": 1})
    if cur and int(cur.get("seq", 0)) >= value:
        return int(cur["seq"])
    await db.counters.update_one(
        {"_id": _key(scope, org_id, year)},
        {"$set": {"seq": int(value), "updated_at": now_iso(), "scope": scope,
                  "org_id": org_id, "year": year}},
        upsert=True,
    )
    return int(value)


async def peek(scope: str, org_id: str, year: str = None) -> int:
    cur = await db.counters.find_one({"_id": _key(scope, org_id, year)}, {"_id": 0, "seq": 1})
    return int((cur or {}).get("seq", 0))
