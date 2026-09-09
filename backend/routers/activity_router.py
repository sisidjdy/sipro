"""Activity feed (+ comments/@mention) and in-app notifications."""
import re

from fastapi import APIRouter, Depends, HTTPException

import notif_center as nc
import notif_prefs as npf
from db import db, ORG_ID
from core_utils import now_iso, serialize_doc, parse_pagination
from rbac import require_permission
from engine import add_activity, create_notification
from models import ActivityCreate, CommentCreate
from models_p65 import NotifGroupAction, NotifPrefsUpdate

router = APIRouter(tags=["collaboration"])


@router.get("/activities")
async def list_activities(entity_type: str, entity_id: str, skip: int = 0, limit: int = 50,
                          user: dict = Depends(require_permission("activities", "view"))):
    skip, limit = parse_pagination(skip, limit)
    q = {"org_id": user.get("org_id", ORG_ID), "entity_type": entity_type, "entity_id": entity_id}
    total = await db.activities.count_documents(q)
    rows = await db.activities.find(q, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    return {"data": serialize_doc(rows), "total": total}


@router.post("/activities")
async def create_activity(payload: ActivityCreate,
                          user: dict = Depends(require_permission("activities", "create"))):
    doc = await add_activity(
        entity_type=payload.entity_type, entity_id=payload.entity_id, body=payload.body,
        type=payload.type, actor=user.get("email"), mentions=payload.mentions,
        parent_id=payload.parent_id, org_id=user.get("org_id", ORG_ID),
    )
    return {"data": serialize_doc(doc)}


@router.post("/activities/{activity_id}/comment")
async def reply_comment(activity_id: str, payload: CommentCreate,
                        user: dict = Depends(require_permission("activities", "create"))):
    parent = await db.activities.find_one({"id": activity_id}, {"_id": 0})
    if not parent:
        raise HTTPException(status_code=404, detail="Aktivitas tidak ditemukan")
    doc = await add_activity(
        entity_type=parent["entity_type"], entity_id=parent["entity_id"], body=payload.body,
        type="comment", actor=user.get("email"), mentions=payload.mentions,
        parent_id=activity_id, org_id=user.get("org_id", ORG_ID),
    )
    return {"data": serialize_doc(doc)}


@router.get("/notifications")
async def list_notifications(unread_only: bool = False, state: str = None,
                            category: str = None, q: str = None, group: bool = False,
                            skip: int = 0, limit: int = 50,
                            user: dict = Depends(require_permission("notifications", "view"))):
    """Daftar notifikasi berkategori — Fase 64, berkelompok sejak Fase 65.

    `state` = `action` (perlu tindakan) | `unread` | `read` | `all`. Notifikasi yang
    tindakannya SUDAH dilakukan dicabut lebih dulu (`resolve_done`), sehingga daftar
    "Perlu tindakan" benar-benar menyusut ketika pekerjaan dikerjakan.
    `group=true` meringkas notifikasi KEMBAR menjadi satu baris berjumlah ("5× persetujuan
    diskon penawaran") tanpa menyembunyikan anggotanya (`group_members`).
    `unread_only=true` tetap didukung karena dipakai lonceng di TopBar.
    """
    skip, limit = parse_pagination(skip, limit)
    org, email = user.get("org_id", ORG_ID), user.get("email")
    dicabut = await nc.resolve_done(org, email)
    base = {"org_id": org, "user_email": email, "dismissed_at": None}
    keadaan = "unread" if unread_only else (state or "all")
    if keadaan in ("unread", "action"):
        base["read"] = False
    elif keadaan == "read":
        base["read"] = True
    if q and q.strip():
        pat = re.escape(q.strip())
        base["$or"] = [{"title": {"$regex": pat, "$options": "i"}},
                       {"body": {"$regex": pat, "$options": "i"}}]
    # Kategori & "perlu tindakan" adalah TURUNAN (bukan field tersimpan), jadi disaring
    # sesudah pengambilan — dibatasi 500 baris terbaru supaya tetap murah.
    ambil = await (db.notifications.find(base, {"_id": 0})
                   .sort("created_at", -1).limit(500).to_list(500))
    rows = [nc.decorate(n) for n in ambil]
    if category:
        pilih = set(category.split(","))
        rows = [r for r in rows if r["category"] in pilih]
    if keadaan == "action":
        rows = [r for r in rows if r["needs_action"] and not r.get("resolved_at")]
    baris = nc.group_rows(rows) if group else rows
    total = len(baris)
    ringkas = await nc.summary(org, email)
    return {"data": serialize_doc(baris[skip:skip + limit]), "total": total,
            "unread": ringkas["unread"], "summary": ringkas, "auto_resolved": dicabut,
            "grouped": bool(group), "rows_total": len(rows)}


# --------------------------------------------------------------- preferensi (Fase 65)
@router.get("/notifications/preferences")
async def get_notif_prefs(user: dict = Depends(require_permission("notifications", "view"))):
    """Preferensi saluran per kategori milik pemakai yang sedang masuk."""
    return {"data": await npf.get_prefs(user.get("org_id", ORG_ID), user.get("email"))}


@router.put("/notifications/preferences")
async def put_notif_prefs(payload: NotifPrefsUpdate,
                          user: dict = Depends(require_permission("notifications", "update"))):
    try:
        data = await npf.set_prefs(user.get("org_id", ORG_ID), user.get("email"),
                                   payload.channels)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"data": data, "message": "Preferensi notifikasi disimpan."}


