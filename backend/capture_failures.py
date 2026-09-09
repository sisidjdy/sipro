"""Antrean LEAD GAGAL MASUK (`capture.failed`) — Fase 30c.

Masalah nyata yang ditutup: webhook iklan (Meta/Google/TikTok/WA/web form) yang
mengirim payload cacat — nomor HP kosong, JSON rusak, field salah nama — sebelumnya
dibalas 422 lalu HILANG. Uang iklan sudah terbayar, tetapi lead-nya tidak pernah ada
di CRM dan tak seorang pun tahu. Lebih buruk: payload tanpa nomor HP membuat kunci
de-duplikasi `provider:None` bertabrakan, sehingga lead berikutnya yang juga tanpa
nomor dianggap "duplikat" dan dibuang diam-diam.

Sekarang setiap kegagalan:
  * DISIMPAN utuh (payload asli + alasan yang bisa dibaca manusia),
  * memicu event `capture.failed` → tugas jobdesk DM-02 di Work Hub + notifikasi,
  * bisa DIPERBAIKI datanya lalu DIULANG oleh tim (lead tetap terselamatkan),
  * kegagalan SEMENTARA (gangguan DB/server) dicoba ulang OTOMATIS maksimal 3 kali,
    sedangkan kegagalan DATA menunggu manusia — supaya tidak berputar sia-sia.
"""
import json
import logging

from core_utils import new_id, normalize_phone_e164, now_iso
from db import db, ORG_ID
from engine import create_notification, dispatch_pending, emit, process_lead_capture

logger = logging.getLogger("sipro.capture")

KIND_DATA = "data"              # butuh koreksi manusia
KIND_TRANSIENT = "transient"    # layak dicoba ulang otomatis
OPEN = "open"
RESOLVED = "resolved"
DISCARDED = "discarded"
MAX_AUTO_ATTEMPTS = 3
EDITABLE = ("name", "phone", "email", "source", "campaign", "message", "interest")


async def read_json(request) -> tuple:
    """Baca body JSON webhook. Kembalikan (payload, error_text) tanpa pernah melempar."""
    try:
        raw = await request.body()
    except Exception as e:  # noqa: BLE001
        return None, f"Body permintaan tidak bisa dibaca: {e}"
    if not raw:
        return None, "Body kosong: provider tidak mengirim data apa pun."
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        return {"_raw_text": raw[:2000].decode("utf-8", "replace")}, f"JSON tidak valid: {e}"
    if not isinstance(data, dict):
        return {"_raw_text": str(data)[:2000]}, "Payload harus berupa objek JSON."
    return data, None


def validate(payload: dict) -> tuple:
    """Validasi minimum agar lead benar-benar bisa ditindaklanjuti. -> (bersih, error)."""
    data = dict(payload or {})
    phone = str(data.get("phone") or "").strip()
    digits = "".join(ch for ch in phone if ch.isdigit())
    if not digits:
        return None, ("Nomor WhatsApp/telepon tidak ada di payload — lead tidak bisa "
                      "dihubungi maupun dide-duplikasi.")
    if len(digits) < 9:
        return None, f"Nomor telepon terlalu pendek ({phone}) — minimal 9 digit."
    data["phone"] = normalize_phone_e164(phone)
    name = str(data.get("name") or "").strip()
    data["name"] = name or "Lead Baru (tanpa nama)"
    return data, None


async def _notify_supervisors(org: str, provider: str, reason: str, fid: str):
    """Beri tahu supervisor Digital Marketing (fallback: pengelola pemasaran)."""
    rows = await db.users.find(
        {"org_id": org, "is_active": {"$ne": False},
         "$or": [{"division": "digital_marketing", "level": "supervisor"},
                 {"role": {"$in": ["dm_supervisor", "marketing_admin", "sales_manager"]}}]},
        {"_id": 0, "email": 1}).to_list(10)
    seen = []
    for r in rows:
        if r.get("email") and r["email"] not in seen:
            seen.append(r["email"])
    for email in seen[:3]:
        await create_notification(
            user_email=email, title=f"Lead gagal masuk ({provider})",
            body=reason[:180], type="lead",
            related_entity_type="capture_failure", related_entity_id=fid, org_id=org)


