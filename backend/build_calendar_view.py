"""KALENDER JADWAL (Fase 36) — agregasi bulanan + DETEKSI BENTROK.

Permintaan owner: "kalender bulanan seluruh tenggat rumah untuk Manajer Proyek supaya
bentrok terlihat SEBELUM terjadi". Sebelum fase ini tenggat hanya bisa dilihat per rumah
(sheet jadwal) atau sebagai daftar (Papan Mandor / Antrean Kerja), jadi tiga masalah nyata
tidak pernah terlihat lebih dulu:

  1. BEBAN MENUMPUK — satu mandor kebagian 5 tenggat pada hari yang sama. Semua "tepat
     jadwal" di atas kertas, mustahil di lapangan.
  2. PEKERJAAN KRITIS BERTABRAKAN — beberapa hold point (harus diperiksa supervisor)
     jatuh pada tanggal sama, padahal supervisornya satu orang.
  3. TENGGAT DI HARI LIBUR — tenggat mendarat di 17 Agustus / Idul Fitri / Minggu, lalu
     otomatis tercatat "telat" pada hari Senin tanpa ada yang bersalah.

Prinsip modul ini:
  * KALENDER = CERMIN DATA NYATA. Tidak ada tanggal/angka karangan: acara diambil dari
    `build_items.planned_finish`, `build_schedules.start_date/target_finish_date`,
    `inspections.scheduled_date`, `punch_items.due_date`, dan `tasks.due_date`.
  * TIDAK MENULIS APA PUN (read-only). Mengubah tanggal tetap lewat jalur Fase 34
    (geser massal: wajib penyebab SSOT + catatan, bukti terverifikasi tidak bergeser).
  * Task Work Hub yang berasal dari item pekerjaan (`tasks.meta.build_item_id`) SENGAJA
    dibuang dari lapisan tugas supaya satu pekerjaan tidak muncul dua kali.
  * Inspeksi tanpa tanggal rencana tidak dikarang tanggalnya: ditaruh di daftar
    "belum dijadwalkan" beserta ajakan menjadwalkan (endpoint terpisah).
"""
import calendar as calmod
import logging
from datetime import date, timedelta

import build_calendar as bcal
from core_utils import today_iso_date
from db import db
from rbac import has_role, is_project_scoped
from reference_p36 import CONFLICT_KINDS, EVENT_KINDS, EVENT_LABEL

logger = logging.getLogger("sipro.build.calendar.view")

KINDS = EVENT_KINDS
PROJECT_DIVISION = "technical"
OPEN_TASK_STATES = ("open", "in_progress", "snoozed", "submitted")
OPEN_PUNCH_STATES = ("open", "in_progress")
MAX_EVENTS = 4000
# Jenis acara yang DIPERIKSA terhadap hari libur / hari bukan kerja.
# Pilihan sengaja: keempat jenis ini menuntut ORANG HADIR DI LAPANGAN pada tanggal itu
# (tenggat pekerjaan, target rumah selesai, inspeksi/QC, dan punch list jatuh tempo), jadi
# kalau tanggalnya libur pekerjaannya pasti tidak terjadi lalu tercatat "telat" tanpa ada
# yang bersalah. `task` (tugas administratif Work Hub) & `schedule_start` DIKELUARKAN
# supaya panel bentrok tidak penuh peringatan yang tidak bisa ditindaklanjuti pelaksana.
# Catatan sejarah: dulu hanya `work_deadline` + `schedule_finish` yang diperiksa, sehingga
# inspeksi QC yang terjadwal pada 17 Agustus tidak ditandai di mana pun.
NONWORK_KINDS = ("work_deadline", "schedule_finish", "inspection", "punch")


# ============================ util ============================
def month_bounds(month: str = None) -> tuple:
    """('YYYY-MM') → (tanggal 1, tanggal terakhir). Bulan kosong = bulan berjalan."""
    ref = str(month or today_iso_date())[:7]
    try:
        year, mon = int(ref[:4]), int(ref[5:7])
        first = date(year, mon, 1)
    except (ValueError, IndexError):
        raise ValueError("Bulan harus format YYYY-MM (mis. 2026-08).")
    last = date(year, mon, calmod.monthrange(year, mon)[1])
    return first, last


