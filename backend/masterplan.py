"""HIERARKI PROYEK (Fase 39): proyek → cluster → blok → unit (+ tipe unit).

Masalah yang diperbaiki (audit CR-05): tidak ada entitas cluster/blok sama sekali. "Blok"
hanya hasil `code.split("-")` pada kode unit, dan unit dibuat lewat generator prefix. Akibat
nyata: harga/target per cluster tidak mungkin, site plan tidak bisa dipetakan per blok,
laporan penjualan kasar, dan wiring unit → customer → konstruksi → finance rapuh.

Kompatibilitas dijaga ketat (tidak ada rename berisiko):
  * STATUS PENJUALAN tetap `units.status` (SSOT `unit_status`, kini + handed_over/blocked)
  * STATUS PEMBANGUNAN tetap `units.construction_status` (kini + scheduled/on_hold)
  * luas tetap `luas_tanah` / `luas_bangunan`, hook tetap `corner` (dipakai site plan & portal)
  * `units.type` (teks tipe) tetap diisi untuk kode lama; ditambah `unit_type_id`/`unit_type_code`
"""
import logging

import numbering as nb
import reference as ref
import settings_store as cfg
from core_utils import new_id, now_iso, parse_pagination
from db import db, ORG_ID

logger = logging.getLogger("sipro.masterplan")

ACTIVE_SALES = ("reserved", "booked", "sold", "handed_over")


def _clean(payload) -> dict:
    return {k: v for k, v in payload.model_dump(exclude_none=True).items()}


def unit_code(block_code: str, no) -> str:
    s = str(no).strip()
    return f"{block_code}-{s.zfill(2) if s.isdigit() else s.upper()}"


# ------------------------------------------------------------------ cluster
async def ensure_default_cluster(project: dict, actor: str = "system") -> dict:
    """Proyek kecil tanpa cluster tetap punya struktur konsisten (cluster UTAMA)."""
    org = project.get("org_id", ORG_ID)
    found = await db.clusters.find_one({"org_id": org, "project_id": project["id"]}, {"_id": 0})
    if found:
        return found
    ts = now_iso()
    doc = {"id": new_id(), "org_id": org, "project_id": project["id"], "code": "UTAMA",
           "name": "Cluster Utama", "order": 0, "status": "selling", "price_multiplier": 1.0,
           "description": "Dibuat otomatis agar setiap unit punya induk cluster.",
           "created_by": actor, "created_at": ts, "updated_at": ts}
    await db.clusters.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


async def list_clusters(project_id: str, org: str = ORG_ID) -> list:
    rows = await db.clusters.find({"org_id": org, "project_id": project_id},
                                  {"_id": 0}).sort([("order", 1), ("code", 1)]).to_list(200)
    for c in rows:
        c["stats"] = await _cluster_stats(c["id"], org)
        c["blocks_count"] = await db.blocks.count_documents(
            {"org_id": org, "cluster_id": c["id"]})
        c["status_label"] = ref.label_of("cluster_status", c.get("status"))
    return rows


async def _cluster_stats(cluster_id: str, org: str = ORG_ID) -> dict:
    out = {"units": 0, "available": 0, "reserved": 0, "booked": 0, "sold": 0,
           "handed_over": 0, "blocked": 0, "value": 0}
    cur = db.units.aggregate([
        {"$match": {"org_id": org, "cluster_id": cluster_id}},
        {"$group": {"_id": "$status", "n": {"$sum": 1}, "v": {"$sum": "$price"}}},
    ])
    async for row in cur:
        out["units"] += row["n"]
        out["value"] += int(row.get("v") or 0)
        if row["_id"] in out:
            out[row["_id"]] = row["n"]
    sold_like = out["booked"] + out["sold"] + out["handed_over"]
    out["absorption_pct"] = round(sold_like / out["units"] * 100) if out["units"] else 0
    return out


