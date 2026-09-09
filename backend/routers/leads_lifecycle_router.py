"""Lead lifecycle & WhatsApp DI DALAM record lead (Fase 29b).

Sebelum fase ini: percakapan WA hidup di halaman /inbox yang terpisah, dan mengirim pesan
tidak berpengaruh apa pun pada lifecycle (tidak mencatat kontak pertama, tidak menghitung
waktu respons, tidak muncul di timeline lead). Sales harus pindah layar dan menebak.

Sekarang: satu record lead memuat checklist syarat tahap, langkah berikutnya (NBA),
thread WA + pengiriman template, penilaian kualitatif respons lead, dan riwayat tahap.
Mode pengiriman WA masih SIMULASI (tanpa kredensial Meta) dan ditandai jujur `mode`.
"""
from fastapi import APIRouter, Depends, HTTPException

import lead_lifecycle as lc
import reference as ref
import slik as slik
import workhub as wh
from core_utils import due_in, new_id, now_iso, serialize_doc
from db import db, ORG_ID
from engine import add_activity, dispatch_pending, emit, render_wa_body, wa_template_vars
from models_p29 import LeadDisposition, LeadStageOverride, LeadWaManual
from models_p30 import SlikPrescreen
from rbac import require_permission, is_scoped_sales
from models import MessageCreate

router = APIRouter(prefix="/leads", tags=["sales"])

DISPOSITIONS = set(ref.values("lead_disposition"))
CLOSE_REASONS = set(ref.values("lead_close_reason"))


async def _lead(lead_id: str, user: dict) -> dict:
    lead = await db.leads.find_one({"id": lead_id, "org_id": user.get("org_id", ORG_ID)},
                                   {"_id": 0})
    if not lead:
        raise HTTPException(status_code=404, detail="Lead tidak ditemukan")
    if is_scoped_sales(user) and lead.get("assigned_to") != user.get("email"):
        raise HTTPException(status_code=403, detail="Akses ditolak: bukan lead Anda")
    return lead


def _window_open(conv: dict) -> bool:
    exp = (conv or {}).get("window_expires_at")
    return bool(exp) and str(exp) > now_iso()


# ----------------------------- lifecycle -----------------------------
@router.get("/{lead_id}/lifecycle")
async def lifecycle(lead_id: str, user: dict = Depends(require_permission("leads", "view"))):
    """Semua yang dibutuhkan UI untuk MEMANDU: tahap, syarat bukti, NBA, riwayat."""
    lead = await _lead(lead_id, user)
    reqs = await lc.requirements(lead)
    stage = lead.get("stage")
    idx = lc.ORDER.index(stage) if stage in lc.ORDER else None
    nxt = lc.ORDER[idx + 1] if idx is not None and idx + 1 < len(lc.ORDER) else None
    ok, blocked, _ = (True, None, {})
    if nxt:
        ok, blocked, _ = await lc.gate(lead, nxt)
    conv = await db.conversations.find_one({"org_id": lead["org_id"], "lead_id": lead_id},
                                          {"_id": 0}, sort=[("last_message_at", -1)])
    return {"data": {
        "stage": stage, "order": lc.ORDER,
        "manual_targets": lc.MANUAL_FLOW.get(stage, []),
        "next_stage": nxt, "can_advance": bool(nxt) and ok, "blocked_reason": blocked,
        "requirements": reqs, "next_actions": lc.next_actions(lead, reqs),
        "history": lead.get("stage_history") or [],
        "disposition": lead.get("disposition"),
        "disposition_note": lead.get("disposition_note"),
        "first_contact_at": lead.get("first_contact_at"),
        "response_time_minutes": lead.get("response_time_minutes"),
        "close_reason": lead.get("close_reason"),
        "slik": slik.summary(lead),
        "slik_history": slik.history(lead),
        "slik_options": slik.options(),
        "slik_mode": slik.MODE,
        "slik_followup_task": await slik.followup_task(lead["org_id"], lead_id),
        "conversation_id": (conv or {}).get("id"),
        "window_open": _window_open(conv),
        "can_override": wh.is_supervisor(user),
        "reasons": [{"value": o["value"], "label": o["label"]}
                    for o in ref.GROUPS["lead_close_reason"]["options"]],
    }}


