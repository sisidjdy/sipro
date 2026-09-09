"""LAPORAN MINGGUAN PEMBANGUNAN (Fase 32).

Permintaan owner: "Kirim ringkasan progres tiap rumah ke direksi setiap Senin, lengkap
grafik rencana vs realisasi" + "unduh PDF untuk dibagikan ke investor/rapat".

Karakter penting:
  * **Idempoten per pekan** (kunci `org_id + project_id + week_key`) — dijalankan ulang
    tidak membuat laporan ganda; angka di-refresh, tetapi tugas & notifikasi tidak dobel.
  * Angka diambil dari data terverifikasi (`build_items`/`build_schedules`), bukan input
    manual — jadi laporan tidak bisa "dipercantik".
  * Grafik rencana vs realisasi dihitung per minggu template: `planned` = bobot yang
    seharusnya selesai s/d minggu itu, `actual` = bobot yang benar-benar diverifikasi.
"""
import io
import logging
from datetime import date, timedelta

import workhub as wh
from core_utils import new_id, now_iso, today_iso_date
from db import db
from engine import create_notification
from reference_p31 import DELAY_CAUSE_LABEL

logger = logging.getLogger("sipro.build.reports")
COLLECTION = "build_weekly_reports"   # nama koleksi eksplisit dipakai di router & audit


def week_key(d: date) -> str:
    iso = d.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def week_bounds(d: date) -> tuple:
    start = d - timedelta(days=d.weekday())          # Senin
    return start, start + timedelta(days=6)          # Minggu


def _dev_tone(dev: float) -> str:
    if dev >= -2:
        return "on_track"
    return "behind" if dev >= -10 else "critical"


async def _project_curve(org: str, project_id: str) -> list:
    """Kurva rencana vs realisasi tingkat proyek (rata-rata berbobot antar rumah)."""
    items = await db.build_items.find(
        {"org_id": org, "project_id": project_id},
        {"_id": 0, "week": 1, "weight": 1, "status": 1, "schedule_id": 1}).to_list(5000)
    if not items:
        return []
    total = sum(float(i.get("weight") or 0) for i in items) or 1
    weeks = sorted({int(i.get("week") or 1) for i in items})
    out, cum_plan, cum_act = [], 0.0, 0.0
    for w in weeks:
        rows = [i for i in items if int(i.get("week") or 1) == w]
        cum_plan += sum(float(i.get("weight") or 0) for i in rows)
        cum_act += sum(float(i.get("weight") or 0) for i in rows if i.get("status") == "done")
        out.append({"week": w, "label": f"M{w}",
                    "planned": round(cum_plan / total * 100, 1),
                    "actual": round(cum_act / total * 100, 1)})
    return out


async def _houses(org: str, project_id: str, period_start: str, period_end: str) -> list:
    scheds = await db.build_schedules.find(
        {"org_id": org, "project_id": project_id}, {"_id": 0}).sort("unit_code", 1).to_list(500)
    rows = []
    for s in scheds:
        verified = await db.build_items.count_documents(
            {"org_id": org, "schedule_id": s["id"], "status": "done",
             "verified_at": {"$gte": period_start, "$lte": period_end + "T23:59:59+00:00"}})
        causes = await db.build_items.find(
            {"org_id": org, "schedule_id": s["id"], "delay_cause": {"$ne": None}},
            {"_id": 0, "delay_cause": 1}).to_list(100)
        top = None
        if causes:
            tally = {}
            for c in causes:
                tally[c["delay_cause"]] = tally.get(c["delay_cause"], 0) + 1
            code = max(tally, key=tally.get)
            top = {"cause": code, "label": DELAY_CAUSE_LABEL.get(code, code),
                   "count": tally[code]}
        rows.append({
            "unit_id": s.get("unit_id"), "unit_code": s.get("unit_code"),
            "unit_type": s.get("unit_type"), "status": s.get("status"),
            "progress": s.get("progress", 0), "planned_progress": s.get("planned_progress", 0),
            "deviation": s.get("deviation", 0), "deviation_days": s.get("deviation_days", 0),
            "items_done": s.get("items_done", 0), "items_total": s.get("items_total", 0),
            "late_items": s.get("late_items", 0), "blocked_items": s.get("blocked_items", 0),
            "overrides": s.get("overrides", 0),
            "target_finish_date": s.get("target_finish_date"),
            "buyer": s.get("lead_name"), "verified_this_week": verified,
            "top_delay_cause": top, "tone": _dev_tone(float(s.get("deviation") or 0)),
        })
    return rows


