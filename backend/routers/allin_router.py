"""Fase 76-78 — master komponen biaya, skema all-in, penagihan biaya, skema pencairan KPR."""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

import allin_amend as am
import allin_engine as ae
import contracts_engine as ce
import kpr_disburse as kd
import kpr_engine as kprmod
from core_utils import new_id, now_iso, serialize_doc
from db import db, ORG_ID
from rbac import audit_log, require_permission

router = APIRouter(tags=["allin"])


class ComponentIn(BaseModel):
    code: Optional[str] = None
    name: Optional[str] = None
    calc_method: Optional[str] = None
    amount: Optional[int] = None
    pct: Optional[float] = None
    default_treatment: Optional[str] = None
    gl_expense: Optional[str] = None
    gl_liability: Optional[str] = None
    gl_ap: Optional[str] = None
    kpr_only: Optional[bool] = None
    is_active: Optional[bool] = None


class SchemeIn(BaseModel):
    code: Optional[str] = None
    name: Optional[str] = None
    note: Optional[str] = None
    project_ids: Optional[List[str]] = None
    unit_types: Optional[List[str]] = None
    items: Optional[List[dict]] = None
    is_active: Optional[bool] = None


class PayIn(BaseModel):
    amount: int
    method: Optional[str] = "transfer"
    note: Optional[str] = None


class DisburseIn(BaseModel):
    component_code: str
    amount: int
    payee: Optional[str] = None
    vendor: Optional[str] = None
    note: Optional[str] = None


class KprSchemeIn(BaseModel):
    code: Optional[str] = None
    bank: Optional[str] = None
    name: Optional[str] = None
    tolerance_pct: Optional[float] = None
    tranches: Optional[List[dict]] = None
    is_active: Optional[bool] = None


class AssignIn(BaseModel):
    scheme_id: str


class KprDisburseIn(BaseModel):
    tranche_code: Optional[str] = None
    amount: Optional[int] = None
    date: Optional[str] = None
    file_id: Optional[str] = None
    note: Optional[str] = None
    allow_deposit: bool = False
    reason: Optional[str] = None
    cash_account_id: Optional[str] = None


class CancelIn(BaseModel):
    reason: str


class AmendIn(BaseModel):
    scheme_id: Optional[str] = None
    items: Optional[List[dict]] = None
    reason: str


class DecideIn(BaseModel):
    approve: bool
    note: Optional[str] = None


def _org(user):
    return user.get("org_id", ORG_ID)


def _err(e):
    if isinstance(e, PermissionError):
        return HTTPException(status_code=403, detail=str(e))
    if isinstance(e, LookupError):
        return HTTPException(status_code=409, detail=str(e))
    return HTTPException(status_code=400, detail=str(e))


# ------------------------------------------------------------ master komponen
@router.get("/cost-components")
async def list_components(include_inactive: bool = False,
                          user: dict = Depends(require_permission("catalog", "view"))):
    org = _org(user)
    await ae.ensure_defaults(org)
    return {"data": serialize_doc(await ae.list_components(org, include_inactive)),
            "calc_methods": ae.CALC_METHODS, "treatments": ae.TREATMENTS}


@router.post("/cost-components")
async def create_component(p: ComponentIn, user: dict = Depends(require_permission("catalog", "update"))):
    org = _org(user)
    code = (p.code or "").strip().upper()
    if not code or not p.name:
        raise HTTPException(status_code=400, detail="Kode & nama komponen wajib.")
    if p.calc_method not in ae.CALC_METHODS or p.default_treatment not in ae.TREATMENTS:
        raise HTTPException(status_code=400, detail="Cara hitung / perlakuan tidak dikenal.")
    if await db.cost_components.find_one({"org_id": org, "code": code}):
        raise HTTPException(status_code=409, detail=f"Kode komponen {code} sudah dipakai.")
    ts = now_iso()
    doc = {"id": new_id(), "org_id": org, "code": code, "name": p.name, "calc_method": p.calc_method,
           "amount": int(p.amount or 0), "pct": float(p.pct or 0), "default_treatment": p.default_treatment,
           "gl_expense": p.gl_expense or ae.GL_BEBAN_PENJUALAN, "gl_liability": p.gl_liability or ae.GL_TITIPAN_BIAYA,
           "gl_ap": p.gl_ap or ae.GL_AP, "kpr_only": bool(p.kpr_only), "is_active": True,
           "created_at": ts, "updated_at": ts}
    await db.cost_components.insert_one(dict(doc))
    # Sinkron: komponen baru langsung masuk ke SEMUA skema all-in/exclude dengan perlakuan
    # bawaannya, supaya admin tidak perlu mengedit tiap skema satu per satu.
    synced = await db.allin_schemes.update_many(
        {"org_id": org, "items.component_code": {"$ne": code}},
        {"$push": {"items": {"component_code": code, "treatment": p.default_treatment,
                             "override_amount": None}},
         "$set": {"updated_at": ts}})
    await audit_log(user, "create", "cost_components", doc["id"],
                    {"code": code, "synced_schemes": synced.modified_count})
    doc.pop("_id", None)
    return {"data": doc, "synced_schemes": synced.modified_count}


