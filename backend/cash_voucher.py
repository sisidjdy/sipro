"""Bukti Kas Masuk (BKM) & Bukti Kas Keluar (BKK) — Fase 87.

Setiap baris jurnal yang menyentuh sub-akun kas/bank (apa pun modul asalnya: kwitansi AR, bayar
AP, komisi, kas bon, pajak, refund, KPR, transfer internal, kas kecil, giro) otomatis menerbitkan
SATU bukti kas bernomor: debit ke kas/bank → BKM, kredit → BKK. Bukti kas adalah TURUNAN jurnal
(sumber kebenaran tetap `journal_entries`), idempoten per (jurnal, sub-akun), dan bisa dicetak
PDF ber-kop. Jurnal lama tanpa bukti diterbitkan susulan saat startup (`backfill`).
"""
import logging

import sequences as seq
from core_utils import new_id, now_iso
from db import ORG_ID, db

logger = logging.getLogger("sipro.cashvoucher")
KIND = {"in": ("BKM", "Bukti Kas Masuk", "cash_voucher_in"), "out": ("BKK", "Bukti Kas Keluar", "cash_voucher_out")}


async def _cash_codes(org: str) -> dict:
    return {a["gl_account_code"]: a async for a in db.bank_accounts.find(
        {"org_id": org, "gl_account_code": {"$ne": None}}, {"_id": 0, "id": 1, "name": 1, "gl_account_code": 1, "kind": 1})}


async def issue_for_journal(org: str, je: dict, codes: dict = None) -> list:
    codes = codes if codes is not None else await _cash_codes(org)
    out = []
    for ln in je.get("lines") or []:
        acc = codes.get(ln["account_code"])
        if not acc:
            continue
        dr, cr = int(ln.get("debit") or 0), int(ln.get("credit") or 0)
        if not dr and not cr:
            continue
        if await db.cash_vouchers.find_one({"org_id": org, "journal_id": je["id"], "cash_account_code": ln["account_code"]},
                                           {"_id": 0, "id": 1}):
            continue
        direction = "in" if dr else "out"
        prefix, label, scope = KIND[direction]
        date = str(je.get("date") or now_iso())[:10]
        counter = [{"account_code": x["account_code"], "account_name": x.get("account_name"),
                    "amount": int(x.get("debit") or 0) - int(x.get("credit") or 0), "memo": x.get("memo")}
                   for x in je["lines"] if x["account_code"] != ln["account_code"]]
        doc = {"id": new_id(), "org_id": org, "no": await seq.next_number(scope, org, prefix=prefix, width=4, year=date[:4]),
               "kind": prefix, "kind_label": label, "direction": direction, "date": date,
               "cash_account_id": acc["id"], "cash_account_name": acc["name"], "cash_account_code": ln["account_code"],
               "cash_kind": acc.get("kind") or "bank", "amount": dr or cr, "memo": je.get("memo"),
               "line_memo": ln.get("memo"), "counter": counter, "journal_id": je["id"], "entry_no": je.get("entry_no"),
               "source_type": je.get("source_type"), "source_id": je.get("source_id"),
               "posted_by": je.get("posted_by"), "created_at": now_iso()}
        await db.cash_vouchers.insert_one(dict(doc))
        doc.pop("_id", None)
        out.append(doc)
    return out


async def backfill(org: str = ORG_ID) -> int:
    codes = await _cash_codes(org)
    if not codes:
        return 0
    done = {(v["journal_id"], v["cash_account_code"]) async for v in db.cash_vouchers.find(
        {"org_id": org}, {"_id": 0, "journal_id": 1, "cash_account_code": 1})}
    n = 0
    cur = db.journal_entries.find({"org_id": org, "lines.account_code": {"$in": list(codes)}}, {"_id": 0}) \
        .sort([("date", 1), ("created_at", 1)])
    async for je in cur:
        if all((je["id"], ln["account_code"]) in done for ln in je["lines"] if ln["account_code"] in codes):
            continue
        n += len(await issue_for_journal(org, je, codes))
    if n:
        logger.info("Bukti kas: %s BKM/BKK diterbitkan susulan untuk jurnal lama (%s).", n, org)
    return n


async def listing(org: str, kind: str = None, account_id: str = None, date_from: str = None,
                  date_to: str = None, q: str = None, skip: int = 0, limit: int = 50) -> dict:
    f = {"org_id": org}
    if kind in ("BKM", "BKK"):
        f["kind"] = kind
    if account_id:
        f["cash_account_id"] = account_id
    if date_from or date_to:
        f["date"] = {}
        if date_from:
            f["date"]["$gte"] = date_from[:10]
        if date_to:
            f["date"]["$lte"] = date_to[:10]
    if q:
        f["$or"] = [{"no": {"$regex": q, "$options": "i"}}, {"memo": {"$regex": q, "$options": "i"}},
                    {"entry_no": {"$regex": q, "$options": "i"}}]
    total = await db.cash_vouchers.count_documents(f)
    rows = await db.cash_vouchers.find(f, {"_id": 0}).sort([("date", -1), ("created_at", -1)]).skip(skip).limit(limit).to_list(limit)
    sums = {"BKM": 0, "BKK": 0}
    async for r in db.cash_vouchers.aggregate([{"$match": f}, {"$group": {"_id": "$kind", "s": {"$sum": "$amount"}}}]):
        sums[r["_id"]] = int(r["s"] or 0)
    return {"rows": rows, "total": total, "sum_in": sums["BKM"], "sum_out": sums["BKK"]}


def pdf_content(v: dict, party: str = None) -> str:
    rp = lambda x: f"Rp {int(x):,}".replace(",", ".")  # noqa: E731
    masuk = v["direction"] == "in"
    lines = [f"Nomor bukti : {v['no']}", f"Tanggal : {v['date']}",
             f"{'Diterima pada' if masuk else 'Dibayar dari'} : {v['cash_account_name']} ({v['cash_account_code']})",
             f"{'Diterima dari' if masuk else 'Dibayar kepada'} : {party or '-'}",
             f"Jumlah : {rp(v['amount'])}", f"Keterangan : {v.get('memo') or '-'}",
             f"Nomor jurnal : {v.get('entry_no') or '-'}", f"Sumber : {v.get('source_type') or '-'}", ""]
    lines.append("Lawan akun:")
    for c in v.get("counter") or []:
        lines.append(f"  {c['account_code']} {c.get('account_name') or ''} : {rp(abs(c['amount']))}"
                     f"{' (Dr)' if c['amount'] > 0 else ' (Cr)'}")
    lines += ["", f"{v['kind_label']} ini diterbitkan otomatis dari jurnal {v.get('entry_no') or ''} dan sah sebagai bukti kas."]
    return "\n".join(lines)
