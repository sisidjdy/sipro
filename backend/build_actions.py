"""BUILD ACTIONS (Fase 31) — aksi berbukti pada item jadwal pembangunan.

Semua aturan "penjaga" ada di sini supaya tidak tersebar di router:
  * ajukan hasil  → wajib catatan + foto minimal + checklist kritis lulus + gerbang terbuka
  * verifikasi    → hanya supervisor, dan TIDAK BOLEH orang yang mengajukan (pemisahan tugas)
  * tolak         → wajib alasan, item kembali menjadi 'rework' + tugas perbaikan
  * override      → menerobos gerbang wajib alasan SSOT + catatan, dilaporkan ke direksi
  * penyebab telat→ kode SSOT (untuk analitik penyebab keterlambatan yang nyata)
  * hentikan/lanjutkan jadwal (mis. hujan panjang, izin belum turun)
"""
import logging
from datetime import datetime, timezone

from pymongo.errors import DuplicateKeyError

import build_engine as be
import build_instruction as bi
import build_policy as bpol
import workhub as wh
from core_utils import new_id, now_iso, today_iso_date
from db import db, ORG_ID
from engine import add_activity, create_notification, emit
from reference_p31 import DELAY_CAUSE_LABEL

logger = logging.getLogger("sipro.build.actions")


def _hist(action: str, actor: str, note: str = None, extra: dict = None) -> dict:
    return {"at": now_iso(), "action": action, "actor": actor, "note": note, **(extra or {})}


async def _owners(org: str) -> list:
    rows = await db.users.find({"org_id": org, "role": {"$in": ["owner", "super_admin"]},
                                "is_active": True}, {"_id": 0, "email": 1}).to_list(20)
    return [r["email"] for r in rows]


async def start_item(org: str, item: dict, sched: dict, actor: str) -> dict:
    if item.get("status") not in ("ready", "rework", "in_progress"):
        raise ValueError(_blocked_message(item))
    await db.build_items.update_one({"id": item["id"]}, {"$set": {
        "status": "in_progress", "started_at": item.get("started_at") or now_iso(),
        "updated_at": now_iso()},
        "$push": {"history": _hist("start", actor)}})
    return await db.build_items.find_one({"id": item["id"]}, {"_id": 0})


def _blocked_message(item: dict) -> str:
    reasons = item.get("gate_reasons") or []
    if reasons:
        detail = " ".join(r.get("detail") or "" for r in reasons)
        return f"Pekerjaan ini masih TERKUNCI. {detail}".strip()
    if item.get("status") == "submitted":
        return "Hasil pekerjaan ini sudah diajukan dan sedang menunggu verifikasi."
    if item.get("status") == "done":
        return "Pekerjaan ini sudah selesai & terverifikasi."
    return f"Status '{item.get('status')}' tidak bisa dikerjakan."


STALE_CLAIM_SECONDS = 120


def _age_seconds(ts) -> float:
    try:
        if isinstance(ts, datetime):
            base = ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
        else:
            base = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - base).total_seconds()
    except Exception:  # noqa: BLE001 — cap waktu rusak jangan sampai memblokir pengajuan
        return STALE_CLAIM_SECONDS + 1


async def _claim_ref(org: str, ref: str) -> bool:
    """Kunci `client_ref` SEBELUM item disentuh (Fase 35 — antrean offline).

    Kenapa perlu: mandor bisa membuka aplikasi di dua tab/jendela; keduanya membaca
    antrean yang sama (IndexedDB) dan bisa mengirim pekerjaan yang sama BERBARENGAN.
    Tanpa kunci ini keduanya lolos pemeriksaan "sudah pernah diterima?", bukti foto
    tercatat dua kali, lalu penyisipan jejak audit yang kedua gagal dengan 500.

    Klaim yang BASI (proses mati di tengah jalan) boleh diambil ulang — kalau tidak,
    antrean akan menganggap pekerjaan "sudah terkirim" padahal belum: kehilangan senyap,
    justru hal yang ingin dicegah fase ini. Koleksi kunci ini bersifat sementara dan
    dibersihkan sendiri lewat indeks TTL (lihat seed_phase31.ensure_build_indexes).
    """
    now = datetime.now(timezone.utc)
    try:
        await db.build_submit_claims.insert_one({"org_id": org, "client_ref": ref, "at": now})
        return True
    except DuplicateKeyError:
        pass
    doc = await db.build_submit_claims.find_one({"org_id": org, "client_ref": ref})
    if doc and _age_seconds(doc.get("at")) > STALE_CLAIM_SECONDS:
        await db.build_submit_claims.update_one({"_id": doc["_id"]}, {"$set": {"at": now}})
        return True
    return False


