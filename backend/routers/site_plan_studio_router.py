"""ROUTER STUDIO SITE PLAN (Fase 72) — prefix `/site-plan-studio`.

Halaman penuh untuk menyiapkan peta: unggah SVG arsitek (parser kaya: transform, teks
label, deteksi kavling), unggah gambar latar PNG/JPG + gambar poligon manual (tracing),
cocokkan bentuk↔unit, dan lahirkan unit langsung dari bentuk peta.
Semua tulisan memerlukan `projects:update`; membaca `projects:view`.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

import site_plan_studio as st
import site_plan_svg as svgplan
from core_utils import serialize_doc
from db import ORG_ID, db
from rbac import audit_log, require_permission
from site_plan_parse import parse_svg_rich

router = APIRouter(prefix="/site-plan-studio", tags=["site-plan-studio"])


class PaletteIn(BaseModel):
    palette: dict


class SvgIn(BaseModel):
    svg: str = Field(min_length=40)
    filename: Optional[str] = None
    keep_mapping: bool = True


class ShapeIn(BaseModel):
    points: List[List[float]]
    kind: str = "lot"
    label: Optional[str] = None
    unit_id: Optional[str] = None


class ShapesIn(BaseModel):
    items: List[ShapeIn]


class ShapePatch(BaseModel):
    points: Optional[List[List[float]]] = None
    kind: Optional[str] = None
    label: Optional[str] = None
    unit_id: Optional[str] = None


class CreateUnitItem(BaseModel):
    shape_id: str
    block_code: str
    no: str
    unit_type_code: Optional[str] = None
    price: Optional[int] = None
    map_existing: bool = True


class CreateUnitsIn(BaseModel):
    items: List[CreateUnitItem]
    create_blocks: bool = False
    cluster_id: Optional[str] = None
    unit_type_code: Optional[str] = None


def _org(user):
    return user.get("org_id", ORG_ID)


async def _project(pid: str, org: str):
    if not await db.projects.count_documents({"id": pid, "org_id": org}):
        raise HTTPException(404, "Proyek tidak ditemukan.")


@router.get("/palette")
async def get_palette(user: dict = Depends(require_permission("projects", "view"))):
    """Palet warna status (penjualan & pembangunan) milik organisasi — dipakai studio, ekspor PNG."""
    return {"data": await st.get_palette(_org(user))}


@router.put("/palette")
async def save_palette(payload: PaletteIn,
                       user: dict = Depends(require_permission("projects", "update"))):
    out = await st.save_palette(_org(user), payload.palette, user.get("email"))
    await audit_log(user, "update", "site_plan_palettes", _org(user), {"groups": list(out)})
    return {"data": out, "message": "Palet warna disimpan."}


@router.get("/{project_id}")
async def studio(project_id: str, user: dict = Depends(require_permission("projects", "view"))):
    await _project(project_id, _org(user))
    return {"data": serialize_doc(await st.studio_payload(project_id, _org(user)))}


@router.post("/{project_id}/svg")
async def upload_svg(project_id: str, payload: SvgIn,
                     user: dict = Depends(require_permission("projects", "update"))):
    """SVG arsitek → geometri absolut + label teks + deteksi kavling + cocok otomatis."""
    org = _org(user)
    await _project(project_id, org)
    try:
        parsed = parse_svg_rich(payload.svg)
    except ValueError as e:
        raise HTTPException(400, str(e))
    old = await st.get_plan(project_id, org)
    if payload.keep_mapping and old:
        prev = {s["shape_id"]: s.get("unit_id") for s in old.get("shapes") or [] if s.get("unit_id")}
        for s in parsed["shapes"]:
            if prev.get(s["shape_id"]):
                s["unit_id"] = prev[s["shape_id"]]
    units = await st.units_light(project_id, org)
    matched = st.auto_match(parsed["shapes"], units)
    plan = await st.save_plan(project_id, org, user.get("email"), source="uploaded",
                              view_box=parsed["view_box"], shapes=parsed["shapes"],
                              filename=payload.filename)
    await audit_log(user, "update", "site_plans", plan["id"],
                    {"svg": payload.filename, "shapes": len(parsed["shapes"])})
    return {"data": {"detected": parsed["detected"], "auto_matched": matched,
                     "stats": svgplan.plan_stats(plan["shapes"], units)}}


@router.post("/{project_id}/background")
async def upload_background(project_id: str, file: UploadFile = File(...), page: int = Form(1),
                            user: dict = Depends(require_permission("projects", "update"))):
    """PNG/JPG langsung; PDF dirender halaman `page` (default 1) menjadi PNG latar."""
    org = _org(user)
    await _project(project_id, org)
    data = await file.read()
    try:
        plan = await st.set_background(project_id, org, data, file.filename or "siteplan.png",
                                       file.content_type or "image/png", user.get("email"),
                                       page=max(1, page))
    except ValueError as e:
        raise HTTPException(400, str(e))
    await audit_log(user, "update", "site_plans", plan["id"], {"background": file.filename})
    return {"data": serialize_doc(await st.studio_payload(project_id, org))}


@router.delete("/{project_id}/background")
async def delete_background(project_id: str,
                            user: dict = Depends(require_permission("projects", "update"))):
    try:
        await st.clear_background(project_id, _org(user), user.get("email"))
    except LookupError as e:
        raise HTTPException(404, str(e))
    return {"data": {"deleted": True}}


@router.post("/{project_id}/shapes")
async def add_shapes(project_id: str, payload: ShapesIn,
                     user: dict = Depends(require_permission("projects", "update"))):
    org = _org(user)
    await _project(project_id, org)
    try:
        out = await st.add_shapes(project_id, org, [i.model_dump() for i in payload.items],
                                  user.get("email"))
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"data": serialize_doc(out)}


@router.put("/{project_id}/shapes/{shape_id}")
async def update_shape(project_id: str, shape_id: str, payload: ShapePatch,
                       user: dict = Depends(require_permission("projects", "update"))):
    try:
        s = await st.update_shape(project_id, _org(user), shape_id,
                                  payload.model_dump(exclude_unset=True), user.get("email"))
    except LookupError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"data": serialize_doc(s)}


@router.delete("/{project_id}/shapes/{shape_id}")
async def delete_shape(project_id: str, shape_id: str,
                       user: dict = Depends(require_permission("projects", "update"))):
    try:
        n = await st.delete_shape(project_id, _org(user), shape_id, user.get("email"))
    except LookupError as e:
        raise HTTPException(404, str(e))
    return {"data": {"remaining": n}}


@router.post("/{project_id}/auto-match")
async def auto_match(project_id: str,
                     user: dict = Depends(require_permission("projects", "update"))):
    try:
        return {"data": await st.rematch(project_id, _org(user), user.get("email"))}
    except LookupError as e:
        raise HTTPException(404, str(e))


@router.get("/{project_id}/suggest-units")
async def suggest_units(project_id: str,
                        user: dict = Depends(require_permission("projects", "view"))):
    return {"data": await st.suggest_units(project_id, _org(user))}


@router.post("/{project_id}/create-units")
async def create_units(project_id: str, payload: CreateUnitsIn,
                       user: dict = Depends(require_permission("projects", "update"))):
    org = _org(user)
    try:
        out = await st.create_units(project_id, org, [i.model_dump() for i in payload.items],
                                    user.get("email"), create_blocks=payload.create_blocks,
                                    cluster_id=payload.cluster_id,
                                    unit_type_code=payload.unit_type_code)
    except LookupError as e:
        raise HTTPException(404, str(e))
    await audit_log(user, "create", "units", project_id,
                    {"from": "site_plan_studio", "created": out["created"], "mapped": out["mapped"]})
    return {"data": out}
