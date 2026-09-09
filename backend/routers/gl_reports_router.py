"""Laporan keuangan periodik + tutup periode (P25 — kelengkapan akuntansi).

Endpoint (RBAC resource `gl` — finance + owner/super_admin):
  GET  /gl/reports/worksheet         — Neraca Lajur (saldo awal|transaksi|penyesuaian|akhir|L/R|Neraca)
  GET  /gl/reports/income-statement  — Laba Rugi periodik + pembanding periode sebelumnya
  GET  /gl/reports/balance-sheet     — Neraca per tanggal (as_of) + klasifikasi lancar
  GET  /gl/reports/cash-flow         — Arus Kas metode langsung (operasi/investasi/pendanaan)
  GET  /gl/reports/projects          — Laba Rugi per proyek (segment)
  GET  /gl/reports/ratios            — Analisa rasio + interpretasi
  GET  /gl/reports/ledger            — buku besar berperiode (drill-down dari laporan)
  GET  /gl/periods                   — status periode (open/closed) + ringkasan
  GET  /gl/periods/close-check       — daftar periksa tutup buku (Fase 49A)
  POST /gl/periods/close             — tutup periode; MENAHAN bila checklist gagal + override
  POST /gl/periods/reopen            — buka kembali periode (owner/super_admin — `approve`)
  GET  /gl/year                      — daftar tahun buku + status penutupan (Fase 49B)
  GET  /gl/year/check                — kesiapan tutup tahun (bulan yang belum ditutup, dsb.)
  POST /gl/year/close                — pindahkan laba/rugi ke Laba Ditahan (idempoten)
  POST /gl/year/reopen               — balik jurnal penutup tahun (beralasan, berjejak)
  GET  /gl/reports/cash-flow-projects — arus kas per proyek + tie-out (Fase 49C)
  GET  /gl/reports/owner-pack        — paket laporan bulanan owner (Fase 49D)
  GET  /gl/reports/closing-history   — riwayat penutupan bulan & tahun

Semua GET memiliki query opsional (default: bulan berjalan) agar endpoint sweep 200.
"""
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

import closing_engine as ce
import gl_engine as gl
import gl_periods as glp
import gl_project_cash as gpc
import gl_reports as glr
import owner_pack as op
from core_utils import serialize_doc
from db import db, ORG_ID
from models_p49 import PeriodCloseAction, YearAction
from rbac import require_permission, audit_log, can

router = APIRouter(prefix="/gl", tags=["gl-reports"])

PERIOD_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
YEAR_RE = re.compile(r"^\d{4}$")


class PeriodAction(BaseModel):
    period: str = Field(..., description="Periode YYYY-MM")
    note: str = None


def _validate_period(period: str) -> str:
    if not PERIOD_RE.match(period or ""):
        raise HTTPException(status_code=400, detail="Format periode harus YYYY-MM (mis. 2026-08).")
    return period


def _validate_year(year: str) -> str:
    if not YEAR_RE.match(str(year or "")):
        raise HTTPException(status_code=400, detail="Format tahun harus YYYY (mis. 2026).")
    return str(year)


# ----------------------------- laporan -----------------------------
@router.get("/reports/worksheet")
async def get_worksheet(date_from: str = None, date_to: str = None,
                        user: dict = Depends(require_permission("gl", "view"))):
    org = user.get("org_id", ORG_ID)
    await gl.ensure_coa(org)
    return {"data": serialize_doc(await glr.worksheet(org, date_from, date_to))}


@router.get("/reports/income-statement")
async def get_income_statement(date_from: str = None, date_to: str = None, compare: bool = True,
                               user: dict = Depends(require_permission("gl", "view"))):
    org = user.get("org_id", ORG_ID)
    await gl.ensure_coa(org)
    return {"data": serialize_doc(await glr.income_statement(org, date_from, date_to, compare))}


@router.get("/reports/balance-sheet")
async def get_balance_sheet(as_of: str = None,
                            user: dict = Depends(require_permission("gl", "view"))):
    org = user.get("org_id", ORG_ID)
    await gl.ensure_coa(org)
    return {"data": serialize_doc(await glr.balance_sheet(org, as_of))}


@router.get("/reports/cash-flow")
async def get_cash_flow(date_from: str = None, date_to: str = None,
                        user: dict = Depends(require_permission("gl", "view"))):
    org = user.get("org_id", ORG_ID)
    await gl.ensure_coa(org)
    return {"data": serialize_doc(await glr.cash_flow(org, date_from, date_to))}