async def create_cluster(project_id: str, payload, actor: str, org: str = ORG_ID) -> dict:
    code = payload.code or await nb.generate_unique(
        "master:cluster", org, "clusters", {"org_id": org, "project_id": project_id},
        context={"project_id": project_id})
    if await db.clusters.find_one({"org_id": org, "project_id": project_id,
                                   "code": code}, {"_id": 1}):
        raise ValueError(f"Cluster '{code}' sudah ada pada proyek ini.")
    ts = now_iso()
    doc = {"id": new_id(), "org_id": org, "project_id": project_id, **_clean(payload), "code": code,
           "created_by": actor, "created_at": ts, "updated_at": ts}
    await db.clusters.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


async def update_cluster(cluster_id: str, payload, actor: str, org: str = ORG_ID) -> dict:
    patch = _clean(payload)
    if not patch:
        raise ValueError("Tidak ada perubahan.")
    patch.update({"updated_at": now_iso(), "updated_by": actor})
    res = await db.clusters.update_one({"id": cluster_id, "org_id": org}, {"$set": patch})
    if not res.matched_count:
        raise LookupError("Cluster tidak ditemukan.")
    return await db.clusters.find_one({"id": cluster_id}, {"_id": 0})


async def delete_cluster(cluster_id: str, org: str = ORG_ID) -> dict:
    units = await db.units.count_documents({"org_id": org, "cluster_id": cluster_id})
    if units:
        raise ValueError(f"Cluster masih memiliki {units} unit — pindahkan/hapus unit dulu.")
    await db.blocks.delete_many({"org_id": org, "cluster_id": cluster_id})
    res = await db.clusters.delete_one({"id": cluster_id, "org_id": org})
    if not res.deleted_count:
        raise LookupError("Cluster tidak ditemukan.")
    return {"deleted": True}


# ------------------------------------------------------------------ blok
async def list_blocks(org: str = ORG_ID, project_id: str = None, cluster_id: str = None) -> list:
    query = {"org_id": org}
    if project_id:
        query["project_id"] = project_id
    if cluster_id:
        query["cluster_id"] = cluster_id
    rows = await db.blocks.find(query, {"_id": 0}).sort([("order", 1), ("code", 1)]).to_list(500)
    for b in rows:
        b["units_count"] = await db.units.count_documents({"org_id": org, "block_id": b["id"]})
        b["available_count"] = await db.units.count_documents(
            {"org_id": org, "block_id": b["id"], "status": "available"})
    return rows


async def create_block(cluster_id: str, payload, actor: str, org: str = ORG_ID) -> dict:
    cluster = await db.clusters.find_one({"id": cluster_id, "org_id": org}, {"_id": 0})
    if not cluster:
        raise LookupError("Cluster tidak ditemukan.")
    code = payload.code or await nb.generate_unique(
        "master:block", org, "blocks", {"org_id": org, "cluster_id": cluster_id},
        context={"project_id": cluster["project_id"], "cluster_code": cluster["code"]})
    if await db.blocks.find_one({"org_id": org, "cluster_id": cluster_id,
                                 "code": code}, {"_id": 1}):
        raise ValueError(f"Blok '{code}' sudah ada pada cluster ini.")
    ts = now_iso()
    doc = {"id": new_id(), "org_id": org, "project_id": cluster["project_id"],
           "cluster_id": cluster_id, "cluster_code": cluster["code"], **_clean(payload),
           "code": code, "created_by": actor, "created_at": ts, "updated_at": ts}
    doc.setdefault("name", f"Blok {code}")
    await db.blocks.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


async def update_block(block_id: str, payload, actor: str, org: str = ORG_ID) -> dict:
    patch = _clean(payload)
    if not patch:
        raise ValueError("Tidak ada perubahan.")
    patch.update({"updated_at": now_iso(), "updated_by": actor})
    res = await db.blocks.update_one({"id": block_id, "org_id": org}, {"$set": patch})
    if not res.matched_count:
        raise LookupError("Blok tidak ditemukan.")
    return await db.blocks.find_one({"id": block_id}, {"_id": 0})


