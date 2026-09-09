"""QC / Inspeksi (EPIC 2.4) — checklist inspeksi multi-item + hasil pass/fail,
auto-buat punch item untuk item gagal, dan kesiapan serah terima (handover) saat lulus.

Alur: buat inspeksi (dari template/kustom) -> isi hasil tiap item -> finalisasi.
- Ada item **fail** -> inspeksi FAILED: setiap item gagal jadi **punch item** + tugas,
  fase/unit ditahan (qc_hold).
- Semua **pass/na** -> inspeksi PASSED; bila kategori 'handover' -> unit ditandai siap
  serah terima (readiness untuk BAST — tidak memblokir alur BAST keuangan yang ada).

RBAC resource `construction` (PM/site create+update, finance view; owner/super full).
Semua ber-scope org + project (assert_project_access).
"""
from fastapi import APIRouter, Depends, HTTPException

import build_calendar as bcal
import sequences as seq
from db import db, ORG_ID
from core_utils import new_id, now_iso, serialize_doc, due_in
from rbac import has_role, require_permission, assert_project_access
from engine import emit, add_activity, auto_create_task
from models import InspectionCreate, InspectionItemsUpdate
from models_p36 import InspectionScheduleIn

router = APIRouter(prefix="/inspections", tags=["inspections"])

ITEM_RESULTS = ("pending", "pass", "fail", "na")
CATEGORIES = ("structural", "mep", "finishing", "handover", "lainnya")


def _counts(items):
    p = sum(1 for i in items if i.get("result") == "pass")
    f = sum(1 for i in items if i.get("result") == "fail")
    na = sum(1 for i in items if i.get("result") == "na")
    pend = sum(1 for i in items if i.get("result") in (None, "pending"))
    return {"pass_count": p, "fail_count": f, "na_count": na, "pending_count": pend}


@router.get("/templates")
async def list_templates(user: dict = Depends(require_permission("construction", "view"))):
    org = user.get("org_id", ORG_ID)
    rows = await db.inspection_templates.find({"org_id": org, "is_active": True}, {"_id": 0}).sort("name", 1).to_list(100)
    return {"data": serialize_doc(rows), "total": len(rows)}


@router.get("")
async def list_inspections(project_id: str = None, status: str = None, unit_id: str = None,
                           user: dict = Depends(require_permission("construction", "view"))):
    org = user.get("org_id", ORG_ID)
    q = {"org_id": org}
    if project_id:
        await assert_project_access(project_id, user)
        q["project_id"] = project_id
    elif has_role(user, "project_manager", "site_engineer"):
        from rbac import project_query
        projs = await db.projects.find(project_query(user, {}), {"_id": 0, "id": 1}).to_list(500)
        q["project_id"] = {"$in": [p["id"] for p in projs]}
    if status:
        q["status"] = status
    # Fase 46 (unit-centric): Unit 360 harus bisa menanyakan inspeksi RUMAH ini saja.
    if unit_id:
        q["unit_id"] = unit_id
    rows = await db.inspections.find(q, {"_id": 0}).sort("created_at", -1).to_list(500)
    summary = {
        "total": len(rows),
        "open": sum(1 for r in rows if r.get("status") == "in_progress"),
        "passed": sum(1 for r in rows if r.get("status") == "passed"),
        "failed": sum(1 for r in rows if r.get("status") == "failed"),
    }
    return {"data": serialize_doc(rows), "total": len(rows), "summary": summary}


@router.post("")
async def create_inspection(payload: InspectionCreate,
                            user: dict = Depends(require_permission("construction", "create"))):
    proj = await assert_project_access(payload.project_id, user)
    org = user.get("org_id", ORG_ID)
    category = payload.category
    items = []
    template = None
    if payload.template_code:
        template = await db.inspection_templates.find_one(
            {"org_id": org, "code": payload.template_code}, {"_id": 0})
        if not template:
            raise HTTPException(status_code=404, detail="Template inspeksi tidak ditemukan")
        items = [{"key": it["key"], "label": it["label"], "result": "pending", "note": None}
                 for it in template.get("items", [])]
        category = category or template.get("category")
    elif payload.items:
        items = [{"key": it.key, "label": it.label or it.key, "result": "pending", "note": None}
                 for it in payload.items]
    if not items:
        raise HTTPException(status_code=400, detail="Inspeksi butuh minimal 1 item (template atau kustom).")
    if category and category not in CATEGORIES:
        raise HTTPException(status_code=400, detail="Kategori inspeksi tidak valid.")

    ts = now_iso()
    doc = {
        "id": new_id(), "org_id": org,
        "inspection_number": await seq.next_number("inspection", org, prefix="QC", context={
            "project_id": payload.project_id, "unit_id": getattr(payload, "unit_id", None)}),
        "project_id": payload.project_id, "project_name": proj.get("name"),
        "unit_id": payload.unit_id, "phase_id": payload.phase_id,
        "template_id": template.get("id") if template else None,
        "template_code": payload.template_code, "category": category or "lainnya",
        "title": payload.title or (template.get("name") if template else "Inspeksi QC"),
        "items": items, "status": "in_progress", **_counts(items),
        "punch_ids": [], "punch_created": False, "result_note": None,
        "created_by": user.get("email"), "created_at": ts, "updated_at": ts,
        "finalized_by": None, "finalized_at": None,
        # Fase 36: tanggal rencana inspeksi (dipakai Kalender Jadwal). Sengaja kosong saat
        # dibuat — kalender tidak boleh mengarang tanggal; ada aksi "Jadwalkan" terpisah.
        "scheduled_date": None, "scheduled_by": None, "scheduled_note": None,
    }
    await db.inspections.insert_one(dict(doc))
    doc.pop("_id", None)
    return {"data": serialize_doc(doc)}


