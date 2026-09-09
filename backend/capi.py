"""EPIC 1.7 + Fase 43 — Conversion API (CAPI) feedback loop, siap-live & jujur.

Saat lead/deal mencapai tonggak konversi, event-nya dikirim BALIK ke platform iklan
(Meta CAPI / Google Enhanced Conversions / TikTok Events API) supaya model optimasi mereka
belajar dari hasil nyata di hilir. Sumber non-iklan (walk-in, referral, manual) dilewati —
tidak ada loop yang perlu ditutup.

APA YANG DITAMBAHKAN FASE 43 (spec `docs/v2/30_MARKETING_INTEGRATION_SPEC.md` §6):

1. **`event_id` deduplikasi.** Platform membuang event kembar berdasarkan `event_id`. Tanpa
   ini, dispatcher yang mengulang event (retry) atau dua event bisnis yang terbit bersamaan
   (`deal.ajb` + `deal.sold`) akan membuat konversi dihitung DUA KALI — dan angka ROAS di
   layar ikut salah karena `conversion_events` juga sumber laporan atribusi. `event_id`
   dihitung deterministik dari (org, event, lead, deal), lalu dijaga index unik.
2. **`user_data` ter-hash SHA-256.** Nomor telepon dinormalkan E.164 lalu di-hash; email
   dihuruf-kecilkan lalu di-hash. Yang tersimpan di `conversion_events` hanya hash-nya, jadi
   dokumen ini boleh dibaca lebih banyak peran tanpa membocorkan data pribadi, DAN payload
   sudah berbentuk final yang diminta platform saat kredensial dinyalakan.
3. **`SubmitApplication`** saat SPR ditandatangani (sinyal lebih awal daripada booking).
4. **Status yang tidak berbohong.** Tanpa kredensial, event TIDAK dikirim ke mana pun, jadi
   statusnya `simulated` — bukan `sent`. Dulu semua baris berstatus "Terkirim" padahal tidak
   ada satu pun paket keluar; itu membuat layar audit tidak bisa dipercaya.
"""
import hashlib
import logging
import os
from datetime import datetime, timezone

import httpx

from core_utils import new_id, normalize_phone_e164, now_iso
from db import db, ORG_ID

logger = logging.getLogger("sipro.capi")

# lead.source -> ad platform that should receive the feedback event.
PLATFORM_BY_SOURCE = {
    "meta_ads": "meta",
    "whatsapp": "meta",        # WhatsApp click-to-chat ads also report to Meta.
    "google_lead": "google",
    "tiktok_lead": "tiktok",
    "tiktok_ads": "tiktok",
    "website": "web_pixel",
}

# platform -> env var whose presence flips transport to LIVE (else simulation).
LIVE_ENV_BY_PLATFORM = {
    "meta": "META_CAPI_TOKEN",
    "google": "GOOGLE_ADS_CONV_TOKEN",
    "tiktok": "TIKTOK_EVENTS_TOKEN",
    "web_pixel": "WEB_PIXEL_TOKEN",
}

PLATFORM_LABEL = {
    "meta": "Meta (Conversions API)",
    "google": "Google (Enhanced Conversions)",
    "tiktok": "TikTok (Events API)",
    "web_pixel": "Web Pixel",
}

from meta_api import GRAPH_BASE as GRAPH  # noqa: E402 — satu konstanta versi (Fase 94B)
TIMEOUT = 10.0


def platform_for_source(source):
    return PLATFORM_BY_SOURCE.get((source or "").lower())


def _live(platform: str) -> bool:
    env = LIVE_ENV_BY_PLATFORM.get(platform)
    return bool(env and os.environ.get(env))


def sha256_of(value: str) -> str:
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()


def hash_phone(phone: str) -> str:
    """E.164 tanpa '+' lalu SHA-256 — bentuk yang diminta Meta/Google."""
    if not phone:
        return None
    return sha256_of(normalize_phone_e164(phone).lstrip("+"))


def hash_email(email: str) -> str:
    if not email:
        return None
    return sha256_of(str(email).strip().lower())


def user_data_for(lead: dict) -> dict:
    """Payload identitas TER-HASH (kunci `ph`/`em` sesuai kontrak platform)."""
    out = {}
    ph = hash_phone((lead or {}).get("phone"))
    em = hash_email((lead or {}).get("email"))
    if ph:
        out["ph"] = ph
    if em:
        out["em"] = em
    return out


def event_id_for(*, org_id: str, event_name: str, lead_id: str = None,
                 deal_id: str = None) -> str:
    """ID event deterministik: peristiwa bisnis yang SAMA selalu menghasilkan ID yang sama,
    sehingga percobaan kedua (retry / event kembar) tidak dihitung dua kali."""
    raw = f"{org_id}|{event_name}|{lead_id or ''}|{deal_id or ''}"
    return sha256_of(raw)[:32]


