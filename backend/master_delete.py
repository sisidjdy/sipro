"""Hapus data master (lead, customer, unit, proyek) dengan pemeriksaan jejak transaksi.

Aturan: baris yang sudah punya jejak keuangan/kontrak (deal aktif, reservasi, invoice AR,
kontrak, pembayaran) TIDAK boleh dihapus — dibatalkan lewat alur pembatalan. Yang boleh
dihapus adalah data yang salah input / belum dipakai; turunannya yang bersifat catatan
(aktivitas, tugas, jadwal tanpa bukti kerja) ikut dibersihkan supaya tidak ada baris yatim.
"""
from db import ORG_ID, db


async def _count(coll: str, q: dict) -> int:
    try:
        return await db[coll].count_documents(q)
    except Exception:  # noqa: BLE001
        return 0


def _fmt(blockers: dict) -> str:
    return ", ".join(f"{v} {k}" for k, v in blockers.items() if v)


async def _cleanup_entity(org: str, entity_type: str, entity_id: str) -> None:
    await db.activities.delete_many({"org_id": org, "entity_type": entity_type, "entity_id": entity_id})
    await db.tasks.delete_many({"org_id": org, "related_entity_type": entity_type, "related_entity_id": entity_id})
    await db.notifications.delete_many({"org_id": org, "related_entity_type": entity_type,
                                        "related_entity_id": entity_id})


# ------------------------------------------------------------------ lead
async def lead_blockers(org: str, lead_id: str) -> dict:
    return {
        "deal": await _count("deals", {"org_id": org, "lead_id": lead_id, "status": {"$nin": ["cancelled", "lost"]}}),
        "customer": await _count("customers", {"org_id": org, "lead_id": lead_id}),
        "unit terikat": await _count("units", {"org_id": org, "lead_id": lead_id}),
    }


async def delete_lead(org: str, lead: dict) -> dict:
    lid = lead["id"]
    blockers = {k: v for k, v in (await lead_blockers(org, lid)).items() if v}
    if blockers:
        raise ValueError(f"Lead sudah punya {_fmt(blockers)} — tidak bisa dihapus. "
                         "Batalkan transaksinya dulu atau tandai lead sebagai lost.")
    removed = {}
    for coll, field in (("appointments", "lead_id"), ("surveys", "lead_id"), ("messages", "lead_id"),
                        ("conversations", "lead_id"), ("deals", "lead_id")):
        res = await db[coll].delete_many({"org_id": org, field: lid})
        if res.deleted_count:
            removed[coll] = res.deleted_count
    await _cleanup_entity(org, "lead", lid)
    await db.leads.delete_one({"id": lid, "org_id": org})
    return {"id": lid, "name": lead.get("name"), "deleted": True, "removed": removed}


# ------------------------------------------------------------------ customer
async def customer_blockers(org: str, cid: str) -> dict:
    cust = await db.customers.find_one({"id": cid, "org_id": org}, {"_id": 0, "lead_id": 1}) or {}
    deal_q = {"org_id": org, "status": {"$nin": ["cancelled", "lost"]},
              "$or": [{"customer_id": cid}] + ([{"lead_id": cust["lead_id"]}] if cust.get("lead_id") else [])}
    return {
        "deal": await _count("deals", deal_q),
        "kontrak": await _count("contracts", {"org_id": org, "customer_id": cid}),
        "invoice AR": await _count("ar_invoices", {"org_id": org, "customer_id": cid}),
        "pembayaran": await _count("payment_intakes", {"org_id": org, "customer_id": cid}),
        "unit dimiliki": await _count("units", {"org_id": org, "customer_id": cid}),
        "KPR": await _count("financing_apps", {"org_id": org, "customer_id": cid}),
    }


async def delete_customer(org: str, cust: dict) -> dict:
    cid = cust["id"]
    blockers = {k: v for k, v in (await customer_blockers(org, cid)).items() if v}
    if blockers:
        raise ValueError(f"Customer sudah punya {_fmt(blockers)} — tidak bisa dihapus. "
                         "Gunakan pembatalan transaksi; data pelanggan wajib tersimpan untuk jejak keuangan.")
    removed = {}
    for coll in ("documents", "complaints", "appointments"):
        res = await db[coll].delete_many({"org_id": org, "customer_id": cid})
        if res.deleted_count:
            removed[coll] = res.deleted_count
    await db.leads.update_many({"org_id": org, "customer_id": cid}, {"$unset": {"customer_id": ""}})
    await _cleanup_entity(org, "customer", cid)
    await db.customers.delete_one({"id": cid, "org_id": org})
    return {"id": cid, "name": cust.get("name"), "deleted": True, "removed": removed}


