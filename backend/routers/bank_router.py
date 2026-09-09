"""ROUTER REKONSILIASI BANK (Fase 47A) — prefix `/bank`.

Pemisahan tugas yang dipaksakan di sini:
  * `view`   — melihat mutasi & ringkasan rekonsiliasi (keuangan + direksi).
  * `create` — mendaftarkan rekening & mengimpor mutasi.
  * `update` — MENCOCOKKAN mutasi ke dokumen (kasir/finance).
  * `approve` — MEMBATALKAN pencocokan (membalik uang) — hanya supervisor keuangan/direksi.
    Sengaja lebih ketat daripada mencocokkan: membalik penerimaan mengubah pembukuan yang
    sudah dilaporkan.
Sales & peran lapangan tidak punya akses sama sekali (mutasi rekening = data sensitif).
"""
from fastapi import APIRouter, Body, Depends, HTTPException, Query

import bank_import as bimp
import bank_match as bmatch
from core_utils import new_id, now_iso, parse_pagination, serialize_doc
from db import ORG_ID, db
from models_p47 import BankAccountIn, BankIgnoreIn, BankImportIn, BankMatchIn, BankUnmatchIn
from rbac import audit_log, require_permission
from reference_p47 import DIRECTION_LABEL, MATCH_STATE_LABEL

router = APIRouter(prefix="/bank", tags=["bank"])


def _org(user: dict) -> str:
    return user.get("org_id", ORG_ID)


# ------------------------------------------------------------------ rekening
@router.get("/accounts")
async def list_accounts(user: dict = Depends(require_permission("bank", "view"))):
    # Fase 82/83: koleksi `bank_accounts` juga memuat kas (kind=cash); rekonsiliasi bank hanya
    # untuk rekening bank — kas tidak punya mutasi rekening untuk dibandingkan.
    rows = await db.bank_accounts.find({"org_id": _org(user), "kind": {"$ne": "cash"}}, {"_id": 0}) \
        .sort([("is_default", -1), ("name", 1)]).to_list(100)
    return {"data": serialize_doc(rows), "total": len(rows)}


@router.post("/accounts")
async def create_account(payload: BankAccountIn,
                         user: dict = Depends(require_permission("bank", "create"))):
    org = _org(user)
    acct = await db.accounts.find_one({"org_id": org, "code": payload.gl_account_code},
                                      {"_id": 0, "code": 1, "name": 1})
    if not acct:
        raise HTTPException(status_code=400, detail=(
            f"Akun GL {payload.gl_account_code} tidak ada di Bagan Akun — pilih akun kas/bank "
            "yang benar supaya saldo buku bisa dibandingkan dengan rekening."))
    if await db.bank_accounts.find_one({"org_id": org, "account_no": payload.account_no},
                                       {"_id": 0, "id": 1}):
        raise HTTPException(status_code=409,
                            detail="Nomor rekening ini sudah terdaftar.")
    ts = now_iso()
    doc = {"id": new_id(), "org_id": org, **payload.model_dump(),
           "gl_account_name": acct.get("name"),
           "created_by": user.get("email"), "created_at": ts, "updated_at": ts}
    await db.bank_accounts.insert_one(dict(doc))
    doc.pop("_id", None)
    # Fase 82: setiap rekening langsung mendapat sub-akun GL sendiri (bukan menumpang 1-1200).
    import cash_bank as _cb
    doc["gl_account_code"] = await _cb._ensure_sub_account(org, {**doc, "kind": "bank"})
    await db.bank_accounts.update_one({"id": doc["id"]}, {"$set": {"kind": "bank"}})
    await _cb._post_opening(org, doc)
    await audit_log(user, "create", "bank_accounts", doc["id"], {"name": doc["name"]})
    return {"data": serialize_doc(doc)}


