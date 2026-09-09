"""AR (piutang pembeli): jadwal, receipts, aging, BAST->RevRec. Slice Finance."""
from fastapi import APIRouter, Depends, HTTPException

import listing as lst
import stage_clock as clock
import reference as ref
from db import db, ORG_ID
from core_utils import serialize_doc, parse_pagination
from rbac import require_permission
import finance_engine as fe
from models import ArScheduleCreate, ReceiptCreate
from models_finance import DepositApply, DepositReceive, DepositRefund

router = APIRouter(prefix="/finance/ar", tags=["finance-ar"])


AR_SORTS = {"unit_code": "unit_code", "lead_name": "lead_name", "status": "status",
            "total": "total", "paid": "paid", "outstanding": "outstanding",
            "created_at": "created_at", "updated_at": "updated_at", **clock.SORTS}

# SSOT status piutang (satu sumber: reference.py) — dipakai untuk menghitung angka per status
# agar tidak ada lagi daftar status karangan di router.
AR_STATUS_OPTIONS = ref.GROUPS["ar_status"]["options"]


@router.get("")
async def list_ar(status: str = None, q: str = None, sort: str = None, direction: str = None,
                  created_from: str = None, created_to: str = None, sla: str = None,
                  skip: int = 0, limit: int = 50,
                  user: dict = Depends(require_permission("finance", "view"))):
    """Daftar tagihan AR: cari + filter multi status + sort server-side (Fase 40) +
    filter umur status/SLA penagihan dari Pusat Konfigurasi (Fase 41)."""
    org = user.get("org_id", ORG_ID)
    skip, limit = parse_pagination(skip, limit)
    q_base = {"org_id": org}
    lst.apply_in(q_base, "status", status)
    clock.apply_sla_filter(q_base, "ar_invoice", sla)
    lst.apply_range(q_base, "created_at", created_from, created_to)
    lst.apply_search(q_base, q, ("unit_code", "lead_name", "scheme_name"))
    total = await db.ar_invoices.count_documents(q_base)
    rows = await (db.ar_invoices.find(q_base, {"_id": 0})
                  .sort(lst.sort_spec(sort, direction, AR_SORTS, ("created_at", -1)))
                  .skip(skip).limit(limit).to_list(limit))
    await clock.attach(rows, "ar_invoice", org_id=org)
    # Piutang BIAYA (invoice biaya INB, per komponen all-in) berdampingan dengan piutang unit —
    # supaya Finance melihat seluruh tagihan pembeli, bukan hanya harga unit.
    deal_ids = [r.get("deal_id") for r in rows if r.get("deal_id")]
    cost_by_deal = {}
    if deal_ids:
        async for ci in db.cost_invoices.find({"org_id": org, "deal_id": {"$in": deal_ids},
                                               "status": {"$ne": "void"}},
                                              {"_id": 0, "deal_id": 1, "total": 1, "outstanding": 1, "number": 1}):
            agg = cost_by_deal.setdefault(ci["deal_id"], {"total": 0, "outstanding": 0, "numbers": []})
            agg["total"] += int(ci.get("total") or 0)
            agg["outstanding"] += int(ci.get("outstanding") or 0)
            agg["numbers"].append(ci.get("number"))
    for r in rows:
        agg = cost_by_deal.get(r.get("deal_id")) or {}
        r["cost_total"] = int(agg.get("total") or 0)
        r["cost_outstanding"] = int(agg.get("outstanding") or 0)
        r["cost_invoice_numbers"] = agg.get("numbers") or []
        bd = r.get("breakdown") or {}
        r["addon_total"] = int(r.get("addon_total") or 0)
        r["unit_total"] = int(r.get("unit_total") if r.get("unit_total") is not None
                              else int(r.get("total") or 0) - r["addon_total"])
        r["buyer_total"] = int(bd.get("buyer_total") or (int(r.get("total") or 0) + r["cost_total"]))
    # Angka per status HARUS memakai kosakata yang benar-benar ditulis mesin keuangan
    # (`finance_engine`: unpaid → partial → paid, sama dengan SSOT `reference.ar_status`).
    # Sebelum ini daftar di sini berisi "draft/open/void" yang TIDAK PERNAH ADA di data,
    # sehingga chip filter selalu 0 dan tagihan `unpaid` tidak punya angka sama sekali —
    # pemakai menyimpulkan "tidak ada piutang belum bayar" padahal ada.
    counts = {}
    for st in [o["value"] for o in AR_STATUS_OPTIONS]:
        counts[st] = await db.ar_invoices.count_documents({"org_id": org, "status": st})
    return {"data": serialize_doc(rows), "total": total, "counts": counts}


