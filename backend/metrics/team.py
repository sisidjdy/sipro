"""metrics/team.py — kamus metrik KINERJA TIM (USR-01..07), spec Dok 31 §6.

Permintaan pemilik: "laporan harian per user". Yang dihitung di sini SELALU dari jejak nyata
(`activities`, `tasks`, `messages`, `leads.stage_history`), sehingga tidak ada user yang bisa
terlihat rajin karena angka diketik. Jika sebuah jejak memang belum direkam sistem (mis.
panggilan telepon), metriknya mengaku — bukan menampilkan 0 yang bisa dibaca sebagai
"orang ini tidak bekerja".
"""
from datetime import datetime, timezone

from db import ORG_ID, db
from metrics.base import day_range_query, date_of, median, pct, result

OPEN_TASK_STATUS = ("open", "in_progress", "waiting", "todo")
DONE_TASK_STATUS = ("done", "completed", "verified")


async def _users(org_id: str) -> dict:
    rows = await db.users.find({"org_id": org_id},
                               {"_id": 0, "email": 1, "name": 1, "role": 1}).to_list(500)
    return {u["email"]: u for u in rows}


# ---------------------------------------------------------------------- USR-01
async def daily_activity(*, org_id: str = ORG_ID, date_from: str = None, date_to: str = None,
                         owner_email: str = None, **_) -> dict:
    """Aktivitas harian per user = jumlah jejak aktivitas + tugas selesai per hari.

    Sumbernya `activities` (catatan kolaborasi & sistem) dan `tasks` (pekerjaan selesai).
    Counter yang belum punya jejak (mis. `calls_logged`) TIDAK dibuat-buat.
    """
    q = {"org_id": org_id, **day_range_query("created_at", date_from, date_to)}
    if owner_email:
        q["actor"] = owner_email
    acts = await db.activities.find(q, {"_id": 0, "actor": 1, "type": 1,
                                        "created_at": 1}).to_list(50000)
    tq = {"org_id": org_id, "status": {"$in": list(DONE_TASK_STATUS)},
          **day_range_query("updated_at", date_from, date_to)}
    if owner_email:
        tq["assigned_to"] = owner_email
    tasks = await db.tasks.find(tq, {"_id": 0, "assigned_to": 1, "updated_at": 1}).to_list(50000)
    users = await _users(org_id)
    per_user, per_day = {}, {}
    for act in acts:
        key = act.get("actor") or "(sistem)"
        row = per_user.setdefault(key, {"key": key, "label": (users.get(key) or {}).get("name")
                                        or key, "value": 0, "activities": 0, "tasks_done": 0})
        row["value"] += 1
        row["activities"] += 1
        day = date_of(act.get("created_at"))
        per_day[day] = per_day.get(day, 0) + 1
    for task in tasks:
        key = task.get("assigned_to") or "(tanpa penugasan)"
        row = per_user.setdefault(key, {"key": key, "label": (users.get(key) or {}).get("name")
                                        or key, "value": 0, "activities": 0, "tasks_done": 0})
        row["value"] += 1
        row["tasks_done"] += 1
    return result("USR-01", len(acts) + len(tasks), label="Jejak aktivitas tim", unit="count",
                  breakdown=sorted(per_user.values(), key=lambda r: -r["value"]),
                  series=[{"bucket": d, "value": v} for d, v in sorted(per_day.items()) if d],
                  inputs={"aktivitas": len(acts), "tugas_selesai": len(tasks),
                          "user_aktif": len(per_user)},
                  # Catatan, BUKAN `missing`: jumlah jejak yang ADA tetap sah dihitung. Yang
                  # perlu diketahui pembaca adalah batas cakupannya — panggilan telepon belum
                  # punya jejak di sistem, jadi angka ini bukan "seluruh pekerjaan tim".
                  note="Panggilan telepon belum punya jejak di sistem, jadi angka ini hanya "
                       "mencakup aktivitas & tugas yang tercatat.",
                  drill="/tasks?tab=tasks&scope=all")


