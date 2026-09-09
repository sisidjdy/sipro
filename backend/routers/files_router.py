"""Files: generic upload + download (backed by storage abstraction).

Staff-authenticated. Downloads support both Bearer header and `?auth=<token>`
query param so <img src> can render protected images (portal reuses this in P8).

Fase 30b — setiap GAMBAR yang diunggah otomatis: dikompres (maks 1600 px, JPEG
progresif), diberi watermark konteks (proyek/kavling + organisasi + tanggal WIB),
dibuang metadata EXIF/GPS-nya, dan dibuatkan thumbnail. Galeri memakai
`?variant=thumb` supaya kuota pembeli tidak habis untuk gambar ukuran penuh.
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query, Request
from fastapi.responses import Response

import photo_utils
import storage
from core_utils import serialize_doc, parse_pagination
from db import db, ORG_ID, ORG_NAME
from rbac import require_permission
from security import get_current_user

router = APIRouter(prefix="/files", tags=["files"])


@router.get("")
async def list_files(owner_type: str = None, owner_id: str = None, skip: int = 0, limit: int = 50,
                     user: dict = Depends(require_permission("files", "view"))):
    skip, limit = parse_pagination(skip, limit)
    q = {"org_id": user.get("org_id", ORG_ID), "is_deleted": False}
    if owner_type:
        q["owner_type"] = owner_type
    if owner_id:
        q["owner_id"] = owner_id
    total = await db.files.count_documents(q)
    rows = await db.files.find(q, {"_id": 0, "data_b64": 0}).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    return {"data": serialize_doc(rows), "total": total}


async def _org_name(org_id: str) -> str:
    org = await db.orgs.find_one({"id": org_id}, {"_id": 0, "name": 1}) or {}
    return org.get("name") or ORG_NAME


async def _derive_context(org_id: str, owner_type: str, owner_id: str) -> str:
    """Turunkan konteks watermark dari data bila pemanggil tidak mengirimnya.

    Kenapa di server? Foto lapangan diunggah dari beberapa layar berbeda; kalau konteks
    hanya diandalkan dari frontend, ada layar yang lupa mengirim dan fotonya jadi tanpa
    penanda. Di sini id pemilik dicari di koleksi yang relevan sehingga cap watermark
    selalu menyebut proyek/kavling/temuan yang benar.
    """
    if not owner_id:
        return None
    proj = await db.projects.find_one({"id": owner_id}, {"_id": 0, "name": 1})
    if proj:
        return proj.get("name")
    unit = await db.units.find_one({"id": owner_id}, {"_id": 0, "code": 1, "project_id": 1})
    if unit:
        p = await db.projects.find_one({"id": unit.get("project_id")}, {"_id": 0, "name": 1}) or {}
        return " · ".join(x for x in [p.get("name"), f"Kavling {unit.get('code')}"] if x)
    punch = await db.punch_items.find_one({"id": owner_id},
                                          {"_id": 0, "title": 1, "unit_code": 1, "project_id": 1})
    if punch:
        p = await db.projects.find_one({"id": punch.get("project_id")}, {"_id": 0, "name": 1}) or {}
        return " · ".join(x for x in [p.get("name"),
                                      f"Kavling {punch['unit_code']}" if punch.get("unit_code") else None,
                                      punch.get("title")] if x)[:70]
    task = await db.tasks.find_one({"id": owner_id}, {"_id": 0, "title": 1})
    if task:
        return str(task.get("title") or "")[:70]
    return None


@router.post("/upload")
async def upload_file(file: UploadFile = File(...), owner_type: str = Form("generic"),
                      owner_id: str = Form(None), doc_type: str = Form(None),
                      watermark: str = Form(None), optimize: bool = Form(True),
                      lat: float = Form(None), lng: float = Form(None),
                      accuracy: float = Form(None), captured_at: str = Form(None),
                      user: dict = Depends(require_permission("files", "create"))):
    """Unggah berkas.

    `watermark` = konteks yang dicap pada foto (mis. "Cluster Asri Blok A · Kavling A-01").
    Baris kedua (organisasi + tanggal/jam WIB) SELALU ditambahkan sistem, jadi foto tetap
    punya penanda asal walau pemanggil tidak mengirim konteks apa pun. `optimize=false`
    dipakai untuk berkas yang harus utuh (mis. lampiran bukti resmi tanpa perubahan).

    Fase 32: `lat/lng/accuracy/captured_at` opsional — koordinat saat foto DIAMBIL,
    dikirim eksplisit oleh aplikasi. Metadata EXIF/GPS pada berkas tetap dibuang (privasi
    lokasi rumah pembeli); koordinat disimpan sebagai field terstruktur yang bisa diaudit
    dan bisa diwajibkan/dimatikan admin lewat Kebijakan Bukti Kerja.
    """
    data = await file.read()
    org_id = user.get("org_id", ORG_ID)
    lines = None
    if optimize:
        context = (watermark or "").strip() or await _derive_context(org_id, owner_type, owner_id)
        lines = photo_utils.context_lines(org_name=await _org_name(org_id), context=context)
    try:
        rec = await storage.save_file(
            data=data, filename=file.filename or "file.bin",
            content_type=file.content_type or "application/octet-stream",
            org_id=org_id, owner_type=owner_type, owner_id=owner_id,
            uploaded_by=user.get("email"), doc_type=doc_type, tag=owner_type or "file",
            optimize=bool(optimize), watermark_lines=lines,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if lat is not None and lng is not None:
        import build_policy as bpol
        geo = bpol.geo_doc({"lat": lat, "lng": lng, "accuracy": accuracy,
                            "captured_at": captured_at})
        if geo:
            await db.files.update_one({"id": rec["id"]}, {"$set": {"geo": geo}})
            rec["geo"] = geo
    return {"data": rec}


@router.get("/{file_id}/meta")
async def file_meta(file_id: str, user: dict = Depends(require_permission("files", "view"))):
    rec = await db.files.find_one({"id": file_id, "org_id": user.get("org_id", ORG_ID),
                                   "is_deleted": False}, {"_id": 0, "data_b64": 0})
    if not rec:
        raise HTTPException(status_code=404, detail="File tidak ditemukan")
    return {"data": serialize_doc(rec)}


@router.get("/{file_id}")
async def download_file(file_id: str, request: Request, auth: str = Query(None),
                       variant: str = Query(None)):
    # Auth: Bearer header or ?auth= query (image tags cannot send headers).
    token = auth or None
    if token:
        # emulate a Bearer header for get_current_user
        from starlette.datastructures import MutableHeaders
        mh = MutableHeaders(raw=list(request.headers.raw))
        mh["Authorization"] = f"Bearer {token}"
        request._headers = mh
    user = await get_current_user(request)
    rec = await db.files.find_one({"id": file_id, "org_id": user.get("org_id", ORG_ID),
                                   "is_deleted": False}, {"_id": 0})
    if not rec:
        raise HTTPException(status_code=404, detail="File tidak ditemukan")
    path, want_type = await storage.variant_source(rec, variant)
    try:
        data, ctype = await storage.get_file_bytes(path, rec.get("provider"))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Objek file tidak ditemukan di storage")
    return Response(content=data, media_type=want_type or ctype,
                    headers={"Content-Disposition": f'inline; filename="{rec.get("original_filename", file_id)}"',
                             "Cache-Control": "private, max-age=3600"})
