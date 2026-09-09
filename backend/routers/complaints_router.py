"""Staff Complaint / CS management + SLA dashboard (Phase 9 — EPIC M1 loop).

Buyer complaints arrive via the Customer Portal (POST /api/portal/complaints), which
also spawns an SLA task. Staff manage them here: list/filter, view the thread, reply
(notifies the buyer via the WhatsApp provider / honest simulation), transition status,
and take ownership. SLA breach is computed live (sla_due_at < now and not resolved).
"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException

import listing as lst
import stage_clock as clock
from db import db, ORG_ID
from core_utils import now_iso, serialize_doc, parse_pagination
from rbac import has_role, require_permission, audit_log
from engine import create_notification
from notifications import send_whatsapp
from models import ComplaintRespond, ComplaintStatusUpdate, ComplaintAssign

router = APIRouter(prefix="/complaints", tags=["complaints"])

STATUSES = ("open", "in_progress", "resolved")


async def _scope(user: dict, base: dict = None) -> dict:
    """org scope + row-scope: plain 'sales' only see complaints assigned to them."""
    q = dict(base or {})
    q["org_id"] = user.get("org_id", ORG_ID)
    if has_role(user, "sales"):
        q["assigned_to"] = user.get("email")
    return q


def _mark_breach(row: dict, now: str) -> dict:
    row["sla_breached"] = bool(
        row.get("status") != "resolved" and row.get("sla_due_at") and row["sla_due_at"] < now)
    return row


COMPLAINT_SORTS = {"subject": "subject", "customer_name": "customer_name",
                   "status": "status", "priority": "priority", "category": "category",
                   "unit_code": "unit_code", "created_at": "created_at",
                   "sla_due_at": "sla_due_at", **clock.SORTS}


@router.get("")
async def list_complaints(status: str = None, priority: str = None, category: str = None,
                          q: str = None, sla: str = None, customer_id: str = None,
                          sort: str = None, direction: str = None,
                          skip: int = 0, limit: int = 50,
                          user: dict = Depends(require_permission("complaints", "view"))):
    """Daftar komplain: cari + filter multi + sort + paginasi nyata (Fase 40).

    Dulu endpoint ini mengirim 500 baris sekaligus tanpa paginasi dan menghitung ringkasan
    dari baris yang terkirim — begitu data melewati 500, angka ringkasan mulai bohong.
    Sekarang baris dipaginasi dan SEMUA angka ringkasan dihitung di database.
    """
    skip, limit = parse_pagination(skip, limit)
    query = await _scope(user)
    lst.apply_in(query, "status", status, STATUSES)
    lst.apply_in(query, "priority", priority)
    lst.apply_in(query, "category", category)
    lst.apply_in(query, "customer_id", customer_id)
    lst.apply_search(query, q, ("subject", "customer_name", "unit_code", "message"))
    now = now_iso()
    if sla == "breached":
        query["status"] = {"$ne": "resolved"} if "status" not in query else query["status"]
        query["sla_due_at"] = {"$lt": now}
    elif sla:
        # Fase 41: umur STATUS (jam tahap) — beda dari `sla_due_at` yang mengukur janji
        # penyelesaian komplain. Keduanya dipertahankan supaya arti angka tidak berubah.
        clock.apply_sla_filter(query, "complaint", sla)
    total = await db.complaints.count_documents(query)
    rows = await (db.complaints.find(query, {"_id": 0})
                  .sort(lst.sort_spec(sort, direction, COMPLAINT_SORTS, ("created_at", -1)))
                  .skip(skip).limit(limit).to_list(limit))
    for r in rows:
        _mark_breach(r, now)
    await clock.attach(rows, "complaint", org_id=user.get("org_id", ORG_ID))
    scope_base = await _scope(user)
    counts = {
        "total": await db.complaints.count_documents(scope_base),
        "open": await db.complaints.count_documents({**scope_base, "status": "open"}),
        "in_progress": await db.complaints.count_documents({**scope_base, "status": "in_progress"}),
        "resolved": await db.complaints.count_documents({**scope_base, "status": "resolved"}),
        "breached": await db.complaints.count_documents(
            {**scope_base, "status": {"$ne": "resolved"}, "sla_due_at": {"$lt": now}}),
    }
    return {"data": serialize_doc(rows), "total": total, "counts": counts}


@router.get("/stats")
async def complaint_stats(user: dict = Depends(require_permission("complaints", "view"))):
    rows = await db.complaints.find(await _scope(user), {"_id": 0}).to_list(2000)
    now = now_iso()
    by_cat, by_pri, res_hours, breached = {}, {}, [], 0
    for r in rows:
        cat = r.get("category", "umum")
        pri = r.get("priority", "medium")
        by_cat[cat] = by_cat.get(cat, 0) + 1
        by_pri[pri] = by_pri.get(pri, 0) + 1
        if r.get("status") != "resolved" and r.get("sla_due_at") and r["sla_due_at"] < now:
            breached += 1
        if r.get("status") == "resolved" and r.get("resolved_at") and r.get("created_at"):
            try:
                delta = datetime.fromisoformat(r["resolved_at"]) - datetime.fromisoformat(r["created_at"])
                res_hours.append(delta.total_seconds() / 3600.0)
            except Exception:  # noqa: BLE001
                pass
    stats = {
        "total": len(rows),
        "open": sum(1 for r in rows if r.get("status") == "open"),
        "in_progress": sum(1 for r in rows if r.get("status") == "in_progress"),
        "resolved": sum(1 for r in rows if r.get("status") == "resolved"),
        "breached": breached,
        "avg_resolution_hours": round(sum(res_hours) / len(res_hours), 1) if res_hours else 0,
        "by_category": by_cat, "by_priority": by_pri,
    }
    return {"data": stats}


async def _get(cid: str, user: dict) -> dict:
    doc = await db.complaints.find_one(await _scope(user, {"id": cid}), {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Komplain tidak ditemukan")
    return doc


@router.get("/{cid}")
async def get_complaint(cid: str, user: dict = Depends(require_permission("complaints", "view"))):
    doc = _mark_breach(await _get(cid, user), now_iso())
    return {"data": serialize_doc(doc)}


@router.post("/{cid}/respond")
async def respond_complaint(cid: str, payload: ComplaintRespond,
                            user: dict = Depends(require_permission("complaints", "update"))):
    if not (payload.message or "").strip():
        raise HTTPException(status_code=400, detail="Pesan balasan tidak boleh kosong.")
    doc = await _get(cid, user)
    ts = now_iso()
    resp = {"by": user.get("email"), "message": payload.message, "at": ts, "staff": True}
    if payload.resolve:
        new_status = "resolved"
    elif doc.get("status") == "open":
        new_status = "in_progress"
    else:
        new_status = doc.get("status")
    setter = {"status": new_status, "updated_at": ts}
    if new_status != doc.get("status"):
        setter.update(await clock.patch_for("complaint", new_status,
                                           org_id=doc["org_id"], at=ts))
    if payload.resolve:
        setter["resolved_at"] = ts
    await db.complaints.update_one({"id": cid, "org_id": doc["org_id"]},
                                   {"$push": {"responses": resp}, "$set": setter})
    cust = await db.customers.find_one({"id": doc.get("customer_id")}, {"_id": 0}) or {}
    await send_whatsapp(cust.get("phone"),
                        f"Update komplain '{doc.get('subject')}': {payload.message}")
    await audit_log(user, "respond", "complaints", cid)
    fresh = _mark_breach(await db.complaints.find_one({"id": cid}, {"_id": 0}), now_iso())
    return {"data": serialize_doc(fresh)}


@router.put("/{cid}/status")
async def update_status(cid: str, payload: ComplaintStatusUpdate,
                        user: dict = Depends(require_permission("complaints", "update"))):
    if payload.status not in STATUSES:
        raise HTTPException(status_code=400, detail="Status tidak valid.")
    doc = await _get(cid, user)
    ts = now_iso()
    setter = {"status": payload.status, "updated_at": ts}
    if payload.status != doc.get("status"):
        setter.update(await clock.patch_for("complaint", payload.status,
                                           org_id=doc["org_id"], at=ts))
    if payload.status == "resolved":
        setter["resolved_at"] = ts
    upd = {"$set": setter}
    if payload.note:
        upd["$push"] = {"responses": {"by": user.get("email"), "message": payload.note,
                                       "at": ts, "staff": True, "system": True}}
    await db.complaints.update_one({"id": cid, "org_id": doc["org_id"]}, upd)
    await audit_log(user, "status", "complaints", cid, {"status": payload.status})
    fresh = _mark_breach(await db.complaints.find_one({"id": cid}, {"_id": 0}), now_iso())
    return {"data": serialize_doc(fresh)}


@router.post("/{cid}/assign")
async def assign_complaint(cid: str, payload: ComplaintAssign,
                           user: dict = Depends(require_permission("complaints", "update"))):
    doc = await _get(cid, user)
    ts = now_iso()
    status = "in_progress" if doc.get("status") == "open" else doc.get("status")
    await db.complaints.update_one(
        {"id": cid, "org_id": doc["org_id"]},
        {"$set": {"assigned_to": payload.assigned_to, "status": status, "updated_at": ts}})
    await create_notification(
        user_email=payload.assigned_to, title="Komplain ditugaskan ke Anda",
        body=f"{doc.get('customer_name')}: {doc.get('subject')}", type="complaint",
        related_entity_type="deal", related_entity_id=doc.get("deal_id"), org_id=doc["org_id"])
    await audit_log(user, "assign", "complaints", cid, {"assigned_to": payload.assigned_to})
    fresh = _mark_breach(await db.complaints.find_one({"id": cid}, {"_id": 0}), now_iso())
    return {"data": serialize_doc(fresh)}
