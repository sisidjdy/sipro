"""Work Hub v2 (Fase 29) — endpoint divisi, katalog jobdesk, papan supervisor,
dan siklus kerja task berbukti: mulai → ajukan → verifikasi/kembalikan.

Semua di bawah prefix `/api/work`. Aturan akses:
  * staf      : hanya task miliknya (mulai/ajukan)
  * supervisor: task divisinya (assign/verifikasi/kembalikan/konfigurasi jobdesk)
  * owner     : lintas divisi
"""
from fastapi import APIRouter, Depends, HTTPException

import jobdesk_catalog as cat
import reference_p29 as p29
import workhub as wh
from core_utils import now_iso, serialize_doc
from db import db, ORG_ID
from engine import add_activity, create_notification
from models_p29 import (JobdeskConfig, JobdeskRun, TaskAssign, TaskReject, TaskSubmit,
                        TaskVerify)
from rbac import require_permission

router = APIRouter(prefix="/work", tags=["workhub"])

VALID_ASSIGNEE_RULES = {o["value"] for o in p29.GROUPS_P29["assignee_rule"]["options"]}
VALID_VERIFY = {o["value"] for o in p29.GROUPS_P29["verify_mode"]["options"]}
VALID_PROOF = {o["value"] for o in p29.GROUPS_P29["proof_kind"]["options"]}
VALID_RECURRENCE = {o["value"] for o in p29.GROUPS_P29["recurrence"]["options"]}


# ----------------------------- helpers -----------------------------
def _org(user: dict) -> str:
    return user.get("org_id", ORG_ID)


def _my_division(user: dict) -> str:
    return wh.division_of(user)


def _assert_supervisor(user: dict, division: str = None):
    if not wh.is_supervisor(user):
        raise HTTPException(status_code=403,
                            detail="Hanya supervisor divisi yang boleh mengatur penugasan.")
    if division and not wh.is_owner_level(user) and _my_division(user) != division:
        raise HTTPException(status_code=403,
                            detail="Akses ditolak: bukan divisi Anda.")


async def _get_task(task_id: str, user: dict) -> dict:
    t = await db.tasks.find_one({"id": task_id, "org_id": _org(user)}, {"_id": 0})
    if not t:
        raise HTTPException(status_code=404, detail="Tugas tidak ditemukan")
    return t


def _can_work(task: dict, user: dict) -> bool:
    if task.get("assigned_to") == user.get("email"):
        return True
    if wh.is_owner_level(user):
        return True
    return wh.is_supervisor(user) and task.get("division") == _my_division(user)


# ----------------------------- divisi -----------------------------
@router.get("/divisions")
async def list_divisions(user: dict = Depends(require_permission("work_tasks", "view"))):
    """Daftar divisi + ringkasan pekerjaan. Staf hanya melihat divisinya."""
    org = _org(user)
    mine = _my_division(user)
    codes = [o["value"] for o in p29.GROUPS_P29["division"]["options"]]
    if not wh.is_owner_level(user) and mine:
        codes = [mine]
    out = []
    for d in codes:
        tasks = await db.tasks.count_documents(
            {"org_id": org, "division": d, "status": {"$in": wh.OPEN_STATES}})
        overdue = await db.tasks.count_documents(
            {"org_id": org, "division": d, "status": {"$in": wh.ACTIVE_STATES},
             "due_date": {"$lt": now_iso()}})
        review = await db.tasks.count_documents(
            {"org_id": org, "division": d, "status": "submitted"})
        members = await wh.division_members(org, d)
        sup = [m for m in members if wh.level_of(m) == "supervisor"]
        out.append({
            "code": d, "label": p29.DIVISION_LABEL.get(d, d), "open": tasks,
            "overdue": overdue, "review": review, "members": len(members),
            "supervisor": (sup[0].get("name") if sup else None),
            "supervisor_email": (sup[0].get("email") if sup else None),
            "jobdesk_count": len([j for j in cat.CATALOG if j["division"] == d]),
        })
    return {"data": out, "my_division": mine, "my_level": wh.level_of(user)}


