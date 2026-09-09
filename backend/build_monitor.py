"""BUILD MONITOR (Fase 31) — papan pantau, pengingat, dan ESKALASI keterlambatan.

Isi:
  * `board()`    — satu baris per unit: progres nyata vs rencana, deviasi hari, item telat,
                   gerbang yang menahan, jumlah override (transparansi anti-kecurangan).
  * `summary()`  — kartu ringkasan untuk halaman monitoring.
  * `timeline()` — kurva rencana vs realisasi per minggu untuk satu unit (bukan angka manual).
  * `delay_report()` — penyebab keterlambatan tersering (dari kode SSOT, bukan teks bebas).
  * `tick()`     — dijalankan scheduler: buka gerbang yang waktu tunggunya sudah lewat,
                   kirim PENGINGAT (H-1 & hari-H), lalu ESKALASI berjenjang bila telat:
                     telat ≥1 hari  → staf + supervisor (tugas TK-13)
                     telat ≥3 hari  → direksi ikut diberi tahu
                     telat ≥7 hari  → peringatan kritis diulang ke direksi
"""
import logging

import build_engine as be
import workhub as wh
from core_utils import now_iso, today_iso_date
from db import db, ORG_ID
from engine import add_activity, create_notification, emit
from reference_p31 import DELAY_CAUSE_LABEL

logger = logging.getLogger("sipro.build.monitor")

LEVELS = [(7, 3), (3, 2), (1, 1)]      # (telat_hari_minimal, level)


def _days_late(planned_finish: str, ref: str = None) -> int:
    from datetime import datetime
    if not planned_finish:
        return 0
    a = datetime.strptime((ref or today_iso_date())[:10], "%Y-%m-%d").date()
    b = datetime.strptime(str(planned_finish)[:10], "%Y-%m-%d").date()
    return max(0, (a - b).days)


async def board(org: str, *, project_id: str = None, status: str = None,
                skip: int = 0, limit: int = 50) -> dict:
    q = {"org_id": org}
    if project_id:
        q["project_id"] = project_id
    if status and status != "all":
        q["status"] = status
    total = await db.build_schedules.count_documents(q)
    rows = await db.build_schedules.find(q, {"_id": 0}).sort(
        [("status", 1), ("deviation", 1)]).skip(skip).limit(limit).to_list(limit)
    today = today_iso_date()
    for r in rows:
        items = await db.build_items.find(
            {"org_id": org, "schedule_id": r["id"]},
            {"_id": 0, "name": 1, "status": 1, "planned_start": 1, "planned_finish": 1,
             "week": 1, "order": 1, "gate_reasons": 1, "assigned_to": 1, "delay_cause": 1,
             "hold_point": 1, "step_code": 1}).sort("order", 1).to_list(400)
        nxt = next((i for i in items if i["status"] in ("ready", "in_progress", "rework")), None)
        waiting = next((i for i in items if i["status"] == "submitted"), None)
        blocked = [i for i in items if i["status"] == "blocked" and i.get("gate_reasons")]
        late = [{"name": i["name"], "planned_finish": i["planned_finish"],
                 "days": _days_late(i["planned_finish"], today), "status": i["status"],
                 "assigned_to": i.get("assigned_to"),
                 "delay_cause": i.get("delay_cause"),
                 "delay_label": DELAY_CAUSE_LABEL.get(i.get("delay_cause")) }
                for i in items if i["status"] != "done"
                and str(i.get("planned_finish") or "") < today]
        r["next_item"] = nxt
        r["awaiting_verification"] = waiting
        r["blocked_detail"] = [{"name": b["name"],
                                "reasons": [x.get("detail") for x in b.get("gate_reasons") or []]}
                               for b in blocked[:3]]
        r["late_detail"] = sorted(late, key=lambda x: -x["days"])[:5]
        r["max_late_days"] = max([x["days"] for x in late], default=0)
    return {"data": rows, "total": total}


