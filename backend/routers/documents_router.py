"""Documents (SPR/PPJB) engine: create from template -> finalize -> sign -> PDF. Slice A."""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
import io

import listing as lst
import stage_clock as clock
import sequences
from db import db, ORG_ID, ORG_NAME
from core_utils import new_id, now_iso, serialize_doc, parse_pagination
from rbac import require_permission, scope_query, is_scoped_sales
from engine import add_activity, dispatch_pending, emit
from models import DocumentCreate, DocumentSign
from pdf_utils import build_document_pdf

router = APIRouter(prefix="/documents", tags=["documents"])


def _resolve(content: str, ctx: dict) -> str:
    out = content
    for k, v in ctx.items():
        out = out.replace("{{" + k + "}}", str(v if v is not None else "-"))
    return out


def _idr(n) -> str:
    try:
        return f"{int(n):,}".replace(",", ".")
    except Exception:
        return str(n)


DOCUMENT_SORTS = {"doc_number": "doc_number", "title": "title", "status": "status",
                  "template_code": "template_code", "created_at": "created_at",
                  "updated_at": "updated_at", **clock.SORTS}


@router.get("")
async def list_documents(q: str = None, status: str = None, template_code: str = None,
                         created_from: str = None, created_to: str = None, sla: str = None,
                         sort: str = None, direction: str = None,
                         skip: int = 0, limit: int = 50,
                         user: dict = Depends(require_permission("documents", "view"))):
    """Daftar dokumen: cari + filter multi (status/template) + sort server-side (Fase 40) +
    filter umur status dari kebijakan Pusat Konfigurasi (Fase 41)."""
    skip, limit = parse_pagination(skip, limit)
    base = {}
    lst.apply_in(base, "status", status)
    lst.apply_in(base, "template_code", template_code)
    clock.apply_sla_filter(base, "document", sla)
    lst.apply_range(base, "created_at", created_from, created_to)
    lst.apply_search(base, q, ("doc_number", "title", "template_code"))
    query = scope_query(user, base)
    total = await db.documents.count_documents(query)
    rows = await (db.documents.find(query, {"_id": 0})
                  .sort(lst.sort_spec(sort, direction, DOCUMENT_SORTS, ("created_at", -1)))
                  .skip(skip).limit(limit).to_list(limit))
    await clock.attach(rows, "document", org_id=user.get("org_id", ORG_ID))
    counts = {}
    for st in ("draft", "final", "signed"):
        counts[st] = await db.documents.count_documents({**scope_query(user, {}), "status": st})
    return {"data": serialize_doc(rows), "total": total, "counts": counts}


