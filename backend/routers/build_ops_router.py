"""ROUTER OPERASIONAL PEMBANGUNAN (Fase 32) — prefix `/build`.

Dipisah dari `build_router.py` supaya tiap file tetap di bawah batas gate compliance
(router ≤800 baris) dan tanggung jawabnya jelas:
  * `build_router.py`     → template, jadwal, item, aksi berbukti (Fase 31)
  * `build_ops_router.py` → Papan Mandor, kebijakan bukti kerja, laporan mingguan,
                            analitik keterlambatan (Fase 32)

RBAC:
  * board/policy(GET)/reports(GET)/analytics → `construction:view`
  * jalankan laporan mingguan                → `construction:approve` (PM/owner)
  * ubah kebijakan bukti kerja               → **hanya Direksi/Super Admin** (admin)
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Response

import build_analytics as ban
import build_board as bb
import build_policy as bp
import build_reports as br
from core_utils import parse_pagination, serialize_doc
from db import db, ORG_ID
from models_p31 import BuildPolicyIn, WeeklyReportRun
from rbac import has_role, assert_project_access, audit_log, require_permission

router = APIRouter(prefix="/build", tags=["build-ops"])
ADMIN_ROLES = ("owner", "super_admin")


def _org(user: dict) -> str:
    return user.get("org_id", ORG_ID)


# ============================ PAPAN MANDOR ============================
@router.get("/board/today")
async def board_today(project_id: str = None,
                      user: dict = Depends(require_permission("construction", "view"))):
    """Satu layar "kerja hari ini" untuk pelaksana (dan antrean verifikasi supervisor)."""
    if project_id:
        await assert_project_access(project_id, user)
    return {"data": serialize_doc(await bb.today(_org(user), user, project_id))}


# ======================= KEBIJAKAN BUKTI KERJA =======================
@router.get("/policy")
async def get_policy(user: dict = Depends(require_permission("construction", "view"))):
    pol = await bp.get_policy(_org(user))
    return {"data": pol, "can_edit": has_role(user, *ADMIN_ROLES)}


@router.put("/policy")
async def put_policy(payload: BuildPolicyIn,
                     user: dict = Depends(require_permission("construction", "view"))):
    """Hanya admin (Direksi/Super Admin) — kebijakan ini menyangkut privasi & audit."""
    if not has_role(user, *ADMIN_ROLES):
        raise HTTPException(status_code=403, detail=(
            "Kebijakan bukti kerja hanya bisa diubah Direksi/Super Admin karena "
            "menyangkut privasi lokasi pekerja dan kekuatan bukti audit."))
    pol = await bp.set_policy(_org(user), payload.model_dump(), user.get("email"))
    await audit_log(user, "update", "build_policy", _org(user), payload.model_dump())
    return {"data": pol, "can_edit": True,
            "message": ("Kebijakan bukti kerja disimpan. "
                        + ("Lokasi WAJIB direkam saat mengajukan hasil kerja."
                           if pol.get("geo_required")
                           else "Lokasi tidak diwajibkan."))}


# ========================= LAPORAN MINGGUAN =========================
@router.get("/reports/weekly")
async def list_weekly(project_id: str = None, skip: int = 0, limit: int = Query(12, le=60),
                      user: dict = Depends(require_permission("construction", "view"))):
    q = {"org_id": _org(user)}
    if project_id:
        await assert_project_access(project_id, user)
        q["project_id"] = project_id
    skip, limit = parse_pagination(skip, limit)
    total = await db.build_weekly_reports.count_documents(q)
    rows = await db.build_weekly_reports.find(
        q, {"_id": 0, "houses": 0, "curve": 0, "delays_top": 0}).sort(
        "week_key", -1).skip(skip).limit(limit).to_list(limit)
    return {"data": serialize_doc(rows), "total": total,
            "can_run": has_role(user, *ADMIN_ROLES, "project_manager")}


@router.post("/reports/weekly/run")
async def run_weekly(payload: WeeklyReportRun,
                     user: dict = Depends(require_permission("construction", "approve"))):
    """Buat/segarkan laporan pekan ini (idempoten). Dipakai juga oleh scheduler Senin."""
    if payload.project_id:
        await assert_project_access(payload.project_id, user)
    out = await br.run_weekly(_org(user), payload.project_id, user.get("email"),
                              payload.ref_date)
    if not out["reports"]:
        raise HTTPException(status_code=400, detail=(
            "Belum ada proyek yang punya jadwal pembangunan — buat jadwal unit dulu "
            "agar laporan mingguan punya isi."))
    await audit_log(user, "create", "build_weekly_report", _org(user),
                    {"week": out["week_key"], "created": out["created"]})
    return {"data": out, "message": (
        f"Laporan pekan {out['week_key']}: {out['created']} laporan baru dibuat, "
        f"{out['refreshed']} disegarkan. Direksi & Manajer Proyek diberi tahu.")}


@router.get("/reports/weekly/{report_id}")
async def get_weekly(report_id: str,
                     user: dict = Depends(require_permission("construction", "view"))):
    rep = await db.build_weekly_reports.find_one({"id": report_id, "org_id": _org(user)},
                                          {"_id": 0})
    if not rep:
        raise HTTPException(status_code=404, detail="Laporan mingguan tidak ditemukan.")
    await assert_project_access(rep["project_id"], user)
    return {"data": serialize_doc(rep)}


@router.get("/reports/weekly/{report_id}/pdf")
async def weekly_pdf(report_id: str,
                     user: dict = Depends(require_permission("construction", "view"))):
    rep = await db.build_weekly_reports.find_one({"id": report_id, "org_id": _org(user)},
                                          {"_id": 0})
    if not rep:
        raise HTTPException(status_code=404, detail="Laporan mingguan tidak ditemukan.")
    await assert_project_access(rep["project_id"], user)
    org = await db.orgs.find_one({"id": _org(user)}, {"_id": 0, "name": 1}) or {}
    pdf = br.pdf_bytes(rep, org.get("name") or "PT SIPRO Land")
    name = f"laporan-mingguan-{rep.get('week_key')}-{(rep.get('project_name') or 'proyek')}"
    safe = "".join(c if c.isalnum() or c in "-_" else "-" for c in name)[:80]
    return Response(content=pdf, media_type="application/pdf", headers={
        "Content-Disposition": f'attachment; filename="{safe}.pdf"'})


# ======================= ANALITIK KETERLAMBATAN =======================
@router.get("/analytics/delays")
async def analytics_delays(project_id: str = None,
                           user: dict = Depends(require_permission("construction", "view"))):
    if project_id:
        await assert_project_access(project_id, user)
    return {"data": serialize_doc(await ban.delays(_org(user), project_id))}