@router.get("/reports/projects")
async def get_project_report(date_from: str = None, date_to: str = None,
                             user: dict = Depends(require_permission("gl", "view"))):
    org = user.get("org_id", ORG_ID)
    await gl.ensure_coa(org)
    return {"data": serialize_doc(await glr.project_report(org, date_from, date_to))}


@router.get("/reports/ratios")
async def get_ratios(date_from: str = None, date_to: str = None,
                     user: dict = Depends(require_permission("gl", "view"))):
    org = user.get("org_id", ORG_ID)
    await gl.ensure_coa(org)
    return {"data": serialize_doc(await glr.ratios(org, date_from, date_to))}


@router.get("/reports/ledger")
async def get_period_ledger(account_code: str = None, date_from: str = None, date_to: str = None,
                            user: dict = Depends(require_permission("gl", "view"))):
    org = user.get("org_id", ORG_ID)
    await gl.ensure_coa(org)
    if not account_code:
        return {"data": {"account": None, "lines": [], "opening": 0, "closing": 0,
                         "total_debit": 0, "total_credit": 0, "period": None}}
    return {"data": serialize_doc(await glr.ledger(org, account_code, date_from, date_to))}


# ----------------------------- tutup periode -----------------------------
@router.get("/periods")
async def list_periods(limit: int = 18, user: dict = Depends(require_permission("gl", "view"))):
    org = user.get("org_id", ORG_ID)
    limit = max(1, min(int(limit or 18), 60))
    closed = await glp.closed_periods(org)
    counts = {}
    for je in await db.journal_entries.find({"org_id": org}, {"_id": 0, "date": 1}).to_list(200000):
        m = str(je.get("date"))[:7]
        if len(m) == 7:
            counts[m] = counts.get(m, 0) + 1
    months = sorted(set(counts) | set(closed), reverse=True)[:limit]
    meta = {p["period"]: p for p in await db.accounting_periods.find(
        {"org_id": org}, {"_id": 0}).to_list(1200)}
    rows = []
    for m in months:
        start, end = glr.month_range(m)
        pl = await glr._pl_block(org, start, end)
        info = meta.get(m) or {}
        rows.append({
            "period": m, "status": "closed" if m in closed else "open",
            "journals": counts.get(m, 0), "revenue": pl["total_revenue"],
            "expense": pl["total_expense"], "net_income": pl["net_income"],
            "closed_by": info.get("closed_by"), "closed_at": info.get("closed_at"),
            "reopened_by": info.get("reopened_by"), "reopened_at": info.get("reopened_at"),
            "note": info.get("note"),
        })
    return {"data": rows, "total": len(rows), "closed_count": len(closed)}


@router.post("/periods/close")
async def close_period(payload: PeriodCloseAction,
                       user: dict = Depends(require_permission("gl", "update"))):
    """Tutup periode — MENAHAN bila daftar periksa belum bersih (Fase 49A).

    Dulu endpoint ini hanya menandai periode "closed" tanpa memeriksa apa pun: mutasi bank
    bisa belum dicocokkan, tagihan masih menunggu keputusan, penyusutan bulan itu belum
    diposting — dan laporan yang sudah dibagikan ke owner tetap bisa berubah. Sekarang
    penutupan ditahan dengan menyebut sebabnya satu per satu; menerobos butuh izin
    `gl:close_override` DAN alasan tertulis ≥10 huruf, lalu melahirkan tugas tinjauan.
    """
    org = user.get("org_id", ORG_ID)
    period = _validate_period(payload.period)
    if payload.override:
        if not await can(user.get("role"), "gl", "close_override"):
            raise HTTPException(status_code=403, detail=(
                "Akses ditolak: menerobos daftar periksa tutup buku hanya untuk Manajer "
                "Keuangan/Direksi. Tuntaskan dulu pemeriksaan yang menahan."))
        if not (payload.override_reason or "").strip():
            raise HTTPException(status_code=400, detail=(
                "Alasan terobosan wajib diisi (minimal 10 huruf) — periode yang ditutup "
                "dengan daftar periksa belum bersih harus punya dasar tertulis."))
    try:
        doc = await ce.close_period(org, period, user.get("email"), payload.note,
                                    override=bool(payload.override),
                                    override_reason=payload.override_reason)
    except ce.ClosingHold as e:
        raise HTTPException(status_code=409, detail=(
            f"Penutupan periode {period} DITAHAN — " + " | ".join(e.reasons)))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit_log(user, "close", "accounting_periods", period,
                    {"note": payload.note, "override": bool(payload.override),
                     "override_reason": payload.override_reason})
    return {"data": serialize_doc(doc)}


