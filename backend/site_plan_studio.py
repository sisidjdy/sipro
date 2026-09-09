"""Studio Site Plan (Fase 72) — mesin: latar gambar, bentuk manual (tracing), pencocokan
otomatis berlabel, usulan & pembuatan unit dari bentuk peta."""
import io
import re

import masterplan
import site_plan_svg as svgplan
import storage
from core_utils import new_id, now_iso
from db import db
from models_v2 import BlockCreate
from site_plan_parse import area, centroid, parse_code, points_of, poly_str

KINDS = ("lot", "road", "green", "water", "facility", "boundary")


async def get_plan(project_id: str, org: str):
    return await db.site_plans.find_one({"org_id": org, "project_id": project_id}, {"_id": 0})


async def save_plan(project_id: str, org: str, actor: str, **fields) -> dict:
    ts = now_iso()
    existing = await get_plan(project_id, org)
    doc = {**(existing or {}), **fields, "id": (existing or {}).get("id") or new_id(),
           "org_id": org, "project_id": project_id, "updated_by": actor, "updated_at": ts,
           "created_at": (existing or {}).get("created_at") or ts}
    doc.setdefault("shapes", [])
    doc.setdefault("source", "manual")
    await db.site_plans.update_one({"org_id": org, "project_id": project_id},
                                   {"$set": doc}, upsert=True)
    return doc


async def units_light(project_id: str, org: str) -> list:
    return await db.units.find({"project_id": project_id, "org_id": org},
                               {"_id": 0, "id": 1, "code": 1, "block": 1, "no": 1, "status": 1,
                                "type": 1, "unit_type_code": 1, "block_id": 1,
                                "construction_progress": 1, "legal_stage": 1}).to_list(5000)


async def studio_payload(project_id: str, org: str) -> dict:
    plan = await get_plan(project_id, org)
    units = await units_light(project_id, org)
    blocks = await db.blocks.find({"org_id": org, "project_id": project_id},
                                  {"_id": 0, "id": 1, "code": 1, "cluster_id": 1,
                                   "cluster_code": 1}).sort("code", 1).to_list(500)
    clusters = await db.clusters.find({"org_id": org, "project_id": project_id},
                                      {"_id": 0, "id": 1, "code": 1, "name": 1}).to_list(200)
    types = await db.unit_types.find({"org_id": org, "active": {"$ne": False}},
                                     {"_id": 0, "id": 1, "code": 1, "name": 1,
                                      "base_price": 1}).sort("code", 1).to_list(300)
    if plan:
        plan["stats"] = svgplan.plan_stats(plan.get("shapes") or [], units)
        bg = plan.get("background")
        if bg and bg.get("file_id"):
            plan["background"] = {**bg, "url": f"/api/files/{bg['file_id']}"}
    return {"plan": plan, "units": units, "blocks": blocks, "clusters": clusters,
            "unit_types": types, "palette": await get_palette(org),
            "project_name": ((await db.projects.find_one({"id": project_id, "org_id": org},
                                                         {"_id": 0, "name": 1})) or {}).get("name")}


# ------------------------------------------------------------------ palet warna (per organisasi)
PALETTE_GROUPS = ("sales", "build", "mapping")
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


async def get_palette(org: str) -> dict:
    doc = await db.site_plan_palettes.find_one({"org_id": org}, {"_id": 0})
    return (doc or {}).get("palette") or {}


async def save_palette(org: str, palette: dict, actor: str) -> dict:
    """Simpan hanya warna yang valid (#rrggbb) per grup/kunci; kosong = kembali ke bawaan."""
    clean = {}
    for group, items in (palette or {}).items():
        if group not in PALETTE_GROUPS or not isinstance(items, dict):
            continue
        for key, col in items.items():
            if not isinstance(col, dict):
                continue
            entry = {k: v for k, v in col.items() if k in ("fill", "stroke", "text") and
                     isinstance(v, str) and _HEX.match(v)}
            if isinstance(col.get("label"), str) and col["label"].strip():
                entry["label"] = col["label"].strip()[:40]
            if entry:
                clean.setdefault(group, {})[str(key)[:32]] = entry
    await db.site_plan_palettes.update_one({"org_id": org}, {"$set": {
        "org_id": org, "palette": clean, "updated_by": actor, "updated_at": now_iso()}}, upsert=True)
    return clean


