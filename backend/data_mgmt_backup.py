"""Backup (JSON penuh per organisasi) & restore, plus snapshot tersimpan di server.

Cakupan: semua koleksi ber-`org_id` milik org, dokumen `orgs` org itu, matriks
`permission_settings` (global), dan `file_blobs` (opsional — bisa besar). Restore membuat
snapshot pengaman dulu, dan akun admin yang menjalankan restore tidak boleh hilang.
"""
import base64
import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from bson import ObjectId
from pymongo.errors import BulkWriteError

from db import db
from core_utils import new_id, now_iso

logger = logging.getLogger("sipro.data_mgmt.backup")
FORMAT, VERSION = "sipro-backup", 1
SYSTEM_COLLS = {"data_backups"}
_SAFE = re.compile(r"[^A-Za-z0-9_.-]+")


def backup_dir(org: str) -> Path:
    p = Path(os.environ["BACKUP_DIR"]) / _SAFE.sub("-", org)
    p.mkdir(parents=True, exist_ok=True)
    return p


def _json_default(o):
    if isinstance(o, datetime):
        return o.isoformat()
    if isinstance(o, ObjectId):
        return str(o)
    if isinstance(o, bytes):
        return {"$b64": base64.b64encode(o).decode()}
    return str(o)


def _clean(doc: dict) -> dict:
    if isinstance(doc.get("_id"), ObjectId):
        doc.pop("_id")
    return doc


async def _org_filter(coll: str, org: str, include_files: bool):
    if coll == "orgs":
        return {"id": org}
    if coll == "permission_settings":
        return {}
    if coll == "file_blobs":
        return {"path": {"$regex": f"/{re.escape(org)}/"}} if include_files else None
    return {"org_id": org}


async def dump_org(org: str, actor: str, include_files: bool = False, label: str = "") -> dict:
    names = sorted(n for n in await db.list_collection_names()
                   if not n.startswith("system.") and n not in SYSTEM_COLLS)
    data, counts = {}, {}
    for coll in names:
        q = await _org_filter(coll, org, include_files)
        if q is None:
            continue
        docs = [_clean(d) async for d in db[coll].find(q)]
        if docs:
            data[coll] = docs
            counts[coll] = len(docs)
    org_doc = await db.orgs.find_one({"id": org}, {"_id": 0, "name": 1})
    return {"meta": {"format": FORMAT, "version": VERSION, "org_id": org,
                     "org_name": (org_doc or {}).get("name"), "created_at": now_iso(),
                     "created_by": actor, "include_files": include_files, "label": label,
                     "collections": counts, "documents": sum(counts.values())},
            "data": data}


def to_bytes(payload: dict) -> bytes:
    return json.dumps(payload, ensure_ascii=False, default=_json_default).encode("utf-8")


def parse_backup(content: bytes) -> dict:
    try:
        payload = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise ValueError(f"Berkas bukan JSON backup yang sah: {e}")
    meta = payload.get("meta") or {}
    if meta.get("format") != FORMAT or not isinstance(payload.get("data"), dict):
        raise ValueError("Format berkas tidak dikenal — gunakan berkas hasil Backup JSON SIPRO.")
    if int(meta.get("version", 0)) > VERSION:
        raise ValueError("Versi backup lebih baru dari aplikasi ini.")
    return payload


# ------------------------------------------------------------------ snapshot di server
async def save_snapshot(org: str, actor: str, include_files: bool, label: str,
                        kind: str = "manual") -> dict:
    payload = await dump_org(org, actor, include_files, label)
    raw = to_bytes(payload)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    fname = f"{stamp}__{_SAFE.sub('-', label or kind)[:40]}.json"
    (backup_dir(org) / fname).write_bytes(raw)
    rec = {"id": new_id(), "org_id": org, "filename": fname, "label": label or kind, "kind": kind,
           "size": len(raw), "include_files": include_files,
           "collections": payload["meta"]["collections"],
           "documents": payload["meta"]["documents"],
           "created_by": actor, "created_at": payload["meta"]["created_at"]}
    await db.data_backups.insert_one(dict(rec))
    rec.pop("_id", None)
    return rec


