"""wa_docs — kirim dokumen terbit (PDF) lewat WhatsApp (Fase 98D).

PDF dirender lewat JALUR YANG SAMA dengan tombol PDF di tab Dokumen Terbit: permintaan internal ke
rute `pdf_url` (ASGI, membawa header autentikasi pemanggil → RBAC ikut berlaku). Berkas disimpan ke
storage, diunggah ke Meta (`/media`) bila live, lalu dikirim `type: document`; tercatat di percakapan
lead/customer dan `doc_shares`.
"""
import re

import httpx
from fastapi import HTTPException

import settings_store as st
import wa_compliance as wcomp
import wa_gateway as gw
from core_utils import new_id, now_iso
from db import db, ORG_NAME

ALLOWED_PDF = re.compile(
    r"^/(booking-fee/deals/[\w-]+/(invoice|refunds/[\w-]+)/pdf|documents/[\w-]+/pdf|finance/ar/[\w-]+/invoice/pdf"
    r"|finance/ar/receipts/[\w-]+/pdf|tax/faktur/[\w-]+/pdf|cost-invoices/[\w-]+/pdf|cost-receipts/[\w-]+/pdf"
    r"|handover/[\w-]+/pdf)$")
DEFAULT_CAPTION = "Halo {nama}, berikut {dokumen}{nomor} dari {org}. Simpan dokumen ini sebagai arsip Anda."


async def _entity(org: str, entity_type: str, entity_id: str) -> dict:
    coll = db.leads if entity_type == "lead" else db.customers
    return await coll.find_one({"id": entity_id, "org_id": org}, {"_id": 0}) or {}


async def _doc_template(org: str) -> dict:
    code = await st.get("wa.document_template_code", org_id=org) or "document_delivery"
    return await db.wa_templates.find_one({"org_id": org, "code": code}, {"_id": 0}) or {}


async def route_for(org: str, phone: str) -> dict:
    """Jalur kirim PDF (Fase 99): sesi 24 jam terbuka → `type: document` + caption; tertutup →
    template UTILITY berheader dokumen (wajib approved saat live)."""
    conv = await db.conversations.find_one({"org_id": org, "channel": "whatsapp", "contact_phone": phone},
                                           {"_id": 0, "window_expires_at": 1}, sort=[("created_at", -1)])
    open_ = gw.window_open(conv)
    tpl = await _doc_template(org)
    ok_tpl = bool(tpl) and tpl.get("header_type") == "document" and tpl.get("status") == "approved"
    out = {"window_open": open_, "template_code": tpl.get("code"), "template_name": tpl.get("name"),
           "template_ready": ok_tpl, "template_status": tpl.get("meta_status") or tpl.get("status")}
    if open_:
        out.update({"via": "session", "note": "Sesi 24 jam terbuka — PDF dikirim langsung dengan teks pengantar."})
    elif ok_tpl:
        out.update({"via": "template", "note": f"Sesi tertutup — PDF dikirim sebagai header template '{tpl.get('name')}'."})
    else:
        out.update({"via": "blocked", "note": ("Sesi 24 jam tertutup dan template berheader dokumen belum tersedia/"
                                              "disetujui — di mode live Meta akan menolak (#131047).")})
    return out


async def eligibility(org: str, entity_type: str, entity_id: str) -> dict:
    """{enabled, reason, phone, name, route} — alasan jelas bila tombol harus nonaktif."""
    ent = await _entity(org, entity_type, entity_id)
    phone = gw.valid_phone(ent.get("phone") or "")
    cfg = await gw.get_config(org)
    out = {"enabled": False, "reason": None, "phone": phone or ent.get("phone"), "name": ent.get("name"),
           "mode": cfg["effective_mode"], "route": None}
    if not ent:
        out["reason"] = "Data pembeli tidak ditemukan."
    elif not phone:
        out["reason"] = "Nomor WhatsApp pembeli tidak valid / belum format +62 — perbaiki di profil."
    elif not cfg.get("is_active", True):
        out["reason"] = "Channel WhatsApp dinonaktifkan di Pusat Konfigurasi."
    elif await wcomp.is_opted_out(org, phone):
        out["reason"] = "Nomor ini opt-out dari WhatsApp (menolak pesan)."
    else:
        out["route"] = await route_for(org, phone)
        if out["route"]["via"] == "blocked" and cfg["effective_mode"] == "live":
            out["reason"] = out["route"]["note"]
        else:
            out["enabled"] = True
    return out