@router.post("/{lead_id}/stage/override")
async def override_stage(lead_id: str, payload: LeadStageOverride,
                         user: dict = Depends(require_permission("leads", "update"))):
    """Override tahap oleh SUPERVISOR — wajib beralasan, tercatat di riwayat & audit."""
    lead = await _lead(lead_id, user)
    if not wh.is_supervisor(user):
        raise HTTPException(status_code=403, detail=(
            "Hanya supervisor divisi (atau Direksi) yang boleh memaksa perubahan tahap."))
    if payload.stage not in ref.values("lead_stage"):
        raise HTTPException(status_code=400, detail="Tahap tidak valid")
    if payload.stage == lead.get("stage"):
        raise HTTPException(status_code=400, detail="Lead sudah berada pada tahap tersebut.")
    fresh = await lc.record(lead, payload.stage, actor=user.get("email"),
                            reason=payload.reason, override=True, source="override")
    await dispatch_pending()
    return {"data": serialize_doc(fresh)}


@router.post("/{lead_id}/disposition")
async def disposition(lead_id: str, payload: LeadDisposition,
                      user: dict = Depends(require_permission("leads", "update"))):
    """Nilai respons lead (kualitatif) — memengaruhi skor & langkah berikutnya."""
    lead = await _lead(lead_id, user)
    if payload.disposition not in DISPOSITIONS:
        raise HTTPException(status_code=400, detail=(
            f"Nilai respons tidak dikenal. Pilihan: {', '.join(sorted(DISPOSITIONS))}"))
    fresh = await lc.set_disposition(lead, disposition=payload.disposition,
                                     actor=user.get("email"), note=payload.note,
                                     intent_tags=payload.intent_tags)
    reqs = await lc.requirements(fresh)
    return {"data": serialize_doc(fresh), "next_actions": lc.next_actions(fresh, reqs)}


# ----------------------------- WhatsApp di record lead -----------------------------
@router.get("/{lead_id}/wa")
async def lead_wa(lead_id: str, user: dict = Depends(require_permission("leads", "view"))):
    """Thread WA lead + status window 24 jam + template yang tersedia."""
    lead = await _lead(lead_id, user)
    org = lead["org_id"]
    conv = await db.conversations.find_one({"org_id": org, "lead_id": lead_id}, {"_id": 0},
                                          sort=[("last_message_at", -1)])
    msgs = []
    if conv:
        msgs = await db.messages.find({"conversation_id": conv["id"]}, {"_id": 0}).sort(
            "created_at", 1).to_list(200)
    tmpl = await db.wa_templates.find({"org_id": org, "status": "approved"},
                                      {"_id": 0, "id": 1, "code": 1, "name": 1, "body": 1,
                                       "category": 1}).to_list(50)
    return {"data": {
        "conversation": serialize_doc(conv), "messages": serialize_doc(msgs),
        "window_open": _window_open(conv), "templates": serialize_doc(tmpl),
        "phone": lead.get("phone"), "mode": "simulation",
        "first_contact_at": lead.get("first_contact_at"),
    }}