async def _delay_highlights(org: str, project_id: str, limit: int = 5) -> list:
    ref = today_iso_date()
    items = await db.build_items.find(
        {"org_id": org, "project_id": project_id, "status": {"$ne": "done"},
         "planned_finish": {"$lt": ref}},
        {"_id": 0, "step_code": 1, "name": 1, "unit_code": 1, "planned_finish": 1,
         "delay_cause": 1}).to_list(1000)
    tally = {}
    for it in items:
        key = it.get("step_code") or it.get("name")
        days = (date.fromisoformat(ref)
                - date.fromisoformat(str(it["planned_finish"])[:10])).days
        row = tally.setdefault(key, {"step_code": it.get("step_code"), "name": it.get("name"),
                                     "units": 0, "days_total": 0, "max_days": 0,
                                     "unit_codes": []})
        row["units"] += 1
        row["days_total"] += days
        row["max_days"] = max(row["max_days"], days)
        if len(row["unit_codes"]) < 6:
            row["unit_codes"].append(it.get("unit_code"))
    out = []
    for r in tally.values():
        out.append({**r, "avg_days": round(r["days_total"] / max(1, r["units"]), 1)})
    out.sort(key=lambda r: (-r["units"], -r["avg_days"]))
    return out[:limit]


async def build_report(org: str, project: dict, ref: date, actor: str) -> dict:
    """Susun (atau segarkan) laporan satu proyek untuk satu pekan."""
    start, end = week_bounds(ref)
    wk = week_key(ref)
    houses = await _houses(org, project["id"], start.isoformat(), end.isoformat())
    scheduled = len(houses)
    avg_p = round(sum(h["progress"] for h in houses) / scheduled, 1) if scheduled else 0
    avg_plan = round(sum(h["planned_progress"] for h in houses) / scheduled, 1) if scheduled else 0
    totals = {
        "units_scheduled": scheduled,
        "avg_progress": avg_p, "avg_planned": avg_plan,
        "deviation": round(avg_p - avg_plan, 1),
        "on_track": sum(1 for h in houses if h["tone"] == "on_track"),
        "behind": sum(1 for h in houses if h["tone"] == "behind"),
        "critical": sum(1 for h in houses if h["tone"] == "critical"),
        "done": sum(1 for h in houses if h["status"] == "done"),
        "on_hold": sum(1 for h in houses if h["status"] == "on_hold"),
        "late_items": sum(h["late_items"] for h in houses),
        "blocked_items": sum(h["blocked_items"] for h in houses),
        "overrides": sum(h["overrides"] for h in houses),
        "verified_this_week": sum(h["verified_this_week"] for h in houses),
    }
    existing = await db.build_weekly_reports.find_one(
        {"org_id": org, "project_id": project["id"], "week_key": wk}, {"_id": 0})
    doc = {
        "id": (existing or {}).get("id") or new_id(),
        "org_id": org, "project_id": project["id"], "project_name": project.get("name"),
        "week_key": wk, "period_start": start.isoformat(), "period_end": end.isoformat(),
        "totals": totals, "houses": houses,
        "curve": await _project_curve(org, project["id"]),
        "delays_top": await _delay_highlights(org, project["id"]),
        "generated_at": now_iso(), "generated_by": actor,
        "created_at": (existing or {}).get("created_at") or now_iso(),
    }
    await db.build_weekly_reports.update_one(
        {"org_id": org, "project_id": project["id"], "week_key": wk},
        {"$set": doc}, upsert=True)
    return {"report": doc, "is_new": existing is None}


async def _recipients(org: str) -> list:
    rows = await db.users.find(
        {"org_id": org, "is_active": True,
         "role": {"$in": ["owner", "super_admin", "project_manager"]}},
        {"_id": 0, "email": 1}).to_list(50)
    return [r["email"] for r in rows]