async def submit_item(org: str, item: dict, sched: dict, payload, user: dict) -> dict:
    """Ajukan hasil kerja + bukti, dengan pengaman antrean offline (Fase 35).

    `client_ref` membuat pengiriman ULANG aman: hasil lama diputar ulang, tidak ada
    pengajuan/bukti kedua. Seluruh penjaga mutu Fase 31/32 tetap berjalan di dalam.
    """
    ref = (getattr(payload, "client_ref", None) or "").strip() or None
    if not ref:
        return await _submit_item(org, item, sched, payload, user)
    prior = await db.build_item_submissions.find_one(
        {"org_id": org, "client_ref": ref}, {"_id": 0})
    if prior:
        fresh = await db.build_items.find_one({"id": prior["item_id"]}, {"_id": 0})
        logger.info("submit idempoten: client_ref %s sudah diterima", ref)
        return {"item": fresh, "warning": None, "replay": True}
    if not await _claim_ref(org, ref):
        fresh = await db.build_items.find_one({"id": item["id"]}, {"_id": 0})
        logger.info("submit idempoten: client_ref %s sedang diproses pengirim lain", ref)
        return {"item": fresh, "warning": None, "replay": True}
    try:
        return await _submit_item(org, item, sched, payload, user, ref=ref)
    except Exception:
        # Ditolak (mis. checklist belum lengkap) → lepas kunci supaya mandor bisa
        # memperbaiki lalu mengirim ulang dengan penanda yang sama.
        await db.build_submit_claims.delete_one({"org_id": org, "client_ref": ref})
        raise


