"""ABSENSI & UPAH HARIAN TENAGA KERJA (Fase 47D) — orang, hari, rupiah, dan pembukuannya.

Cacat yang ditutup: tenaga kerja harian hanya berupa SATU ANGKA di buku harian
(`site_diaries.workforce`). Tidak ada daftar orang, tidak ada absensi, tidak ada upah, dan
biaya upah — komponen biaya konstruksi yang paling sering bocor — tidak pernah masuk
pembukuan maupun realisasi anggaran. `docs/v2/29` §1 sudah menjanjikan "absensi mandor" di
tab Lapangan sejak awal; Fase 47 menepatinya.

Aturan yang dipegang:

  1. **Satu orang satu catatan per hari per proyek** — dijaga index unik di MongoDB
     (`uq_labor_attendance`), bukan sekadar pengecekan aplikasi, karena absensi ganda
     langsung menjadi upah ganda.
  2. **Upah bisa direkonstruksi**: `hari_efektif × upah_harian + jam_lembur × tarif_lembur`,
     dengan `hari_efektif` dari `ATTENDANCE_DAY_FACTOR` (hadir 1, setengah hari 0,5, absen &
     izin 0). Tarif lembur = `upah_harian / jam_kerja_normal × pengali_lembur` (dua-duanya
     setting admin). Setiap rekap menyimpan baris per orang beserta angka pembentuknya.
  3. **Rekap upah punya siklus persetujuan**: draf → diajukan → disetujui keuangan → dibayar.
     Pembayaran melahirkan jurnal (Dr WIP proyek / Cr Bank) dan — bila `budget_item_id`
     disebut — masuk realisasi anggaran lewat `cost_ref` (Fase 45), sehingga tidak ada biaya
     upah yang "hilang" dari laporan proyek.
  4. **Selisih dengan buku harian dilaporkan, tidak ditimpa.** Bila buku harian menulis 8
     pekerja sedangkan absensi mencatat 6, keduanya tetap apa adanya dan sistem menampilkan
     peringatan selisih — menimpa salah satunya berarti membuang bukti.
  5. **Periode yang sudah punya rekap dikunci**: absensi pada rentang tanggal yang sudah
     masuk rekap disetujui/dibayar tidak bisa diubah tanpa membatalkan rekapnya.
"""
import logging
from datetime import date

import gl_engine as gl
import sequences as seq
import settings_store as cfg
from core_utils import new_id, now_iso
from db import ORG_ID, db
from engine import add_activity, create_notification, emit
from reference_p47 import (ATTENDANCE_DAY_FACTOR, ATTENDANCE_LABEL, GL_BANK, GL_WIP,
                          LABOR_ROLE_LABEL, PAYROLL_LABEL)

logger = logging.getLogger("sipro.labor")
LOCKED_PAYROLL = ("submitted", "approved", "paid")


# ============================================================ master tenaga kerja
async def create_worker(org: str, payload: dict, actor: str) -> dict:
    name = str(payload.get("name") or "").strip()
    if await db.workers.find_one({"org_id": org, "name": name}, {"_id": 0, "id": 1}):
        raise ValueError(f"Tenaga kerja '{name}' sudah terdaftar — pakai data yang ada "
                         "agar riwayat upahnya tidak terpecah.")
    ts = now_iso()
    doc = {"id": new_id(), "org_id": org, "name": name,
           "role": payload.get("role"), "role_label": LABOR_ROLE_LABEL.get(payload.get("role")),
           "daily_wage": int(payload.get("daily_wage") or 0),
           "phone": payload.get("phone"), "subcon_id": payload.get("subcon_id"),
           "project_ids": payload.get("project_ids") or [], "note": payload.get("note"),
           "is_active": bool(payload.get("is_active", True)),
           "created_by": actor, "created_at": ts, "updated_at": ts}
    await db.workers.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


async def update_worker(org: str, worker_id: str, patch: dict, actor: str) -> dict:
    upd = {k: v for k, v in (patch or {}).items() if v is not None}
    if not upd:
        raise ValueError("Tidak ada perubahan.")
    if "role" in upd:
        upd["role_label"] = LABOR_ROLE_LABEL.get(upd["role"])
    upd["updated_at"] = now_iso()
    upd["updated_by"] = actor
    res = await db.workers.update_one({"id": worker_id, "org_id": org}, {"$set": upd})
    if not res.matched_count:
        raise ValueError("Tenaga kerja tidak ditemukan.")
    return await db.workers.find_one({"id": worker_id}, {"_id": 0})


