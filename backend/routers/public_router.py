"""Showroom PUBLIK (tanpa login) — Fase 28b.

Satu halaman marketing per proyek yang bisa dibagikan ke calon pembeli (link + QR di
grup WhatsApp / bio Instagram / iklan). Yang keluar ke publik hanya data yang memang
boleh dilihat siapa pun: kode kavling, tipe, luas, orientasi, harga (bisa dimatikan),
status tersedia/terjual, dan geometri peta. **Tidak ada** identitas pembeli, nilai deal,
progres pembayaran, maupun id internal deal.

Akses dikunci `showroom_token` acak per proyek: link hanya hidup selama owner
mengaktifkannya (`showroom_enabled`), dan token bisa diputar ulang kapan pun.

Form tangkap lead memakai ENGINE yang sama dengan webhook iklan
(`engine.process_lead_capture`) sehingga lead publik ikut: dedup nomor, penugasan
sales otomatis, skoring, jejak `lead_capture_events`, dan pemicu automasi WhatsApp.
"""
import logging
import time

from fastapi import APIRouter, HTTPException, Request, Response

import doc_share as ds
import reference as ref
import p28_utils as p28
from core_utils import normalize_phone_e164, now_iso, serialize_doc
from db import db
from engine import add_activity, process_lead_capture
from models_p28 import ShowroomLeadCreate

router = APIRouter(prefix="/public", tags=["public-showroom"])
logger = logging.getLogger("sipro.showroom")

# Pembatas laju sederhana per proses (bukan pengganti WAF): cukup untuk menahan
# spam form dari satu IP tanpa menambah dependensi infrastruktur.
_HITS: dict = {}
RATE_MAX, RATE_WINDOW = 6, 600
LABEL_GROUPS = ("unit_status", "unit_type", "unit_orientation")


def _rate_ok(key: str) -> bool:
    now = time.time()
    hits = [t for t in _HITS.get(key, []) if now - t < RATE_WINDOW]
    if len(hits) >= RATE_MAX:
        _HITS[key] = hits
        return False
    hits.append(now)
    _HITS[key] = hits
    return True


async def _project_by_token(token: str) -> dict:
    proj = await db.projects.find_one(
        {"showroom_token": token, "showroom_enabled": True},
        {"_id": 0, "id": 1, "org_id": 1, "name": 1, "code": 1, "location": 1,
         "showroom_headline": 1, "showroom_contact_wa": 1, "showroom_show_price": 1,
         "construction_progress": 1})
    if not proj:
        raise HTTPException(404, "Halaman showroom tidak ditemukan atau sudah ditutup pemiliknya.")
    return proj


@router.get("/showroom/{token}")
async def public_showroom(token: str):
    """Data halaman showroom publik: proyek, peta, kavling (aman), statistik, label SSOT."""
    proj = await _project_by_token(token)
    org, pid = proj["org_id"], proj["id"]
    show_price = proj.get("showroom_show_price", True)
    rows = await db.units.find(
        {"org_id": org, "project_id": pid},
        {"_id": 0, "id": 1, "code": 1, "block": 1, "type": 1, "status": 1, "price": 1,
         "luas_bangunan": 1, "luas_tanah": 1, "orientation": 1, "corner": 1}
    ).sort("code", 1).to_list(2000)
    units = [p28.public_unit(u, show_price=show_price) for u in rows]
    plan = await db.site_plans.find_one({"org_id": org, "project_id": pid},
                                        {"_id": 0, "view_box": 1, "shapes": 1, "source": 1,
                                         "background": 1})
    if plan and (plan.get("background") or {}).get("file_id"):
        plan["background"] = {**plan["background"],
                              "url": f"/api/files/{plan['background']['file_id']}"}
    prices = [u["price"] for u in units if u["available"] and u.get("price")]
    types = sorted({u["type"] for u in units if u.get("type")})
    stats = {
        "total": len(units),
        "available": sum(1 for u in units if u["available"]),
        "taken": sum(1 for u in units if not u["available"]),
        "price_min": min(prices) if prices else None,
        "price_max": max(prices) if prices else None,
        "progress": proj.get("construction_progress", 0),
    }
    return {"data": {
        "project": {"name": proj.get("name"), "code": proj.get("code"),
                    "location": proj.get("location"),
                    "headline": proj.get("showroom_headline"),
                    "contact_wa": proj.get("showroom_contact_wa"),
                    "show_price": show_price},
        "plan": serialize_doc(plan),
        "units": units, "types": types, "stats": stats,
        "labels": {g: ref.labels(g) for g in LABEL_GROUPS},
    }}