async def _submit_item(org: str, item: dict, sched: dict, payload, user: dict,
                       ref: str = None) -> dict:
    """Ajukan hasil kerja + bukti. Semua penjaga mutu diperiksa di DATA, bukan di UI saja."""
    actor = user.get("email")
    if item.get("status") in ("done", "submitted"):
        raise ValueError(_blocked_message(item))
    if item.get("status") == "blocked" and not item.get("override"):
        raise ValueError(_blocked_message(item))
    # Fase 32: kebijakan bukti kerja (panjang uraian + kewajiban lokasi) diatur admin,
    # jadi aturannya sama lewat jalur mana pun (Papan Mandor, sheet jadwal, atau API).
    policy = await bpol.get_policy(org)
    bpol.check_note(policy, payload.note)
    geo = bpol.check_geo(policy, getattr(payload, "geo", None))
    photos = list(payload.photo_file_ids or [])
    docs = list(payload.document_file_ids or [])
    need = int(item.get("min_photos") or 0)
    old_photos = [e for e in (item.get("evidence") or [])
                  if str(e.get("content_type") or "").startswith("image")]
    if item.get("status") == "rework":
        # Setelah dikembalikan, foto lama tetap dihitung tetapi WAJIB ada foto perbaikan baru
        # (kalau tidak, "perbaikan" bisa diklaim tanpa bukti apa pun).
        if not photos:
            raise ValueError("Pekerjaan ini dikembalikan supervisor — wajib melampirkan "
                             "minimal 1 FOTO PERBAIKAN yang baru sebelum diajukan ulang.")
        if len(old_photos) + len(photos) < need:
            raise ValueError(f"Total bukti foto masih {len(old_photos) + len(photos)} dari "
                             f"minimal {need} untuk pekerjaan ini.")
    elif len(photos) < need:
        raise ValueError(f"Bukti foto wajib minimal {need} foto untuk pekerjaan ini "
                         f"(baru {len(photos)}). Foto diambil lewat aplikasi agar otomatis "
                         "diberi watermark proyek + tanggal.")
    checklist, missing, failed = be.checklist_merge(
        item, [a.model_dump() for a in (payload.checklist or [])])
    if missing:
        raise ValueError("Checklist mutu belum lengkap: " + "; ".join(missing[:4])
                         + (" …" if len(missing) > 4 else ""))
    if failed:
        raise ValueError("Item mutu KRITIS belum lulus: " + "; ".join(failed[:3])
                         + ". Perbaiki dulu — tidak boleh dilewati.")
    evidence = await be.collect_evidence(org, photos + docs, item, actor)
    ts = now_iso()
    if geo:
        for e in evidence:
            e["geo"] = geo
    upd = {
        "status": "submitted", "note": payload.note.strip(), "checklist": checklist,
        "evidence": (item.get("evidence") or []) + evidence,
        "submitted_at": ts, "submitted_by": actor, "updated_at": ts,
        "started_at": item.get("started_at") or ts,
        "gate_reasons": [], "rejected_reason": None, "geo": geo,
    }
    await db.build_items.update_one({"id": item["id"]}, {
        "$set": upd,
        "$push": {"history": _hist("submit", actor, payload.note.strip()[:200],
                                   {"photos": len(photos), "documents": len(docs),
                                    "geo": geo})}})
    # Jejak audit pengajuan (koleksi terpisah agar bukti tidak ikut terhapus/berubah saat
    # item diajukan ulang): siapa, kapan, di mana, dengan berkas & hash apa.
    audit = {
        "id": new_id(), "org_id": org, "item_id": item["id"],
        "schedule_id": item["schedule_id"], "unit_id": item["unit_id"],
        "unit_code": item.get("unit_code"), "step_code": item.get("step_code"),
        "attempt": int(item.get("rework_count") or 0) + 1,
        "submitted_by": actor, "submitted_at": ts, "note": payload.note.strip(),
        "geo": geo, "checklist": checklist,
        "files": [{"file_id": e.get("file_id"), "sha256": e.get("sha256"),
                   "filename": e.get("filename"), "by_other_person": e.get("by_other_person")}
                  for e in evidence],
        "policy_snapshot": {k: policy.get(k) for k in
                            ("geo_required", "camera_only", "min_note_chars")},
    }
    # Penanda antrean hanya DITULIS bila ada. Indeks unik `client_ref` bersifat *sparse*:
    # sparse melewati dokumen yang FIELD-nya TIDAK ADA, tetapi `null` tetap dianggap nilai —
    # jadi menulis `client_ref: None` membuat pengajuan kedua dari layar biasa (tanpa antrean)
    # gagal 500 karena bentrok "null" dengan pengajuan sebelumnya.
    if ref:
        audit["client_ref"] = ref
    await db.build_item_submissions.insert_one(audit)
    await be._close_item_tasks(org, item, "pending", "Hasil diajukan, menunggu verifikasi.")
    verifier = item.get("verifier_hint")
    await wh.spawn(org, "TK-11", source_event=f"build.item_submitted:{item['id']}",
                   assignee_override=verifier, entity_type="unit", entity_id=item["unit_id"],
                   title=f"Verifikasi: {item['name']} — unit {item.get('unit_code')}",
                   description=(f"Diajukan {actor} dengan {len(photos)} foto bukti. "
                                "Periksa bukti & checklist, lalu setujui atau kembalikan."),
                   meta={"build_item_id": item["id"], "schedule_id": item["schedule_id"],
                         "unit_code": item.get("unit_code")})
    if verifier:
        await create_notification(
            user_email=verifier, title="Hasil pekerjaan menunggu verifikasi",
            body=f"{item['name']} — unit {item.get('unit_code')} · {len(photos)} foto bukti",
            type="task", related_entity_type="unit", related_entity_id=item["unit_id"],
            org_id=org)
    await add_activity(entity_type="unit", entity_id=item["unit_id"], type="system",
                       body=(f"Hasil '{item['name']}' diajukan dengan {len(photos)} foto bukti "
                             f"& checklist mutu lengkap."), actor=actor, org_id=org)
    await emit("build.item_submitted", "unit", item["unit_id"],
               {"label": item.get("unit_code"), "item_id": item["id"]}, org_id=org)
    fresh = await db.build_items.find_one({"id": item["id"]}, {"_id": 0})
    warn = [e["filename"] for e in evidence if e.get("by_other_person")]
    return {"item": fresh, "warning": (
        f"Catatan audit: {len(warn)} berkas bukti diunggah oleh orang lain — "
        "diteruskan ke verifikator." if warn else None)}


