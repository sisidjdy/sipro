"""Fase 80 — endpoint RAB terstruktur (template tipe/add-on, ringkasan HPP & margin, draf SPK dari RAB).
Fase 81 — versi RAB (riwayat + pulihkan), salin dari tipe lain, impor Excel, kendali fasum vs progres fase."""
from typing import List, Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from pydantic import BaseModel

import rab_engine as re_
import rab_templates_ext as ext
from core_utils import serialize_doc
from db import ORG_ID, db
from rbac import assert_project_access, require_permission

router = APIRouter(prefix="/rab", tags=["rab"])
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class TemplateIn(BaseModel):
    items: List[dict] = []
    note: Optional[str] = None


class CopyIn(BaseModel):
    source_ref_code: str
    factor: float = 1.0


class AllocationIn(BaseModel):
    method: str


class DraftIn(BaseModel):
    project_id: str
    mode: str = "unit_addon"           # unit | addon | unit_addon | fasum | umum
    unit_ids: List[str] = []
    boq_item_ids: List[str] = []


def _org(user):
    return user.get("org_id", ORG_ID)


def _err(e):
    return HTTPException(status_code=400, detail=str(e))


@router.get("/options")
async def options(user: dict = Depends(require_permission("boq", "view"))):
    return {"data": {"facilities": [{"code": c, "label": l} for c, l in re_.FACILITIES],
                     "umum_kinds": [{"code": c, "label": l} for c, l in re_.UMUM_KINDS],
                     "allocations": re_.ALLOCATIONS}}


@router.get("/import-template.xlsx")
async def import_template(kind: str = "unit_type", user: dict = Depends(require_permission("boq", "view"))):
    if kind not in ("unit_type", "addon"):
        raise HTTPException(status_code=404, detail="Jenis template tidak dikenal.")
    name = f"SIPRO_Template_RAB_{'Tipe' if kind == 'unit_type' else 'AddOn'}.xlsx"
    return Response(content=ext.import_workbook(kind), media_type=XLSX,
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}"})


@router.get("/templates/{kind}")
async def list_templates(kind: str, user: dict = Depends(require_permission("boq", "view"))):
    if kind not in ("unit_type", "addon"):
        raise HTTPException(status_code=404, detail="Jenis template tidak dikenal.")
    return {"data": serialize_doc(await re_.list_templates(_org(user), kind))}


@router.get("/templates/{kind}/{ref_code}")
async def get_template(kind: str, ref_code: str, user: dict = Depends(require_permission("boq", "view"))):
    return {"data": serialize_doc(await re_.get_template(_org(user), kind, ref_code))}


@router.put("/templates/{kind}/{ref_code}")
async def save_template(kind: str, ref_code: str, p: TemplateIn,
                        user: dict = Depends(require_permission("boq", "update"))):
    try:
        data = await re_.save_template(_org(user), kind, ref_code, p.items, user.get("email"), note=p.note)
    except ValueError as e:
        raise _err(e)
    sync = await re_.step_sync_check(_org(user), ref_code) if kind == "unit_type" else None
    return {"data": serialize_doc(data), "sync": serialize_doc(sync) if sync else None}


@router.get("/templates/{kind}/{ref_code}/sync-check")
async def sync_check(kind: str, ref_code: str, user: dict = Depends(require_permission("boq", "view"))):
    """Cek sinkron RAB tipe ↔ template jadwal: baris RAB dengan kode langkah yang tidak ada di jadwal tipe."""
    if kind != "unit_type":
        raise HTTPException(status_code=404, detail="Cek sinkron hanya untuk RAB tipe unit.")
    return {"data": serialize_doc(await re_.step_sync_check(_org(user), ref_code))}


@router.get("/templates/{kind}/{ref_code}/versions")
async def list_versions(kind: str, ref_code: str, user: dict = Depends(require_permission("boq", "view"))):
    return {"data": serialize_doc(await ext.list_versions(_org(user), kind, ref_code))}


@router.get("/templates/{kind}/{ref_code}/versions/{vid}")
async def get_version(kind: str, ref_code: str, vid: str, user: dict = Depends(require_permission("boq", "view"))):
    try:
        return {"data": serialize_doc(await ext.get_version(_org(user), kind, ref_code, vid))}
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/templates/{kind}/{ref_code}/versions/{vid}/restore")
async def restore_version(kind: str, ref_code: str, vid: str, user: dict = Depends(require_permission("boq", "update"))):
    try:
        return {"data": serialize_doc(await ext.restore_version(_org(user), kind, ref_code, vid, user.get("email")))}
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise _err(e)


@router.post("/templates/{kind}/{ref_code}/copy-from")
async def copy_from(kind: str, ref_code: str, p: CopyIn, user: dict = Depends(require_permission("boq", "update"))):
    """Pratinjau salinan (tidak menyimpan): baris sumber × faktor harga. Simpan lewat PUT template."""
    try:
        return {"data": serialize_doc(await ext.copy_items(_org(user), kind, ref_code, p.source_ref_code, p.factor))}
    except ValueError as e:
        raise _err(e)


@router.post("/templates/{kind}/{ref_code}/import")
async def import_preview(kind: str, ref_code: str, file: UploadFile = File(...),
                         user: dict = Depends(require_permission("boq", "update"))):
    """Pratinjau impor Excel (tidak menyimpan): baris tervalidasi + daftar kesalahan/peringatan."""
    if not (file.filename or "").lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Berkas harus berekstensi .xlsx.")
    content = await file.read()
    if not content or len(content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Berkas kosong atau melebihi 5 MB.")
    try:
        return {"data": serialize_doc(await ext.parse_import(_org(user), kind, content))}
    except ValueError as e:
        raise _err(e)


@router.get("/spk/{sid}/fasum-cap")
async def spk_fasum_cap(sid: str, user: dict = Depends(require_permission("subcon", "view"))):
    spk = await db.spk.find_one({"org_id": _org(user), "id": sid}, {"_id": 0})
    if not spk:
        raise HTTPException(status_code=404, detail="SPK tidak ditemukan.")
    await assert_project_access(spk["project_id"], user)
    cap = await re_.fasum_phase_cap(_org(user), spk)
    return {"data": serialize_doc({**cap, "spk_kind": spk.get("spk_kind"), "billed_pct": int(spk.get("progress_pct") or 0),
                                   "applies": spk.get("spk_kind") == "fasum" and bool(cap["covered_value"])})}


@router.get("/projects/{pid}/summary")
async def project_summary(pid: str, user: dict = Depends(require_permission("boq", "view"))):
    await assert_project_access(pid, user)
    return {"data": serialize_doc(await re_.project_summary(_org(user), pid))}


@router.put("/projects/{pid}/allocation")
async def set_allocation(pid: str, p: AllocationIn, user: dict = Depends(require_permission("boq", "update"))):
    await assert_project_access(pid, user)
    try:
        return {"data": {"allocation": await re_.set_allocation(_org(user), pid, p.method)}}
    except ValueError as e:
        raise _err(e)


@router.post("/spk-draft")
async def spk_draft(p: DraftIn, user: dict = Depends(require_permission("subcon", "view"))):
    await assert_project_access(p.project_id, user)
    try:
        if p.mode in ("fasum", "umum"):
            return {"data": serialize_doc(await re_.fasum_draft(_org(user), p.project_id, p.mode, p.boq_item_ids))}
        if not p.unit_ids:
            raise ValueError("Pilih minimal satu unit.")
        return {"data": serialize_doc(await re_.spk_draft(_org(user), p.project_id, p.unit_ids, p.mode))}
    except ValueError as e:
        raise _err(e)
