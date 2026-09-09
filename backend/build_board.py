"""PAPAN MANDOR — "kerja hari ini" (Fase 32).

Permintaan owner: "Beri pelaksana satu layar 'kerja hari ini' yang enak dipakai dari HP,
foto langsung dari lokasi".

Prinsip yang dipegang:
  * Yang tampil hanya pekerjaan yang MEMANG boleh dikerjakan orang tersebut. Urutan
    dijaga: step yang pendahulunya belum diverifikasi TIDAK menjadi pekerjaan aktif,
    tetapi tetap tampil sebagai INSTRUKSI MENUNGGU beserta alasan terkunci & perkiraan
    tanggal terbuka — mandor tahu apa berikutnya tanpa bisa melangkahi urutan.
  * Tidak ada mesin task baru: kartu di sini menunjuk task Work Hub yang sudah ada
    (`tasks.meta.build_item_id`), dan pengajuan hasil tetap lewat endpoint `/build`
    agar seluruh gerbang mutu (foto minimal, checklist KRITIS, anti foto daur ulang,
    pemisahan tugas) tetap berlaku.
"""
from datetime import date

import build_instruction as bi
import build_policy as bp
from core_utils import today_iso_date
from db import db

SUPERVISOR_ROLES = ("owner", "super_admin", "project_manager")
WORKABLE = ("ready", "in_progress", "rework")
OPEN_TASK_STATES = ["open", "in_progress", "snoozed", "submitted"]


def _days_late(planned_finish: str, ref: str) -> int:
    pf = str(planned_finish or "")[:10]
    if not pf or pf >= ref:
        return 0
    return (date.fromisoformat(ref) - date.fromisoformat(pf)).days


async def _tasks_for(org: str, item_ids: list) -> dict:
    """Peta item → task Work Hub aktif (agar kartu papan bisa menunjuk task nyata)."""
    if not item_ids:
        return {}
    rows = await db.tasks.find(
        {"org_id": org, "meta.build_item_id": {"$in": item_ids},
         "status": {"$in": OPEN_TASK_STATES}},
        {"_id": 0, "id": 1, "status": 1, "due_date": 1, "jobdesk_code": 1,
         "meta": 1}).to_list(600)
    out = {}
    for r in rows:
        key = (r.get("meta") or {}).get("build_item_id")
        if key:
            out[key] = r
    return out


def _row(item: dict, ref: str, tmap: dict) -> dict:
    row = bi.brief(item)
    row["days_late"] = _days_late(item.get("planned_finish"), ref)
    t = tmap.get(item["id"]) or {}
    row["task_id"] = t.get("id") or item.get("task_id")
    row["task_status"] = t.get("status")
    row["task_due"] = t.get("due_date")
    row["jobdesk_code"] = t.get("jobdesk_code")
    return row


async def today(org: str, user: dict, project_id: str = None) -> dict:
    """Kelompok pekerjaan untuk SATU orang pada hari ini (mobile-first)."""
    email = user.get("email")
    role = user.get("role")
    is_sup = role in SUPERVISOR_ROLES
    ref = today_iso_date()
    base = {"org_id": org}
    if project_id:
        base["project_id"] = project_id

    mine = await db.build_items.find(
        {**base, "assigned_to": email, "status": {"$in": list(WORKABLE)}},
        {"_id": 0}).sort("planned_finish", 1).to_list(300)
    submitted_mine = await db.build_items.find(
        {**base, "submitted_by": email, "status": "submitted"},
        {"_id": 0}).sort("submitted_at", -1).to_list(100)
    verify_q = {**base, "status": "submitted"}
    if not is_sup:
        verify_q["verifier_hint"] = email
    queue = await db.build_items.find(verify_q, {"_id": 0}).sort(
        "submitted_at", 1).to_list(200)
    blocked = await db.build_items.find(
        {**base, "assigned_to": email, "status": "blocked"},
        {"_id": 0}).sort("order", 1).to_list(12)

    ids = [i["id"] for i in mine + submitted_mine + queue + blocked]
    tmap = await _tasks_for(org, ids)

    groups = {"overdue": [], "today": [], "in_progress": [], "rework": [],
              "scheduled_later": [], "awaiting_verification": [], "to_verify": [],
              "upcoming": []}
    for it in mine:
        row = _row(it, ref, tmap)
        if row["days_late"]:
            groups["overdue"].append(row)
        elif it.get("status") == "rework":
            groups["rework"].append(row)
        elif it.get("status") == "in_progress":
            groups["in_progress"].append(row)
        elif str(it.get("planned_start") or "")[:10] <= ref:
            groups["today"].append(row)
        else:
            groups["scheduled_later"].append(row)
    groups["awaiting_verification"] = [_row(i, ref, tmap) for i in submitted_mine]
    groups["to_verify"] = [_row(i, ref, tmap) for i in queue
                           if i.get("submitted_by") != email]
    groups["upcoming"] = [_row(i, ref, tmap) for i in blocked]

    counts = {k: len(v) for k, v in groups.items()}
    counts["actionable"] = (len(groups["overdue"]) + len(groups["today"])
                            + len(groups["in_progress"]) + len(groups["rework"]))
    return {
        "as_of": ref, "me": email, "role": role, "is_supervisor": is_sup,
        "counts": counts, "groups": groups, "policy": await bp.get_policy(org),
    }
