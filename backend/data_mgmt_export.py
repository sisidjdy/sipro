"""Ekspor master data (per entitas skema) menjadi baris Excel — kebalikan dari impor."""
from db import db
from data_mgmt_schema import ENTITIES

_FIELD_MAP = {  # kolom skema → field dokumen bila namanya berbeda
    "units": {"land_area": "luas_tanah", "building_area": "luas_bangunan", "is_hook": "corner",
              "block_code": "block"},
}
_SORT = {"units": [("code", 1)], "accounts": [("code", 1)], "users": [("name", 1)]}


async def _project_codes(org: str) -> dict:
    rows = await db.projects.find({"org_id": org}, {"_id": 0, "id": 1, "code": 1}).to_list(500)
    return {r["id"]: r.get("code") for r in rows}


async def export_rows(org: str) -> dict:
    pcodes = await _project_codes(org)
    out = {}
    for ent in ENTITIES:
        q = {"org_id": org}
        if ent["key"] == "users":
            q["role"] = {"$ne": "super_admin"}
        cur = db[ent["collection"]].find(q, {"_id": 0})
        for f, d in _SORT.get(ent["key"], [("created_at", 1)]):
            cur = cur.sort(f, d)
        docs = await cur.to_list(20000)
        fmap = _FIELD_MAP.get(ent["key"], {})
        rows = []
        for d in docs:
            row = {}
            for f in ent["fields"]:
                k = f["key"]
                if k == "project_code":
                    row[k] = pcodes.get(d.get("project_id"))
                elif k == "project_codes":
                    row[k] = [pcodes.get(p) for p in d.get("project_ids") or [] if pcodes.get(p)]
                elif k == "password":
                    row[k] = None
                else:
                    row[k] = d.get(fmap.get(k, k))
            rows.append(row)
        out[ent["key"]] = rows
    return out


async def master_counts(org: str) -> list:
    res = []
    for ent in ENTITIES:
        res.append({"key": ent["key"], "sheet": ent["sheet"], "collection": ent["collection"],
                    "count": await db[ent["collection"]].count_documents({"org_id": org})})
    return res
