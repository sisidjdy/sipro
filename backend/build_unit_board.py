"""PAPAN UNIT (Fase 46) — satu baris per RUMAH, bukan per jadwal.

Mengapa file baru padahal `build_monitor.board()` sudah ada? Karena keduanya menjawab
pertanyaan berbeda dan itu dulu menjadi sumber kebingungan:

  * `build_monitor.board()` = baris per **jadwal**. Unit yang BELUM dijadwalkan tidak
    muncul sama sekali — padahal justru unit itulah yang butuh perhatian.
  * `unit_rows()` (di sini) = baris per **unit** (semua unit, terjadwal atau belum),
    lengkap dengan kolom yang diminta dok 29 §4: progres realisasi, rencana, deviasi,
    langkah aktif, tenggat, umur telat, PIC, bukti terakhir, dan kesiapan mulai bangun.

Satu kebenaran dijaga: progres & rencana TIDAK dihitung ulang di sini. Nilainya dibaca
dari `build_schedules` (hasil `build_engine.recompute_schedule`, yaitu Σ bobot item
terverifikasi). Kolom `items_done/items_total` disertakan supaya angkanya bisa
direkonstruksi pembaca laporan.

Kejujuran: unit tanpa jadwal → `planned_progress=None`, `deviation=None`,
`days_late=None`, `missing=["jadwal_pembangunan"]`. **Tidak pernah 0** — karena 0%
berarti "sudah dijadwalkan, belum dikerjakan", sedangkan `None` berarti "belum ada
datanya". Dua hal itu keputusan manajerial yang berbeda.
"""
import re

import permit_scope as ps
import settings_store as cfg
from core_utils import today_iso_date
from db import ORG_ID, db
from reference_p46 import READINESS_LABEL, STARTED_UNIT_STATUS

WORKABLE = ("ready", "in_progress", "rework")
SORTABLE = {"code": "code", "type": "type", "cluster_code": "cluster_code",
            "block": "block", "construction_status": "construction_status",
            "construction_progress": "construction_progress", "status": "status"}
DERIVED_SORT = ("planned_progress", "deviation", "days_late", "due_date", "readiness")


def _days_late(planned_finish: str, ref: str) -> int:
    pf = str(planned_finish or "")[:10]
    if not pf or pf >= ref:
        return 0
    from datetime import date
    return (date.fromisoformat(ref) - date.fromisoformat(pf)).days


def _evidence_of(items: list) -> dict:
    """Bukti terakhir: langkah terverifikasi terbaru, atau pengajuan yang menunggu."""
    best, best_at, kind = None, "", None
    for i in items:
        for field, k in (("verified_at", "verified"), ("submitted_at", "submitted")):
            at = str(i.get(field) or "")
            if at and at > best_at:
                best, best_at, kind = i, at, k
    if not best:
        return None
    return {"at": best_at, "kind": kind, "item_name": best.get("name"),
            "by": best.get("verified_by") if kind == "verified" else best.get("submitted_by"),
            "photos": len(best.get("evidence") or [])}


