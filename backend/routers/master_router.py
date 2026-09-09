"""Master data yang sebelumnya TERKUNCI di seed (temuan audit: tidak ada endpoint tulis).

- document_templates: template PPJB/Surat Pesanan/BAST — dipakai documents_router.
- inspection_templates: template checklist QC — dipakai inspection_router.

Sebelum perbaikan ini keduanya hanya bisa dibuat oleh script seed, sehingga user tidak
bisa menambah/mengubah template dari aplikasi.
"""
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

import reference as ref
from db import db, ORG_ID
from core_utils import new_id, now_iso, serialize_doc
from rbac import require_permission, audit_log
from models_master import (DocTemplateCreate, DocTemplateUpdate,
                           QcTemplateCreate, QcTemplateUpdate)

router = APIRouter(prefix="/master", tags=["master-data"])


# ----------------------------- document templates -----------------------------
@router.get("/doc-templates")
async def list_doc_templates(include_inactive: bool = False,
                             user: dict = Depends(require_permission("documents", "view"))):
    q = {"org_id": user.get("org_id", ORG_ID)}
    if not include_inactive:
        q["is_active"] = True
    rows = await db.document_templates.find(q, {"_id": 0}).sort("code", 1).to_list(200)
    return {"data": serialize_doc(rows), "total": len(rows)}


@router.post("/doc-templates")
async def create_doc_template(payload: DocTemplateCreate,
                              user: dict = Depends(require_permission("documents", "update"))):
    org = user.get("org_id", ORG_ID)
    code = payload.code.strip().upper()
    if await db.document_templates.find_one({"org_id": org, "code": code}):
        raise HTTPException(status_code=409, detail=f"Kode template '{code}' sudah dipakai.")
    doc = {"id": new_id(), "org_id": org, "code": code, "name": payload.name,
           "content": payload.content, "is_active": True,
           "created_by": user.get("email"), "created_at": now_iso(), "updated_at": now_iso()}
    await db.document_templates.insert_one(dict(doc))
    await audit_log(user, "create", "document_templates", doc["id"], {"code": code})
    doc.pop("_id", None)
    return {"data": serialize_doc(doc)}


@router.put("/doc-templates/{tid}")
async def update_doc_template(tid: str, payload: DocTemplateUpdate,
                              user: dict = Depends(require_permission("documents", "update"))):
    org = user.get("org_id", ORG_ID)
    cur = await db.document_templates.find_one({"id": tid, "org_id": org}, {"_id": 0})
    if not cur:
        raise HTTPException(status_code=404, detail="Template dokumen tidak ditemukan.")
    upd = {k: v for k, v in payload.model_dump(exclude_unset=True).items() if v is not None}
    if not upd:
        return {"data": serialize_doc(cur)}
    upd["updated_at"] = now_iso()
    await db.document_templates.update_one({"id": tid, "org_id": org}, {"$set": upd})
    await audit_log(user, "update", "document_templates", tid, {"fields": sorted(upd)})
    return {"data": serialize_doc(await db.document_templates.find_one({"id": tid}, {"_id": 0}))}


@router.delete("/doc-templates/{tid}")
async def archive_doc_template(tid: str,
                               user: dict = Depends(require_permission("documents", "update"))):
    """Arsip (soft delete) — dokumen yang sudah terbit tetap merujuk template ini."""
    org = user.get("org_id", ORG_ID)
    res = await db.document_templates.update_one(
        {"id": tid, "org_id": org}, {"$set": {"is_active": False, "updated_at": now_iso()}})
    if not res.matched_count:
        raise HTTPException(status_code=404, detail="Template dokumen tidak ditemukan.")
    await audit_log(user, "archive", "document_templates", tid)
    return {"data": {"id": tid, "is_active": False}}


# ----------------------------- QC / inspection templates -----------------------------
@router.get("/qc-templates")
async def list_qc_templates(include_inactive: bool = False,
                            user: dict = Depends(require_permission("construction", "view"))):
    q = {"org_id": user.get("org_id", ORG_ID)}
    if not include_inactive:
        q["is_active"] = True
    rows = await db.inspection_templates.find(q, {"_id": 0}).sort("code", 1).to_list(200)
    return {"data": serialize_doc(rows), "total": len(rows)}


def _clean_items(items) -> list:
    out = []
    for it in items or []:
        label = (it.label if hasattr(it, "label") else it.get("label", "")).strip()
        if not label:
            continue
        out.append({"label": label,
                    "critical": bool(it.critical if hasattr(it, "critical") else it.get("critical"))})
    return out