async def list_snapshots(org: str) -> list:
    return await db.data_backups.find({"org_id": org}, {"_id": 0}).sort("created_at", -1).to_list(200)


async def get_snapshot(org: str, sid: str) -> tuple:
    rec = await db.data_backups.find_one({"id": sid, "org_id": org}, {"_id": 0})
    if not rec:
        raise LookupError("Snapshot tidak ditemukan.")
    path = backup_dir(org) / rec["filename"]
    if not path.exists():
        raise LookupError("Berkas snapshot sudah tidak ada di server.")
    return rec, path


async def delete_snapshot(org: str, sid: str) -> dict:
    rec, path = await get_snapshot(org, sid)
    path.unlink(missing_ok=True)
    await db.data_backups.delete_one({"id": sid, "org_id": org})
    return {"deleted": True, "filename": rec["filename"]}


# ------------------------------------------------------------------ restore
async def _unique_indexes(coll: str) -> list:
    info = await db[coll].index_information()
    return [[k for k, _ in ix["key"]] for ix in info.values() if ix.get("unique")]


def _merge_key(d: dict, uniques: list):
    """Kunci upsert: _id → id → indeks unik koleksi yang semua fieldnya ada di dokumen."""
    if "_id" in d:
        return {"_id": d["_id"]}
    if d.get("id"):
        return {"id": d["id"]}
    for fields in uniques:
        if fields and all(f in d for f in fields):
            return {f: d[f] for f in fields}
    return None


async def restore(payload: dict, org: str, actor: str, mode: str, actor_user: dict) -> dict:
    """mode 'replace' = hapus data org pada koleksi yang ada di backup lalu isi ulang;
    'merge' = upsert per `id` (dokumen lain dibiarkan)."""
    if mode not in ("replace", "merge"):
        raise ValueError("Mode restore harus 'replace' atau 'merge'.")
    src_org = payload["meta"].get("org_id")
    pre = await save_snapshot(org, actor, include_files=True, label="pra-restore", kind="auto")
    report = {}
    for coll, docs in payload["data"].items():
        if coll in SYSTEM_COLLS or not isinstance(docs, list):
            continue
        deleted = inserted = updated = 0
        for d in docs:
            if "org_id" in d:
                d["org_id"] = org
            if coll == "orgs" and d.get("id") == src_org:
                d["id"] = org
        if mode == "replace":
            q = await _org_filter(coll, org, include_files=True)
            deleted = (await db[coll].delete_many(q)).deleted_count if q is not None else 0
            if docs:
                try:
                    await db[coll].insert_many([dict(d) for d in docs], ordered=False)
                    inserted = len(docs)
                except BulkWriteError as e:
                    inserted = int(e.details.get("nInserted", 0))
                    report.setdefault("_warnings", []).append(
                        f"{coll}: {len(docs) - inserted} dokumen ditolak indeks unik.")
        else:
            uniques = await _unique_indexes(coll)
            for d in docs:
                key = _merge_key(d, uniques)
                if key is None:
                    await db[coll].insert_one(dict(d))
                    inserted += 1
                    continue
                res = await db[coll].replace_one(key, dict(d), upsert=True)
                if res.upserted_id is not None:
                    inserted += 1
                else:
                    updated += 1
        report[coll] = {"deleted": deleted, "inserted": inserted, "updated": updated}
    if actor_user and not await db.users.find_one({"id": actor_user["id"]}):
        keep = {k: v for k, v in actor_user.items() if k != "_id"}
        await db.users.insert_one(keep)
        report["users"] = {**report.get("users", {}), "admin_restored": True}
    logger.warning("RESTORE %s oleh %s (org %s): %s koleksi", mode, actor, org, len(report))
    return {"mode": mode, "source_org": src_org, "snapshot_before": pre,
            "collections": report,
            "documents": sum(r["inserted"] + r["updated"] for r in report.values()
                             if isinstance(r, dict))}