@router.post("/{lead_id}/wa")
async def send_lead_wa(lead_id: str, payload: MessageCreate,
                       user: dict = Depends(require_permission("leads", "update"))):
    """Kirim WA dari record lead (SIMULASI) + efek lifecycle yang sesungguhnya.

    Efek: pesan tercatat di percakapan, aktivitas masuk timeline LEAD, kontak pertama
    tercatat (menghitung waktu respons sekali), tahap `acquisition → nurturing`, dan
    tugas "hubungi lead" ditutup dengan bukti.
    """
    lead = await _lead(lead_id, user)
    org = lead["org_id"]
    ts = now_iso()
    conv = await db.conversations.find_one({"org_id": org, "lead_id": lead_id}, {"_id": 0},
                                          sort=[("last_message_at", -1)])
    if not conv:
        conv = {
            "id": new_id(), "org_id": org, "channel": "whatsapp",
            "contact_phone": lead.get("phone"), "contact_name": lead.get("name"),
            "lead_id": lead_id, "owner": lead.get("assigned_to") or user.get("email"),
            "status": "active", "mode": "simulation", "unread": 0,
            "last_message_at": None, "last_direction": None, "window_expires_at": None,
            "created_at": ts, "updated_at": ts,
        }
        await db.conversations.insert_one(dict(conv))
    template = None
    if payload.template_id or payload.template_code:
        q = {"org_id": org}
        q.update({"id": payload.template_id} if payload.template_id
                 else {"code": payload.template_code})
        template = await db.wa_templates.find_one(q, {"_id": 0})
        if not template:
            raise HTTPException(status_code=404, detail="Template WA tidak ditemukan")
    if template is None and not _window_open(conv):
        raise HTTPException(status_code=400, detail=(
            "Sesi 24 jam WhatsApp tertutup (pelanggan belum membalas). Gunakan template "
            "pra-approved untuk membuka percakapan."))
    body = template["body"] if template else (payload.body or "").strip()
    if not body:
        raise HTTPException(status_code=400, detail="Isi pesan tidak boleh kosong.")
    body = render_wa_body(body, await wa_template_vars(lead))
    msg = {
        "id": new_id(), "org_id": org, "conversation_id": conv["id"], "direction": "out",
        "body": body, "sender": user.get("email"), "is_template": bool(template),
        "template_id": (template or {}).get("id"), "template_code": (template or {}).get("code"),
        "mode": "simulation", "created_at": ts,
    }
    await db.messages.insert_one(dict(msg))
    await db.conversations.update_one({"id": conv["id"]}, {"$set": {
        "last_message_at": ts, "last_direction": "out", "status": "active",
        "unanswered_task_at": None, "updated_at": ts}})
    await add_activity(entity_type="lead", entity_id=lead_id, type="system",
                       body=f"WhatsApp terkirim (SIMULASI): {body[:120]}",
                       actor=user.get("email"), org_id=org,
                       meta={"conversation_id": conv["id"], "template": msg["template_code"]})
    fresh = await lc.mark_first_contact(lead, actor=user.get("email"), channel="whatsapp",
                                        note=f"WA: {body[:80]}")
    await emit("message.sent", "conversation", conv["id"], {"lead_id": lead_id}, org_id=org)
    await dispatch_pending()
    reqs = await lc.requirements(fresh)
    return {"data": {"message": serialize_doc(msg), "lead": serialize_doc(fresh),
                     "conversation_id": conv["id"], "mode": "simulation",
                     "next_actions": lc.next_actions(fresh, reqs)},
            "message_text": "Pesan WhatsApp terkirim (mode simulasi) & kontak pertama tercatat."}