def shift_month(month: str, delta: int) -> str:
    first, _ = month_bounds(month)
    y, m = first.year, first.month + delta
    y += (m - 1) // 12
    m = (m - 1) % 12 + 1
    return f"{y:04d}-{m:02d}"


async def project_scope(org: str, user: dict, project_id: str = None) -> tuple:
    """Proyek yang boleh dilihat pengguna (INV-36-9). Kosongkan project_id = portofolio."""
    q = {"org_id": org}
    if project_id:
        q["id"] = project_id
    rows = await db.projects.find(q, {"_id": 0, "id": 1, "name": 1, "code": 1,
                                      "members": 1}).sort("code", 1).to_list(200)
    if is_project_scoped(user):
        email = user.get("email")
        rows = [p for p in rows if email in (p.get("members") or [])]
    return [p["id"] for p in rows], {p["id"]: (p.get("name") or p.get("code")) for p in rows}


def _in_month(value, first: date, last: date) -> bool:
    day = str(value or "")[:10]
    return bool(day) and first.isoformat() <= day <= last.isoformat()


# ============================ pengumpulan acara ============================
async def _work_deadlines(org, pids, first, last, assignee, names, today) -> list:
    q = {"org_id": org, "project_id": {"$in": pids},
         "planned_finish": {"$gte": first.isoformat(), "$lte": f"{last.isoformat()}~"}}
    if assignee:
        q["assigned_to"] = assignee
    rows = await db.build_items.find(q, {"_id": 0, "evidence": 0, "history": 0}).sort(
        "planned_finish", 1).to_list(MAX_EVENTS)
    out = []
    for r in rows:
        day = str(r.get("planned_finish") or "")[:10]
        if not _in_month(day, first, last):
            continue
        critical = bool(r.get("hold_point")) or any(
            c.get("critical") for c in (r.get("checklist") or []))
        out.append({
            "kind": "work_deadline", "date": day, "id": r["id"],
            "title": r.get("name"), "step_code": r.get("step_code"),
            "unit_id": r.get("unit_id"), "unit_code": r.get("unit_code"),
            "schedule_id": r.get("schedule_id"), "project_id": r.get("project_id"),
            "project_name": names.get(r.get("project_id")),
            "status": r.get("status"), "assigned_to": r.get("assigned_to"),
            "verifier_hint": r.get("verifier_hint"), "week": int(r.get("week") or 1),
            "critical": critical, "hold_point": bool(r.get("hold_point")),
            "min_photos": int(r.get("min_photos") or 0),
            "planned_start": str(r.get("planned_start") or "")[:10],
            "late": bool(r.get("status") != "done" and day < today),
            "done": r.get("status") == "done",
            "link": f"/construction?tab=board&item={r['id']}",
        })
    return out


async def _schedule_events(org, pids, first, last, names) -> list:
    q = {"org_id": org, "project_id": {"$in": pids},
         "$or": [{"start_date": {"$gte": first.isoformat(), "$lte": f"{last.isoformat()}~"}},
                 {"target_finish_date": {"$gte": first.isoformat(),
                                         "$lte": f"{last.isoformat()}~"}}]}
    rows = await db.build_schedules.find(q, {"_id": 0}).sort("unit_code", 1).to_list(600)
    out = []
    for r in rows:
        base = {"unit_id": r.get("unit_id"), "unit_code": r.get("unit_code"),
                "schedule_id": r["id"], "project_id": r.get("project_id"),
                "project_name": names.get(r.get("project_id")),
                "status": r.get("status"), "progress": r.get("progress"),
                "unit_type": r.get("unit_type"), "template_code": r.get("template_code"),
                "items_total": r.get("items_total"), "items_done": r.get("items_done"),
                "link": "/construction?tab=monitor", "critical": False}
        if _in_month(r.get("start_date"), first, last):
            out.append({**base, "kind": "schedule_start", "id": f"{r['id']}:start",
                        "date": str(r.get("start_date"))[:10],
                        "title": f"Mulai pembangunan {r.get('unit_code')}"})
        if _in_month(r.get("target_finish_date"), first, last):
            out.append({**base, "kind": "schedule_finish", "id": f"{r['id']}:finish",
                        "date": str(r.get("target_finish_date"))[:10],
                        "title": f"Target selesai {r.get('unit_code')}"})
    return out