@router.post("/qc-templates")
async def create_qc_template(payload: QcTemplateCreate,
                             user: dict = Depends(require_permission("construction", "update"))):
    org = user.get("org_id", ORG_ID)
    code = payload.code.strip().upper()
    items = _clean_items(payload.items)
    if not items:
        raise HTTPException(status_code=400, detail="Template QC butuh minimal 1 item checklist.")
    if await db.inspection_templates.find_one({"org_id": org, "code": code}):
        raise HTTPException(status_code=409, detail=f"Kode template '{code}' sudah dipakai.")
    doc = {"id": new_id(), "org_id": org, "code": code, "name": payload.name,
           "category": payload.category or "lainnya", "items": items, "is_active": True,
           "created_by": user.get("email"), "created_at": now_iso(), "updated_at": now_iso()}
    await db.inspection_templates.insert_one(dict(doc))
    await audit_log(user, "create", "inspection_templates", doc["id"], {"code": code})
    doc.pop("_id", None)
    return {"data": serialize_doc(doc)}


@router.put("/qc-templates/{tid}")
async def update_qc_template(tid: str, payload: QcTemplateUpdate,
                             user: dict = Depends(require_permission("construction", "update"))):
    org = user.get("org_id", ORG_ID)
    cur = await db.inspection_templates.find_one({"id": tid, "org_id": org}, {"_id": 0})
    if not cur:
        raise HTTPException(status_code=404, detail="Template QC tidak ditemukan.")
    data = payload.model_dump(exclude_unset=True)
    upd = {}
    for k in ("name", "category", "is_active"):
        if data.get(k) is not None:
            upd[k] = data[k]
    if data.get("items") is not None:
        items = _clean_items(payload.items)
        if not items:
            raise HTTPException(status_code=400, detail="Template QC butuh minimal 1 item checklist.")
        upd["items"] = items
    if not upd:
        return {"data": serialize_doc(cur)}
    upd["updated_at"] = now_iso()
    await db.inspection_templates.update_one({"id": tid, "org_id": org}, {"$set": upd})
    await audit_log(user, "update", "inspection_templates", tid, {"fields": sorted(upd)})
    return {"data": serialize_doc(await db.inspection_templates.find_one({"id": tid}, {"_id": 0}))}


@router.delete("/qc-templates/{tid}")
async def archive_qc_template(tid: str,
                              user: dict = Depends(require_permission("construction", "update"))):
    org = user.get("org_id", ORG_ID)
    res = await db.inspection_templates.update_one(
        {"id": tid, "org_id": org}, {"$set": {"is_active": False, "updated_at": now_iso()}})
    if not res.matched_count:
        raise HTTPException(status_code=404, detail="Template QC tidak ditemukan.")
    await audit_log(user, "archive", "inspection_templates", tid)
    return {"data": {"id": tid, "is_active": False}}


# ----------------------------- integritas data (read-only) -----------------------------
@router.get("/phone-health")
async def phone_health(user: dict = Depends(require_permission("audit_logs", "view"))):
    """Pratinjau nomor telepon yang belum berformat +62 (lead, customer, portal, WA, pengguna)."""
    from migrations import phone_health as _ph
    return {"data": await _ph(user.get("org_id", ORG_ID))}


@router.post("/normalize-phones")
async def normalize_phones(user: dict = Depends(require_permission("settings", "manage"))):
    """SEKALI JALAN: rapikan nomor 08xx/62xx menjadi +62xx di semua koleksi berkontak.
    Nomor yang setelah dirapikan bentrok dengan baris lain TIDAK diubah (dilaporkan)."""
    from migrations import normalize_phones as _np, phone_health as _ph
    report = await _np()
    await audit_log(user, "update", "phones", "normalize", meta=report)
    after = await _ph(user.get("org_id", ORG_ID))
    changed = sum(v.get("normalized", 0) for v in report.values())
    skipped = sum(v.get("skipped_duplicate", 0) for v in report.values())
    return {"data": {"report": report, "after": after},
            "message": f"{changed} nomor dirapikan ke +62; {skipped} dilewati karena akan ganda."}


class PhoneFixIn(BaseModel):
    collection: str
    id: str
    phone: str = ""


@router.post("/phone-fix")
async def phone_fix(body: PhoneFixIn, user: dict = Depends(require_permission("settings", "manage"))):
    """Tindak lanjut baris ganda/tidak valid: ganti nomor satu baris (kosong = hapus nomor)."""
    from migrations import PHONE_FIELDS, phone_health as _ph
    from core_utils import normalize_phone_e164
    field = dict(PHONE_FIELDS).get(body.collection)
    if not field:
        raise HTTPException(status_code=400, detail="Koleksi tidak dikenal.")
    org = user.get("org_id", ORG_ID)
    row = await db[body.collection].find_one({"id": body.id, "org_id": org}, {"_id": 0, "id": 1, field: 1})
    if not row:
        raise HTTPException(status_code=404, detail="Baris tidak ditemukan.")
    norm = normalize_phone_e164(body.phone.strip()) if body.phone.strip() else None
    if norm is not None:
        if not re.fullmatch(r"\+62\d{8,13}", norm):
            raise HTTPException(status_code=400, detail="Nomor tidak valid. Gunakan format 08xx atau +62xx (8–13 digit).")
        clash = await db[body.collection].find_one(
            {"org_id": org, field: norm, "id": {"$ne": body.id}}, {"_id": 0, "id": 1, "name": 1})
        if clash:
            raise HTTPException(status_code=409,
                                detail=f"Nomor {norm} sudah dipakai baris lain ({clash.get('name') or clash.get('id')}).")
    await db[body.collection].update_one({"id": body.id}, {"$set": {field: norm, "updated_at": now_iso()}})
    await audit_log(user, "update", body.collection, body.id,
                    meta={"field": field, "from": row.get(field), "to": norm, "reason": "phone_fix"})
    msg = f"Nomor diperbarui menjadi {norm}." if norm else "Nomor dihapus dari baris."
    return {"data": {"phone": norm, "after": await _ph(org)}, "message": msg}


