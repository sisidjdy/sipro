"""Drill-down KPI lintas modul (Fase 92): Beranda, Pipeline Lead, Pembangunan.

Setiap kunci mengembalikan {title, rows[], total, count, href_all}; tiap baris membawa
`href` ke halaman/tabel yang sudah terfilter. Kunci keuangan didelegasikan ke
`finance_drilldown` supaya satu definisi angka dipakai di mana pun."""
from datetime import datetime, timedelta, timezone

import reference as ref
import workhub as wh
from db import db, ORG_ID
from rbac import can, scope_query
from core_utils import now_iso

# kunci -> (resource, action) izin yang wajib dimiliki peran pemanggil
PERMISSION = {
    "tasks": ("work_tasks", "view"), "leads": ("leads", "view"), "deals": ("deals", "view"),
    "projects": ("projects", "view"), "units_qc_hold": ("construction", "view"),
    "punch_open": ("construction", "view"), "build": ("construction", "view"),
    "board": ("construction", "view"), "ads": ("ads", "view"), "project": ("projects", "view"),
    "retention_held": ("finance", "view"),
}
FINANCE_KEYS = {"ar_outstanding", "ar_overdue", "ar_bucket", "ap_outstanding", "ap_pending",
                "ap_bucket", "contract_liability", "customer_deposits", "revenue_recognized"}
BUILD_KEYS = {"unscheduled": "Unit belum dijadwalkan", "awaiting_verification": "Pekerjaan menunggu verifikasi",
              "rework": "Pekerjaan minta perbaikan", "late_items": "Pekerjaan telat",
              "blocked_items": "Pekerjaan tertahan gerbang", "at_risk": "Unit berisiko",
              "scheduled": "Unit terjadwal"}


def _row(id_, title, subtitle="", amount=None, status=None, group=None, href=None, **extra):
    return {"id": id_, "title": title, "subtitle": subtitle, "amount": amount, "status": status,
            "status_group": group, "href": href, **extra}


def _csv(v):
    return [x for x in str(v or "").split(",") if x]


async def allowed(user: dict, key: str) -> bool:
    if key in FINANCE_KEYS:
        res = ("finance", "view")
    else:
        res = PERMISSION.get(key.split(":")[0])
    if not res:
        return False
    return await can(user.get("role"), *res)


async def _tasks(user, p):
    from routers.work_router import _scope_query, _bucket_filter
    scope, bucket, sla = p.get("scope") or "mine", p.get("bucket") or "", p.get("sla") or ""
    q = await _scope_query(user, scope, _bucket_filter(bucket))
    if scope == "mine":
        q["assigned_to"] = user.get("email")
    if sla == "breached":
        q.update({"sla_breached": True, "status": {"$in": list(wh.ACTIVE_STATES)}})
    rows = await db.tasks.find(q, {"_id": 0, "description": 0}).sort("due_date", 1).to_list(300)
    count = await db.tasks.count_documents(q)
    label = {"overdue": "Tugas terlambat", "today": "Tugas hari ini", "review": "Menunggu verifikasi",
             "waiting": "Ditunda", "upcoming": "Mendatang"}.get(bucket, "Tugas")
    if sla == "breached":
        label = "Tugas melewati SLA"
    base = f"/tasks?tab=tasks&scope={scope}" + (f"&bucket={bucket}" if bucket else "") + (f"&sla={sla}" if sla else "")
    return label, base, [
        _row(t["id"], t.get("title") or "-",
             " · ".join(x for x in [t.get("assigned_to") or "belum bertuan",
                                    f"jatuh tempo {str(t.get('due_date') or '')[:10]}" if t.get("due_date") else ""] if x),
             status=t.get("status"), group="task_status", href=f"{base}&q={t.get('title') or ''}", task_id=t["id"])
        for t in rows], count