async def verify_item(org: str, item: dict, sched: dict, note: str, user: dict) -> dict:
    """Verifikasi supervisor. Pengaju TIDAK boleh memverifikasi pekerjaannya sendiri."""
    actor = user.get("email")
    if item.get("status") != "submitted":
        raise ValueError("Hanya pekerjaan yang sudah DIAJUKAN bisa diverifikasi.")
    if item.get("submitted_by") == actor:
        raise PermissionError("Pemisahan tugas: Anda yang mengajukan pekerjaan ini, "
                             "jadi tidak boleh memverifikasinya sendiri. Minta supervisor "
                             "lain atau direksi yang memeriksa.")
    ts = now_iso()
    await db.build_items.update_one({"id": item["id"]}, {
        "$set": {"status": "done", "verified_at": ts, "verified_by": actor,
                 "verify_note": note, "updated_at": ts},
        "$push": {"history": _hist("verify", actor, note)}})
    await be._close_item_tasks(org, item, "approved", note or "Diverifikasi supervisor.")
    fresh = await db.build_items.find_one({"id": item["id"]}, {"_id": 0})
    await be.refresh_gates(org, item["schedule_id"])
    sched2 = await be.recompute_schedule(org, item["schedule_id"])
    if item.get("submitted_by"):
        await create_notification(
            user_email=item["submitted_by"], title="Pekerjaan Anda disetujui",
            body=f"{item['name']} — unit {item.get('unit_code')} diverifikasi {actor}",
            type="task", related_entity_type="unit", related_entity_id=item["unit_id"],
            org_id=org)
    await add_activity(entity_type="unit", entity_id=item["unit_id"], type="system",
                       body=(f"'{item['name']}' DIVERIFIKASI {actor}. Progres unit "
                             f"{sched2.get('progress')}% (rencana {sched2.get('planned_progress')}%)."),
                       actor=actor, org_id=org)
    await emit("build.item_verified", "unit", item["unit_id"],
               {"label": item.get("unit_code"), "item_id": item["id"]}, org_id=org)
    if item.get("handover_gate"):
        await db.units.update_one({"id": item["unit_id"], "org_id": org},
                                 {"$set": {"construction_status": "done",
                                           "ready_handover": True, "updated_at": ts}})
        await emit("build.unit_ready_handover", "unit", item["unit_id"],
                   {"label": item.get("unit_code")}, org_id=org)
    if sched2.get("status") == "done":
        for email in await _owners(org):
            await create_notification(
                user_email=email, title=f"Unit {item.get('unit_code')} selesai dibangun",
                body=(f"Seluruh {sched2.get('items_total')} item pekerjaan terverifikasi. "
                      f"Target {sched2.get('target_finish_date')}."),
                type="info", related_entity_type="unit", related_entity_id=item["unit_id"],
                org_id=org)
    return {"item": fresh, "schedule": sched2}


async def reject_item(org: str, item: dict, reason: str, user: dict) -> dict:
    actor = user.get("email")
    if item.get("status") != "submitted":
        raise ValueError("Hanya pekerjaan yang sudah DIAJUKAN bisa dikembalikan.")
    ts = now_iso()
    await db.build_items.update_one({"id": item["id"]}, {
        "$set": {"status": "rework", "rejected_reason": reason, "verified_at": None,
                 "verified_by": None, "updated_at": ts,
                 "rework_count": int(item.get("rework_count") or 0) + 1},
        "$push": {"history": _hist("reject", actor, reason)}})
    await be._close_item_tasks(org, item, "rejected", reason)
    rows = await wh.spawn(org, "TK-12", source_event=f"build.item_rework:{item['id']}:"
                                                    f"{int(item.get('rework_count') or 0) + 1}",
                          assignee_override=item.get("assigned_to"), entity_type="unit",
                          entity_id=item["unit_id"],
                          title=f"Perbaiki: {item['name']} — unit {item.get('unit_code')}",
                          description=(f"Dikembalikan {actor}: {reason}\n\n"
                                       + bi.task_description(item)),
                          link=bi.item_link(item),
                          meta={"build_item_id": item["id"],
                                "schedule_id": item["schedule_id"],
                                "unit_code": item.get("unit_code"),
                                "step_code": item.get("step_code")})
    if rows:
        await db.build_items.update_one({"id": item["id"]},
                                       {"$set": {"task_id": rows[0]["id"]}})
    if item.get("assigned_to"):
        await create_notification(
            user_email=item["assigned_to"], title="Pekerjaan dikembalikan (perlu perbaikan)",
            body=f"{item['name']} — unit {item.get('unit_code')}: {reason[:120]}",
            type="task", related_entity_type="unit", related_entity_id=item["unit_id"],
            org_id=org)
    await add_activity(entity_type="unit", entity_id=item["unit_id"], type="system",
                       body=f"'{item['name']}' DIKEMBALIKAN {actor}: {reason}",
                       actor=actor, org_id=org)
    await emit("build.item_rework", "unit", item["unit_id"],
               {"label": item.get("unit_code"), "item_id": item["id"]}, org_id=org)
    await be.recompute_schedule(org, item["schedule_id"])
    return await db.build_items.find_one({"id": item["id"]}, {"_id": 0})


