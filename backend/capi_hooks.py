"""capi_hooks.py — Fase 43: SEMUA umpan-balik konversi ke platform iklan, satu tempat.

Sebelum fase ini, tiga panggilan CAPI berserak di dalam `engine.py` (di dalam handler yang
tugas utamanya keuangan/lifecycle). Akibatnya: (a) sulit membuktikan event mana saja yang
benar-benar dikirim, (b) `engine.py` menumpuk tanggung jawab yang tidak berhubungan, dan
(c) event yang diminta spec (`SubmitApplication` saat SPR ditandatangani) tidak ketahuan
belum pernah dipasang. Modul ini memasang handler dengan pola yang sama seperti
`partner_engine.register()`: ditempelkan pada event yang MEMANG sudah terbit di aplikasi,
bukan event karangan.

Peta peristiwa bisnis → taksonomi event platform (`docs/v2/30_MARKETING_INTEGRATION_SPEC.md`
§6):

| Peristiwa nyata di SIPRO        | Event bus         | Event platform      |
|---------------------------------|-------------------|---------------------|
| Lead masuk dari kanal iklan     | `lead.captured`   | `Lead`              |
| SPR ditandatangani (baru)       | `document.signed` | `SubmitApplication` |
| Booking/reservasi unit          | `deal.booked`     | `InitiateCheckout`  |
| AJB / deal selesai              | `deal.sold`       | `Purchase`          |

Kegagalan transport TIDAK PERNAH menggagalkan proses bisnisnya (tanda tangan, booking, AJB
tetap tersimpan) — kegagalan dicatat di `conversion_events.status` + log, supaya bisa dikirim
ulang dari halaman Atribusi & CAPI.
"""
import logging

from capi import record_conversion
from db import db, ORG_ID

logger = logging.getLogger("sipro.capi_hooks")

# Dokumen legal -> event platform. PPJB/AJB punya pemicunya sendiri (deal.ppjb/deal.sold),
# jadi hanya SPR yang menerbitkan event dari jalur tanda tangan dokumen.
DOC_EVENT = {"SPR": "SubmitApplication"}


async def _lead_of(deal: dict, org: str):
    if not deal or not deal.get("lead_id"):
        return None
    return await db.leads.find_one({"id": deal["lead_id"], "org_id": org}, {"_id": 0})


async def _feed(event_name: str, *, lead, deal=None, value=0, org=ORG_ID, ctx=""):
    try:
        await record_conversion(event_name=event_name, lead=lead, deal=deal, value=value,
                                org_id=org)
    except Exception:  # noqa: BLE001 — transport tidak boleh menggagalkan proses bisnis
        logger.exception("CAPI '%s' gagal (%s)", event_name, ctx)


async def on_lead_captured(ev):
    """Lead masuk dari kanal iklan → event `Lead`."""
    org = ev.get("org_id", ORG_ID)
    lead = await db.leads.find_one({"id": ev["entity_id"], "org_id": org}, {"_id": 0})
    if lead:
        await _feed("Lead", lead=lead, org=org, ctx=f"lead {ev.get('entity_id')}")


async def on_deal_booked(ev):
    """Booking = konversi tengah funnel → `InitiateCheckout`."""
    org = ev.get("org_id", ORG_ID)
    deal = await db.deals.find_one({"id": ev["entity_id"], "org_id": org}, {"_id": 0})
    if not deal:
        return
    await _feed("InitiateCheckout", lead=await _lead_of(deal, org), deal=deal,
                value=deal.get("price", 0), org=org, ctx=f"deal {deal.get('id')}")


async def on_deal_sold(ev):
    """AJB / deal selesai → `Purchase` (nilai = harga transaksi)."""
    org = ev.get("org_id", ORG_ID)
    deal = await db.deals.find_one({"id": ev["entity_id"], "org_id": org}, {"_id": 0})
    if not deal:
        return
    await _feed("Purchase", lead=await _lead_of(deal, org), deal=deal,
                value=deal.get("price", 0), org=org, ctx=f"deal {deal.get('id')}")


async def on_document_signed(ev):
    """SPR ditandatangani → `SubmitApplication` (nilai = total kontrak).

    Sinyal ini terjadi jauh lebih awal daripada booking, jadi model optimasi platform belajar
    lebih cepat. Hanya tanda tangan PERTAMA yang menerbitkan event (dijaga di
    `documents_router`), dan `event_id` CAPI menjadi lapis kedua penjagaan.
    """
    doc = await db.documents.find_one({"id": ev["entity_id"]}, {"_id": 0})
    if not doc:
        return
    event_name = DOC_EVENT.get((doc.get("template_code") or "").upper())
    if not event_name:
        return
    org = ev.get("org_id", ORG_ID)
    deal = await db.deals.find_one({"id": doc.get("deal_id"), "org_id": org}, {"_id": 0}) \
        if doc.get("deal_id") else None
    lead = await _lead_of(deal, org)
    if not lead:
        return  # tanpa lead tidak ada atribusi iklan yang loopnya bisa ditutup
    await _feed(event_name, lead=lead, deal=deal, value=(deal or {}).get("price", 0), org=org,
                ctx=f"dokumen {doc.get('doc_number')}")


HOOKS = {
    "lead.captured": on_lead_captured,
    "deal.booked": on_deal_booked,
    "deal.sold": on_deal_sold,
    "document.signed": on_document_signed,
}


def register():
    """Pasang handler pada event yang sudah terbit di aplikasi. Idempoten."""
    import engine
    for etype, handler in HOOKS.items():
        engine.HANDLERS.setdefault(etype, [])
        if handler not in engine.HANDLERS[etype]:
            engine.HANDLERS[etype].append(handler)
    return sorted(HOOKS)