async def record(provider: str, payload: dict, reason: str, *, kind: str = KIND_DATA,
                 org_id: str = ORG_ID) -> dict:
    """Simpan kegagalan + picu event/tugas/notifikasi. Tidak pernah menggagalkan webhook."""
    ts = now_iso()
    doc = {
        "id": new_id(), "org_id": org_id, "provider": provider,
        "raw_payload": payload or {}, "payload": dict(payload or {}),
        "reason": str(reason or "Kegagalan tidak diketahui")[:400], "kind": kind,
        "status": OPEN, "needs_fix": kind == KIND_DATA, "attempts": 0,
        "lead_id": None, "resolved_at": None, "resolved_by": None,
        "created_at": ts, "updated_at": ts,
    }
    await db.lead_capture_failures.insert_one(dict(doc))
    doc.pop("_id", None)
    try:
        await emit("capture.failed", "capture_failure", doc["id"],
                  {"label": f"{provider}: {doc['reason'][:60]}", "provider": provider},
                  org_id=org_id)
        await _notify_supervisors(org_id, provider, doc["reason"], doc["id"])
        await dispatch_pending()
    except Exception:  # noqa: BLE001 - antrean tetap tersimpan walau notifikasi gagal
        logger.exception("Gagal memicu event/notifikasi capture.failed %s", doc["id"])
    logger.warning("Lead capture GAGAL (%s): %s", provider, doc["reason"])
    return doc


async def get(fid: str, org: str) -> dict:
    row = await db.lead_capture_failures.find_one({"id": fid, "org_id": org}, {"_id": 0})
    return row


async def listing(org: str, *, status: str = None, provider: str = None,
                  skip: int = 0, limit: int = 20) -> tuple:
    q = {"org_id": org}
    if status:
        q["status"] = status
    if provider:
        q["provider"] = provider
    total = await db.lead_capture_failures.count_documents(q)
    rows = await db.lead_capture_failures.find(q, {"_id": 0}).sort(
        "created_at", -1).skip(skip).limit(limit).to_list(limit)
    return rows, total


async def summary(org: str) -> dict:
    """Ringkasan untuk lencana & papan: berapa tertahan, per provider, per alasan."""
    out = {"open": 0, "resolved": 0, "discarded": 0, "needs_fix": 0,
           "by_provider": {}, "recent_reason": None}
    for st in (OPEN, RESOLVED, DISCARDED):
        out[st] = await db.lead_capture_failures.count_documents({"org_id": org, "status": st})
    out["needs_fix"] = await db.lead_capture_failures.count_documents(
        {"org_id": org, "status": OPEN, "needs_fix": True})
    rows = await db.lead_capture_failures.find(
        {"org_id": org, "status": OPEN}, {"_id": 0, "provider": 1, "reason": 1}).to_list(200)
    for r in rows:
        p = r.get("provider") or "lain"
        out["by_provider"][p] = out["by_provider"].get(p, 0) + 1
    if rows:
        out["recent_reason"] = rows[0].get("reason")
    return out


async def _close_tasks(org: str, fid: str, actor: str, outcome: str) -> int:
    ts = now_iso()
    res = await db.tasks.update_many(
        {"org_id": org, "related_entity_type": "capture_failure", "related_entity_id": fid,
         "status": {"$in": ["open", "in_progress", "snoozed", "submitted"]}},
        {"$set": {"status": "done", "review": "approved", "completed_at": ts,
                  "completed_by": actor, "verified_by": "system", "outcome": outcome,
                  "updated_at": ts}})
    return res.modified_count


