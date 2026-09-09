"""EPIC P29 — Interactive Site Plan / Digital Showroom (backend).

Fase 28 menambah **peta berbasis SVG**: satu dokumen `site_plans` per proyek berisi
geometri shape (kavling, jalan, taman, fasilitas) + pemetaan shape→unit. Peta bisa
dibangkitkan realistis (`POST /generate`) atau diunggah dari SVG arsitek (`POST /svg`,
geometri saja — markup mentah tidak pernah disuntikkan ke DOM).

Bila proyek belum punya peta SVG, auto-layout lama (blok kotak) tetap dipakai sebagai
fallback jujur sehingga tidak ada regresi.
"""
from typing import Optional

import secrets

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

import p28_utils as p28
import site_plan_svg as svgplan
from db import db, ORG_ID
from core_utils import normalize_phone_e164, serialize_doc, now_iso, new_id
from models_p28 import ShowroomConfig
from rbac import require_permission, audit_log

router = APIRouter(prefix="/site-plan", tags=["site-plan"])

# Layout geometry (virtual units; frontend scales/zooms).
UNIT_W, UNIT_H = 116, 92
GAP_X, GAP_Y = 16, 16
COLS = 6                 # plots per row within a block
BLOCK_LABEL_H = 30
ROAD_Y = 56              # vertical gap (road) between blocks
PAD = 28

STATUS_ORDER = ["available", "reserved", "booked", "sold"]


class PlanPosition(BaseModel):
    unit_id: str
    x: float
    y: float
    w: Optional[float] = None
    h: Optional[float] = None
    block: Optional[str] = None


class LayoutSave(BaseModel):
    positions: list[PlanPosition] = []


def _block_of(u: dict) -> str:
    if u.get("block"):
        return str(u["block"])
    code = u.get("code") or ""
    return code.split("-")[0] if "-" in code else (code[:1] or "A")


def _parse_luas(u: dict):
    """Luas bangunan/tanah unit (field nyata; fallback turunan nama tipe untuk data lama)."""
    return p28.parse_luas(u)


async def _buyer_for(u: dict, org: str):
    """Nama pembeli + tahap legal (PPJB/AJB) + TANGGAL DEAL untuk kavling non-tersedia.

    Tanggal deal dipakai menghitung **lama sampai laku** (days on market) pada mode
    heatmap; untuk kavling yang masih dipasarkan, umur listing dihitung sampai hari ini.
    """
    deal_id = u.get("booked_by_deal") or u.get("reserved_by_deal")
    stage = None
    if deal_id:
        d = await db.deals.find_one({"id": deal_id}, {"_id": 0, "lead_id": 1,
                                                     "legal_stage": 1, "created_at": 1})
        if d:
            stage = d.get("legal_stage")
            created = d.get("created_at")
            if u.get("buyer_name"):
                return u["buyer_name"], deal_id, stage, created
            lead = await db.leads.find_one({"id": d.get("lead_id")}, {"_id": 0, "name": 1})
            return (lead or {}).get("name"), deal_id, stage, created
    return u.get("buyer_name"), deal_id, stage, None


