"""Webhooks (SIMULATION-first) for omnichannel lead capture.

Public endpoints (no auth) that accept sample payloads from multiple providers:
Meta Lead Ads, WhatsApp, Google Lead Form, TikTok Lead, a generic Web form, dan — sejak
Fase 43 — MITRA (token per mitra). Ads attribution (campaign/campaign_id/adset/ad/creative/
form + utm/fbclid/gclid) dibawa sampai ke lead + lead_capture_event. Saat kredensial nyata
tersedia, cukup set `channel_accounts.mode='live'` — kontrak capture-nya tidak berubah.

Fase 30c — TIDAK ADA LEAD YANG HILANG LAGI. Dulu payload cacat (JSON rusak, nomor HP
kosong, field salah nama) dibalas 422 dan menguap: uang iklan terbayar tetapi lead tidak
pernah masuk CRM dan tidak ada jejaknya. Sekarang setiap kegagalan disimpan di antrean
`lead_capture_failures`, memicu event `capture.failed` (tugas DM-02 + notifikasi
supervisor), dan bisa diperbaiki lalu diulang dari halaman Automasi & Channel.

Fase 43 — webhook MITRA (`docs/v2/25_PARTNER_SPEC.md` §4). Dua hal yang membuatnya berbeda
dari kanal lain dan karena itu ditulis eksplisit:
  1. Nomor telepon lead UNIK per organisasi (index `uq_leads_phone`). Jadi mitra kedua yang
     mengklaim nomor yang sudah ada TIDAK boleh membuat lead kedua — klaimnya dicatat lewat
     mesin atribusi mitra (`partner_engine.attribute`) yang memutuskan pemenangnya sesuai
     model (first/last touch) dan menyimpan SENGKETA bila perlu. Dulu tidak ada pintu masuk
     resmi untuk lead mitra sama sekali; atribusi bergantung pada ingatan orang.
  2. Mitra yang kontraknya habis / ditangguhkan DITOLAK dengan alasan — bukan diterima
     diam-diam lalu memunculkan tagihan fee yang tidak boleh ada.
"""
import asyncio
import json

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import ValidationError

import capture_failures as cf
import partner_engine as pengine
import wa_gateway as gw
import wa_inbound as wi
from core_utils import new_id, now_iso, today_iso_date
from db import db, ORG_ID
from engine import process_lead_capture
from models import WebhookLead

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


def _failed(provider: str, failure: dict, reason: str) -> JSONResponse:
    """202: kami MENERIMA panggilan provider, tetapi leadnya tertahan (bukan hilang)."""
    return JSONResponse(status_code=202, content={"data": {
        "captured": False, "lead_id": None, "duplicate": False,
        "failure_id": failure["id"], "reason": reason,
        "queued": "Antrean lead gagal masuk (Automasi & Channel → Gagal Masuk)",
        "mode": "simulation", "provider": provider}})


async def _parse(provider: str, request: Request, defaults: dict = None):
    """-> (payload bersih, JSONResponse kegagalan). Satu pintu validasi semua provider."""
    raw, parse_err = await cf.read_json(request)
    if parse_err:
        failure = await cf.record(provider, raw or {}, parse_err, kind=cf.KIND_DATA,
                                  org_id=ORG_ID)
        return None, _failed(provider, failure, parse_err)
    try:
        data = WebhookLead(**raw).model_dump()
    except ValidationError as e:
        first = (e.errors() or [{}])[0]
        loc = ".".join(str(x) for x in (first.get("loc") or []))
        reason = f"Payload tidak sesuai kontrak pada '{loc or 'payload'}': {first.get('msg')}"
        failure = await cf.record(provider, raw, reason, kind=cf.KIND_DATA, org_id=ORG_ID)
        return None, _failed(provider, failure, reason)
    data.setdefault("source", provider)
    for key, value in (defaults or {}).items():
        data[key] = value
    clean, err = cf.validate(data)
    if err:
        failure = await cf.record(provider, data, err, kind=cf.KIND_DATA, org_id=ORG_ID)
        return None, _failed(provider, failure, err)
    return clean, None