async def retry(fid: str, org: str, *, actor: str = "system", fixes: dict = None) -> dict:
    """Coba masukkan lead lagi (boleh dengan koreksi data). Melempar ValueError bila cacat."""
    row = await get(fid, org)
    if not row:
        raise LookupError("Data gagal-masuk tidak ditemukan.")
    if row.get("status") == RESOLVED:
        raise ValueError("Sudah diselesaikan sebelumnya (lead sudah dibuat).")
    if row.get("status") == DISCARDED:
        raise ValueError("Sudah dibuang — tidak bisa diulang. Buat lead manual bila perlu.")
    payload = dict(row.get("payload") or row.get("raw_payload") or {})
    for k, v in (fixes or {}).items():
        if k in EDITABLE and str(v or "").strip():
            payload[k] = str(v).strip()
    clean, err = validate(payload)
    ts = now_iso()
    if err:
        await db.lead_capture_failures.update_one({"id": fid, "org_id": org}, {
            "$set": {"payload": payload, "reason": err, "kind": KIND_DATA, "needs_fix": True,
                     "last_attempt_at": ts, "updated_at": ts},
            "$inc": {"attempts": 1}})
        raise ValueError(err)
    try:
        lead_id, duplicate = await process_lead_capture(row.get("provider") or "website",
                                                        clean, org_id=org)
    except Exception as e:  # noqa: BLE001
        await db.lead_capture_failures.update_one({"id": fid, "org_id": org}, {
            "$set": {"payload": payload, "reason": f"Gagal saat memproses ulang: {e}",
                     "kind": KIND_TRANSIENT, "needs_fix": False, "last_attempt_at": ts,
                     "updated_at": ts},
            "$inc": {"attempts": 1}})
        raise ValueError(f"Gagal memproses ulang: {e}")
    await db.lead_capture_failures.update_one({"id": fid, "org_id": org}, {
        "$set": {"payload": clean, "status": RESOLVED, "needs_fix": False,
                 "lead_id": lead_id, "duplicate": bool(duplicate), "resolved_at": ts,
                 "resolved_by": actor, "last_attempt_at": ts, "updated_at": ts},
        "$inc": {"attempts": 1}})
    await _close_tasks(org, fid, actor,
                       f"Lead diselamatkan{' (duplikat)' if duplicate else ''}: {lead_id}")
    return {"lead_id": lead_id, "duplicate": bool(duplicate),
            "failure": await get(fid, org)}


async def discard(fid: str, org: str, *, actor: str, reason: str) -> dict:
    """Buang antrean dengan ALASAN (mis. spam/uji coba) — tetap tersimpan untuk audit."""
    row = await get(fid, org)
    if not row:
        raise LookupError("Data gagal-masuk tidak ditemukan.")
    if row.get("status") == RESOLVED:
        raise ValueError("Sudah diselesaikan — tidak perlu dibuang.")
    why = str(reason or "").strip()
    if len(why) < 3:
        raise ValueError("Alasan wajib diisi (minimal 3 karakter) agar bisa diaudit.")
    ts = now_iso()
    await db.lead_capture_failures.update_one({"id": fid, "org_id": org}, {"$set": {
        "status": DISCARDED, "needs_fix": False, "discard_reason": why[:300],
        "resolved_by": actor, "resolved_at": ts, "updated_at": ts}})
    await _close_tasks(org, fid, actor, f"Dibuang: {why[:120]}")
    return await get(fid, org)


async def auto_retry_tick() -> dict:
    """Coba ulang OTOMATIS hanya kegagalan sementara (maks 3 kali) — dijalankan scheduler."""
    out = {"tried": 0, "recovered": 0}
    rows = await db.lead_capture_failures.find(
        {"status": OPEN, "kind": KIND_TRANSIENT,
         "attempts": {"$lt": MAX_AUTO_ATTEMPTS}}, {"_id": 0, "id": 1, "org_id": 1}).to_list(50)
    for r in rows:
        out["tried"] += 1
        try:
            await retry(r["id"], r.get("org_id", ORG_ID), actor="system")
            out["recovered"] += 1
        except (ValueError, LookupError):
            continue
    return out
