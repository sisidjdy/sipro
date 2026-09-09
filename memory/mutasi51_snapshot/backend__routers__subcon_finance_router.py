"""subcon_finance_router.py — uang muka, potongan, retensi & evaluasi subkon (Fase 48C/48D).

Rute (prefix `/subcon`, tanpa pintu sidebar baru — dipakai tab di halaman Subkontraktor):
  GET/POST  /advances                        ajukan & lihat uang muka
  POST      /advances/{aid}/decision         setujui/tolak (manajer keuangan)
  POST      /advances/{aid}/pay              bayar (jurnal Dr 1-1800 / Cr 1-1200)
  GET/POST  /deductions                      potongan termin (uang muka/denda/bon material)
  POST      /deductions/{did}/cancel         batalkan potongan (alasan wajib)
  GET       /retentions                      daftar retensi + gerbang pencairan
  POST      /retentions/{rid}/request-release ajukan pencairan (lapangan/PM)
  POST      /retentions/{rid}/release        cairkan (manajer keuangan)
  GET       /evaluations                     rapor subkon berbukti
  POST      /subcontractors/{sid}/assessment penilaian manusia

Pemisahan tugas yang DISENGAJA: yang MENGAJUKAN tidak boleh MEMUTUSKAN. Uang muka & pencairan
retensi hanya boleh diputus `finance_manager` (aksi `manage`) — finance biasa cukup melihat.
"""
from fastapi import APIRouter, Depends, HTTPException

import logging

import offline_intake as intake
import subcon_finance as sf
import vendor_engine as ve
from db import db, ORG_ID
from core_utils import serialize_doc
from engine import add_activity, create_notification
from models_p48 import AdvanceDecisionIn, AdvanceIn, AdvancePayIn, AssessmentIn, DeductionIn, ReasonIn
from models_p51 import RetentionReleaseIn, RetentionWaiveIn
from rbac import require_permission, assert_project_access, project_query, audit_log

logger = logging.getLogger("sipro.subcon_finance")

router = APIRouter(prefix="/subcon", tags=["subcon-finance"])
SCOPED = ("project_manager", "site_engineer")


async def _scope(user: dict):
    if user.get("role") not in SCOPED:
        return None
    projs = await db.projects.find(project_query(user, {}), {"_id": 0, "id": 1}).to_list(500)
    return [p["id"] for p in projs]


async def _spk_or_404(org: str, spk_id: str, user: dict) -> dict:
    spk = await db.spk.find_one({"id": spk_id, "org_id": org}, {"_id": 0})
    if not spk:
        raise HTTPException(status_code=404, detail="SPK tidak ditemukan.")
    await assert_project_access(spk["project_id"], user)
    return spk


async def _doc_or_404(coll, org: str, did: str, user: dict, what: str) -> dict:
    doc = await coll.find_one({"id": did, "org_id": org}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail=f"{what} tidak ditemukan.")
    await assert_project_access(doc["project_id"], user)
    return doc


# ------------------------------------------------------------------ uang muka
@router.get("/advances")
async def list_advances(spk_id: str = None,
                        user: dict = Depends(require_permission("subcon_finance", "view"))):
    org = user.get("org_id", ORG_ID)
    out = await sf.list_advances(org, spk_id, await _scope(user))
    return {"data": serialize_doc(out["rows"]), "total": len(out["rows"]),
            "summary": out["summary"]}


@router.post("/advances")
async def create_advance(payload: AdvanceIn,
                        user: dict = Depends(require_permission("subcon_finance", "create"))):
    org = user.get("org_id", ORG_ID)
    spk = await _spk_or_404(org, payload.spk_id, user)
    try:
        doc = await sf.create_advance(org, spk, payload.model_dump(), user.get("email"))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit_log(user, "create", "subcon_advance", doc["id"],
                    {"spk": spk.get("spk_number"), "amount": doc["amount"]})
    await add_activity(entity_type="project", entity_id=spk["project_id"], type="system",
                       body=(f"Uang muka {doc['advance_number']} diajukan untuk SPK "
                             f"{spk.get('spk_number')}: Rp {doc['amount']:,}. {doc['reason']}"),
                       actor=user.get("email"), org_id=org)
    return {"data": serialize_doc(doc)}


