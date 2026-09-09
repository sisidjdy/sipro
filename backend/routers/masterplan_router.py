"""Master Proyek → Cluster → Blok → Unit (Fase 39) + Unit 360.

Menutup CR-05: sebelum ini tidak ada endpoint untuk mengelola struktur proyek; unit hanya
bisa dibuat lewat generator prefiks dan "blok" adalah tebakan dari kode unit.
"""
from fastapi import APIRouter, Depends, HTTPException

import masterplan as mp
from core_utils import serialize_doc
from db import ORG_ID
from models_v2 import (BlockCreate, BlockUpdate, ClusterCreate, ClusterUpdate, UnitBlockToggle,
                       UnitCreateV2, UnitGenerateV2, UnitImport, UnitPatchV2)
from rbac import assert_project_access, audit_log, require_permission

router = APIRouter(prefix="/masterplan", tags=["masterplan"])


def _org(user: dict) -> str:
    return user.get("org_id", ORG_ID)


# ------------------------------------------------------------------ struktur
@router.get("/projects/{project_id}/tree")
async def project_tree(project_id: str,
                       user: dict = Depends(require_permission("projects", "view"))):
    """Pohon cluster → blok (+ statistik unit) untuk navigasi & site plan."""
    await assert_project_access(project_id, user)
    try:
        return {"data": serialize_doc(await mp.project_tree(project_id, _org(user)))}
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/projects/{project_id}/siteplan-consistency")
async def siteplan_consistency(project_id: str,
                               user: dict = Depends(require_permission("projects", "view"))):
    """Unit yang belum dipetakan + shape yang menunjuk unit tidak ada (peta vs data)."""
    await assert_project_access(project_id, user)
    return {"data": serialize_doc(await mp.siteplan_consistency(project_id, _org(user)))}


@router.get("/projects/{project_id}/clusters")
async def list_clusters(project_id: str,
                        user: dict = Depends(require_permission("projects", "view"))):
    await assert_project_access(project_id, user)
    return {"data": serialize_doc(await mp.list_clusters(project_id, _org(user)))}


@router.post("/projects/{project_id}/clusters")
async def create_cluster(project_id: str, payload: ClusterCreate,
                         user: dict = Depends(require_permission("projects", "create"))):
    await assert_project_access(project_id, user)
    try:
        row = await mp.create_cluster(project_id, payload, user.get("email"), _org(user))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit_log(user, "create", "clusters", row["id"], {"code": row["code"]})
    return {"data": serialize_doc(row)}


@router.put("/clusters/{cluster_id}")
async def update_cluster(cluster_id: str, payload: ClusterUpdate,
                         user: dict = Depends(require_permission("projects", "update"))):
    try:
        row = await mp.update_cluster(cluster_id, payload, user.get("email"), _org(user))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit_log(user, "update", "clusters", cluster_id, {})
    return {"data": serialize_doc(row)}


@router.delete("/clusters/{cluster_id}")
async def delete_cluster(cluster_id: str,
                         user: dict = Depends(require_permission("projects", "update"))):
    try:
        res = await mp.delete_cluster(cluster_id, _org(user))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit_log(user, "delete", "clusters", cluster_id, {})
    return {"data": res}


@router.get("/blocks")
async def list_blocks(project_id: str = None, cluster_id: str = None,
                      user: dict = Depends(require_permission("projects", "view"))):
    return {"data": serialize_doc(await mp.list_blocks(_org(user), project_id=project_id,
                                                       cluster_id=cluster_id))}


@router.post("/clusters/{cluster_id}/blocks")
async def create_block(cluster_id: str, payload: BlockCreate,
                       user: dict = Depends(require_permission("projects", "create"))):
    try:
        row = await mp.create_block(cluster_id, payload, user.get("email"), _org(user))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit_log(user, "create", "blocks", row["id"], {"code": row["code"]})
    return {"data": serialize_doc(row)}


@router.put("/blocks/{block_id}")
async def update_block(block_id: str, payload: BlockUpdate,
                       user: dict = Depends(require_permission("projects", "update"))):
    try:
        row = await mp.update_block(block_id, payload, user.get("email"), _org(user))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"data": serialize_doc(row)}


