"""Kas kecil sistem imprest (Fase 84) — pengeluaran LANGSUNG dari kas kecil (bukan kas bon).

Beda dengan kas bon (uang muka karyawan yang dipertanggungjawabkan belakangan): pengeluaran kas
kecil dibayar tunai oleh kasir SAAT ITU, berbukti, dan langsung menjadi beban/WIP:
    Dr beban/WIP per kategori (`reference_p27.CASHBON_ACCOUNT`)  /  Cr sub-akun kas kecil
Pembatalan (void) membalik jurnal itu — jejak tidak dihapus.

Imprest: setiap kas kecil punya BATAS DANA TETAP (`imprest_limit`, per kas atau bawaan org).
Saldo turun setiap pengeluaran; bila saldo < ambang (% dari batas) sistem MENGUSULKAN pengisian
sebesar batas − saldo lewat transfer internal `isi_kas_kecil` (tetap butuh persetujuan SoD).
"""
import logging

import cash_bank as cb
import gl_engine as gl
import reference_p27 as r27
import sequences as seq
import settings_store as cfg
from core_utils import new_id, now_iso
from db import ORG_ID, db

logger = logging.getLogger("sipro.pettyexpense")

KEY_LIMIT = "petty_cash.imprest_limit"
KEY_THRESHOLD = "petty_cash.replenish_threshold_pct"
KEY_MAX = "petty_cash.max_expense"
KEY_PROOF = "petty_cash.require_proof"
SOURCE_TYPE = "petty_expense"


async def policy(org: str = ORG_ID) -> dict:
    v = await cfg.get_many([KEY_LIMIT, KEY_THRESHOLD, KEY_MAX, KEY_PROOF], org_id=org)
    return {"imprest_limit": int(v[KEY_LIMIT] or 0), "threshold_pct": int(v[KEY_THRESHOLD] or 0),
            "max_expense": int(v[KEY_MAX] or 0), "require_proof": bool(v[KEY_PROOF])}


def limit_of(acc: dict, pol: dict) -> int:
    return int(acc.get("imprest_limit") or pol["imprest_limit"] or 0)


async def _cash_account(org: str, account_id: str) -> dict:
    acc = await db.bank_accounts.find_one({"id": account_id, "org_id": org}, {"_id": 0})
    if not acc:
        raise ValueError("Kas kecil tidak ditemukan.")
    if cb.kind_of(acc) != "cash":
        raise ValueError(f"{acc['name']} adalah rekening bank — pengeluaran kas kecil hanya dari kas tunai.")
    if not acc.get("is_active", True):
        raise ValueError(f"Kas {acc['name']} sudah nonaktif.")
    return acc


async def _month_spent(org: str, month: str) -> dict:
    out = {}
    async for r in db.petty_expenses.aggregate([
            {"$match": {"org_id": org, "status": "posted", "date": {"$gte": month}}},
            {"$group": {"_id": "$cash_account_id", "s": {"$sum": "$amount"}, "n": {"$sum": 1}}}]):
        out[r["_id"]] = {"amount": int(r["s"] or 0), "count": int(r["n"] or 0)}
    return out


async def _pending_replenish(org: str) -> dict:
    out = {}
    async for t in db.cash_transfers.find({"org_id": org, "status": "pending", "kind": "isi_kas_kecil"},
                                          {"_id": 0, "to_account_id": 1, "amount": 1, "no": 1}):
        cur = out.setdefault(t["to_account_id"], {"amount": 0, "nos": []})
        cur["amount"] += int(t["amount"] or 0)
        cur["nos"].append(t["no"])
    return out


def _status_of(balance: int, limit: int, threshold: int, pending: int) -> str:
    if limit and balance > limit:
        return "melebihi_batas"
    if balance < threshold:
        return "menunggu_isi" if pending else "perlu_isi"
    return "cukup"