async def delete_block(block_id: str, org: str = ORG_ID) -> dict:
    units = await db.units.count_documents({"org_id": org, "block_id": block_id})
    if units:
        raise ValueError(f"Blok masih memiliki {units} unit — pindahkan/hapus unit dulu.")
    res = await db.blocks.delete_one({"id": block_id, "org_id": org})
    if not res.deleted_count:
        raise LookupError("Blok tidak ditemukan.")
    return {"deleted": True}


# ------------------------------------------------------------------ unit
async def _unit_type(code: str, org: str = ORG_ID) -> dict:
    if not code:
        return None
    return await db.unit_types.find_one({"org_id": org, "code": code}, {"_id": 0})


async def _price_for(utype: dict, cluster: dict, given: int = None) -> int:
    if given:
        return int(given)
    base = int((utype or {}).get("base_price") or 0)
    mult = float((cluster or {}).get("price_multiplier") or 1.0)
    return int(round(base * mult / 1000.0) * 1000)


async def _new_unit_doc(block: dict, cluster: dict, project: dict, utype: dict, *, no,
                        price=None, corner=False, luas_tanah=None, luas_bangunan=None,
                        excess=0, actor="system", notes=None) -> dict:
    ts = now_iso()
    org = block["org_id"]
    code = await nb.generate("master:unit", org, context={
        "project_id": project["id"], "cluster_code": cluster["code"],
        "block_code": block["code"], "unit_type_code": (utype or {}).get("code"), "no": no})
    if await db.units.find_one({"org_id": org, "project_id": project["id"], "code": code},
                               {"_id": 1}):
        raise ValueError(f"Unit '{code}' sudah ada pada proyek ini.")
    price = await _price_for(utype, cluster, price)
    return {
        "id": new_id(), "org_id": org, "project_id": project["id"],
        "project_name": project.get("name"), "cluster_id": cluster["id"],
        "cluster_code": cluster["code"], "block_id": block["id"], "block": block["code"],
        "no": str(no), "code": code,
        "unit_type_id": (utype or {}).get("id"), "unit_type_code": (utype or {}).get("code"),
        "type": (utype or {}).get("name") or "Kavling",
        "luas_tanah": luas_tanah if luas_tanah is not None else (utype or {}).get("land_area_std"),
        "luas_bangunan": (luas_bangunan if luas_bangunan is not None
                          else (utype or {}).get("building_area")),
        "corner": bool(corner), "excess_land_m2": int(excess or 0),
        "excess_land_price_agreed": None,
        "price": price, "price_components": {
            "base": int((utype or {}).get("base_price") or 0),
            "cluster_multiplier": float(cluster.get("price_multiplier") or 1.0),
        },
        "status": "available", "construction_status": "not_started",
        "construction_progress": 0, "payment_status": None, "notes": notes,
        "status_history": [{"field": "status", "from": None, "to": "available", "at": ts,
                            "actor": actor, "reason": "Unit dibuat"}],
        "created_by": actor, "created_at": ts, "updated_at": ts,
    }


async def create_unit(block_id: str, payload, actor: str, org: str = ORG_ID) -> dict:
    block = await db.blocks.find_one({"id": block_id, "org_id": org}, {"_id": 0})
    if not block:
        raise LookupError("Blok tidak ditemukan.")
    cluster = await db.clusters.find_one({"id": block["cluster_id"]}, {"_id": 0})
    project = await db.projects.find_one({"id": block["project_id"]}, {"_id": 0})
    utype = await _unit_type(payload.unit_type_code, org)
    doc = await _new_unit_doc(block, cluster, project, utype, no=payload.no,
                              price=payload.price, corner=payload.is_hook,
                              luas_tanah=payload.land_area, luas_bangunan=payload.building_area,
                              excess=payload.excess_land_m2, actor=actor, notes=payload.notes)
    await db.units.insert_one(dict(doc))
    doc.pop("_id", None)
    await recompute_stats(block["project_id"], org)
    return doc


