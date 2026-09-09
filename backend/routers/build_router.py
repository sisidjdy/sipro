"""ROUTER Jadwal Pembangunan Berbukti (Fase 31) — prefix `/build`.

Tidak menggantikan `/construction` (fase INFRASTRUKTUR proyek: jalan, drainase, saluran)
dan tidak menggantikan `/inspections` (QC formal per fase). Router ini menambah lapisan
yang selama ini hilang: **jadwal & bukti pekerjaan per UNIT rumah**.

RBAC (resource `construction`):
  * view    — semua peran yang boleh melihat proyek
  * create  — buat template & bangkitkan jadwal (PM/owner)
  * update  — kerjakan & ajukan hasil (site engineer + PM/owner)
  * approve — verifikasi/tolak/override gerbang (PM/owner) ← pemisahan tugas
"""
from fastapi import APIRouter, Depends, HTTPException, Query

import build_actions as ba
import build_engine as be
import build_monitor as bm
import reference as ref
from core_utils import new_id, now_iso, parse_pagination, serialize_doc
from db import db, ORG_ID
from models_p31 import (BuildTemplateClone, BuildTemplateIn, ItemDelayCause, ItemOverride,
                        ItemReject, ItemSubmit, ItemVerify, ScheduleGenerate, ScheduleHold)
from rbac import has_role, assert_project_access, audit_log, require_permission

router = APIRouter(prefix="/build", tags=["build"])
SUPERVISOR_ROLES = ("owner", "super_admin", "project_manager")


def _org(user: dict) -> str:
    return user.get("org_id", ORG_ID)


def _can(user: dict) -> dict:
    role = user.get("role")
    return {"submit": role in SUPERVISOR_ROLES + ("site_engineer",),
            "verify": role in SUPERVISOR_ROLES,
            "override": role in SUPERVISOR_ROLES,
            "configure": role in SUPERVISOR_ROLES}


async def _get_item(item_id: str, user: dict) -> tuple:
    org = _org(user)
    item = await db.build_items.find_one({"id": item_id, "org_id": org}, {"_id": 0})
    if not item:
        raise HTTPException(status_code=404, detail="Item pekerjaan tidak ditemukan")
    await assert_project_access(item["project_id"], user)
    sched = await db.build_schedules.find_one({"id": item["schedule_id"]}, {"_id": 0})
    return item, sched


def _check_enum(group: str, value: str, label: str):
    if value not in ref.values(group):
        raise HTTPException(status_code=400,
                            detail=f"{label} '{value}' tidak dikenal. Pilih dari daftar.")


# ================================ TEMPLATE ================================
@router.get("/templates")
async def list_templates(unit_type: str = None, project_id: str = None,
                         user: dict = Depends(require_permission("construction", "view"))):
    q = {"org_id": _org(user)}
    if project_id:
        q["project_id"] = {"$in": [project_id, None]}
    rows = await db.build_templates.find(q, {"_id": 0}).sort("code", 1).to_list(100)
    if unit_type:
        keys = await be.expand_type_keys(
            _org(user), be.unit_type_keys({"type": unit_type, "unit_type_code": unit_type}))
        rows = [r for r in rows if be.template_matches(r, keys)]
    for r in rows:
        r["steps_count"] = len(r.get("steps") or [])
        r["total_weight"] = round(sum(float(s.get("weight") or 0)
                                      for s in r.get("steps") or []), 2)
        r["total_days"] = max([int(s.get("day_to") or 0) for s in r.get("steps") or []],
                             default=0)
        r["used_by"] = await db.build_schedules.count_documents(
            {"org_id": _org(user), "template_id": r["id"]})
    return {"data": serialize_doc(rows), "total": len(rows)}


@router.get("/templates/{template_id}")
async def get_template(template_id: str,
                       user: dict = Depends(require_permission("construction", "view"))):
    tpl = await db.build_templates.find_one({"id": template_id, "org_id": _org(user)},
                                           {"_id": 0})
    if not tpl:
        raise HTTPException(status_code=404, detail="Template tidak ditemukan")
    return {"data": serialize_doc(tpl), "warnings": await _warnings(_org(user), tpl)}


