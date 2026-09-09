"""RAPOR MINGGUAN DIVISI + PAPAN KANBAN (Fase 29d).

Kenapa perlu? Papan divisi menjawab "apa yang sedang berjalan", tetapi supervisor juga perlu
menjawab dua hal lain: **"siapa tepat waktu"** dan **"apa buktinya"** — tanpa harus membuka
tugas satu per satu. Rapor dihitung dari data yang sudah ada (tanggal jatuh tempo vs waktu
selesai, hasil verifikasi, dan lampiran bukti), jadi angkanya tidak bisa "dikarang".

Definisi yang dipakai (jujur & konsisten):
  * **Selesai tepat waktu** = `completed_at <= due_date`
  * **Selesai terlambat**   = `completed_at > due_date`
  * **Dikembalikan**        = pernah `review = rejected` (butuh perbaikan)
  * **Bukti**               = jumlah lampiran pada `proof[]` (catatan/foto/dokumen)
  * **Ketepatan waktu (%)** = tepat waktu / total selesai pada periode
"""
import logging

from core_utils import new_id, now_iso, serialize_doc
from db import db, ORG_ID
from engine import create_notification
from workhub import ACTIVE_STATES, OPEN_STATES, division_members, level_of, period_key

logger = logging.getLogger("sipro.workhub.report")

KANBAN_COLUMNS = [
    {"key": "open", "label": "Belum dimulai"},
    {"key": "in_progress", "label": "Dikerjakan"},
    {"key": "submitted", "label": "Menunggu verifikasi"},
    {"key": "done", "label": "Selesai (7 hari terakhir)"},
]


def _week_bounds(week: str) -> tuple:
    """Awal/akhir ISO week ('2026-W33') sebagai ISO-8601 string."""
    from datetime import datetime, timedelta, timezone
    year, wk = week.split("-W")
    monday = datetime.fromisocalendar(int(year), int(wk), 1).replace(tzinfo=timezone.utc)
    return monday.isoformat(), (monday + timedelta(days=7)).isoformat()


def shift_week(week: str, delta: int) -> str:
    from datetime import datetime, timedelta, timezone
    year, wk = week.split("-W")
    monday = datetime.fromisocalendar(int(year), int(wk), 1).replace(tzinfo=timezone.utc)
    return period_key("weekly", monday + timedelta(days=7 * delta))


async def weekly_report(org: str, division: str, week: str = None) -> dict:
    """Rapor satu divisi untuk satu pekan: ketepatan waktu + bukti kerja per staf."""
    week = week or period_key("weekly")
    start, end = _week_bounds(week)
    members = await division_members(org, division)
    rows = await db.tasks.find(
        {"org_id": org, "division": division,
         "$or": [{"completed_at": {"$gte": start, "$lt": end}},
                 {"created_at": {"$gte": start, "$lt": end}},
                 {"status": {"$in": OPEN_STATES}}]}, {"_id": 0}).to_list(3000)
    now_s = now_iso()
    per, totals = [], {"done": 0, "on_time": 0, "late": 0, "returned": 0, "evidence": 0,
                       "open": 0, "overdue": 0, "submitted": 0, "created": 0}
    for m in members:
        mine = [t for t in rows if t.get("assigned_to") == m["email"]]
        done = [t for t in mine if t.get("status") == "done"
                and start <= str(t.get("completed_at") or "") < end]
        on_time = [t for t in done if not t.get("due_date")
                   or str(t.get("completed_at") or "") <= str(t["due_date"])]
        late = [t for t in done if t not in on_time]
        openq = [t for t in mine if t.get("status") in ACTIVE_STATES]
        overdue = [t for t in openq if (t.get("due_date") or "9") < now_s]
        submitted = [t for t in mine if t.get("status") == "submitted"]
        returned = [t for t in mine if t.get("rejected_reason")]
        created = [t for t in mine if start <= str(t.get("created_at") or "") < end]
        evidence = sum(len(t.get("proof") or []) for t in done)
        samples = []
        for t in done[:6]:
            note = next((p.get("value") for p in (t.get("proof") or [])
                         if p.get("kind") == "note"), None)
            photos = [p.get("value") for p in (t.get("proof") or []) if p.get("kind") == "photo"]
            samples.append({"task_id": t["id"], "title": t.get("title"),
                            "jobdesk_code": t.get("jobdesk_code"),
                            "completed_at": t.get("completed_at"), "note": note,
                            "photos": photos[:3],
                            "verified_by": t.get("verified_by"),
                            "on_time": t in on_time})
        rate = round(len(on_time) / len(done) * 100) if done else None
        per.append({
            "email": m["email"], "name": m.get("name"), "role": m.get("role"),
            "level": level_of(m), "created": len(created), "done": len(done),
            "on_time": len(on_time), "late": len(late), "returned": len(returned),
            "open": len(openq), "overdue": len(overdue), "submitted": len(submitted),
            "evidence": evidence, "on_time_rate": rate, "samples": samples,
        })
        for k, v in (("done", len(done)), ("on_time", len(on_time)), ("late", len(late)),
                     ("returned", len(returned)), ("evidence", evidence),
                     ("open", len(openq)), ("overdue", len(overdue)),
                     ("submitted", len(submitted)), ("created", len(created))):
            totals[k] += v
    per.sort(key=lambda r: (-(r["on_time_rate"] if r["on_time_rate"] is not None else -1),
                            -r["done"], r["name"] or ""))
    totals["on_time_rate"] = (round(totals["on_time"] / totals["done"] * 100)
                              if totals["done"] else None)
    # Ringkasan per jobdesk (pekerjaan mana yang paling sering terlambat)
    jd = {}
    for t in rows:
        code = t.get("jobdesk_code")
        if not code:
            continue
        import jobdesk_catalog as cat
        j = jd.setdefault(code, {"code": code,
                                 "title": (cat.BY_CODE.get(code) or {}).get("title")
                                 or t.get("title"), "done": 0, "late": 0, "open": 0})
        if t.get("status") == "done" and start <= str(t.get("completed_at") or "") < end:
            j["done"] += 1
            if t.get("due_date") and str(t.get("completed_at") or "") > str(t["due_date"]):
                j["late"] += 1
        elif t.get("status") in ACTIVE_STATES:
            j["open"] += 1
    return {"week": week, "division": division, "start": start, "end": end,
            "prev_week": shift_week(week, -1), "next_week": shift_week(week, 1),
            "totals": totals, "members": per,
            "jobdesks": sorted(jd.values(), key=lambda x: (-x["late"], -x["done"]))[:10]}


