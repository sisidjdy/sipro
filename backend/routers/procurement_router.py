"""Procurement + Anti-Fraud 3-way match (Phase 12 — EPIC 3.6).

Flow: Purchase Order (PO) → Goods Receipt Note (GRN) → Bill (AP invoice).
The 3-way match compares ORDERED (PO) vs RECEIVED (GRN) vs BILLED (invoice); a bill
that exceeds what was received (beyond a small tolerance) is FLAGGED and raises an
anti-fraud review task for finance. Controls:
  * Segregation of duties (RBAC): PM/site raise POs/GRNs/bills; finance/owner APPROVE.
  * Tiered approval: high-value POs (> threshold) require owner/super_admin.
  * 3-way match: prevents over-billing vs goods actually received.
  * Audit trail: audit_log + activities + events on every state change.
Material-type GRNs also post an 'in' material_txn so stock stays in sync.
"""
from fastapi import APIRouter, Depends, HTTPException, Response

import docgen_p61 as p61
import sequences as seq
import procurement_extra as pe
import vendor_engine as ve
from db import db, ORG_ID
from core_utils import new_id, now_iso, serialize_doc, parse_pagination
from rbac import has_role, require_permission, assert_project_access, project_query, audit_log
from engine import add_activity, auto_create_task, create_notification
import finance_engine as fe
from models import POCreate, POAction, GRNCreate, ProcurementBillCreate

router = APIRouter(prefix="/procurement", tags=["procurement"])

PROJECT_SCOPED = ("project_manager", "site_engineer")
SENIOR_ROLES = ("owner", "super_admin")
HIGH_VALUE_THRESHOLD = 500_000_000  # PO di atas ini butuh persetujuan Owner (anti-fraud tiered)
MATCH_TOL = 0.005  # 0.5% toleransi pembulatan (SSOT: reference_p48.THREEWAY_TOLERANCE)
PO_OPEN = ("approved", "partially_received")


async def _accessible_project_ids(user: dict):
    projs = await db.projects.find(project_query(user, {}), {"_id": 0, "id": 1, "name": 1}).to_list(500)
    return {p["id"]: p["name"] for p in projs}


SCOPE_BY_PREFIX = {"PO": "po", "GRN": "grn"}


async def _next_number(prefix: str, coll, org_id: str = None, context: dict = None) -> str:
    """Nomor atomik per org+tahun (lihat sequences.py)."""
    return await seq.next_number(SCOPE_BY_PREFIX.get(prefix, prefix.lower()),
                                 org_id or ORG_ID, prefix=prefix, context=context)


def _line_amount(qty, unit_price) -> int:
    return int(round(float(qty or 0) * int(unit_price or 0)))