async def _leads(user, p):
    org = user.get("org_id", ORG_ID)
    q = scope_query(user, {"org_id": org})
    stages, band, sla = _csv(p.get("stage")), p.get("band"), p.get("sla")
    idle_days, new_hours = int(p.get("idle_days") or 0), int(p.get("new_hours") or 0)
    if stages:
        q["stage"] = {"$in": stages}
    if band:
        q["score_band"] = band
    now = datetime.now(timezone.utc)
    if sla == "breached":
        # Definisi SAMA dengan kolom tabel (stage_clock): jatuh tempo tahap tersimpan sudah lewat.
        q["stage_due_at"] = {"$ne": None, "$lt": now.isoformat()}
    if new_hours:
        q["created_at"] = {"$gte": (now - timedelta(hours=new_hours)).isoformat()}
    if idle_days:
        cutoff = (now - timedelta(days=idle_days)).isoformat()
        q["stage"] = {"$nin": ["won", "lost", "closed"]} if not stages else q["stage"]
        # Lead yang baru dibuat TIDAK boleh dihitung "diam" hanya karena belum punya aktivitas.
        q["created_at"] = {"$lt": cutoff}
        q["$or"] = [{"last_activity_at": {"$lt": cutoff}}, {"last_activity_at": None},
                    {"last_activity_at": {"$exists": False}}]
    rows = await db.leads.find(q, {"_id": 0, "id": 1, "name": 1, "phone": 1, "stage": 1, "score": 1,
                                   "score_band": 1, "assigned_to": 1, "source": 1}).sort("updated_at", -1).to_list(300)
    # Angka kartu = jumlah SEBENARNYA di database, bukan panjang daftar yang dipangkas 300 baris.
    count = await db.leads.count_documents(q)
    title = "Lead"
    if stages:
        title = "Lead tahap " + ", ".join(ref.label_of("lead_stage", s) for s in stages)
    elif band:
        title = f"Lead {ref.label_of('score_band', band)}"
    elif sla == "breached":
        title = "Lead melewati SLA tahap"
    elif new_hours:
        title = f"Lead baru {new_hours} jam terakhir"
    elif idle_days:
        title = f"Lead diam ≥ {idle_days} hari"
    parts = []
    if stages:
        parts.append("stage=" + ",".join(stages))
    if band:
        parts.append("score_band=" + band)
    if sla:
        parts.append("sla=" + sla)
    href_all = "/leads" + ("?" + "&".join(parts) if parts else "")
    return title, href_all, [
        _row(l["id"], l.get("name") or "-",
             " · ".join(x for x in [l.get("phone") or "", ref.label_of("lead_source", l.get("source")) if l.get("source") else "",
                                    l.get("assigned_to") or ""] if x),
             amount=None, status=l.get("stage"), group="lead_stage", href=f"/leads/{l['id']}",
             score=l.get("score"), score_band=l.get("score_band"))
        for l in rows], count


async def _deals(user, p):
    org = user.get("org_id", ORG_ID)
    statuses = _csv(p.get("status")) or ["reserved", "booked", "active"]
    q = scope_query(user, {"org_id": org, "status": {"$in": statuses}})
    if p.get("mine") == "1":
        q["assigned_to"] = user.get("email")
    rows = await db.deals.find(q, {"_id": 0}).sort("updated_at", -1).to_list(300)
    count = await db.deals.count_documents(q)
    lead_ids = [d.get("lead_id") for d in rows if d.get("lead_id")]
    names = {l["id"]: l.get("name") for l in await db.leads.find({"id": {"$in": lead_ids}}, {"_id": 0, "id": 1, "name": 1}).to_list(300)}
    base = f"/customers?hub=deal&status={','.join(statuses)}"
    return "Deal " + ", ".join(ref.label_of("deal_status", s) for s in statuses), base, [
        _row(d["id"], f"{d.get('unit_code') or '-'} · {names.get(d.get('lead_id')) or '-'}",
             d.get("assigned_to") or "", amount=d.get("price"), status=d.get("status"), group="deal_status",
             href=f"{base}&q={d.get('unit_code') or ''}")
        for d in rows], count


async def _projects(user, p):
    org = user.get("org_id", ORG_ID)
    rows = await db.projects.find({"org_id": org}, {"_id": 0, "id": 1, "name": 1, "location": 1, "status": 1}).to_list(200)
    return "Proyek", "/projects", [
        _row(r["id"], r.get("name") or "-", r.get("location") or "", status=r.get("status"), href=f"/projects/{r['id']}") for r in rows]