# ------------------------------------------------------------------ latar gambar
def pdf_to_png(data: bytes, page: int = 1, max_dim: int = 3000) -> bytes:
    """Render satu halaman PDF site plan arsitek menjadi PNG (PyMuPDF), sisi terpanjang ≤ max_dim."""
    import pymupdf
    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception:
        raise ValueError("Berkas PDF tidak bisa dibuka.")
    if doc.page_count < 1:
        raise ValueError("PDF tidak memuat halaman.")
    page = max(1, min(page, doc.page_count))
    pg = doc[page - 1]
    rect = pg.rect
    zoom = min(max_dim / max(rect.width, rect.height, 1), 6.0)
    pix = pg.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
    return pix.tobytes("png"), doc.page_count, page


async def set_background(project_id: str, org: str, data: bytes, filename: str,
                         content_type: str, actor: str, page: int = 1) -> dict:
    is_pdf = (content_type or "").lower() == "application/pdf" or \
        (filename or "").lower().endswith(".pdf") or data[:5] == b"%PDF-"
    pages = None
    if is_pdf:
        data, pages, page = pdf_to_png(data, page)
        filename = re.sub(r"\.pdf$", "", filename or "siteplan", flags=re.I) + f"-hal{page}.png"
        content_type = "image/png"
    try:
        from PIL import Image
        im = Image.open(io.BytesIO(data))
        w, h = im.size
    except Exception:
        raise ValueError("Berkas bukan gambar PNG/JPG/PDF yang bisa dibaca.")
    rec = await storage.save_file(data=data, filename=filename, content_type=content_type,
                                  org_id=org, owner_type="site_plan", owner_id=project_id,
                                  uploaded_by=actor, doc_type="site_plan_background",
                                  tag="siteplan", optimize=False)
    plan = await get_plan(project_id, org)
    fields = {"background": {"file_id": rec["id"], "width": w, "height": h,
                             "filename": filename, "opacity": 1.0,
                             "source": "pdf" if is_pdf else "image",
                             "pdf_page": page if is_pdf else None,
                             "pdf_pages": pages}}
    if not plan or not plan.get("shapes"):
        fields["view_box"] = f"0 0 {w} {h}"
        fields["source"] = "manual"
    return await save_plan(project_id, org, actor, **fields)


async def clear_background(project_id: str, org: str, actor: str) -> dict:
    plan = await get_plan(project_id, org)
    if not plan:
        raise LookupError("Peta belum ada.")
    await db.site_plans.update_one({"id": plan["id"]}, {"$unset": {"background": ""},
                                                        "$set": {"updated_at": now_iso(),
                                                                 "updated_by": actor}})
    return await get_plan(project_id, org)


# ------------------------------------------------------------------ bentuk manual
def _shape_from_points(pts: list, kind: str, label: str = None, sid: str = None) -> dict:
    if len(pts) < 3:
        raise ValueError("Poligon minimal 3 titik.")
    if area(pts) <= 0:
        raise ValueError("Poligon tidak punya luas (titik segaris).")
    return {"shape_id": sid or f"manual-{new_id()[:8]}", "kind": kind if kind in KINDS else "lot",
            "label": (label or "").strip() or None, "unit_id": None,
            "geom": {"type": "polygon", "points": poly_str(pts)}, "centroid": centroid(pts),
            "manual": True}


async def add_shapes(project_id: str, org: str, items: list, actor: str) -> dict:
    plan = await get_plan(project_id, org)
    shapes = list((plan or {}).get("shapes") or [])
    added = []
    for it in items:
        pts = [(float(p[0]), float(p[1])) for p in (it.get("points") or [])]
        s = _shape_from_points(pts, it.get("kind") or "lot", it.get("label"))
        if it.get("unit_id"):
            for o in shapes:
                if o.get("unit_id") == it["unit_id"]:
                    o["unit_id"] = None
            s["unit_id"] = it["unit_id"]
        shapes.append(s)
        added.append(s)
    fields = {"shapes": shapes}
    if not plan or not plan.get("view_box"):
        xs = [p[0] for s in shapes for p in points_of(s["geom"])]
        ys = [p[1] for s in shapes for p in points_of(s["geom"])]
        fields["view_box"] = f"0 0 {int(max(xs) + 40)} {int(max(ys) + 40)}"
    await save_plan(project_id, org, actor, **fields)
    return {"added": added, "total": len(shapes)}