async def run_weekly(org: str, project_id: str = None, actor: str = "system",
                     ref_date: str = None) -> dict:
    """Jalankan laporan mingguan (dipakai scheduler Senin & tombol manual PM/owner)."""
    ref = date.fromisoformat(ref_date) if ref_date else date.fromisoformat(today_iso_date())
    q = {"org_id": org}
    if project_id:
        q["id"] = project_id
    projects = await db.projects.find(q, {"_id": 0, "id": 1, "name": 1}).to_list(200)
    made, refreshed, reports = 0, 0, []
    for p in projects:
        if not await db.build_schedules.count_documents({"org_id": org, "project_id": p["id"]}):
            continue
        out = await build_report(org, p, ref, actor)
        rep = out["report"]
        reports.append({"id": rep["id"], "project_id": p["id"], "project_name": p.get("name"),
                        "week_key": rep["week_key"], "is_new": out["is_new"],
                        "totals": rep["totals"]})
        if out["is_new"]:
            made += 1
        else:
            refreshed += 1
        # Selalu dipanggil: pembuatan tugas & notifikasi sudah idempoten per (laporan,
        # penerima). Dulu hanya dipanggil saat laporan BARU, sehingga penerima yang
        # belum punya tugas baca (mis. PM yang baru ditugaskan tengah pekan) tidak
        # pernah tahu ada laporan.
        await _announce(org, rep)
    return {"week_key": week_key(ref), "created": made, "refreshed": refreshed,
            "reports": reports}


async def _announce(org: str, rep: dict):
    """Notifikasi + TUGAS BACA untuk direksi & manajer proyek (idempoten per penerima)."""
    t = rep["totals"]
    body = (f"{rep.get('project_name')} pekan {rep['week_key']}: rata-rata progres "
            f"{t['avg_progress']}% vs rencana {t['avg_planned']}% "
            f"({t['deviation']:+}%), {t['late_items']} pekerjaan telat, "
            f"{t['verified_this_week']} pekerjaan diverifikasi pekan ini.")
    link = f"/construction?tab=reports&report={rep['id']}"
    for email in await _recipients(org):
        # `source_event` HARUS memuat penerima: idempotensi Work Hub berbasis
        # (org, source_event) — tanpa email, hanya penerima pertama yang dapat tugas
        # dan direksi lain tidak pernah tahu ada laporan.
        rows = await wh.spawn(
            org, "TK-14", source_event=f"build.weekly_report:{rep['id']}:{email}",
            assignee_override=email, entity_type="project",
            entity_id=rep["project_id"],
            title=f"Baca laporan mingguan {rep['week_key']} — {rep.get('project_name')}",
            description=body, link=link,
            meta={"weekly_report_id": rep["id"], "week_key": rep["week_key"]})
        # Notifikasi menempel pada pembuatan tugas supaya penyegaran laporan tidak
        # membanjiri direksi dengan pemberitahuan yang sama berulang kali.
        if rows:
            await create_notification(
                user_email=email, title=f"Laporan mingguan pembangunan {rep['week_key']}",
                body=body, type="info", related_entity_type="project",
                related_entity_id=rep["project_id"], org_id=org)