@router.get("/aging")
async def ar_aging(user: dict = Depends(require_permission("finance", "view"))):
    return {"data": await fe.ar_aging(user.get("org_id", ORG_ID))}


# --- Fase 26: titipan pelanggan (kelebihan bayar) ---
# CATATAN URUTAN RUTE: harus didaftarkan SEBELUM "/{deal_id}" agar tidak tertelan path param.
@router.get("/deposits")
async def list_deposits(user: dict = Depends(require_permission("finance", "view"))):
    """Daftar saldo titipan pelanggan + totalnya (dipakai KPI & panel Titipan)."""
    org = user.get("org_id", ORG_ID)
    rows = await db.customer_deposits.find({"org_id": org}, {"_id": 0}).sort("updated_at", -1).to_list(500)
    return {"data": serialize_doc(rows), "total": len(rows),
            "balance_total": sum(int(r.get("balance", 0) or 0) for r in rows)}


@router.post("/{deal_id}/deposit")
async def deposit_receive(deal_id: str, payload: DepositReceive,
                         user: dict = Depends(require_permission("finance", "create"))):
    """Terima titipan di muka (belum dialokasikan ke termin)."""
    try:
        res = await fe.receive_deposit(deal_id, payload.amount, payload.note,
                                      user.get("email"), user.get("org_id", ORG_ID))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"data": serialize_doc(res)}


@router.post("/{deal_id}/deposit/apply")
async def deposit_apply(deal_id: str, payload: DepositApply,
                        user: dict = Depends(require_permission("finance", "update"))):
    try:
        res = await fe.apply_deposit(deal_id, payload.amount, user.get("email"),
                                     user.get("org_id", ORG_ID), payload.note)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"data": serialize_doc(res)}


@router.post("/{deal_id}/deposit/refund")
async def deposit_refund(deal_id: str, payload: DepositRefund,
                         user: dict = Depends(require_permission("finance", "update"))):
    try:
        res = await fe.refund_deposit(deal_id, payload.amount, payload.note,
                                      user.get("email"), user.get("org_id", ORG_ID))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"data": serialize_doc(res)}


@router.get("/{deal_id}/spr-compare")
async def ar_spr_compare(deal_id: str, user: dict = Depends(require_permission("finance", "view"))):
    """SPR (angka saat terbit) vs tagihan Finance (AR + invoice biaya), baris per baris."""
    import spr_compare
    return {"data": serialize_doc(await spr_compare.compare(user.get("org_id", ORG_ID), deal_id))}


@router.get("/{deal_id}")
async def ar_detail(deal_id: str, user: dict = Depends(require_permission("finance", "view"))):
    org = user.get("org_id", ORG_ID)
    inv = await db.ar_invoices.find_one({"org_id": org, "deal_id": deal_id}, {"_id": 0})
    if not inv:
        raise HTTPException(status_code=404, detail="Jadwal AR tidak ditemukan untuk deal ini")
    receipts = await db.receipts.find({"org_id": org, "deal_id": deal_id}, {"_id": 0}).sort("created_at", -1).to_list(200)
    liab = await db.contract_liabilities.find_one({"org_id": org, "deal_id": deal_id}, {"_id": 0})
    rev = await db.revenue_recognitions.find_one({"org_id": org, "deal_id": deal_id}, {"_id": 0})
    dep = await db.customer_deposits.find_one({"org_id": org, "deal_id": deal_id}, {"_id": 0})
    cost_invoices = await db.cost_invoices.find({"org_id": org, "deal_id": deal_id}, {"_id": 0}).to_list(20)
    if not inv.get("breakdown"):
        deal = await db.deals.find_one({"id": deal_id}, {"_id": 0}) or {}
        inv["breakdown"] = fe.ar_breakdown(deal) if deal else None
    inv["addon_total"] = int(inv.get("addon_total") or 0)
    inv["unit_total"] = int(inv.get("unit_total") if inv.get("unit_total") is not None
                            else int(inv.get("total") or 0) - inv["addon_total"])
    inv["kpr_outstanding"] = fe.kpr_outstanding(inv)
    return {"data": serialize_doc(inv), "receipts": serialize_doc(receipts),
            "contract_liability": serialize_doc(liab), "revenue_recognition": serialize_doc(rev),
            "deposit": serialize_doc(dep), "cost_invoices": serialize_doc(cost_invoices)}