async def override_gate(org: str, item: dict, reason_code: str, note: str, user: dict) -> dict:
    """Menerobos gerbang: tetap DICATAT, dihitung, dan dilaporkan ke direksi."""
    actor = user.get("email")
    if item.get("status") != "blocked":
        raise ValueError("Gerbang pekerjaan ini tidak sedang terkunci — override tidak perlu.")
    bypassed = item.get("gate_reasons") or []
    ts = now_iso()
    override = {"by": actor, "at": ts, "reason_code": reason_code, "note": note,
                "bypassed": bypassed}
    await db.build_items.update_one({"id": item["id"]}, {
        "$set": {"status": "ready", "override": override, "gate_reasons": [], "updated_at": ts},
        "$push": {"history": _hist("override", actor, note, {"reason_code": reason_code})}})
    await db.build_schedules.update_one({"id": item["schedule_id"]},
                                      {"$inc": {"overrides": 1},
                                       "$set": {"updated_at": ts}})
    detail = "; ".join(r.get("detail") or "" for r in bypassed) or "-"
    for email in await _owners(org):
        await create_notification(
            user_email=email, title=f"Gerbang mutu diterobos — unit {item.get('unit_code')}",
            body=f"{item['name']} oleh {actor}. Alasan: {note}. Yang dilewati: {detail[:160]}",
            type="alert", related_entity_type="unit", related_entity_id=item["unit_id"],
            org_id=org)
    await add_activity(entity_type="unit", entity_id=item["unit_id"], type="system",
                       body=(f"GERBANG DITEROBOS pada '{item['name']}' oleh {actor} "
                             f"({reason_code}): {note}. Yang dilewati: {detail}"),
                       actor=actor, org_id=org)
    await emit("build.gate_overridden", "unit", item["unit_id"],
               {"label": item.get("unit_code"), "item_id": item["id"]}, org_id=org)
    fresh = await db.build_items.find_one({"id": item["id"]}, {"_id": 0})
    await _spawn_if_ready(org, fresh)
    return fresh


async def _spawn_if_ready(org: str, item: dict):
    sched = await db.build_schedules.find_one({"id": item["schedule_id"]}, {"_id": 0})
    await be._spawn_work_task(org, item, sched)


async def set_delay_cause(org: str, item: dict, cause: str, note: str, user: dict) -> dict:
    """Penyebab telat memakai kode SSOT supaya bisa dianalisis, bukan teks bebas."""
    if item.get("status") == "done":
        raise ValueError("Pekerjaan sudah selesai — penyebab keterlambatan tidak relevan.")
    ts = now_iso()
    await db.build_items.update_one({"id": item["id"]}, {
        "$set": {"delay_cause": cause, "delay_note": note, "updated_at": ts},
        "$push": {"history": _hist("delay_cause", user.get("email"), note,
                                   {"cause": cause})}})
    await add_activity(entity_type="unit", entity_id=item["unit_id"], type="system",
                       body=(f"Penyebab keterlambatan '{item['name']}': "
                             f"{DELAY_CAUSE_LABEL.get(cause, cause)}"
                             + (f" — {note}" if note else "")),
                       actor=user.get("email"), org_id=org)
    return await db.build_items.find_one({"id": item["id"]}, {"_id": 0})


async def hold_schedule(org: str, sched: dict, cause: str, note: str, user: dict) -> dict:
    ts = now_iso()
    await db.build_schedules.update_one({"id": sched["id"]}, {"$set": {
        "status": "on_hold", "hold_cause": cause, "hold_note": note,
        "held_by": user.get("email"), "held_at": ts, "updated_at": ts}})
    await be.refresh_gates(org, sched["id"])
    await add_activity(entity_type="unit", entity_id=sched["unit_id"], type="system",
                       body=(f"Jadwal unit {sched.get('unit_code')} DIHENTIKAN sementara "
                             f"({DELAY_CAUSE_LABEL.get(cause, cause)}): {note}"),
                       actor=user.get("email"), org_id=org)
    return await db.build_schedules.find_one({"id": sched["id"]}, {"_id": 0})


async def resume_schedule(org: str, sched: dict, user: dict) -> dict:
    ts = now_iso()
    await db.build_schedules.update_one({"id": sched["id"]}, {"$set": {
        "status": "in_progress", "hold_cause": None, "hold_note": None,
        "resumed_by": user.get("email"), "resumed_at": ts, "updated_at": ts}})
    await be.refresh_gates(org, sched["id"])
    out = await be.recompute_schedule(org, sched["id"])
    await add_activity(entity_type="unit", entity_id=sched["unit_id"], type="system",
                       body=f"Jadwal unit {sched.get('unit_code')} DILANJUTKAN.",
                       actor=user.get("email"), org_id=org)
    return out
