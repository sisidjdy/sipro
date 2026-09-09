"""ROUTER PENAWARAN (Fase 47C) — prefix `/quotations`.

Pemisahan tugas:
  * sales boleh MEMBUAT, MEREVISI, MENGIRIM, dan MENGONVERSI penawaran miliknya
    (`quotations:create/update`, row-scope: hanya penawaran yang ia buat);
  * hanya manajer sales/direksi yang boleh MEMUTUSKAN diskon di atas kewenangan
    (`quotations:approve`) — kalau tidak, batas diskon hanya hiasan.
"""
from fastapi import APIRouter, Depends, HTTPException, Response

import catalog as cat
import quotation_engine as qe
from core_utils import parse_pagination, serialize_doc
from db import ORG_ID, db
from models_p47 import (QuotationCreateIn, QuotationDecisionIn, QuotationSendIn,
                       QuotationSimulateIn)
from pdf_utils import build_document_pdf
from rbac import is_scoped_sales, audit_log, require_permission

router = APIRouter(prefix="/quotations", tags=["quotations"])


def _org(user: dict) -> str:
    return user.get("org_id", ORG_ID)


def _own(user: dict) -> str:
    """Sales hanya melihat penawaran yang ia buat (row-scope dipaksa server)."""
    return user.get("email") if is_scoped_sales(user) else None


async def _guard_owner(org: str, quotation_id: str, user: dict) -> dict:
    q = await qe.get(org, quotation_id)
    if is_scoped_sales(user) and q.get("created_by") != user.get("email"):
        raise HTTPException(status_code=403,
                            detail="Penawaran ini milik sales lain.")
    return q


@router.post("/simulate")
async def simulate(payload: QuotationSimulateIn,
                   user: dict = Depends(require_permission("quotations", "create"))):
    """Hitung harga+termin+simulasi KPR TANPA menyimpan. KPR kosong = 'belum ada data'."""
    try:
        out = await qe.simulate(_org(user), unit_id=payload.unit_id,
                                addons=[a.model_dump() for a in payload.addons],
                                scheme_id=payload.scheme_id,
                                discount_amount=payload.discount_amount,
                                kpr=(payload.kpr.model_dump() if payload.kpr else None),
                                discount_scheme_id=payload.discount_scheme_id,
                                promo_id=payload.promo_id, coupon_code=payload.coupon_code,
                                lead_id=payload.lead_id, allin_scheme_id=payload.allin_scheme_id,
                                booking_fee=payload.booking_fee)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"data": serialize_doc(out)}


@router.get("/options")
async def form_options(project_id: str = None,
                       user: dict = Depends(require_permission("quotations", "view"))):
    """Master minimum untuk layar penawaran: unit tersedia + skema bayar + add-on aktif.

    Kenapa ada pintu sendiri (temuan uji E2E Fase 47): daftar skema pembayaran hanya tersedia
    di `GET /finance/config/payment-schemes` yang menuntut `finance:view` — izin yang SENGAJA
    TIDAK dimiliki sales (di sana ada data kas/AR). Akibatnya dialog "Buat penawaran" milik
    sales gagal memuat SELURUH masternya ("Akses ditolak: tidak memiliki izin 'view' pada
    'finance'" + daftar unit kosong), sehingga fitur inti Fase 47C tidak bisa dicapai oleh
    peran yang justru memakainya — cacat "fitur yang tidak bisa dijangkau", bukan sekadar
    kosmetik.

    Yang dikirim di sini hanya PROYEKSI READ-ONLY yang memang tampil pada penawaran (kode
    unit, harga, nama skema, add-on beserta harga satuannya) — bukan konfigurasi keuangan.
    Sumber datanya tetap satu: koleksi yang sama dengan yang dipakai mesin harga.
    """
    org = _org(user)
    units = await db.units.find(
        {"org_id": org, "status": "available",
         **({"project_id": project_id} if project_id else {})},
        {"_id": 0, "id": 1, "code": 1, "type": 1, "price": 1, "project_id": 1, "block": 1,
         "cluster_code": 1}).sort("code", 1).to_list(300)
    schemes = await db.payment_schemes.find(
        {"org_id": org}, {"_id": 0, "id": 1, "name": 1, "type": 1, "is_default": 1,
                          "dp_pct": 1, "installments": 1}).sort("created_at", 1).to_list(50)
    addons = await cat.list_addons(org, None, True, project_id)
    return {"data": {"units": serialize_doc(units), "schemes": serialize_doc(schemes),
                     "addons": serialize_doc(addons)}}