@router.put("/accounts/{account_id}")
async def update_account(account_id: str, payload: BankAccountIn,
                         user: dict = Depends(require_permission("bank", "update"))):
    org = _org(user)
    res = await db.bank_accounts.update_one(
        {"id": account_id, "org_id": org},
        {"$set": {**payload.model_dump(), "updated_at": now_iso(),
                  "updated_by": user.get("email")}})
    if not res.matched_count:
        raise HTTPException(status_code=404, detail="Rekening tidak ditemukan")
    await audit_log(user, "update", "bank_accounts", account_id, {"name": payload.name})
    return {"data": serialize_doc(await db.bank_accounts.find_one({"id": account_id},
                                                                 {"_id": 0}))}


# ------------------------------------------------------------------ impor mutasi
@router.post("/statements/import")
async def import_statement(payload: BankImportIn,
                           user: dict = Depends(require_permission("bank", "create"))):
    """Impor CSV mutasi. `dry_run=true` (bawaan) HANYA memberi pratinjau, tanpa menulis."""
    try:
        out = await bimp.import_csv(_org(user), payload.account_id, payload.filename,
                                    payload.csv_text, user.get("email"),
                                    dry_run=payload.dry_run)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not payload.dry_run:
        await audit_log(user, "import", "bank_transactions", payload.account_id,
                        {"file": payload.filename, "counts": out["counts"]})
    return {"data": serialize_doc(out), "message": out["message"]}


@router.get("/statements")
async def list_statements(account_id: str = None, skip: int = 0, limit: int = 25,
                          user: dict = Depends(require_permission("bank", "view"))):
    skip, limit = parse_pagination(skip, limit)
    q = {"org_id": _org(user)}
    if account_id:
        q["account_id"] = account_id
    total = await db.bank_statements.count_documents(q)
    rows = await db.bank_statements.find(q, {"_id": 0}).sort("created_at", -1) \
        .skip(skip).limit(limit).to_list(limit)
    return {"data": serialize_doc(rows), "total": total}


# ------------------------------------------------------------------ mutasi & pencocokan
@router.get("/transactions")
async def list_transactions(account_id: str = None, match_state: str = None,
                            direction: str = None, date_from: str = None,
                            date_to: str = None, q: str = None, skip: int = 0,
                            limit: int = Query(25, ge=1, le=200),
                            user: dict = Depends(require_permission("bank", "view"))):
    org = _org(user)
    skip, limit = parse_pagination(skip, limit)
    query = {"org_id": org}
    if account_id:
        query["account_id"] = account_id
    if match_state:
        query["match_state"] = {"$in": [s for s in match_state.split(",") if s]}
    if direction:
        query["direction"] = direction
    if date_from or date_to:
        query["date"] = {k: v for k, v in (("$gte", date_from), ("$lte", date_to)) if v}
    if q:
        query["$or"] = [{"description": {"$regex": q, "$options": "i"}},
                        {"ref": {"$regex": q, "$options": "i"}}]
    total = await db.bank_transactions.count_documents(query)
    rows = await db.bank_transactions.find(query, {"_id": 0}) \
        .sort([("date", -1), ("created_at", -1)]).skip(skip).limit(limit).to_list(limit)
    for r in rows:
        r["direction_label"] = DIRECTION_LABEL.get(r.get("direction"))
        r["match_state_label"] = MATCH_STATE_LABEL.get(r.get("match_state"))
    base = {"org_id": org, **({"account_id": account_id} if account_id else {})}
    summary = {s: await db.bank_transactions.count_documents({**base, "match_state": s})
               for s in MATCH_STATE_LABEL}
    return {"data": serialize_doc(rows), "total": total, "summary": summary}


@router.get("/transactions/{txn_id}/suggest")
async def suggest_match(txn_id: str,
                        user: dict = Depends(require_permission("bank", "view"))):
    """Kandidat pencocokan + SKOR & ALASANNYA. Sistem mengusulkan, manusia memutuskan."""
    try:
        return {"data": serialize_doc(await bmatch.suggest(_org(user), txn_id))}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/transactions/{txn_id}/match")