@router.get("/divisions/{division}/members")
async def division_members(division: str,
                           user: dict = Depends(require_permission("work_tasks", "view"))):
    org = _org(user)
    if not wh.is_owner_level(user) and _my_division(user) != division:
        raise HTTPException(status_code=403, detail="Akses ditolak: bukan divisi Anda.")
    rows = await wh.division_members(org, division)
    return {"data": [{"email": r["email"], "name": r.get("name"), "role": r.get("role"),
                      "level": wh.level_of(r)} for r in rows]}


# ----------------------------- katalog jobdesk -----------------------------
@router.get("/jobdesks")
async def list_jobdesks(division: str = None,
                        user: dict = Depends(require_permission("work_tasks", "view"))):
    org = _org(user)
    if not wh.is_owner_level(user):
        division = division or _my_division(user)
    rows = await wh.jobdesks(org, division)
    for r in rows:
        r["open_tasks"] = await db.tasks.count_documents(
            {"org_id": org, "jobdesk_code": r["code"], "status": {"$in": wh.OPEN_STATES}})
        r["done_tasks"] = await db.tasks.count_documents(
            {"org_id": org, "jobdesk_code": r["code"], "status": "done"})
    return {"data": rows, "total": len(rows), "can_manage": wh.is_supervisor(user)}


@router.put("/jobdesks/{code}")
async def update_jobdesk(code: str, payload: JobdeskConfig,
                         user: dict = Depends(require_permission("work_tasks", "update"))):
    """Supervisor mengatur jobdesk divisinya (SLA, prioritas, penerima, verifikasi)."""
    org = _org(user)
    jd = await wh.jobdesk(org, code)
    if not jd.get("title"):
        raise HTTPException(status_code=404, detail="Jobdesk tidak ditemukan")
    _assert_supervisor(user, jd.get("division"))
    upd = {k: v for k, v in payload.model_dump(exclude_none=True).items()}
    if "assignee_rule" in upd and upd["assignee_rule"] not in VALID_ASSIGNEE_RULES:
        raise HTTPException(status_code=400, detail="Aturan penerima tidak valid")
    if "verify_mode" in upd and upd["verify_mode"] not in VALID_VERIFY:
        raise HTTPException(status_code=400, detail="Cara verifikasi tidak valid")
    if "proof_kind" in upd and upd["proof_kind"] not in VALID_PROOF:
        raise HTTPException(status_code=400, detail="Jenis bukti tidak valid")
    if "recurrence" in upd and upd["recurrence"] not in VALID_RECURRENCE:
        raise HTTPException(status_code=400, detail="Perulangan tidak valid")
    if upd.get("assignee_rule") == "specific" and not (upd.get("assignee_email")
                                                       or jd.get("assignee_email")):
        raise HTTPException(status_code=400,
                            detail="Pilih orang tertentu untuk aturan 'Orang tertentu'.")
    if upd.get("assignee_email"):
        target = await wh.user_by_email(org, upd["assignee_email"])
        if not target:
            raise HTTPException(status_code=400, detail="Pengguna tujuan tidak ditemukan")
    upd["updated_at"] = now_iso()
    upd["updated_by"] = user.get("email")
    await db.jobdesk_templates.update_one({"org_id": org, "code": code}, {"$set": upd},
                                          upsert=True)
    return {"data": await wh.jobdesk(org, code)}


@router.post("/jobdesks/{code}/run")
async def run_jobdesk(code: str, payload: JobdeskRun,
                      user: dict = Depends(require_permission("work_tasks", "create"))):
    """Jalankan jobdesk sekarang (mis. jobdesk manual atau ad-hoc mendesak)."""
    org = _org(user)
    jd = await wh.jobdesk(org, code)
    if not jd.get("title"):
        raise HTTPException(status_code=404, detail="Jobdesk tidak ditemukan")
    _assert_supervisor(user, jd.get("division"))
    if payload.assigned_to:
        target = await wh.user_by_email(org, payload.assigned_to)
        if not target:
            raise HTTPException(status_code=400, detail="Pengguna tujuan tidak ditemukan")
        tgt_div = wh.division_of(target)
        if tgt_div != jd.get("division") and not wh.is_owner_level(user):
            raise HTTPException(status_code=400, detail=(
                f"{target.get('name')} bukan anggota divisi jobdesk ini."))
    stamp = now_iso().replace(":", "").replace(".", "")[:15]
    rows = await wh.spawn(org, code, source_event=f"manual:{code}:{stamp}",
                          description=payload.note or jd.get("description"),
                          due_date=payload.due_date, entity_type="jobdesk", entity_id=code,
                          assignee_override=payload.assigned_to,
                          assigned_by=user.get("email"),
                          meta={"assigned_by": user.get("email")})
    if not rows:
        raise HTTPException(status_code=400, detail=(
            "Tidak ada penerima yang cocok. Atur aturan penerima jobdesk atau tambahkan "
            "staf pada divisi ini."))
    for t in rows:
        await db.tasks.update_one({"id": t["id"]}, {"$set": {
            "assigned_by": user.get("email"), "auto_generated": False}})
    return {"data": serialize_doc(rows), "created": len(rows)}