@router.get("")
async def listing(lead_id: str = None, unit_id: str = None, state: str = None,
                  skip: int = 0, limit: int = 25,
                  user: dict = Depends(require_permission("quotations", "view"))):
    skip, limit = parse_pagination(skip, limit)
    out = await qe.listing(_org(user), lead_id=lead_id, unit_id=unit_id, state=state,
                           owner_email=_own(user), skip=skip, limit=limit)
    return {"data": serialize_doc(out["data"]), "total": out["total"],
            "summary": out["summary"]}


@router.post("")
async def create(payload: QuotationCreateIn,
                 user: dict = Depends(require_permission("quotations", "create"))):
    try:
        doc = await qe.create(_org(user), lead_id=payload.lead_id, unit_id=payload.unit_id,
                              addons=[a.model_dump() for a in payload.addons],
                              scheme_id=payload.scheme_id,
                              discount_amount=payload.discount_amount,
                              kpr=(payload.kpr.model_dump() if payload.kpr else None),
                              valid_days=payload.valid_days, note=payload.note,
                              discount_reason=payload.discount_reason,
                              actor=user.get("email"),
                              discount_scheme_id=payload.discount_scheme_id,
                              promo_id=payload.promo_id, coupon_code=payload.coupon_code)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit_log(user, "create", "quotations", doc["id"],
                    {"no": doc["no"], "net_price": doc["net_price"],
                     "discount": doc["discount_amount"]})
    return {"data": serialize_doc(doc),
            "message": ("Penawaran menunggu persetujuan diskon manajer."
                        if doc["state"] == "awaiting_approval" else "Penawaran dibuat.")}


@router.get("/{quotation_id}")
async def detail(quotation_id: str,
                 user: dict = Depends(require_permission("quotations", "view"))):
    try:
        return {"data": serialize_doc(await _guard_owner(_org(user), quotation_id, user))}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{quotation_id}/revise")
async def revise(quotation_id: str, payload: QuotationCreateIn,
                 user: dict = Depends(require_permission("quotations", "update"))):
    """Revisi = VERSI BARU; versi lama menjadi 'diganti revisi terbaru' dan tetap terbaca."""
    org = _org(user)
    try:
        old = await _guard_owner(org, quotation_id, user)
        doc = await qe.create(org, lead_id=payload.lead_id or old["lead_id"],
                              unit_id=payload.unit_id,
                              addons=[a.model_dump() for a in payload.addons],
                              scheme_id=payload.scheme_id,
                              discount_amount=payload.discount_amount,
                              kpr=(payload.kpr.model_dump() if payload.kpr else None),
                              valid_days=payload.valid_days, note=payload.note,
                              discount_reason=payload.discount_reason,
                              actor=user.get("email"), version_of=old,
                              discount_scheme_id=payload.discount_scheme_id,
                              promo_id=payload.promo_id, coupon_code=payload.coupon_code)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit_log(user, "revise", "quotations", doc["id"],
                    {"from": quotation_id, "version": doc["version"]})
    return {"data": serialize_doc(doc), "message": f"Revisi v{doc['version']} dibuat."}


@router.post("/{quotation_id}/decision")
async def decision(quotation_id: str, payload: QuotationDecisionIn,
                   user: dict = Depends(require_permission("quotations", "approve"))):
    """Manajer menyetujui/menolak diskon (wajib beralasan)."""
    try:
        out = await qe.decide_discount(_org(user), quotation_id, user.get("email"),
                                       payload.approve, payload.reason)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit_log(user, "decide_discount", "quotations", quotation_id,
                    {"approve": payload.approve, "reason": payload.reason})
    return {"data": serialize_doc(out),
            "message": ("Diskon disetujui." if payload.approve else "Diskon ditolak.")}