async def summary(org: str, project_id: str = None) -> dict:
    q = {"org_id": org}
    if project_id:
        q["project_id"] = project_id
    rows = await db.build_schedules.find(q, {"_id": 0}).to_list(1000)
    units_total = await db.units.count_documents(
        {"org_id": org, **({"project_id": project_id} if project_id else {})})
    prog = [float(r.get("progress") or 0) for r in rows]
    out = {
        "units_total": units_total, "scheduled": len(rows),
        "unscheduled": max(0, units_total - len(rows)),
        "avg_progress": round(sum(prog) / len(prog), 1) if prog else 0,
        "avg_planned": round(sum(float(r.get("planned_progress") or 0)
                                 for r in rows) / len(rows), 1) if rows else 0,
        "on_track": len([r for r in rows if r.get("status") == "in_progress"]),
        "at_risk": len([r for r in rows if r.get("status") == "at_risk"]),
        "on_hold": len([r for r in rows if r.get("status") == "on_hold"]),
        "done": len([r for r in rows if r.get("status") == "done"]),
        "not_started": len([r for r in rows if r.get("status") == "not_started"]),
        "late_items": sum(int(r.get("late_items") or 0) for r in rows),
        "blocked_items": sum(int(r.get("blocked_items") or 0) for r in rows),
        "overrides": sum(int(r.get("overrides") or 0) for r in rows),
    }
    iq = {"org_id": org, **({"project_id": project_id} if project_id else {})}
    out["awaiting_verification"] = await db.build_items.count_documents(
        {**iq, "status": "submitted"})
    out["rework"] = await db.build_items.count_documents({**iq, "status": "rework"})
    return out


async def timeline(org: str, schedule_id: str) -> dict:
    """Kurva rencana vs realisasi per MINGGU jadwal (dihitung dari data, bukan input)."""
    items = await db.build_items.find({"org_id": org, "schedule_id": schedule_id},
                                      {"_id": 0}).sort("order", 1).to_list(500)
    total = sum(float(i.get("weight") or 0) for i in items) or 1
    weeks = sorted({int(i.get("week") or 1) for i in items})
    today = today_iso_date()
    points, cum_p, cum_a = [{"name": "Mulai", "planned": 0, "actual": 0}], 0.0, 0.0
    for w in weeks:
        rows = [i for i in items if int(i.get("week") or 1) == w]
        cum_p += sum(float(i.get("weight") or 0) for i in rows)
        cum_a += sum(float(i.get("weight") or 0) for i in rows if i.get("status") == "done")
        last = max((str(i.get("planned_finish") or "") for i in rows), default="")
        points.append({"name": f"M{w}", "planned": round(cum_p / total * 100, 1),
                       "actual": round(cum_a / total * 100, 1) if last <= today or cum_a else 0,
                       "until": last})
    return {"points": points, "weeks": len(weeks)}


async def delay_report(org: str, project_id: str = None) -> dict:
    q = {"org_id": org, "status": {"$ne": "done"}}
    if project_id:
        q["project_id"] = project_id
    today = today_iso_date()
    items = await db.build_items.find(q, {"_id": 0}).to_list(2000)
    late = [i for i in items if str(i.get("planned_finish") or "") < today]
    by_cause, by_category = {}, {}
    for i in late:
        c = i.get("delay_cause") or "unreported"
        by_cause[c] = by_cause.get(c, 0) + 1
        cat = i.get("work_category") or "lainnya"
        by_category[cat] = by_category.get(cat, 0) + 1
    return {
        "late_total": len(late),
        "unreported_cause": by_cause.get("unreported", 0),
        "by_cause": [{"cause": k, "label": DELAY_CAUSE_LABEL.get(k, "Belum dijelaskan"),
                      "count": v} for k, v in sorted(by_cause.items(), key=lambda x: -x[1])],
        "by_category": [{"category": k, "count": v}
                        for k, v in sorted(by_category.items(), key=lambda x: -x[1])],
        "worst": sorted([{"unit_code": i.get("unit_code"), "name": i.get("name"),
                          "days": _days_late(i.get("planned_finish"), today),
                          "assigned_to": i.get("assigned_to")} for i in late],
                        key=lambda x: -x["days"])[:8],
    }