@router.post("/advances/{aid}/decision")
async def decide_advance(aid: str, payload: AdvanceDecisionIn,
                        user: dict = Depends(require_permission("subcon_finance", "manage"))):
    org = user.get("org_id", ORG_ID)
    adv = await _doc_or_404(db.subcon_advances, org, aid, user, "Uang muka")
    try:
        doc = await sf.decide_advance(org, adv, payload.approve, payload.reason, user.get("email"))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit_log(user, "approve" if payload.approve else "reject", "subcon_advance", aid,
                    {"reason": payload.reason})
    await create_notification(
        user_email=adv.get("created_by"),
        title="Uang muka " + ("disetujui" if payload.approve else "ditolak"),
        body=f"{adv.get('advance_number')} Rp {adv['amount']:,} — {payload.reason}",
        type="procurement", related_entity_type="project",
        related_entity_id=adv["project_id"], org_id=org)
    return {"data": serialize_doc(doc)}


@router.post("/advances/{aid}/pay")
async def pay_advance(aid: str, payload: AdvancePayIn,
                     user: dict = Depends(require_permission("subcon_finance", "approve"))):
    org = user.get("org_id", ORG_ID)
    adv = await _doc_or_404(db.subcon_advances, org, aid, user, "Uang muka")
    try:
        doc = await sf.pay_advance(org, adv, user.get("email"), payload.note)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit_log(user, "pay", "subcon_advance", aid, {"amount": adv["amount"]})
    await add_activity(entity_type="project", entity_id=adv["project_id"], type="system",
                       body=(f"Uang muka {adv.get('advance_number')} dibayar Rp {adv['amount']:,} "
                             f"(jurnal {doc.get('journal_no')}). Akan diangsur dari termin."),
                       actor=user.get("email"), org_id=org)
    return {"data": serialize_doc(doc)}


# ------------------------------------------------------------------ potongan
@router.get("/deductions")
async def list_deductions(spk_id: str = None,
                          user: dict = Depends(require_permission("subcon_finance", "view"))):
    org = user.get("org_id", ORG_ID)
    out = await sf.list_deductions(org, spk_id, await _scope(user))
    return {"data": serialize_doc(out["rows"]), "total": len(out["rows"]),
            "summary": out["summary"]}


@router.post("/deductions")
async def create_deduction(payload: DeductionIn,
                          user: dict = Depends(require_permission("subcon_finance", "create"))):
    org = user.get("org_id", ORG_ID)
    spk = await _spk_or_404(org, payload.spk_id, user)
    try:
        doc = await sf.create_deduction(org, spk, payload.model_dump(), user.get("email"))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit_log(user, "create", "subcon_deduction", doc["id"],
                    {"kind": doc["kind"], "amount": doc["amount"], "spk": spk.get("spk_number")})
    return {"data": serialize_doc(doc)}


@router.post("/deductions/{did}/cancel")
async def cancel_deduction(did: str, payload: ReasonIn,
                          user: dict = Depends(require_permission("subcon_finance", "update"))):
    org = user.get("org_id", ORG_ID)
    ded = await _doc_or_404(db.subcon_deductions, org, did, user, "Potongan")
    try:
        doc = await sf.cancel_deduction(org, ded, payload.reason, user.get("email"))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit_log(user, "cancel", "subcon_deduction", did, {"reason": payload.reason})
    return {"data": serialize_doc(doc)}


# ------------------------------------------------------------------ retensi
@router.get("/retentions")
async def list_retentions(spk_id: str = None, state: str = None,
                          user: dict = Depends(require_permission("subcon_finance", "view"))):
    org = user.get("org_id", ORG_ID)
    out = await sf.list_retentions(org, spk_id=spk_id, state=state,
                                  project_ids=await _scope(user))
    return {"data": serialize_doc(out["rows"]), "total": len(out["rows"]),
            "summary": out["summary"]}