async def workers(org: str = ORG_ID, *, project_id: str = None, active: bool = None,
                  q: str = None) -> list:
    query = {"org_id": org}
    if active is not None:
        query["is_active"] = active
    if q:
        query["name"] = {"$regex": str(q).strip(), "$options": "i"}
    rows = await db.workers.find(query, {"_id": 0}).sort("name", 1).to_list(500)
    if project_id:
        rows = [r for r in rows if not r.get("project_ids")
                or project_id in r["project_ids"]]
    return rows


# ============================================================ tarif & matematika upah
async def rates(org: str = ORG_ID) -> dict:
    """Aturan hitung upah dari konfigurasi — satu sumber untuk papan, rekap, dan gate."""
    return {
        "overtime_multiplier": float(await cfg.get("labor.overtime_multiplier",
                                                  org_id=org) or 1.5),
        "normal_hours": float(await cfg.get("labor.normal_hours_per_day", org_id=org) or 8),
        "day_factor": dict(ATTENDANCE_DAY_FACTOR),
    }


def wage_of(entry: dict, daily_wage: int, rate: dict) -> dict:
    """Upah satu baris absensi + angka pembentuknya (bisa dijelaskan ke tukangnya)."""
    factor = ATTENDANCE_DAY_FACTOR.get(entry.get("status"), 0.0)
    base = int(round(int(daily_wage or 0) * factor))
    hours = float(entry.get("overtime_hours") or 0)
    hourly = (int(daily_wage or 0) / rate["normal_hours"]) if rate["normal_hours"] else 0
    overtime = int(round(hours * hourly * rate["overtime_multiplier"])) if factor > 0 else 0
    return {"day_factor": factor, "base_wage": base, "overtime_hours": hours,
            "overtime_wage": overtime, "total": base + overtime,
            "formula": (f"{factor:g} hari × Rp {int(daily_wage or 0):,}"
                        + (f" + {hours:g} jam × Rp {int(round(hourly)):,} × "
                           f"{rate['overtime_multiplier']:g}" if overtime else "")
                        ).replace(",", ".")}


# ============================================================ absensi harian
async def _locked_payroll(org: str, project_id: str, work_date: str) -> dict:
    return await db.labor_payrolls.find_one(
        {"org_id": org, "project_id": project_id, "state": {"$in": list(LOCKED_PAYROLL)},
         "period_start": {"$lte": work_date}, "period_end": {"$gte": work_date}},
        {"_id": 0, "no": 1, "state": 1})


async def record_attendance(org: str, *, project_id: str, work_date: str, entries: list,
                            actor: str) -> dict:
    """Catat absensi satu hari. Menolak orang kembar & periode yang sudah direkap."""
    project = await db.projects.find_one({"id": project_id, "org_id": org}, {"_id": 0})
    if not project:
        raise ValueError("Proyek tidak ditemukan.")
    day = str(work_date)[:10]
    try:
        if date.fromisoformat(day) > date.fromisoformat(now_iso()[:10]):
            raise ValueError("Absensi tidak boleh diisi untuk tanggal yang belum terjadi.")
    except ValueError as e:
        if "belum terjadi" in str(e):
            raise
        raise ValueError("Tanggal absensi tidak sah (format YYYY-MM-DD).") from e
    locked = await _locked_payroll(org, project_id, day)
    if locked:
        raise ValueError(f"Tanggal {day} sudah masuk rekap upah {locked['no']} "
                        f"({PAYROLL_LABEL.get(locked['state'], locked['state'])}) — "
                         "batalkan rekap itu dulu bila absensinya perlu dikoreksi.")
    ids = [e["worker_id"] if isinstance(e, dict) else e.worker_id for e in entries]
    if len(set(ids)) != len(ids):
        raise ValueError("Ada tenaga kerja yang tercatat dua kali dalam satu kiriman.")
    rate = await rates(org)
    saved, ts = [], now_iso()
    for e in entries:
        row = e if isinstance(e, dict) else e.model_dump()
        worker = await db.workers.find_one({"id": row["worker_id"], "org_id": org}, {"_id": 0})
        if not worker:
            raise ValueError(f"Tenaga kerja {row['worker_id']} tidak ditemukan.")
        if worker.get("is_active") is False:
            raise ValueError(f"{worker.get('name')} sudah tidak aktif — aktifkan dulu "
                             "di master tenaga kerja.")
        calc = wage_of(row, worker.get("daily_wage"), rate)
        doc = {
            "org_id": org, "project_id": project_id, "project_name": project.get("name"),
            "work_date": day, "worker_id": worker["id"], "worker_name": worker.get("name"),
            "role": worker.get("role"), "role_label": worker.get("role_label"),
            "daily_wage": int(worker.get("daily_wage") or 0),
            "status": row["status"], "status_label": ATTENDANCE_LABEL.get(row["status"]),
            "overtime_hours": float(row.get("overtime_hours") or 0),
            "unit_id": row.get("unit_id"), "note": row.get("note"),
            **calc, "payroll_id": None, "recorded_by": actor, "updated_at": ts,
        }
        existing = await db.labor_attendance.find_one(
            {"org_id": org, "project_id": project_id, "work_date": day,
             "worker_id": worker["id"]}, {"_id": 0, "id": 1, "status": 1})
        if existing:
            await db.labor_attendance.update_one({"id": existing["id"]}, {
                "$set": doc,
                "$push": {"history": {"at": ts, "by": actor, "from": existing.get("status"),
                                      "to": row["status"]}}})
            doc["id"] = existing["id"]
            doc["action"] = "updated"
        else:
            doc.update({"id": new_id(), "created_at": ts, "history": []})
            await db.labor_attendance.insert_one(dict(doc))
            doc["action"] = "created"
        doc.pop("_id", None)
        saved.append(doc)
    await add_activity(entity_type="project", entity_id=project_id, type="construction",
                       actor=actor, org_id=org,
                       body=(f"Absensi {day}: {len([s for s in saved if s['day_factor'] > 0])} "
                             f"orang hadir dari {len(saved)} tercatat."))
    return {"work_date": day, "project_id": project_id, "entries": saved,
            "present": len([s for s in saved if s["day_factor"] > 0]),
            "wage_total": sum(s["total"] for s in saved),
            "diary": await diary_check(org, project_id, day)}