async def update_shape(project_id: str, org: str, sid: str, patch: dict, actor: str) -> dict:
    plan = await get_plan(project_id, org)
    if not plan:
        raise LookupError("Peta belum ada.")
    shapes = plan.get("shapes") or []
    s = next((x for x in shapes if x["shape_id"] == sid), None)
    if not s:
        raise LookupError("Bentuk tidak ditemukan.")
    if patch.get("points"):
        pts = [(float(p[0]), float(p[1])) for p in patch["points"]]
        s.update(_shape_from_points(pts, s["kind"], s.get("label"), sid=sid)
                 | {"unit_id": s.get("unit_id"), "manual": bool(s.get("manual"))})
    if patch.get("kind") in KINDS:
        s["kind"] = patch["kind"]
        if s["kind"] != "lot":
            s["unit_id"] = None
    if "label" in patch:
        s["label"] = (patch["label"] or "").strip() or None
    if "unit_id" in patch:
        uid = patch["unit_id"] or None
        if uid:
            for o in shapes:
                if o is not s and o.get("unit_id") == uid:
                    o["unit_id"] = None
        s["unit_id"] = uid
    await db.site_plans.update_one({"id": plan["id"]}, {"$set": {
        "shapes": shapes, "updated_at": now_iso(), "updated_by": actor}})
    return s


async def delete_shape(project_id: str, org: str, sid: str, actor: str) -> int:
    plan = await get_plan(project_id, org)
    if not plan:
        raise LookupError("Peta belum ada.")
    shapes = [s for s in (plan.get("shapes") or []) if s["shape_id"] != sid]
    await db.site_plans.update_one({"id": plan["id"]}, {"$set": {
        "shapes": shapes, "updated_at": now_iso(), "updated_by": actor}})
    return len(shapes)


# ------------------------------------------------------------------ pencocokan & usulan
def _norm(code: str) -> str:
    s = re.sub(r"[^A-Z0-9]", "", (code or "").upper())
    return re.sub(r"(?<=[A-Z])0+(?=\d)", "", s)


def auto_match(shapes: list, units: list) -> int:
    """Cocokkan bentuk kavling ke unit lewat label/id (toleran tanda pisah & nol depan)."""
    by_code = {}
    for u in units:
        if u.get("code"):
            by_code.setdefault(_norm(u["code"]), u["id"])
            pc = parse_code(u["code"])
            if pc:
                by_code.setdefault(_norm(pc[0] + pc[1]), u["id"])
    taken = {s["unit_id"] for s in shapes if s.get("unit_id")}
    hit = 0
    for s in shapes:
        if s.get("unit_id") or s.get("kind") != "lot":
            continue
        cands = [_norm(s.get("label") or ""), _norm(s["shape_id"])]
        pc = parse_code(s.get("label") or "")
        if pc:
            cands.insert(0, _norm(pc[0] + pc[1]))
        match = next((by_code[c] for c in cands if c and c in by_code and by_code[c] not in taken), None)
        if match:
            s["unit_id"] = match
            taken.add(match)
            hit += 1
    return hit


async def rematch(project_id: str, org: str, actor: str) -> dict:
    plan = await get_plan(project_id, org)
    if not plan:
        raise LookupError("Peta belum ada.")
    units = await units_light(project_id, org)
    hit = auto_match(plan.get("shapes") or [], units)
    await db.site_plans.update_one({"id": plan["id"]}, {"$set": {
        "shapes": plan["shapes"], "updated_at": now_iso(), "updated_by": actor}})
    return {"matched": hit, "stats": svgplan.plan_stats(plan["shapes"], units)}


async def suggest_units(project_id: str, org: str) -> list:
    """Untuk tiap bentuk kavling yang belum terpetakan: tebakan blok/nomor dari label,
    apakah bloknya sudah ada, dan apakah unit dengan kode itu sudah ada."""
    plan = await get_plan(project_id, org)
    if not plan:
        return []
    units = await units_light(project_id, org)
    by_code = {_norm(u["code"]): u for u in units if u.get("code")}
    blocks = {b["code"].upper(): b for b in await db.blocks.find(
        {"org_id": org, "project_id": project_id}, {"_id": 0, "id": 1, "code": 1,
                                                    "cluster_id": 1}).to_list(500)}
    out = []
    for s in plan.get("shapes") or []:
        if s.get("kind") != "lot" or s.get("unit_id"):
            continue
        pc = parse_code(s.get("label") or "")
        block_code, no = (pc if pc else (None, None))
        existing = by_code.get(_norm(f"{block_code}{no}")) if pc else None
        out.append({"shape_id": s["shape_id"], "label": s.get("label"),
                    "block_code": block_code, "no": no, "parsed": bool(pc),
                    "block_exists": bool(block_code and block_code in blocks),
                    "block_id": (blocks.get(block_code) or {}).get("id") if block_code else None,
                    "existing_unit_id": (existing or {}).get("id"),
                    "existing_unit_code": (existing or {}).get("code")})
    return out


