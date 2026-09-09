"""Seed EPIC 2.4 — QC/Inspeksi: template checklist + 1 inspeksi demo (indexes internal)."""
from db import db, ORG_ID
from core_utils import new_id

TEMPLATES = [
    {"code": "QC-STR", "name": "Inspeksi Struktur", "category": "structural", "items": [
        {"key": "besi", "label": "Pembesian sesuai gambar"},
        {"key": "bekisting", "label": "Bekisting kokoh & rapi"},
        {"key": "cor", "label": "Mutu beton/cor sesuai spek"},
        {"key": "dimensi", "label": "Dimensi elemen sesuai gambar"}]},
    {"code": "QC-MEP", "name": "Inspeksi MEP", "category": "mep", "items": [
        {"key": "pipa", "label": "Instalasi pipa tidak bocor"},
        {"key": "listrik", "label": "Instalasi listrik sesuai SLD"},
        {"key": "grounding", "label": "Grounding terpasang benar"}]},
    {"code": "QC-HO", "name": "Inspeksi Serah Terima (Handover)", "category": "handover", "items": [
        {"key": "dinding", "label": "Dinding & cat rapi tanpa retak"},
        {"key": "pintu", "label": "Pintu & jendela berfungsi"},
        {"key": "sanitair", "label": "Sanitair & air mengalir baik"},
        {"key": "titik_listrik", "label": "Semua titik listrik berfungsi"},
        {"key": "kebersihan", "label": "Unit bersih siap serah terima"}]},
]


async def seed_inspections(project_id, ts):
    await db.inspections.create_index([("org_id", 1), ("project_id", 1)])
    await db.inspections.create_index([("org_id", 1), ("status", 1)])
    await db.inspection_templates.create_index([("org_id", 1), ("code", 1)], unique=True)

    if not await db.inspection_templates.count_documents({"org_id": ORG_ID}):
        await db.inspection_templates.insert_many([
            {"id": new_id(), "org_id": ORG_ID, "is_active": True, "created_at": ts, **t} for t in TEMPLATES])
    if await db.inspections.count_documents({"org_id": ORG_ID}):
        return

    phase = await db.construction_phases.find_one(
        {"org_id": ORG_ID, "project_id": project_id, "name": "Struktur"}, {"_id": 0, "id": 1})
    tpl = TEMPLATES[0]
    items = [{"key": it["key"], "label": it["label"], "result": "pending", "note": None} for it in tpl["items"]]
    await db.inspections.insert_one({
        "id": new_id(), "org_id": ORG_ID, "inspection_number": f"QC/{ts[:4]}/0001",
        "project_id": project_id, "project_name": "Cluster Asri Blok A",
        "unit_id": None, "phase_id": phase["id"] if phase else None, "template_id": None,
        "template_code": "QC-STR", "category": "structural", "title": "Inspeksi Struktur",
        "items": items, "status": "in_progress",
        "pass_count": 0, "fail_count": 0, "na_count": 0, "pending_count": len(items),
        "punch_ids": [], "punch_created": False, "result_note": None,
        "created_by": "site@sipro.co.id", "created_at": ts, "updated_at": ts,
        "finalized_by": None, "finalized_at": None,
    })