@router.get("/{project_id}")
async def get_site_plan(project_id: str,
                        user: dict = Depends(require_permission("projects", "view"))):
    org = user.get("org_id", ORG_ID)
    project = await db.projects.find_one({"id": project_id, "org_id": org}, {"_id": 0})
    if not project:
        raise HTTPException(404, "Proyek tidak ditemukan.")
    units = await db.units.find({"project_id": project_id, "org_id": org}, {"_id": 0}).to_list(2000)

    # Group by block, sort blocks + units-within-block by code.
    blocks: dict = {}
    for u in units:
        blocks.setdefault(_block_of(u), []).append(u)
    for b in blocks:
        blocks[b].sort(key=lambda x: (x.get("code") or ""))

    enriched, block_meta = [], []
    max_w, y_cursor = 0, PAD
    for bname in sorted(blocks.keys()):
        bunits = blocks[bname]
        rows = (len(bunits) + COLS - 1) // COLS
        block_h = BLOCK_LABEL_H + rows * (UNIT_H + GAP_Y)
        block_top = y_cursor
        for idx, u in enumerate(bunits):
            row, col = divmod(idx, COLS)
            x = PAD + col * (UNIT_W + GAP_X)
            y = y_cursor + BLOCK_LABEL_H + row * (UNIT_H + GAP_Y)
            lb, lt = _parse_luas(u)
            has_pos = isinstance(u.get("plan"), dict) and "x" in u["plan"]
            pos = u["plan"] if has_pos else {}
            buyer, deal_id, legal_stage, deal_created = await _buyer_for(u, org)
            dom = p28.days_on_market(u, deal_created)
            enriched.append({
                "id": u["id"], "code": u.get("code"), "block": bname,
                "type": u.get("type"), "price": u.get("price", 0),
                "status": u.get("status", "available"),
                "luas_bangunan": lb, "luas_tanah": lt,
                "orientation": u.get("orientation"), "corner": bool(u.get("corner")),
                "construction_status": u.get("construction_status"),
                "construction_progress": u.get("construction_progress", 0),
                "payment_status": u.get("payment_status", "none"),
                "buyer_name": buyer, "deal_id": deal_id, "legal_stage": legal_stage,
                "days_on_market": dom["days"], "dom_open": dom["open"],
                "price_per_m2": round(u.get("price", 0) / lt) if lt else None,
                "x": pos.get("x", x), "y": pos.get("y", y),
                "w": pos.get("w", UNIT_W), "h": pos.get("h", UNIT_H),
            })
            max_w = max(max_w, PAD + (col + 1) * (UNIT_W + GAP_X))
        block_meta.append({"name": bname, "x": PAD, "y": block_top,
                           "count": len(bunits), "height": block_h})
        y_cursor = block_top + block_h + ROAD_Y

    canvas = {"width": max(max_w + PAD, PAD * 2 + COLS * (UNIT_W + GAP_X)),
              "height": y_cursor + PAD}

    counts = {s: 0 for s in STATUS_ORDER}
    total_value = sold_value = available_value = 0
    for u in enriched:
        counts[u["status"]] = counts.get(u["status"], 0) + 1
        total_value += u["price"]
        if u["status"] == "sold":
            sold_value += u["price"]
        elif u["status"] == "available":
            available_value += u["price"]
    total = len(enriched)
    closed = counts.get("booked", 0) + counts.get("sold", 0)
    stats = {
        "total": total, "counts": counts,
        "absorption_pct": round(closed / total * 100) if total else 0,
        "available_pct": round(counts.get("available", 0) / total * 100) if total else 0,
        "total_value": total_value, "sold_value": sold_value, "available_value": available_value,
    }
    return {"data": {
        "project": serialize_doc(project), "units": enriched,
        "blocks": block_meta, "canvas": canvas, "stats": stats,
        "plan": await _plan_payload(project_id, org, enriched),
    }}


# ----------------------------- Peta SVG (Fase 28) -----------------------------
class ShapeMap(BaseModel):
    shape_id: str
    unit_id: Optional[str] = None
    kind: Optional[str] = None


class MappingSave(BaseModel):
    items: list[ShapeMap] = Field(default_factory=list)


class SvgUpload(BaseModel):
    svg: str = Field(min_length=40)
    filename: Optional[str] = None


async def _get_plan(project_id: str, org: str) -> Optional[dict]:
    return await db.site_plans.find_one({"org_id": org, "project_id": project_id},
                                        {"_id": 0})


async def _plan_payload(project_id: str, org: str, units: list) -> Optional[dict]:
    plan = await _get_plan(project_id, org)
    if not plan:
        return None
    stats = svgplan.plan_stats(plan.get("shapes") or [], units)
    bg = plan.get("background")
    if bg and bg.get("file_id"):
        bg = {**bg, "url": f"/api/files/{bg['file_id']}"}
    return {"id": plan["id"], "source": plan.get("source"), "view_box": plan.get("view_box"),
            "filename": plan.get("filename"), "updated_at": plan.get("updated_at"),
            "background": bg,
            "shapes": plan.get("shapes") or [], "stats": stats}