async def _inspections(org, pids, first, last, names) -> list:
    q = {"org_id": org, "project_id": {"$in": pids},
         "scheduled_date": {"$gte": first.isoformat(), "$lte": f"{last.isoformat()}~"}}
    rows = await db.inspections.find(q, {"_id": 0, "items": 0}).sort(
        "scheduled_date", 1).to_list(600)
    return [{
        "kind": "inspection", "date": str(r.get("scheduled_date"))[:10], "id": r["id"],
        "title": r.get("title") or r.get("inspection_number"),
        "inspection_number": r.get("inspection_number"), "category": r.get("category"),
        "unit_id": r.get("unit_id"), "unit_code": r.get("unit_code"),
        "project_id": r.get("project_id"), "project_name": names.get(r.get("project_id")),
        "status": r.get("status"), "assigned_to": r.get("created_by"),
        "critical": True, "link": "/construction?tab=qc",
    } for r in rows]


async def _punch_items(org, pids, first, last, assignee, names) -> list:
    q = {"org_id": org, "project_id": {"$in": pids},
         "status": {"$in": list(OPEN_PUNCH_STATES)},
         "due_date": {"$gte": first.isoformat(), "$lte": f"{last.isoformat()}~"}}
    if assignee:
        q["assigned_to"] = assignee
    rows = await db.punch_items.find(q, {"_id": 0, "photo": 0}).sort(
        "due_date", 1).to_list(600)
    return [{
        "kind": "punch", "date": str(r.get("due_date"))[:10], "id": r["id"],
        "title": r.get("title"), "severity": r.get("severity"),
        "unit_id": r.get("unit_id"), "project_id": r.get("project_id"),
        "project_name": names.get(r.get("project_id")), "status": r.get("status"),
        "assigned_to": r.get("assigned_to"), "location": r.get("location"),
        "critical": r.get("severity") in ("major", "critical", "high"),
        "link": "/field", "category": r.get("category"),
    } for r in rows]


async def _tasks(org, pids, first, last, assignee, names) -> list:
    """Tugas Work Hub milik tim proyek — TANPA tugas yang lahir dari item pekerjaan."""
    q = {"org_id": org, "status": {"$in": list(OPEN_TASK_STATES)},
         "meta.build_item_id": {"$exists": False},
         "due_date": {"$gte": f"{first.isoformat()}T00:00:00",
                      "$lte": f"{last.isoformat()}T23:59:59.999999"},
         "$or": [{"division": PROJECT_DIVISION},
                 {"related_entity_type": {"$in": ["unit", "project"]}}]}
    if assignee:
        q["assigned_to"] = assignee
    rows = await db.tasks.find(q, {"_id": 0, "proof": 0}).sort("due_date", 1).to_list(800)
    out = []
    for r in rows:
        if r.get("related_entity_type") == "project" and r.get("related_entity_id") \
                and r.get("related_entity_id") not in pids:
            continue
        out.append({
            "kind": "task", "date": str(r.get("due_date"))[:10], "id": r["id"],
            "title": r.get("title"), "status": r.get("status"),
            "assigned_to": r.get("assigned_to"), "priority": r.get("priority"),
            "task_type": r.get("type"), "division": r.get("division"),
            "project_id": (r.get("related_entity_id")
                           if r.get("related_entity_type") == "project" else None),
            "project_name": names.get(r.get("related_entity_id")),
            "critical": r.get("priority") in ("high", "urgent"),
            "link": "/tasks",
        })
    return out


# ============================ deteksi bentrok ============================
def _fmt_day(day: str) -> str:
    bulan = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus",
             "September", "Oktober", "November", "Desember"]
    d = bcal._d(day)
    return f"{d.day} {bulan[d.month - 1]} {d.year}"


def _lower_first(text: str) -> str:
    """Huruf pertama label SSOT dikecilkan agar menyatu di tengah kalimat, tanpa merusak
    singkatan di dalamnya (mis. "Inspeksi / QC terjadwal" → "inspeksi / QC terjadwal")."""
    return (text[:1].lower() + text[1:]) if text else text