@router.post("")
async def create_document(payload: DocumentCreate,
                          user: dict = Depends(require_permission("documents", "create"))):
    org = user.get("org_id", ORG_ID)
    deal = await db.deals.find_one({"id": payload.deal_id, "org_id": org}, {"_id": 0})
    if not deal:
        raise HTTPException(status_code=404, detail="Deal tidak ditemukan")
    if is_scoped_sales(user) and deal.get("assigned_to") != user.get("email"):
        raise HTTPException(status_code=403, detail="Akses ditolak: bukan deal Anda")
    tpl = await db.document_templates.find_one({"org_id": org, "code": payload.template_code}, {"_id": 0})
    if not tpl:
        raise HTTPException(status_code=404, detail=f"Template {payload.template_code} tidak ditemukan")
    # SPR generik (jalur lama) DITUTUP: SPR resmi hanya lahir dari kontrak (docgen, sesuai skema
    # deal = piutang Finance). Dua jalur dokumen = dua versi angka.
    if payload.template_code == "SPR":
        if deal.get("contract_id"):
            raise HTTPException(status_code=400, detail=(
                "SPR generik tidak lagi diterbitkan. Terbitkan SPR resmi dari kontrak "
                "(Dokumen › Terbitkan Dokumen, atau tombol SPR di daftar deal) — variannya "
                "mengikuti skema pembayaran deal."))
        raise HTTPException(status_code=400, detail=(
            "SPR resmi lahir dari kontrak — jadikan deal ini Pembeli dulu (booking → Jadikan "
            "Pembeli), lalu terbitkan SPR sesuai skema dari kontraknya."))
    # PPJB guard (prasyarat): butuh progress konstruksi >= 20%
    unit = await db.units.find_one({"id": deal.get("unit_id")}, {"_id": 0}) or {}
    if payload.template_code == "PPJB" and (unit.get("construction_progress") or 0) < 20:
        raise HTTPException(status_code=400,
                            detail="PPJB ditolak: progres konstruksi < 20% (prasyarat belum terpenuhi).")
    # AJB guard (prasyarat): butuh BAST (revenue recognition) sudah terjadi untuk deal ini.
    if payload.template_code == "AJB":
        rr = await db.revenue_recognitions.find_one({"org_id": org, "deal_id": payload.deal_id}, {"_id": 0})
        if not rr:
            raise HTTPException(status_code=400,
                                detail="AJB ditolak: BAST/serah terima belum dilakukan (prasyarat belum terpenuhi).")
    lead = await db.leads.find_one({"id": deal.get("lead_id")}, {"_id": 0}) or {}
    project = await db.projects.find_one({"id": deal.get("project_id")}, {"_id": 0}) or {}
    ts = now_iso()
    year = ts[:4]
    doc_number = await sequences.next_number(f"document:{payload.template_code}", org,
                                             prefix=payload.template_code, year=year,
                                             context={"template_code": payload.template_code,
                                                      "project_code": project.get("code"),
                                                      "project_name": project.get("name"),
                                                      "unit_id": deal.get("unit_id"),
                                                      "customer_name": lead.get("name")})
    ctx = {
        "doc_number": doc_number, "date": ts[:10], "buyer_name": lead.get("name"),
        "buyer_phone": lead.get("phone"), "project_name": project.get("name"),
        "unit_code": unit.get("code"), "unit_type": unit.get("type"),
        "price": _idr(deal.get("price")), "booking_fee": _idr(deal.get("booking_fee")),
        "reserved_until": (deal.get("reserved_until") or "-")[:10], "sales_name": user.get("name"),
        "org_name": ORG_NAME,
    }
    content = _resolve(tpl["content"], ctx)
    doc = {
        "id": new_id(), "org_id": org, "template_id": tpl["id"], "template_code": payload.template_code,
        "doc_number": doc_number, "title": tpl.get("name", payload.template_code),
        "deal_id": payload.deal_id, "lead_id": deal.get("lead_id"), "unit_id": deal.get("unit_id"),
        "assigned_to": deal.get("assigned_to"), "content": content, "status": "draft",
        "signatures": [], "created_by": user.get("email"), "created_at": ts, "updated_at": ts,
    }
    await db.documents.insert_one(doc)
    await add_activity(entity_type="deal", entity_id=payload.deal_id, type="document",
                       body=f"Dokumen {doc_number} dibuat (draft).", actor=user.get("email"), org_id=org)
    doc.pop("_id", None)
    return {"data": serialize_doc(doc)}


async def _get_doc_scoped(doc_id: str, user: dict) -> dict:
    d = await db.documents.find_one({"id": doc_id}, {"_id": 0})
    if not d:
        raise HTTPException(status_code=404, detail="Dokumen tidak ditemukan")
    if is_scoped_sales(user) and d.get("assigned_to") != user.get("email"):
        raise HTTPException(status_code=403, detail="Akses ditolak: bukan dokumen Anda")
    return d


@router.get("/{doc_id}")
async def get_document(doc_id: str, user: dict = Depends(require_permission("documents", "view"))):
    d = await _get_doc_scoped(doc_id, user)
    return {"data": serialize_doc(d)}


@router.post("/{doc_id}/finalize")
async def finalize_document(doc_id: str, user: dict = Depends(require_permission("documents", "update"))):
    d = await _get_doc_scoped(doc_id, user)
    if d.get("status") != "draft":
        raise HTTPException(status_code=400, detail="Hanya dokumen draft yang bisa difinalisasi.")
    ts = now_iso()
    await db.documents.update_one({"id": doc_id}, {"$set": {"status": "finalized", "finalized_at": ts, "updated_at": ts}})
    fresh = await db.documents.find_one({"id": doc_id}, {"_id": 0})
    return {"data": serialize_doc(fresh)}