@router.post("/retentions/{rid}/request-release")
async def request_release(rid: str, payload: ReasonIn,
                         user: dict = Depends(require_permission("subcon_finance", "create"))):
    org = user.get("org_id", ORG_ID)
    ret = await _doc_or_404(db.subcon_retentions, org, rid, user, "Retensi")
    try:
        doc = await sf.request_release(org, ret, payload.reason, user.get("email"))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit_log(user, "request", "subcon_retention", rid, {"amount": ret["amount"]})
    fin = await db.users.find_one({"org_id": org, "role": "finance_manager", "is_active": True},
                                  {"_id": 0, "email": 1})
    await create_notification(
        user_email=(fin or {}).get("email"), title="Pencairan retensi diajukan",
        body=(f"{ret.get('retention_number')} — {ret.get('subcontractor_name')} "
              f"Rp {ret['amount']:,}. {payload.reason}"),
        type="finance", related_entity_type="project",
        related_entity_id=ret["project_id"], org_id=org)
    return {"data": serialize_doc(doc)}


@router.post("/retentions/{rid}/waive")
async def waive_retention_hold(rid: str, payload: RetentionWaiveIn,
                               user: dict = Depends(
                                   require_permission("subcon_finance", "override"))):
    """Abaikan penahanan pencairan retensi (masa pemeliharaan / punch / klaim garansi).

    Kenapa pintu terpisah, bukan bendera pada endpoint pencairan: mengabaikan jaminan mutu
    adalah KEPUTUSAN yang berdiri sendiri dan harus bisa ditelusuri walau pencairannya
    akhirnya tidak pernah terjadi. Yang boleh mengabaikan (`override`) juga sengaja bukan
    yang mengajukan pencairan — pola empat mata yang sama dengan terobosan serah terima.
    """
    org = user.get("org_id", ORG_ID)
    ret = await _doc_or_404(db.subcon_retentions, org, rid, user, "Retensi")
    try:
        doc = await sf.waive(org, ret, payload.codes, payload.reason, user.get("email"))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit_log(user, "override", "subcon_retention", rid,
                    {"codes": payload.codes, "reason": payload.reason,
                     "amount": ret.get("amount")})
    # Tugas penelaahan: pengabaian tidak boleh menghilang begitu saja dari radar.
    await spawn_review(org, ret, payload, user)
    await add_activity(entity_type="project", entity_id=ret.get("project_id"), type="system",
                       body=(f"Penahanan pencairan retensi {ret.get('retention_number')} "
                             f"diabaikan ({', '.join(payload.codes)}) oleh "
                             f"{user.get('email')}: {payload.reason}"),
                       actor=user.get("email"), org_id=org)
    return {"data": serialize_doc(doc),
            "message": ("Penahanan diabaikan dengan alasan tertulis. Jejaknya tersimpan dan "
                        "tugas penelaahan dibuat.")}


async def spawn_review(org: str, ret: dict, payload, user: dict) -> None:
    from workhub import spawn
    try:
        await spawn(org, "FN-01",
                    source_event=f"retention_waiver:{ret['id']}:{','.join(payload.codes)}",
                    record_owner=user.get("email"), entity_type="subcon_retention",
                    entity_id=ret["id"],
                    title=(f"Telaah pengabaian penahanan retensi "
                           f"{ret.get('retention_number')}"),
                    description=(f"Diabaikan: {', '.join(payload.codes)}. Alasan: "
                                 f"{payload.reason}. Pastikan risiko mutunya benar-benar "
                                 "tertutup (adendum/garansi subkon)."))
    except Exception:  # noqa: BLE001 — tugas gagal jangan membatalkan keputusan
        logger.exception("Tugas penelaahan pengabaian retensi gagal dibuat")


