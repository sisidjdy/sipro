"""Manajemen Data — migrasi Excel (template/impor/ekspor) + backup/restore JSON.

Khusus peran FULL_ACCESS (super_admin/owner) — data lintas modul, bukan satu resource RBAC.
"""
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from db import ORG_ID
from rbac import has_role, FULL_ACCESS_ROLES, audit_log
from security import get_current_user
from data_mgmt_schema import public_entities
from data_mgmt_excel import build_workbook, parse_workbook
from data_mgmt_import import run_import
from data_mgmt_export import export_rows, master_counts
import data_mgmt_backup as bk
import data_mgmt_purge as pg

router = APIRouter(prefix="/data-mgmt", tags=["data-mgmt"])
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
MAX_UPLOAD = 60 * 1024 * 1024


async def require_data_admin(user: dict = Depends(get_current_user)) -> dict:
    if not has_role(user, *FULL_ACCESS_ROLES):
        raise HTTPException(status_code=403, detail="Akses ditolak: khusus admin/owner.")
    return user


def _org(user: dict) -> str:
    return user.get("org_id", ORG_ID)


def _attachment(content: bytes, filename: str, media: str) -> Response:
    return Response(content=content, media_type=media, headers={
        "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"})


async def _read_upload(file: UploadFile, exts: tuple) -> bytes:
    name = (file.filename or "").lower()
    if not name.endswith(exts):
        raise HTTPException(status_code=400, detail=f"Berkas harus berekstensi {', '.join(exts)}.")
    content = await file.read()
    if len(content) > MAX_UPLOAD:
        raise HTTPException(status_code=400, detail="Berkas melebihi 60 MB.")
    if not content:
        raise HTTPException(status_code=400, detail="Berkas kosong.")
    return content


@router.get("/overview")
async def overview(user: dict = Depends(require_data_admin)):
    org = _org(user)
    return {"entities": public_entities(), "counts": await master_counts(org),
            "snapshots": await bk.list_snapshots(org)}


@router.get("/template.xlsx")
async def download_template(with_example: bool = True, user: dict = Depends(require_data_admin)):
    content = build_workbook({}, with_example=with_example)
    return _attachment(content, "SIPRO_Template_Migrasi_Master.xlsx", XLSX)


@router.get("/public/template.xlsx")
async def download_template_public(with_example: bool = True):
    """Template kosong (tanpa data organisasi) — boleh dibagikan ke klien lewat tautan."""
    content = build_workbook({}, with_example=with_example)
    return _attachment(content, "SIPRO_Template_Migrasi_Master.xlsx", XLSX)


@router.get("/export.xlsx")
async def export_master(user: dict = Depends(require_data_admin)):
    org = _org(user)
    content = build_workbook(await export_rows(org))
    await audit_log(user, "export", "data_mgmt", meta={"format": "xlsx"})
    return _attachment(content, f"SIPRO_Master_{org}.xlsx", XLSX)


@router.post("/import")
async def import_excel(file: UploadFile = File(...), mode: str = Form("upsert"),
                       dry_run: bool = Form(True), user: dict = Depends(require_data_admin)):
    if mode not in ("upsert", "skip"):
        raise HTTPException(status_code=400, detail="Mode harus 'upsert' atau 'skip'.")
    content = await _read_upload(file, (".xlsx", ".xlsm"))
    try:
        parsed = parse_workbook(content)
    except Exception as e:  # noqa: BLE001 — openpyxl melempar banyak jenis galat untuk berkas rusak
        raise HTTPException(status_code=400, detail=f"Berkas Excel tidak bisa dibaca: {e}")
    if not any(parsed["sheets"].values()):
        raise HTTPException(status_code=400, detail=(
            "Tidak ada baris data yang dikenali. Pastikan nama sheet & baris kunci kolom "
            "mengikuti template."))
    report = await run_import(parsed["sheets"], _org(user), user.get("email"), mode, dry_run)
    report["unknown_sheets"] = parsed["unknown_sheets"]
    report["filename"] = file.filename
    if not dry_run:
        await audit_log(user, "import", "data_mgmt",
                        meta={"filename": file.filename, "mode": mode, "totals": report["totals"]})
    return report


