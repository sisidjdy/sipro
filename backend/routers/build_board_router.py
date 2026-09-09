"""ROUTER PAPAN UNIT & GERBANG MULAI BANGUN (Fase 46) — prefix `/build`.

Pelengkap `build_router.py` (jadwal & bukti per langkah) dan `build_ops_router.py`
(papan mandor, rapor mingguan, analitik). Yang ditambahkan di sini adalah dua hal yang
selama ini tidak dijawab satu layar pun:

  1. **Papan Unit** — satu baris per RUMAH termasuk unit yang BELUM dijadwalkan, dengan
     kolom deviasi, umur telat, langkah aktif, PIC, bukti terakhir, dan kesiapan mulai.
     `build_monitor.board()` tidak bisa dipakai: ia berbaris per JADWAL, jadi unit tanpa
     jadwal (justru yang paling perlu perhatian) hilang dari layar.
  2. **Gerbang "Mulai Bangun"** — klausul SPR "pembangunan dimulai setelah pembayaran
     tahap pertama diterima" akhirnya benar-benar dibaca kode. Bawaan = PERINGATAN
     (harus diakui + beralasan), bukan blokir; menjadi blokir bila admin menyalakan
     `build.require_dp_before_start` / mengisi `permit.block_build_without`.

RBAC (resource `construction`):
  * view    — melihat papan unit & kesiapan (semua peran yang boleh melihat proyek)
  * approve — menekan "Mulai bangun" (owner/super_admin/manajer proyek).
    SENGAJA: memulai pembangunan adalah keputusan manajerial (uang & jadwal), berbeda dari
    mengerjakan langkah (`update`, boleh pelaksana lapangan).
"""
from fastapi import APIRouter, Depends, HTTPException, Query

import build_readiness as brd
import build_unit_board as bub
from core_utils import serialize_doc
from db import ORG_ID, db
from models_p46 import StartBuildIn
from rbac import has_role, assert_project_access, audit_log, project_query, require_permission

router = APIRouter(prefix="/build", tags=["build-board"])


def _org(user: dict) -> str:
    return user.get("org_id", ORG_ID)


def _multi(value: str) -> list:
    """Filter multi dikirim frontend sebagai "a,b" (kontrak `useListQuery`)."""
    return [v.strip() for v in str(value or "").split(",") if v.strip()]


async def _my_project_ids(user: dict):
    """Peran ber-lingkup proyek (PM/pelaksana) hanya melihat proyek yang diikutinya."""
    if not has_role(user, "project_manager", "site_engineer"):
        return None
    rows = await db.projects.find(project_query(user, {}), {"_id": 0, "id": 1}).to_list(500)
    return [r["id"] for r in rows]


@router.get("/board/units")
async def board_units(project_id: str = None, cluster_id: str = None, block_id: str = None,
                      construction_status: str = None, readiness: str = None,
                      late_only: bool = False, unscheduled_only: bool = False,
                      q: str = None, sort: str = "code", direction: str = "asc",
                      skip: int = 0, limit: int = Query(25, ge=1, le=200),
                      user: dict = Depends(require_permission("construction", "view"))):
    """Papan Unit: satu baris per unit (terjadwal maupun belum) + ringkasan jujur."""
    org = _org(user)
    if project_id:
        await assert_project_access(project_id, user)
    mine = await _my_project_ids(user)
    res = await bub.unit_rows(
        org, project_id=project_id, cluster_id=cluster_id, block_id=block_id,
        project_ids=(mine if (mine is not None and not project_id) else None),
        construction_status=_multi(construction_status), readiness=_multi(readiness),
        late_only=late_only, unscheduled_only=unscheduled_only, q=q,
        sort=sort, direction=direction, skip=skip, limit=limit)
    return {"data": serialize_doc(res["data"]), "total": res["total"],
            "summary": res["summary"], "mode": res["mode"], "as_of": res["as_of"],
            "sortable": sorted(set(bub.SORTABLE) | set(bub.DERIVED_SORT))}


async def _unit_or_404(unit_id: str, user: dict) -> dict:
    unit = await db.units.find_one({"id": unit_id, "org_id": _org(user)}, {"_id": 0})
    if not unit:
        raise HTTPException(status_code=404, detail="Unit tidak ditemukan")
    await assert_project_access(unit["project_id"], user)
    return unit


@router.get("/unit/{unit_id}/readiness")
async def unit_readiness(unit_id: str,
                         user: dict = Depends(require_permission("construction", "view"))):
    """Kesiapan mulai bangun + SELURUH alasannya (agar layar bisa menjelaskan, bukan diam)."""
    await _unit_or_404(unit_id, user)
    try:
        return {"data": serialize_doc(await brd.evaluate(_org(user), unit_id))}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/unit/{unit_id}/start")
async def unit_start_build(unit_id: str, payload: StartBuildIn,
                           user: dict = Depends(require_permission("construction",
                                                                   "approve"))):
    """Mulai bangun. Peringatan WAJIB diakui + beralasan; penolakan selalu menyebut sebabnya."""
    unit = await _unit_or_404(unit_id, user)
    try:
        out = await brd.start_build(_org(user), unit_id, user.get("email"),
                                    ack=payload.ack, reason=payload.reason)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit_log(user, "build.start", "unit", unit_id,
                    {"unit_code": unit.get("code"), "acknowledged": out["acknowledged"],
                     "reason": out["reason"],
                     "warnings": [w["code"] for w in out["warnings"]]})
    msg = "Pembangunan dimulai."
    if out["warnings"]:
        msg = (f"Pembangunan dimulai dengan {len(out['warnings'])} peringatan yang "
               "Anda akui — keputusan ini tercatat pada jejak unit.")
    return {"data": serialize_doc(out), "message": msg}