async def render_pdf(app, pdf_url: str, headers: dict) -> bytes:
    if not ALLOWED_PDF.match(pdf_url or ""):
        raise HTTPException(400, "pdf_url bukan dokumen terbit yang dikenal.")
    fwd = {k: v for k, v in headers.items() if k.lower() in ("authorization", "cookie")}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://sipro.internal",
                                 timeout=60) as cli:
        r = await cli.get(f"/api{pdf_url}", headers=fwd)
    if r.status_code >= 300:
        try:
            detail = r.json().get("detail")
        except ValueError:
            detail = r.text[:200]
        raise HTTPException(r.status_code if r.status_code in (403, 404) else 400,
                            f"PDF belum bisa dirender: {detail}")
    return r.content


async def send_document(org: str, *, app, headers: dict, entity_type: str, entity_id: str, pdf_url: str,
                        label: str, number: str = None, caption: str = None, actor: str) -> dict:
    elig = await eligibility(org, entity_type, entity_id)
    if not elig["enabled"]:
        raise HTTPException(400, elig["reason"])
    pdf = await render_pdf(app, pdf_url, headers)
    filename = re.sub(r"[^\w.-]+", "_", f"{label}{'-' + number if number else ''}.pdf")
    import storage
    rec = await storage.save_file(data=pdf, filename=filename, content_type="application/pdf", org_id=org,
                                  owner_type=entity_type, owner_id=entity_id, uploaded_by=actor,
                                  doc_type="wa_document", tag="wa_document", optimize=False)
    tpl = await st.get("wa.document_caption", org_id=org) or DEFAULT_CAPTION
    text = caption or str(tpl).format(nama=elig["name"] or "Bapak/Ibu", dokumen=label,
                                      nomor=f" {number}" if number else "", org=ORG_NAME)
    adapter, _cfg = await gw.adapter_for(org)
    document = {"filename": filename, "caption": text, "file_id": rec.get("id"),
                "link": f"/api/files/{rec.get('id')}"}
    if getattr(adapter, "mode", "") == "live":
        up = await adapter.upload_media(pdf, filename, "application/pdf")
        if not up.get("ok"):
            raise HTTPException(424, f"Unggah PDF ke Meta gagal ({up.get('error_code')}): {up.get('error_detail')}")
        document = {**document, "media_id": up["media_id"], "link": None}
    import wa_inbound as wi
    lead = await db.leads.find_one({"org_id": org, "phone": elig["phone"]}, {"_id": 0})
    conv = await wi._conversation_for(org, elig["phone"], elig["name"], lead)
    route = elig["route"]
    template = params = None
    if route["via"] == "template":
        template = await _doc_template(org)
        vals = {"nama": elig["name"] or "Bapak/Ibu", "dokumen": label, "nomor": f" {number}" if number else "",
                "org": ORG_NAME}
        params = gw.template_params(template, vals)
        text = template.get("body") or text
        for k, v in vals.items():
            text = text.replace("{{%s}}" % k, str(v))
        document = {**document, "caption": text}
    msg = await gw.send(org, elig["phone"], kind="document", body=text, document=document, template=template,
                        template_params=params, conversation_id=conv["id"], actor=actor, category="utility",
                        ref={"entity_type": entity_type, "entity_id": entity_id, "pdf_url": pdf_url,
                             "via": route["via"]})
    share = {"id": new_id(), "org_id": org, "entity_type": entity_type, "entity_id": entity_id, "pdf_url": pdf_url,
             "label": label, "number": number, "file_id": rec.get("id"), "message_id": msg["id"],
             "conversation_id": conv["id"], "channel": "whatsapp", "to": elig["phone"], "status": msg["status"],
             "via": route["via"], "template_code": (template or {}).get("code"),
             "error_code": msg.get("error_code"), "error_detail": msg.get("error_detail"),
             "created_by": actor, "created_at": now_iso()}
    await db.wa_doc_shares.insert_one(dict(share))
    if lead:
        from engine import add_activity
        await add_activity(entity_type="lead", entity_id=lead["id"], type="system",
                           body=f"Dokumen {label}{' ' + number if number else ''} dikirim via WhatsApp ({msg['status']}).",
                           actor=actor, org_id=org, meta={"message_id": msg["id"], "pdf_url": pdf_url})
    msg.pop("_id", None)
    return {"message": msg, "share": share}


async def shares(org: str, entity_type: str, entity_id: str) -> list:
    rows = await db.wa_doc_shares.find({"org_id": org, "entity_type": entity_type, "entity_id": entity_id}, {"_id": 0}) \
        .sort("created_at", -1).to_list(200)
    ids = [r["message_id"] for r in rows]
    live = {m["id"]: m for m in await db.messages.find({"id": {"$in": ids}}, {"_id": 0, "id": 1, "status": 1,
                                                                            "error_code": 1, "error_detail": 1}).to_list(200)}
    for r in rows:
        m = live.get(r["message_id"]) or {}
        r.update({k: m.get(k, r.get(k)) for k in ("status", "error_code", "error_detail")})
    return rows