async def generate_units(block_id: str, payload, actor: str, org: str = ORG_ID) -> dict:
    block = await db.blocks.find_one({"id": block_id, "org_id": org}, {"_id": 0})
    if not block:
        raise LookupError("Blok tidak ditemukan.")
    cluster = await db.clusters.find_one({"id": block["cluster_id"]}, {"_id": 0})
    project = await db.projects.find_one({"id": block["project_id"]}, {"_id": 0})
    utype = await _unit_type(payload.unit_type_code, org)
    if not utype:
        raise ValueError(f"Tipe unit '{payload.unit_type_code}' tidak ada di master tipe.")
    created, skipped = [], []
    for i in range(payload.count):
        no = payload.start_no + i
        try:
            doc = await _new_unit_doc(block, cluster, project, utype, no=no,
                                      price=payload.price, corner=no in (payload.hook_numbers or []),
                                      actor=actor)
        except ValueError as e:
            skipped.append({"no": no, "reason": str(e)})
            continue
        await db.units.insert_one(dict(doc))
        created.append(doc["code"])
    await recompute_stats(block["project_id"], org)
    return {"created": created, "skipped": skipped, "block": block["code"]}


async def patch_unit(unit_id: str, payload, actor: str, org: str = ORG_ID) -> dict:
    unit = await db.units.find_one({"id": unit_id, "org_id": org}, {"_id": 0})
    if not unit:
        raise LookupError("Unit tidak ditemukan.")
    data = payload.model_dump(exclude_none=True)
    reason = (data.pop("reason", None) or "").strip()
    patch, hist = {}, []
    if "unit_type_code" in data:
        utype = await _unit_type(data["unit_type_code"], org)
        if not utype:
            raise ValueError("Tipe unit tidak ada di master tipe.")
        patch.update({"unit_type_code": utype["code"], "unit_type_id": utype["id"],
                      "type": utype["name"]})
    for src, dst in (("land_area", "luas_tanah"), ("building_area", "luas_bangunan"),
                     ("is_hook", "corner"), ("excess_land_m2", "excess_land_m2"),
                     ("excess_land_price_agreed", "excess_land_price_agreed"),
                     ("notes", "notes")):
        if src in data:
            patch[dst] = data[src]
    if "price" in data and int(data["price"]) != int(unit.get("price") or 0):
        if unit.get("status") in ACTIVE_SALES and not reason:
            raise ValueError("Unit sudah terikat transaksi — perubahan harga wajib beralasan.")
        patch["price"] = int(data["price"])
        hist.append({"field": "price", "from": unit.get("price"), "to": patch["price"],
                     "at": now_iso(), "actor": actor, "reason": reason or None})
    if not patch:
        raise ValueError("Tidak ada perubahan.")
    patch.update({"updated_at": now_iso(), "updated_by": actor})
    upd = {"$set": patch}
    if hist:
        upd["$push"] = {"status_history": {"$each": hist}}
    await db.units.update_one({"id": unit_id}, upd)
    await recompute_stats(unit["project_id"], org)
    return await db.units.find_one({"id": unit_id}, {"_id": 0})


async def toggle_unit_block(unit_id: str, payload, actor: str, org: str = ORG_ID) -> dict:
    unit = await db.units.find_one({"id": unit_id, "org_id": org}, {"_id": 0})
    if not unit:
        raise LookupError("Unit tidak ditemukan.")
    if payload.blocked and unit.get("status") in ACTIVE_SALES:
        raise ValueError(f"Unit berstatus '{ref.label_of('unit_status', unit['status'])}' "
                         "tidak bisa diblokir — lepas/batalkan transaksinya dulu.")
    new_status = "blocked" if payload.blocked else "available"
    ts = now_iso()
    await db.units.update_one({"id": unit_id}, {
        "$set": {"status": new_status, "updated_at": ts, "updated_by": actor,
                 "blocked": ({"reason": payload.reason, "by": actor, "at": ts}
                             if payload.blocked else None)},
        "$push": {"status_history": {"field": "status", "from": unit.get("status"),
                                     "to": new_status, "at": ts, "actor": actor,
                                     "reason": payload.reason}}})
    await recompute_stats(unit["project_id"], org)
    return await db.units.find_one({"id": unit_id}, {"_id": 0})