async def buyer_milestones(org: str, unit_id: str) -> dict:
    """Ringkasan untuk PEMBELI: progres nyata rumahnya + tahapan per minggu.

    Pembeli dulu melihat progres FASE PROYEK (jalan/drainase kawasan) seolah-olah itu
    progres rumahnya. Sekarang yang tampil adalah jadwal unitnya sendiri.
    """
    sched = await db.build_schedules.find_one({"org_id": org, "unit_id": unit_id}, {"_id": 0})
    if not sched:
        return None
    items = await db.build_items.find(
        {"org_id": org, "schedule_id": sched["id"]},
        {"_id": 0, "name": 1, "status": 1, "week": 1, "order": 1, "planned_start": 1,
         "planned_finish": 1, "verified_at": 1, "weight": 1}).sort("order", 1).to_list(500)
    today = today_iso_date()
    weeks = {}
    for it in items:
        weeks.setdefault(int(it.get("week") or 1), []).append(it)
    milestones = []
    for w, rows in sorted(weeks.items()):
        done = [i for i in rows if i["status"] == "done"]
        pf = max(str(i.get("planned_finish") or "") for i in rows)
        if len(done) == len(rows):
            status = "done"
        elif done or any(i["status"] in ("in_progress", "submitted", "rework") for i in rows):
            status = "in_progress"
        else:
            status = "pending"
        milestones.append({
            "week": w, "status": status, "planned_finish": pf,
            "late": status != "done" and pf < today,
            # JUJUR: tanggal "disetujui" hanya keluar bila SELURUH pekerjaan minggu itu
            # sudah diverifikasi. Sebelumnya minggu yang baru sebagian selesai ikut
            # menampilkan tanggal persetujuan sehingga pembeli bisa salah paham
            # (mengira tahapannya sudah tuntas padahal masih dikerjakan).
            "done_at": (max((str(i.get("verified_at") or "") for i in done), default=None)
                        if status == "done" else None),
            "works": [i["name"] for i in rows], "items_done": len(done),
            "items_total": len(rows),
        })
    return {
        "progress": sched.get("progress"), "planned_progress": sched.get("planned_progress"),
        "status": sched.get("status"), "start_date": sched.get("start_date"),
        "target_finish_date": sched.get("target_finish_date"),
        "deviation_days": sched.get("deviation_days"), "late_items": sched.get("late_items"),
        "template_name": sched.get("template_name"), "milestones": milestones,
    }


# ============================ pengingat & eskalasi ============================
async def _remind(org: str, item: dict, when: str):
    if not item.get("assigned_to"):
        return
    today = today_iso_date()
    if item.get("reminded_on") == today:
        return
    body = (f"Unit {item.get('unit_code')} · rencana {item.get('planned_start')} → "
            f"{item.get('planned_finish')}")
    await create_notification(
        user_email=item["assigned_to"],
        title=("Besok mulai: " if when == "h1" else "Dikerjakan hari ini: ") + item["name"],
        body=body, type="task", related_entity_type="unit",
        related_entity_id=item["unit_id"], org_id=org)
    await db.build_items.update_one({"id": item["id"]},
                                   {"$set": {"reminded_on": today, "updated_at": now_iso()}})