async def _save_plan(project_id: str, org: str, source: str, view_box: str, shapes: list,
                     actor: str, filename=None) -> dict:
    ts = now_iso()
    existing = await _get_plan(project_id, org)
    doc = {"id": (existing or {}).get("id") or new_id(), "org_id": org,
           "project_id": project_id, "source": source, "view_box": view_box,
           "shapes": shapes, "filename": filename, "updated_by": actor, "updated_at": ts,
           "created_at": (existing or {}).get("created_at") or ts}
    await db.site_plans.update_one({"org_id": org, "project_id": project_id},
                                   {"$set": doc}, upsert=True)
    return doc


async def _units_of(project_id: str, org: str) -> list:
    return await db.units.find({"project_id": project_id, "org_id": org},
                               {"_id": 0, "id": 1, "code": 1}).to_list(3000)


@router.post("/{project_id}/generate")
async def generate_plan(project_id: str,
                        user: dict = Depends(require_permission("projects", "update"))):
    """Bangkitkan peta realistis (jalan, deret kavling, cul-de-sac, taman) untuk proyek.

    Dipakai selama SVG asli dari arsitek belum tersedia — semua kavling langsung
    terpetakan 1:1 ke unit sehingga peta bisa diuji utuh tanpa data palsu.
    """
    org = user.get("org_id", ORG_ID)
    if not await db.projects.count_documents({"id": project_id, "org_id": org}):
        raise HTTPException(404, "Proyek tidak ditemukan.")
    units = await _units_of(project_id, org)
    if not units:
        raise HTTPException(400, "Proyek ini belum punya unit — tambahkan unit terlebih dahulu.")
    built = svgplan.generate_demo_plan(units)
    plan = await _save_plan(project_id, org, "generated", built["view_box"],
                            built["shapes"], user.get("email"))
    return {"data": {"id": plan["id"], "source": plan["source"],
                     "stats": svgplan.plan_stats(plan["shapes"], units)}}


@router.post("/{project_id}/svg")
async def upload_svg(project_id: str, payload: SvgUpload,
                     user: dict = Depends(require_permission("projects", "update"))):
    """Unggah SVG site plan asli: geometri diekstrak lalu dicocokkan otomatis ke unit."""
    org = user.get("org_id", ORG_ID)
    if not await db.projects.count_documents({"id": project_id, "org_id": org}):
        raise HTTPException(404, "Proyek tidak ditemukan.")
    try:
        from site_plan_parse import parse_svg_rich
        parsed = parse_svg_rich(payload.svg)
    except ValueError as e:
        raise HTTPException(400, str(e))
    units = await _units_of(project_id, org)
    matched = svgplan.auto_match(parsed["shapes"], units)
    plan = await _save_plan(project_id, org, "uploaded", parsed["view_box"],
                            parsed["shapes"], user.get("email"), payload.filename)
    stats = svgplan.plan_stats(plan["shapes"], units)
    return {"data": {"id": plan["id"], "source": "uploaded", "auto_matched": matched,
                     "stats": stats}}


@router.put("/{project_id}/mapping")
async def save_mapping(project_id: str, payload: MappingSave,
                       user: dict = Depends(require_permission("projects", "update"))):
    """Simpan pemetaan shape→unit (dan/atau jenis shape) dari Studio Pemetaan."""
    org = user.get("org_id", ORG_ID)
    plan = await _get_plan(project_id, org)
    if not plan:
        raise HTTPException(404, "Peta site plan belum ada untuk proyek ini.")
    shapes = plan.get("shapes") or []
    index = {s["shape_id"]: s for s in shapes}
    changed = 0
    for item in payload.items:
        s = index.get(item.shape_id)
        if not s:
            continue
        if item.kind:
            s["kind"] = item.kind
        if item.unit_id is not None:
            uid = item.unit_id or None
            if uid:
                for other in shapes:
                    if other is not s and other.get("unit_id") == uid:
                        other["unit_id"] = None  # satu unit hanya boleh satu shape
            s["unit_id"] = uid
        changed += 1
    await db.site_plans.update_one({"id": plan["id"]}, {"$set": {
        "shapes": shapes, "updated_by": user.get("email"), "updated_at": now_iso()}})
    units = await _units_of(project_id, org)
    return {"data": {"updated": changed, "stats": svgplan.plan_stats(shapes, units)}}