async def _get(org: str, iid: str, user: dict) -> dict:
    insp = await db.inspections.find_one({"id": iid, "org_id": org}, {"_id": 0})
    if not insp:
        raise HTTPException(status_code=404, detail="Inspeksi tidak ditemukan")
    await assert_project_access(insp["project_id"], user)
    return insp


@router.get("/{iid}")
async def get_inspection(iid: str, user: dict = Depends(require_permission("construction", "view"))):
    return {"data": serialize_doc(await _get(user.get("org_id", ORG_ID), iid, user))}


@router.put("/{iid}/items")
async def update_items(iid: str, payload: InspectionItemsUpdate,
                       user: dict = Depends(require_permission("construction", "update"))):
    org = user.get("org_id", ORG_ID)
    insp = await _get(org, iid, user)
    if insp.get("status") != "in_progress":
        raise HTTPException(status_code=400, detail="Inspeksi sudah difinalisasi, tidak bisa diubah.")
    by_key = {i["key"]: i for i in insp["items"]}
    for upd in payload.items:
        if upd.key not in by_key:
            raise HTTPException(status_code=400, detail=f"Item '{upd.key}' tidak ada di inspeksi ini.")
        if upd.result is not None:
            if upd.result not in ITEM_RESULTS:
                raise HTTPException(status_code=400, detail="Hasil item harus pending/pass/fail/na.")
            by_key[upd.key]["result"] = upd.result
        if upd.note is not None:
            by_key[upd.key]["note"] = upd.note
    items = list(by_key.values())
    await db.inspections.update_one({"id": iid, "org_id": org},
                                    {"$set": {"items": items, **_counts(items), "updated_at": now_iso()}})
    return {"data": serialize_doc(await db.inspections.find_one({"id": iid}, {"_id": 0}))}


@router.put("/{iid}/schedule")
async def schedule_inspection(iid: str, payload: InspectionScheduleIn,
                              user: dict = Depends(require_permission("construction",
                                                                      "update"))):
    """Fase 36 — beri (atau hapus) TANGGAL RENCANA inspeksi supaya muncul di Kalender Jadwal.

    Sebelum ini inspeksi hanya punya `created_at`/`finalized_at`, jadi kalender tidak punya
    tanggal jujur untuk dipakai. Tanggal boleh dikosongkan lagi (`scheduled_date: null`)
    bila rencananya dibatalkan — inspeksi kembali ke daftar "belum dijadwalkan".
    """
    org = user.get("org_id", ORG_ID)
    insp = await _get(org, iid, user)
    if insp.get("status") != "in_progress":
        raise HTTPException(status_code=400,
                            detail="Inspeksi sudah difinalisasi — tanggal rencananya "
                                   "tidak relevan lagi.")
    target = payload.scheduled_date
    if target:
        cal = await bcal.resolve(org, insp.get("project_id"))
        info = bcal.day_info(cal, target)
        if not info["is_workday"]:
            suggest = bcal.next_workday(cal, target).isoformat()
            why = (f"hari libur {info['holiday']}" if info.get("holiday")
                   else f"{info['weekday_label']} bukan hari kerja")
            raise HTTPException(
                status_code=400,
                detail=(f"{target} adalah {why} pada kalender kerja. Pilih hari kerja "
                        f"(terdekat: {suggest}) atau ubah kalender kerja lebih dulu."))
    await db.inspections.update_one({"id": iid, "org_id": org}, {"$set": {
        "scheduled_date": target, "scheduled_by": user.get("email") if target else None,
        "scheduled_note": payload.note, "updated_at": now_iso()}})
    await add_activity(entity_type="inspection", entity_id=iid, type="system",
                       body=(f"Inspeksi {insp.get('inspection_number')} dijadwalkan "
                             f"{target}." if target else
                             f"Tanggal rencana inspeksi {insp.get('inspection_number')} "
                             "dihapus."),
                       actor=user.get("email"), org_id=org)
    return {"data": serialize_doc(await db.inspections.find_one({"id": iid}, {"_id": 0}))}