async def _warnings(org: str, tpl: dict) -> list:
    """Peringatan struktur langkah + RAB tipe yang memakai kode langkah di luar template ini."""
    import rab_engine as re_
    return be.validate_steps(tpl.get("steps") or []) + await re_.rab_step_warnings_for_template(org, tpl)


async def _assert_no_overlap(org: str, doc: dict, exclude_id: str = None) -> None:
    """Satu tipe unit pada satu lingkup proyek hanya boleh dilayani SATU template aktif —
    kalau dua template mengklaim tipe yang sama, jadwal unit menjadi tebak-tebakan."""
    mine = set(doc.get("unit_types") or [])
    if not mine:
        return
    q = {"org_id": org, "is_active": {"$ne": False}, "unit_types": {"$in": list(mine)},
         "project_id": doc.get("project_id") or None}
    if exclude_id:
        q["id"] = {"$ne": exclude_id}
    clash = await db.build_templates.find_one(q, {"_id": 0, "code": 1, "unit_types": 1})
    if clash:
        sama = sorted(mine & set(clash.get("unit_types") or []))
        raise HTTPException(status_code=409, detail=(
            f"Tipe unit {', '.join(sama)} sudah dipakai template '{clash['code']}' pada lingkup proyek "
            "yang sama. Satu tipe unit hanya boleh punya satu template tahapan aktif — ubah/nonaktifkan "
            "template itu atau pilih tipe lain."))


async def _save_template(org: str, doc: dict, actor: str) -> dict:
    dup = await db.build_templates.find_one({"org_id": org, "code": doc["code"]}, {"_id": 0})
    if dup:
        raise HTTPException(status_code=409, detail=f"Kode template '{doc['code']}' sudah ada.")
    await _assert_no_overlap(org, doc)
    await db.build_templates.insert_one(dict(doc))
    return doc


@router.post("/templates")
async def create_template(payload: BuildTemplateIn,
                          user: dict = Depends(require_permission("construction", "create"))):
    if not has_role(user, *SUPERVISOR_ROLES):
        raise HTTPException(status_code=403,
                            detail="Hanya Manajer Proyek/direksi yang boleh mengatur template.")
    org, ts = _org(user), now_iso()
    steps = [s.model_dump() for s in payload.steps]
    doc = {**payload.model_dump(exclude={"steps"}), "steps": steps, "id": new_id(),
           "org_id": org, "is_active": True, "is_default": False, "version": 1,
           "created_by": user.get("email"), "created_at": ts, "updated_at": ts}
    await _save_template(org, doc, user.get("email"))
    await audit_log(user, "create", "build_templates", doc["id"], {"code": doc["code"]})
    return {"data": serialize_doc(doc), "warnings": await _warnings(org, doc)}


@router.post("/templates/clone")
async def clone_template(payload: BuildTemplateClone,
                         user: dict = Depends(require_permission("construction", "create"))):
    """Duplikasi template default lalu ubah sesuai tipe unit / proyek (tanpa sentuh kode)."""
    if not has_role(user, *SUPERVISOR_ROLES):
        raise HTTPException(status_code=403, detail="Hanya Manajer Proyek/direksi.")
    org, ts = _org(user), now_iso()
    src = await db.build_templates.find_one({"id": payload.clone_from, "org_id": org},
                                            {"_id": 0})
    if not src:
        raise HTTPException(status_code=404, detail="Template sumber tidak ditemukan")
    doc = {**{k: v for k, v in src.items() if k not in ("id", "created_at", "updated_at")},
           "id": new_id(), "code": payload.code, "name": payload.name,
           "unit_types": payload.unit_types or src.get("unit_types") or [],
           "project_id": payload.project_id, "is_default": False, "version": 1,
           "cloned_from": src["code"], "created_by": user.get("email"),
           "created_at": ts, "updated_at": ts}
    await _save_template(org, doc, user.get("email"))
    return {"data": serialize_doc(doc)}