# ---------------------------------------------------------------------- USR-02
async def on_time_rate(*, org_id: str = ORG_ID, date_from: str = None, date_to: str = None,
                       owner_email: str = None, **_) -> dict:
    """Ketepatan waktu = `tugas selesai sebelum tenggat / total tugas selesai`."""
    q = {"org_id": org_id, "status": {"$in": list(DONE_TASK_STATUS)},
         **day_range_query("updated_at", date_from, date_to)}
    if owner_email:
        q["assigned_to"] = owner_email
    tasks = await db.tasks.find(q, {"_id": 0, "assigned_to": 1, "due_date": 1,
                                    "updated_at": 1, "sla_breached": 1}).to_list(50000)
    users = await _users(org_id)
    per_user, tanpa_tenggat, tepat = {}, 0, 0
    for task in tasks:
        key = task.get("assigned_to") or "(tanpa penugasan)"
        row = per_user.setdefault(key, {"key": key, "label": (users.get(key) or {}).get("name")
                                        or key, "done": 0, "on_time": 0, "value": None})
        row["done"] += 1
        due, finished = task.get("due_date"), task.get("updated_at")
        if not due:
            tanpa_tenggat += 1
            continue
        if finished and finished <= due:
            row["on_time"] += 1
            tepat += 1
    for row in per_user.values():
        row["value"] = pct(row["on_time"], row["done"])
    dinilai = len(tasks) - tanpa_tenggat
    return result("USR-02", pct(tepat, dinilai), label="Ketepatan waktu tugas", unit="pct",
                  breakdown=sorted(per_user.values(), key=lambda r: -(r["value"] or 0)),
                  inputs={"tugas_selesai": len(tasks), "dinilai": dinilai, "tepat": tepat},
                  coverage={"rows": dinilai, "total": len(tasks)} if tanpa_tenggat else None,
                  missing=[f"{tanpa_tenggat} tugas selesai tanpa tenggat (tidak bisa dinilai)"]
                  if tanpa_tenggat else None,
                  drill="/tasks?tab=tasks&scope=all")


# ---------------------------------------------------------------------- USR-03
async def pipeline_contribution(*, org_id: str = ORG_ID, date_from: str = None,
                                date_to: str = None, **_) -> dict:
    """Kontribusi pipeline per user = lead ditangani → booking → nilai deal."""
    leads = await db.leads.find({"org_id": org_id, **day_range_query("created_at", date_from,
                                                                     date_to)},
                                {"_id": 0, "assigned_to": 1, "stage": 1, "id": 1}).to_list(50000)
    deals = await db.deals.find({"org_id": org_id, "status": {"$in": ["booked", "completed"]}},
                                {"_id": 0, "assigned_to": 1, "price": 1}).to_list(20000)
    users = await _users(org_id)
    per_user = {}
    for lead in leads:
        key = lead.get("assigned_to") or "(belum ditugaskan)"
        row = per_user.setdefault(key, {"key": key, "label": (users.get(key) or {}).get("name")
                                        or key, "value": 0, "leads": 0, "booking": 0,
                                        "nilai": 0})
        row["leads"] += 1
        row["value"] += 1
        if lead.get("stage") in ("booking", "won"):
            row["booking"] += 1
    for deal in deals:
        key = deal.get("assigned_to") or "(belum ditugaskan)"
        row = per_user.setdefault(key, {"key": key, "label": (users.get(key) or {}).get("name")
                                        or key, "value": 0, "leads": 0, "booking": 0,
                                        "nilai": 0})
        row["nilai"] += int(deal.get("price") or 0)
    return result("USR-03", len(per_user), label="Kontribusi pipeline per user", unit="count",
                  breakdown=sorted(per_user.values(), key=lambda r: -r["nilai"]),
                  inputs={"lead": len(leads), "deal": len(deals)},
                  missing=["belum ada lead pada periode ini"] if not leads else None,
                  drill="/leads")