def detect_conflicts(cal: dict, events: list, thresholds: dict) -> list:
    """Tiga jenis bentrok (pilihan owner: semuanya) — dengan alasan yang bisa dibaca orang."""
    max_person = int(thresholds.get("max_items_per_person_per_day")
                     or bcal.DEFAULT_THRESHOLDS["max_items_per_person_per_day"])
    max_crit = int(thresholds.get("max_critical_per_day")
                   or bcal.DEFAULT_THRESHOLDS["max_critical_per_day"])
    work = [e for e in events if e["kind"] == "work_deadline" and not e.get("done")]
    by_person, by_crit, by_nonwork = {}, {}, {}
    for e in work:
        if e.get("assigned_to"):
            by_person.setdefault((e["date"], e["assigned_to"]), []).append(e)
        if e.get("critical"):
            by_crit.setdefault(e["date"], []).append(e)
    for e in events:
        if e["kind"] in NONWORK_KINDS and not e.get("done") \
                and not bcal.is_workday(cal, e["date"]):
            by_nonwork.setdefault(e["date"], []).append(e)

    out = []
    for (day, person), rows in by_person.items():
        if len(rows) <= max_person:
            continue
        out.append({
            "kind": "overload", "date": day, "person": person, "count": len(rows),
            "threshold": max_person,
            "severity": "high" if len(rows) >= max_person * 2 else "medium",
            "unit_codes": sorted({r.get("unit_code") for r in rows if r.get("unit_code")}),
            "item_ids": [r["id"] for r in rows],
            "schedule_ids": sorted({r.get("schedule_id") for r in rows
                                    if r.get("schedule_id")}),
            "detail": (f"{person} kebagian {len(rows)} tenggat pekerjaan pada "
                       f"{_fmt_day(day)} (batas wajar {max_person}). Geser sebagian ke "
                       "hari lain atau tambah pelaksana."),
        })
    for day, rows in by_crit.items():
        if len(rows) <= max_crit:
            continue
        out.append({
            "kind": "critical_stack", "date": day, "person": None, "count": len(rows),
            "threshold": max_crit,
            "severity": "high" if len(rows) >= max_crit * 2 else "medium",
            "unit_codes": sorted({r.get("unit_code") for r in rows if r.get("unit_code")}),
            "item_ids": [r["id"] for r in rows],
            "schedule_ids": sorted({r.get("schedule_id") for r in rows
                                    if r.get("schedule_id")}),
            "detail": (f"{len(rows)} pekerjaan kritis / hold point jatuh bersamaan pada "
                       f"{_fmt_day(day)} (batas {max_crit}). Supervisor tidak mungkin "
                       "memeriksa semuanya di hari yang sama."),
        })
    for day, rows in by_nonwork.items():
        info = bcal.day_info(cal, day)
        suggest = bcal.next_workday(cal, day).isoformat()
        why = (f"hari libur {info['holiday']}" if info.get("holiday")
               else f"{info['weekday_label']} bukan hari kerja")
        # Rincian per jenis supaya PM tahu YANG MANA yang jatuh di hari libur — dulu
        # pesannya hanya menyebut "tenggat" padahal inspeksi/punch juga ikut terperiksa.
        tally = {}
        for r in rows:
            tally[r["kind"]] = tally.get(r["kind"], 0) + 1
        parts = ", ".join(f"{n} {_lower_first(EVENT_LABEL.get(k, k))}"
                          for k, n in sorted(tally.items(), key=lambda x: -x[1]))
        out.append({
            "kind": "non_workday", "date": day, "person": None, "count": len(rows),
            "threshold": None, "severity": "medium",
            "unit_codes": sorted({r.get("unit_code") for r in rows if r.get("unit_code")}),
            "item_ids": [r["id"] for r in rows],
            "schedule_ids": sorted({r.get("schedule_id") for r in rows
                                    if r.get("schedule_id")}),
            "kinds": sorted(tally.keys()),
            "suggested_date": suggest, "day_kind": info["kind"], "holiday": info.get("holiday"),
            "detail": (f"{len(rows)} agenda lapangan jatuh pada {_fmt_day(day)} "
                       f"({parts}) — {why}. Hari kerja terdekat: {_fmt_day(suggest)}."),
        })
    order = {k: i for i, k in enumerate(CONFLICT_KINDS)}
    return sorted(out, key=lambda c: (c["date"], order.get(c["kind"], 9)))


