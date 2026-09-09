"""MIGRASI V2 (Fase 39) — idempoten, beralasan, tidak pernah mengarang angka.

Aturan yang dipegang (lihat docs/v2/35_MIGRASI_DATA.md):
  * Tidak ada `DROP`, tidak ada penghapusan dokumen lama.
  * Nilai yang tidak diketahui → `null` + `needs_review=True`, BUKAN 0.
  * Boleh dijalankan berulang tanpa efek samping.
  * Ringkasan tiap jalan dicatat di `migration_runs` agar bisa diperiksa manusia.

Migrasi di sini menutup CR-05 (tidak ada cluster/blok) tanpa menyentuh jurnal keuangan.
"""
import logging
import re

import catalog as cat
import doc_registry as docreg
import masterplan as mp
from core_utils import new_id, now_iso
from db import db, ORG_ID

logger = logging.getLogger("sipro.migrations_v2")


def _parse_type_name(name: str) -> tuple:
    """'Tipe 45/90' -> (45, 90). Tidak bisa diparse -> (None, None) + needs_review."""
    m = re.search(r"(\d{2,4})\s*/\s*(\d{2,4})", str(name or ""))
    if not m:
        return None, None
    return int(m.group(1)), int(m.group(2))


# ---------------------------------------------------------------- M39-1
async def seed_default_cluster_block(org: str = ORG_ID) -> dict:
    """Setiap proyek punya cluster; setiap unit punya blok (dari `block`/prefiks kode lama)."""
    out = {"clusters": 0, "blocks": 0, "units_linked": 0}
    projects = await db.projects.find({"org_id": org}, {"_id": 0}).to_list(200)
    for project in projects:
        existed = await db.clusters.count_documents(
            {"org_id": org, "project_id": project["id"]})
        cluster = await mp.ensure_default_cluster(project, actor="migration")
        if not existed:
            out["clusters"] += 1
        units = await db.units.find(
            {"org_id": org, "project_id": project["id"],
             "$or": [{"block_id": None}, {"block_id": {"$exists": False}}]},
            {"_id": 0}).to_list(5000)
        for u in units:
            code = str(u.get("code") or "")
            bcode = str(u.get("block") or (code.split("-")[0] if "-" in code else "A")).upper()
            no = code.split("-", 1)[1] if "-" in code else code
            block = await db.blocks.find_one(
                {"org_id": org, "cluster_id": cluster["id"], "code": bcode}, {"_id": 0})
            if not block:
                ts = now_iso()
                block = {"id": new_id(), "org_id": org, "project_id": project["id"],
                         "cluster_id": cluster["id"], "cluster_code": cluster["code"],
                         "code": bcode, "name": f"Blok {bcode}", "order": 0,
                         "notes": "Dibuat migrasi V2 dari prefiks kode unit.",
                         "created_by": "migration", "created_at": ts, "updated_at": ts}
                await db.blocks.insert_one(dict(block))
                out["blocks"] += 1
            await db.units.update_one({"id": u["id"]}, {"$set": {
                "cluster_id": cluster["id"], "cluster_code": cluster["code"],
                "block_id": block["id"], "block": bcode, "no": no,
                "updated_at": now_iso()}})
            out["units_linked"] += 1
    return out