# ---------------------------------------------------------------------- USR-04
async def response_time(*, org_id: str = ORG_ID, date_from: str = None, date_to: str = None,
                        **_) -> dict:
    """Waktu respons per user = median selisih waktu pesan masuk → balasan keluar."""
    convs = await db.conversations.find({"org_id": org_id},
                                        {"_id": 0, "id": 1, "owner": 1}).to_list(20000)
    owners = {c["id"]: c.get("owner") for c in convs}
    msgs = await db.messages.find({"org_id": org_id, **day_range_query("created_at", date_from,
                                                                       date_to)},
                                  {"_id": 0, "conversation_id": 1, "direction": 1,
                                   "created_at": 1}).to_list(50000)
    per_conv = {}
    for m in msgs:
        per_conv.setdefault(m.get("conversation_id"), []).append(m)
    per_user, samples = {}, []
    for conv_id, rows in per_conv.items():
        rows.sort(key=lambda m: m.get("created_at") or "")
        pending = None
        for m in rows:
            if m.get("direction") == "in":
                pending = m.get("created_at")
            elif pending and m.get("direction") == "out":
                minutes = (datetime.fromisoformat(m["created_at"])
                           - datetime.fromisoformat(pending)).total_seconds() / 60
                key = owners.get(conv_id) or "(tanpa pemilik)"
                per_user.setdefault(key, []).append(round(minutes, 1))
                samples.append(round(minutes, 1))
                pending = None
    breakdown = [{"key": k, "label": k, "value": median(v), "count": len(v)}
                 for k, v in per_user.items()]
    return result("USR-04", median(samples), label="Waktu respons WA (median menit)",
                  unit="count", breakdown=sorted(breakdown, key=lambda r: r["value"] or 0),
                  inputs={"pesan": len(msgs), "pasangan_balasan": len(samples),
                          "percakapan": len(per_conv)},
                  coverage={"rows": len(samples), "total": len(msgs)} if samples else None,
                  missing=["belum ada pasangan pesan masuk→balasan pada periode ini"]
                  if not samples else None,
                  drill="/inbox")


# ---------------------------------------------------------------------- USR-05
async def workload(*, org_id: str = ORG_ID, **_) -> dict:
    """Beban kerja = tugas aktif + lead aktif per user (deteksi kelebihan beban)."""
    tasks = await db.tasks.find({"org_id": org_id, "status": {"$in": list(OPEN_TASK_STATUS)}},
                                {"_id": 0, "assigned_to": 1}).to_list(50000)
    leads = await db.leads.find({"org_id": org_id, "stage": {"$nin": ["won", "lost"]}},
                                {"_id": 0, "assigned_to": 1}).to_list(50000)
    users = await _users(org_id)
    per_user = {}
    for row_src, field in ((tasks, "tugas"), (leads, "lead")):
        for row in row_src:
            key = row.get("assigned_to") or "(tanpa penugasan)"
            entry = per_user.setdefault(key, {"key": key,
                                              "label": (users.get(key) or {}).get("name") or key,
                                              "value": 0, "tugas": 0, "lead": 0})
            entry[field] += 1
            entry["value"] += 1
    rata = round(sum(r["value"] for r in per_user.values()) / len(per_user), 1) \
        if per_user else None
    return result("USR-05", rata, label="Beban kerja aktif rata-rata", unit="count",
                  breakdown=sorted(per_user.values(), key=lambda r: -r["value"]),
                  inputs={"tugas_aktif": len(tasks), "lead_aktif": len(leads)},
                  missing=["belum ada tugas/lead aktif"] if not per_user else None,
                  drill="/tasks?tab=tasks&scope=all")


# ---------------------------------------------------------------------- USR-06
async def work_evidence(*, org_id: str = ORG_ID, date_from: str = None, date_to: str = None,
                        **_) -> dict:
    """Bukti kerja = pangsa tugas selesai yang melampirkan bukti (`proof`)."""
    q = {"org_id": org_id, "status": {"$in": list(DONE_TASK_STATUS)},
         **day_range_query("updated_at", date_from, date_to)}
    tasks = await db.tasks.find(q, {"_id": 0, "assigned_to": 1, "proof": 1,
                                    "verify_mode": 1}).to_list(50000)
    users = await _users(org_id)
    per_user, berbukti = {}, 0
    for task in tasks:
        key = task.get("assigned_to") or "(tanpa penugasan)"
        row = per_user.setdefault(key, {"key": key, "label": (users.get(key) or {}).get("name")
                                        or key, "done": 0, "with_proof": 0, "value": None})
        row["done"] += 1
        if task.get("proof"):
            row["with_proof"] += 1
            berbukti += 1
    for row in per_user.values():
        row["value"] = pct(row["with_proof"], row["done"])
    return result("USR-06", pct(berbukti, len(tasks)), label="Tugas selesai berbukti",
                  unit="pct", breakdown=sorted(per_user.values(),
                                               key=lambda r: -(r["value"] or 0)),
                  inputs={"tugas_selesai": len(tasks), "berbukti": berbukti},
                  missing=["belum ada tugas selesai pada periode ini"] if not tasks else None,
                  drill="/tasks?tab=tasks&scope=all")