async def kanban(org: str, division: str, assignee: str = None) -> dict:
    """Papan tugas divisi per status (tanpa geser-tarik: perpindahan tetap lewat aksi resmi)."""
    from core_utils import due_in
    q = {"org_id": org, "division": division}
    if assignee:
        q["assigned_to"] = assignee
    rows = await db.tasks.find(
        {**q, "$or": [{"status": {"$in": OPEN_STATES}},
                      {"status": "done", "completed_at": {"$gte": due_in(days=-7)}}]},
        {"_id": 0}).sort("due_date", 1).to_list(1000)
    now_s = now_iso()
    cols = []
    for c in KANBAN_COLUMNS:
        items = [t for t in rows if (t.get("status") == c["key"]
                                    or (c["key"] == "open" and t.get("status") == "snoozed"))]
        cols.append({"key": c["key"], "label": c["label"], "count": len(items),
                     "overdue": sum(1 for t in items if (t.get("due_date") or "9") < now_s
                                    and t.get("status") != "done"),
                     "tasks": serialize_doc(items[:40])})
    return {"division": division, "columns": cols, "total": len(rows)}


async def report_tick() -> int:
    """Snapshot rapor mingguan + kirim ke supervisor (idempoten per divisi per pekan)."""
    made = 0
    week = period_key("weekly")
    divisions = await db.tasks.distinct("division", {"division": {"$nin": [None, ""]}})
    for division in divisions:
        orgs = await db.tasks.distinct("org_id", {"division": division})
        for org in orgs:
            exists = await db.workhub_reports.find_one(
                {"org_id": org, "division": division, "week": week}, {"_id": 0, "id": 1})
            if exists:
                continue
            rep = await weekly_report(org, division, week)
            await db.workhub_reports.insert_one({
                "id": new_id(), "org_id": org, "division": division, "week": week,
                "totals": rep["totals"], "created_at": now_iso()})
            sup = await division_members(org, division, level="supervisor")
            rate = rep["totals"].get("on_time_rate")
            for s in sup:
                await create_notification(
                    user_email=s["email"], title=f"Rapor divisi pekan {week} siap",
                    body=(f"{rep['totals']['done']} tugas selesai · ketepatan waktu "
                          f"{rate if rate is not None else '—'}% · {rep['totals']['overdue']} "
                          f"terlambat berjalan · {rep['totals']['evidence']} bukti kerja"),
                    type="info", org_id=org)
            made += 1
    return made