@router.post("/showroom/{token}/lead")
async def public_showroom_lead(token: str, payload: ShowroomLeadCreate, request: Request):
    """Tangkap minat calon pembeli → lead nyata di pipeline (bukan sekadar email)."""
    proj = await _project_by_token(token)
    if payload.website:                     # honeypot terisi → bot
        raise HTTPException(400, "Pengiriman ditolak.")
    ip = (request.client.host if request.client else "?")
    if not _rate_ok(f"{ip}:{token}"):
        raise HTTPException(429, "Terlalu banyak pengiriman dari perangkat ini. "
                                 "Coba lagi beberapa menit lagi atau hubungi kami via WhatsApp.")
    org = proj["org_id"]
    phone = normalize_phone_e164(payload.phone)
    if not phone or len(phone) < 9:
        raise HTTPException(400, "Nomor WhatsApp tidak valid. Contoh: 0812xxxxxxx.")
    unit = None
    if payload.unit_code:
        unit = await db.units.find_one(
            {"org_id": org, "project_id": proj["id"], "code": payload.unit_code},
            {"_id": 0, "code": 1, "type": 1})
    note_parts = [f"Showroom publik {proj.get('name')}"]
    if unit:
        note_parts.append(f"minat kavling {unit['code']} ({unit.get('type') or '-'})")
    if payload.message:
        note_parts.append(payload.message.strip())
    note = " · ".join(note_parts)

    existing = await db.leads.find_one({"org_id": org, "phone": phone}, {"_id": 0, "id": 1})
    if existing:
        # Index unik leads(org,phone) melindungi data: jangan buat lead kembar — catat
        # minat baru sebagai aktivitas pada lead yang sudah ada.
        await db.leads.update_one({"id": existing["id"]},
                                  {"$set": {"updated_at": now_iso()}})
        await add_activity(entity_type="lead", entity_id=existing["id"], type="system",
                          body=f"Mengisi form showroom publik lagi — {note}",
                          actor="showroom", org_id=org)
        return {"data": {"ok": True, "duplicate": True,
                         "message": "Terima kasih! Nomor Anda sudah terdaftar — "
                                    "tim marketing kami akan segera menghubungi Anda."}}

    lead_id, dup = await process_lead_capture("showroom_public", {
        "name": payload.name.strip(), "phone": phone, "source": "showroom_public",
        "campaign": f"showroom:{proj.get('code') or proj.get('name')}",
        "interest": (unit or {}).get("type"), "message": note,
    }, org_id=org)
    logger.info("Lead showroom publik: proyek=%s lead=%s duplikat=%s", proj["id"], lead_id, dup)
    return {"data": {"ok": True, "duplicate": dup,
                     "message": "Terima kasih! Data Anda sudah kami terima — "
                                "tim marketing akan menghubungi via WhatsApp."}}


# ============================== dokumen berbagi (Fase 62) ==============================
@router.get("/docs/{token}")
async def shared_document(token: str):
    """Dokumen yang dibagikan ke PIHAK LUAR lewat tautan berbatas waktu.

    Tanpa login karena subkontraktor/vendor/pembeli tidak punya akun staf — tetapi satu
    token = SATU dokumen, berumur pendek, bisa dicabut, dan setiap pembukaan tercatat.
    Isi dokumen dirender ULANG dari data terkini, jadi tidak ada berkas basi yang beredar.
    """
    share = await ds.resolve(token)
    if not share:
        raise HTTPException(status_code=404, detail=(
            "Tautan dokumen ini sudah tidak berlaku. Mintakan tautan baru kepada "
            "penerbitnya."))
    pdf, nama = await ds.render(share)
    if not pdf:
        raise HTTPException(status_code=404, detail="Dokumen sudah tidak ada.")
    logger.info("Dokumen bagikan dibuka: %s %s", share["kind"], share.get("doc_number"))
    return Response(content=pdf, media_type="application/pdf", headers={
        "Content-Disposition": f'inline; filename="{nama}.pdf"',
        "Cache-Control": "private, no-store"})