async def imprest_status(org: str = ORG_ID) -> dict:
    """Keadaan imprest setiap kas tunai aktif: saldo, batas, ambang, usulan pengisian."""
    pol = await policy(org)
    rows = [a for a in await cb.list_accounts(org, active_only=True) if a["kind"] == "cash"]
    month = now_iso()[:7]
    spent = await _month_spent(org, month)
    pending = await _pending_replenish(org)
    out = []
    for a in rows:
        limit = limit_of(a, pol)
        threshold = limit * pol["threshold_pct"] // 100
        pend = pending.get(a["id"], {"amount": 0, "nos": []})
        bal = int(a["balance"])
        suggested = max(0, limit - bal - pend["amount"]) if (limit and bal < threshold) else 0
        sp = spent.get(a["id"], {"amount": 0, "count": 0})
        out.append({"account_id": a["id"], "name": a["name"], "account_no": a["account_no"],
                    "gl_account_code": a["gl_account_code"], "is_default": a["is_default"],
                    "balance": bal, "imprest_limit": limit, "limit_source": "kas" if a.get("imprest_limit") else "org",
                    "threshold": threshold, "threshold_pct": pol["threshold_pct"],
                    "suggested_replenish": suggested, "pending_replenish": pend["amount"],
                    "pending_transfer_nos": pend["nos"], "month": month,
                    "month_spent": sp["amount"], "month_count": sp["count"],
                    "status": _status_of(bal, limit, threshold, pend["amount"])})
    return {"accounts": out, "policy": pol,
            "need_replenish": sum(1 for r in out if r["status"] == "perlu_isi"),
            "over_limit": sum(1 for r in out if r["status"] == "melebihi_batas")}


async def create_expense(org: str, payload: dict, actor: str, actor_name: str = None) -> dict:
    pol = await policy(org)
    acc = await _cash_account(org, payload["cash_account_id"])
    amount = int(payload.get("amount") or 0)
    if amount <= 0:
        raise ValueError("Nominal pengeluaran harus lebih dari 0.")
    if pol["max_expense"] and amount > pol["max_expense"]:
        raise ValueError(f"Nominal Rp {amount:,} melebihi batas satu pengeluaran kas kecil "
                         f"Rp {pol['max_expense']:,} — gunakan kas bon atau tagihan vendor (AP).")
    category = payload.get("category")
    expense_code = r27.CASHBON_ACCOUNT.get(category)
    if not expense_code:
        raise ValueError("Kategori pengeluaran tidak dikenal (lihat daftar kategori kas bon).")
    file_ids = [f for f in (payload.get("file_ids") or []) if f]
    if pol["require_proof"] and not file_ids:
        raise ValueError("Bukti (nota/kuitansi) wajib dilampirkan untuk pengeluaran kas kecil.")
    bal = (await cb.balances(org)).get(acc["gl_account_code"], 0)
    if bal < amount:
        raise ValueError(f"Saldo {acc['name']} Rp {bal:,} tidak cukup untuk Rp {amount:,} — "
                         "ajukan pengisian kas kecil dulu.")
    ts = now_iso()
    date = (payload.get("date") or ts[:10])[:10]
    if date > ts[:10]:
        raise ValueError("Tanggal pengeluaran tidak boleh di masa depan.")
    project_id = payload.get("project_id") or None
    project = await db.projects.find_one({"id": project_id, "org_id": org}, {"_id": 0, "name": 1}) \
        if project_id else None
    if project_id and not project:
        raise ValueError("Proyek tidak ditemukan.")
    eid = new_id()
    no = await seq.next_number(SOURCE_TYPE, org, prefix="KK", width=4, year=ts[:4],
                               context={"project_id": project_id})
    desc = payload["description"].strip()
    je = await gl.post_journal(
        org, f"Kas kecil {no} — {desc}",
        [{"account_code": expense_code, "debit": amount, "credit": 0, "memo": desc},
         {"account_code": acc["gl_account_code"], "debit": 0, "credit": amount,
          "memo": f"Dibayar tunai dari {acc['name']}"}],
        date=date, source_type=SOURCE_TYPE, source_id=eid, source_event=f"petty.expense:{eid}",
        posted_by=actor, auto=False)
    doc = {"id": eid, "org_id": org, "no": no, "status": "posted", "date": date,
           "cash_account_id": acc["id"], "cash_account_name": acc["name"],
           "cash_account_code": acc["gl_account_code"],
           "category": category, "expense_account_code": expense_code,
           "description": desc, "payee": (payload.get("payee") or None),
           "amount": amount, "project_id": project_id, "project_name": (project or {}).get("name"),
           "file_ids": file_ids, "journal_id": je["id"], "journal_no": je["entry_no"],
           "created_by": actor, "creator_name": actor_name, "created_at": ts, "updated_at": ts,
           "voided_by": None, "voided_at": None, "void_reason": None, "void_journal_id": None}
    await db.petty_expenses.insert_one(dict(doc))
    doc.pop("_id", None)
    if file_ids:
        await db.files.update_many({"id": {"$in": file_ids}, "org_id": org},
                                   {"$set": {"owner_type": SOURCE_TYPE, "owner_id": eid}})
    return doc