@router.post("/{deal_id}/schedule")
async def create_schedule(deal_id: str, payload: ArScheduleCreate,
                          user: dict = Depends(require_permission("finance", "create"))):
    org = user.get("org_id", ORG_ID)
    deal = await db.deals.find_one({"id": deal_id, "org_id": org}, {"_id": 0})
    if not deal:
        raise HTTPException(status_code=404, detail="Deal tidak ditemukan")
    try:
        inv = await fe.create_ar_for_deal(deal, scheme_id=payload.scheme_id, org_id=org,
                                          replace=True, actor=user.get("email"))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    # Skema/angka berubah setelah SPR ditandatangani → adendum otomatis (tidak menimpa SPR).
    import spr_compare
    adendum = await spr_compare.ensure_addendum(org, deal_id, user.get("email"),
                                                "skema pembayaran diganti oleh Finance")
    return {"data": serialize_doc(inv), "addendum": serialize_doc(adendum)}


@router.post("/receipts")
async def create_receipt(payload: ReceiptCreate,
                         user: dict = Depends(require_permission("finance", "create"))):
    if payload.amount <= 0:
        raise HTTPException(status_code=400, detail="Jumlah pembayaran harus lebih dari 0")
    try:
        res = await fe.apply_receipt(payload.deal_id, payload.amount, payload.method,
                                     payload.note, user.get("email"), user.get("org_id", ORG_ID),
                                     allow_overpay=payload.allow_overpay,
                                     cash_account_id=payload.cash_account_id,
                                     targets={a.item_id: a.amount for a in (payload.allocations or [])} or None)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"data": serialize_doc(res)}


@router.post("/{deal_id}/bast")
async def bast(deal_id: str, user: dict = Depends(require_permission("finance", "update"))):
    org = user.get("org_id", ORG_ID)
    deal = await db.deals.find_one({"id": deal_id, "org_id": org}, {"_id": 0})
    if not deal:
        raise HTTPException(status_code=404, detail="Deal tidak ditemukan")
    rev = await fe.recognize_revenue(deal, org_id=org, actor=user.get("email"))
    return {"data": serialize_doc(rev)}


# ----------------------- Bukti tertulis booking: invoice & kwitansi (PDF) -----------------------
def _idr(v) -> str:
    return f"Rp {int(v or 0):,}".replace(",", ".")


def _ref_label(group: str, value):
    try:
        return ref.label_of(group, value) or value or "-"
    except KeyError:
        return value or "-"


@router.delete("/receipts/{rid}")
async def delete_receipt(rid: str, reason: str = None,
                         user: dict = Depends(require_permission("finance", "update"))):
    """HAPUS satu pembayaran (kuitansi) + jurnalnya; alokasi termin/titipan dibalik. Akses penuh + alasan."""
    import force_delete as fd
    from rbac import audit_log
    org = user.get("org_id", ORG_ID)
    if not fd.may_force(user):
        raise HTTPException(status_code=403, detail="Hapus pembayaran hanya untuk Direksi/Super Admin.")
    if len((reason or "").strip()) < 10:
        raise HTTPException(status_code=400, detail="Hapus pembayaran wajib alasan (minimal 10 huruf).")
    rc = await db.receipts.find_one({"id": rid, "org_id": org}, {"_id": 0})
    if not rc:
        raise HTTPException(status_code=404, detail="Kuitansi tidak ditemukan.")
    out = await fd.delete_receipt(org, rc, user.get("email"))
    await audit_log(user, "force_delete", "receipts", rid, {"reason": reason.strip(), "receipt_no": rc.get("receipt_no"),
                                                            "amount": rc.get("amount"), "deal_id": rc.get("deal_id")})
    return {"data": out}


