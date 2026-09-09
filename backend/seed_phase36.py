"""Seed Fase 36 — MASTER kalender kerja + hari libur bawaan + inspeksi demo terjadwal.

Jujur soal daftar hari libur: tanggal libur keagamaan Indonesia ditetapkan lewat SKB
tiga menteri dan bisa bergeser 1–2 hari dari perkiraan astronomis. Karena itu daftar di
sini ditandai eksplisit sebagai **bawaan yang wajib disesuaikan admin** (`note` pada tiap
baris + `note` pada dokumen kalender), dan seluruhnya bisa diubah/dihapus dari layar
Kalender Jadwal → Pengaturan kalender kerja. Aplikasi TIDAK berpura-pura ini keputusan resmi.

Seed ini idempoten: kalender hanya dibuat bila organisasi belum punya, dan inspeksi demo
hanya dijadwalkan bila `scheduled_date`-nya masih kosong.
"""
import logging
from datetime import timedelta

import build_calendar as bcal
from core_utils import new_id, now, now_iso
from db import db, ORG_ID

logger = logging.getLogger("sipro.seed")

SOURCE_NOTE = ("Daftar bawaan SIPRO (perkiraan libur nasional 2026). WAJIB disesuaikan "
               "dengan SKB pemerintah oleh admin — tanggal libur keagamaan bisa bergeser.")

# (tanggal, nama, jenis) — jenis mengikuti SSOT `holiday_kind`.
HOLIDAYS_2026 = [
    ("2026-01-01", "Tahun Baru 2026", "national"),
    ("2026-01-16", "Isra Mikraj Nabi Muhammad", "religious"),
    ("2026-02-17", "Tahun Baru Imlek 2577", "religious"),
    ("2026-03-19", "Hari Suci Nyepi (Tahun Baru Saka 1948)", "religious"),
    ("2026-03-20", "Idul Fitri 1447H (hari pertama)", "religious"),
    ("2026-03-21", "Idul Fitri 1447H (hari kedua)", "religious"),
    ("2026-03-23", "Cuti bersama Idul Fitri", "company"),
    ("2026-04-03", "Wafat Isa Almasih", "religious"),
    ("2026-05-01", "Hari Buruh Internasional", "national"),
    ("2026-05-14", "Kenaikan Isa Almasih", "religious"),
    ("2026-05-27", "Idul Adha 1447H", "religious"),
    ("2026-05-31", "Hari Raya Waisak 2570", "religious"),
    ("2026-06-01", "Hari Lahir Pancasila", "national"),
    ("2026-06-16", "Tahun Baru Islam 1448H", "religious"),
    ("2026-08-17", "Hari Kemerdekaan Republik Indonesia", "national"),
    ("2026-08-25", "Maulid Nabi Muhammad", "religious"),
    ("2026-12-25", "Hari Raya Natal", "national"),
    ("2027-01-01", "Tahun Baru 2027", "national"),
]


def default_holidays() -> list:
    return [{"date": d, "name": n, "kind": k, "note": SOURCE_NOTE} for d, n, k in HOLIDAYS_2026]


async def _ensure_calendar(org: str) -> int:
    if await db.build_work_calendars.count_documents({"org_id": org, "project_id": None}):
        return 0
    await db.build_work_calendars.insert_one({
        "id": new_id(), "org_id": org, "project_id": None,
        "pattern": dict(bcal.DEFAULT_PATTERN),
        "thresholds": dict(bcal.DEFAULT_THRESHOLDS),
        "holidays": default_holidays(),
        "note": SOURCE_NOTE,
        "updated_by": "system (bawaan organisasi)",
        "updated_at": now_iso(), "created_at": now_iso()})
    return 1