@router.get("/backup.json")
async def download_backup(include_files: bool = False, user: dict = Depends(require_data_admin)):
    org = _org(user)
    payload = await bk.dump_org(org, user.get("email"), include_files, label="unduh")
    await audit_log(user, "backup", "data_mgmt", meta={"include_files": include_files})
    stamp = payload["meta"]["created_at"][:19].replace(":", "")
    return _attachment(bk.to_bytes(payload), f"SIPRO_Backup_{org}_{stamp}.json",
                       "application/json")


@router.post("/snapshots")
async def create_snapshot(label: str = Form(""), include_files: bool = Form(True),
                          user: dict = Depends(require_data_admin)):
    rec = await bk.save_snapshot(_org(user), user.get("email"), include_files, label.strip())
    await audit_log(user, "snapshot", "data_mgmt", entity_id=rec["id"], meta={"label": label})
    return rec


@router.get("/snapshots")
async def list_snapshots(user: dict = Depends(require_data_admin)):
    return await bk.list_snapshots(_org(user))


@router.get("/snapshots/{sid}/download")
async def download_snapshot(sid: str, user: dict = Depends(require_data_admin)):
    try:
        rec, path = await bk.get_snapshot(_org(user), sid)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return _attachment(path.read_bytes(), rec["filename"], "application/json")


@router.delete("/snapshots/{sid}")
async def delete_snapshot(sid: str, user: dict = Depends(require_data_admin)):
    try:
        res = await bk.delete_snapshot(_org(user), sid)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    await audit_log(user, "delete_snapshot", "data_mgmt", entity_id=sid)
    return res


async def _do_restore(payload: dict, user: dict, mode: str, confirm: str, source: str) -> dict:
    if confirm.strip().upper() != "RESTORE":
        raise HTTPException(status_code=400, detail="Ketik RESTORE untuk mengonfirmasi.")
    try:
        res = await bk.restore(payload, _org(user), user.get("email"), mode, user)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit_log(user, "restore", "data_mgmt",
                    meta={"mode": mode, "source": source, "documents": res["documents"]})
    return res


@router.post("/snapshots/{sid}/restore")
async def restore_snapshot(sid: str, mode: str = Form("replace"), confirm: str = Form(""),
                           user: dict = Depends(require_data_admin)):
    try:
        rec, path = await bk.get_snapshot(_org(user), sid)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    payload = bk.parse_backup(path.read_bytes())
    return await _do_restore(payload, user, mode, confirm, f"snapshot:{rec['filename']}")


@router.post("/restore")
async def restore_upload(file: UploadFile = File(...), mode: str = Form("replace"),
                         confirm: str = Form(""), user: dict = Depends(require_data_admin)):
    content = await _read_upload(file, (".json",))
    try:
        payload = bk.parse_backup(content)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return await _do_restore(payload, user, mode, confirm, f"upload:{file.filename}")


@router.post("/restore/inspect")
async def inspect_backup(file: UploadFile = File(...), user: dict = Depends(require_data_admin)):
    content = await _read_upload(file, (".json",))
    try:
        payload = bk.parse_backup(content)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return payload["meta"]


class PurgeRequest(BaseModel):
    groups: list[str]
    confirm: str = ""
    snapshot: bool = True


@router.get("/purge/preview")
async def purge_preview(user: dict = Depends(require_data_admin)):
    return await pg.preview(_org(user))


@router.post("/purge")
async def purge_operational(payload: PurgeRequest, user: dict = Depends(require_data_admin)):
    if payload.confirm.strip().upper() != "HAPUS":
        raise HTTPException(status_code=400, detail="Ketik HAPUS untuk mengonfirmasi.")
    org = _org(user)
    snap = None
    if payload.snapshot:
        snap = await bk.save_snapshot(org, user.get("email"), True, "pra-hapus-massal", kind="auto")
    try:
        res = await pg.purge(org, payload.groups, user.get("email"))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit_log(user, "purge", "data_mgmt", meta={"groups": payload.groups, "deleted": res["deleted"]})
    res["snapshot_before"] = snap
    return res