# ----------------------------- papan divisi (supervisor) -----------------------------
@router.get("/board")
async def board(division: str = None,
                user: dict = Depends(require_permission("work_tasks", "view"))):
    org = _org(user)
    division = division or _my_division(user)
    if not division and wh.is_owner_level(user):
        # Direksi/Super Admin tidak berada di satu divisi: tampilkan divisi pertama
        # sebagai default agar papan tetap bisa dibuka tanpa parameter.
        division = p29.GROUPS_P29["division"]["options"][0]["value"]
    if not division:
        raise HTTPException(status_code=400, detail=(
            "Pilih divisi. Akun Anda belum ditempatkan pada divisi mana pun."))
    _assert_supervisor(user, division)
    data = await wh.division_board(org, division)
    return {"data": serialize_doc(data)}


# ----------------------------- siklus kerja task -----------------------------
@router.post("/tasks/{task_id}/start")
async def start_task(task_id: str,
                     user: dict = Depends(require_permission("work_tasks", "update"))):
    t = await _get_task(task_id, user)
    if not _can_work(t, user):
        raise HTTPException(status_code=403, detail="Akses ditolak: bukan tugas Anda.")
    if build_item_id_of(t):
        raise HTTPException(status_code=400, detail=build_task_message(t, "dimulai"))
    if t.get("status") not in ("open", "snoozed", "in_progress"):
        raise HTTPException(status_code=400,
                            detail=f"Tugas berstatus '{t.get('status')}' tidak bisa dimulai.")
    await db.tasks.update_one({"id": task_id}, {"$set": {
        "status": "in_progress", "started_at": t.get("started_at") or now_iso(),
        "review": "none", "updated_at": now_iso()}})
    return {"data": serialize_doc(await db.tasks.find_one({"id": task_id}, {"_id": 0}))}


BUILD_TASK_CODES = ("TK-10", "TK-12")


def build_item_id_of(task: dict) -> str:
    """Task ini mewakili satu STEP konstruksi? (Fase 32)"""
    return (task.get("meta") or {}).get("build_item_id")


def build_task_message(task: dict, action: str) -> str:
    """Pesan pengalihan yang MEMANDU, bukan penolakan buntu.

    Kenapa dialihkan: task pekerjaan konstruksi punya penjaga yang tidak ada pada task
    biasa — jumlah foto minimal, checklist mutu (butir KRITIS wajib lulus), penolakan foto
    daur ulang, urutan pekerjaan (pendahulu wajib terverifikasi), waktu tunggu/curing, dan
    kenaikan progres unit berbobot. Bila diselesaikan lewat jalur task generik, task akan
    tampak SELESAI padahal progres rumah tidak bergerak dan gerbang mutu terlewati.
    """
    meta = task.get("meta") or {}
    where = " ".join(x for x in [meta.get("step_code"), f"unit {meta.get('unit_code')}"
                                 if meta.get("unit_code") else None] if x)
    return (f"Pekerjaan konstruksi {where} tidak bisa {action} dari Work Hub. Buka "
            "\"Papan Mandor\" pada halaman Progres & Mutu (tombol pada tugas ini) — di "
            "sana bukti foto, checklist mutu, dan urutan pekerjaan diperiksa dulu "
            "sebelum progres rumah naik.")