async def _capture(provider: str, request: Request, defaults: dict = None):
    """Satu pintu untuk semua provider: parse → validasi → proses → (atau antrekan)."""
    clean, failed = await _parse(provider, request, defaults)
    if failed:
        return failed
    try:
        lead_id, duplicate = await process_lead_capture(provider, clean, org_id=ORG_ID)
    except Exception as e:  # noqa: BLE001 - gangguan sementara: layak dicoba ulang otomatis
        reason = f"Gangguan saat memproses lead: {e}"
        failure = await cf.record(provider, clean, reason, kind=cf.KIND_TRANSIENT,
                                  org_id=ORG_ID)
        return _failed(provider, failure, reason)
    return {"data": {"lead_id": lead_id, "duplicate": duplicate, "captured": True,
                     "mode": "simulation", "provider": provider}}


@router.post("/meta-lead")
async def meta_lead(request: Request):
    return await _capture("meta_ads", request)


@router.get("/wa")
async def wa_verify(request: Request):
    """Handshake Meta: hub.mode=subscribe & hub.verify_token cocok → balas hub.challenge."""
    qp = request.query_params
    cfg = await gw.get_config(ORG_ID)
    expected = cfg["creds"].get("verify_token")
    if qp.get("hub.mode") == "subscribe" and expected and qp.get("hub.verify_token") == expected:
        # uji handshake dari SIPRO sendiri (wa_setup) tidak dihitung sebagai webhook Meta yang sungguhan
        if not request.headers.get("X-Sipro-Selfcheck"):
            await gw.note_webhook(ORG_ID, signature_ok=True, kind="verify")
        return PlainTextResponse(qp.get("hub.challenge") or "")
    await gw.note_webhook(ORG_ID, signature_ok=False, kind="verify_failed")
    return PlainTextResponse("verify token tidak cocok", status_code=403)


@router.post("/wa")
async def wa_inbound(request: Request):
    """Dua kontrak: payload Meta asli (object=whatsapp_business_account) atau `WebhookLead` lama."""
    body = await request.body()
    try:
        raw = json.loads(body or b"{}")
    except ValueError:
        raw = None
    if not wi.is_meta_payload(raw):
        return await _capture("whatsapp", request)
    cfg = await gw.get_config(ORG_ID)
    sig_ok = wi.verify_signature(cfg["creds"].get("app_secret"), body,
                                 request.headers.get("X-Hub-Signature-256"))
    if sig_ok is False:
        # App secret terpasang tetapi tanda tangan tidak cocok → tolak (siapa pun bisa menyuntik lead palsu).
        await gw.note_webhook(ORG_ID, signature_ok=False, kind="messages")
        failure = await cf.record("whatsapp", raw, "Tanda tangan X-Hub-Signature-256 tidak sah",
                                  kind=cf.KIND_DATA, org_id=ORG_ID)
        return JSONResponse(status_code=403, content={"detail": "signature tidak sah",
                                                      "failure_id": failure["id"]})
    await gw.note_webhook(ORG_ID, signature_ok=sig_ok, kind="messages")
    ev = {"id": new_id(), "waba_id": (raw.get("entry") or [{}])[0].get("id"), "org_id": ORG_ID, "received_at": now_iso(), "status": "processing",
          "payload": raw, "signature_ok": sig_ok}
    ev_id = (await db.wa_webhook_events.insert_one(dict(ev))).inserted_id

    async def _run():
        try:
            summary = await wi.process_meta_payload(raw, ORG_ID)
            await db.wa_webhook_events.update_one({"_id": ev_id}, {"$set": {
                "status": "done", "summary": {k: v for k, v in summary.items() if k != "results"}}})
            return summary
        except Exception as e:  # noqa: BLE001 — payload TIDAK dibuang: masuk antrean gagal
            failure = await cf.record("whatsapp", raw, f"Gangguan memproses webhook Meta: {e}",
                                      kind=cf.KIND_TRANSIENT, org_id=ORG_ID)
            await db.wa_webhook_events.update_one({"_id": ev_id}, {"$set": {"status": "failed", "failure_id": failure["id"]}})
            return {"queued": True, "failure_id": failure["id"]}

    # Meta menunggu < 5 detik: proses berjalan sebagai task; bila belum selesai dalam 4 detik, balas
    # 200 lebih dulu dan biarkan task melanjutkan (idempotensi dijaga indeks unik wamid).
    task = asyncio.create_task(_run())
    done, _pending = await asyncio.wait({task}, timeout=4.0)
    if not done:
        return {"data": {"accepted": True, "deferred": True}, "mode": cfg["effective_mode"], "signature_ok": sig_ok}
    summary = task.result()
    return {"data": {k: v for k, v in summary.items() if k != "results"},
            "mode": cfg["effective_mode"], "signature_ok": sig_ok}