@router.delete("/blocks/{block_id}")
async def delete_block(block_id: str,
                       user: dict = Depends(require_permission("projects", "update"))):
    try:
        res = await mp.delete_block(block_id, _org(user))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit_log(user, "delete", "blocks", block_id, {})
    return {"data": res}


# ------------------------------------------------------------------ unit
@router.get("/units")
async def list_units(project_id: str = None, cluster_id: str = None, block_id: str = None,
                     status: str = None, construction_status: str = None,
                     unit_type_code: str = None, q: str = None, sort: str = "code",
                     direction: str = "asc", skip: int = 0, limit: int = 50,
                     user: dict = Depends(require_permission("units", "view"))):
    """Tabel unit lengkap: filter cluster/blok/status ganda/tipe + sort + paginasi."""
    res = await mp.units_listing(_org(user), project_id=project_id, cluster_id=cluster_id,
                                 block_id=block_id, status=status,
                                 construction_status=construction_status,
                                 unit_type_code=unit_type_code, q=q, sort=sort,
                                 direction=direction, skip=skip, limit=limit)
    return {"data": serialize_doc(res["data"]), "total": res["total"],
            "summary": res["summary"], "sortable": res["sortable"]}


@router.post("/blocks/{block_id}/units")
async def create_unit(block_id: str, payload: UnitCreateV2,
                      user: dict = Depends(require_permission("units", "update"))):
    try:
        row = await mp.create_unit(block_id, payload, user.get("email"), _org(user))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit_log(user, "create", "units", row["id"], {"code": row["code"]})
    return {"data": serialize_doc(row)}


@router.post("/blocks/{block_id}/units/generate")
async def generate_units(block_id: str, payload: UnitGenerateV2,
                         user: dict = Depends(require_permission("units", "update"))):
    try:
        res = await mp.generate_units(block_id, payload, user.get("email"), _org(user))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit_log(user, "create", "units", block_id,
                    {"generated": len(res["created"]), "skipped": len(res["skipped"])})
    return {"data": res}


@router.post("/units/import")
async def import_units(payload: UnitImport,
                       user: dict = Depends(require_permission("units", "update"))):
    """Impor massal. `dry_run=true` = pratinjau (tidak menulis apa pun)."""
    try:
        res = await mp.import_units(payload, user.get("email"), _org(user))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not payload.dry_run:
        await audit_log(user, "create", "units", payload.project_id,
                        {"imported": res["inserted"], "invalid": res["invalid"]})
    return {"data": res}


@router.get("/units/{unit_id}/360")
async def unit_360(unit_id: str, user: dict = Depends(require_permission("units", "view"))):
    """Unit 360: penjualan + pembangunan + dokumen + pembayaran + riwayat."""
    try:
        return {"data": serialize_doc(await mp.unit_360(unit_id, _org(user)))}
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.patch("/units/{unit_id}")
async def patch_unit(unit_id: str, payload: UnitPatchV2,
                     user: dict = Depends(require_permission("units", "update"))):
    try:
        row = await mp.patch_unit(unit_id, payload, user.get("email"), _org(user))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit_log(user, "update", "units", unit_id,
                    {"reason": payload.reason})
    return {"data": serialize_doc(row)}


@router.post("/units/{unit_id}/block")
async def toggle_unit_block(unit_id: str, payload: UnitBlockToggle,
                            user: dict = Depends(require_permission("units", "update"))):
    """Blokir / buka blokir unit (mis. rumah contoh, sengketa) — wajib beralasan."""
    try:
        row = await mp.toggle_unit_block(unit_id, payload, user.get("email"), _org(user))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit_log(user, "update", "units", unit_id,
                    {"blocked": payload.blocked, "reason": payload.reason})
    return {"data": serialize_doc(row)}


@router.post("/recompute-stats")
async def recompute(project_id: str = None,
                    user: dict = Depends(require_permission("projects", "update"))):
    return {"data": await mp.recompute_stats(project_id, _org(user))}