# ============================ pandangan bulanan ============================
async def unscheduled_inspections(org: str, pids: list, names: dict) -> list:
    """Inspeksi/QC yang belum punya tanggal — kalender tidak boleh mengarang tanggalnya."""
    rows = await db.inspections.find(
        {"org_id": org, "project_id": {"$in": pids}, "status": "in_progress",
         "scheduled_date": {"$in": [None, ""]}},
        {"_id": 0, "items": 0}).sort("created_at", -1).to_list(50)
    return [{"id": r["id"], "inspection_number": r.get("inspection_number"),
             "title": r.get("title"), "category": r.get("category"),
             "unit_id": r.get("unit_id"), "project_id": r.get("project_id"),
             "project_name": names.get(r.get("project_id")),
             "status": r.get("status"), "created_at": r.get("created_at")} for r in rows]


async def outlook(org: str, user: dict, month: str, project_id: str = None,
                  months: int = 3) -> list:
    """Ringkasan bentrok BULAN-BULAN BERIKUTNYA — supaya perencana tidak perlu menebak
    bulan mana yang bermasalah lalu mengklik satu-satu (temuan UX: bentrok terbesar sering
    berada 1-2 bulan ke depan, saat banyak rumah masuk tahap yang sama).

    Lapisan acara di sini SAMA dengan lapisan yang diperiksa terhadap hari libur
    (`NONWORK_KINDS`) supaya angka bentrok pada chip bulan tidak pernah lebih kecil
    daripada kenyataan ketika bulan itu benar-benar dibuka. Tugas Work Hub tidak ikut
    dihitung karena tidak pernah memicu bentrok.
    """
    pids, names = await project_scope(org, user, project_id)
    cal = await bcal.resolve(org, project_id)
    today = today_iso_date()
    out = []
    for step in range(1, max(1, int(months or 3)) + 1):
        ref = shift_month(month, step)
        first, last = month_bounds(ref)
        events = []
        if pids:
            events += await _work_deadlines(org, pids, first, last, None, names, today)
            events += await _schedule_events(org, pids, first, last, names)
            events += await _inspections(org, pids, first, last, names)
            events += await _punch_items(org, pids, first, last, None, names)
        conflicts = detect_conflicts(cal, events, cal["thresholds"])
        out.append({
            "month": ref, "events": len(events),
            "conflicts": {**{k: len([c for c in conflicts if c["kind"] == k])
                             for k in CONFLICT_KINDS}, "total": len(conflicts)},
        })
    return out