@router.get("/data-health")
async def data_health(user: dict = Depends(require_permission("audit_logs", "view"))):
    """Ringkasan kesehatan data: field kopi basi, nilai enum liar, dan referensi menggantung."""
    from denorm import audit_stale
    org = user.get("org_id", ORG_ID)
    stale = await audit_stale()
    invalid = []
    checks = [("boq_items", "category", "work_category"), ("boq_items", "uom", "uom"),
              ("materials", "uom", "uom"), ("punch_items", "category", "work_category"),
              ("subcontractors", "specialty", "subcon_specialty"),
              ("leads", "source", "lead_source"), ("leads", "stage", "lead_stage"),
              ("complaints", "category", "complaint_category"),
              ("site_diaries", "weather", "weather")]
    for coll, field, group in checks:
        allowed = set(ref.values(group))
        for v in await db[coll].distinct(field, {"org_id": org}):
            if isinstance(v, str) and v and v not in allowed:
                n = await db[coll].count_documents({"org_id": org, field: v})
                invalid.append({"collection": coll, "field": field, "value": v, "count": n})
    orphans = await _orphan_references(org)
    return {"data": {"stale_denormalized": stale, "invalid_enum_values": invalid,
                     "orphan_references": orphans,
                     "stale_count": len(stale), "invalid_count": len(invalid),
                     "orphan_count": len(orphans)}}


# koleksi anak -> (field FK, koleksi induk)
ORPHAN_CHECKS = [
    ("tasks", "related_entity_id", None),          # ditangani khusus (polymorphic)
    ("deals", "unit_id", "units"),
    ("deals", "lead_id", "leads"),
    ("ar_invoices", "deal_id", "deals"),
    ("commissions", "deal_id", "deals"),
    ("spk", "subcontractor_id", "subcontractors"),
    ("progress_claims", "spk_id", "spk"),
    ("change_orders", "spk_id", "spk"),
    ("purchase_orders", "project_id", "projects"),
    ("grns", "po_id", "purchase_orders"),
    ("material_txns", "material_id", "materials"),
    ("material_requisitions", "project_id", "projects"),
    ("inspections", "project_id", "projects"),
    ("punch_items", "project_id", "projects"),
    ("permits", "project_id", "projects"),
    ("boq_items", "project_id", "projects"),
    ("complaints", "customer_id", "customers"),
    ("financing_apps", "deal_id", "deals"),
    ("surveys", "lead_id", "leads"),
    ("appointments", "lead_id", "leads"),
]

POLY_PARENT = {"lead": "leads", "deal": "deals", "unit": "units", "project": "projects",
               "customer": "customers", "complaint": "complaints", "permit": "permits",
               "purchase_order": "purchase_orders", "spk": "spk", "inspection": "inspections"}


async def _orphan_references(org: str) -> list:
    """Cari FK yang menunjuk dokumen induk yang sudah tidak ada (data menggantung)."""
    out = []
    existing = set(await db.list_collection_names())
    cache = {}

    async def parent_ids(coll: str) -> set:
        if coll not in cache:
            cache[coll] = {d["id"] for d in
                           await db[coll].find({}, {"_id": 0, "id": 1}).to_list(20000) if d.get("id")}
        return cache[coll]

    for child, fk, parent in ORPHAN_CHECKS:
        if child not in existing or (parent and parent not in existing):
            continue
        if parent is None:
            rows = await db[child].find(
                {"related_entity_id": {"$ne": None}},
                {"_id": 0, "id": 1, "title": 1, "related_entity_type": 1,
                 "related_entity_id": 1}).to_list(5000)
            for r in rows:
                pcoll = POLY_PARENT.get(r.get("related_entity_type"))
                if not pcoll or pcoll not in existing:
                    continue
                if r["related_entity_id"] not in await parent_ids(pcoll):
                    out.append({"collection": child, "id": r.get("id"), "field": "related_entity_id",
                                "value": r["related_entity_id"], "missing_in": pcoll,
                                "label": r.get("title")})
            continue
        ids = await parent_ids(parent)
        rows = await db[child].find({fk: {"$ne": None}}, {"_id": 0, "id": 1, fk: 1}).to_list(20000)
        for r in rows:
            if r.get(fk) not in ids:
                out.append({"collection": child, "id": r.get("id"), "field": fk,
                            "value": r.get(fk), "missing_in": parent, "label": None})
    return out[:200]