async def import_units(payload, actor: str, org: str = ORG_ID) -> dict:
    """Impor unit massal. `dry_run=True` hanya memvalidasi (pratinjau) — tidak menulis."""
    project = await db.projects.find_one({"id": payload.project_id, "org_id": org}, {"_id": 0})
    if not project:
        raise LookupError("Proyek tidak ditemukan.")
    ok_rows, bad_rows = [], []
    for idx, row in enumerate(payload.rows, start=1):
        cluster = await db.clusters.find_one(
            {"org_id": org, "project_id": project["id"], "code": row.cluster_code.upper()},
            {"_id": 0})
        if not cluster:
            bad_rows.append({"row": idx, "reason": f"Cluster '{row.cluster_code}' tidak ada."})
            continue
        block = await db.blocks.find_one(
            {"org_id": org, "cluster_id": cluster["id"], "code": row.block_code.upper()},
            {"_id": 0})
        if not block:
            bad_rows.append({"row": idx, "reason": f"Blok '{row.block_code}' tidak ada "
                                                   f"pada cluster {row.cluster_code}."})
            continue
        utype = await _unit_type(row.unit_type_code, org) if row.unit_type_code else None
        if row.unit_type_code and not utype:
            bad_rows.append({"row": idx, "reason": f"Tipe '{row.unit_type_code}' tidak ada."})
            continue
        try:
            doc = await _new_unit_doc(block, cluster, project, utype, no=row.no,
                                      price=row.price, corner=row.is_hook,
                                      luas_tanah=row.land_area, luas_bangunan=row.building_area,
                                      actor=actor)
        except ValueError as e:
            bad_rows.append({"row": idx, "reason": str(e)})
            continue
        ok_rows.append(doc)
    inserted = 0
    if not payload.dry_run and ok_rows:
        await db.units.insert_many([dict(d) for d in ok_rows])
        inserted = len(ok_rows)
        await recompute_stats(project["id"], org)
    return {"dry_run": payload.dry_run, "valid": len(ok_rows), "invalid": len(bad_rows),
            "inserted": inserted, "errors": bad_rows[:50],
            "preview": [{"code": d["code"], "block": d["block"], "cluster": d["cluster_code"],
                         "type": d["type"], "price": d["price"]} for d in ok_rows[:50]]}


SORTABLE = {"code": "code", "price": "price", "status": "status",
            "construction_status": "construction_status", "progress": "construction_progress",
            "cluster": "cluster_code", "block": "block", "type": "type",
            "updated_at": "updated_at"}


async def units_listing(org: str = ORG_ID, *, project_id=None, cluster_id=None, block_id=None,
                        status=None, construction_status=None, unit_type_code=None, q=None,
                        sort="code", direction="asc", skip=0, limit=50) -> dict:
    skip, limit = parse_pagination(skip, limit)
    query = {"org_id": org}
    for field, val in (("project_id", project_id), ("cluster_id", cluster_id),
                       ("block_id", block_id), ("status", status),
                       ("construction_status", construction_status),
                       ("unit_type_code", unit_type_code)):
        if val:
            query[field] = {"$in": val.split(",")} if isinstance(val, str) and "," in val else val
    if q:
        query["$or"] = [{"code": {"$regex": q, "$options": "i"}},
                        {"type": {"$regex": q, "$options": "i"}},
                        {"lead_name": {"$regex": q, "$options": "i"}}]
    total = await db.units.count_documents(query)
    key = SORTABLE.get(sort, "code")
    rows = await db.units.find(query, {"_id": 0}).sort(
        key, 1 if direction != "desc" else -1).skip(skip).limit(limit).to_list(limit)
    for u in rows:
        u["status_label"] = ref.label_of("unit_status", u.get("status"))
        u["construction_label"] = ref.label_of("construction_status",
                                               u.get("construction_status"))
    agg = {"available": 0, "reserved": 0, "booked": 0, "sold": 0, "handed_over": 0,
           "blocked": 0}
    cur = db.units.aggregate([{"$match": query},
                              {"$group": {"_id": "$status", "n": {"$sum": 1}}}])
    async for row in cur:
        if row["_id"] in agg:
            agg[row["_id"]] = row["n"]
    return {"data": rows, "total": total, "summary": agg,
            "sortable": sorted(SORTABLE.keys())}