@router.put("/templates/{template_id}")
async def update_template(template_id: str, payload: BuildTemplateIn,
                          user: dict = Depends(require_permission("construction", "update"))):
    if not has_role(user, *SUPERVISOR_ROLES):
        raise HTTPException(status_code=403, detail="Hanya Manajer Proyek/direksi.")
    org = _org(user)
    tpl = await db.build_templates.find_one({"id": template_id, "org_id": org}, {"_id": 0})
    if not tpl:
        raise HTTPException(status_code=404, detail="Template tidak ditemukan")
    steps = [s.model_dump() for s in payload.steps]
    upd = {**payload.model_dump(exclude={"steps", "code"}), "steps": steps,
           "version": int(tpl.get("version") or 1) + 1, "updated_at": now_iso(),
           "updated_by": user.get("email")}
    await _assert_no_overlap(org, {**tpl, **upd}, exclude_id=template_id)
    await db.build_templates.update_one({"id": template_id}, {"$set": upd})
    used = await db.build_schedules.count_documents({"org_id": org, "template_id": template_id})
    await audit_log(user, "update", "build_templates", template_id,
                    {"steps": len(steps), "version": upd["version"]})
    fresh = await db.build_templates.find_one({"id": template_id}, {"_id": 0})
    return {"data": serialize_doc(fresh), "warnings": await _warnings(org, fresh),
            "note": (f"{used} jadwal unit yang sudah dibuat TIDAK diubah otomatis "
                     "(bukti kerja tidak boleh bergeser). Template baru berlaku untuk "
                     "jadwal berikutnya." if used else None)}


@router.delete("/templates/{template_id}")
async def delete_template(template_id: str,
                          user: dict = Depends(require_permission("construction", "update"))):
    if not has_role(user, *SUPERVISOR_ROLES):
        raise HTTPException(status_code=403, detail="Hanya Manajer Proyek/direksi.")
    org = _org(user)
    used = await db.build_schedules.count_documents({"org_id": org, "template_id": template_id})
    if used:
        raise HTTPException(status_code=400, detail=(
            f"Template dipakai {used} jadwal unit — tidak bisa dihapus. "
            "Nonaktifkan saja bila tidak dipakai lagi."))
    res = await db.build_templates.delete_one({"id": template_id, "org_id": org})
    if not res.deleted_count:
        raise HTTPException(status_code=404, detail="Template tidak ditemukan")
    return {"data": {"id": template_id, "deleted": True}}


# ================================ JADWAL UNIT ================================
@router.post("/schedules")
async def generate(payload: ScheduleGenerate,
                   user: dict = Depends(require_permission("construction", "create"))):
    org = _org(user)
    if not has_role(user, *SUPERVISOR_ROLES):
        raise HTTPException(status_code=403, detail=(
            "Hanya Manajer Proyek/direksi yang boleh menetapkan jadwal pembangunan "
            "(tanggal jadi dasar tenggat, pengingat, dan eskalasi)."))
    unit = await db.units.find_one({"id": payload.unit_id, "org_id": org}, {"_id": 0})
    if not unit:
        raise HTTPException(status_code=404, detail="Unit tidak ditemukan")
    await assert_project_access(unit["project_id"], user)
    try:
        tpl = await be.template_for_unit(org, unit, payload.template_id)
        sched = await be.generate_schedule(org, unit, tpl, payload.start_date,
                                           user.get("email"), regenerate=payload.regenerate)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit_log(user, "create", "build_schedules", sched["id"],
                    {"unit": unit.get("code"), "template": tpl.get("code")})
    return {"data": serialize_doc(sched)}


@router.get("/schedules")
async def schedules(project_id: str = None, status: str = None, skip: int = 0, limit: int = 50,
                    user: dict = Depends(require_permission("construction", "view"))):
    skip, limit = parse_pagination(skip, limit)
    if project_id:
        await assert_project_access(project_id, user)
    out = await bm.board(_org(user), project_id=project_id, status=status,
                         skip=skip, limit=limit)
    return {"data": serialize_doc(out["data"]), "total": out["total"],
            "summary": await bm.summary(_org(user), project_id), "can": _can(user)}


@router.get("/summary")
async def summary(project_id: str = None,
                  user: dict = Depends(require_permission("construction", "view"))):
    return {"data": await bm.summary(_org(user), project_id)}


@router.get("/delays")
async def delays(project_id: str = None,
                 user: dict = Depends(require_permission("construction", "view"))):
    return {"data": await bm.delay_report(_org(user), project_id)}