async def diary_check(org: str, project_id: str, work_date: str) -> dict:
    """Bandingkan jumlah hadir dengan `site_diaries.workforce` hari itu — JUJUR soal selisih."""
    day = str(work_date)[:10]
    rows = await db.labor_attendance.find(
        {"org_id": org, "project_id": project_id, "work_date": day},
        {"_id": 0, "day_factor": 1}).to_list(500)
    present = len([r for r in rows if float(r.get("day_factor") or 0) > 0])
    diary = await db.site_diaries.find_one(
        {"org_id": org, "project_id": project_id,
         "log_date": {"$regex": f"^{day}"}}, {"_id": 0, "workforce": 1, "id": 1})
    if not diary:
        return {"present": present, "diary_workforce": None, "difference": None,
                "state": "missing_diary",
                "detail": "Buku harian hari ini belum ditulis — tidak ada pembanding."}
    wf = int(diary.get("workforce") or 0)
    diff = present - wf
    return {"present": present, "diary_workforce": wf, "difference": diff,
            "diary_id": diary.get("id"),
            "state": ("match" if diff == 0 else "mismatch"),
            "detail": (None if diff == 0 else
                       (f"Buku harian menulis {wf} pekerja, absensi mencatat {present} hadir "
                        f"(selisih {diff:+d}). Dua-duanya dibiarkan apa adanya — perbaiki "
                        "yang salah, jangan ditimpa."))}


async def attendance(org: str = ORG_ID, *, project_id: str = None, work_date: str = None,
                     date_from: str = None, date_to: str = None,
                     worker_id: str = None) -> dict:
    q = {"org_id": org}
    if project_id:
        q["project_id"] = project_id
    if worker_id:
        q["worker_id"] = worker_id
    if work_date:
        q["work_date"] = str(work_date)[:10]
    elif date_from or date_to:
        q["work_date"] = {k: v for k, v in (("$gte", date_from), ("$lte", date_to)) if v}
    rows = await db.labor_attendance.find(q, {"_id": 0}) \
        .sort([("work_date", -1), ("worker_name", 1)]).to_list(2000)
    return {"data": rows, "total": len(rows),
            "present": len([r for r in rows if float(r.get("day_factor") or 0) > 0]),
            "wage_total": sum(int(r.get("total") or 0) for r in rows),
            "overtime_hours": sum(float(r.get("overtime_hours") or 0) for r in rows)}


