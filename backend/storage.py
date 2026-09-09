"""Object storage abstraction (config-driven, real-ready + honest fallback).

- Provider `emergent`: Emergent managed Object Storage via EMERGENT_LLM_KEY.
- Provider `mongo`:   fallback that stores bytes (base64) in `file_blobs` so uploads
                      keep working locally even without integration credentials.

The active provider is decided ONCE at startup (init_storage). Every file record in
Mongo stores its own `provider` + `storage_path`, so downloads always resolve
correctly regardless of the current default provider.
"""
import os
import base64
import asyncio
import hashlib
import logging

import requests

import photo_utils
from db import db, ORG_ID
from core_utils import new_id, now_iso

logger = logging.getLogger("sipro.storage")

STORAGE_URL = "https://integrations.emergentagent.com/objstore/api/v1/storage"
EMERGENT_KEY = os.environ.get("EMERGENT_LLM_KEY")
APP_NAME = "sipro"

_storage_key = None
_provider = None  # "emergent" | "mongo"

MIME_BY_EXT = {
    "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "gif": "image/gif",
    "webp": "image/webp", "pdf": "application/pdf", "json": "application/json",
    "csv": "text/csv", "txt": "text/plain", "doc": "application/msword",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


def guess_content_type(filename: str, provided: str = None) -> str:
    if provided and provided != "application/octet-stream":
        return provided
    ext = filename.rsplit(".", 1)[-1].lower() if "." in (filename or "") else ""
    return MIME_BY_EXT.get(ext, provided or "application/octet-stream")


def _init_emergent() -> str:
    global _storage_key
    resp = requests.post(f"{STORAGE_URL}/init", json={"emergent_key": EMERGENT_KEY}, timeout=20)
    resp.raise_for_status()
    _storage_key = resp.json()["storage_key"]
    return _storage_key


async def init_storage() -> str:
    """Decide provider once. `STORAGE_PROVIDER=mongo` forces mongo fallback;
    otherwise use real Emergent storage if key + network OK, else mongo."""
    global _provider
    if _provider:
        return _provider
    forced = os.environ.get("STORAGE_PROVIDER", "").strip().lower()
    if forced == "mongo":
        _provider = "mongo"
        logger.info("Object storage ready: provider=mongo (forced via STORAGE_PROVIDER=mongo)")
        return _provider
    if EMERGENT_KEY:
        try:
            await asyncio.to_thread(_init_emergent)
            _provider = "emergent"
            logger.info("Object storage ready: provider=emergent (managed)")
            return _provider
        except Exception as e:  # noqa: BLE001
            logger.warning("Emergent storage init failed (%s); using mongo fallback.", e)
    _provider = "mongo"
    logger.info("Object storage ready: provider=mongo (fallback; set EMERGENT_LLM_KEY for managed)")
    return _provider


def provider_name() -> str:
    return _provider or "mongo"


def _put_emergent(path: str, data: bytes, content_type: str) -> dict:
    key = _storage_key or _init_emergent()
    resp = requests.put(
        f"{STORAGE_URL}/objects/{path}",
        headers={"X-Storage-Key": key, "Content-Type": content_type},
        data=data, timeout=120,
    )
    resp.raise_for_status()
    return resp.json()


def _get_emergent(path: str):
    key = _storage_key or _init_emergent()
    resp = requests.get(f"{STORAGE_URL}/objects/{path}", headers={"X-Storage-Key": key}, timeout=60)
    resp.raise_for_status()
    return resp.content, resp.headers.get("Content-Type", "application/octet-stream")


async def _put_bytes(path: str, data: bytes, content_type: str) -> str:
    """Store bytes, return the provider actually used ('emergent' | 'mongo')."""
    prov = await init_storage()
    if prov == "emergent":
        try:
            await asyncio.to_thread(_put_emergent, path, data, content_type)
            return "emergent"
        except Exception as e:  # noqa: BLE001
            logger.warning("Emergent put failed (%s); storing in mongo.", e)
    await db.file_blobs.update_one(
        {"path": path},
        {"$set": {"path": path, "data_b64": base64.b64encode(data).decode(),
                  "content_type": content_type, "size": len(data)}},
        upsert=True,
    )
    return "mongo"


async def get_file_bytes(path: str, provider: str = None):
    prov = provider or provider_name()
    if prov == "emergent":
        return await asyncio.to_thread(_get_emergent, path)
    doc = await db.file_blobs.find_one({"path": path}, {"_id": 0})
    if not doc:
        raise FileNotFoundError(path)
    return base64.b64decode(doc["data_b64"]), doc.get("content_type", "application/octet-stream")


MAX_FILE_BYTES = 15 * 1024 * 1024  # 15 MB guard


async def save_file(*, data: bytes, filename: str, content_type: str, org_id: str,
                    owner_type: str, owner_id: str, uploaded_by: str,
                    doc_type: str = None, tag: str = "file", optimize: bool = True,
                    watermark_lines: list = None) -> dict:
    """Persist bytes + a Mongo `files` metadata record (source of truth). Returns record.

    Fase 30b: berkas GAMBAR dikompres (maks 1600 px, JPEG progresif), diberi watermark
    konteks (proyek/kavling + organisasi + tanggal WIB), dibuang metadata EXIF/GPS-nya,
    dan dibuatkan THUMBNAIL untuk grid galeri. Bila optimasi gagal (format aneh/berkas
    rusak), berkas ASLI tetap tersimpan — unggahan tidak pernah ikut gagal.
    """
    if not data:
        raise ValueError("File kosong.")
    if len(data) > MAX_FILE_BYTES:
        raise ValueError("Ukuran file melebihi 15 MB.")
    ct = guess_content_type(filename, content_type)
    original_size = len(data)
    # Sidik jari berkas ASLI: dipakai Fase 31 untuk menolak foto bukti yang didaur ulang
    # (satu foto tidak boleh mengklaim dua pekerjaan berbeda).
    sha256 = hashlib.sha256(data).hexdigest()
    opt = None
    if optimize and photo_utils.is_image(ct, filename):
        opt = await asyncio.to_thread(photo_utils.optimize, data,
                                      watermark_lines=watermark_lines)
    if opt:
        data, ct = opt["data"], opt["content_type"]
    ext = "jpg" if opt else (filename.rsplit(".", 1)[-1].lower()
                             if "." in (filename or "") else "bin")
    fid = new_id()
    base = f"{APP_NAME}/{org_id}/{tag}/{owner_id or 'na'}/{fid}"
    path = f"{base}.{ext}"
    used = await _put_bytes(path, data, ct)
    thumb_path = None
    if opt and opt.get("thumb"):
        thumb_path = f"{base}.thumb.jpg"
        await _put_bytes(thumb_path, opt["thumb"], "image/jpeg")
    rec = {
        "id": fid, "org_id": org_id, "storage_path": path, "provider": used,
        "original_filename": filename, "content_type": ct, "size": len(data),
        "owner_type": owner_type, "owner_id": owner_id, "doc_type": doc_type,
        "uploaded_by": uploaded_by, "is_deleted": False, "created_at": now_iso(),
        "sha256": sha256,
        "optimized": bool(opt), "original_size": original_size,
        "saving_pct": photo_utils.saving_pct(original_size, len(data)) if opt else 0,
        "width": (opt or {}).get("width"), "height": (opt or {}).get("height"),
        "watermark": (opt or {}).get("watermark"),
        "thumb_path": thumb_path, "thumb_size": (opt or {}).get("thumb_size"),
    }
    await db.files.insert_one(dict(rec))
    rec.pop("_id", None)
    return rec


async def variant_source(rec: dict, variant: str = None) -> tuple:
    """Pilih objek yang dilayani: thumbnail bila diminta & tersedia, kalau tidak yang penuh.

    Dipakai bersama oleh endpoint staf dan portal pembeli supaya satu aturan saja.
    """
    if variant == "thumb" and rec.get("thumb_path"):
        return rec["thumb_path"], "image/jpeg"
    return rec.get("storage_path"), rec.get("content_type", "application/octet-stream")


async def seed_demo_file(*, org_id: str, owner_type: str, owner_id: str, doc_type: str,
                         filename: str, text: str) -> dict:
    """Idempotent-ish helper for seed: store a tiny text file via mongo fallback."""
    return await save_file(
        data=text.encode("utf-8"), filename=filename, content_type="text/plain",
        org_id=org_id, owner_type=owner_type, owner_id=owner_id,
        uploaded_by="seed", doc_type=doc_type, tag="kyc",
    )
