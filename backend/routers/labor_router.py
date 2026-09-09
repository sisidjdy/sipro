"""ROUTER ABSENSI & UPAH HARIAN (Fase 47D) — prefix `/labor`.

Pemisahan tugas yang dipaksakan:
  * `labor:create/update` — pelaksana lapangan & manajer proyek MENCATAT absensi dan
    menyusun/mengajukan rekap upah;
  * `labor:approve` — hanya keuangan/direksi yang MENYETUJUI & MEMBAYAR. Yang mencatat
    kehadiran tidak boleh sekaligus menyetujui pembayarannya — itu inti pengendalian upah.
"""
from fastapi import APIRouter, Depends, HTTPException, Query

import labor_engine as labor
from core_utils import parse_pagination, serialize_doc
from db import db, ORG_ID
from models_p47 import AttendanceIn, PayrollBuildIn, PayrollDecisionIn, PayrollPayIn, WorkerIn
import offline_intake as oi
from rbac import assert_project_access, audit_log, require_permission

router = APIRouter(prefix="/labor", tags=["labor"])


def _org(user: dict) -> str:
    return user.get("org_id", ORG_ID)


# ------------------------------------------------------------------ master pekerja
@router.get("/workers")
async def list_workers(project_id: str = None, active: bool = None, q: str = None,
                       user: dict = Depends(require_permission("labor", "view"))):
    rows = await labor.workers(_org(user), project_id=project_id, active=active, q=q)
    return {"data": serialize_doc(rows), "total": len(rows)}


@router.post("/workers")
async def create_worker(payload: WorkerIn,
                        user: dict = Depends(require_permission("labor", "create"))):
    try:
        doc = await labor.create_worker(_org(user), payload.model_dump(), user.get("email"))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit_log(user, "create", "workers", doc["id"],
                    {"name": doc["name"], "daily_wage": doc["daily_wage"]})
    return {"data": serialize_doc(doc)}


@router.put("/workers/{worker_id}")
async def update_worker(worker_id: str, payload: WorkerIn,
                        user: dict = Depends(require_permission("labor", "update"))):
    try:
        doc = await labor.update_worker(_org(user), worker_id, payload.model_dump(),
                                        user.get("email"))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit_log(user, "update", "workers", worker_id, {"name": payload.name})
    return {"data": serialize_doc(doc)}


@router.get("/rates")
async def wage_rates(user: dict = Depends(require_permission("labor", "view"))):
    """Aturan hitung upah yang dipakai server — layar memakai ini, tidak menghitung sendiri."""
    return {"data": await labor.rates(_org(user))}


# ------------------------------------------------------------------ absensi
@router.post("/attendance")
async def record_attendance(payload: AttendanceIn,
                            user: dict = Depends(require_permission("labor", "create"))):
    """Catat absensi satu hari (banyak orang sekaligus). Orang kembar & tanggal terkunci ditolak.

    Fase 50B: `client_ref` membuat kiriman dari ANTREAN PERANGKAT aman diputar ulang —
    hasil lama dikembalikan apa adanya, tanpa absensi (dan upah) kedua.
    """
    await assert_project_access(payload.project_id, user)
    org = _org(user)
    intake = await oi.begin(org, "attendance_submit", payload.client_ref)
    if intake["state"] == "replay":
        prior = intake.get("summary") or {}
        return {"data": serialize_doc(intake.get("doc") or {}), "replay": True,
                "message": ("Absensi ini sudah pernah diterima server \u2014 catatan lamanya "
                            "dipakai, tidak ada absensi kedua."),
                "summary": prior}
    if intake["state"] == "inflight":
        raise HTTPException(status_code=409,
                            detail="Kiriman absensi dengan penanda yang sama sedang diproses.")
    try:
        out = await labor.record_attendance(
            _org(user), project_id=payload.project_id, work_date=payload.work_date,
            entries=[e.model_dump() for e in payload.entries], actor=user.get("email"))
    except ValueError as e:
        await oi.rollback(org, "attendance_submit", payload.client_ref)
        raise HTTPException(status_code=400, detail=str(e))
    if payload.client_ref:
        # Absensi harian tidak punya satu dokumen induk (satu baris per orang), jadi yang
        # disimpan sebagai hasil adalah baris PERTAMA hari itu + ringkasannya.
        first = await db.labor_attendance.find_one(
            {"org_id": org, "project_id": payload.project_id, "work_date": payload.work_date},
            {"_id": 0, "id": 1})
        await oi.commit(org, "attendance_submit", payload.client_ref,
                        collection="labor_attendance", doc_id=(first or {}).get("id"),
                        summary={k: out.get(k) for k in ("present", "wage_total")})
    await audit_log(user, "create", "labor_attendance", payload.project_id,
                    {"work_date": payload.work_date, "entries": len(payload.entries)})
    return {"data": serialize_doc(out),
            "message": (f"{out['present']} orang hadir dicatat · upah hari ini "
                        f"Rp {out['wage_total']:,}").replace(",", ".")}