@router.post("/{lead_id}/wa/manual")
async def log_manual_wa(lead_id: str, payload: LeadWaManual,
                        user: dict = Depends(require_permission("leads", "update"))):
    """Catat chat WA yang dilakukan DI LUAR sistem (HP pribadi) — WAJIB bukti foto.

    Jalur bypass selama integrasi WhatsApp resmi belum terpasang: staf tetap chat lewat
    WA pribadi, lalu mencatatnya di sini dengan tangkapan layar percakapan sebagai bukti.
    Efek lifecycle SAMA dengan kirim WA dari sistem: kontak pertama tercatat (sekali),
    tahap acquisition → nurturing naik, dan tugas "hubungi lead" tertutup berbukti.
    """
    lead = await _lead(lead_id, user)
    org = lead["org_id"]
    ids = payload.evidence_file_ids
    files = await db.files.find({"id": {"$in": ids}, "org_id": org, "is_deleted": False},
                                {"_id": 0, "id": 1, "content_type": 1}).to_list(len(ids))
    if len(files) != len(set(ids)):
        raise HTTPException(status_code=404, detail=(
            "Sebagian file bukti tidak ditemukan. Unggah ulang tangkapan layarnya."))
    if any(not str(f.get("content_type") or "").startswith("image/") for f in files):
        raise HTTPException(status_code=400, detail=(
            "Bukti wajib berupa FOTO/tangkapan layar percakapan (bukan PDF/berkas lain)."))
    task = None
    if payload.task_id:
        task = await db.tasks.find_one({"id": payload.task_id, "org_id": org,
                                        "related_entity_type": "lead",
                                        "related_entity_id": lead_id}, {"_id": 0})
        if not task:
            raise HTTPException(status_code=404, detail=(
                "Tugas tidak ditemukan atau tidak terkait dengan lead ini."))
        if task.get("status") in ("done", "cancelled"):
            raise HTTPException(status_code=400, detail="Tugas ini sudah ditutup.")
    ts = now_iso()
    conv = await db.conversations.find_one({"org_id": org, "lead_id": lead_id}, {"_id": 0},
                                          sort=[("last_message_at", -1)])
    if not conv:
        conv = {
            "id": new_id(), "org_id": org, "channel": "whatsapp",
            "contact_phone": lead.get("phone"), "contact_name": lead.get("name"),
            "lead_id": lead_id, "owner": lead.get("assigned_to") or user.get("email"),
            "status": "active", "mode": "manual", "unread": 0,
            "last_message_at": None, "last_direction": None, "window_expires_at": None,
            "created_at": ts, "updated_at": ts,
        }
        await db.conversations.insert_one(dict(conv))
    note = payload.note.strip()
    msg = {
        "id": new_id(), "org_id": org, "conversation_id": conv["id"], "direction": "out",
        "body": note, "sender": user.get("email"), "is_template": False,
        "mode": "manual", "evidence_file_ids": ids, "created_at": ts,
    }
    await db.messages.insert_one(dict(msg))
    await db.conversations.update_one({"id": conv["id"]}, {"$set": {
        "last_message_at": ts, "last_direction": "out", "status": "active",
        "unanswered_task_at": None, "updated_at": ts}})
    await add_activity(entity_type="lead", entity_id=lead_id, type="system",
                       body=(f"WA manual (di luar sistem) dicatat dengan {len(ids)} bukti "
                             f"foto: {note[:120]}"),
                       actor=user.get("email"), org_id=org,
                       meta={"conversation_id": conv["id"], "evidence_file_ids": ids,
                             "mode": "manual"})
    fresh = await lc.mark_first_contact(lead, actor=user.get("email"),
                                        channel="whatsapp_manual",
                                        note=f"WA manual (bukti foto): {note[:80]}")
    closed_task = None
    if task:
        fresh_task = await db.tasks.find_one({"id": task["id"]}, {"_id": 0})
        if fresh_task.get("status") not in ("done", "cancelled"):
            proof = list(fresh_task.get("proof") or [])
            proof.append({"kind": "note", "at": ts,
                          "value": f"WA manual (di luar sistem): {note[:500]}"})
            proof.extend({"kind": "photo", "value": f, "at": ts} for f in ids)
            upd = {"status": "done", "review": "approved", "proof": proof,
                   "outcome": f"WA manual berbukti foto: {note[:200]}",
                   "completed_at": ts, "completed_by": user.get("email"),
                   "verified_by": "system", "verified_at": ts,
                   "verify_note": f"Bukti foto WA manual ({len(ids)} lampiran) tervalidasi.",
                   "updated_at": ts}
            await db.tasks.update_one({"id": task["id"]}, {"$set": upd})
            closed_task = {**fresh_task, **upd}
        else:
            closed_task = fresh_task
        await wh.log_task_activity(
            closed_task, f"Tugas ditutup lewat catatan WA manual berbukti ({len(ids)} foto).",
            user.get("email"))
    await emit("message.sent", "conversation", conv["id"],
               {"lead_id": lead_id, "mode": "manual"}, org_id=org)
    await dispatch_pending()
    reqs = await lc.requirements(fresh)
    return {"data": {"message": serialize_doc(msg), "lead": serialize_doc(fresh),
                     "conversation_id": conv["id"], "mode": "manual",
                     "task": serialize_doc(closed_task),
                     "next_actions": lc.next_actions(fresh, reqs)},
            "message_text": ("Chat WA manual tercatat dengan bukti foto — kontak pertama "
                             "terverifikasi tanpa integrasi WhatsApp.")}