@router.put("/cost-components/{cid}")
async def update_component(cid: str, p: ComponentIn, user: dict = Depends(require_permission("catalog", "update"))):
    org = _org(user)
    cur = await db.cost_components.find_one({"org_id": org, "id": cid}, {"_id": 0})
    if not cur:
        raise HTTPException(status_code=404, detail="Komponen tidak ditemukan.")
    upd = {k: v for k, v in p.model_dump(exclude_unset=True).items() if v is not None and k != "code"}
    upd["updated_at"] = now_iso()
    await db.cost_components.update_one({"id": cid}, {"$set": upd})
    await audit_log(user, "update", "cost_components", cid, {"fields": sorted(upd)})
    return {"data": serialize_doc(await db.cost_components.find_one({"id": cid}, {"_id": 0}))}


# ------------------------------------------------------------ skema all-in
@router.get("/allin-schemes")
async def list_schemes(project_id: str = None, unit_type: str = None, include_inactive: bool = False,
                       user: dict = Depends(require_permission("deals", "view_own"))):
    org = _org(user)
    await ae.ensure_defaults(org)
    return {"data": serialize_doc(await ae.list_schemes(org, project_id, unit_type, include_inactive))}


@router.get("/allin-schemes/{sid}/preview")
async def preview_scheme(sid: str, price: int, project_id: str = None, scheme: str = None,
                         user: dict = Depends(require_permission("deals", "view_own"))):
    try:
        return {"data": await ae.resolve_scheme(_org(user), sid, price, project_id, scheme)}
    except ValueError as e:
        raise _err(e)


@router.post("/allin-schemes")
async def create_scheme(p: SchemeIn, user: dict = Depends(require_permission("catalog", "update"))):
    org = _org(user)
    if not p.name or not p.items:
        raise HTTPException(status_code=400, detail="Nama & daftar komponen wajib.")
    for it in p.items:
        if it.get("treatment") not in ae.TREATMENTS:
            raise HTTPException(status_code=400, detail=f"Perlakuan '{it.get('treatment')}' tidak dikenal.")
    code = (p.code or p.name).strip().upper().replace(" ", "_")[:24]
    if await db.allin_schemes.find_one({"org_id": org, "code": code}):
        raise HTTPException(status_code=409, detail=f"Kode skema {code} sudah dipakai.")
    ts = now_iso()
    doc = {"id": new_id(), "org_id": org, "code": code, "name": p.name, "note": p.note or "",
           "project_ids": p.project_ids or [], "unit_types": p.unit_types or [], "items": p.items,
           "is_active": True, "created_at": ts, "updated_at": ts}
    await db.allin_schemes.insert_one(dict(doc))
    await audit_log(user, "create", "allin_schemes", doc["id"], {"code": code})
    doc.pop("_id", None)
    return {"data": doc}


@router.put("/allin-schemes/{sid}")
async def update_scheme(sid: str, p: SchemeIn, user: dict = Depends(require_permission("catalog", "update"))):
    org = _org(user)
    if not await db.allin_schemes.find_one({"org_id": org, "id": sid}):
        raise HTTPException(status_code=404, detail="Skema tidak ditemukan.")
    upd = {k: v for k, v in p.model_dump(exclude_unset=True).items() if v is not None and k != "code"}
    upd["updated_at"] = now_iso()
    await db.allin_schemes.update_one({"id": sid}, {"$set": upd})
    await audit_log(user, "update", "allin_schemes", sid, {"fields": sorted(upd)})
    return {"data": serialize_doc(await db.allin_schemes.find_one({"id": sid}, {"_id": 0}))}