def _row_of(unit: dict, sched: dict, items: list, pay: dict, ref: str) -> dict:
    """Satu baris papan unit (angka dibaca dari engine, bukan dihitung ulang)."""
    missing = []
    row = {
        "unit_id": unit["id"], "code": unit.get("code"), "type": unit.get("type"),
        "project_id": unit.get("project_id"), "cluster_code": unit.get("cluster_code"),
        "cluster_id": unit.get("cluster_id"), "block": unit.get("block"),
        "block_id": unit.get("block_id"), "status": unit.get("status"),
        "payment_status": unit.get("payment_status"), "lead_name": unit.get("lead_name"),
        "construction_status": unit.get("construction_status") or "not_started",
        "actual_progress": None, "planned_progress": None, "deviation": None,
        "deviation_days": None, "days_late": None, "late_items": None,
        "blocked_items": None, "items_done": None, "items_total": None,
        "schedule_id": None, "schedule_status": None, "template_name": None,
        "start_date": None, "target_finish_date": None, "build_started_at": None,
        "active_step": None, "pic": None, "due_date": None, "last_evidence": None,
        "dp_paid": None, "dp_label": None, "dp_known": False,
    }
    if not sched:
        missing.append("jadwal_pembangunan")
    else:
        active = next((i for i in items if i.get("status") in WORKABLE), None)
        waiting = next((i for i in items if i.get("status") == "submitted"), None)
        step = active or waiting
        late = [i for i in items if i.get("status") != "done"
                and str(i.get("planned_finish") or "") < ref]
        row.update({
            "actual_progress": float(sched.get("progress") or 0),
            "planned_progress": (float(sched["planned_progress"])
                                 if sched.get("planned_progress") is not None else None),
            "deviation": (float(sched["deviation"])
                          if sched.get("deviation") is not None else None),
            "deviation_days": int(sched.get("deviation_days") or 0),
            "days_late": max([_days_late(i.get("planned_finish"), ref) for i in late],
                             default=0),
            "late_items": len(late), "blocked_items": int(sched.get("blocked_items") or 0),
            "items_done": int(sched.get("items_done") or 0),
            "items_total": int(sched.get("items_total") or 0),
            "schedule_id": sched["id"], "schedule_status": sched.get("status"),
            "template_name": sched.get("template_name"),
            "start_date": sched.get("start_date"),
            "target_finish_date": sched.get("target_finish_date"),
            "build_started_at": sched.get("build_started_at"),
            "active_step": ({"id": step["id"], "name": step.get("name"),
                             "status": step.get("status"),
                             "planned_finish": step.get("planned_finish"),
                             "assigned_to": step.get("assigned_to")} if step else None),
            "pic": (step or {}).get("assigned_to"),
            "due_date": (step or {}).get("planned_finish") or sched.get("target_finish_date"),
            "last_evidence": _evidence_of(items),
        })
        if row["last_evidence"] is None:
            missing.append("bukti_kerja")
    row["dp_known"] = bool(pay)
    if pay:
        row["dp_paid"] = bool(pay["paid"])
        row["dp_label"] = pay["label"]
    else:
        missing.append("rencana_bayar")
    row["missing"] = missing
    return row


def _readiness_hint(row: dict, blocking_codes: list, permit_missing: bool,
                    require_dp: bool) -> dict:
    """Ringkas kesiapan untuk tabel. Rumus SAMA dengan `build_readiness.evaluate()`."""
    codes = []
    if row["construction_status"] in STARTED_UNIT_STATUS:
        state = "started"
    else:
        if not row["schedule_id"]:
            codes.append("no_schedule")
        elif row["schedule_status"] == "on_hold":
            codes.append("schedule_on_hold")
        elif not row["active_step"]:
            codes.append("no_ready_item")
        if blocking_codes and permit_missing:
            codes.append("permit_missing")
        pay = []
        if not row["dp_known"]:
            pay.append("no_payment_plan")
        elif not row["dp_paid"]:
            pay.append("dp_unpaid")
        # Kebijakan: bila "Mulai bangun butuh DP terbayar" MENYALA, alasan pembayaran
        # naik dari peringatan menjadi penghalang — sama seperti evaluator.
        if require_dp:
            codes += pay
            warn = []
        else:
            warn = pay
        state = "blocked" if codes else ("warning" if warn else "ready")
        codes += warn
    return {"readiness": state, "readiness_label": READINESS_LABEL[state],
            "readiness_codes": codes}


async def _payments(org: str, unit_ids: list) -> dict:
    rows = await db.ar_invoices.find({"org_id": org, "unit_id": {"$in": unit_ids}},
                                    {"_id": 0, "unit_id": 1, "items": 1}).to_list(500)
    out = {}
    for r in rows:
        items = r.get("items") or []
        if not items or r.get("unit_id") in out:
            continue
        first = items[0]
        amount = int(first.get("amount") or 0)
        paid_amount = int(first.get("paid_amount") or 0)
        out[r["unit_id"]] = {
            "paid": first.get("status") == "paid" or (amount > 0 and paid_amount >= amount),
            "label": first.get("label"), "amount": amount, "paid_amount": paid_amount}
    return out


def _unit_query(org: str, f: dict) -> dict:
    q = {"org_id": org}
    for key, field in (("project_id", "project_id"), ("cluster_id", "cluster_id"),
                       ("block_id", "block_id")):
        if f.get(key):
            q[field] = f[key]
    if f.get("construction_status"):
        q["construction_status"] = {"$in": list(f["construction_status"])}
    if f.get("project_ids") is not None:
        q["project_id"] = {"$in": list(f["project_ids"])}
    if f.get("q"):
        rx = re.escape(str(f["q"]).strip())
        q["$or"] = [{"code": {"$regex": rx, "$options": "i"}},
                    {"type": {"$regex": rx, "$options": "i"}},
                    {"block": {"$regex": rx, "$options": "i"}},
                    {"lead_name": {"$regex": rx, "$options": "i"}}]
    return q


