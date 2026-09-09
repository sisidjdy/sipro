"""Rekonsiliasi bank PER REKENING (Fase 83) — saldo rekening pada tanggal mutasi terakhir vs saldo
SUB-AKUN GL rekening itu pada tanggal yang sama, lalu selisihnya DIURAI menjadi item yang bisa
ditunjuk: (a) mutasi rekening yang belum ada di buku, (b) jurnal buku yang belum ada di rekening,
(c) saldo awal rekening yang tersirat sebelum mutasi pertama diimpor, (d) residu yang tidak
terjelaskan. Item buku boleh diberi alasan (setoran dalam perjalanan, cek belum cair, dst.) —
alasan hanya DOKUMENTASI, tidak mengubah angka.
"""
import cash_bank as cb
from core_utils import new_id, now_iso
from db import ORG_ID, db

EXPLAIN_REASONS = {
    "deposit_in_transit": "Setoran dalam perjalanan (belum muncul di rekening)",
    "outstanding_payment": "Pembayaran/cek belum dikliring bank",
    "timing": "Beda tanggal pencatatan (akan cocok periode berikut)",
    "bank_fee_pending": "Biaya/bunga bank belum diimpor",
    "book_error": "Salah catat di buku — perlu jurnal koreksi",
    "other": "Lainnya (lihat catatan)",
}


def _signed(txn: dict) -> int:
    amt = int(txn.get("amount") or 0)
    return amt if txn.get("direction") == "in" else -amt


async def _paired_ids(org: str, account_id: str) -> set:
    ids = set()
    async for m in db.bank_matches.find({"org_id": org, "account_id": account_id, "state": "matched"},
                                        {"_id": 0, "txn_id": 1, "target_id": 1, "result": 1}):
        ids.update({m.get("txn_id"), m.get("target_id")})
        res = m.get("result") or {}
        ids.update(v for k, v in res.items() if k.endswith("_id") and isinstance(v, str))
    ids.discard(None)
    return ids


async def _book_lines(org: str, code: str, as_of: str) -> list:
    q = {"org_id": org, "lines.account_code": code}
    if as_of:
        q["date"] = {"$lt": as_of[:10] + "T99"}
    out = []
    async for je in db.journal_entries.find(q, {"_id": 0}):
        for ln in je["lines"]:
            if ln["account_code"] != code:
                continue
            counter = [x["account_name"] for x in je["lines"] if x["account_code"] != code]
            out.append({"journal_id": je["id"], "entry_no": je["entry_no"], "date": je["date"][:10],
                        "memo": je["memo"], "source_type": je.get("source_type"),
                        "source_id": je.get("source_id"), "counter": ", ".join(dict.fromkeys(counter)),
                        "amount": int(ln.get("debit") or 0) - int(ln.get("credit") or 0)})
    out.sort(key=lambda x: (x["date"], x["entry_no"]))
    return out