# ---------------------------------------------------------------- M39-2
async def map_unit_type_enum(org: str = ORG_ID) -> dict:
    """Enum teks `units.type` → master `unit_types` (harga = MEDIAN harga unit nyata)."""
    out = {"types_created": 0, "needs_review": [], "units_tagged": 0}
    names = await db.units.distinct("type", {"org_id": org})
    for name in [n for n in names if n]:
        code = re.sub(r"[^A-Z0-9]+", "-", str(name).upper()).strip("-")[:24]
        existing = await db.unit_types.find_one({"org_id": org, "code": code}, {"_id": 0})
        if not existing:
            lb, lt = _parse_type_name(name)
            prices = [u["price"] for u in await db.units.find(
                {"org_id": org, "type": name}, {"_id": 0, "price": 1}).to_list(2000)
                if u.get("price")]
            prices.sort()
            base = prices[len(prices) // 2] if prices else None
            ts = now_iso()
            doc = {"id": new_id(), "org_id": org, "code": code, "name": str(name),
                   "building_area": lb, "land_area_std": lt, "base_price": base,
                   "floors": 1, "spec": {}, "active": True,
                   "needs_review": bool(lb is None or lt is None or base is None),
                   "note": "Dibuat migrasi V2 dari enum tipe lama; harga = median harga unit nyata.",
                   "created_by": "migration", "created_at": ts, "updated_at": ts}
            await db.unit_types.insert_one(dict(doc))
            out["types_created"] += 1
            if doc["needs_review"]:
                out["needs_review"].append(code)
            existing = doc
        res = await db.units.update_many(
            {"org_id": org, "type": name,
             "$or": [{"unit_type_code": None}, {"unit_type_code": {"$exists": False}}]},
            {"$set": {"unit_type_code": existing["code"], "unit_type_id": existing["id"]}})
        out["units_tagged"] += res.modified_count
    return out


# ---------------------------------------------------------------- M39-3
async def backfill_unit_dual_status(org: str = ORG_ID) -> dict:
    """Pastikan kedua status ada + riwayat status terbentuk (tanpa mengubah nilai lama)."""
    out = {"construction_status": 0, "history": 0, "scheduled": 0}
    res = await db.units.update_many(
        {"org_id": org, "$or": [{"construction_status": None},
                                {"construction_status": {"$exists": False}}]},
        {"$set": {"construction_status": "not_started"}})
    out["construction_status"] = res.modified_count
    # Unit yang punya jadwal bangun tetapi belum mulai → status 'scheduled' (nilai baru).
    scheduled_ids = await db.build_schedules.distinct("unit_id", {"org_id": org})
    if scheduled_ids:
        res = await db.units.update_many(
            {"org_id": org, "id": {"$in": scheduled_ids}, "construction_status": "not_started"},
            {"$set": {"construction_status": "scheduled"}})
        out["scheduled"] = res.modified_count
    units = await db.units.find(
        {"org_id": org, "$or": [{"status_history": None}, {"status_history": {"$exists": False}}]},
        {"_id": 0, "id": 1, "status": 1, "created_at": 1}).to_list(5000)
    for u in units:
        await db.units.update_one({"id": u["id"]}, {"$set": {"status_history": [{
            "field": "status", "from": None, "to": u.get("status"),
            "at": u.get("created_at") or now_iso(), "actor": "migration",
            "reason": "Riwayat awal dibentuk migrasi V2 (nilai tidak diubah).",
            "estimated": True}]}})
        out["history"] += 1
    return out


# ---------------------------------------------------------------- M39-4
UNIT_SHAPE_KINDS = ("unit", "lot", "kavling")


async def link_siteplan_shapes(org: str = ORG_ID) -> dict:
    """Tautkan shape peta <-> unit dua arah + laporkan yang tidak berpasangan.

    Catatan: generator peta memakai `kind='lot'` untuk kavling (bukan 'unit'), jadi kedua
    penamaan diterima — kalau hanya 'unit' yang dicek, 18 kavling demo tidak pernah tertaut.
    """
    out = {"linked": 0, "back_linked": 0, "shapes_without_unit": [], "units_without_shape": 0}
    plans = await db.site_plans.find({"org_id": org}, {"_id": 0}).to_list(100)
    for plan in plans:
        units = await db.units.find({"org_id": org, "project_id": plan["project_id"]},
                                    {"_id": 0, "id": 1, "code": 1}).to_list(5000)
        by_code = {str(u["code"]).upper(): u["id"] for u in units}
        shapes = plan.get("shapes") or []
        changed = False
        for sh in shapes:
            if sh.get("kind") not in UNIT_SHAPE_KINDS:
                continue
            uid = sh.get("unit_id") or by_code.get(str(sh.get("label") or "").upper())
            if not uid:
                out["shapes_without_unit"].append(
                    f"{plan['project_id'][:8]}:{sh.get('shape_id')}({sh.get('label') or '-'})")
                continue
            if not sh.get("unit_id"):
                sh["unit_id"] = uid
                changed = True
                out["linked"] += 1
            res = await db.units.update_one(
                {"id": uid, "org_id": org,
                 "siteplan.shape_id": {"$ne": sh.get("shape_id")}},
                {"$set": {"siteplan": {"shape_id": sh.get("shape_id"),
                                       "centroid": sh.get("centroid"),
                                       "plan_id": plan.get("id")}}})
            out["back_linked"] += res.modified_count
        if changed:
            await db.site_plans.update_one({"id": plan["id"]}, {
                "$set": {"shapes": shapes, "updated_at": now_iso()}})
        out["units_without_shape"] += await db.units.count_documents(
            {"org_id": org, "project_id": plan["project_id"],
             "$or": [{"siteplan": None}, {"siteplan": {"$exists": False}}]})
    out["shapes_without_unit"] = out["shapes_without_unit"][:20]
    return out


# ---------------------------------------------------------------- runner
async def run_v2_migrations(org: str = ORG_ID) -> dict:
    """Dijalankan pada startup (idempoten). Ringkasan disimpan di `migration_runs`."""
    report = {"name": "v2_fase39", "at": now_iso(), "org_id": org}
    report["catalog_seed"] = await cat.seed_defaults(org)
    import pricing_engine as _pe
    report["pricing_seed"] = await _pe.seed_defaults(org)
    report["doc_requirements_seed"] = await docreg.seed_defaults(org)
    report["M39_1_cluster_block"] = await seed_default_cluster_block(org)
    report["M39_2_unit_types"] = await map_unit_type_enum(org)
    report["M39_3_dual_status"] = await backfill_unit_dual_status(org)
    report["M39_4_siteplan"] = await link_siteplan_shapes(org)
    report["stats"] = await mp.recompute_stats(None, org)
    changed = any(
        isinstance(v, dict) and any(isinstance(x, int) and x > 0 for x in v.values())
        for v in report.values())
    if changed:
        await db.migration_runs.insert_one({"id": new_id(), **report})
        logger.info("Migrasi V2 (Fase 39): %s", {k: v for k, v in report.items()
                                                 if isinstance(v, dict)})
    return report