# ---------------------------------------------------------------------- USR-07
async def stage_actors(*, org_id: str = ORG_ID, date_from: str = None, date_to: str = None,
                       **_) -> dict:
    """Jejak siapa mengerjakan tahap = `stage_history.actor` per tahap (permintaan pemilik)."""
    leads = await db.leads.find({"org_id": org_id, **day_range_query("created_at", date_from,
                                                                     date_to)},
                                {"_id": 0, "stage_history": 1}).to_list(50000)
    per_actor, transisi, tanpa_aktor = {}, 0, 0
    for lead in leads:
        for entry in lead.get("stage_history") or []:
            transisi += 1
            actor = entry.get("actor") or entry.get("by")
            if not actor:
                tanpa_aktor += 1
                continue
            row = per_actor.setdefault(actor, {"key": actor, "label": actor, "value": 0,
                                              "tahap": {}})
            row["value"] += 1
            stage = entry.get("to") or "?"
            row["tahap"][stage] = row["tahap"].get(stage, 0) + 1
    return result("USR-07", transisi, label="Perpindahan tahap tercatat", unit="count",
                  breakdown=sorted(per_actor.values(), key=lambda r: -r["value"]),
                  inputs={"lead": len(leads), "transisi": transisi},
                  coverage={"rows": transisi - tanpa_aktor, "total": transisi}
                  if tanpa_aktor else None,
                  missing=[f"{tanpa_aktor} perpindahan tahap tanpa nama pelaku"]
                  if tanpa_aktor else
                  (["belum ada perpindahan tahap tercatat"] if not transisi else None),
                  drill="/leads")


METRICS = {
    "USR-01": {"fn": daily_activity, "label": "Jejak aktivitas tim", "unit": "count",
               "persona": "tim", "snapshot": True,
               "formula": "count(activities) + count(tugas selesai) per user & hari",
               "requires": ["activities", "tasks"], "drill": "/tasks?tab=tasks&scope=all"},
    "USR-02": {"fn": on_time_rate, "label": "Ketepatan waktu tugas", "unit": "pct",
               "persona": "tim", "snapshot": True,
               "formula": "tugas selesai ≤ tenggat / tugas selesai bertenggat",
               "requires": ["tasks"], "drill": "/tasks?tab=tasks&scope=all"},
    "USR-03": {"fn": pipeline_contribution, "label": "Kontribusi pipeline per user",
               "unit": "count", "persona": "tim",
               "formula": "lead ditangani → booking → Σ nilai deal per user",
               "requires": ["leads", "deals"], "drill": "/leads"},
    "USR-04": {"fn": response_time, "label": "Waktu respons WA (median menit)", "unit": "count",
               "persona": "tim", "formula": "median(waktu balas) dari pasangan pesan in→out",
               "requires": ["messages", "conversations"], "drill": "/inbox"},
    "USR-05": {"fn": workload, "label": "Beban kerja aktif rata-rata", "unit": "count",
               "persona": "tim", "snapshot": True,
               "formula": "(tugas aktif + lead aktif) / jumlah user aktif",
               "requires": ["tasks", "leads"], "drill": "/tasks?tab=tasks&scope=all"},
    "USR-06": {"fn": work_evidence, "label": "Tugas selesai berbukti", "unit": "pct",
               "persona": "tim", "snapshot": True,
               "formula": "tugas selesai dengan lampiran bukti / tugas selesai",
               "requires": ["tasks.proof"], "drill": "/tasks?tab=tasks&scope=all"},
    "USR-07": {"fn": stage_actors, "label": "Perpindahan tahap tercatat", "unit": "count",
               "persona": "tim", "formula": "count(stage_history) per pelaku & tahap",
               "requires": ["leads.stage_history"], "drill": "/leads"},
}
