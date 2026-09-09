"""Seed Fase 99 — template UTILITY berheader DOKUMEN untuk pengantar PDF (idempoten).

Saat live, `type: document` bebas hanya boleh di dalam sesi 24 jam. Template ini membuat
"Kirim via WhatsApp" di Dokumen Terbit tetap lolos di luar sesi: PDF dikirim sebagai parameter
HEADER template, teks pengantar sebagai BODY berparameter.
"""
from core_utils import new_id, now_iso
from db import db, ORG_ID

DOC_TEMPLATE_CODE = "document_delivery"
DOC_TEMPLATE_BODY = ("Halo {{nama}}, berikut {{dokumen}}{{nomor}} dari {{org}}. "
                     "Simpan dokumen ini sebagai arsip Anda.")
DOC_TEMPLATE_VARS = ["nama", "dokumen", "nomor", "org"]


async def seed_phase99(org_id: str = ORG_ID) -> dict:
    import wa_gateway as gw
    import wa_templates_meta as wtm
    existing = await db.wa_templates.find_one({"org_id": org_id, "code": DOC_TEMPLATE_CODE}, {"_id": 0, "id": 1})
    if existing:
        return {"created": 0}
    live = (await gw.get_config(org_id))["effective_mode"] == "live"
    ts = now_iso()
    await db.wa_templates.insert_one({
        "id": new_id(), "org_id": org_id, "code": DOC_TEMPLATE_CODE, "name": "Pengantar Dokumen (PDF)",
        "category": "utility", "language": "id", "body": DOC_TEMPLATE_BODY, "variables": DOC_TEMPLATE_VARS,
        "header_type": "document", "header_text": None, "header_sample_handle": None,
        **wtm.initial_fields(DOC_TEMPLATE_CODE, live),
        "created_by": "seed", "created_at": ts, "updated_at": ts})
    return {"created": 1}