# ============================================================ rekap upah (payroll)
async def build_payroll(org: str, *, project_id: str, period_start: str, period_end: str,
                        actor: str, budget_item_id: str = None, note: str = None) -> dict:
    """Rekap upah satu periode dari ABSENSI (bukan angka yang diketik ulang)."""
    if str(period_end) < str(period_start):
        raise ValueError("Tanggal akhir periode tidak boleh sebelum tanggal mulai.")
    project = await db.projects.find_one({"id": project_id, "org_id": org}, {"_id": 0})
    if not project:
        raise ValueError("Proyek tidak ditemukan.")
    clash = await db.labor_payrolls.find_one(
        {"org_id": org, "project_id": project_id, "state": {"$ne": "rejected"},
         "period_start": {"$lte": period_end}, "period_end": {"$gte": period_start}},
        {"_id": 0, "no": 1, "state": 1})
    if clash:
        raise ValueError(f"Periode ini bertumpang dengan rekap {clash['no']} "
                         f"({PAYROLL_LABEL.get(clash['state'], clash['state'])}).")
    rows = (await attendance(org, project_id=project_id, date_from=period_start,
                             date_to=period_end))["data"]
    payable = [r for r in rows if int(r.get("total") or 0) > 0]
    if not payable:
        raise ValueError("Tidak ada absensi berupah pada periode ini — rekap kosong tidak "
                         "dibuat agar tidak ada dokumen tanpa isi.")
    per_worker = {}
    for r in payable:
        w = per_worker.setdefault(r["worker_id"], {
            "worker_id": r["worker_id"], "worker_name": r.get("worker_name"),
            "role": r.get("role"), "role_label": r.get("role_label"),
            "daily_wage": int(r.get("daily_wage") or 0), "days": 0.0,
            "overtime_hours": 0.0, "base_wage": 0, "overtime_wage": 0, "total": 0,
            "dates": []})
        w["days"] += float(r.get("day_factor") or 0)
        w["overtime_hours"] += float(r.get("overtime_hours") or 0)
        w["base_wage"] += int(r.get("base_wage") or 0)
        w["overtime_wage"] += int(r.get("overtime_wage") or 0)
        w["total"] += int(r.get("total") or 0)
        w["dates"].append(r["work_date"])
    lines = sorted(per_worker.values(), key=lambda x: x["worker_name"] or "")
    ts = now_iso()
    doc = {
        "id": new_id(), "org_id": org,
        "no": await seq.next_number("labor_payroll", org, prefix="UPH", context={"project_id": project_id}),
        "project_id": project_id, "project_name": project.get("name"),
        "period_start": str(period_start)[:10], "period_end": str(period_end)[:10],
        "lines": lines, "worker_count": len(lines),
        "attendance_ids": [r["id"] for r in payable],
        "days_total": round(sum(x["days"] for x in lines), 2),
        "overtime_hours": round(sum(x["overtime_hours"] for x in lines), 2),
        "base_total": sum(x["base_wage"] for x in lines),
        "overtime_total": sum(x["overtime_wage"] for x in lines),
        "total": sum(x["total"] for x in lines),
        "state": "draft", "state_label": PAYROLL_LABEL["draft"],
        "budget_item_id": budget_item_id,
        "cost_ref": ({"budget_item_id": budget_item_id} if budget_item_id else None),
        "note": note, "journal_id": None, "bank_txn_id": None, "paid_at": None,
        "submitted_by": None, "submitted_at": None, "approved_by": None,
        "approved_at": None, "decision_reason": None,
        "created_by": actor, "created_at": ts, "updated_at": ts,
        "history": [{"at": ts, "by": actor, "action": "build", "state": "draft"}],
    }
    await db.labor_payrolls.insert_one(dict(doc))
    doc.pop("_id", None)
    await db.labor_attendance.update_many(
        {"id": {"$in": doc["attendance_ids"]}}, {"$set": {"payroll_id": doc["id"]}})
    return doc


async def payroll_or_error(org: str, payroll_id: str) -> dict:
    row = await db.labor_payrolls.find_one({"id": payroll_id, "org_id": org}, {"_id": 0})
    if not row:
        raise ValueError("Rekap upah tidak ditemukan.")
    return row


async def _advance(org: str, payroll_id: str, actor: str, *, state: str, action: str,
                   reason: str = None, extra: dict = None) -> dict:
    ts = now_iso()
    await db.labor_payrolls.update_one({"id": payroll_id}, {
        "$set": {"state": state, "state_label": PAYROLL_LABEL[state], "updated_at": ts,
                 **(extra or {})},
        "$push": {"history": {"at": ts, "by": actor, "action": action, "state": state,
                              "reason": reason}}})
    return await payroll_or_error(org, payroll_id)


async def submit_payroll(org: str, payroll_id: str, actor: str) -> dict:
    p = await payroll_or_error(org, payroll_id)
    if p["state"] != "draft":
        raise ValueError(f"Rekap ini sudah {p.get('state_label')}.")
    out = await _advance(org, payroll_id, actor, state="submitted", action="submit",
                         extra={"submitted_by": actor, "submitted_at": now_iso()})
    import finance_engine as fin
    await fin.notify_finance(
        org, "Rekap upah menunggu persetujuan",
        (f"{p['no']} · {p.get('project_name')} · {p['worker_count']} orang · "
         f"Rp {p['total']:,}").replace(",", "."), "finance", "labor_payroll", payroll_id)
    return out