@router.post("/allin-schemes/migrate-legacy")
async def migrate_legacy(user: dict = Depends(require_permission("catalog", "update"))):
    org = _org(user)
    await ae.ensure_defaults(org)
    return {"data": {"migrated": await ae.migrate_legacy_contracts(org)}}


# ------------------------------------------------------------ penagihan biaya per kontrak
async def _contract(cid: str, user: dict) -> dict:
    try:
        return await ce.get_raw(_org(user), cid)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/contracts/{cid}/costs-ledger")
async def costs_ledger(cid: str, user: dict = Depends(require_permission("contracts", "view_own"))):
    c = await _contract(cid, user)
    return {"data": serialize_doc(await ae.ledger(_org(user), c))}


@router.post("/contracts/{cid}/cost-invoices")
async def issue_cost_invoice(cid: str, user: dict = Depends(require_permission("finance", "create"))):
    c = await _contract(cid, user)
    try:
        return {"data": await ae.issue_cost_invoice(_org(user), c, user.get("email"))}
    except ValueError as e:
        raise _err(e)


@router.post("/cost-invoices/{iid}/pay")
async def pay_cost_invoice(iid: str, p: PayIn, user: dict = Depends(require_permission("finance", "create"))):
    try:
        return {"data": await ae.pay_cost_invoice(_org(user), iid, p.amount, p.method, p.note, user.get("email"))}
    except ValueError as e:
        raise _err(e)


@router.post("/contracts/{cid}/cost-disbursements")
async def disburse_titipan(cid: str, p: DisburseIn, user: dict = Depends(require_permission("finance", "create"))):
    c = await _contract(cid, user)
    try:
        return {"data": await ae.disburse_titipan(_org(user), c, p.component_code, p.amount, p.payee, p.note,
                                                  user.get("email"))}
    except ValueError as e:
        raise _err(e)


@router.post("/contracts/{cid}/cost-expenses")
async def developer_expense(cid: str, p: DisburseIn, user: dict = Depends(require_permission("finance", "create"))):
    c = await _contract(cid, user)
    try:
        return {"data": await ae.record_developer_expense(_org(user), c, p.component_code, p.amount,
                                                          p.vendor or p.payee, p.note, user.get("email"))}
    except ValueError as e:
        raise _err(e)


# ------------------------------------------------------------ skema pencairan KPR
@router.get("/kpr-disbursement-schemes")
async def list_kpr_schemes(include_inactive: bool = False,
                           user: dict = Depends(require_permission("financing", "view_own"))):
    org = _org(user)
    await kd.ensure_default(org)
    q = {"org_id": org} if include_inactive else {"org_id": org, "is_active": True}
    rows = await db.kpr_disbursement_schemes.find(q, {"_id": 0}).sort("name", 1).to_list(100)
    return {"data": serialize_doc(rows), "conditions": kd.CONDITIONS}


@router.post("/kpr-disbursement-schemes")
async def create_kpr_scheme(p: KprSchemeIn, user: dict = Depends(require_permission("catalog", "update"))):
    org = _org(user)
    try:
        doc = kd.validate_scheme(p.model_dump())
    except ValueError as e:
        raise _err(e)
    doc["code"] = doc["code"] or doc["name"].upper().replace(" ", "_")[:24]
    if await db.kpr_disbursement_schemes.find_one({"org_id": org, "code": doc["code"]}):
        raise HTTPException(status_code=409, detail=f"Kode skema {doc['code']} sudah dipakai.")
    doc.update({"id": new_id(), "org_id": org, "created_at": now_iso()})
    await db.kpr_disbursement_schemes.insert_one(dict(doc))
    await audit_log(user, "create", "kpr_disbursement_schemes", doc["id"], {"code": doc["code"]})
    doc.pop("_id", None)
    return {"data": doc}


@router.put("/kpr-disbursement-schemes/{sid}")
async def update_kpr_scheme(sid: str, p: KprSchemeIn, user: dict = Depends(require_permission("catalog", "update"))):
    org = _org(user)
    cur = await db.kpr_disbursement_schemes.find_one({"org_id": org, "id": sid}, {"_id": 0})
    if not cur:
        raise HTTPException(status_code=404, detail="Skema tidak ditemukan.")
    merged = {**cur, **{k: v for k, v in p.model_dump(exclude_unset=True).items() if v is not None}}
    try:
        doc = kd.validate_scheme(merged)
    except ValueError as e:
        raise _err(e)
    doc["code"] = cur["code"]
    doc["updated_at"] = now_iso()
    await db.kpr_disbursement_schemes.update_one({"id": sid}, {"$set": doc})
    await audit_log(user, "update", "kpr_disbursement_schemes", sid, {})
    return {"data": serialize_doc(await db.kpr_disbursement_schemes.find_one({"id": sid}, {"_id": 0}))}