def _proof_ok(kind: str, payload: TaskSubmit) -> tuple:
    if kind in (None, "none"):
        return True, None
    if kind == "photo" and not payload.photos:
        return False, "Bukti FOTO wajib dilampirkan untuk tugas ini."
    if kind == "document" and not (payload.documents or payload.photos):
        return False, "Bukti DOKUMEN wajib dilampirkan untuk tugas ini."
    if kind in ("note", "record", "wa_message") and not (payload.note or "").strip():
        return False, "Catatan hasil kerja wajib diisi (minimal apa yang Anda lakukan)."
    return True, None


@router.post("/tasks/{task_id}/submit")
async def submit_task(task_id: str, payload: TaskSubmit,
                      user: dict = Depends(require_permission("work_tasks", "update"))):
    """Ajukan hasil kerja + bukti. Verifikasi otomatis bila mesin bisa memeriksa."""
    t = await _get_task(task_id, user)
    if not _can_work(t, user):
        raise HTTPException(status_code=403, detail="Akses ditolak: bukan tugas Anda.")
    if build_item_id_of(t):
        raise HTTPException(status_code=400, detail=build_task_message(t, "diajukan"))
    if t.get("status") in ("done", "cancelled"):
        raise HTTPException(status_code=400, detail="Tugas ini sudah ditutup.")
    ok, msg = _proof_ok(t.get("proof_kind"), payload)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    ts = now_iso()
    proof = list(t.get("proof") or [])
    if payload.note:
        proof.append({"kind": "note", "value": payload.note.strip()[:1000], "at": ts})
    for f in payload.photos:
        proof.append({"kind": "photo", "value": f, "at": ts})
    for f in payload.documents:
        proof.append({"kind": "document", "value": f, "at": ts})
    if payload.amount is not None:
        proof.append({"kind": "amount", "value": payload.amount, "at": ts})
    upd = {"proof": proof, "outcome": (payload.note or t.get("outcome")),
           "submitted_at": ts, "submitted_by": user.get("email"), "updated_at": ts}
    verify = t.get("verify_mode") or "none"
    fresh = {**t, **upd}
    if verify == "system":
        auto_ok, auto_msg = await wh.auto_verify(fresh)
        if auto_ok:
            upd.update({"status": "done", "review": "approved", "completed_at": ts,
                        "completed_by": user.get("email"), "verified_by": "system",
                        "verified_at": ts, "verify_note": auto_msg})
        else:
            upd.update({"status": "submitted", "review": "pending", "verify_note": auto_msg})
    elif verify == "supervisor":
        upd.update({"status": "submitted", "review": "pending"})
    else:
        upd.update({"status": "done", "review": "approved", "completed_at": ts,
                    "completed_by": user.get("email")})
    await db.tasks.update_one({"id": task_id}, {"$set": upd})
    result = {**t, **upd}
    await wh.log_task_activity(result, f"Tugas '{t.get('title')}' diajukan"
                               + (f": {payload.note}" if payload.note else ""), user.get("email"))
    if result.get("status") == "submitted":
        await wh.notify_supervisor(
            _org(user), t.get("division"), title="Menunggu verifikasi Anda",
            body=f"{t.get('title')} — diajukan {user.get('name') or user.get('email')}",
            entity_type="task", entity_id=task_id)
    return {"data": serialize_doc(result),
            "verified": result.get("status") == "done",
            "message": upd.get("verify_note") or ("Tugas selesai." if result.get("status") == "done"
                                                  else "Diajukan, menunggu verifikasi supervisor.")}