@router.get("/notifications/wa-digest")
async def notif_wa_digest(user: dict = Depends(require_permission("notifications", "view"))):
    """Teks + tautan `wa.me` untuk kategori yang diizinkan lewat WhatsApp.

    Sistem TIDAK mengirim sendiri (kredensial WhatsApp perusahaan bukan milik sistem) —
    pemakai yang menekan kirim, sama seperti pengiriman dokumen Fase 62.
    """
    return {"data": await npf.wa_digest(user.get("org_id", ORG_ID), user.get("email"))}


# ----------------------------------------------------- aksi pada kelompok (Fase 65)
async def _group_ids(org: str, email: str, key: str) -> list:
    rows = await db.notifications.find(
        {"org_id": org, "user_email": email, "dismissed_at": None},
        {"_id": 0, "id": 1, "type": 1, "related_entity_type": 1, "title": 1}
    ).sort("created_at", -1).limit(500).to_list(500)
    return [r["id"] for r in rows if nc.group_key(r) == key]


@router.post("/notifications/group/read")
async def group_read(payload: NotifGroupAction,
                     user: dict = Depends(require_permission("notifications", "update"))):
    """Tandai SELURUH anggota satu kelompok kembar sebagai dibaca (satu tindakan, satu klik)."""
    org, email = user.get("org_id", ORG_ID), user.get("email")
    ids = await _group_ids(org, email, payload.group_key)
    if not ids:
        raise HTTPException(status_code=404, detail="Kelompok notifikasi tidak ditemukan")
    res = await db.notifications.update_many(
        {"id": {"$in": ids}, "user_email": email, "read": False},
        {"$set": {"read": True, "read_at": now_iso()}})
    return {"data": {"marked": res.modified_count, "members": len(ids)}}


@router.post("/notifications/group/dismiss")
async def group_dismiss(payload: NotifGroupAction,
                        user: dict = Depends(require_permission("notifications", "update"))):
    """Sembunyikan seluruh anggota kelompok (TIDAK dihapus — jejaknya tetap bisa diaudit)."""
    org, email = user.get("org_id", ORG_ID), user.get("email")
    ids = await _group_ids(org, email, payload.group_key)
    if not ids:
        raise HTTPException(status_code=404, detail="Kelompok notifikasi tidak ditemukan")
    ts = now_iso()
    res = await db.notifications.update_many(
        {"id": {"$in": ids}, "user_email": email},
        {"$set": {"dismissed_at": ts, "read": True, "read_at": ts}})
    return {"data": {"dismissed": res.modified_count, "members": len(ids)}}


@router.post("/notifications/{notif_id}/read")
async def mark_read(notif_id: str, user: dict = Depends(require_permission("notifications", "update"))):
    res = await db.notifications.update_one(
        {"id": notif_id, "user_email": user.get("email")}, {"$set": {"read": True, "read_at": now_iso()}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Notifikasi tidak ditemukan")
    return {"message": "Ditandai sudah dibaca"}


@router.post("/notifications/{notif_id}/dismiss")
async def dismiss(notif_id: str,
                  user: dict = Depends(require_permission("notifications", "update"))):
    """Sembunyikan satu notifikasi dari daftar (TIDAK dihapus — jejaknya tetap bisa diaudit)."""
    ts = now_iso()
    res = await db.notifications.update_one(
        {"id": notif_id, "user_email": user.get("email")},
        {"$set": {"dismissed_at": ts, "read": True, "read_at": ts}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Notifikasi tidak ditemukan")
    return {"data": {"ok": True, "id": notif_id}}


@router.post("/notifications/clear-read")
async def clear_read(user: dict = Depends(require_permission("notifications", "update"))):
    """Bersihkan seluruh notifikasi yang SUDAH dilihat, supaya daftar tidak menumpuk."""
    res = await db.notifications.update_many(
        {"org_id": user.get("org_id", ORG_ID), "user_email": user.get("email"),
         "read": True, "dismissed_at": None},
        {"$set": {"dismissed_at": now_iso()}})
    return {"data": {"cleared": res.modified_count}}


@router.post("/notifications/read-all")
async def mark_all_read(category: str = None,
                        user: dict = Depends(require_permission("notifications", "update"))):
    """Tandai dibaca — seluruhnya, atau hanya SATU kategori bila `?category=` disebut."""
    org, email = user.get("org_id", ORG_ID), user.get("email")
    if not category:
        res = await db.notifications.update_many(
            {"user_email": email, "read": False},
            {"$set": {"read": True, "read_at": now_iso()}})
        return {"data": {"marked": res.modified_count}}
    rows = await db.notifications.find(
        {"org_id": org, "user_email": email, "read": False, "dismissed_at": None},
        {"_id": 0, "id": 1, "type": 1, "related_entity_type": 1, "title": 1, "body": 1}
    ).limit(1000).to_list(1000)
    ids = [r["id"] for r in rows if nc.category_of(r) == category]
    if not ids:
        return {"data": {"marked": 0}}
    res = await db.notifications.update_many(
        {"id": {"$in": ids}}, {"$set": {"read": True, "read_at": now_iso()}})
    return {"data": {"marked": res.modified_count}}
