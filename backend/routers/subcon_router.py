"""Subkontraktor & SPK (Phase 12 — EPIC 2.2).

Subcontractor master + Surat Perintah Kerja (work orders) that bind a subcontractor
to a project with a contract value + retention. SPK are the contractual basis for
subcon Purchase Orders / bills in the procurement pillar. Read is org-scoped;
project-scoped roles (PM/site) only see SPK for their assigned projects.
"""
from fastapi import APIRouter, Depends, HTTPException, Response
from typing import List

import docgen_p61 as p61
import docgen_p62 as p62
import opname as op
import sequences as seq
from denorm import cascade_master_change
from db import db, ORG_ID
from core_utils import new_id, now_iso, serialize_doc
from rbac import has_role, require_permission, assert_project_access, project_query
from engine import add_activity
from models import (
    SubcontractorCreate, SubcontractorUpdate,
    SPKCreate, SPKUpdate, SPKStatusUpdate,
)
from models_p62 import SpkAttachmentIn

router = APIRouter(prefix="/subcon", tags=["subcon"])

SPK_STATUS = ("draft", "active", "completed", "cancelled")
PROJECT_SCOPED = ("project_manager", "site_engineer")


async def _accessible_project_ids(user: dict):
    projs = await db.projects.find(project_query(user, {}), {"_id": 0, "id": 1, "name": 1}).to_list(500)
    return {p["id"]: p["name"] for p in projs}


SCOPE_BY_PREFIX = {"SPK": "spk"}


async def _next_number(prefix: str, coll, org_id: str = None, context: dict = None) -> str:
    """Nomor atomik per org+tahun. Dulu `count_documents+1`: dua request bersamaan
    menghasilkan nomor identik, dan hitungannya memakai org default (bocor antar tenant)."""
    return await seq.next_number(SCOPE_BY_PREFIX.get(prefix, prefix.lower()),
                                 org_id or ORG_ID, prefix=prefix, context=context)


# ----------------------------- Subcontractors -----------------------------
@router.get("/subcontractors")
async def list_subcontractors(q: str = None, active: str = None,
                              user: dict = Depends(require_permission("subcon", "view"))):
    org = user.get("org_id", ORG_ID)
    fq = {"org_id": org}
    if active in ("true", "false"):
        fq["is_active"] = active == "true"
    if q:
        fq["$or"] = [{"name": {"$regex": q, "$options": "i"}},
                     {"code": {"$regex": q, "$options": "i"}},
                     {"specialty": {"$regex": q, "$options": "i"}}]
    rows = await db.subcontractors.find(fq, {"_id": 0}).sort("name", 1).to_list(500)
    for r in rows:
        r["active_spk"] = await db.spk.count_documents(
            {"org_id": org, "subcontractor_id": r["id"], "status": "active"})
    return {"data": serialize_doc(rows), "total": len(rows)}


@router.post("/subcontractors")
async def create_subcontractor(payload: SubcontractorCreate,
                               user: dict = Depends(require_permission("subcon", "create"))):
    org = user.get("org_id", ORG_ID)
    import numbering as nb
    code = payload.code or await nb.generate_unique(
        "master:subcontractor", org, "subcontractors", {"org_id": org},
        context={"category": payload.specialty})
    if await db.subcontractors.find_one({"org_id": org, "code": code}):
        raise HTTPException(status_code=400, detail="Kode subkontraktor sudah dipakai.")
    ts = now_iso()
    doc = {
        "id": new_id(), "org_id": org, "code": code, "name": payload.name,
        "specialty": payload.specialty, "phone": payload.phone, "email": payload.email,
        "npwp": payload.npwp, "address": payload.address, "pic_name": payload.pic_name,
        "rating": payload.rating, "is_active": True, "notes": payload.notes,
        "created_by": user.get("email"), "created_at": ts, "updated_at": ts,
    }
    await db.subcontractors.insert_one(dict(doc))
    doc.pop("_id", None)
    return {"data": serialize_doc(doc)}