@router.post("/{quotation_id}/send")
async def send(quotation_id: str, payload: QuotationSendIn,
               user: dict = Depends(require_permission("quotations", "update"))):
    """Kirim ke calon pembeli. Tanpa kredensial WhatsApp → status ditulis 'simulasi'."""
    org = _org(user)
    try:
        await _guard_owner(org, quotation_id, user)
        out = await qe.mark_sent(org, quotation_id, user.get("email"),
                                 channel=payload.channel or "whatsapp", note=payload.note)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"data": serialize_doc(out),
            "message": f"Pengiriman: {out['delivery'].get('status')}"}


@router.post("/{quotation_id}/convert")
async def convert(quotation_id: str,
                  user: dict = Depends(require_permission("quotations", "update"))):
    """Konversi penawaran menjadi reservasi unit (deal)."""
    org = _org(user)
    try:
        await _guard_owner(org, quotation_id, user)
        out = await qe.convert(org, quotation_id, user.get("email"))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit_log(user, "convert", "quotations", quotation_id,
                    {"deal_id": out["deal"]["id"]})
    return {"data": serialize_doc(out), "message": "Penawaran menjadi reservasi unit."}


@router.get("/{quotation_id}/pdf")
async def pdf(quotation_id: str,
              user: dict = Depends(require_permission("quotations", "view"))):
    """PDF penawaran — isinya PERSIS angka yang tersimpan (bukan dihitung ulang di render)."""
    org = _org(user)
    try:
        q = await _guard_owner(org, quotation_id, user)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    def rp(v):
        return "Rp " + f"{int(v or 0):,}".replace(",", ".")

    lines = [f"Calon pembeli : {q.get('lead_name') or '-'}",
             f"Unit : {q.get('unit_code') or '-'}",
             f"Harga unit : {rp(q.get('base_price'))}"]
    for a in q.get("addons") or []:
        lines.append(f"Tambahan {a.get('name')} : {rp(a.get('amount'))} ({a.get('formula')})")
    lines += [f"Total sebelum potongan : {rp(q.get('gross_price'))}"]
    for dl in q.get("discount_lines") or []:
        lines.append(f"{dl.get('source_label')} {dl.get('code')} : -{rp(dl.get('amount'))} "
                     f"({dl.get('formula')})")
    lines += [f"Total potongan : {rp(q.get('discount_amount'))} ({q.get('discount_pct')}%)",
              f"Harga penawaran : {rp(q.get('net_price'))}",
              f"Skema pembayaran : {(q.get('scheme') or {}).get('name') or '-'}"]
    for t in q.get("terms") or []:
        lines.append(f"{t.get('label')} : {rp(t.get('amount'))} · jatuh tempo "
                     f"{str(t.get('due_date'))[:10]}")
    kpr = q.get("kpr") or {}
    if kpr.get("state") == "complete":
        lines.append(f"Estimasi KPR : {rp(kpr.get('monthly_installment'))}/bulan · "
                     f"{kpr.get('tenor_months')} bulan · bunga {kpr.get('annual_rate_pct')}%")
    else:
        lines.append("Estimasi KPR : belum bisa dihitung ("
                     + ", ".join(kpr.get("missing") or []).replace("_", " ")
                     + " belum diisi)")
    lines.append(f"Berlaku sampai : {q.get('valid_until')}")
    import doc_layout as dl
    _lay = await dl.get_layout(org, "PENAWARAN")
    body = build_document_pdf(layout=_lay, images=await dl.images(org, _lay),
        title="PENAWARAN HARGA UNIT", doc_number=f"{q.get('no')} v{q.get('version')}",
        script_context={"date": str(q.get("created_at") or "")[:10], "sales_name": q.get("created_by") or ""},
        content="\n".join(lines),
        signatures=[{"role": "Sales", "name": q.get("created_by"), "signed_at": None},
                    {"role": "Calon Pembeli", "name": q.get("lead_name"), "signed_at": None}])
    return Response(content=body, media_type="application/pdf", headers={
        "Content-Disposition": f'inline; filename="{q.get("no")}.pdf"'})