async def _send_live(doc: dict) -> tuple:
    """Kirim event ke platform. -> (status, pesan). Hanya dipanggil saat kredensial ada."""
    platform = doc["platform"]
    if platform != "meta":
        return "pending", (f"Kredensial {PLATFORM_LABEL.get(platform, platform)} terpasang, "
                           "tetapi transport live untuk platform ini belum dipasang — event "
                           "tersimpan dan bisa dikirim ulang tanpa mengubah kontrak.")
    pixel = os.environ.get("META_PIXEL_ID")
    if not pixel:
        return "pending", ("META_CAPI_TOKEN terisi tetapi META_PIXEL_ID belum — Meta tidak "
                           "tahu ke pixel mana event ini harus masuk.")
    payload = {"data": [{
        "event_name": doc["event_name"],
        "event_time": int(datetime.now(timezone.utc).timestamp()),
        "event_id": doc["event_id"], "action_source": "system_generated",
        "user_data": doc.get("user_data") or {},
        "custom_data": {"value": doc.get("value") or 0,
                        "currency": doc.get("currency") or "IDR"},
    }]}
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            res = await client.post(f"{GRAPH}/{pixel}/events", json=payload,
                                    params={"access_token": os.environ["META_CAPI_TOKEN"]})
        if res.status_code == 200:
            return "sent", "Diterima Meta Conversions API."
        detail = ((res.json() or {}).get("error") or {}).get("message") or res.text[:200]
        return "failed", f"Meta menolak event (HTTP {res.status_code}): {detail}"
    except Exception as exc:  # noqa: BLE001 — jaringan: laporkan apa adanya
        return "failed", f"Gagal menghubungi Meta: {exc}"


async def record_conversion(*, event_name, lead=None, deal=None, value=0,
                            currency="IDR", org_id=ORG_ID):
    """Tulis satu baris `conversion_events` + kirim balik ke platform (bila live).

    `event_name` memakai taksonomi iklan: 'Lead', 'SubmitApplication', 'InitiateCheckout',
    'Purchase'. Mengembalikan dokumen tersimpan, atau None bila sumbernya tidak bisa
    dilacak ke platform iklan. Idempoten: peristiwa yang sama tidak pernah tersimpan dua kali.
    """
    lead = lead or {}
    source = lead.get("source")
    platform = platform_for_source(source)
    if not platform:
        return None  # organic / manual channel — no loop to close.
    event_id = event_id_for(org_id=org_id, event_name=event_name, lead_id=lead.get("id"),
                            deal_id=(deal or {}).get("id"))
    existing = await db.conversion_events.find_one({"org_id": org_id, "event_id": event_id},
                                                  {"_id": 0})
    if existing:
        logger.info("[CAPI dedup] event %s sudah ada (%s) — tidak dihitung dua kali",
                    event_name, event_id)
        return {**existing, "duplicate": True}
    ts = now_iso()
    attribution = lead.get("attribution") or {}
    live = _live(platform)
    doc = {
        "id": new_id(), "org_id": org_id, "platform": platform,
        "platform_label": PLATFORM_LABEL.get(platform, platform),
        "event_name": event_name, "event_id": event_id,
        "source": source, "campaign": lead.get("campaign"),
        "campaign_id": attribution.get("campaign_id"),
        "adset_id": attribution.get("adset_id"), "ad_id": attribution.get("ad_id"),
        "creative_id": attribution.get("creative_id"),
        "lead_id": lead.get("id"), "deal_id": (deal or {}).get("id"),
        "value": int(value or 0), "currency": currency,
        "transport": "live" if live else "simulation",
        "user_data": user_data_for(lead),
        "status": "sent" if not live else "pending",
        "message": None, "attempts": 0, "last_attempt_at": None,
        "sent_at": ts, "created_at": ts,
    }
    if not live:
        # Tanpa kredensial tidak ada paket yang keluar: katakan apa adanya.
        doc["status"] = "simulated"
        doc["message"] = ("Mode simulasi: event dicatat lengkap (termasuk hash identitas) dan "
                          "siap dikirim begitu kredensial platform diisi.")
    else:
        status, message = await _send_live(doc)
        doc.update({"status": status, "message": message, "attempts": 1,
                    "last_attempt_at": now_iso()})
    await db.conversion_events.insert_one(dict(doc))
    doc.pop("_id", None)
    logger.info("[CAPI %s/%s] platform=%s event=%s value=%s campaign=%s lead=%s",
                doc["transport"], doc["status"], platform, event_name, value,
                doc.get("campaign"), lead.get("id"))
    return doc


async def resend_conversion(event_row_id: str, *, org_id=ORG_ID, actor="system"):
    """Kirim ulang satu event. Di mode simulasi tidak ada yang dikirim — dan itu dikatakan."""
    doc = await db.conversion_events.find_one({"id": event_row_id, "org_id": org_id},
                                              {"_id": 0})
    if not doc:
        raise ValueError("Event konversi tidak ditemukan.")
    platform = doc.get("platform")
    if not _live(platform):
        raise ValueError(
            f"{PLATFORM_LABEL.get(platform, platform)} masih mode simulasi "
            f"({LIVE_ENV_BY_PLATFORM.get(platform, 'token')} belum diisi) — tidak ada yang "
            "bisa dikirim ulang. Event tetap tersimpan dan akan bisa dikirim setelah "
            "kredensial dipasang.")
    doc.setdefault("user_data", {})
    status, message = await _send_live(doc)
    ts = now_iso()
    await db.conversion_events.update_one({"id": event_row_id}, {
        "$set": {"status": status, "message": message, "transport": "live",
                 "last_attempt_at": ts, "resent_by": actor},
        "$inc": {"attempts": 1}})
    return await db.conversion_events.find_one({"id": event_row_id}, {"_id": 0})