async def create_units(project_id: str, org: str, items: list, actor: str, *,
                       create_blocks: bool, cluster_id: str = None,
                       unit_type_code: str = None) -> dict:
    """Lahirkan unit dari bentuk peta. Tiap baris diproses sendiri: satu kegagalan tidak
    menggagalkan yang lain. Blok yang belum ada dibuat hanya bila `create_blocks`."""
    project = await db.projects.find_one({"id": project_id, "org_id": org}, {"_id": 0})
    if not project:
        raise LookupError("Proyek tidak ditemukan.")
    plan = await get_plan(project_id, org)
    if not plan:
        raise LookupError("Peta belum ada.")
    shapes = plan.get("shapes") or []
    by_sid = {s["shape_id"]: s for s in shapes}
    cluster = (await db.clusters.find_one({"id": cluster_id, "org_id": org}, {"_id": 0})
               if cluster_id else None) or await masterplan.ensure_default_cluster(project, actor)
    results, created, mapped = [], 0, 0
    for it in items:
        sid = it.get("shape_id")
        s = by_sid.get(sid)
        row = {"shape_id": sid, "ok": False}
        try:
            if not s:
                raise ValueError("Bentuk tidak ditemukan di peta.")
            if s.get("unit_id"):
                raise ValueError("Bentuk sudah terpetakan.")
            bcode = (it.get("block_code") or "").strip().upper()
            no = (it.get("no") or "").strip()
            if not bcode or not no:
                raise ValueError("Blok dan nomor wajib diisi.")
            block = await db.blocks.find_one({"org_id": org, "project_id": project_id,
                                              "code": bcode}, {"_id": 0})
            if not block:
                if not create_blocks:
                    raise ValueError(f"Blok '{bcode}' belum ada — centang 'buat blok baru' "
                                     "atau pilih blok yang ada.")
                block = await masterplan.create_block(cluster["id"], BlockCreate(code=bcode),
                                                      actor, org)
                row["block_created"] = True
            bcluster = await db.clusters.find_one({"id": block["cluster_id"]}, {"_id": 0})
            tcode = it.get("unit_type_code") or unit_type_code
            utype = await masterplan._unit_type(tcode, org) if tcode else None
            if tcode and not utype:
                raise ValueError(f"Tipe unit '{tcode}' tidak ada.")
            code = masterplan.unit_code(block["code"], no)
            existing = await db.units.find_one({"org_id": org, "project_id": project_id,
                                                "code": code}, {"_id": 0, "id": 1})
            if existing:
                if not it.get("map_existing", True):
                    raise ValueError(f"Unit {code} sudah ada.")
                uid, row["reused"] = existing["id"], True
            else:
                doc = await masterplan._new_unit_doc(block, bcluster, project, utype, no=no,
                                                     price=it.get("price"), actor=actor,
                                                     notes="Dibuat dari Studio Site Plan")
                await db.units.insert_one(dict(doc))
                uid, created = doc["id"], created + 1
            for o in shapes:
                if o.get("unit_id") == uid:
                    o["unit_id"] = None
            s["unit_id"] = uid
            if not s.get("label"):
                s["label"] = code
            row.update({"ok": True, "unit_id": uid, "code": code})
            mapped += 1
        except (ValueError, LookupError) as e:
            row["error"] = str(e)
        results.append(row)
    await db.site_plans.update_one({"id": plan["id"]}, {"$set": {
        "shapes": shapes, "updated_at": now_iso(), "updated_by": actor}})
    if created:
        await masterplan.recompute_stats(project_id, org)
    return {"created": created, "mapped": mapped, "failed": sum(1 for r in results if not r["ok"]),
            "results": results}