async def _units_qc_hold(user, p):
    org = user.get("org_id", ORG_ID)
    rows = await db.units.find({"org_id": org, "construction_status": "qc_hold"}, {"_id": 0, "id": 1, "code": 1, "type": 1, "project_id": 1}).to_list(300)
    return "Unit QC hold", "/build?hub=unit&construction_status=qc_hold", [
        _row(u["id"], u.get("code") or "-", u.get("type") or "", status="qc_hold", href=f"/units/{u['id']}") for u in rows]


async def _punch_open(user, p):
    org = user.get("org_id", ORG_ID)
    rows = await db.punch_items.find({"org_id": org, "status": {"$in": ["open", "in_progress"]}}, {"_id": 0}).sort("created_at", -1).to_list(300)
    return "Punch list terbuka", "/build?hub=lapangan", [
        _row(r["id"], r.get("title") or r.get("description") or "-", r.get("unit_code") or "", status=r.get("status"),
             href=f"/units/{r['unit_id']}" if r.get("unit_id") else "/build?hub=lapangan") for r in rows]


async def _build(user, p, sub):
    org = user.get("org_id", ORG_ID)
    pid = p.get("project_id") or None
    q = {"org_id": org, **({"project_id": pid} if pid else {})}
    title = BUILD_KEYS.get(sub, "Pembangunan")
    href_all = "/build?hub=monitor" + (f"&project_id={pid}" if pid else "")
    rows = []
    if sub == "unscheduled":
        have = await db.build_schedules.distinct("unit_id", dict(q))
        for u in await db.units.find({**q, "id": {"$nin": have}}, {"_id": 0, "id": 1, "code": 1, "type": 1}).sort("code", 1).to_list(300):
            rows.append(_row(u["id"], u.get("code") or "-", u.get("type") or "", status="belum dijadwalkan", href=f"/units/{u['id']}"))
    elif sub in ("awaiting_verification", "rework", "late_items", "blocked_items"):
        iq = dict(q)
        if sub == "awaiting_verification":
            iq["status"] = "submitted"
        elif sub == "rework":
            iq["status"] = "rework"
        elif sub == "late_items":
            iq.update({"status": {"$ne": "done"}, "planned_finish": {"$lt": now_iso()[:10]}})
        else:
            iq.update({"status": {"$nin": ["done"]}, "gate_reasons.0": {"$exists": True}})
        for it in await db.build_items.find(iq, {"_id": 0, "evidence": 0, "checklist": 0, "history": 0}).sort("planned_finish", 1).to_list(400):
            note = f"rencana selesai {it.get('planned_finish')}" if it.get("planned_finish") else ""
            if sub == "blocked_items" and it.get("gate_reasons"):
                note = "; ".join(str(g.get("label") or g.get("reason") or g) if isinstance(g, dict) else str(g) for g in it["gate_reasons"][:2])
            rows.append(_row(it["id"], f"{it.get('unit_code') or '-'} · {it.get('name') or it.get('step_code')}",
                             " · ".join(x for x in [note, it.get("assigned_to") or ""] if x),
                             status=it.get("status"), group="build_item_status", href=f"/units/{it['unit_id']}"))
    else:
        sq = dict(q)
        if sub == "at_risk":
            sq["status"] = "at_risk"
        for s in await db.build_schedules.find(sq, {"_id": 0}).sort("deviation", 1).to_list(300):
            rows.append(_row(s["id"], f"{s.get('unit_code') or '-'} · {s.get('customer_name') or s.get('lead_name') or 'belum ada pembeli'}",
                             f"progres {s.get('progress', 0)}% vs rencana {s.get('planned_progress', 0)}%"
                             + (f" · telat {s.get('deviation_days')} hari" if s.get("deviation_days") else ""),
                             status=s.get("status"), group="build_schedule_status", href=f"/units/{s['unit_id']}"))
    return title, href_all, rows