@router.get("/periods/close-check")
async def close_check(period: str = None,
                      user: dict = Depends(require_permission("gl", "view"))):
    """Daftar periksa satu periode: item + keadaan + sebab + tautan ke halaman sumber."""
    org = user.get("org_id", ORG_ID)
    p = period or glr.today_str()[:7]
    _validate_period(p)
    return {"data": serialize_doc(await ce.close_check(org, p))}


# ----------------------------- tutup tahun (49B) -----------------------------
@router.get("/year")
async def year_list(user: dict = Depends(require_permission("gl", "view"))):
    return {"data": serialize_doc(await ce.year_list(user.get("org_id", ORG_ID)))}


@router.get("/year/check")
async def year_check(year: str = None, user: dict = Depends(require_permission("gl", "view"))):
    org = user.get("org_id", ORG_ID)
    y = _validate_year(year or glr.today_str()[:4])
    return {"data": serialize_doc(await ce.year_check(org, y))}


@router.post("/year/close")
async def year_close(payload: YearAction,
                     user: dict = Depends(require_permission("gl", "year_close"))):
    """Pindahkan laba/rugi tahun berjalan ke Laba Ditahan (idempoten, jurnal seimbang)."""
    org = user.get("org_id", ORG_ID)
    year = _validate_year(payload.year)
    try:
        doc = await ce.year_close(org, year, user.get("email"), payload.note)
    except ce.ClosingHold as e:
        raise HTTPException(status_code=409, detail=(
            f"Tutup tahun {year} DITAHAN — " + " | ".join(e.reasons)))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not doc.get("idempotent"):
        await audit_log(user, "year_close", "gl_year_closings", year,
                        {"entry_no": doc.get("entry_no"), "net_income": doc.get("net_income")})
    return {"data": serialize_doc(doc)}


@router.post("/year/reopen")
async def year_reopen(payload: YearAction,
                      user: dict = Depends(require_permission("gl", "year_close"))):
    """Buka kembali tahun buku: jurnal penutup DIBALIK (bukan dihapus), alasan wajib."""
    org = user.get("org_id", ORG_ID)
    year = _validate_year(payload.year)
    if not (payload.reason or "").strip():
        raise HTTPException(status_code=400, detail=(
            "Alasan wajib diisi (minimal 10 huruf) — membuka tahun buku membalik jurnal "
            "penutup dan mengubah ekuitas yang sudah dilaporkan."))
    try:
        doc = await ce.year_reopen(org, year, user.get("email"), payload.reason)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit_log(user, "year_reopen", "gl_year_closings", year,
                    {"reason": payload.reason, "reversal": doc.get("reversal_entry_no")})
    return {"data": serialize_doc(doc)}


# ----------------------------- 49C/49D laporan lanjutan -----------------------------
@router.get("/reports/cash-flow-projects")
async def cash_flow_projects(date_from: str = None, date_to: str = None,
                             user: dict = Depends(require_permission("gl", "view"))):
    """Arus kas PER PROYEK + baris "tidak teralokasi" + bukti tie-out ke konsolidasi."""
    org = user.get("org_id", ORG_ID)
    await gl.ensure_coa(org)
    return {"data": serialize_doc(await gpc.cash_flow_projects(org, date_from, date_to))}


@router.get("/reports/owner-pack")
async def owner_pack(period: str = None, user: dict = Depends(require_permission("gl", "view"))):
    """Paket laporan bulanan owner: BS/PL/CF + per proyek + rasio + metadata penutupan."""
    org = user.get("org_id", ORG_ID)
    p = period or glr.today_str()[:7]
    _validate_period(p)
    await gl.ensure_coa(org)
    return {"data": serialize_doc(await op.owner_pack(org, p))}


@router.get("/reports/closing-history")
async def closing_history(limit: int = 24,
                          user: dict = Depends(require_permission("gl", "view"))):
    """Riwayat penutupan: siapa menutup bulan apa, diterobos atau tidak, plus tutup tahun."""
    return {"data": serialize_doc(
        await op.closing_history(user.get("org_id", ORG_ID), limit))}


@router.post("/periods/reopen")
async def reopen_period(payload: PeriodAction,
                        user: dict = Depends(require_permission("gl", "approve"))):
    """Buka kembali periode — sengaja dibatasi (owner/super_admin) sebagai kontrol SoD."""
    org = user.get("org_id", ORG_ID)
    period = _validate_period(payload.period)
    if period not in await glp.closed_periods(org):
        raise HTTPException(status_code=400, detail=f"Periode {period} tidak dalam status tertutup.")
    doc = await glp.reopen_period(org, period, user.get("email"), payload.note)
    await audit_log(user, "reopen", "accounting_periods", period, {"note": payload.note})
    return {"data": serialize_doc(doc)}