async def reconcile(org: str, account_id: str, as_of: str = None) -> dict:
    acc = await db.bank_accounts.find_one({"id": account_id, "org_id": org}, {"_id": 0})
    if not acc:
        raise ValueError("Rekening tidak ditemukan.")
    code = acc.get("gl_account_code")
    if not code or code in cb.HEADER_CODES:
        code = await cb.resolve_code(org, account_id)
    txns = await db.bank_transactions.find({"org_id": org, "account_id": account_id}, {"_id": 0}).to_list(5000)
    txns.sort(key=lambda t: (t["date"], t.get("created_at") or ""))
    with_bal = [t for t in txns if t.get("balance") is not None]
    if as_of:
        with_bal = [t for t in with_bal if t["date"][:10] <= as_of[:10]]
    latest = with_bal[-1] if with_bal else None
    cutoff = (latest["date"][:10] if latest else (as_of or now_iso())[:10])
    stmt = int(latest["balance"]) if latest else None
    first = with_bal[0] if with_bal else None
    # Saldo tersirat sebelum mutasi pertama = saldo akhir − Σ seluruh mutasi (tidak bergantung
    # urutan baris dalam satu tanggal).
    stmt_opening = (stmt - sum(_signed(t) for t in txns if t["date"][:10] <= cutoff)) if latest else None

    scoped = [t for t in txns if t["date"][:10] <= cutoff]
    unmatched = [t for t in scoped if t.get("match_state") == "unmatched"]
    bank_only_signed = sum(_signed(t) for t in unmatched)

    lines = await _book_lines(org, code, cutoff)
    book = sum(l["amount"] for l in lines)
    paired = await _paired_ids(org, account_id)
    notes = {n["journal_id"]: n async for n in db.bank_recon_notes.find(
        {"org_id": org, "account_id": account_id}, {"_id": 0})}
    book_only = []
    for l in lines:
        if l["source_id"] in paired or l["journal_id"] in paired:
            continue
        n = notes.get(l["journal_id"])
        book_only.append({**l, "explained": bool(n),
                          "reason_code": (n or {}).get("reason_code"),
                          "reason_label": EXPLAIN_REASONS.get((n or {}).get("reason_code")),
                          "note": (n or {}).get("note"), "explained_by": (n or {}).get("actor")})
    book_only_signed = sum(l["amount"] for l in book_only)
    unexplained_items = [l for l in book_only if not l["explained"]]

    residual = None
    if stmt is not None:
        residual = (stmt + book_only_signed) - (book + bank_only_signed)
        if stmt_opening is not None:
            residual -= stmt_opening
    if stmt is None:
        status = "tanpa_data"
    elif residual == 0 and not unmatched and not unexplained_items:
        status = "seimbang"
    elif residual == 0 and not unexplained_items:
        status = "dijelaskan"
    else:
        status = "belum_dijelaskan"

    causes = []
    if unmatched:
        causes.append({"code": "unmatched", "count": len(unmatched), "amount": bank_only_signed,
                       "detail": f"{len(unmatched)} mutasi rekening belum dicocokkan ke buku "
                                 f"(bersih {cb_rp(bank_only_signed)})."})
    if unexplained_items:
        amt = sum(l["amount"] for l in unexplained_items)
        causes.append({"code": "book_only", "count": len(unexplained_items), "amount": amt,
                       "detail": f"{len(unexplained_items)} jurnal di buku belum ada pasangannya di "
                                 f"rekening dan belum diberi alasan (bersih {cb_rp(amt)})."})
    if stmt_opening:
        causes.append({"code": "statement_opening", "count": None, "amount": stmt_opening,
                       "detail": f"Rekening sudah bersaldo {cb_rp(stmt_opening)} sebelum mutasi pertama "
                                 f"yang diimpor ({first['date'][:10]}) — periode sebelumnya belum diimpor."})
    if residual:
        causes.append({"code": "unexplained", "count": None, "amount": residual,
                       "detail": f"{cb_rp(abs(residual))} residu TIDAK terjelaskan oleh item mana pun — "
                                 "periksa impor mutasi yang hilang atau jurnal ke rekening lain."})
    return {
        "account": {**acc, "kind": cb.kind_of(acc)}, "gl_account_code": code, "as_of": cutoff,
        "book_balance": book, "statement_balance": stmt,
        "statement_balance_at": (latest or {}).get("date"), "statement_opening": stmt_opening,
        "difference": None if stmt is None else stmt - book,
        "bank_only": [{k: t.get(k) for k in ("id", "date", "description", "ref", "direction", "amount")}
                      for t in unmatched],
        "bank_only_total": bank_only_signed,
        "book_only": book_only, "book_only_total": book_only_signed,
        "explained_count": len(book_only) - len(unexplained_items),
        "unexplained_count": len(unexplained_items), "unexplained": residual, "residual": residual,
        "status": status, "causes": causes,
        "unmatched_count": len(unmatched),
        "unmatched_in": sum(int(t["amount"]) for t in unmatched if t["direction"] == "in"),
        "unmatched_out": sum(int(t["amount"]) for t in unmatched if t["direction"] == "out"),
        "matched_count": len([t for t in scoped if t.get("match_state") == "matched"]),
        "ignored_count": len([t for t in scoped if t.get("match_state") == "ignored"]),
        "txn_total": len(txns), "missing": [] if stmt is not None else ["saldo_rekening"],
        "reasons": [{"value": k, "label": v} for k, v in EXPLAIN_REASONS.items()],
        "generated_at": now_iso(),
    }


def cb_rp(v) -> str:
    return f"Rp {int(v):,}".replace(",", ".")


async def overview(org: str = ORG_ID) -> list:
    rows = []
    for acc in await db.bank_accounts.find({"org_id": org, "kind": "bank"}, {"_id": 0}).sort("name", 1).to_list(200):
        r = await reconcile(org, acc["id"])
        rows.append({"account_id": acc["id"], "name": acc["name"], "bank_name": acc.get("bank_name"),
                     "account_no": acc.get("account_no"), "gl_account_code": r["gl_account_code"],
                     "is_active": acc.get("is_active", True), "as_of": r["as_of"],
                     "book_balance": r["book_balance"], "statement_balance": r["statement_balance"],
                     "difference": r["difference"], "residual": r["residual"], "status": r["status"],
                     "unmatched_count": r["unmatched_count"], "unexplained_count": r["unexplained_count"],
                     "txn_total": r["txn_total"]})
    return rows


async def explain(org: str, account_id: str, journal_id: str, reason_code: str, note: str, actor: str) -> dict:
    if reason_code not in EXPLAIN_REASONS:
        raise ValueError("Kode alasan tidak dikenal.")
    if reason_code == "other" and not (note or "").strip():
        raise ValueError("Alasan 'Lainnya' wajib disertai catatan.")
    je = await db.journal_entries.find_one({"id": journal_id, "org_id": org}, {"_id": 0, "id": 1})
    if not je:
        raise ValueError("Jurnal tidak ditemukan.")
    ts = now_iso()
    doc = {"id": new_id(), "org_id": org, "account_id": account_id, "journal_id": journal_id,
           "reason_code": reason_code, "note": note, "actor": actor, "created_at": ts}
    await db.bank_recon_notes.update_one({"org_id": org, "account_id": account_id, "journal_id": journal_id},
                                         {"$set": doc}, upsert=True)
    return doc


async def unexplain(org: str, account_id: str, journal_id: str) -> bool:
    r = await db.bank_recon_notes.delete_one({"org_id": org, "account_id": account_id, "journal_id": journal_id})
    return r.deleted_count > 0