@router.delete("/{project_id}/plan")
async def delete_plan(project_id: str,
                      user: dict = Depends(require_permission("projects", "update"))):
    """Hapus peta SVG — peta kembali memakai auto-layout blok (fallback jujur)."""
    org = user.get("org_id", ORG_ID)
    res = await db.site_plans.delete_one({"org_id": org, "project_id": project_id})
    return {"data": {"deleted": res.deleted_count}}


@router.get("/{project_id}/unit/{unit_id}")
async def unit_detail(project_id: str, unit_id: str,
                      user: dict = Depends(require_permission("projects", "view"))):
    """Detail lengkap satu kavling: spesifikasi, penjualan/AR/KPR, dan pembangunan.

    Merangkai data yang SUDAH ada di modul lain (deal, lead, AR, fase konstruksi,
    punch list, KPR) menjadi satu payload untuk drawer bertab di peta.
    """
    org = user.get("org_id", ORG_ID)
    unit = await db.units.find_one({"id": unit_id, "project_id": project_id, "org_id": org},
                                   {"_id": 0})
    if not unit:
        raise HTTPException(404, "Kavling tidak ditemukan.")
    lb, lt = _parse_luas(unit)
    deal_id = unit.get("booked_by_deal") or unit.get("reserved_by_deal")
    deal = await db.deals.find_one({"id": deal_id, "org_id": org}, {"_id": 0}) if deal_id else None
    lead = None
    if deal and deal.get("lead_id"):
        lead = await db.leads.find_one({"id": deal["lead_id"]}, {"_id": 0, "name": 1,
                                                                "phone": 1, "stage": 1,
                                                                "score_band": 1, "source": 1})
    ar = await db.ar_invoices.find_one({"org_id": org, "unit_id": unit_id}, {"_id": 0})
    schedule = []
    if ar:
        for it in ar.get("items", []):
            schedule.append({"label": it.get("label"), "amount": it.get("amount"),
                             "paid_amount": it.get("paid_amount", 0),
                             "due_date": it.get("due_date"), "status": it.get("status")})
    financing = await db.financing_apps.find_one(
        {"org_id": org, "deal_id": deal_id}, {"_id": 0, "bank_name": 1, "status": 1,
                                              "plafon": 1, "disbursed_total": 1}) if deal_id else None
    phases = await db.construction_phases.find(
        {"org_id": org, "project_id": project_id},
        {"_id": 0, "name": 1, "weight": 1, "progress": 1, "status": 1, "order": 1}
    ).sort("order", 1).to_list(50)
    punch = await db.punch_items.find(
        {"org_id": org, "unit_id": unit_id}, {"_id": 0, "title": 1, "severity": 1,
                                              "status": 1, "due_date": 1,
                                              "created_at": 1}).to_list(50)
    # Foto progres NYATA: temuan punch berfoto pada unit ini (termasuk foto perbaikan)
    # + dokumentasi buku harian proyek. Rujukan foto dibentuk p28_utils sehingga
    # file di object storage maupun data URL warisan sama-sama bisa dirender.
    photos = await p28.collect_unit_photos(org, project_id, unit_id, limit=8)
    # Bukti kerja berpasangan (sebelum → sesudah) per temuan pada kavling ini.
    repairs = await p28.collect_repair_pairs(org, unit_id, limit=6)
    activities = await db.activities.find(
        {"org_id": org, "entity_type": "unit", "entity_id": unit_id}, {"_id": 0}
    ).sort("created_at", -1).to_list(20)
    if deal_id:
        acts = await db.activities.find(
            {"org_id": org, "entity_type": "deal", "entity_id": deal_id}, {"_id": 0}
        ).sort("created_at", -1).to_list(20)
        activities = (activities + acts)[:20]
    return {"data": {
        "unit": {**serialize_doc(unit), "luas_bangunan": lb, "luas_tanah": lt,
                 "days_on_market": p28.days_on_market(
                     unit, (deal or {}).get("created_at"))},
        "deal": serialize_doc(deal), "lead": serialize_doc(lead),
        "ar": {"total": (ar or {}).get("total", 0), "paid": (ar or {}).get("paid", 0),
               "outstanding": (ar or {}).get("outstanding", 0),
               "status": (ar or {}).get("status"), "schedule": schedule} if ar else None,
        "financing": serialize_doc(financing),
        "construction": {"progress": unit.get("construction_progress", 0),
                         "status": unit.get("construction_status"),
                         "phases": serialize_doc(phases),
                         "punch_open": [p for p in serialize_doc(punch)
                                        if p.get("status") not in ("closed", "verified")],
                         "punch_total": len(punch), "photos": serialize_doc(photos),
                         "repairs": serialize_doc(repairs)},
        "activities": serialize_doc(activities),
    }}