async def do_match(txn_id: str, payload: BankMatchIn,
                   user: dict = Depends(require_permission("bank", "update"))):
    try:
        out = await bmatch.match(_org(user), txn_id, payload.kind, payload.target_id,
                                 user.get("email"), payload.note)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit_log(user, "bank.match", "bank_transactions", txn_id,
                    {"kind": payload.kind, "target_id": payload.target_id})
    return {"data": serialize_doc(out), "message": out["message"]}


@router.post("/transactions/{txn_id}/unmatch")
async def do_unmatch(txn_id: str, payload: BankUnmatchIn,
                     user: dict = Depends(require_permission("bank", "approve"))):
    """Batalkan pencocokan + balikkan dampaknya. Wajib beralasan."""
    try:
        out = await bmatch.unmatch(_org(user), txn_id, user.get("email"), payload.reason)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit_log(user, "bank.unmatch", "bank_transactions", txn_id,
                    {"reason": payload.reason})
    return {"data": serialize_doc(out), "message": out["message"]}


@router.post("/transactions/{txn_id}/ignore")
async def do_ignore(txn_id: str, payload: BankIgnoreIn,
                    user: dict = Depends(require_permission("bank", "update"))):
    try:
        out = await bmatch.ignore(_org(user), txn_id, user.get("email"), payload.reason)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit_log(user, "bank.ignore", "bank_transactions", txn_id,
                    {"reason": payload.reason})
    return {"data": serialize_doc(out)}


@router.get("/reconciliation")
async def reconciliation(account_id: str = None, as_of: str = None,
                         user: dict = Depends(require_permission("bank", "view"))):
    """Fase 83: saldo rekening vs saldo SUB-AKUN GL rekening itu pada tanggal yang sama; selisih
    diurai per item (mutasi belum cocok, jurnal tanpa pasangan, saldo awal tersirat, residu)."""
    import bank_recon as brc
    org = _org(user)
    if not account_id:
        acc = await db.bank_accounts.find_one({"org_id": org, "kind": "bank", "is_default": True},
                                              {"_id": 0, "id": 1}) \
            or await db.bank_accounts.find_one({"org_id": org, "kind": "bank"}, {"_id": 0, "id": 1})
        if not acc:
            raise HTTPException(status_code=404, detail="Belum ada rekening bank terdaftar.")
        account_id = acc["id"]
    try:
        return {"data": serialize_doc(await brc.reconcile(org, account_id, as_of))}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/reconciliation/overview")
async def reconciliation_overview(user: dict = Depends(require_permission("bank", "view"))):
    import bank_recon as brc
    rows = await brc.overview(_org(user))
    return {"data": serialize_doc(rows), "total": len(rows),
            "summary": {s: sum(1 for r in rows if r["status"] == s)
                        for s in ("seimbang", "dijelaskan", "belum_dijelaskan", "tanpa_data")}}


@router.post("/reconciliation/explain")
async def reconciliation_explain(payload: dict = Body(...),
                                 user: dict = Depends(require_permission("bank", "update"))):
    import bank_recon as brc
    for k in ("account_id", "journal_id", "reason_code"):
        if not payload.get(k):
            raise HTTPException(status_code=400, detail=f"Field '{k}' wajib diisi.")
    try:
        doc = await brc.explain(_org(user), payload["account_id"], payload["journal_id"],
                                payload["reason_code"], payload.get("note"), user.get("email"))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit_log(user, "update", "bank_recon_notes", doc["id"],
                    {"journal_id": payload["journal_id"], "reason_code": payload["reason_code"]})
    return {"data": serialize_doc(doc)}


@router.post("/reconciliation/unexplain")
async def reconciliation_unexplain(payload: dict = Body(...),
                                   user: dict = Depends(require_permission("bank", "update"))):
    import bank_recon as brc
    ok = await brc.unexplain(_org(user), payload.get("account_id"), payload.get("journal_id"))
    if not ok:
        raise HTTPException(status_code=404, detail="Alasan tidak ditemukan.")
    await audit_log(user, "update", "bank_recon_notes", payload.get("journal_id"), {"removed": True})
    return {"data": {"removed": True}}