async def _kpr_app(cid: str, user: dict):
    c = await _contract(cid, user)
    if c.get("scheme") != "kpr":
        raise HTTPException(status_code=400, detail="Kontrak ini bukan skema KPR.")
    app = await kprmod.ensure_kpr_app(_org(user), c, user.get("email"))
    return c, app


@router.post("/contracts/{cid}/kpr/disbursement-scheme")
async def assign_kpr_scheme(cid: str, p: AssignIn, user: dict = Depends(require_permission("financing", "update"))):
    c, app = await _kpr_app(cid, user)
    try:
        return {"data": serialize_doc(await kd.assign_scheme(_org(user), c, app, p.scheme_id, user.get("email")))}
    except ValueError as e:
        raise _err(e)


@router.post("/contracts/{cid}/kpr/disbursements")
async def kpr_disburse(cid: str, p: KprDisburseIn, user: dict = Depends(require_permission("financing", "update"))):
    c, app = await _kpr_app(cid, user)
    try:
        return {"data": serialize_doc(await kd.disburse(_org(user), c, app, p.model_dump(), user))}
    except (ValueError, LookupError, PermissionError) as e:
        raise _err(e)


@router.post("/contracts/{cid}/kpr/disbursements/{did}/cancel")
async def kpr_cancel(cid: str, did: str, p: CancelIn, user: dict = Depends(require_permission("financing", "update"))):
    c, app = await _kpr_app(cid, user)
    try:
        return {"data": serialize_doc(await kd.cancel(_org(user), c, app, did, p.reason, user))}
    except (ValueError, PermissionError) as e:
        raise _err(e)


# ------------------------------------------------------------ Fase 79: amandemen skema all-in
@router.get("/contracts/{cid}/allin-amendments")
async def list_amendments(cid: str, user: dict = Depends(require_permission("contracts", "view_own"))):
    await _contract(cid, user)
    return {"data": serialize_doc(await am.list_amendments(_org(user), cid))}


@router.post("/contracts/{cid}/allin-amendments")
async def request_amendment(cid: str, p: AmendIn, user: dict = Depends(require_permission("finance", "update"))):
    c = await _contract(cid, user)
    try:
        doc = await am.request_amendment(_org(user), c, p.model_dump(), user)
    except (ValueError, PermissionError) as e:
        raise _err(e)
    await audit_log(user, "request", "allin_amendments", doc["id"], {"contract_id": cid, "reason": p.reason})
    return {"data": doc}


@router.post("/allin-amendments/{aid}/decide")
async def decide_amendment(aid: str, p: DecideIn, user: dict = Depends(require_permission("finance", "approve"))):
    try:
        doc = await am.decide_amendment(_org(user), aid, p.approve, p.note, user)
    except (ValueError, PermissionError) as e:
        raise _err(e)
    await audit_log(user, "approve" if p.approve else "reject", "allin_amendments", aid, {"note": p.note})
    return {"data": serialize_doc(doc)}


# ------------------------------------------------------------ Fase 79: PDF invoice & kuitansi biaya
def _idr(v):
    return f"Rp {int(v or 0):,}".replace(",", ".")


