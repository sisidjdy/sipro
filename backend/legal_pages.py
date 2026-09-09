"""Halaman legal publik: Kebijakan Privasi, Syarat & Ketentuan, Penghapusan Data (ID + EN).

Identitas perusahaan & teks kustom disimpan di `legal_settings` (konfigurasi — tidak ikut
Hapus Massal). Teks kosong = memakai template bawaan yang mengisi placeholder otomatis.
"""
import random
import string
from datetime import datetime, timezone

import reference as _ref
from db import db, ORG_ID
from core_utils import new_id, now_iso
from legal_templates import TEMPLATES

PAGES = ("privacy", "terms", "deletion")
LANGS = ("id", "en")
DELETION_STATUSES = _ref.values("deletion_request_status")  # SSOT: reference_p100

DEFAULT_IDENTITY = {
    "company_name": "PT. HARMONY CAHAYA LAND",
    "brand": "Harmony Land 5",
    "address": "",
    "email": "",
    "phone": "",
    "dpo_name": "",
    "effective_date": "",
}


async def get_settings(org: str = ORG_ID) -> dict:
    doc = await db.legal_settings.find_one({"org_id": org}, {"_id": 0}) or {}
    identity = {**DEFAULT_IDENTITY, **(doc.get("identity") or {})}
    if not identity.get("brand"):
        o = await db.orgs.find_one({"id": org}, {"_id": 0, "name": 1})
        identity["brand"] = (o or {}).get("name") or DEFAULT_IDENTITY["brand"]
    texts = doc.get("texts") or {}
    return {"org_id": org, "identity": identity, "texts": texts, "updated_at": doc.get("updated_at"),
            "updated_by": doc.get("updated_by")}


async def save_settings(org: str, identity: dict, texts: dict, actor: str) -> dict:
    clean_id = {k: (str(identity.get(k) or "")).strip() for k in DEFAULT_IDENTITY}
    clean_tx = {}
    for lang in LANGS:
        for page in PAGES:
            v = ((texts.get(lang) or {}).get(page) or "").strip()
            if v:
                clean_tx.setdefault(lang, {})[page] = v
    await db.legal_settings.update_one({"org_id": org}, {"$set": {
        "org_id": org, "identity": clean_id, "texts": clean_tx,
        "updated_at": now_iso(), "updated_by": actor}}, upsert=True)
    return await get_settings(org)


def _fill(text: str, identity: dict, public_base: str) -> str:
    eff = identity.get("effective_date") or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    values = {
        "company": identity.get("company_name") or DEFAULT_IDENTITY["company_name"],
        "brand": identity.get("brand") or DEFAULT_IDENTITY["brand"],
        "address": identity.get("address") or "-",
        "email": identity.get("email") or "-",
        "phone": identity.get("phone") or "-",
        "dpo": identity.get("dpo_name") or (identity.get("company_name") or "-"),
        "domain": public_base or "",
        "effective_date": eff,
    }
    for k, v in values.items():
        text = text.replace("{{" + k + "}}", v)
    return text


async def render(org: str, lang: str, public_base: str = "") -> dict:
    lang = lang if lang in LANGS else "id"
    st = await get_settings(org)
    pages = {}
    for page in PAGES:
        custom = (st["texts"].get(lang) or {}).get(page)
        pages[page] = {"content": _fill(custom or TEMPLATES[lang][page], st["identity"], public_base),
                       "is_custom": bool(custom)}
    return {"lang": lang, "identity": st["identity"], "pages": pages, "updated_at": st["updated_at"]}


def _ticket() -> str:
    tail = "".join(random.choices(string.ascii_uppercase + string.digits, k=4))
    return f"DEL-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{tail}"


async def create_deletion_request(org: str, payload: dict) -> dict:
    ts = now_iso()
    doc = {"id": new_id(), "org_id": org, "ticket": _ticket(), "name": payload["name"],
           "contact": payload["contact"], "reason": payload.get("reason") or "",
           "lang": payload.get("lang") or "id", "status": "open", "note": None,
           "handled_by": None, "created_at": ts, "updated_at": ts}
    await db.data_deletion_requests.insert_one(dict(doc))
    return doc


async def list_deletion_requests(org: str) -> list:
    return await db.data_deletion_requests.find({"org_id": org}, {"_id": 0}).sort("created_at", -1).to_list(500)


async def update_deletion_request(org: str, rid: str, status: str, note: str, actor: str):
    if status not in DELETION_STATUSES:
        raise ValueError("Status tidak dikenal.")
    r = await db.data_deletion_requests.update_one({"id": rid, "org_id": org}, {"$set": {
        "status": status, "note": (note or "").strip() or None, "handled_by": actor, "updated_at": now_iso()}})
    if not r.matched_count:
        raise LookupError("Permintaan tidak ditemukan.")
    return await db.data_deletion_requests.find_one({"id": rid}, {"_id": 0})