# ----------------------------- Purchase Orders -----------------------------
@router.get("/pos")
async def list_pos(project_id: str = None, status: str = None, po_type: str = None,
                   skip: int = 0, limit: int = 100,
                   user: dict = Depends(require_permission("procurement", "view"))):
    org = user.get("org_id", ORG_ID)
    skip, limit = parse_pagination(skip, limit)
    pmap = await _accessible_project_ids(user)
    fq = {"org_id": org}
    if has_role(user, *PROJECT_SCOPED):
        fq["project_id"] = {"$in": list(pmap.keys())}
    if project_id:
        fq["project_id"] = project_id
    if status:
        fq["status"] = status
    if po_type:
        fq["po_type"] = po_type
    total = await db.purchase_orders.count_documents(fq)
    rows = await db.purchase_orders.find(fq, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    for r in rows:
        r["project_name"] = pmap.get(r.get("project_id"), r.get("project_name"))
    all_rows = await db.purchase_orders.find({k: v for k, v in fq.items() if k != "status"}, {"_id": 0, "status": 1, "total": 1}).to_list(2000)
    summary = {
        "total": len(all_rows),
        "draft": sum(1 for r in all_rows if r.get("status") == "draft"),
        "approved": sum(1 for r in all_rows if r.get("status") in ("approved", "partially_received")),
        "received": sum(1 for r in all_rows if r.get("status") in ("received", "closed")),
        "value": sum(int(r.get("total", 0)) for r in all_rows if r.get("status") != "cancelled"),
    }
    return {"data": serialize_doc(rows), "total": total, "summary": summary}


@router.post("/pos")
async def create_po(payload: POCreate,
                    user: dict = Depends(require_permission("procurement", "create"))):
    proj = await assert_project_access(payload.project_id, user)
    org = user.get("org_id", ORG_ID)
    if not payload.items:
        raise HTTPException(status_code=400, detail="PO harus memiliki minimal 1 item.")
    sub_name = None
    if payload.subcontractor_id:
        sub = await db.subcontractors.find_one({"id": payload.subcontractor_id, "org_id": org}, {"_id": 0})
        if not sub:
            raise HTTPException(status_code=404, detail="Subkontraktor tidak ditemukan")
        sub_name = sub.get("name")
    # Fase 48A: bila PO menunjuk MASTER vendor, namanya diambil dari master (snapshot) supaya
    # riwayat satu vendor bisa dijumlahkan \u2014 bukan tiga ejaan berbeda.
    vendor_name = payload.vendor
    if payload.vendor_id:
        vend = await ve.get_vendor(org, payload.vendor_id)
        if not vend:
            raise HTTPException(status_code=404, detail="Vendor tidak ditemukan.")
        if not vend.get("is_active", True):
            raise HTTPException(status_code=400, detail="Vendor ini sudah tidak aktif.")
        vendor_name = vend.get("name")
    items = []
    subtotal = 0
    checks = []
    for it in payload.items:
        amt = _line_amount(it.qty, it.unit_price)
        subtotal += amt
        items.append({
            "description": it.description, "material_id": it.material_id, "boq_item_id": it.boq_item_id,
            "uom": it.uom, "qty": float(it.qty or 0), "unit_price": int(it.unit_price or 0),
            "amount": amt, "received_qty": 0.0,
        })
        # Fase 48A: harga PO diuji terhadap acuan (daftar harga vendor). Tidak pernah
        # MENAHAN \u2014 hanya memberi alasan yang bisa dibaca penyetuju.
        if it.material_id:
            checks.append({"material_id": it.material_id, "description": it.description,
                           **await ve.price_check(org, it.material_id, int(it.unit_price or 0),
                                                  payload.vendor_id)})
    total = int(subtotal)
    ts = now_iso()
    doc = {
        "id": new_id(), "org_id": org, "po_number": await _next_number(
            "PO", db.purchase_orders, org, {"project_id": payload.project_id, "vendor_id": payload.vendor_id}),
        "project_id": payload.project_id, "project_name": proj.get("name"),
        "po_type": payload.po_type, "vendor": vendor_name, "vendor_id": payload.vendor_id,
        "subcontractor_id": payload.subcontractor_id, "subcontractor_name": sub_name,
        "spk_id": payload.spk_id, "items": items, "subtotal": total, "total": total,
        "status": "draft", "received_value": 0, "billed_value": 0,
        "high_value": total > HIGH_VALUE_THRESHOLD, "due_date": payload.due_date, "note": payload.note,
        "po_source": "manual", "requisition_id": None, "price_checks": checks,
        "approved_by": None, "approved_at": None,
        "created_by": user.get("email"), "created_at": ts, "updated_at": ts,
    }
    await db.purchase_orders.insert_one(dict(doc))
    await add_activity(entity_type="project", entity_id=payload.project_id, type="system",
                       body=f"PO {doc['po_number']} dibuat untuk {vendor_name} (Rp {total:,}).",
                       actor=user.get("email"), org_id=org)
    doc.pop("_id", None)
    return {"data": serialize_doc(doc), "price_checks": serialize_doc(checks)}


async def _get_po(pid: str, user: dict) -> dict:
    doc = await db.purchase_orders.find_one({"id": pid, "org_id": user.get("org_id", ORG_ID)}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="PO tidak ditemukan")
    await assert_project_access(doc["project_id"], user)
    return doc


@router.get("/pos/{pid}")
async def get_po(pid: str, user: dict = Depends(require_permission("procurement", "view"))):
    doc = await _get_po(pid, user)
    org = doc["org_id"]
    grns = await db.grns.find({"org_id": org, "po_id": pid}, {"_id": 0}).sort("created_at", -1).to_list(200)
    bills = await db.ap_invoices.find({"org_id": org, "po_id": pid}, {"_id": 0}).sort("created_at", -1).to_list(200)
    return {"data": serialize_doc(doc), "grns": serialize_doc(grns), "bills": serialize_doc(bills)}


@router.get("/pos/{pid}/pdf")
async def po_pdf(pid: str, user: dict = Depends(require_permission("procurement", "view"))):
    """Cetak PO berkop (Fase 61) — dasar vendor mengirim barang & menagih."""
    doc = await _get_po(pid, user)
    pdf = await p61.po_pdf(doc["org_id"], doc,
                           {"name": user.get("name"), "role": user.get("role")})
    nama = str(doc.get("po_number") or "po").replace("/", "-")
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{nama}.pdf"'})


@router.post("/pos/{pid}/approve")
async def approve_po(pid: str, payload: POAction,
                     user: dict = Depends(require_permission("procurement", "approve"))):
    doc = await _get_po(pid, user)
    if doc.get("status") != "draft":
        raise HTTPException(status_code=400, detail="Hanya PO berstatus draft yang bisa disetujui.")
    if doc.get("high_value") and not has_role(user, *SENIOR_ROLES):
        raise HTTPException(status_code=403,
                            detail=f"PO nilai tinggi (> Rp {HIGH_VALUE_THRESHOLD:,}) memerlukan persetujuan Owner.")
    ts = now_iso()
    await db.purchase_orders.update_one({"id": pid, "org_id": doc["org_id"]}, {"$set": {
        "status": "approved", "approved_by": user.get("email"), "approved_at": ts, "updated_at": ts}})
    await audit_log(user, "approve", "purchase_order", pid, {"total": doc.get("total"), "vendor": doc.get("vendor")})
    await add_activity(entity_type="project", entity_id=doc["project_id"], type="system",
                       body=f"PO {doc.get('po_number')} disetujui oleh {user.get('email')}.",
                       actor=user.get("email"), org_id=doc["org_id"])
    await create_notification(user_email=doc.get("created_by"), title="PO disetujui",
                              body=f"{doc.get('po_number')} — {doc.get('vendor')} siap diterima/ditagih.",
                              type="procurement", related_entity_type="project",
                              related_entity_id=doc["project_id"], org_id=doc["org_id"])
    return {"data": serialize_doc(await db.purchase_orders.find_one({"id": pid}, {"_id": 0}))}


@router.post("/pos/{pid}/cancel")
async def cancel_po(pid: str, payload: POAction,
                    user: dict = Depends(require_permission("procurement", "update"))):
    doc = await _get_po(pid, user)
    if doc.get("status") in ("received", "closed", "cancelled"):
        raise HTTPException(status_code=400, detail="PO tidak dapat dibatalkan pada status ini.")
    ts = now_iso()
    await db.purchase_orders.update_one({"id": pid, "org_id": doc["org_id"]}, {"$set": {
        "status": "cancelled", "updated_at": ts}})
    await audit_log(user, "cancel", "purchase_order", pid, {"note": payload.note})
    return {"data": serialize_doc(await db.purchase_orders.find_one({"id": pid}, {"_id": 0}))}


# ----------------------------- Goods Receipt Notes -----------------------------
@router.get("/grns")
async def list_grns(po_id: str = None, project_id: str = None,
                    user: dict = Depends(require_permission("procurement", "view"))):
    org = user.get("org_id", ORG_ID)
    pmap = await _accessible_project_ids(user)
    fq = {"org_id": org}
    if has_role(user, *PROJECT_SCOPED):
        fq["project_id"] = {"$in": list(pmap.keys())}
    if po_id:
        fq["po_id"] = po_id
    if project_id:
        fq["project_id"] = project_id
    rows = await db.grns.find(fq, {"_id": 0}).sort("created_at", -1).to_list(500)
    return {"data": serialize_doc(rows), "total": len(rows)}


@router.post("/grns")
async def create_grn(payload: GRNCreate,
                     user: dict = Depends(require_permission("procurement", "create"))):
    org = user.get("org_id", ORG_ID)
    po = await _get_po(payload.po_id, user)
    if po.get("status") not in PO_OPEN:
        raise HTTPException(status_code=400, detail="PO harus berstatus 'disetujui' untuk penerimaan barang.")
    if not payload.items:
        raise HTTPException(status_code=400, detail="GRN harus memiliki minimal 1 item diterima.")
    items = po.get("items", [])
    grn_items = []
    received_value = 0
    ts = now_iso()
    grn_number = await _next_number("GRN", db.grns, org, {"project_id": po.get("project_id"),
                                                          "vendor_id": po.get("vendor_id")})
    for gi in payload.items:
        idx = gi.po_item_index
        if idx < 0 or idx >= len(items):
            raise HTTPException(status_code=400, detail="Indeks item PO tidak valid.")
        it = items[idx]
        qty_recv = float(gi.qty_received or 0)
        if qty_recv <= 0:
            continue
        remaining = float(it.get("qty", 0)) - float(it.get("received_qty", 0))
        if qty_recv > remaining + 1e-9:
            raise HTTPException(status_code=400,
                                detail=f"Qty diterima ({qty_recv}) melebihi sisa PO ({remaining}) untuk '{it.get('description')}'.")
        amt = _line_amount(qty_recv, it.get("unit_price"))
        received_value += amt
        it["received_qty"] = round(float(it.get("received_qty", 0)) + qty_recv, 4)
        grn_items.append({
            "po_item_index": idx, "description": it.get("description"),
            "material_id": it.get("material_id"), "uom": it.get("uom"),
            "qty_received": qty_recv, "unit_price": int(it.get("unit_price", 0)), "amount": amt,
            # Fase 48B: sisa yang masih bisa diretur dihitung dari sini.
            "returned_qty": 0.0,
        })
        # Keep material stock in sync for material-type lines.
        if it.get("material_id"):
            mat = await db.materials.find_one({"id": it["material_id"], "org_id": org}, {"_id": 0, "id": 1})
            if mat:
                await db.material_txns.insert_one({
                    "id": new_id(), "org_id": org, "project_id": po["project_id"],
                    "material_id": it["material_id"], "type": "in", "qty": qty_recv,
                    # Fase 48E: harga ikut dicatat supaya NILAI persediaan bisa dihitung
                    # (harga rata-rata bergerak). Tanpa ini, stok hanya kuantitas dan
                    # laporan nilai persediaan terpaksa mengarang angka.
                    "unit_price": int(it.get("unit_price", 0) or 0), "amount": amt,
                    "note": f"Penerimaan PO {po.get('po_number')}", "ref": grn_number,
                    "actor": user.get("email"), "created_at": ts})
    if not grn_items:
        raise HTTPException(status_code=400, detail="Tidak ada item dengan qty diterima > 0.")
    grn = {
        "id": new_id(), "org_id": org, "grn_number": grn_number, "po_id": po["id"],
        "po_number": po.get("po_number"), "project_id": po["project_id"], "vendor": po.get("vendor"),
        "items": grn_items, "received_value": int(received_value), "note": payload.note,
        "received_by": user.get("email"), "created_at": ts,
    }
    await db.grns.insert_one(dict(grn))
    # Recompute PO received rollup + status.
    total_received_value = int(po.get("received_value", 0)) + int(received_value)
    fully = all(float(i.get("received_qty", 0)) >= float(i.get("qty", 0)) - 1e-9 for i in items)
    new_status = "received" if fully else "partially_received"
    await db.purchase_orders.update_one({"id": po["id"], "org_id": org}, {"$set": {
        "items": items, "received_value": total_received_value, "status": new_status, "updated_at": ts}})
    await add_activity(entity_type="project", entity_id=po["project_id"], type="system",
                       body=f"GRN {grn_number} diterima untuk PO {po.get('po_number')} (Rp {int(received_value):,}).",
                       actor=user.get("email"), org_id=org)
    grn.pop("_id", None)
    return {"data": serialize_doc(grn)}


# ----------------------------- Bills + 3-way match -----------------------------
# Fase 48B: rumus 3-way match PINDAH ke `procurement_extra.evaluate_bill()` supaya hanya ada
# SATU kebenaran yang dipakai router, gate, dan uji-mutasi \u2014 dan supaya hasilnya bukan cuma
# label (`flagged`) melainkan keadaan yang MENAHAN (`held`).


@router.get("/threeway")
async def threeway(status: str = None,
                   user: dict = Depends(require_permission("procurement", "view"))):
    org = user.get("org_id", ORG_ID)
    pmap = await _accessible_project_ids(user)
    fq = {"org_id": org, "po_id": {"$ne": None}}
    if has_role(user, *PROJECT_SCOPED):
        fq["project_id"] = {"$in": list(pmap.keys())}
    if status:
        fq["match_status"] = status
    rows = await db.ap_invoices.find(fq, {"_id": 0}).sort("created_at", -1).to_list(500)
    summary = {
        "total": len(rows),
        "matched": sum(1 for r in rows if r.get("match_status") == "matched"),
        "flagged": sum(1 for r in rows if r.get("match_status") == "flagged"),
    }
    return {"data": serialize_doc(rows), "total": len(rows), "summary": summary}


@router.post("/bills")
async def create_bill(payload: ProcurementBillCreate,
                      user: dict = Depends(require_permission("procurement", "create"))):
    org = user.get("org_id", ORG_ID)
    po = await _get_po(payload.po_id, user)
    if po.get("status") not in ("approved", "partially_received", "received", "closed"):
        raise HTTPException(status_code=400, detail="PO harus disetujui sebelum dapat ditagih.")
    if payload.claimed <= 0:
        raise HTTPException(status_code=400, detail="Nilai klaim harus lebih dari 0.")
    grn_received_value = 0
    if payload.grn_id:
        grn = await db.grns.find_one({"id": payload.grn_id, "org_id": org, "po_id": po["id"]}, {"_id": 0})
        if not grn:
            raise HTTPException(status_code=404, detail="GRN tidak ditemukan untuk PO ini.")
        grn_received_value = int(grn.get("received_value", 0))
    match = pe.evaluate_bill(po, int(payload.claimed), grn_received_value)
    override = False
    if match["state"] == "held":
        # Fase 48B: MENAHAN, bukan sekadar menandai. Tagihan yang melebihi barang diterima
        # tidak boleh lahir; hanya manajer keuangan yang boleh menerobos dengan alasan
        # tertulis (dan terobosan itu tetap melahirkan tugas tinjauan + notifikasi).
        if not payload.override_hold:
            raise HTTPException(status_code=400, detail=(
                "Tagihan DITAHAN 3-way match. " + match["detail"] +
                " Terima barangnya dulu (GRN), kurangi nilai tagihan, atau minta manajer "
                "keuangan menerobos dengan alasan tertulis."))
        if not has_role(user, "finance_manager", *SENIOR_ROLES):
            raise HTTPException(status_code=403, detail=(
                "Hanya Manajer Keuangan (atau Owner) yang boleh menerobos tahanan 3-way "
                "match \u2014 pemisahan tugas."))
        if len((payload.override_reason or "").strip()) < 10:
            raise HTTPException(status_code=400, detail=(
                "Alasan terobosan minimal 10 huruf \u2014 tulis dasar tagihan ini tetap diproses "
                "walau melebihi barang diterima."))
        override = True
        match = {**match, "state": "overridden"}
    # Create the AP invoice via finance engine (retention + aging aware), then attach match info.
    bill = await fe.create_ap_bill(po.get("vendor"), po["project_id"], int(payload.claimed),
                                   payload.retention_pct, payload.due_date,
                                   payload.note or f"Tagihan PO {po.get('po_number')}",
                                   user.get("email"), org)
    ts = now_iso()
    await db.ap_invoices.update_one({"id": bill["id"], "org_id": org}, {"$set": {
        "po_id": po["id"], "po_number": po.get("po_number"), "grn_id": payload.grn_id,
        "subcontractor_id": po.get("subcontractor_id"), "spk_id": po.get("spk_id"),
        "vendor_id": po.get("vendor_id"),
        "match_status": match["status"], "match_state": match["state"], "match_detail": match,
        "override_by": user.get("email") if override else None,
        "override_reason": payload.override_reason if override else None,
        "requires_senior_approval": override, "updated_at": ts}})
    await db.purchase_orders.update_one({"id": po["id"], "org_id": org}, {"$set": {
        "billed_value": match["billed_after"], "updated_at": ts}})
    await audit_log(user, "create", "procurement_bill", bill["id"],
                    {"po": po.get("po_number"), "claimed": int(payload.claimed),
                     "match": match["state"]})
    if override:
        fin = await db.users.find_one({"org_id": org, "role": "finance", "is_active": True}, {"_id": 0, "email": 1})
        assignee = fin["email"] if fin else None
        await auto_create_task(
            source_event=f"3way.override:{bill['id']}",
            title=f"Tinjau terobosan 3-way \u2014 PO {po.get('po_number')}",
            jobdesk_code="TK-07",
            type="review", related_entity_type="ap_bill", related_entity_id=bill["id"],
            assigned_to=assignee, priority="urgent", org_id=org,
            description=("; ".join(match["reasons"]) +
                         f" | Diterobos {user.get('email')}: {payload.override_reason}"))
        await fe.notify_finance(org, "3-way match diterobos",
                                f"PO {po.get('po_number')} ({po.get('vendor')}): " +
                                "; ".join(match["reasons"]) +
                                f" \u2014 alasan: {payload.override_reason}",
                                "finance", "ap_bill", bill["id"])
    updated = await db.ap_invoices.find_one({"id": bill["id"]}, {"_id": 0})
    return {"data": serialize_doc(updated), "match": match}