@router.get("/receipts/{rid}/pdf")
async def receipt_pdf(rid: str, user: dict = Depends(require_permission("finance", "view"))):
    """Kwitansi resmi (PDF ber-kop) untuk staf — bukti penerimaan booking fee/termin."""
    from fastapi.responses import Response
    import doc_layout as dl
    from pdf_utils import build_document_pdf
    from db import ORG_NAME
    org = user.get("org_id", ORG_ID)
    doc = await db.receipts.find_one({"id": rid, "org_id": org}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Kwitansi tidak ditemukan.")
    deal = await db.deals.find_one({"id": doc.get("deal_id"), "org_id": org}, {"_id": 0}) or {}
    alokasi = "; ".join(f"{a.get('label')}: {_idr(a.get('amount'))}"
                        for a in (doc.get("allocations") or [])) or "-"
    isi = "\n".join([
        f"Nomor kwitansi : {doc.get('receipt_no') or doc.get('id')}",
        f"Tanggal : {str(doc.get('created_at'))[:10]}",
        f"Diterima dari : {deal.get('lead_name') or deal.get('customer_name') or '-'}",
        f"Unit : {doc.get('unit_code') or deal.get('unit_code') or '-'}",
        f"Jumlah : {_idr(doc.get('amount'))}",
        f"Cara bayar : {_ref_label('payment_method', doc.get('method'))}",
        f"Dialokasikan ke : {alokasi}",
        f"Catatan : {doc.get('note') or '-'}",
        "",
        "Kwitansi ini sah sebagai bukti penerimaan pembayaran dan dicetak dari sistem.",
    ])
    layout = await dl.get_layout(org, "KWITANSI")
    pdf = build_document_pdf(title="Kwitansi Penerimaan Pembayaran",
                             doc_number=doc.get("receipt_no") or doc.get("id"),
                             content=isi, signatures=None, org_name=ORG_NAME, layout=layout,
                             script_context={"date": str(doc.get("created_at") or "")[:10]},
                             images=await dl.images(org, layout))
    name = str(doc.get("receipt_no") or "kwitansi").replace("/", "-")
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{name}.pdf"'})


@router.get("/{deal_id}/invoice/pdf")
async def invoice_pdf(deal_id: str, user: dict = Depends(require_permission("finance", "view"))):
    """Invoice/tagihan resmi (PDF ber-kop): jadwal termin + sudah dibayar + sisa."""
    from fastapi.responses import Response
    import doc_layout as dl
    from pdf_utils import build_table_pdf
    from db import ORG_NAME
    org = user.get("org_id", ORG_ID)
    inv = await db.ar_invoices.find_one({"org_id": org, "deal_id": deal_id}, {"_id": 0})
    if not inv:
        raise HTTPException(status_code=404, detail=(
            "Belum ada jadwal tagihan untuk transaksi ini — buat jadwal AR dulu."))
    deal = await db.deals.find_one({"id": deal_id, "org_id": org}, {"_id": 0}) or {}
    rows = []
    for it in inv.get("items", []):
        rows.append([
            it.get("label") or "-",
            str(it.get("due_date") or "-")[:10],
            _idr(it.get("amount")),
            _idr(it.get("paid_amount")),  # item = paid_amount; invoice = paid (FIELD_MAP.md)
            _ref_label("ar_status", it.get("status")),
        ])
    layout = await dl.get_layout(org, "INVOICE")  # DOC-02: tampilan invoice sendiri
    import doc_script as ds
    from datetime import datetime as _dt
    buyer = deal.get("lead_name") or deal.get("customer_name") or inv.get("lead_name")
    if not buyer and deal.get("lead_id"):
        lead = await db.leads.find_one({"id": deal["lead_id"]}, {"_id": 0, "name": 1}) or {}
        buyer = lead.get("name")
    buyer = buyer or "-"
    pending = sorted(str(it.get("due_date") or "")[:10] for it in inv.get("items", [])
                     if it.get("status") != "paid" and (it.get("amount") or 0) > (it.get("paid_amount") or 0))
    intro = await ds.intro_for(org, "INVOICE", {
        "date": _dt.now().strftime("%d-%m-%Y"), "org_name": ORG_NAME, "customer_name": buyer,
        "unit_code": deal.get("unit_code") or "-", "project_name": deal.get("project_name") or "",
        "total": _idr(inv.get("total")), "paid": _idr(inv.get("paid")),
        "outstanding": _idr(inv.get("outstanding")), "next_due": pending[0] if pending else "-",
        "status": _ref_label("ar_status", inv.get("status"))}, use_default=True)
    subtitle = " · ".join(filter(None, [
        f"Pembeli: {buyer}",
        f"Unit: {deal.get('unit_code') or '-'}",
        f"Status: {_ref_label('ar_status', inv.get('status'))}",
        f"Sudah dibayar: {_idr(inv.get('paid'))}",
        f"Sisa: {_idr(inv.get('outstanding'))}",
    ]))
    pdf = build_table_pdf(title="Invoice / Tagihan Pembayaran Unit", subtitle=subtitle,
                          columns=["Termin", "Jatuh tempo", "Jumlah", "Dibayar", "Status"],
                          rows=rows, total_row=["TOTAL", "", _idr(inv.get("total")),
                                                _idr(inv.get("paid")), ""],
                          org_name=ORG_NAME, layout=layout, intro=intro,
                          note="Invoice diterbitkan otomatis oleh SIPRO dari jadwal termin yang tercatat.",
                          images=await dl.images(org, layout))
    name = f"invoice-{(deal.get('unit_code') or deal_id).replace('/', '-')}"
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{name}.pdf"'})
