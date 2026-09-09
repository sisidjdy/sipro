"""ROUTER KONTRAK PEMBELI (Fase 53) — prefix `/contracts` + konversi deal → pembeli.

Pintu masuk untuk tiga hal yang sebelumnya tidak punya pintu sama sekali:
  1. **Menjadikan lead sebagai PEMBELI** (`POST /deals/{id}/convert`) — sebelum ini tidak ada
     satu endpoint pun yang membuat `customers` dari sebuah deal.
  2. **Kontrak**: rincian komponen biaya, rencana bayar, tahap legal (termasuk **akad
     kredit**), dan sub-alur KPR dengan gerbang bukti.
  3. **Dokumen owner**: menerbitkan SPR (3 varian) & SPKT dari template asli owner, lalu
     mencetaknya (PDF lewat `/documents/{id}/pdf` yang sudah ada).

Pemisahan tugas yang dipaksakan di sini:
  * membuat pembeli & kontrak = `customers:create` (sales/marketing/manajer);
  * mengisi komponen biaya & mengaktifkan kontrak = `contracts:update` (termasuk Keuangan,
    karena angka BPHTB/notaris/bank memang miliknya);
  * memajukan tahap legal = `contracts:manage`;
  * tahap KPR = `financing:update` (tim yang mengurus bank), penolakan bank juga;
  * menerbitkan dokumen = `documents:create`.
"""
from fastapi import APIRouter, Depends, HTTPException

import contracts_engine as ce
import customer_convert as cc
import docgen
import kpr_engine as kpr
from core_utils import parse_pagination, serialize_doc
from db import ORG_ID, db
from models_p53 import (ContractCostsIn, ContractSchemeIn, ConvertToCustomerIn,
                       DocGenerateIn, KprRejectIn, KprStageIn, LegalAdvanceIn)
from rbac import audit_log, is_scoped_sales, require_permission

router = APIRouter(tags=["contracts"])


def _org(user: dict) -> str:
    return user.get("org_id", ORG_ID)


async def _deal_scoped(deal_id: str, user: dict) -> dict:
    d = await db.deals.find_one({"id": deal_id, "org_id": _org(user)}, {"_id": 0})
    if not d:
        raise HTTPException(status_code=404, detail="Deal tidak ditemukan")
    if is_scoped_sales(user) and d.get("assigned_to") != user.get("email"):
        raise HTTPException(status_code=403, detail="Akses ditolak: bukan deal Anda")
    return d