@router.post("/{iid}/finalize")
async def finalize(iid: str, user: dict = Depends(require_permission("construction", "update"))):
    org = user.get("org_id", ORG_ID)
    insp = await _get(org, iid, user)
    if insp.get("status") != "in_progress":
        raise HTTPException(status_code=400, detail="Inspeksi sudah difinalisasi.")
    items = insp["items"]
    if any(i.get("result") in (None, "pending") for i in items):
        raise HTTPException(status_code=400, detail="Lengkapi hasil semua item sebelum finalisasi.")
    proj = await assert_project_access(insp["project_id"], user)
    fails = [i for i in items if i.get("result") == "fail"]
    overall = "failed" if fails else "passed"
    ts = now_iso()
    pm = None
    members = proj.get("members") or []
    if members:
        pmu = await db.users.find_one({"org_id": org, "email": {"$in": members}, "role": "project_manager"},
                                      {"_id": 0, "email": 1})
        pm = pmu["email"] if pmu else members[0]

    punch_ids = []
    for f in fails:
        pid = new_id()
        await db.punch_items.insert_one({
            "id": pid, "org_id": org, "project_id": insp["project_id"], "project_name": proj.get("name"),
            "unit_id": insp.get("unit_id"),
            "title": f"[QC {insp['inspection_number']}] {f.get('label') or f.get('key')}",
            "description": f.get("note") or f"Item gagal pada inspeksi {insp['inspection_number']}.",
            "location": None, "category": insp.get("category") or "lainnya", "severity": "high",
            "status": "open", "assigned_to": pm, "due_date": due_in(days=3), "photo": None,
            "source": "inspection", "inspection_id": iid, "opened_by": user.get("email"),
            "closed_at": None, "created_at": ts, "updated_at": ts,
        })
        await auto_create_task(
            source_event=f"inspection.punch:{pid}",
            title=f"Punch QC: {f.get('label') or f.get('key')} — {proj.get('code') or proj.get('name')}",
            jobdesk_code="TK-05",
            type="review", related_entity_type="punch_item", related_entity_id=pid,
            assigned_to=pm, due_date=due_in(days=3), sla_due_at=due_in(days=3),
            priority="urgent", org_id=org, description=f.get("note") or "")
        punch_ids.append(pid)

    await db.inspections.update_one({"id": iid, "org_id": org}, {"$set": {
        "status": overall, "punch_ids": punch_ids, "punch_created": bool(punch_ids),
        "finalized_by": user.get("email"), "finalized_at": ts, "updated_at": ts, **_counts(items)}})

    if overall == "failed":
        if insp.get("phase_id"):
            await db.construction_phases.update_one({"id": insp["phase_id"], "org_id": org},
                                                    {"$set": {"status": "qc_hold", "updated_at": ts}})
        if insp.get("unit_id"):
            await db.units.update_one({"id": insp["unit_id"], "org_id": org},
                                      {"$set": {"construction_status": "qc_hold", "updated_at": ts}})
        await emit("qc.failed", "project", insp["project_id"],
                   {"inspection_id": iid, "punch": len(punch_ids)}, org_id=org)
        body = f"Inspeksi {insp['inspection_number']} GAGAL — {len(punch_ids)} punch item dibuat."
    else:
        if insp.get("category") == "handover" and insp.get("unit_id"):
            await db.units.update_one({"id": insp["unit_id"], "org_id": org},
                                      {"$set": {"qc_status": "passed", "construction_status": "ready_handover",
                                                "updated_at": ts}})
        if insp.get("phase_id"):
            await db.construction_phases.update_one(
                {"id": insp["phase_id"], "org_id": org, "status": "qc_hold"},
                {"$set": {"status": "in_progress", "updated_at": ts}})
        await emit("qc.passed", "project", insp["project_id"], {"inspection_id": iid}, org_id=org)
        body = (f"Inspeksi {insp['inspection_number']} LULUS."
                + (" Unit siap serah terima (BAST)." if insp.get("category") == "handover" and insp.get("unit_id") else ""))

    await add_activity(entity_type="project", entity_id=insp["project_id"], type="system",
                       body=body, actor=user.get("email"), org_id=org)
    return {"data": serialize_doc(await db.inspections.find_one({"id": iid}, {"_id": 0}))}