@router.get("/attendance")
async def list_attendance(project_id: str = None, work_date: str = None,
                          date_from: str = None, date_to: str = None,
                          worker_id: str = None,
                          user: dict = Depends(require_permission("labor", "view"))):
    if project_id:
        await assert_project_access(project_id, user)
    out = await labor.attendance(_org(user), project_id=project_id, work_date=work_date,
                                date_from=date_from, date_to=date_to, worker_id=worker_id)
    return {"data": serialize_doc(out["data"]), "total": out["total"],
            "summary": {k: out[k] for k in ("present", "wage_total", "overtime_hours")}}


@router.get("/attendance/diary-check")
async def diary_check(project_id: str, work_date: str,
                      user: dict = Depends(require_permission("labor", "view"))):
    """Bandingkan absensi dengan jumlah pekerja di buku harian — selisih dilaporkan apa adanya."""
    await assert_project_access(project_id, user)
    return {"data": await labor.diary_check(_org(user), project_id, work_date)}


# ------------------------------------------------------------------ rekap upah
@router.post("/payrolls")
async def build_payroll(payload: PayrollBuildIn,
                        user: dict = Depends(require_permission("labor", "create"))):
    await assert_project_access(payload.project_id, user)
    try:
        doc = await labor.build_payroll(
            _org(user), project_id=payload.project_id, period_start=payload.period_start,
            period_end=payload.period_end, actor=user.get("email"),
            budget_item_id=payload.budget_item_id, note=payload.note)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit_log(user, "create", "labor_payrolls", doc["id"],
                    {"no": doc["no"], "total": doc["total"]})
    return {"data": serialize_doc(doc),
            "message": (f"Rekap {doc['no']}: {doc['worker_count']} orang · "
                        f"Rp {doc['total']:,}").replace(",", ".")}


@router.get("/payrolls")
async def list_payrolls(project_id: str = None, state: str = None, skip: int = 0,
                        limit: int = Query(25, ge=1, le=100),
                        user: dict = Depends(require_permission("labor", "view"))):
    skip, limit = parse_pagination(skip, limit)
    out = await labor.payrolls(_org(user), project_id=project_id, state=state, skip=skip,
                               limit=limit)
    return {"data": serialize_doc(out["data"]), "total": out["total"],
            "summary": out["summary"]}


@router.get("/payrolls/{payroll_id}")
async def payroll_detail(payroll_id: str,
                         user: dict = Depends(require_permission("labor", "view"))):
    try:
        return {"data": serialize_doc(await labor.payroll_or_error(_org(user), payroll_id))}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/payrolls/{payroll_id}/submit")
async def submit_payroll(payroll_id: str,
                         user: dict = Depends(require_permission("labor", "update"))):
    try:
        out = await labor.submit_payroll(_org(user), payroll_id, user.get("email"))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit_log(user, "submit", "labor_payrolls", payroll_id, {"total": out["total"]})
    return {"data": serialize_doc(out), "message": "Rekap upah diajukan ke keuangan."}


@router.post("/payrolls/{payroll_id}/decision")
async def decide_payroll(payroll_id: str, payload: PayrollDecisionIn,
                         user: dict = Depends(require_permission("labor", "approve"))):
    """Keuangan menyetujui/menolak rekap upah (penolakan wajib beralasan)."""
    try:
        out = await labor.decide_payroll(_org(user), payroll_id, user.get("email"),
                                         payload.approve, payload.reason)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit_log(user, "decide", "labor_payrolls", payroll_id,
                    {"approve": payload.approve, "reason": payload.reason})
    return {"data": serialize_doc(out),
            "message": ("Rekap upah disetujui." if payload.approve
                        else "Rekap upah ditolak.")}


@router.post("/payrolls/{payroll_id}/pay")
async def pay_payroll(payroll_id: str, payload: PayrollPayIn,
                      user: dict = Depends(require_permission("labor", "approve"))):
    """Bayar upah → jurnal Dr WIP proyek / Cr Bank + realisasi anggaran bila ditaut."""
    try:
        out = await labor.pay_payroll(_org(user), payroll_id, user.get("email"),
                                      bank_txn_id=payload.bank_txn_id, note=payload.note)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit_log(user, "pay", "labor_payrolls", payroll_id,
                    {"total": out["total"], "journal": out.get("journal_no")})
    return {"data": serialize_doc(out),
            "message": f"Upah dibayar — jurnal {out.get('journal_no')}."}