async def decide_payroll(org: str, payroll_id: str, actor: str, approve: bool,
                        reason: str = None) -> dict:
    p = await payroll_or_error(org, payroll_id)
    if p["state"] != "submitted":
        raise ValueError("Hanya rekap yang DIAJUKAN bisa disetujui/ditolak.")
    if not approve and len((reason or "").strip()) < 5:
        raise ValueError("Penolakan wajib beralasan (minimal 5 huruf) — mandor perlu tahu "
                         "apa yang harus diperbaiki.")
    state = "approved" if approve else "rejected"
    out = await _advance(org, payroll_id, actor, state=state,
                         action=("approve" if approve else "reject"), reason=reason,
                         extra={"approved_by": actor, "approved_at": now_iso(),
                                "decision_reason": (reason or "").strip() or None})
    if not approve:
        await db.labor_attendance.update_many({"id": {"$in": p.get("attendance_ids") or []}},
                                              {"$set": {"payroll_id": None}})
    await create_notification(
        user_email=p.get("created_by"), org_id=org, type="construction",
        title=f"Rekap upah {p['no']} {'disetujui' if approve else 'ditolak'}",
        body=(reason or "").strip() or None,
        related_entity_type="labor_payroll", related_entity_id=payroll_id)
    return out


async def pay_payroll(org: str, payroll_id: str, actor: str, *, bank_txn_id: str = None,
                     note: str = None) -> dict:
    """Bayar upah: jurnal Dr WIP proyek / Cr Bank + masuk realisasi anggaran bila ditaut."""
    p = await payroll_or_error(org, payroll_id)
    if p["state"] != "approved":
        raise ValueError(f"Rekap harus DISETUJUI sebelum dibayar (sekarang {p.get('state_label')}).")
    amount = int(p.get("total") or 0)
    if amount <= 0:
        raise ValueError("Nilai rekap upah nol — tidak ada yang bisa dibayar.")
    je = await gl.post_journal(
        org, f"Pembayaran upah harian {p['no']} — {p.get('project_name')}",
        [{"account_code": GL_WIP, "debit": amount, "credit": 0,
          "memo": f"{p['worker_count']} orang · {p['days_total']} hari kerja"},
         {"account_code": GL_BANK, "debit": 0, "credit": amount}],
        date=p.get("period_end"), source_type="labor_payroll", source_id=payroll_id,
        source_event=f"labor.paid:{payroll_id}", posted_by=actor, auto=False)
    out = await _advance(org, payroll_id, actor, state="paid", action="pay", reason=note,
                         extra={"journal_id": je["id"], "journal_no": je["entry_no"],
                                "bank_txn_id": bank_txn_id, "paid_at": now_iso(),
                                "paid_by": actor})
    await add_activity(entity_type="project", entity_id=p["project_id"], type="finance",
                       actor=actor, org_id=org,
                       body=(f"Upah {p['no']} dibayar Rp {amount:,} ({p['worker_count']} "
                             f"orang) — jurnal {je['entry_no']}.").replace(",", "."))
    await emit("labor.paid", "project", p["project_id"],
              {"payroll_id": payroll_id, "amount": amount}, org_id=org)
    return out


async def payrolls(org: str = ORG_ID, *, project_id: str = None, state: str = None,
                   skip: int = 0, limit: int = 50) -> dict:
    q = {"org_id": org}
    if project_id:
        q["project_id"] = project_id
    if state:
        q["state"] = state
    total = await db.labor_payrolls.count_documents(q)
    rows = await db.labor_payrolls.find(q, {"_id": 0}).sort("created_at", -1) \
        .skip(skip).limit(limit).to_list(limit)
    # Ringkasan mengikuti saringan barisnya (proyek yang sedang dibuka), bukan seluruh
    # organisasi: papan lapangan yang menulis "3 rekap menunggu keputusan" padahal rekap itu
    # milik proyek lain membuat mandor menunggu sesuatu yang bukan urusannya.
    base = {k: v for k, v in q.items() if k != "state"}
    summary = {s: await db.labor_payrolls.count_documents({**base, "state": s})
               for s in PAYROLL_LABEL}
    unpaid = await db.labor_payrolls.find(
        {**base, "state": {"$in": ["submitted", "approved"]}},
        {"_id": 0, "total": 1}).to_list(200)
    summary["unpaid_amount"] = sum(int(r.get("total") or 0) for r in unpaid)
    return {"data": rows, "total": total, "summary": summary}