# ------------------------------------------------------------------ unit
async def unit_blockers(org: str, unit_id: str) -> dict:
    sched_ids = [s["id"] for s in await db.build_schedules.find(
        {"org_id": org, "unit_id": unit_id}, {"_id": 0, "id": 1}).to_list(10)]
    return {
        "deal": await _count("deals", {"org_id": org, "unit_id": unit_id, "status": {"$nin": ["cancelled", "lost"]}}),
        "kontrak": await _count("contracts", {"org_id": org, "unit_id": unit_id}),
        "invoice AR": await _count("ar_invoices", {"org_id": org, "unit_id": unit_id}),
        "SPK": await _count("spk", {"org_id": org, "unit_id": unit_id}),
        "pekerjaan terverifikasi": await _count("build_items", {"org_id": org, "schedule_id": {"$in": sched_ids},
                                                                "status": {"$in": ["done", "submitted"]}}) if sched_ids else 0,
        "serah terima": await _count("unit_handovers", {"org_id": org, "unit_id": unit_id}),
        "KPR": await _count("financing_apps", {"org_id": org, "unit_id": unit_id}),
    }


async def delete_unit(org: str, unit: dict) -> dict:
    uid = unit["id"]
    blockers = {k: v for k, v in (await unit_blockers(org, uid)).items() if v}
    if blockers:
        raise ValueError(f"Unit {unit.get('code')} dipakai oleh {_fmt(blockers)} — tidak bisa dihapus. "
                         "Batalkan transaksi/pekerjaannya dulu.")
    removed = {}
    sched_ids = [s["id"] for s in await db.build_schedules.find(
        {"org_id": org, "unit_id": uid}, {"_id": 0, "id": 1}).to_list(10)]
    if sched_ids:
        removed["build_items"] = (await db.build_items.delete_many({"org_id": org, "schedule_id": {"$in": sched_ids}})).deleted_count
        removed["build_schedules"] = (await db.build_schedules.delete_many({"org_id": org, "unit_id": uid})).deleted_count
    for coll in ("inspections", "punch_items", "complaints", "deals"):
        res = await db[coll].delete_many({"org_id": org, "unit_id": uid})
        if res.deleted_count:
            removed[coll] = res.deleted_count
    await db.site_plan_shapes.update_many({"org_id": org, "unit_id": uid}, {"$unset": {"unit_id": ""}})
    await _cleanup_entity(org, "unit", uid)
    await db.units.delete_one({"id": uid, "org_id": org})
    return {"id": uid, "code": unit.get("code"), "deleted": True, "removed": removed}


# ------------------------------------------------------------------ project
async def project_blockers(org: str, project_id: str) -> dict:
    unit_ids = [u["id"] for u in await db.units.find(
        {"org_id": org, "project_id": project_id}, {"_id": 0, "id": 1}).to_list(5000)]
    uq = {"org_id": org, "unit_id": {"$in": unit_ids}} if unit_ids else None
    return {
        "unit terjual/booking": await _count("units", {"org_id": org, "project_id": project_id,
                                                        "status": {"$in": ["reserved", "booked", "sold"]}}),
        "deal": await _count("deals", {**uq, "status": {"$nin": ["cancelled", "lost"]}}) if uq else 0,
        "kontrak": await _count("contracts", {**uq}) if uq else 0,
        "invoice AR": await _count("ar_invoices", {**uq}) if uq else 0,
        "SPK": await _count("spk", {"org_id": org, "project_id": project_id}),
        "PO": await _count("purchase_orders", {"org_id": org, "project_id": project_id}),
        "jurnal": await _count("journal_entries", {"org_id": org, "project_id": project_id}),
    }


PROJECT_CHILD_COLLECTIONS = (
    "units", "clusters", "blocks", "construction_phases", "build_schedules", "build_templates",
    "site_plans", "site_plan_shapes", "permits", "inspections", "punch_items", "budget_items",
    "budget_manual_entries", "project_targets",
)


async def delete_project(org: str, project: dict) -> dict:
    pid = project["id"]
    blockers = {k: v for k, v in (await project_blockers(org, pid)).items() if v}
    if blockers:
        raise ValueError(f"Proyek {project.get('code')} sudah punya {_fmt(blockers)} — tidak bisa dihapus. "
                         "Proyek berjalan diarsipkan (status), bukan dihapus.")
    removed = {}
    sched_ids = [s["id"] for s in await db.build_schedules.find(
        {"org_id": org, "project_id": pid}, {"_id": 0, "id": 1}).to_list(5000)]
    if sched_ids:
        removed["build_items"] = (await db.build_items.delete_many({"org_id": org, "schedule_id": {"$in": sched_ids}})).deleted_count
    for coll in PROJECT_CHILD_COLLECTIONS:
        try:
            res = await db[coll].delete_many({"org_id": org, "project_id": pid})
        except Exception:  # noqa: BLE001
            continue
        if res.deleted_count:
            removed[coll] = res.deleted_count
    await db.users.update_many({"org_id": org, "project_ids": pid}, {"$pull": {"project_ids": pid}})
    await _cleanup_entity(org, "project", pid)
    await db.projects.delete_one({"id": pid, "org_id": org})
    return {"id": pid, "code": project.get("code"), "deleted": True, "removed": removed}


async def blockers_of(org: str, kind: str, doc: dict) -> dict:
    fn = {"lead": lead_blockers, "customer": customer_blockers, "unit": unit_blockers,
          "project": project_blockers}[kind]
    return {k: v for k, v in (await fn(org or ORG_ID, doc["id"])).items() if v}