@router.post("/retentions/{rid}/release")
async def release_retention(rid: str, payload: RetentionReleaseIn,
                            user: dict = Depends(require_permission("subcon_finance", "manage"))):
    org = user.get("org_id", ORG_ID)
    ret = await _doc_or_404(db.subcon_retentions, org, rid, user, "Retensi")
    # Idempotensi: sinyal buruk / klik ganda tidak boleh melahirkan tagihan AP kedua.
    lock = await intake.begin(org, "retention_release", payload.client_ref) \
        if payload.client_ref else {"state": "new"}
    if lock["state"] == "replay":
        doc = await db.subcon_retentions.find_one({"id": rid, "org_id": org}, {"_id": 0})
        return {"data": serialize_doc(doc), "replay": True,
                "bill_id": (doc or {}).get("release_bill_id"),
                "journal_no": (doc or {}).get("journal_no"),
                "message": ("Pencairan ini sudah pernah diterima — jawaban lama dikembalikan, "
                            "tidak ada tagihan kedua.")}
    if lock["state"] == "inflight":
        raise HTTPException(status_code=409,
                            detail="Kiriman dengan penanda yang sama sedang diproses.")
    try:
        out = await sf.release(org, ret, payload.reason, user.get("email"))
    except ValueError as e:
        if payload.client_ref:
            await intake.rollback(org, "retention_release", payload.client_ref)
        raise HTTPException(status_code=400, detail=str(e))
    if payload.client_ref:
        await intake.commit(org, "retention_release", payload.client_ref,
                            collection="subcon_retentions", doc_id=rid,
                            summary={"bill_id": out["bill_id"],
                                     "journal_no": out["journal_no"]})
    await audit_log(user, "release", "subcon_retention", rid,
                    {"amount": ret["amount"], "journal": out["journal_no"],
                     "waivers": [w.get("code") for w in (ret.get("waivers") or [])]})
    await add_activity(entity_type="project", entity_id=ret["project_id"], type="system",
                       body=(f"Retensi {ret.get('retention_number')} dicairkan "
                             f"Rp {ret['amount']:,} untuk {ret.get('subcontractor_name')} "
                             f"(jurnal {out['journal_no']}). Siap dibayar lewat Utang (AP)."),
                       actor=user.get("email"), org_id=org)
    return {"data": serialize_doc(out["retention"]), "bill_id": out["bill_id"],
            "journal_no": out["journal_no"]}


# ------------------------------------------------------------------ evaluasi subkon
@router.get("/evaluations")
async def subcon_evaluations(user: dict = Depends(require_permission("subcon", "view"))):
    org = user.get("org_id", ORG_ID)
    subs = await db.subcontractors.find({"org_id": org}, {"_id": 0}).sort("name", 1).to_list(300)
    rows = [await ve.evaluate_subcon(org, s) for s in subs]
    graded = [r for r in rows if r["score"] is not None]
    return {"data": serialize_doc(rows), "total": len(rows), "summary": {
        "total": len(rows), "graded": len(graded), "missing_data": len(rows) - len(graded),
        "avg_score": round(sum(r["score"] for r in graded) / len(graded), 1) if graded else None,
        "detail": ("Skor dihitung dari SPK/termin/denda nyata." if graded else
                   "Belum ada subkontraktor dengan SPK yang bisa dinilai."),
    }}


@router.get("/subcontractors/{sid}/evaluation")
async def subcon_evaluation(sid: str, user: dict = Depends(require_permission("subcon", "view"))):
    org = user.get("org_id", ORG_ID)
    sub = await db.subcontractors.find_one({"id": sid, "org_id": org}, {"_id": 0})
    if not sub:
        raise HTTPException(status_code=404, detail="Subkontraktor tidak ditemukan.")
    return {"data": serialize_doc(await ve.evaluate_subcon(org, sub)),
            "assessments": serialize_doc(await ve.list_assessments(org, "subcontractor", sid))}


@router.post("/subcontractors/{sid}/assessment")
async def assess_subcon(sid: str, payload: AssessmentIn,
                        user: dict = Depends(require_permission("subcon", "update"))):
    org = user.get("org_id", ORG_ID)
    sub = await db.subcontractors.find_one({"id": sid, "org_id": org}, {"_id": 0})
    if not sub:
        raise HTTPException(status_code=404, detail="Subkontraktor tidak ditemukan.")
    doc = await ve.save_assessment(org, {"type": "subcontractor", "id": sid,
                                        "name": sub.get("name")},
                                   payload.model_dump(), user.get("email"))
    await audit_log(user, "create", "subcon_assessment", doc["id"],
                    {"subcon": sub.get("name"), "average": doc.get("average")})
    return {"data": serialize_doc(doc)}