@router.get("/unscheduled")
async def unscheduled(project_id: str = None,
                      user: dict = Depends(require_permission("construction", "view"))):
    """Unit yang BELUM punya jadwal — supaya tidak ada rumah yang lupa dijadwalkan."""
    org = _org(user)
    q = {"org_id": org}
    if project_id:
        await assert_project_access(project_id, user)
        q["project_id"] = project_id
    have = await db.build_schedules.distinct("unit_id", dict(q))
    q["id"] = {"$nin": have}
    rows = await db.units.find(q, {"_id": 0, "id": 1, "code": 1, "type": 1, "status": 1,
                                   "project_id": 1, "unit_type_code": 1}).sort("code", 1).to_list(300)
    import build_catalog as bcat
    for r in rows:
        r["buildable"] = r.get("type") not in bcat.NO_BUILD_UNIT_TYPES
    return {"data": serialize_doc(rows), "total": len(rows)}


async def contract_of(org: str, item_ids: list) -> dict:
    """Nilai borongan & status tagih per pekerjaan (Fase 33) — transparan untuk PM.

    Tanpa ini, orang lapangan tidak tahu pekerjaan mana yang sudah jadi dasar pembayaran
    subkontraktor, sehingga verifikasi terasa \"cuma administrasi\".
    """
    if not item_ids:
        return {}
    rows = await db.spk_scope_items.find(
        {"org_id": org, "build_item_id": {"$in": item_ids}}, {"_id": 0}).to_list(2000)
    out = {}
    for r in rows:
        out[r["build_item_id"]] = {
            "spk_id": r.get("spk_id"), "spk_number": r.get("spk_number"),
            "subcontractor_name": r.get("subcontractor_name"),
            "value": int(r.get("value") or 0), "cost_code": r.get("cost_code"),
            "billed": bool(r.get("claim_id")), "claim_number": r.get("claim_number"),
            "pending_claim": bool(r.get("pending_claim_id") and not r.get("claim_id")),
            "exclude_reason": r.get("exclude_reason"),
        }
    return out


@router.get("/unit/{unit_id}")
async def unit_bundle(unit_id: str,
                      user: dict = Depends(require_permission("construction", "view"))):
    org = _org(user)
    unit = await db.units.find_one({"id": unit_id, "org_id": org}, {"_id": 0})
    if not unit:
        raise HTTPException(status_code=404, detail="Unit tidak ditemukan")
    await assert_project_access(unit["project_id"], user)
    sched = await db.build_schedules.find_one({"org_id": org, "unit_id": unit_id}, {"_id": 0})
    if not sched:
        import build_catalog as bcat
        buildable = unit.get("type") not in bcat.NO_BUILD_UNIT_TYPES
        keys = await be.expand_type_keys(org, be.unit_type_keys(unit))
        tpls = await db.build_templates.find(
            {"org_id": org, "is_active": {"$ne": False},
             "project_id": {"$in": [unit.get("project_id"), None]}},
            {"_id": 0, "id": 1, "code": 1, "name": 1, "unit_types": 1, "project_id": 1,
             "steps": 1}).sort("code", 1).to_list(200)
        matching = [{"id": t["id"], "code": t["code"], "name": t.get("name"),
                     "unit_types": t.get("unit_types") or [],
                     "project_id": t.get("project_id"),
                     "steps_count": len(t.get("steps") or [])}
                    for t in tpls if be.template_matches(t, keys)]
        return {"data": None, "unit": serialize_doc(unit), "items": [], "weeks": [],
                "can": _can(user), "buildable": buildable,
                "matching_templates": matching,
                "message": ("Unit ini belum punya jadwal pembangunan. Bangkitkan dari "
                            "template sesuai tipe unit agar progres, pengingat, dan bukti "
                            "kerja bisa dipantau.")}
    items = await db.build_items.find({"org_id": org, "schedule_id": sched["id"]},
                                      {"_id": 0}).sort("order", 1).to_list(500)
    contracts = await contract_of(org, [i["id"] for i in items])
    by_code = {i["step_code"]: i for i in items}
    weeks = {}
    for it in items:
        it["gate"] = be.gate_of(it, by_code, sched)
        it["contract"] = contracts.get(it["id"])
        weeks.setdefault(int(it.get("week") or 1), []).append(it)
    grouped = [{"week": w, "items": serialize_doc(rows)} for w, rows in sorted(weeks.items())]
    return {"data": serialize_doc(sched), "unit": serialize_doc(unit),
            "items": serialize_doc(items), "weeks": grouped,
            "timeline": await bm.timeline(org, sched["id"]), "can": _can(user)}