@router.post("/google-lead")
async def google_lead(request: Request):
    return await _capture("google_lead", request)


@router.post("/tiktok-lead")
async def tiktok_lead(request: Request):
    return await _capture("tiktok_lead", request)


@router.post("/web")
async def web_form(request: Request):
    return await _capture("website", request)


@router.post("/partner/{partner_id}")
async def partner_lead(partner_id: str, request: Request, token: str = None):
    """Lead dari sistem MITRA. Wajib token mitra (header `X-Partner-Token` atau `?token=`)."""
    provided = token or request.headers.get("X-Partner-Token") or ""
    partner = await db.agents.find_one({"id": partner_id, "org_id": ORG_ID}, {"_id": 0})
    # Jawaban SAMA untuk mitra tak dikenal dan token salah: siapa pun yang menebak-nebak
    # tidak boleh bisa memetakan daftar mitra kami dari balasan endpoint publik.
    if not partner or not partner.get("webhook_token") \
            or provided != partner.get("webhook_token"):
        return JSONResponse(status_code=401, content={"detail": (
            "Token mitra tidak sah. Minta ulang token di halaman profil mitra "
            "(Mitra & Fee → profil mitra → Webhook Lead).")})
    ok, why = pengine.contract_active(partner, today_iso_date())
    if partner.get("status") != "active" or not ok:
        return JSONResponse(status_code=403, content={"detail": (
            f"Mitra {partner.get('name')} tidak sedang aktif ({partner.get('status')}"
            f"{'; ' + why if why else ''}) — lead baru dari mitra ini ditolak supaya tidak "
            "melahirkan hak fee yang tidak boleh ada.")})
    clean, failed = await _parse("partner", request,
                                 {"source": "partner", "partner_id": partner_id})
    if failed:
        return failed
    existing = await db.leads.find_one({"org_id": ORG_ID, "phone": clean["phone"]},
                                      {"_id": 0, "id": 1, "partner_id": 1, "name": 1})
    verdict = await pengine.attribute(partner_id=partner_id, phone=clean["phone"],
                                      org_id=ORG_ID,
                                      lead_id=(existing or {}).get("id"))
    if existing:
        # Nomor sudah ada: JANGAN membuat lead kedua (nomor unik per organisasi). Klaim
        # mitra tetap dicatat + pemenangnya ditetapkan mesin atribusi.
        ts = now_iso()
        await db.leads.update_one({"id": existing["id"]}, {"$set": {
            "partner_id": verdict["partner_id"],
            "partner_attribution_model": verdict["model"],
            "partner_attributed_at": ts, "updated_at": ts,
            "last_touch": {"at": ts, "provider": "partner", "source": "partner",
                           "campaign": clean.get("campaign"), "partner_id": partner_id},
        }})
        for pid in {partner_id, verdict.get("partner_id")}:
            if pid:
                await pengine.refresh_stats(pid, org_id=ORG_ID)
        return {"data": {
            "lead_id": existing["id"], "duplicate": True, "captured": False,
            "mode": "simulation", "provider": "partner",
            "attributed_to": verdict["partner_id"], "attribution_model": verdict["model"],
            "conflict_id": (verdict.get("conflict") or {}).get("id"),
            "note": ("Nomor ini sudah ada di CRM. Klaim mitra dicatat dan atribusinya "
                     f"diputuskan dengan model {verdict['model']} — tidak ada lead kembar "
                     "yang dibuat.")}}
    clean["partner_id"] = verdict["partner_id"]
    try:
        lead_id, duplicate = await process_lead_capture("partner", clean, org_id=ORG_ID)
    except Exception as e:  # noqa: BLE001
        reason = f"Gangguan saat memproses lead mitra: {e}"
        failure = await cf.record("partner", clean, reason, kind=cf.KIND_TRANSIENT,
                                  org_id=ORG_ID)
        return _failed("partner", failure, reason)
    await pengine.refresh_stats(verdict["partner_id"], org_id=ORG_ID)
    return {"data": {"lead_id": lead_id, "duplicate": duplicate, "captured": True,
                     "mode": "simulation", "provider": "partner",
                     "attributed_to": verdict["partner_id"],
                     "attribution_model": verdict["model"],
                     "conflict_id": (verdict.get("conflict") or {}).get("id")}}