async def _escalate(org: str, item: dict, days: int, sched: dict):
    level = next((lv for min_d, lv in LEVELS if days >= min_d), 0)
    if not level or level <= int(item.get("escalation_level") or 0):
        return 0
    ts = now_iso()
    await db.build_items.update_one({"id": item["id"]}, {"$set": {
        "late_days": days, "escalation_level": level, "escalated_at": ts, "updated_at": ts}})
    label = f"{item['name']} — unit {item.get('unit_code')} TELAT {days} hari"
    targets = [item.get("assigned_to"), item.get("verifier_hint")]
    if level >= 2:
        rows = await db.users.find({"org_id": org, "role": {"$in": ["owner", "super_admin"]},
                                    "is_active": True}, {"_id": 0, "email": 1}).to_list(20)
        targets += [r["email"] for r in rows]
    seen = set()
    for email in [t for t in targets if t]:
        if email in seen:
            continue
        seen.add(email)
        await create_notification(
            user_email=email,
            title=("PERINGATAN KRITIS: pekerjaan telat" if level >= 3
                   else ("Eskalasi keterlambatan" if level >= 2 else "Pekerjaan lewat tenggat")),
            body=label + (f" · penyebab: {DELAY_CAUSE_LABEL.get(item.get('delay_cause'))}"
                          if item.get("delay_cause") else " · penyebab belum dijelaskan"),
            type="alert", related_entity_type="unit", related_entity_id=item["unit_id"],
            org_id=org)
    await wh.spawn(org, "TK-13", source_event=f"build.item_late:{item['id']}:L{level}",
                   assignee_override=(item.get("verifier_hint") if level >= 2
                                      else item.get("assigned_to")),
                   entity_type="unit", entity_id=item["unit_id"],
                   title=f"Kejar keterlambatan: {item['name']} — unit {item.get('unit_code')}",
                   description=(f"Telat {days} hari dari rencana {item.get('planned_finish')}. "
                                "Wajib isi penyebab keterlambatan + rencana pemulihan."),
                   meta={"build_item_id": item["id"], "schedule_id": item["schedule_id"],
                         "late_days": days, "level": level})
    await add_activity(entity_type="unit", entity_id=item["unit_id"], type="system",
                       body=f"ESKALASI L{level}: {label}.", actor="system", org_id=org)
    await emit("build.item_late", "unit", item["unit_id"],
               {"label": item.get("unit_code"), "item_id": item["id"], "days": days},
               org_id=org)
    return 1


async def tick() -> dict:
    """Satu putaran pemantauan: gerbang, pengingat, eskalasi (idempoten per hari/level)."""
    out = {"gates_opened": 0, "reminders": 0, "escalations": 0, "schedules": 0,
           "tasks_closed": 0}
    today = today_iso_date()
    scheds = await db.build_schedules.find(
        {"status": {"$in": ["not_started", "in_progress", "at_risk"]}}, {"_id": 0}).to_list(500)
    from datetime import datetime, timedelta
    tomorrow = (datetime.strptime(today, "%Y-%m-%d").date() + timedelta(days=1)).isoformat()
    for s in scheds:
        org = s.get("org_id", ORG_ID)
        out["schedules"] += 1
        out["gates_opened"] += await be.refresh_gates(org, s["id"])
        items = await db.build_items.find(
            {"org_id": org, "schedule_id": s["id"], "status": {"$ne": "done"}},
            {"_id": 0}).to_list(400)
        for it in items:
            ps, pf = str(it.get("planned_start") or ""), str(it.get("planned_finish") or "")
            if it.get("status") in ("ready", "in_progress", "rework"):
                if ps == tomorrow:
                    await _remind(org, it, "h1")
                    out["reminders"] += 1
                elif ps <= today <= pf:
                    await _remind(org, it, "h0")
                    out["reminders"] += 1
            days = _days_late(pf, today)
            if days:
                out["escalations"] += await _escalate(org, it, days, s)
        await be.recompute_schedule(org, s["id"])
    # Fase 32: tutup task pekerjaan yang sudah tidak relevan supaya papan kerja pelaksana
    # tidak menyimpan "task hantu" (mis. item sudah diverifikasi lewat jalur lain).
    for org in sorted({s.get("org_id", ORG_ID) for s in scheds} or {ORG_ID}):
        out["tasks_closed"] += await be.reconcile_item_tasks(org)
    return out