@router.put("/{project_id}/layout")
async def save_layout(project_id: str, payload: LayoutSave,
                      user: dict = Depends(require_permission("projects", "update"))):
    """Persist custom plot positions (for a future drag-editor). Idempotent per unit."""
    org = user.get("org_id", ORG_ID)
    ts = now_iso()
    n = 0
    for p in payload.positions:
        plan = {"x": p.x, "y": p.y, "w": p.w or UNIT_W, "h": p.h or UNIT_H}
        if p.block:
            plan["block"] = p.block
        r = await db.units.update_one(
            {"id": p.unit_id, "project_id": project_id, "org_id": org},
            {"$set": {"plan": plan, "updated_at": ts}})
        n += r.modified_count
    return {"data": {"updated": n}}


# ------------------- Showroom publik (Fase 28b) -------------------
def _showroom_view(proj: dict) -> dict:
    token = proj.get("showroom_token")
    enabled = bool(proj.get("showroom_enabled"))
    return {"enabled": enabled, "token": token if enabled else None,
            "path": f"/showroom/{token}" if (enabled and token) else None,
            "headline": proj.get("showroom_headline"),
            "contact_wa": proj.get("showroom_contact_wa"),
            "show_price": proj.get("showroom_show_price", True)}


@router.get("/{project_id}/showroom")
async def get_showroom(project_id: str,
                       user: dict = Depends(require_permission("showroom", "view"))):
    """Status link showroom publik proyek (aktif/tidak + tautan yang bisa dibagikan)."""
    org = user.get("org_id", ORG_ID)
    proj = await db.projects.find_one({"id": project_id, "org_id": org}, {"_id": 0})
    if not proj:
        raise HTTPException(404, "Proyek tidak ditemukan.")
    return {"data": _showroom_view(proj)}


@router.post("/{project_id}/showroom")
async def set_showroom(project_id: str, payload: ShowroomConfig,
                       user: dict = Depends(require_permission("showroom", "update"))):
    """Aktifkan/tutup halaman showroom publik + putar ulang token bila link tersebar.

    Token acak (bukan id proyek) supaya orang tidak bisa menebak URL proyek lain, dan
    mematikan `enabled` langsung membuat halaman 404 tanpa menghapus datanya.
    """
    org = user.get("org_id", ORG_ID)
    proj = await db.projects.find_one({"id": project_id, "org_id": org}, {"_id": 0})
    if not proj:
        raise HTTPException(404, "Proyek tidak ditemukan.")
    token = proj.get("showroom_token")
    if payload.enabled and (payload.regenerate or not token):
        token = secrets.token_urlsafe(9)
    upd = {"showroom_enabled": payload.enabled, "showroom_token": token,
           "showroom_show_price": payload.show_price, "updated_at": now_iso()}
    if payload.headline is not None:
        upd["showroom_headline"] = payload.headline.strip() or None
    if payload.contact_wa is not None:
        wa = normalize_phone_e164(payload.contact_wa) if payload.contact_wa.strip() else None
        upd["showroom_contact_wa"] = wa
    await db.projects.update_one({"id": project_id, "org_id": org}, {"$set": upd})
    await audit_log(user, "update", "projects", project_id,
                    {"showroom_enabled": payload.enabled,
                     "token_regenerated": bool(payload.regenerate)})
    fresh = await db.projects.find_one({"id": project_id, "org_id": org}, {"_id": 0})
    return {"data": _showroom_view(fresh)}