@router.get("/cost-invoices/{iid}/pdf")
async def cost_invoice_pdf(iid: str, user: dict = Depends(require_permission("finance", "view"))):
    from fastapi.responses import Response
    import doc_layout as dl
    from pdf_utils import build_table_pdf
    from db import ORG_NAME
    org = _org(user)
    inv = await db.cost_invoices.find_one({"org_id": org, "id": iid}, {"_id": 0})
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice biaya tidak ditemukan.")
    c = await db.contracts.find_one({"id": inv["contract_id"], "org_id": org}, {"_id": 0, "costs": 1, "number": 1}) or {}
    comps = {x["code"]: x for x in (c.get("costs") or {}).get("components") or []}
    rows = [[it["name"], (comps.get(it["code"]) or {}).get("formula") or "-", "Ditagih ke pembeli (titipan)", _idr(it["amount"])]
            for it in inv.get("items") or []]
    layout = await dl.get_layout(org, "INVOICE")  # DOC-02: tampilan invoice sendiri
    import doc_script as ds
    intro = await ds.intro_for(org, "INVOICE", {
        "date": str(inv.get("created_at") or "")[:10], "org_name": (layout.get("brand") or {}).get("company_name") or ORG_NAME,
        "customer_name": inv.get("customer_name") or "-", "unit_code": inv.get("unit_code") or "-",
        "project_name": "", "total": _idr(inv.get("total")), "paid": _idr(inv.get("paid")),
        "outstanding": _idr(inv.get("outstanding")), "next_due": str(inv.get("due_date") or "belum ditetapkan")[:10],
        "status": inv.get("status") or "-"})
    subtitle = " · ".join([f"Pembeli: {inv.get('customer_name') or '-'}", f"Unit: {inv.get('unit_code') or '-'}",
                           f"Kontrak: {c.get('number') or '-'}", f"Skema: {(c.get('costs') or {}).get('scheme_name') or '-'}",
                           f"Status: {inv.get('status')}", f"Sudah dibayar: {_idr(inv.get('paid'))}",
                           f"Sisa: {_idr(inv.get('outstanding'))}",
                           "Biaya ini DI LUAR harga unit — dana dititipkan untuk disalurkan ke notaris/BPN."])
    pdf = build_table_pdf(title=f"Invoice Biaya Transaksi {inv['number']}", subtitle=subtitle,
                          columns=["Komponen", "Dasar hitung", "Perlakuan", "Jumlah"], rows=rows,
                          total_row=["TOTAL", "", "", _idr(inv.get("total"))],
                          org_name=ORG_NAME, layout=layout, intro=intro, images=await dl.images(org, layout))
    name = inv["number"].replace("/", "-")
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{name}.pdf"'})


@router.get("/cost-receipts/{rid}/pdf")
async def cost_receipt_pdf(rid: str, user: dict = Depends(require_permission("finance", "view"))):
    from fastapi.responses import Response
    import doc_layout as dl
    from pdf_utils import build_document_pdf
    from db import ORG_NAME
    org = _org(user)
    rc = await db.cost_receipts.find_one({"org_id": org, "id": rid}, {"_id": 0})
    if not rc:
        raise HTTPException(status_code=404, detail="Kuitansi biaya tidak ditemukan.")
    isi = "\n".join([
        f"Nomor kuitansi : {rc['receipt_no']}", f"Tanggal : {str(rc.get('created_at'))[:10]}",
        f"Diterima dari : {rc.get('customer_name') or '-'}", f"Unit : {rc.get('unit_code') or '-'}",
        f"Untuk invoice biaya : {rc.get('invoice_no') or '-'}", f"Jumlah : {_idr(rc.get('amount'))}",
        f"Cara bayar : {rc.get('method') or '-'}", f"Catatan : {rc.get('note') or '-'}", "",
        "Dana ini adalah TITIPAN biaya BPHTB/notaris/bank di luar harga unit, akan disalurkan ke "
        "notaris/BPN atas nama pembeli, dan BUKAN pembayaran harga unit.",
        "Kuitansi ini sah sebagai bukti penerimaan dan dicetak dari sistem."])
    layout = await dl.get_layout(org, "KWITANSI")
    pdf = build_document_pdf(title="Kwitansi Penerimaan Titipan Biaya", doc_number=rc["receipt_no"], content=isi,
                             signatures=None, org_name=ORG_NAME, layout=layout, script_context={"date": str(rc.get("created_at") or "")[:10]}, images=await dl.images(org, layout))
    name = rc["receipt_no"].replace("/", "-")
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{name}.pdf"'})


# ------------------------------------------------------------ Fase 79: pengingat tahap cair
@router.get("/kpr/tranche-reminders")
async def tranche_reminders(user: dict = Depends(require_permission("financing", "view_own"))):
    return {"data": serialize_doc(await am.ready_tranches(_org(user)))}


@router.post("/kpr/tranche-reminders/run")
async def run_tranche_reminders(user: dict = Depends(require_permission("finance", "update"))):
    return {"data": serialize_doc(await am.run_tranche_reminders(_org(user)))}