async def _schedule_demo_inspections(org: str) -> int:
    """Inspeksi demo diberi tanggal rencana supaya lapisan QC kalender tidak kosong.

    Hanya menyentuh inspeksi yang MASIH berjalan dan belum bertanggal; tanggalnya diambil
    dari hari kerja terdekat (mengikuti master kalender) agar tidak mendarat di hari libur.
    """
    cal = await bcal.resolve(org, None)
    rows = await db.inspections.find(
        {"org_id": org, "status": "in_progress",
         "$or": [{"scheduled_date": {"$exists": False}}, {"scheduled_date": None},
                 {"scheduled_date": ""}]},
        {"_id": 0, "id": 1}).sort("created_at", 1).to_list(20)
    made = 0
    for idx, r in enumerate(rows):
        target = bcal.next_workday(cal, now().date() + timedelta(days=2 + idx * 3))
        await db.inspections.update_one({"id": r["id"]}, {"$set": {
            "scheduled_date": target.isoformat(),
            "scheduled_by": "system (penyiapan data awal)",
            "scheduled_note": "Dijadwalkan otomatis saat penyiapan data demo.",
            "updated_at": now_iso()}})
        made += 1
    return made


async def _demo_unscheduled_inspection(org: str) -> int:
    """Satu inspeksi MEP demo yang SENGAJA belum bertanggal.

    Alasannya jujur: layar Kalender Jadwal punya dua keadaan yang harus terlihat sejak
    data demo — (1) inspeksi yang sudah punya tanggal muncul di kalender, dan (2) inspeksi
    yang BELUM bertanggal tampil di panel "belum dijadwalkan" beserta ajakan menjadwalkan.
    Tanpa contoh kedua, panel itu tidak pernah terlihat pada database baru.
    """
    if await db.inspections.count_documents({"org_id": org, "template_code": "QC-MEP"}):
        return 0
    project = await db.projects.find_one({"org_id": org}, {"_id": 0, "id": 1, "name": 1})
    if not project:
        return 0
    tpl = await db.inspection_templates.find_one({"org_id": org, "code": "QC-MEP"}, {"_id": 0})
    if not tpl:
        return 0
    unit = await db.units.find_one({"org_id": org, "project_id": project["id"]},
                                   {"_id": 0, "id": 1}) or {}
    items = [{"key": it["key"], "label": it["label"], "result": "pending", "note": None}
             for it in tpl.get("items") or []]
    ts = now_iso()
    await db.inspections.insert_one({
        "id": new_id(), "org_id": org, "inspection_number": f"QC/{ts[:4]}/0009",
        "project_id": project["id"], "project_name": project.get("name"),
        "unit_id": unit.get("id"), "phase_id": None, "template_id": tpl.get("id"),
        "template_code": "QC-MEP", "category": tpl.get("category") or "mep",
        "title": tpl.get("name") or "Inspeksi MEP", "items": items, "status": "in_progress",
        "pass_count": 0, "fail_count": 0, "na_count": 0, "pending_count": len(items),
        "punch_ids": [], "punch_created": False, "result_note": None,
        "created_by": "site@sipro.co.id", "created_at": ts, "updated_at": ts,
        "finalized_by": None, "finalized_at": None,
        "scheduled_date": None, "scheduled_by": None, "scheduled_note": None})
    return 1


async def seed_phase36(org_id: str = ORG_ID) -> dict:
    """Dipanggil di lifespan `server.py` setelah seed Fase 33 (butuh inspeksi & jadwal)."""
    await bcal.ensure_indexes()
    out = {"calendar": await _ensure_calendar(org_id)}
    out["inspections_scheduled"] = await _schedule_demo_inspections(org_id)
    out["inspection_unscheduled"] = await _demo_unscheduled_inspection(org_id)
    if out["calendar"] or out["inspections_scheduled"]:
        logger.info("Seed Fase 36: %s kalender kerja (%s hari libur bawaan), "
                    "%s inspeksi demo dijadwalkan, %s inspeksi menunggu dijadwalkan.",
                    out["calendar"], len(HOLIDAYS_2026), out["inspections_scheduled"],
                    out["inspection_unscheduled"])
    return out