@router.post("/schedules/{schedule_id}/hold")
async def hold(schedule_id: str, payload: ScheduleHold,
               user: dict = Depends(require_permission("construction", "approve"))):
    org = _org(user)
    sched = await db.build_schedules.find_one({"id": schedule_id, "org_id": org}, {"_id": 0})
    if not sched:
        raise HTTPException(status_code=404, detail="Jadwal tidak ditemukan")
    _check_enum("build_delay_cause", payload.cause, "Penyebab")
    return {"data": serialize_doc(await ba.hold_schedule(org, sched, payload.cause,
                                                         payload.note, user))}


@router.post("/schedules/{schedule_id}/resume")
async def resume(schedule_id: str,
                 user: dict = Depends(require_permission("construction", "approve"))):
    org = _org(user)
    sched = await db.build_schedules.find_one({"id": schedule_id, "org_id": org}, {"_id": 0})
    if not sched:
        raise HTTPException(status_code=404, detail="Jadwal tidak ditemukan")
    return {"data": serialize_doc(await ba.resume_schedule(org, sched, user))}


@router.delete("/schedules/{schedule_id}")
async def delete_schedule(schedule_id: str,
                          user: dict = Depends(require_permission("construction", "approve"))):
    org = _org(user)
    sched = await db.build_schedules.find_one({"id": schedule_id, "org_id": org}, {"_id": 0})
    if not sched:
        raise HTTPException(status_code=404, detail="Jadwal tidak ditemukan")
    done = await db.build_items.count_documents({"org_id": org, "schedule_id": schedule_id,
                                                 "status": "done"})
    if done:
        raise HTTPException(status_code=400, detail=(
            f"{done} pekerjaan sudah diverifikasi — jadwal tidak boleh dihapus "
            "(bukti kerja & jejak audit harus utuh)."))
    await db.build_items.delete_many({"org_id": org, "schedule_id": schedule_id})
    await db.build_schedules.delete_one({"id": schedule_id})
    await db.units.update_one({"id": sched["unit_id"]}, {"$set": {
        "construction_progress": 0, "construction_status": "not_started",
        "updated_at": now_iso()}})
    await audit_log(user, "delete", "build_schedules", schedule_id,
                    {"unit": sched.get("unit_code")})
    return {"data": {"id": schedule_id, "deleted": True}}


# ================================ ITEM PEKERJAAN ================================
@router.get("/items")
async def list_items(project_id: str = None, status: str = None, mine: bool = False,
                     unit_id: str = None, skip: int = 0, limit: int = 50,
                     user: dict = Depends(require_permission("construction", "view"))):
    """Antrean kerja: `mine=true` → tugas saya; `status=submitted` → antrean verifikasi.

    Dua nilai `status` khusus dipakai UI antrean supaya pengguna tidak menggulir
    pekerjaan yang sudah beres: `todo` (siap/dikerjakan/perbaiki) dan `open` (belum
    selesai, termasuk yang masih terkunci gerbang).
    """
    skip, limit = parse_pagination(skip, limit)
    q = {"org_id": _org(user)}
    if project_id:
        q["project_id"] = project_id
    if unit_id:
        q["unit_id"] = unit_id
    if status == "todo":
        q["status"] = {"$in": ["ready", "in_progress", "rework"]}
    elif status == "open":
        q["status"] = {"$ne": "done"}
    elif status and status != "all":
        q["status"] = status
    if mine:
        q["assigned_to"] = user.get("email")
    total = await db.build_items.count_documents(q)
    rows = await db.build_items.find(q, {"_id": 0}).sort(
        [("planned_finish", 1), ("order", 1)]).skip(skip).limit(limit).to_list(limit)
    return {"data": serialize_doc(rows), "total": total, "can": _can(user)}