@router.post("/{lead_id}/wa/inbound-demo")
async def inbound_demo(lead_id: str, payload: MessageCreate,
                       user: dict = Depends(require_permission("leads", "update"))):
    """Simulasikan balasan pelanggan (untuk uji alur otomasi tanpa kredensial Meta).

    Ditandai JUJUR sebagai simulasi: membuka window 24 jam, memicu automasi keyword,
    dan mencatat aktivitas pada lead.
    """
    lead = await _lead(lead_id, user)
    org = lead["org_id"]
    conv = await db.conversations.find_one({"org_id": org, "lead_id": lead_id}, {"_id": 0},
                                          sort=[("last_message_at", -1)])
    if not conv:
        raise HTTPException(status_code=400, detail=(
            "Belum ada percakapan. Kirim WA lebih dulu agar ada thread."))
    ts = now_iso()
    body = (payload.body or "").strip()
    if not body:
        raise HTTPException(status_code=400, detail="Isi pesan tidak boleh kosong.")
    await db.messages.insert_one({
        "id": new_id(), "org_id": org, "conversation_id": conv["id"], "direction": "in",
        "body": body, "sender": "contact", "mode": "simulation", "created_at": ts})
    await db.conversations.update_one({"id": conv["id"]}, {"$set": {
        "last_message_at": ts, "last_direction": "in", "status": "active",
        "window_expires_at": due_in(hours=24), "unread": 1, "updated_at": ts}})
    await add_activity(entity_type="lead", entity_id=lead_id, type="system",
                       body=f"Balasan pelanggan (SIMULASI): {body[:120]}",
                       actor="contact", org_id=org)
    await emit("message.received", "conversation", conv["id"], {"body": body}, org_id=org)
    await dispatch_pending()
    fresh = await db.leads.find_one({"id": lead_id}, {"_id": 0})
    return {"data": serialize_doc(fresh), "window_open": True, "mode": "simulation"}


@router.post("/{lead_id}/slik-prescreen")
async def slik_prescreen(lead_id: str, payload: SlikPrescreen,
                         user: dict = Depends(require_permission("leads", "update"))):
    """Pra-skrining BI/SLIK BERBUKTI sebagai GERBANG sebelum lead naik ke Booking.

    MODE SIMULASI (ditandai jujur): hasil iDeb didapat petugas lewat kanal resmi lalu
    dicatat di sini BERSAMA lampirannya. Hasil `clear`/`flagged` WAJIB berbukti; `rejected`
    wajib beralasan, menahan lead, melahirkan tugas tindak lanjut (SM-12), dan mengusulkan
    penutupan lead dengan alasan SSOT. Semua pemeriksaan tersimpan di riwayat.
    """
    lead = await _lead(lead_id, user)
    try:
        res = await slik.prescreen(lead, status=payload.status, note=payload.note,
                                   evidence_ids=payload.evidence_file_ids,
                                   actor=user.get("email"))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await dispatch_pending()          # event -> tugas Work Hub lahir sekarang, bukan nanti
    fresh = res["lead"]
    reqs = await lc.requirements(fresh)
    return {"data": serialize_doc(fresh), "slik": slik.summary(fresh),
            "history": slik.history(fresh), "mode": slik.MODE,
            "suggest_close": res["suggest_close"],
            "followup_task": serialize_doc(await slik.followup_task(lead["org_id"], lead_id)),
            "closed_followups": res["closed_followups"],
            "requirements": reqs.get("booking")}