async def unit_rows(org: str = ORG_ID, *, skip: int = 0, limit: int = 25,
                    sort: str = "code", direction: str = "asc", **filters) -> dict:
    """Baris papan unit + ringkasan. Filter turunan (telat/kesiapan) disaring setelah hitung."""
    ref = today_iso_date()
    q = _unit_query(org, filters)
    units = await db.units.find(q, {"_id": 0}).to_list(3000)
    unit_ids = [u["id"] for u in units]
    scheds = await db.build_schedules.find({"org_id": org, "unit_id": {"$in": unit_ids}},
                                           {"_id": 0}).to_list(3000)
    smap = {s["unit_id"]: s for s in scheds}
    items = await db.build_items.find(
        {"org_id": org, "schedule_id": {"$in": [s["id"] for s in scheds]}},
        {"_id": 0, "id": 1, "schedule_id": 1, "name": 1, "status": 1, "order": 1,
         "planned_finish": 1, "assigned_to": 1, "verified_at": 1, "verified_by": 1,
         "submitted_at": 1, "submitted_by": 1, "evidence": 1}).sort("order", 1).to_list(20000)
    imap = {}
    for i in items:
        imap.setdefault(i["schedule_id"], []).append(i)
    pays = await _payments(org, unit_ids)
    block_codes = list(await cfg.get("permit.block_build_without", org_id=org) or [])
    require_dp = bool(await cfg.get("build.require_dp_before_start", org_id=org))

    rows = []
    projects = {p["id"]: p.get("name") for p in await db.projects.find(
        {"org_id": org}, {"_id": 0, "id": 1, "name": 1}).to_list(200)}
    for u in units:
        sched = smap.get(u["id"])
        row = _row_of(u, sched, imap.get((sched or {}).get("id"), []), pays.get(u["id"]), ref)
        row["project_name"] = projects.get(u.get("project_id"))
        permit_missing = False
        if block_codes:
            cov = await ps.coverage(org, unit_id=u["id"], required_codes=block_codes)
            permit_missing = bool(cov["missing_codes"])
            row["permit_missing_codes"] = cov["missing_codes"]
        row.update(_readiness_hint(row, block_codes, permit_missing, require_dp))
        rows.append(row)

    summary = {
        "units_total": len(rows),
        "scheduled": sum(1 for r in rows if r["schedule_id"]),
        "unscheduled": sum(1 for r in rows if not r["schedule_id"]),
        "late": sum(1 for r in rows if (r["days_late"] or 0) > 0),
        "on_hold": sum(1 for r in rows if r["schedule_status"] == "on_hold"),
        "awaiting_verification": sum(
            1 for r in rows if (r["active_step"] or {}).get("status") == "submitted"),
        "ready_to_start": sum(1 for r in rows if r["readiness"] == "ready"),
        "warning_to_start": sum(1 for r in rows if r["readiness"] == "warning"),
        "blocked_to_start": sum(1 for r in rows if r["readiness"] == "blocked"),
        "running": sum(1 for r in rows if r["readiness"] == "started"),
        # JUJUR: rata-rata hanya dari unit yang punya jadwal; bila tidak ada → None.
        "avg_progress": None, "avg_planned": None,
    }
    prog = [r["actual_progress"] for r in rows if r["actual_progress"] is not None]
    plan = [r["planned_progress"] for r in rows if r["planned_progress"] is not None]
    if prog:
        summary["avg_progress"] = round(sum(prog) / len(prog), 1)
    if plan:
        summary["avg_planned"] = round(sum(plan) / len(plan), 1)

    if filters.get("late_only"):
        rows = [r for r in rows if (r["days_late"] or 0) > 0]
    if filters.get("unscheduled_only"):
        rows = [r for r in rows if not r["schedule_id"]]
    if filters.get("readiness"):
        want = list(filters["readiness"])
        rows = [r for r in rows if r["readiness"] in want]

    key = sort if sort in SORTABLE or sort in DERIVED_SORT else "code"
    rev = str(direction).lower() == "desc"

    def _sk(r):
        v = r.get(key)
        if v is None:
            return (1, "") if isinstance(r.get("code"), str) and key in SORTABLE else (1, 0)
        return (0, v)

    try:
        rows.sort(key=_sk, reverse=rev)
    except TypeError:
        rows.sort(key=lambda r: str(r.get(key) or ""), reverse=rev)
    total = len(rows)
    page = rows[skip:skip + limit] if limit else rows
    return {"data": page, "total": total, "summary": summary, "as_of": ref,
            "mode": {"block_build_without": block_codes,
                     "require_dp_before_start": require_dp,
                     "enforced": bool(block_codes or require_dp)}}