async def month_view(org: str, user: dict, month: str = None, project_id: str = None,
                     kinds: list = None, assignee: str = None) -> dict:
    """Satu payload untuk halaman Kalender Jadwal (hari, acara, bentrok, ringkasan)."""
    first, last = month_bounds(month)
    ref_month = f"{first.year:04d}-{first.month:02d}"
    pids, names = await project_scope(org, user, project_id)
    cal = await bcal.resolve(org, project_id)
    want = [k for k in (kinds or KINDS) if k in KINDS] or list(KINDS)
    today = today_iso_date()

    events = []
    if not pids:
        days = _build_days(cal, first, last, [], [], today)
        return {
            "month": ref_month, "first": first.isoformat(), "last": last.isoformat(),
            "prev_month": shift_month(ref_month, -1), "next_month": shift_month(ref_month, 1),
            "scope": "project" if project_id else "all", "project_id": project_id,
            "projects": [], "kinds": want, "assignee": assignee, "today": today,
            "calendar": bcal.public(cal), "days": days, "events": [], "conflicts": [],
            "assignees": [], "unscheduled": [], "outlook": [],
            "summary": _summary(days, [], [], cal, [], first, last),
        }

    if "work_deadline" in want:
        events += await _work_deadlines(org, pids, first, last, assignee, names, today)
    if "schedule_start" in want or "schedule_finish" in want:
        events += [e for e in await _schedule_events(org, pids, first, last, names)
                   if e["kind"] in want]
    if "inspection" in want:
        events += await _inspections(org, pids, first, last, names)
    if "punch" in want:
        events += await _punch_items(org, pids, first, last, assignee, names)
    if "task" in want:
        events += await _tasks(org, pids, first, last, assignee, names)
    if assignee:
        # Saring terakhir supaya penyaringan per ORANG benar-benar jujur: acara yang tidak
        # punya pemilik (mis. 'mulai pembangunan rumah') tidak ikut menumpang saat
        # perencana sedang memeriksa beban satu pelaksana.
        events = [e for e in events if e.get("assigned_to") == assignee]
    events.sort(key=lambda e: (e["date"], e["kind"], str(e.get("unit_code") or ""),
                               str(e.get("title") or "")))

    conflicts = detect_conflicts(cal, events, cal["thresholds"])
    days = _build_days(cal, first, last, events, conflicts, today)
    assignees = sorted({e["assigned_to"] for e in events if e.get("assigned_to")})
    unsched = await unscheduled_inspections(org, pids, names) if "inspection" in want else []
    return {
        "month": ref_month, "first": first.isoformat(), "last": last.isoformat(),
        "prev_month": shift_month(ref_month, -1), "next_month": shift_month(ref_month, 1),
        "scope": "project" if project_id else "all", "project_id": project_id,
        "projects": [{"id": pid, "name": names.get(pid)} for pid in pids],
        "kinds": want, "assignee": assignee, "today": today,
        "calendar": bcal.public(cal), "days": days, "events": events,
        "conflicts": conflicts, "assignees": assignees, "unscheduled": unsched,
        "outlook": await outlook(org, user, ref_month, project_id, 3),
        "summary": _summary(days, events, conflicts, cal, assignees, first, last),
    }


def _build_days(cal, first, last, events, conflicts, today) -> list:
    by_day, conf_day = {}, {}
    for e in events:
        by_day.setdefault(e["date"], []).append(e)
    for c in conflicts:
        conf_day.setdefault(c["date"], []).append(c)
    out = []
    for info in bcal.month_days(cal, first, last):
        day_events = by_day.get(info["date"], [])
        counts = {k: 0 for k in KINDS}
        load = {}
        for e in day_events:
            counts[e["kind"]] = counts.get(e["kind"], 0) + 1
            if e.get("assigned_to") and e["kind"] in ("work_deadline", "punch", "task"):
                load[e["assigned_to"]] = load.get(e["assigned_to"], 0) + 1
        day_conf = conf_day.get(info["date"], [])
        out.append({
            **info, "total": len(day_events), "counts": counts,
            "late": len([e for e in day_events if e.get("late")]),
            "critical": len([e for e in day_events if e.get("critical")]),
            "load": sorted([{"assigned_to": k, "count": v} for k, v in load.items()],
                           key=lambda r: -r["count"]),
            "conflicts": [c["kind"] for c in day_conf],
            "conflict_count": len(day_conf),
            "is_today": info["date"] == today,
            "is_past": info["date"] < today,
        })
    return out


def _summary(days, events, conflicts, cal, assignees, first, last) -> dict:
    counts = {k: len([e for e in events if e["kind"] == k]) for k in KINDS}
    busiest = max(days, key=lambda d: d["total"], default=None)
    return {
        "totals": {**counts, "all": len(events)},
        "work_days": len([d for d in days if d["is_workday"]]),
        "half_days": len([d for d in days if d.get("half_day")]),
        "off_days": len([d for d in days if not d["is_workday"]]),
        "holidays": [{"date": d["date"], "name": d["holiday"], "kind": d.get("holiday_kind")}
                     for d in days if d.get("holiday")],
        "late": len([e for e in events if e.get("late")]),
        "critical": len([e for e in events if e.get("critical")]),
        "people": len(assignees),
        "conflicts": {**{k: len([c for c in conflicts if c["kind"] == k])
                         for k in CONFLICT_KINDS}, "total": len(conflicts)},
        "busiest": ({"date": busiest["date"], "count": busiest["total"]}
                    if busiest and busiest["total"] else None),
        "range": {"first": first.isoformat(), "last": last.isoformat()},
        "thresholds": cal.get("thresholds"),
    }
