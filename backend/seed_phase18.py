"""Seed EPIC 2.6 — Material Requisition + Budget (RAB link) — Phase 18.

Menaut sebagian material ke item BoQ + budget_qty (RAB dalam satuan material),
lalu membuat 2 permintaan material demo: satu 'disetujui' (belum dikeluarkan)
untuk mendemokan alur Keluarkan, dan satu 'dikeluarkan' yang membuat pemakaian
melampaui RAB -> memicu tugas & notifikasi over-budget ke PM.
"""
from db import db, ORG_ID
from core_utils import new_id, now_iso, due_in

# code -> (BoQ cost_code, budget_qty dalam satuan material)
BUDGETS = {"SMN": ("STR-01", 250), "BSI": ("STR-02", 350),
           "PSR": ("STR-01", 150), "BTA": ("ARS-01", 4000)}


async def seed_material_requisitions(project_id, material_ids, ts):
    await db.material_requisitions.create_index([("org_id", 1), ("project_id", 1), ("status", 1)])
    await db.material_requisitions.create_index([("org_id", 1), ("req_number", 1)])
    if await db.material_requisitions.count_documents({"org_id": ORG_ID}):
        return

    boq_rows = await db.boq_items.find(
        {"org_id": ORG_ID, "project_id": project_id}, {"_id": 0, "id": 1, "cost_code": 1}).to_list(100)
    boq = {b["cost_code"]: b["id"] for b in boq_rows}
    for code, (cc, bqty) in BUDGETS.items():
        m = material_ids.get(code)
        if not m:
            continue
        await db.materials.update_one(
            {"id": m["id"], "org_id": ORG_ID},
            {"$set": {"boq_item_id": boq.get(cc), "budget_qty": float(bqty),
                      "over_budget": False, "consumed_qty": 0.0, "updated_at": ts}})

    proj = await db.projects.find_one({"id": project_id, "org_id": ORG_ID}, {"_id": 0, "name": 1}) or {}
    pname = proj.get("name")

    def _item(code, qty, issued=0.0):
        m = material_ids[code]
        return {"material_id": m["id"], "code": code, "name": m["name"], "uom": m["uom"],
                "qty_requested": float(qty), "qty_issued": float(issued)}

    # PR/0001 — disetujui, belum dikeluarkan (demo alur Keluarkan).
    await db.material_requisitions.insert_one({
        "id": new_id(), "org_id": ORG_ID, "req_number": f"PR/{ts[:4]}/0001",
        "project_id": project_id, "project_name": pname, "phase_id": None,
        "phase_name": "Struktur", "task_id": None,
        "purpose": "Kebutuhan pengecoran kolom lantai 2",
        "items": [_item("SMN", 40), _item("BSI", 20)], "status": "approved",
        "requested_by": "site@sipro.co.id", "approved_by": "pm@sipro.co.id",
        "approved_at": ts, "issued_by": None, "issued_at": None,
        "rejected_by": None, "rejected_at": None, "note": None,
        "created_at": due_in(hours=-20), "updated_at": ts})

    # PR/0002 — dikeluarkan (BTA 5000) -> pemakaian melampaui RAB (4000) -> alert.
    rid2 = new_id()
    await db.material_requisitions.insert_one({
        "id": rid2, "org_id": ORG_ID, "req_number": f"PR/{ts[:4]}/0002",
        "project_id": project_id, "project_name": pname, "phase_id": None,
        "phase_name": "Dinding & Atap", "task_id": None,
        "purpose": "Pasangan dinding bata Blok A", "items": [_item("BTA", 5000, 5000)],
        "status": "issued", "requested_by": "site@sipro.co.id",
        "approved_by": "pm@sipro.co.id", "approved_at": due_in(hours=-10),
        "issued_by": "site@sipro.co.id", "issued_at": ts,
        "rejected_by": None, "rejected_at": None, "note": None,
        "created_at": due_in(hours=-12), "updated_at": ts})
    bta = material_ids["BTA"]
    await db.material_txns.insert_one({
        "id": new_id(), "org_id": ORG_ID, "project_id": project_id, "material_id": bta["id"],
        "type": "out", "qty": 5000, "note": "Pengeluaran PR/0002 (pasangan bata)",
        "ref": f"PR/{ts[:4]}/0002", "requisition_id": rid2, "phase_id": None, "task_id": None,
        "actor": "site@sipro.co.id", "created_at": ts})
    from routers.materials_router import _check_material_budget
    await _check_material_budget(project_id, bta["id"], ORG_ID, "site@sipro.co.id")