async def project_tree(project_id: str, org: str = ORG_ID) -> dict:
    # Kartu unit_stats adalah denormalisasi; status unit bisa berubah lewat jalur lain
    # (reservasi/pembatalan/impor) tanpa memanggil recompute → kartu ≠ baris. Hitung ulang
    # saat dibaca (satu agregasi ringan) supaya kartu selalu = jumlah rinciannya.
    await recompute_stats(project_id, org)
    project = await db.projects.find_one({"id": project_id, "org_id": org}, {"_id": 0})
    if not project:
        raise LookupError("Proyek tidak ditemukan.")
    clusters = await list_clusters(project_id, org)
    blocks = await list_blocks(org, project_id=project_id)
    by_cluster = {}
    for b in blocks:
        by_cluster.setdefault(b["cluster_id"], []).append(b)
    for c in clusters:
        c["blocks"] = by_cluster.get(c["id"], [])
    totals = {"clusters": len(clusters), "blocks": len(blocks),
              "units": await db.units.count_documents({"org_id": org, "project_id": project_id}),
              "unmapped_units": await db.units.count_documents(
                  {"org_id": org, "project_id": project_id,
                   "$or": [{"cluster_id": None}, {"cluster_id": {"$exists": False}}]})}
    return {"project": project, "clusters": clusters, "totals": totals}


async def unit_360(unit_id: str, org: str = ORG_ID) -> dict:
    """Agregat Unit 360: penjualan + pembangunan + dokumen + riwayat dalam satu panggilan."""
    unit = await db.units.find_one({"id": unit_id, "org_id": org}, {"_id": 0})
    if not unit:
        raise LookupError("Unit tidak ditemukan.")
    project = await db.projects.find_one({"id": unit.get("project_id")}, {"_id": 0})
    cluster = await db.clusters.find_one({"id": unit.get("cluster_id")}, {"_id": 0})
    block = await db.blocks.find_one({"id": unit.get("block_id")}, {"_id": 0})
    utype = await db.unit_types.find_one({"id": unit.get("unit_type_id")}, {"_id": 0})
    customer = (await db.customers.find_one({"id": unit.get("customer_id")}, {"_id": 0})
                if unit.get("customer_id") else None)
    deals = await db.deals.find({"org_id": org, "unit_id": unit_id}, {"_id": 0}).sort(
        "created_at", -1).to_list(20)
    schedule = await db.build_schedules.find_one({"org_id": org, "unit_id": unit_id}, {"_id": 0})
    permits = await db.permits.find({"org_id": org, "unit_id": unit_id}, {"_id": 0}).to_list(50)
    docs = await db.doc_submissions.find({"org_id": org, "entity_type": "unit",
                                          "entity_id": unit_id}, {"_id": 0}).to_list(100)
    invoices = await db.ar_invoices.find({"org_id": org, "unit_id": unit_id}, {"_id": 0}).sort(
        "created_at", -1).to_list(50)
    addons = await db.addon_items.find({"org_id": org, "active": True}, {"_id": 0}).to_list(200)
    import catalog as cat
    return {
        "unit": {**unit,
                 "status_label": ref.label_of("unit_status", unit.get("status")),
                 "construction_label": ref.label_of("construction_status",
                                                    unit.get("construction_status"))},
        "project": project, "cluster": cluster, "block": block, "unit_type": utype,
        "customer": customer, "deals": deals, "schedule": schedule, "permits": permits,
        "documents": docs, "invoices": invoices,
        "suggested_addons": await cat.suggested_addons_for_unit(unit, org),
        "addon_catalog": [{"code": a["code"], "name": a["name"], "category": a.get("category"),
                           "pricing_mode": a.get("pricing_mode"),
                           "unit_price": a.get("unit_price")} for a in addons],
        "history": list(reversed(unit.get("status_history") or []))[:50],
        "settings": await cfg.get_many(
            ["reservation.hold_days", "build.require_dp_before_start"],
            org_id=org, project_id=unit.get("project_id")),
    }


