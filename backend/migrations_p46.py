"""MIGRASI Fase 46 — izin lama dinaikkan menjadi izin BERTINGKAT (idempoten).

Sebelum fase ini `permits` hanya punya `project_id`. Supaya Unit 360 & Papan Unit bisa
menanyakan "izin apa yang berlaku untuk unit ini", setiap izin harus menyatakan OBJEK yang
dilekatinya. Migrasi ini:

  * mengisi `scope="project"` + `scope_id=project_id` untuk izin lama — nilainya TIDAK
    ditebak: izin lama memang dibuat pada tingkat proyek;
  * TIDAK mengarang `expiry_at`. Izin lama tanpa masa berlaku tetap kosong dan dilaporkan
    apa adanya (`expiry_known=false`), karena menebak tanggal berlaku izin = memalsukan
    dokumen legal;
  * menambah indeks pencarian (`org_id+scope+scope_id`, `org_id+expiry_at`) agar pencarian
    izin per objek dan sapuan kedaluwarsa tidak memindai seluruh koleksi.
"""
import logging

from db import ORG_ID, db

logger = logging.getLogger("sipro.migrations.p46")


async def backfill_permit_scope(org: str = ORG_ID) -> dict:
    """Izin lama → `scope=project`. Aman diulang; tidak menyentuh izin yang sudah bertingkat."""
    out = {"scoped": 0, "scope_id_filled": 0}
    cur = db.permits.find({"org_id": org,
                           "$or": [{"scope": {"$in": [None, ""]}},
                                   {"scope": {"$exists": False}}]},
                          {"_id": 0, "id": 1, "project_id": 1})
    async for p in cur:
        await db.permits.update_one({"id": p["id"]}, {"$set": {
            "scope": "project", "scope_id": p.get("project_id")}})
        out["scoped"] += 1
    res = await db.permits.update_many(
        {"org_id": org, "scope": "project",
         "$or": [{"scope_id": {"$in": [None, ""]}}, {"scope_id": {"$exists": False}}]},
        [{"$set": {"scope_id": "$project_id"}}])
    out["scope_id_filled"] = res.modified_count
    return out


async def ensure_indexes() -> dict:
    """Indeks pencarian izin per objek + sapuan kedaluwarsa (bukan indeks unik)."""
    made = []
    for keys, name in (([("org_id", 1), ("scope", 1), ("scope_id", 1)], "ix_permits_scope"),
                       ([("org_id", 1), ("expiry_at", 1)], "ix_permits_expiry"),
                       ([("org_id", 1), ("requirement_code", 1)], "ix_permits_req")):
        try:
            await db.permits.create_index(keys, name=name)
            made.append(name)
        except Exception as e:                                   # pragma: no cover
            logger.warning("Index %s gagal: %s", name, e)
    return {"indexes": made}


async def run(org: str = ORG_ID) -> dict:
    out = {**await backfill_permit_scope(org), **await ensure_indexes()}
    if out["scoped"]:
        logger.info("Fase 46: %s izin lama dinaikkan ke izin bertingkat (scope=project).",
                    out["scoped"])
    return out