@router.post("/tasks/{task_id}/verify")
async def verify_task(task_id: str, payload: TaskVerify,
                      user: dict = Depends(require_permission("work_tasks", "update"))):
    t = await _get_task(task_id, user)
    _assert_supervisor(user, t.get("division"))
    if build_item_id_of(t):
        raise HTTPException(status_code=400, detail=build_task_message(t, "diverifikasi"))
    if t.get("status") != "submitted":
        raise HTTPException(status_code=400, detail="Hanya tugas yang diajukan bisa diverifikasi.")
    ts = now_iso()
    await db.tasks.update_one({"id": task_id}, {"$set": {
        "status": "done", "review": "approved", "verified_by": user.get("email"),
        "verified_at": ts, "verify_note": payload.note, "completed_at": ts,
        "completed_by": t.get("submitted_by") or t.get("assigned_to"), "updated_at": ts}})
    await create_notification(
        user_email=t.get("assigned_to"), title="Tugas Anda disetujui",
        body=f"{t.get('title')} diverifikasi {user.get('name') or user.get('email')}",
        type="task", related_entity_type=t.get("related_entity_type"),
        related_entity_id=t.get("related_entity_id"), org_id=_org(user))
    await wh.log_task_activity(t, f"Tugas '{t.get('title')}' diverifikasi supervisor.",
                               user.get("email"))
    return {"data": serialize_doc(await db.tasks.find_one({"id": task_id}, {"_id": 0}))}


@router.post("/tasks/{task_id}/reject")
async def reject_task(task_id: str, payload: TaskReject,
                      user: dict = Depends(require_permission("work_tasks", "update"))):
    t = await _get_task(task_id, user)
    _assert_supervisor(user, t.get("division"))
    if build_item_id_of(t):
        raise HTTPException(status_code=400, detail=build_task_message(t, "dikembalikan"))
    if t.get("status") != "submitted":
        raise HTTPException(status_code=400, detail="Hanya tugas yang diajukan bisa dikembalikan.")
    ts = now_iso()
    await db.tasks.update_one({"id": task_id}, {"$set": {
        "status": "in_progress", "review": "rejected", "rejected_reason": payload.reason,
        "rejected_by": user.get("email"), "rejected_at": ts, "updated_at": ts}})
    await create_notification(
        user_email=t.get("assigned_to"), title="Tugas dikembalikan untuk diperbaiki",
        body=f"{t.get('title')}: {payload.reason}", type="task",
        related_entity_type=t.get("related_entity_type"),
        related_entity_id=t.get("related_entity_id"), org_id=_org(user))
    return {"data": serialize_doc(await db.tasks.find_one({"id": task_id}, {"_id": 0}))}


@router.post("/tasks/{task_id}/assign")
async def assign_task(task_id: str, payload: TaskAssign,
                      user: dict = Depends(require_permission("work_tasks", "update"))):
    """Supervisor menugaskan/mengalihkan tugas ke staf di divisinya."""
    org = _org(user)
    t = await _get_task(task_id, user)
    _assert_supervisor(user, t.get("division"))
    target = await wh.user_by_email(org, payload.assigned_to)
    if not target:
        raise HTTPException(status_code=400, detail="Pengguna tujuan tidak ditemukan")
    tgt_div = wh.division_of(target)
    if t.get("division") and tgt_div and tgt_div != t.get("division") and not wh.is_owner_level(user):
        raise HTTPException(status_code=400, detail=(
            f"{target.get('name')} berada di divisi lain ({p29.DIVISION_LABEL.get(tgt_div, tgt_div)})."))
    ts = now_iso()
    upd = {"assigned_to": payload.assigned_to, "assigned_by": user.get("email"),
           "assigned_at": ts, "updated_at": ts}
    if payload.due_date:
        upd["due_date"] = payload.due_date
        upd["sla_due_at"] = payload.due_date
        upd["sla_breached"] = False
    if payload.priority:
        upd["priority"] = payload.priority
    if t.get("status") == "submitted":
        upd["status"] = "in_progress"
        upd["review"] = "none"
    await db.tasks.update_one({"id": task_id}, {"$set": upd})
    await create_notification(
        user_email=payload.assigned_to, title=f"Tugas ditugaskan: {t.get('title')}",
        body=payload.note or f"Dari {user.get('name') or user.get('email')}", type="task",
        related_entity_type=t.get("related_entity_type"),
        related_entity_id=t.get("related_entity_id"), org_id=org)
    await add_activity(entity_type="task", entity_id=task_id, type="system",
                       body=f"Tugas dialihkan ke {target.get('name')}"
                            + (f": {payload.note}" if payload.note else ""),
                       actor=user.get("email"), org_id=org)
    return {"data": serialize_doc(await db.tasks.find_one({"id": task_id}, {"_id": 0}))}