@router.post("/{doc_id}/sign")
async def sign_document(doc_id: str, payload: DocumentSign,
                        user: dict = Depends(require_permission("documents", "sign"))):
    d = await _get_doc_scoped(doc_id, user)
    if d.get("status") not in ("finalized", "signed"):
        raise HTTPException(status_code=400, detail="Dokumen harus difinalisasi sebelum ditandatangani.")
    # SPR yang angkanya sudah tidak sama dengan tagihan Finance tidak boleh ditandatangani.
    import spr_compare
    alasan = await spr_compare.sign_block_reason(user.get("org_id", ORG_ID), d)
    if alasan:
        raise HTTPException(status_code=400, detail=alasan)
    ts = now_iso()
    sig = {"role": payload.role, "name": payload.name, "signed_at": ts}
    first_signature = not d.get("first_signed_at")
    await db.documents.update_one({"id": doc_id}, {
        "$push": {"signatures": sig},
        "$set": {"status": "signed", "first_signed_at": d.get("first_signed_at") or ts, "updated_at": ts}})
    await add_activity(entity_type="deal", entity_id=d.get("deal_id"), type="document",
                       body=f"Dokumen {d.get('doc_number')} ditandatangani oleh {payload.name} ({payload.role}).",
                       actor=user.get("email"), org_id=user.get("org_id", ORG_ID))
    if first_signature:
        # Fase 43: hanya TANDA TANGAN PERTAMA yang menjadi peristiwa bisnis. Tanpa penjagaan
        # ini, dokumen dengan 3 pihak penanda tangan akan menerbitkan 3 event konversi untuk
        # satu SPR yang sama (dan `event_id` CAPI juga akan menghitungnya sebagai satu — jadi
        # dua lapis penjagaan, bukan hanya satu).
        await emit("document.signed", "document", doc_id,
                   {"template_code": d.get("template_code"), "deal_id": d.get("deal_id")},
                   org_id=user.get("org_id", ORG_ID))
        await dispatch_pending()
    fresh = await db.documents.find_one({"id": doc_id}, {"_id": 0})
    return {"data": serialize_doc(fresh)}


@router.get("/{doc_id}/pdf")
async def document_pdf(doc_id: str, user: dict = Depends(require_permission("documents", "view"))):
    d = await _get_doc_scoped(doc_id, user)
    # Fase 60: tampilan (kop, footer, tanda tangan, baris biaya) dibaca dari Konfigurasi
    # Dokumen milik organisasi — bukan lagi teks polos tanpa identitas.
    import doc_layout as dl
    org = user.get("org_id", ORG_ID)
    layout = await dl.get_layout(org, d.get("template_code") or "SPR_CASH")
    snap = d.get("context_snapshot") or {}
    layout.setdefault("options", {}).setdefault("doc_date", snap.get("document_date"))
    # Baris biaya terkonfigurasi (urutan/label/tampil dari Konfigurasi Dokumen, NILAI dari
    # kontrak). Dulu hanya pratinjau yang memakainya; dokumen asli mengabaikannya.
    money_rows = None
    from document_pdf_context import money_rows_for_document
    money_rows = await money_rows_for_document(org, d, layout)
    pdf = build_document_pdf(title=d.get("title", "Dokumen"), doc_number=d.get("doc_number"),
                             content=d.get("content", ""), signatures=d.get("signatures"),
                             org_name=ORG_NAME, layout=layout, money_rows=money_rows,
                             images=await dl.images(org, layout))
    filename = f"{d.get('doc_number', 'dokumen').replace('/', '-')}.pdf"
    return StreamingResponse(io.BytesIO(pdf), media_type="application/pdf",
                             headers={"Content-Disposition": f'inline; filename="{filename}"'})