async def recompute_stats(project_id: str = None, org: str = ORG_ID) -> dict:
    """Denormalisasi ringkas untuk kartu/tabel (idempoten, aman dipanggil sering)."""
    query = {"org_id": org}
    if project_id:
        query["id"] = project_id  # dulu `project_id` → tidak cocok dokumen proyek mana pun (kartu tak pernah segar)
    projects = await db.projects.find(query, {"_id": 0, "id": 1}).to_list(200)
    touched = 0
    for p in projects:
        stats = {"units": 0, "available": 0, "reserved": 0, "booked": 0, "sold": 0,
                 "handed_over": 0, "blocked": 0, "value": 0}
        cur = db.units.aggregate([
            {"$match": {"org_id": org, "project_id": p["id"]}},
            {"$group": {"_id": "$status", "n": {"$sum": 1}, "v": {"$sum": "$price"}}}])
        async for row in cur:
            stats["units"] += row["n"]
            stats["value"] += int(row.get("v") or 0)
            if row["_id"] in stats:
                stats[row["_id"]] = row["n"]
        sold_like = stats["booked"] + stats["sold"] + stats["handed_over"]
        stats["absorption_pct"] = round(sold_like / stats["units"] * 100) if stats["units"] else 0
        await db.projects.update_one({"id": p["id"]}, {"$set": {
            "unit_stats": stats,
            "cluster_count": await db.clusters.count_documents(
                {"org_id": org, "project_id": p["id"]}),
            "block_count": await db.blocks.count_documents(
                {"org_id": org, "project_id": p["id"]})}})
        touched += 1
    return {"projects": touched}

async def siteplan_consistency(project_id: str, org: str = ORG_ID) -> dict:
    """Laporan konsistensi peta ↔ unit (dua arah).

    Dipisah dari migrasi supaya bisa dilihat kapan saja: unit BARU yang dibuat setelah peta
    digambar memang belum punya shape — itu pekerjaan pemetaan, bukan kerusakan data. Yang
    TIDAK boleh terjadi adalah shape yang menunjuk unit tidak ada (peta berbohong).
    """
    plans = await db.site_plans.find({"org_id": org, "project_id": project_id},
                                     {"_id": 0}).to_list(20)
    unit_ids = {u["id"] for u in await db.units.find(
        {"org_id": org, "project_id": project_id}, {"_id": 0, "id": 1}).to_list(5000)}
    dangling, mapped = [], set()
    for plan in plans:
        for sh in (plan.get("shapes") or []):
            if sh.get("kind") not in ("unit", "lot", "kavling"):
                continue
            uid = sh.get("unit_id")
            if uid and uid in unit_ids:
                mapped.add(uid)
            else:
                dangling.append({"shape_id": sh.get("shape_id"), "label": sh.get("label")})
    unmapped = await db.units.find(
        {"org_id": org, "project_id": project_id, "id": {"$nin": list(mapped)}},
        {"_id": 0, "id": 1, "code": 1, "block": 1}).to_list(200)
    return {"has_plan": bool(plans), "mapped_units": len(mapped),
            "unmapped_units": [{"id": u["id"], "code": u.get("code"), "block": u.get("block")}
                               for u in unmapped],
            "unmapped_count": len(unmapped), "dangling_shapes": dangling}