@router.get("/subcontractors/{sid}")
async def get_subcontractor(sid: str, user: dict = Depends(require_permission("subcon", "view"))):
    org = user.get("org_id", ORG_ID)
    doc = await db.subcontractors.find_one({"id": sid, "org_id": org}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Subkontraktor tidak ditemukan")
    spks = await db.spk.find({"org_id": org, "subcontractor_id": sid}, {"_id": 0}).sort("created_at", -1).to_list(200)
    return {"data": serialize_doc(doc), "spk": serialize_doc(spks)}


@router.put("/subcontractors/{sid}")
async def update_subcontractor(sid: str, payload: SubcontractorUpdate,
                               user: dict = Depends(require_permission("subcon", "update"))):
    org = user.get("org_id", ORG_ID)
    doc = await db.subcontractors.find_one({"id": sid, "org_id": org}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Subkontraktor tidak ditemukan")
    upd = {k: v for k, v in payload.dict(exclude_unset=True).items()}
    upd["updated_at"] = now_iso()
    await db.subcontractors.update_one({"id": sid, "org_id": org}, {"$set": upd})
    fresh = await db.subcontractors.find_one({"id": sid}, {"_id": 0})
    # SSOT: samakan nama yang dikopi ke SPK/termin/CO/PO (dulu jadi basi saat rename).
    await cascade_master_change("subcontractors", sid, fresh)
    return {"data": serialize_doc(fresh)}


# ----------------------------- SPK (work orders) -----------------------------
@router.get("/spk")
async def list_spk(project_id: str = None, subcontractor_id: str = None, status: str = None,
                   user: dict = Depends(require_permission("subcon", "view"))):
    org = user.get("org_id", ORG_ID)
    pmap = await _accessible_project_ids(user)
    fq = {"org_id": org}
    if has_role(user, *PROJECT_SCOPED):
        fq["project_id"] = {"$in": list(pmap.keys())}
    if project_id:
        fq["project_id"] = project_id
    if subcontractor_id:
        fq["subcontractor_id"] = subcontractor_id
    if status:
        fq["status"] = status
    rows = await db.spk.find(fq, {"_id": 0}).sort("created_at", -1).to_list(500)
    rows = await op.enrich_spk_list(org, rows)
    summary = {
        "total": len(rows),
        "active": sum(1 for r in rows if r.get("status") == "active"),
        "completed": sum(1 for r in rows if r.get("status") == "completed"),
        "contract_value": sum(int(r.get("contract_value", 0)) for r in rows),
        "item_based": sum(1 for r in rows if r.get("scope_mode") == "items"),
        "verified_value": sum(int(r.get("scope_verified_value") or 0) for r in rows),
        "billed_value": sum(int(r.get("scope_billed_value") or 0) for r in rows),
        "claimable_value": sum(int(r.get("scope_claimable_value") or 0) for r in rows),
    }
    return {"data": serialize_doc(rows), "total": len(rows), "summary": summary}


@router.post("/spk")
async def create_spk(payload: SPKCreate,
                     user: dict = Depends(require_permission("subcon", "create"))):
    org = user.get("org_id", ORG_ID)
    proj = await assert_project_access(payload.project_id, user)
    sub = await db.subcontractors.find_one({"id": payload.subcontractor_id, "org_id": org}, {"_id": 0})
    if not sub:
        raise HTTPException(status_code=404, detail="Subkontraktor tidak ditemukan")
    ts = now_iso()
    doc = {
        "id": new_id(), "org_id": org, "spk_number": await _next_number(
            "SPK", db.spk, org, {"project_id": payload.project_id, "subcon_code": sub.get("code")}),
        "subcontractor_id": payload.subcontractor_id, "subcontractor_name": sub.get("name"),
        "project_id": payload.project_id, "project_name": proj.get("name"),
        "title": payload.title, "scope": payload.scope,
        "contract_value": int(payload.contract_value or 0), "retention_pct": float(payload.retention_pct or 0),
        # Fase 48C: masa pemeliharaan dipakai gerbang pencairan retensi.
        "maintenance_days": int(payload.maintenance_days or 90),
        "start_date": payload.start_date, "end_date": payload.end_date,
        "status": "draft", "progress_pct": 0, "notes": payload.notes,
        "created_by": user.get("email"), "created_at": ts, "updated_at": ts,
    }
    await db.spk.insert_one(dict(doc))
    await add_activity(entity_type="project", entity_id=payload.project_id, type="system",
                       body=f"SPK {doc['spk_number']} untuk {sub.get('name')} dibuat (Rp {doc['contract_value']:,}).",
                       actor=user.get("email"), org_id=org)
    doc.pop("_id", None)
    return {"data": serialize_doc(doc)}


class SPKFromRabIn(SPKCreate):
    spk_kind: str = "unit_addon"            # unit | addon | unit_addon | fasum | umum
    unit_ids: List[str] = []
    lines: List[dict] = []


@router.post("/spk/from-rab")
async def create_spk_from_rab(payload: SPKFromRabIn,
                              user: dict = Depends(require_permission("subcon", "create"))):
    """SPK berdasar RAB: baris dari RAB tipe unit + add-on deal (atau item RAB fasum/umum), boleh
    dioverride dengan alasan; nilai kontrak = Σ baris; baris ber-step_code otomatis masuk lingkup jadwal."""
    import rab_engine as re_
    if payload.spk_kind not in re_.SPK_KIND_SCOPE:
        raise HTTPException(status_code=400, detail="Jenis SPK tidak dikenal.")
    try:
        lines = re_.validate_lines(payload.lines)
        await re_.assert_boq_not_contracted(user.get("org_id", ORG_ID), lines)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not lines:
        raise HTTPException(status_code=400, detail="SPK dari RAB harus punya minimal satu baris.")
    total = sum(ln["value"] for ln in lines)
    if total <= 0:
        raise HTTPException(status_code=400, detail="Total nilai SPK harus lebih dari 0.")
    payload.contract_value = total
    res = await create_spk(payload, user)
    doc = res["data"]
    org = user.get("org_id", ORG_ID)
    unit_codes = sorted({ln.get("unit_code") for ln in lines if ln.get("unit_code")})
    extra = {"spk_kind": payload.spk_kind, "rab_lines": lines, "unit_ids": payload.unit_ids, "unit_codes": unit_codes,
             "rab_total": sum(ln["rab_amount"] for ln in lines), "override_count": sum(1 for ln in lines if ln["override"])}
    await db.spk.update_one({"id": doc["id"]}, {"$set": extra})
    doc.update(extra)
    doc["auto_scope"] = await re_.auto_scope_lines(org, doc, lines, user.get("email"))
    return {"data": serialize_doc(doc)}


async def _get_spk(sid: str, user: dict) -> dict:
    doc = await db.spk.find_one({"id": sid, "org_id": user.get("org_id", ORG_ID)}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="SPK tidak ditemukan")
    await assert_project_access(doc["project_id"], user)
    return doc


@router.get("/spk/{sid}")
async def get_spk(sid: str, user: dict = Depends(require_permission("subcon", "view"))):
    doc = await _get_spk(sid, user)
    pos = await db.purchase_orders.find(
        {"org_id": doc["org_id"], "spk_id": sid}, {"_id": 0}).sort("created_at", -1).to_list(200)
    rows = await op.scope_rows(doc["org_id"], sid)
    return {"data": serialize_doc(doc), "purchase_orders": serialize_doc(pos),
            "scope_summary": op.summarize(rows)}


@router.get("/spk/{sid}/pdf")
async def spk_pdf(sid: str, user: dict = Depends(require_permission("subcon", "view"))):
    """Cetak SPK berkop (Fase 61) — surat yang ditandatangani subkontraktor sebelum bekerja."""
    doc = await _get_spk(sid, user)
    pdf = await p61.spk_pdf(doc["org_id"], doc,
                            {"name": user.get("name"), "role": user.get("role")})
    nama = str(doc.get("spk_number") or "spk").replace("/", "-")
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{nama}.pdf"'})


# ------------------------- Lampiran SPK (Fase 62) -------------------------
@router.get("/spk/{sid}/attachments")
async def list_attachments(sid: str,
                           user: dict = Depends(require_permission("subcon", "view"))):
    """Gambar kerja & spesifikasi yang menjadi lampiran SPK (ikut tercetak pada PDF)."""
    doc = await _get_spk(sid, user)
    rows = await p62.spk_attachments(doc["org_id"], sid)
    return {"data": serialize_doc(rows), "total": len(rows)}


@router.post("/spk/{sid}/attachments")
async def add_attachment(sid: str, payload: SpkAttachmentIn,
                         user: dict = Depends(require_permission("subcon", "update"))):
    doc = await _get_spk(sid, user)
    org = doc["org_id"]
    berkas = await db.files.find_one(
        {"id": payload.file_id, "org_id": org, "is_deleted": False},
        {"_id": 0, "original_filename": 1, "content_type": 1})
    if not berkas:
        raise HTTPException(status_code=404, detail="Berkas lampiran tidak ditemukan")
    if payload.kind not in ("gambar_kerja", "spesifikasi", "lainnya"):
        raise HTTPException(status_code=400, detail="Jenis lampiran tidak dikenal.")
    if await db.spk_attachments.find_one({"org_id": org, "spk_id": sid,
                                          "file_id": payload.file_id,
                                          "is_deleted": {"$ne": True}}, {"_id": 0, "id": 1}):
        raise HTTPException(status_code=400,
                            detail="Berkas ini sudah menjadi lampiran SPK tersebut.")
    ts = now_iso()
    row = {"id": new_id(), "org_id": org, "spk_id": sid, "file_id": payload.file_id,
           "kind": payload.kind,
           "label": (payload.label or berkas.get("original_filename") or "")[:120],
           "filename": berkas.get("original_filename"),
           "content_type": berkas.get("content_type"),
           "is_deleted": False, "created_by": user.get("email"), "created_at": ts}
    await db.spk_attachments.insert_one(dict(row))
    row.pop("_id", None)
    await add_activity(entity_type="project", entity_id=doc["project_id"], type="system",
                       body=f"Lampiran '{row['label']}' ditambahkan ke SPK "
                            f"{doc.get('spk_number')} dan akan tercetak pada surat.",
                       actor=user.get("email"), org_id=org)
    return {"data": serialize_doc(row)}


@router.delete("/spk/{sid}/attachments/{aid}")
async def remove_attachment(sid: str, aid: str,
                            user: dict = Depends(require_permission("subcon", "update"))):
    doc = await _get_spk(sid, user)
    res = await db.spk_attachments.update_one(
        {"id": aid, "org_id": doc["org_id"], "spk_id": sid},
        {"$set": {"is_deleted": True, "deleted_by": user.get("email"),
                  "deleted_at": now_iso()}})
    if not res.matched_count:
        raise HTTPException(status_code=404, detail="Lampiran tidak ditemukan")
    return {"data": {"ok": True, "id": aid}}


@router.put("/spk/{sid}")
async def update_spk(sid: str, payload: SPKUpdate,
                     user: dict = Depends(require_permission("subcon", "update"))):
    doc = await _get_spk(sid, user)
    upd = {k: v for k, v in payload.dict(exclude_unset=True).items()}
    scope = await op.scope_rows(doc["org_id"], sid)
    s = op.summarize(scope)
    if scope and upd.get("progress_pct") is not None:
        # INV-33-5: progres SPK berbasis item LAHIR DARI BUKTI, tidak boleh diketik.
        raise HTTPException(status_code=400, detail=(
            "SPK ini dibayar per item pekerjaan, jadi progresnya dihitung otomatis dari "
            f"pekerjaan yang sudah diverifikasi (sekarang {s['progress_pct']}%). "
            "Untuk menaikkan progres: verifikasi pekerjaan di Progres & Mutu Konstruksi."))
    if "contract_value" in upd and upd["contract_value"] is not None:
        upd["contract_value"] = int(upd["contract_value"])
        if scope and upd["contract_value"] < s["scope_value"]:
            raise HTTPException(status_code=400, detail=(
                f"Nilai kontrak {op.rp(upd['contract_value'])} lebih kecil dari total lingkup "
                f"pekerjaan {op.rp(s['scope_value'])}. Kurangi lingkup dulu, atau naikkan "
                "nilai kontrak lewat Change Order."))
    if "progress_pct" in upd and upd["progress_pct"] is not None:
        upd["progress_pct"] = max(0, min(100, int(upd["progress_pct"])))
    upd["updated_at"] = now_iso()
    await db.spk.update_one({"id": sid, "org_id": doc["org_id"]}, {"$set": upd})
    return {"data": serialize_doc(await db.spk.find_one({"id": sid}, {"_id": 0}))}


@router.post("/spk/{sid}/status")
async def spk_status(sid: str, payload: SPKStatusUpdate,
                     user: dict = Depends(require_permission("subcon", "update"))):
    if payload.status not in SPK_STATUS:
        raise HTTPException(status_code=400, detail="Status SPK tidak valid.")
    doc = await _get_spk(sid, user)
    ts = now_iso()
    setter = {"status": payload.status, "updated_at": ts}
    if payload.status == "completed":
        scope = await op.scope_rows(doc["org_id"], sid)
        if scope:
            s = op.summarize(scope)
            pending = [r for r in scope if not r.get("verified")]
            if pending:
                raise HTTPException(status_code=400, detail=(
                    f"{len(pending)} pekerjaan dalam lingkup SPK ini belum diverifikasi "
                    f"(progres terbukti {s['progress_pct']}%). Selesaikan/verifikasi dulu, "
                    "atau keluarkan pekerjaan itu dari lingkup sebelum menutup SPK."))
            setter["progress_pct"] = int(s["progress_pct"])
        else:
            setter["progress_pct"] = 100
        setter["completed_at"] = ts
    if payload.note:
        setter["notes"] = ((doc.get("notes") or "") + f"\n[{ts[:10]}] {payload.note}").strip()
    await db.spk.update_one({"id": sid, "org_id": doc["org_id"]}, {"$set": setter})
    await add_activity(entity_type="project", entity_id=doc["project_id"], type="system",
                       body=f"SPK {doc.get('spk_number')} → status {payload.status}.",
                       actor=user.get("email"), org_id=doc["org_id"])
    return {"data": serialize_doc(await db.spk.find_one({"id": sid}, {"_id": 0}))}