# ================================ PDF ================================
def pdf_bytes(rep: dict, org_name: str = "PT SIPRO Land") -> bytes:
    """PDF ringkas untuk rapat/investor — tabel per rumah + rencana vs realisasi."""
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import (Paragraph, SimpleDocTemplate, Spacer, Table,
                                    TableStyle)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), topMargin=16 * mm,
                            bottomMargin=14 * mm, leftMargin=14 * mm, rightMargin=14 * mm,
                            title=f"Laporan Mingguan {rep.get('week_key')}")
    st = getSampleStyleSheet()
    s_org = ParagraphStyle("o", parent=st["Normal"], fontSize=9, alignment=TA_CENTER,
                           textColor=colors.HexColor("#0f766e"))
    s_title = ParagraphStyle("t", parent=st["Title"], fontSize=15, spaceAfter=2)
    s_sub = ParagraphStyle("s", parent=st["Normal"], fontSize=8.5, alignment=TA_CENTER,
                           textColor=colors.HexColor("#64748b"))
    s_h = ParagraphStyle("h", parent=st["Normal"], fontSize=10.5, spaceBefore=8,
                         spaceAfter=4, textColor=colors.HexColor("#0f172a"))
    s_b = ParagraphStyle("b", parent=st["Normal"], fontSize=8.5, leading=12)
    t = rep.get("totals") or {}
    flow = [
        Paragraph(org_name, s_org),
        Paragraph(f"Laporan Mingguan Pembangunan — {rep.get('week_key')}", s_title),
        Paragraph(f"{rep.get('project_name')} · periode {rep.get('period_start')} "
                  f"s/d {rep.get('period_end')} · dibuat {str(rep.get('generated_at'))[:16]}",
                  s_sub),
        Spacer(1, 10),
        Paragraph("Ringkasan", s_h),
    ]
    summary = [
        ["Rumah terjadwal", t.get("units_scheduled", 0),
         "Progres rata-rata", f"{t.get('avg_progress', 0)}%",
         "Rencana", f"{t.get('avg_planned', 0)}%"],
        ["Deviasi", f"{t.get('deviation', 0):+}%",
         "Sesuai jadwal", t.get("on_track", 0),
         "Tertinggal", t.get("behind", 0)],
        ["Kritis", t.get("critical", 0),
         "Pekerjaan telat", t.get("late_items", 0),
         "Diverifikasi pekan ini", t.get("verified_this_week", 0)],
        ["Tertahan gerbang", t.get("blocked_items", 0),
         "Gerbang diterobos", t.get("overrides", 0),
         "Dihentikan sementara", t.get("on_hold", 0)],
    ]
    tbl = Table(summary, colWidths=[38 * mm, 22 * mm, 40 * mm, 22 * mm, 40 * mm, 22 * mm])
    tbl.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#475569")),
        ("TEXTCOLOR", (2, 0), (2, -1), colors.HexColor("#475569")),
        ("TEXTCOLOR", (4, 0), (4, -1), colors.HexColor("#475569")),
        ("FONTNAME", (1, 0), (1, -1), "Helvetica-Bold"),
        ("FONTNAME", (3, 0), (3, -1), "Helvetica-Bold"),
        ("FONTNAME", (5, 0), (5, -1), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#e2e8f0")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    flow += [tbl, Paragraph("Progres tiap rumah (rencana vs realisasi)", s_h)]
    head = ["Unit", "Tipe", "Pembeli", "Progres", "Rencana", "Deviasi", "Hari telat",
            "Item selesai", "Telat", "Tertahan", "Target selesai", "Penyebab telat utama"]
    rows = [head]
    for h in rep.get("houses") or []:
        rows.append([
            h.get("unit_code") or "-", h.get("unit_type") or "-",
            (h.get("buyer") or "belum ada")[:18],
            f"{h.get('progress', 0)}%", f"{h.get('planned_progress', 0)}%",
            f"{h.get('deviation', 0):+}%", h.get("deviation_days", 0),
            f"{h.get('items_done', 0)}/{h.get('items_total', 0)}",
            h.get("late_items", 0), h.get("blocked_items", 0),
            str(h.get("target_finish_date") or "-"),
            ((h.get("top_delay_cause") or {}).get("label") or "-")[:22],
        ])
    ht = Table(rows, repeatRows=1)
    ht.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 7.5),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f766e")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#e2e8f0")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
        ("ALIGN", (3, 1), (9, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    flow.append(ht)
    curve = rep.get("curve") or []
    if curve:
        flow.append(Paragraph("Kurva rencana vs realisasi (kumulatif per minggu)", s_h))
        crows = [["Minggu"] + [c["label"] for c in curve],
                 ["Rencana %"] + [c["planned"] for c in curve],
                 ["Realisasi %"] + [c["actual"] for c in curve]]
        ct = Table(crows)
        ct.setStyle(TableStyle([
            ("FONTSIZE", (0, 0), (-1, -1), 7.5),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#e2e8f0")),
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
            ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ]))
        flow.append(ct)
    delays = rep.get("delays_top") or []
    if delays:
        flow.append(Paragraph("Pekerjaan paling sering telat pekan ini", s_h))
        for d in delays:
            flow.append(Paragraph(
                f"• <b>{d.get('step_code')} {d.get('name')}</b> — {d.get('units')} rumah, "
                f"rata-rata {d.get('avg_days')} hari (maksimal {d.get('max_days')} hari): "
                f"{', '.join([u for u in (d.get('unit_codes') or []) if u])}", s_b))
    flow += [Spacer(1, 12), Paragraph(
        "Angka pada laporan ini dihitung dari pekerjaan yang sudah diverifikasi beserta "
        "bukti fotonya — bukan progres yang diketik manual.", s_sub)]
    doc.build(flow)
    return buf.getvalue()
