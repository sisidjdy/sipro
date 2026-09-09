"""Bersihkan data uji Fase 71 (nama mengandung 'Uji') + reset override aturan penomoran."""
import asyncio
import os
import sys

sys.path.insert(0, "/app/backend")
from db import db  # noqa: E402


async def main():
    for key in ("spk", "master:cluster", "quotation", "master:unit"):
        await db.numbering_rules.delete_many({"key": key})
    left = await db.numbering_rules.find({}, {"_id": 0, "key": 1}).to_list(100)
    print("override tersisa:", [r["key"] for r in left])

    projs = await db.projects.find({"name": {"$regex": "Uji", "$options": "i"}}, {"_id": 0, "id": 1}).to_list(500)
    pids = [p["id"] for p in projs]
    print("proyek uji:", len(pids))
    for coll in ("units", "blocks", "clusters"):
        r = await db[coll].delete_many({"project_id": {"$in": pids}})
        print(coll, "dihapus", r.deleted_count)
    print("projects dihapus", (await db.projects.delete_many({"id": {"$in": pids}})).deleted_count)
    for coll in ("vendors", "subcontractors", "unit_types", "addons"):
        r = await db[coll].delete_many({"name": {"$regex": "Uji", "$options": "i"}})
        print(coll, "dihapus", r.deleted_count)
    r = await db.spk.delete_many({"title": {"$regex": "Uji penomoran", "$options": "i"}})
    print("spk dihapus", r.deleted_count)


asyncio.run(main())