async def _contract_scoped(contract_id: str, user: dict) -> dict:
    try:
        c = await ce.get_raw(_org(user), contract_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    if is_scoped_sales(user) and c.get("assigned_to") != user.get("email"):
        raise HTTPException(status_code=403, detail="Akses ditolak: bukan kontrak Anda")
    return c


# ============================================================ konversi lead → pembeli
@router.get("/deals/{deal_id}/convert-preview")
async def convert_preview(deal_id: str,
                          user: dict = Depends(require_permission("deals", "view"))):
    """Apa yang akan terjadi bila deal ini dijadikan pembeli — atau sebab belum boleh."""
    await _deal_scoped(deal_id, user)
    try:
        return {"data": serialize_doc(await cc.preview(_org(user), deal_id))}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/deals/{deal_id}/convert")
async def convert_deal(deal_id: str, payload: ConvertToCustomerIn,
                       user: dict = Depends(require_permission("customers", "create"))):
    """Jadikan lead PEMBELI: `customers` + `contracts` (+ pengajuan KPR bila skema KPR)."""
    await _deal_scoped(deal_id, user)
    try:
        out = await cc.convert(_org(user), deal_id, user.get("email"),
                               payload.model_dump(exclude_none=True))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if out.get("created"):
        await audit_log(user, "create", "contract", (out.get("contract") or {}).get("id"),
                        {"deal_id": deal_id,
                         "customer_id": (out.get("customer") or {}).get("id")})
    return {"data": serialize_doc(out)}


# ============================================================ kontrak
@router.get("/contracts")
async def list_contracts(customer_id: str = None, deal_id: str = None, scheme: str = None,
                        state: str = None, legal_stage: str = None, q: str = None,
                        skip: int = 0, limit: int = 50,
                        user: dict = Depends(require_permission("contracts", "view"))):
    skip, limit = parse_pagination(skip, limit)
    out = await ce.listing(_org(user), customer_id=customer_id, deal_id=deal_id,
                           scheme=scheme, state=state, legal_stage=legal_stage, q=q,
                           skip=skip, limit=limit)
    tersembunyi = 0
    if is_scoped_sales(user):
        milik = [r for r in out["data"] if r.get("assigned_to") == user.get("email")]
        tersembunyi = len(out["data"]) - len(milik)
        out["data"] = milik
        out["total"] = len(milik)
    resp = {"data": serialize_doc(out["data"]), "total": out["total"],
            "counts": out["counts"]}
    if tersembunyi and not out["data"]:
        # KEJUJURAN LINGKUP DATA (temuan uji peramban Fase 56). Tanpa kalimat ini panel
        # kontrak menulis "Belum ada kontrak — kontrak lahir saat lead dijadikan PEMBELI"
        # kepada sales yang membuka pembeli rekannya: layar menyatakan "tidak ada" untuk
        # sesuatu yang ADA tetapi bukan lingkupnya. Kalimat ini menyebut SEBAB tanpa
        # membocorkan isi kontrak (nomor, nilai, maupun nama pemegangnya).
        resp["reason_code"] = "di_luar_lingkup"
        resp["reason"] = (
            f"Ada {tersembunyi} kontrak pada pembeli ini, tetapi lead-nya dipegang rekan "
            "lain sehingga di luar lingkup data Anda. Minta manajer sales membukanya bila "
            "Anda memang perlu membacanya." if customer_id or deal_id else
            f"{tersembunyi} kontrak tidak ditampilkan karena berada di luar lingkup data "
            "Anda (hanya lead yang Anda pegang).")
    return resp


@router.get("/contracts/by-deal/{deal_id}")
async def contract_by_deal(deal_id: str,
                           user: dict = Depends(require_permission("contracts", "view"))):
    """Kontrak milik satu deal — `null` bila lead-nya belum menjadi pembeli (jujur)."""
    await _deal_scoped(deal_id, user)
    c = await db.contracts.find_one({"org_id": _org(user), "deal_id": deal_id}, {"_id": 0})
    if not c:
        return {"data": None,
                "reason": ("Deal ini belum menjadi pembeli, jadi belum ada kontrak. "
                           "Pakai tombol 'Jadikan Pembeli' setelah booking dikonfirmasi.")}
    return {"data": serialize_doc(await ce.enrich(_org(user), c))}


@router.get("/contracts/{contract_id}")
async def get_contract(contract_id: str,
                       user: dict = Depends(require_permission("contracts", "view"))):
    c = await _contract_scoped(contract_id, user)
    return {"data": serialize_doc(await ce.enrich(_org(user), c))}


@router.post("/contracts/{contract_id}/costs")
async def set_costs(contract_id: str, payload: ContractCostsIn,
                    user: dict = Depends(require_permission("contracts", "update"))):
    """Isi komponen biaya. Kirim -1 untuk MENGOSONGKAN kembali (bukan 0)."""
    await _contract_scoped(contract_id, user)
    try:
        c = await ce.set_costs(_org(user), contract_id,
                               payload.model_dump(exclude_none=True), user.get("email"))
    except LookupError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit_log(user, "update", "contract", contract_id,
                    payload.model_dump(exclude_none=True))
    return {"data": serialize_doc(await ce.enrich(_org(user), c))}


@router.post("/contracts/{contract_id}/scheme")
async def set_scheme(contract_id: str, payload: ContractSchemeIn,
                     user: dict = Depends(require_permission("contracts", "update"))):
    await _contract_scoped(contract_id, user)
    try:
        c = await ce.set_scheme(_org(user), contract_id, payload.scheme,
                               user.get("email"), payload.reason)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit_log(user, "update", "contract", contract_id, {"scheme": payload.scheme})
    return {"data": serialize_doc(await ce.enrich(_org(user), c))}


@router.post("/contracts/{contract_id}/activate")
async def activate_contract(contract_id: str,
                            user: dict = Depends(require_permission("contracts", "update"))):
    """Aktifkan kontrak: termin AR mengikuti SKEMA KONTRAK (bukan skema bawaan keuangan)."""
    await _contract_scoped(contract_id, user)
    try:
        c = await ce.activate(_org(user), contract_id, user.get("email"))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit_log(user, "update", "contract", contract_id, {"action": "activate"})
    return {"data": serialize_doc(await ce.enrich(_org(user), c))}


@router.post("/contracts/{contract_id}/legal/{stage}")
async def legal_advance(contract_id: str, stage: str, payload: LegalAdvanceIn,
                        user: dict = Depends(require_permission("contracts", "manage"))):
    """Majukan tahap legal (ppjb / akad_kredit / pelunasan / bast / ajb / sertifikat)."""
    await _contract_scoped(contract_id, user)
    try:
        c = await ce.legal_advance(_org(user), contract_id, stage,
                                   payload.model_dump(exclude_none=True),
                                   user.get("email"))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit_log(user, "update", "contract", contract_id, {"legal_stage": stage})
    return {"data": serialize_doc(await ce.enrich(_org(user), c))}


# ============================================================ sub-alur KPR
@router.get("/contracts/{contract_id}/kpr")
async def get_kpr(contract_id: str,
                  user: dict = Depends(require_permission("financing", "view"))):
    c = await _contract_scoped(contract_id, user)
    return {"data": serialize_doc(await kpr.kpr_of(_org(user), c))}


@router.post("/contracts/{contract_id}/kpr/stage/{stage}")
async def kpr_stage(contract_id: str, stage: str, payload: KprStageIn,
                    user: dict = Depends(require_permission("financing", "update"))):
    """Majukan tahap KPR. SP3K wajib berkas + plafon; akad wajib SP3K & kelebihan tanah lunas."""
    c = await _contract_scoped(contract_id, user)
    try:
        app = await kpr.kpr_advance(_org(user), contract_id, stage,
                                    payload.model_dump(exclude_none=True),
                                    user.get("email"), user=user)
    except LookupError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit_log(user, "update", "financing", app.get("id"), {"kpr_stage": stage,
                                                                 "contract_id": c["id"]})
    return {"data": serialize_doc(app)}


@router.post("/contracts/{contract_id}/kpr/reject")
async def kpr_reject(contract_id: str, payload: KprRejectIn,
                     user: dict = Depends(require_permission("financing", "update"))):
    """Bank menolak: tahap `ditolak` + usulan refund booking fee sesuai ketentuan SPR."""
    await _contract_scoped(contract_id, user)
    try:
        app = await kpr.kpr_reject(_org(user), contract_id, payload.reason,
                                   payload.file_id, user.get("email"))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit_log(user, "update", "financing", app.get("id"),
                    {"kpr_stage": "ditolak", "reason": payload.reason})
    return {"data": serialize_doc(app)}


# ============================================================ dokumen owner (SPR/SPKT)
@router.get("/contracts/{contract_id}/documents/available")
async def available_documents(contract_id: str,
                              user: dict = Depends(require_permission("documents", "view"))):
    """Template mana yang boleh diterbitkan untuk kontrak ini + sebab bila tidak boleh."""
    c = await _contract_scoped(contract_id, user)
    return {"data": serialize_doc(await docgen.applicable(_org(user), c)),
            "scheme": c.get("scheme"),
            "recommended": docgen.TEMPLATES.get(
                ce.SCHEME_DOC.get(c.get("scheme")) or "", (None,))[0]
            if ce.SCHEME_DOC.get(c.get("scheme")) else None,
            "recommended_code": ce.SCHEME_DOC.get(c.get("scheme"))}


@router.post("/contracts/{contract_id}/documents")
async def generate_document(contract_id: str, payload: DocGenerateIn,
                            user: dict = Depends(require_permission("documents", "create"))):
    """Terbitkan dokumen dari template owner. Angka HANYA dari kontrak (Dok 27 §5.1)."""
    c = await _contract_scoped(contract_id, user)
    code = payload.template_code or ce.SCHEME_DOC.get(c.get("scheme"))
    if not code:
        raise HTTPException(status_code=400,
                            detail="Skema kontrak belum ditetapkan — pilih skema dulu.")
    try:
        doc = await docgen.generate(_org(user), c, code, user, payload.note)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit_log(user, "create", "document", doc["id"],
                    {"template_code": code, "contract_id": contract_id,
                     "doc_number": doc["doc_number"]})
    return {"data": serialize_doc(doc)}


@router.get("/document-templates")
async def list_templates(user: dict = Depends(require_permission("documents", "view"))):
    """Daftar template dokumen (termasuk 4 template asli owner) — dipakai layar Dokumen."""
    rows = await db.document_templates.find(
        {"org_id": _org(user)}, {"_id": 0, "content": 0}
    ).sort("code", 1).to_list(100)
    return {"data": serialize_doc(rows)}