async def _board(user, p, sub):
    """Papan Unit (hub Pembangunan): pakai mesin papan yang sama supaya angka = rincian."""
    import build_unit_board as bub
    org = user.get("org_id", ORG_ID)
    pid = p.get("project_id") or None
    f = {"project_id": pid} if pid else {}
    title = {"all": "Semua unit", "unscheduled": "Unit belum dijadwalkan", "running": "Unit sedang berjalan",
             "late": "Unit telat", "ready": "Unit siap dimulai", "awaiting": "Unit menunggu verifikasi",
             "progress": "Progres per unit"}.get(sub, "Papan unit")
    qs = []
    if sub == "unscheduled":
        f["unscheduled_only"] = "1"; qs.append("unscheduled_only=1")
    elif sub == "late":
        f["late_only"] = "1"; qs.append("late_only=1")
    elif sub == "running":
        f["readiness"] = ["started"]; qs.append("readiness=started")
    elif sub == "ready":
        f["readiness"] = ["ready"]; qs.append("readiness=ready")
    if pid:
        qs.append(f"project_id={pid}")
    res = await bub.unit_rows(org, skip=0, limit=0, **f)
    rows = res["data"]
    if sub == "awaiting":
        rows = [r for r in rows if (r.get("active_step") or {}).get("status") == "submitted"]
    if sub == "progress":
        rows = [r for r in rows if r.get("schedule_id")]
        rows.sort(key=lambda r: (r.get("actual_progress") or 0))
    out = []
    for r in rows:
        step = (r.get("active_step") or {}).get("name")
        sub_t = " · ".join(x for x in [
            r.get("project_name") or "", r.get("type") or "",
            f"progres {r.get('actual_progress')}% vs rencana {r.get('planned_progress')}%" if r.get("actual_progress") is not None else "belum dijadwalkan",
            f"telat {r.get('days_late')} hari" if (r.get("days_late") or 0) > 0 else "",
            f"langkah aktif: {step}" if step else ""] if x)
        uid = r.get("unit_id") or r.get("id")
        out.append(_row(uid, r.get("code") or "-", sub_t, status=r.get("readiness"), group="build_readiness_state",
                        href=f"/units/{uid}"))
    return title, "/build?hub=unit" + ("&" + "&".join(qs) if qs else ""), out


async def drilldown(user: dict, key: str, params: dict) -> dict:
    if key in FINANCE_KEYS:
        import finance_drilldown as fd
        return await fd.drilldown(user.get("org_id", ORG_ID), key, params.get("bucket"))
    if key == "retention_held":
        import finance_drilldown as fd
        org = user.get("org_id", ORG_ID)
        bills = await db.ap_invoices.find({"org_id": org, "retention_held": {"$gt": 0}, "retention_released": {"$ne": True}}, {"_id": 0}).to_list(500)
        rows = [fd._ap_row(b, b.get("retention_held", 0)) for b in bills]
        return {"key": key, "title": "Retensi ditahan per tagihan vendor", "rows": rows,
                "total": sum(r["amount"] for r in rows), "count": len(rows), "href_all": fd.AP_BASE}
    root, _, sub = key.partition(":")
    fn = {"tasks": _tasks, "leads": _leads, "deals": _deals, "projects": _projects,
          "units_qc_hold": _units_qc_hold, "punch_open": _punch_open}.get(root)
    show_total = True
    count = None
    if root == "build":
        title, href_all, rows = await _build(user, params, sub)
    elif root == "board":
        title, href_all, rows = await _board(user, params, sub)
    elif root in ("ads", "project"):
        import kpi_drilldown_ext as ext
        title, href_all, rows, show_total = await (ext.ads if root == "ads" else ext.project)(user, sub, params)
    elif fn:
        res = await fn(user, params)
        title, href_all, rows = res[:3]
        count = res[3] if len(res) > 3 else None
    else:
        raise KeyError(key)
    total = sum(int(r.get("amount") or 0) for r in rows)
    unit = "count" if rows and all(r.get("unit") == "count" for r in rows) else "idr"
    return {"key": key, "title": title, "rows": rows, "total": total if (total and show_total) else None,
            "unit": unit, "count": count if count is not None else len(rows), "href_all": href_all}