async def _related_info(t: dict, org: str):
    """Rangkum record terkait tugas (nama + tautan) agar detail sheet bisa menampilkannya."""
    rtype, rid = t.get("related_entity_type"), t.get("related_entity_id")
    if not rtype or not rid:
        return None
    cfg = {
        "lead": (db.leads, "Lead", f"/leads/{rid}",
                 lambda r: f"{r.get('name') or rid}{' — ' + r['phone'] if r.get('phone') else ''}"),
        "deal": (db.deals, "Deal / Booking", "/deals",
                 lambda r: f"{r.get('lead_name') or 'Deal'}"
                           f"{' — Rp ' + format(int(r['price']), ',').replace(',', '.') if r.get('price') else ''}"),
        "unit": (db.units, "Unit", f"/units/{rid}",
                 lambda r: f"{r.get('code') or r.get('no') or rid}"
                           f"{' — Blok ' + r['block'] if r.get('block') else ''}"),
        "customer": (db.customers, "Customer", f"/customers/{rid}",
                     lambda r: f"{r.get('name') or rid}{' — ' + r['email'] if r.get('email') else ''}"),
        "project": (db.projects, "Proyek", f"/projects/{rid}",
                    lambda r: f"{r.get('name') or rid}{' (' + r['code'] + ')' if r.get('code') else ''}"),
    }.get(rtype)
    if not cfg:
        return {"type": rtype, "id": rid, "label": rtype, "name": rid, "link": None}
    coll, label, link, to_name = cfg
    r = await coll.find_one({"id": rid, "org_id": org}, {"_id": 0})
    if not r:
        return {"type": rtype, "id": rid, "label": label,
                "name": "(record tidak ditemukan)", "link": None}
    return {"type": rtype, "id": rid, "label": label, "name": to_name(r), "link": link}


@router.get("/tasks/{task_id}")
async def task_detail(task_id: str,
                      user: dict = Depends(require_permission("work_tasks", "view"))):
    t = await _get_task(task_id, user)
    jd = await wh.jobdesk(_org(user), t.get("jobdesk_code")) if t.get("jobdesk_code") else None
    acts = await db.activities.find({"entity_type": "task", "entity_id": task_id},
                                   {"_id": 0}).sort("created_at", -1).to_list(50)
    return {"data": {"task": serialize_doc(t), "jobdesk": jd,
                     "related": await _related_info(t, _org(user)),
                     "activities": serialize_doc(acts),
                     "can_work": _can_work(t, user),
                     "can_verify": wh.is_supervisor(user) and (
                         wh.is_owner_level(user) or t.get("division") == _my_division(user))}}


# ----------------------------- Fase 29d — Rapor mingguan & papan kanban -----------------------------
@router.get("/report")
async def division_report(division: str = None, week: str = None,
                          user: dict = Depends(require_permission("work_tasks", "view"))):
    """Rapor mingguan divisi: ketepatan waktu + bukti kerja per staf (supervisor/owner)."""
    import workhub_report as wr
    org = _org(user)
    division = division or _my_division(user)
    if not division and wh.is_owner_level(user):
        division = p29.GROUPS_P29["division"]["options"][0]["value"]
    if not division:
        raise HTTPException(status_code=400, detail="Pilih divisi terlebih dahulu.")
    _assert_supervisor(user, division)
    return {"data": serialize_doc(await wr.weekly_report(org, division, week))}


@router.get("/kanban")
async def division_kanban(division: str = None, assignee: str = None,
                          user: dict = Depends(require_permission("work_tasks", "view"))):
    """Papan tugas per status. Staf otomatis dibatasi pada tugasnya sendiri."""
    import workhub_report as wr
    org = _org(user)
    division = division or _my_division(user)
    if not division and wh.is_owner_level(user):
        division = p29.GROUPS_P29["division"]["options"][0]["value"]
    if not division:
        raise HTTPException(status_code=400, detail="Akun Anda belum ditempatkan pada divisi.")
    if not wh.is_supervisor(user):
        assignee = user.get("email")          # staf: hanya papan miliknya
    elif not wh.is_owner_level(user) and division != _my_division(user):
        raise HTTPException(status_code=403, detail="Akses ditolak: bukan divisi Anda.")
    return {"data": serialize_doc(await wr.kanban(org, division, assignee))}