async def void_expense(org: str, expense_id: str, actor: str, reason: str) -> dict:
    doc = await db.petty_expenses.find_one({"id": expense_id, "org_id": org}, {"_id": 0})
    if not doc:
        raise ValueError("Pengeluaran kas kecil tidak ditemukan.")
    if doc["status"] != "posted":
        raise ValueError("Pengeluaran ini sudah dibatalkan.")
    if doc["created_by"] == actor:
        raise ValueError("Pemisahan tugas: pencatat tidak boleh membatalkan pengeluarannya sendiri.")
    je = await gl.post_journal(
        org, f"Pembatalan kas kecil {doc['no']} — {reason}",
        [{"account_code": doc["cash_account_code"], "debit": doc["amount"], "credit": 0,
          "memo": "Kas kecil dikembalikan"},
         {"account_code": doc["expense_account_code"], "debit": 0, "credit": doc["amount"],
          "memo": f"Balik beban {doc['no']}"}],
        source_type=SOURCE_TYPE, source_id=expense_id, source_event=f"petty.expense.void:{expense_id}",
        posted_by=actor, auto=False)
    ts = now_iso()
    await db.petty_expenses.update_one({"id": expense_id}, {"$set": {
        "status": "voided", "voided_by": actor, "voided_at": ts, "void_reason": reason,
        "void_journal_id": je["id"], "void_journal_no": je["entry_no"], "updated_at": ts}})
    return await db.petty_expenses.find_one({"id": expense_id}, {"_id": 0})


async def list_expenses(org: str, account_id: str = None, status: str = None, date_from: str = None,
                        date_to: str = None, limit: int = 100) -> dict:
    q = {"org_id": org}
    if account_id:
        q["cash_account_id"] = account_id
    if status:
        q["status"] = status
    if date_from or date_to:
        q["date"] = {}
        if date_from:
            q["date"]["$gte"] = date_from[:10]
        if date_to:
            q["date"]["$lte"] = date_to[:10]
    rows = await db.petty_expenses.find(q, {"_id": 0}).sort([("date", -1), ("created_at", -1)]).to_list(limit)
    total = await db.petty_expenses.count_documents(q)
    posted = [r for r in rows if r["status"] == "posted"]
    return {"rows": rows, "total": total, "sum_posted": sum(r["amount"] for r in posted)}


async def propose_replenish(org: str, account_id: str, actor: str, from_account_id: str = None,
                            amount: int = None, note: str = None) -> dict:
    """Ajukan `isi_kas_kecil` (pending, SoD) sebesar usulan imprest atau nominal yang diminta."""
    acc = await _cash_account(org, account_id)
    st = next((r for r in (await imprest_status(org))["accounts"] if r["account_id"] == account_id), None)
    if st is None:
        raise ValueError("Kas kecil tidak aktif.")
    amt = int(amount or 0) or st["suggested_replenish"]
    if amt <= 0:
        if st["pending_replenish"]:
            raise ValueError(f"Pengisian {', '.join(st['pending_transfer_nos'])} masih menunggu persetujuan.")
        raise ValueError(f"Saldo {acc['name']} Rp {st['balance']:,} masih di atas ambang Rp {st['threshold']:,}.")
    if st["imprest_limit"] and st["balance"] + st["pending_replenish"] + amt > st["imprest_limit"]:
        raise ValueError(f"Pengisian Rp {amt:,} membuat saldo melampaui batas imprest Rp {st['imprest_limit']:,}.")
    src_id = from_account_id or (await cb.default_account(org, "bank"))["id"]
    return await cb.create_transfer(org, {
        "kind": "isi_kas_kecil", "from_account_id": src_id, "to_account_id": account_id,
        "amount": amt, "fee": 0, "note": note or f"Pengisian imprest {acc['name']}: saldo Rp {st['balance']:,} "
                                                f"< ambang Rp {st['threshold']:,} (batas Rp {st['imprest_limit']:,}).",
    }, actor)