@router.get("/items/{item_id}")
async def get_item(item_id: str,
                   user: dict = Depends(require_permission("construction", "view"))):
    """Detail SATU pekerjaan + instruksi + jejak pengajuan (dipakai deep link task).

    Tanpa endpoint ini, tautan pada tugas Work Hub tidak bisa membuka pekerjaan yang
    dimaksud dan pengguna harus mencari sendiri di daftar jadwal.
    """
    import build_instruction as bi
    item, sched = await _get_item(item_id, user)
    subs = await db.build_item_submissions.find(
        {"org_id": _org(user), "item_id": item_id}, {"_id": 0, "checklist": 0}).sort(
        "submitted_at", -1).to_list(20)
    return {"data": serialize_doc(item), "schedule": serialize_doc(sched),
            "instruction": bi.instruction_lines(item, sched or {}),
            "brief": serialize_doc(bi.brief(item)),
            "contract": (await contract_of(_org(user), [item_id])).get(item_id),
            "submissions": serialize_doc(subs), "can": _can(user)}


@router.post("/items/{item_id}/start")
async def start_item(item_id: str,
                     user: dict = Depends(require_permission("construction", "update"))):
    item, sched = await _get_item(item_id, user)
    try:
        return {"data": serialize_doc(await ba.start_item(_org(user), item, sched,
                                                          user.get("email")))}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/items/{item_id}/submit")
async def submit_item(item_id: str, payload: ItemSubmit,
                      user: dict = Depends(require_permission("construction", "update"))):
    item, sched = await _get_item(item_id, user)
    try:
        out = await ba.submit_item(_org(user), item, sched, payload, user)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"data": serialize_doc(out["item"]), "warning": out.get("warning"),
            "replay": bool(out.get("replay")),
            "message": ("Pengajuan ini sudah diterima sebelumnya — antrean offline dikirim "
                        "ulang, tidak dibuat dobel."
                        if out.get("replay")
                        else "Hasil kerja diajukan — menunggu verifikasi supervisor.")}


@router.post("/items/{item_id}/verify")
async def verify_item(item_id: str, payload: ItemVerify,
                      user: dict = Depends(require_permission("construction", "approve"))):
    item, sched = await _get_item(item_id, user)
    try:
        out = await ba.verify_item(_org(user), item, sched, payload.note, user)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"data": serialize_doc(out["item"]), "schedule": serialize_doc(out["schedule"]),
            "message": f"Diverifikasi. Progres unit {out['schedule'].get('progress')}%."}


@router.post("/items/{item_id}/reject")
async def reject_item(item_id: str, payload: ItemReject,
                      user: dict = Depends(require_permission("construction", "approve"))):
    item, _ = await _get_item(item_id, user)
    try:
        return {"data": serialize_doc(await ba.reject_item(_org(user), item, payload.reason,
                                                           user))}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/items/{item_id}/override")
async def override_item(item_id: str, payload: ItemOverride,
                        user: dict = Depends(require_permission("construction", "approve"))):
    item, _ = await _get_item(item_id, user)
    _check_enum("build_override_reason", payload.reason_code, "Alasan override")
    try:
        return {"data": serialize_doc(await ba.override_gate(_org(user), item,
                                                             payload.reason_code,
                                                             payload.note, user)),
                "message": ("Gerbang diterobos — dicatat pada jejak audit dan dilaporkan "
                            "ke direksi.")}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/items/{item_id}/delay-cause")
async def delay_cause(item_id: str, payload: ItemDelayCause,
                      user: dict = Depends(require_permission("construction", "update"))):
    item, _ = await _get_item(item_id, user)
    _check_enum("build_delay_cause", payload.cause, "Penyebab keterlambatan")
    try:
        return {"data": serialize_doc(await ba.set_delay_cause(_org(user), item, payload.cause,
                                                               payload.note, user))}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/tick")
async def run_tick(user: dict = Depends(require_permission("construction", "approve"))):
    """Jalankan pemantauan sekarang (pengingat + eskalasi) — dipakai supervisor & uji."""
    return {"data": await bm.tick()}
