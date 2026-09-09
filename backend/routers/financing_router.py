"""Financing (KPR): pengajuan bank + plafon/DP/tenor + status SLIK/BI +
pencairan bertahap terkait milestone/progres konstruksi. EPIC 1.5.

Worksheet-level (belum integrasi bank nyata); provider bank/SLIK dapat diaktifkan
via env di kemudian hari. Semua ber-org_id + RBAC.
"""
from fastapi import APIRouter, Depends, HTTPException

from db import db, ORG_ID
from core_utils import new_id, now_iso, serialize_doc, parse_pagination
from rbac import require_permission
from engine import add_activity, create_notification, emit
import finance_engine as fe
import slik as slik_engine
from models import FinancingCreate, FinancingUpdate, SlikUpdate, DisbursementCreate

router = APIRouter(prefix="/financing", tags=["financing"])


async def _deal_ctx(deal_id: str, org: str):
    deal = await db.deals.find_one({"id": deal_id, "org_id": org}, {"_id": 0})
    if not deal:
        raise HTTPException(status_code=404, detail="Deal tidak ditemukan")
    unit = await db.units.find_one({"id": deal.get("unit_id")}, {"_id": 0}) or {}
    return deal, unit


@router.get("")
async def list_financing(deal_id: str = None, customer_id: str = None, skip: int = 0, limit: int = 50,
                         user: dict = Depends(require_permission("financing", "view"))):
    skip, limit = parse_pagination(skip, limit)
    query = {"org_id": user.get("org_id", ORG_ID)}
    if deal_id:
        query["deal_id"] = deal_id
    if customer_id:
        query["customer_id"] = customer_id
    total = await db.financing_apps.count_documents(query)
    rows = await db.financing_apps.find(query, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    return {"data": serialize_doc(rows), "total": total}


@router.post("")
async def create_financing(payload: FinancingCreate,
                           user: dict = Depends(require_permission("financing", "create"))):
    """Buat pengajuan KPR.

    Fase 30a: hasil PRA-SKRINING BI/SLIK dari lead ikut menempel (`slik_prescreen`) supaya
    petugas KPR tidak mengulang pemeriksaan dari nol. Yang TIDAK dilakukan (sengaja, demi
    kejujuran laporan): pra-skrining tidak dipakai sebagai `slik_status` resmi dan tidak
    otomatis menyetujui pengajuan — hasil resmi tetap harus datang dari bank.
    """
    org = user.get("org_id", ORG_ID)
    deal, unit = await _deal_ctx(payload.deal_id, org)
    pre = await slik_engine.prescreen_for_deal(deal)
    ts = now_iso()
    doc = {
        "id": new_id(), "org_id": org, "deal_id": payload.deal_id,
        "customer_id": payload.customer_id, "unit_id": deal.get("unit_id"),
        "bank_name": payload.bank_name, "plafon": int(payload.plafon or 0),
        "dp_amount": int(payload.dp_amount or 0), "tenor_months": int(payload.tenor_months or 0),
        "interest_rate_pct": float(payload.interest_rate_pct or 0),
        "status": "submitted", "slik_status": "pending",
        "slik_note": slik_engine.financing_note(pre),
        "slik_prescreen": pre,
        "disbursements": [], "disbursed_total": 0,
        "assigned_to": deal.get("assigned_to"), "created_by": user.get("email"),
        "created_at": ts, "updated_at": ts,
    }
    await db.financing_apps.insert_one(doc)
    await add_activity(entity_type="deal", entity_id=payload.deal_id, type="financing",
                       body=f"Pengajuan KPR {payload.bank_name} plafon Rp {doc['plafon']:,} dibuat."
                            + (f" {doc['slik_note']}" if doc["slik_note"] else ""),
                       actor=user.get("email"), org_id=org)
    warning = None
    if pre and pre.get("status") != "clear":
        warning = (
            "Pra-skrining BI/SLIK lead berstatus "
            f"{pre.get('label')} — pengajuan tetap dibuat, tetapi "
            + ("peluang disetujui bank rendah. Pertimbangkan skema tunai bertahap "
               "atau ganti bank." if not pre.get("passing")
               else "bank kemungkinan meminta dokumen tambahan/penjamin. Siapkan "
                    "penjelasan riwayat kredit sebelum berkas dikirim."))
        await create_notification(
            user_email=deal.get("assigned_to") or user.get("email"),
            title="Perhatian: pra-skrining SLIK perlu tindak lanjut",
            body=warning[:180], type="financing",
            related_entity_type="deal", related_entity_id=payload.deal_id, org_id=org)
    doc.pop("_id", None)
    return {"data": serialize_doc(doc), "prescreen": pre, "prescreen_warning": warning}


async def _get(fid: str, org: str) -> dict:
    f = await db.financing_apps.find_one({"id": fid, "org_id": org}, {"_id": 0})
    if not f:
        raise HTTPException(status_code=404, detail="Pengajuan KPR tidak ditemukan")
    return f


@router.get("/{fid}")
async def get_financing(fid: str, user: dict = Depends(require_permission("financing", "view"))):
    return {"data": serialize_doc(await _get(fid, user.get("org_id", ORG_ID)))}


@router.put("/{fid}")
async def update_financing(fid: str, payload: FinancingUpdate,
                           user: dict = Depends(require_permission("financing", "update"))):
    org = user.get("org_id", ORG_ID)
    await _get(fid, org)
    # status divalidasi SSOT di models.FinancingUpdate (reference.financing_status)
    data = {k: v for k, v in payload.model_dump().items() if v is not None}
    for money in ("plafon", "dp_amount"):
        if money in data:
            data[money] = int(data[money])
    data["updated_at"] = now_iso()
    await db.financing_apps.update_one({"id": fid, "org_id": org}, {"$set": data})
    return {"data": serialize_doc(await _get(fid, org))}


@router.post("/{fid}/slik")
async def update_slik(fid: str, payload: SlikUpdate,
                      user: dict = Depends(require_permission("financing", "update"))):
    org = user.get("org_id", ORG_ID)
    f = await _get(fid, org)
    status = payload.slik_status
    if status not in {"pending", "clear", "flagged", "rejected"}:
        raise HTTPException(status_code=400, detail="Status SLIK tidak valid.")
    new_status = f.get("status")
    if status == "clear":
        new_status = "approved"
    elif status == "rejected":
        new_status = "rejected"
    await db.financing_apps.update_one({"id": fid, "org_id": org}, {"$set": {
        "slik_status": status, "slik_note": payload.note, "status": new_status,
        "updated_at": now_iso()}})
    await add_activity(entity_type="deal", entity_id=f.get("deal_id"), type="financing",
                       body=f"Hasil BI/SLIK check: {status}. Status KPR -> {new_status}.",
                       actor=user.get("email"), org_id=org)
    return {"data": serialize_doc(await _get(fid, org))}


@router.post("/{fid}/disburse")
async def disburse(fid: str, payload: DisbursementCreate,
                   user: dict = Depends(require_permission("financing", "approve"))):
    org = user.get("org_id", ORG_ID)
    f = await _get(fid, org)
    if f.get("status") not in ("approved", "disbursing"):
        raise HTTPException(status_code=400,
                            detail="Pencairan hanya untuk pengajuan yang sudah disetujui (SLIK clear).")
    _deal, unit = await _deal_ctx(f.get("deal_id"), org)
    progress = int(unit.get("construction_progress") or 0)
    if payload.min_progress and progress < int(payload.min_progress):
        raise HTTPException(status_code=400,
                            detail=f"Milestone belum tercapai: progres konstruksi {progress}% < {payload.min_progress}%.")
    amount = int(payload.amount or 0)
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Nominal pencairan harus > 0.")
    # Kebenaran uang: pencairan bank = kas masuk = piutang berkurang. Tidak ada lagi jalur
    # "catat pencairan tanpa AR" — itu membuat Keuangan & layar pelanggan berbeda angka.
    if not await db.ar_invoices.find_one({"org_id": org, "deal_id": f.get("deal_id")}, {"_id": 0, "id": 1}):
        raise HTTPException(status_code=400, detail=(
            "Jadwal tagihan (AR) unit ini belum terbit — aktifkan kontrak / konfirmasi booking dulu. "
            "Pencairan KPR tidak boleh dicatat tanpa mengurangi piutang."))
    disbursed = int(f.get("disbursed_total") or 0) + amount
    if disbursed > int(f.get("plafon") or 0):
        raise HTTPException(status_code=400, detail="Total pencairan melebihi plafon.")
    ts = now_iso()
    entry = {"id": new_id(), "amount": amount, "milestone": payload.milestone,
             "progress_at": progress, "note": payload.note, "created_by": user.get("email"),
             "created_at": ts}
    status = "done" if disbursed >= int(f.get("plafon") or 0) else "disbursing"
    await db.financing_apps.update_one({"id": fid, "org_id": org}, {
        "$push": {"disbursements": entry},
        "$set": {"disbursed_total": disbursed, "status": status, "updated_at": ts}})
    # Fase 42: pencairan PERTAMA hanya mungkin terjadi setelah AKAD KREDIT ditandatangani —
    # bank tidak mencairkan tanpa akad. Karena itu peristiwa ini dipakai sebagai bukti
    # `kpr.akad` (pemicu hak fee mitra `akad_kredit`). Tidak ada event karangan: yang
    # dijadikan bukti adalah pencairan yang benar-benar tercatat.
    if not (f.get("disbursements") or []):
        await emit("kpr.akad", "financing", fid,
                   {"deal_id": f.get("deal_id"), "bank": f.get("bank_name"),
                    "amount": amount}, org_id=org)
    # Fase 26 (kebenaran uang): dana KPR yang cair adalah KAS MASUK untuk pengembang dan
    # harus mengurangi piutang pembeli. Dulu pencairan hanya dicatat di dokumen KPR
    # sehingga AR tetap utuh & tidak ada jurnal apa pun (uang tak terlihat di GL).
    booking = {"booked": False, "reason": "gagal dibukukan"}
    if True:  # selalu dibukukan ke AR (book_to_ar lama diabaikan — kebenaran uang)
        try:
            res = await fe.apply_receipt(f.get("deal_id"), amount, "kpr",
                                         f"Pencairan KPR {f.get('bank_name')} — {payload.milestone}",
                                         user.get("email"), org, allow_overpay=True,
                                         cash_account_id=payload.cash_account_id)
            booking = {"booked": True, "applied": res["receipt"]["applied"],
                       "deposit_amount": res["receipt"]["deposit_amount"],
                       "outstanding": res["invoice"]["outstanding"],
                       "paid_off": res["paid_off"]}
            await db.financing_apps.update_one(
                {"id": fid, "org_id": org, "disbursements.id": entry["id"]},
                {"$set": {"disbursements.$.receipt_id": res["receipt"]["id"]}})
        except ValueError as e:
            booking = {"booked": False, "reason": str(e)}
    await create_notification(user_email=f.get("assigned_to") or user.get("email"),
                              title="Pencairan KPR",
                              body=f"Pencairan Rp {amount:,} ({payload.milestone}) tercatat.",
                              type="finance", org_id=org)
    return {"data": serialize_doc(await _get(fid, org)), "ar_booking": booking}
