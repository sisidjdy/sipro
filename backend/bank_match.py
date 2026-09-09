"""PENCOCOKAN MUTASI BANK (Fase 47A) — usul, cocokkan, batalkan; semuanya berjejak.

Prinsip yang dipegang:

  1. **Sistem MENGUSULKAN, manusia MEMUTUSKAN.** Tidak ada pencocokan otomatis diam-diam;
     uang yang salah dicocokkan lebih berbahaya daripada mutasi yang belum dicocokkan.
     Setiap kandidat menyebut SKOR dan ALASAN skornya (nominal sama, tanggal berdekatan,
     nama/unit disebut di keterangan) sehingga kasir bisa menilai, bukan menebak.
  2. **Tidak ada dua kebenaran.** Pencocokan tidak pernah menulis pelunasan sendiri: ia
     memanggil jalur resmi yang sudah dipakai layar lain — `finance_engine.apply_receipt`
     (AR), `finance_engine.pay_ap_bill` (AP), `labor_engine.pay_payroll` (upah),
     `payment_intake.verify` (bukti transfer portal). Jurnal GL tetap lahir dari event
     subledger yang sudah ada, jadi kas di GL selalu = kas yang benar-benar diterima.
  3. **Mutasi yang belum dicocokkan TIDAK PERNAH dianggap pelunasan.** Ia tampil apa adanya
     di daftar "belum cocok" dan masuk ke ringkasan selisih rekonsiliasi.
  4. **Bisa dibatalkan, tetapi beralasan.** `unmatch` membalik dampaknya (membatalkan
     kuitansi + jurnal pembalik) dan menuntut alasan — karena membalik uang adalah
     keputusan yang harus bisa dipertanggungjawabkan. Pembayaran vendor & upah SENGAJA
     tidak bisa dibatalkan dari sini (lihat `UNMATCHABLE_KINDS`).
  5. **Saldo yang belum diketahui bukan nol.** Bila ekspor bank tidak memuat kolom saldo,
     rekonsiliasi menulis `null` + menyebut apa yang kurang.
"""
import logging

import finance_engine as fin
import gl_engine as gl
import settings_store as cfg
from core_utils import new_id, now_iso
from db import ORG_ID, db
from engine import add_activity, emit
from reference_p47 import (GL_BANK, GL_BANK_FEE, GL_CONTRACT_LIABILITY, GL_OTHER_INCOME,
                          MATCH_KIND_LABEL, UNMATCHABLE_KINDS)

logger = logging.getLogger("sipro.bank.match")
MIN_REASON = 5


async def txn_or_error(org: str, txn_id: str) -> dict:
    txn = await db.bank_transactions.find_one({"id": txn_id, "org_id": org}, {"_id": 0})
    if not txn:
        raise ValueError("Mutasi bank tidak ditemukan.")
    return txn


def _days(a: str, b: str):
    from datetime import date
    try:
        return abs((date.fromisoformat(str(a)[:10]) - date.fromisoformat(str(b)[:10])).days)
    except ValueError:
        return None


def _mentions(haystack: str, needle: str) -> bool:
    if not needle:
        return False
    return str(needle).strip().lower() in str(haystack or "").lower()


async def _tolerance(org: str) -> tuple:
    tol = int(await cfg.get("bank.match_amount_tolerance", org_id=org) or 0)
    win = int(await cfg.get("bank.match_date_window_days", org_id=org) or 7)
    return tol, win


def _score(txn: dict, *, amount: int, ref_date: str, texts: list, base: int) -> dict:
    """Skor kandidat + alasan yang bisa dibaca manusia (bukan angka gelap)."""
    score, why = base, []
    if amount and int(amount) == int(txn["amount"]):
        score += 45
        why.append("nominal sama persis")
    gap = _days(txn["date"], ref_date) if ref_date else None
    if gap is not None and gap <= 3:
        score += 20
        why.append(f"tanggal berdekatan ({gap} hari)")
    elif gap is not None and gap <= 14:
        score += 8
        why.append(f"tanggal dalam 2 minggu ({gap} hari)")
    for t in texts:
        if _mentions(txn.get("description"), t) or _mentions(txn.get("ref"), t):
            score += 15
            why.append(f"keterangan menyebut '{t}'")
            break
    return {"score": min(100, score), "reasons": why}


async def _ar_candidates(org: str, txn: dict, tol: int) -> list:
    """Termin pembeli yang masih terutang — kandidat untuk uang MASUK."""
    out = []
    invs = await db.ar_invoices.find({"org_id": org, "outstanding": {"$gt": 0}},
                                     {"_id": 0}).to_list(300)
    for inv in invs:
        items = [i for i in (inv.get("items") or []) if i.get("status") != "paid"]
        nxt = sorted(items, key=lambda x: x.get("due_date") or "")[:1]
        due = (nxt[0].get("due_date") if nxt else None)
        item_out = (int(nxt[0]["amount"]) - int(nxt[0].get("paid_amount") or 0)) if nxt else 0
        exact = abs(item_out - int(txn["amount"])) <= tol \
            or abs(int(inv.get("outstanding") or 0) - int(txn["amount"])) <= tol
        sc = _score(txn, amount=item_out, ref_date=due,
                    texts=[inv.get("unit_code"), inv.get("customer_name"),
                           inv.get("lead_name")],
                    base=20 if exact else 0)
        if sc["score"] < 25:
            continue
        out.append({
            "kind": "ar_deal", "target_id": inv.get("deal_id"),
            "label": (f"Termin {(nxt[0].get('label') if nxt else 'AR')} · unit "
                      f"{inv.get('unit_code') or '-'}"),
            "sub_label": inv.get("customer_name") or inv.get("lead_name"),
            "amount": item_out or int(inv.get("outstanding") or 0),
            "outstanding": int(inv.get("outstanding") or 0), "date": due,
            "link": f"/finance?tab=ar&deal={inv.get('deal_id')}", **sc})
    return out


async def _intake_candidates(org: str, txn: dict, tol: int) -> list:
    """Bukti transfer yang dikirim pelanggan lewat portal dan masih menunggu verifikasi."""
    rows = await db.payment_intakes.find({"org_id": org, "state": "pending"},
                                         {"_id": 0}).to_list(200)
    out = []
    for r in rows:
        exact = abs(int(r.get("amount") or 0) - int(txn["amount"])) <= tol
        sc = _score(txn, amount=int(r.get("amount") or 0), ref_date=r.get("transfer_date"),
                    texts=[r.get("unit_code"), r.get("customer_name")],
                    base=35 if exact else 0)
        if sc["score"] < 25:
            continue
        out.append({"kind": "payment_intake", "target_id": r["id"],
                    "label": (f"Bukti transfer {r.get('customer_name') or '-'} · unit "
                              f"{r.get('unit_code') or '-'}"),
                    "sub_label": f"dikirim {str(r.get('created_at'))[:10]} lewat portal",
                    "amount": int(r.get("amount") or 0), "date": r.get("transfer_date"),
                    "link": "/finance?tab=recon", **sc})
    return out


async def _ap_candidates(org: str, txn: dict, tol: int) -> list:
    rows = await db.ap_invoices.find({"org_id": org, "status": {"$in": ["approved", "partial"]}},
                                     {"_id": 0}).to_list(300)
    out = []
    for b in rows:
        outstanding = int(b.get("net", 0)) - int(b.get("paid", 0))
        if outstanding <= 0:
            continue
        sc = _score(txn, amount=outstanding, ref_date=b.get("due_date"),
                    texts=[b.get("vendor")],
                    base=20 if abs(outstanding - int(txn["amount"])) <= tol else 0)
        if sc["score"] < 25:
            continue
        out.append({"kind": "ap_bill", "target_id": b["id"],
                    "label": f"Tagihan vendor {b.get('vendor')}",
                    "sub_label": f"sisa Rp {outstanding:,}".replace(",", "."),
                    "amount": outstanding, "date": b.get("due_date"),
                    "link": "/finance?tab=ap", **sc})
    return out


async def _payroll_candidates(org: str, txn: dict, tol: int) -> list:
    rows = await db.labor_payrolls.find({"org_id": org, "state": "approved"},
                                        {"_id": 0}).to_list(200)
    out = []
    for p in rows:
        total = int(p.get("total") or 0)
        sc = _score(txn, amount=total, ref_date=p.get("period_end"),
                    texts=[p.get("no"), p.get("project_name"), "upah"],
                    base=20 if abs(total - int(txn["amount"])) <= tol else 0)
        if sc["score"] < 25:
            continue
        out.append({"kind": "labor_payroll", "target_id": p["id"],
                    "label": f"Upah {p.get('no')} · {p.get('project_name') or '-'}",
                    "sub_label": f"periode {p.get('period_start')} s/d {p.get('period_end')}",
                    "amount": total, "date": p.get("period_end"),
                    "link": "/build?hub=lapangan", **sc})
    return out


async def suggest(org: str = ORG_ID, txn_id: str = None) -> dict:
    """Kandidat pencocokan untuk satu mutasi — berurut dari yang paling meyakinkan."""
    txn = await txn_or_error(org, txn_id)
    tol, _win = await _tolerance(org)
    if txn["direction"] == "in":
        cands = await _intake_candidates(org, txn, tol) + await _ar_candidates(org, txn, tol)
        cands.append({"kind": "bank_interest", "target_id": None,
                      "label": "Jasa giro / bunga bank", "sub_label": "pendapatan lain-lain",
                      "amount": int(txn["amount"]), "date": txn["date"], "score": 10,
                      "reasons": ["pilihan manual bila mutasi ini bukan pembayaran pembeli"]})
    else:
        cands = await _ap_candidates(org, txn, tol) + await _payroll_candidates(org, txn, tol)
        cands.append({"kind": "bank_fee", "target_id": None,
                      "label": "Biaya administrasi / bunga bank", "sub_label": "beban bank",
                      "amount": int(txn["amount"]), "date": txn["date"], "score": 10,
                      "reasons": ["pilihan manual untuk biaya bank"]})
    cands.sort(key=lambda c: (-c["score"], c["label"]))
    return {"txn": txn, "candidates": cands,
            "state": ("empty" if not [c for c in cands if c["score"] >= 25] else "filled"),
            "note": ("Tidak ada kandidat yang meyakinkan — mutasi ini tetap 'belum cocok' "
                     "sampai ada dokumen yang sesuai." if not [c for c in cands
                                                               if c["score"] >= 25] else None)}


async def _apply(org: str, txn: dict, kind: str, target_id: str, actor: str,
                 note: str = None) -> dict:
    """Jalankan dampak pencocokan lewat JALUR RESMI masing-masing subledger."""
    amount = int(txn["amount"])
    memo = note or f"Rekonsiliasi bank {txn['date']} — {txn.get('description')}"
    acc = await db.bank_accounts.find_one({"id": txn.get("account_id"), "org_id": org}, {"_id": 0})
    acc_id = (acc or {}).get("id")
    bank_code = (acc or {}).get("gl_account_code") or GL_BANK
    if kind == "ar_deal":
        res = await fin.apply_receipt(target_id, amount, "transfer", memo, actor, org_id=org,
                                      cash_account_id=acc_id)
        return {"receipt_id": res["receipt"]["id"], "deal_id": target_id,
                "detail": f"Kuitansi {res['receipt']['id'][:8]} dibuat dari mutasi bank."}
    if kind == "payment_intake":
        import payment_intake as intake
        res = await intake.verify(org, target_id, actor, bank_txn_id=txn["id"], note=memo)
        return {"receipt_id": (res.get("receipt") or {}).get("id"),
                "intake_id": target_id, "deal_id": res["intake"].get("deal_id"),
                "detail": "Bukti transfer pelanggan diverifikasi lewat rekonsiliasi."}
    if kind == "ap_bill":
        await fin.pay_ap_bill(target_id, amount, memo, actor, org_id=org, cash_account_id=acc_id)
        return {"bill_id": target_id, "detail": "Pembayaran tagihan vendor dicatat."}
    if kind == "labor_payroll":
        import labor_engine as labor
        await labor.pay_payroll(org, target_id, actor, bank_txn_id=txn["id"], note=memo)
        return {"payroll_id": target_id, "detail": "Pembayaran upah dicatat."}
    if kind == "bank_fee":
        je = await gl.post_journal(org, f"Biaya bank — {txn.get('description')}", [
            {"account_code": GL_BANK_FEE, "debit": amount, "credit": 0},
            {"account_code": bank_code, "debit": 0, "credit": amount}],
            date=txn["date"], source_type="bank_txn", source_id=txn["id"],
            source_event=f"bank.fee:{txn['id']}", posted_by=actor, auto=False)
        return {"journal_id": je["id"], "detail": f"Jurnal {je['entry_no']} (beban bank)."}
    if kind == "bank_interest":
        je = await gl.post_journal(org, f"Jasa giro — {txn.get('description')}", [
            {"account_code": bank_code, "debit": amount, "credit": 0},
            {"account_code": GL_OTHER_INCOME, "debit": 0, "credit": amount}],
            date=txn["date"], source_type="bank_txn", source_id=txn["id"],
            source_event=f"bank.interest:{txn['id']}", posted_by=actor, auto=False)
        return {"journal_id": je["id"], "detail": f"Jurnal {je['entry_no']} (jasa giro)."}
    raise ValueError(f"Jenis pencocokan '{kind}' belum didukung.")


async def match(org: str = ORG_ID, txn_id: str = None, kind: str = None,
                target_id: str = None, actor: str = "system", note: str = None) -> dict:
    """Cocokkan satu mutasi ke satu dokumen. Menolak bila mutasi sudah dipakai."""
    txn = await txn_or_error(org, txn_id)
    if txn.get("match_state") == "matched":
        raise ValueError("Mutasi ini sudah dicocokkan — batalkan dulu bila salah.")
    if txn.get("match_state") == "ignored":
        raise ValueError("Mutasi ini ditandai diabaikan — batalkan tanda itu lebih dulu.")
    if kind in ("ar_deal", "payment_intake", "ap_bill", "labor_payroll") and not target_id:
        raise ValueError(f"Pencocokan '{MATCH_KIND_LABEL.get(kind, kind)}' butuh dokumen tujuan.")
    wants_in = kind in ("ar_deal", "payment_intake", "bank_interest")
    if wants_in != (txn["direction"] == "in"):
        raise ValueError("Arah mutasi tidak cocok dengan jenis dokumen yang dipilih "
                         f"(mutasi ini {'uang masuk' if txn['direction'] == 'in' else 'uang keluar'}).")
    out = await _apply(org, txn, kind, target_id, actor, note)
    ts = now_iso()
    doc = {"id": new_id(), "org_id": org, "txn_id": txn["id"], "account_id": txn["account_id"],
           "kind": kind, "kind_label": MATCH_KIND_LABEL[kind], "target_id": target_id,
           "amount": int(txn["amount"]), "direction": txn["direction"], "note": note,
           "result": out, "state": "matched", "matched_by": actor, "created_at": ts,
           "reversed_at": None, "reversed_by": None, "reverse_reason": None}
    await db.bank_matches.insert_one(dict(doc))
    await db.bank_transactions.update_one({"id": txn["id"]}, {"$set": {
        "match_state": "matched", "match_id": doc["id"], "match_kind": kind,
        "matched_at": ts, "matched_by": actor, "updated_at": ts}})
    await emit("bank.matched", "bank_txn", txn["id"],
              {"kind": kind, "amount": int(txn["amount"])}, org_id=org)
    doc.pop("_id", None)
    return {"match": doc, "txn": await txn_or_error(org, txn["id"]),
            "message": out.get("detail")}


async def void_receipt(org: str, receipt_id: str, actor: str, reason: str) -> dict:
    """Batalkan satu kuitansi penerimaan: alokasi dikembalikan + jurnal pembalik.

    Ini satu-satunya jalur pembatalan penerimaan di sistem, jadi ia harus jujur: item termin
    dikembalikan PERSIS sebesar alokasi yang tercatat pada kuitansi (bukan ditebak ulang),
    kewajiban kontrak diturunkan, lalu jurnal pembalik diposting sehingga saldo bank di GL
    kembali seperti sebelum uang itu diakui.
    """
    if len((reason or "").strip()) < MIN_REASON:
        raise ValueError(f"Alasan pembatalan minimal {MIN_REASON} huruf.")
    rec = await db.receipts.find_one({"id": receipt_id, "org_id": org}, {"_id": 0})
    if not rec:
        raise ValueError("Kuitansi tidak ditemukan.")
    if rec.get("status") == "void":
        raise ValueError("Kuitansi ini sudah dibatalkan.")
    if int(rec.get("deposit_amount") or 0) > 0:
        raise ValueError("Kuitansi ini melahirkan TITIPAN pelanggan — batalkan dari layar "
                         "Titipan agar saldo titipan tetap benar.")
    inv = await db.ar_invoices.find_one({"org_id": org, "deal_id": rec["deal_id"]}, {"_id": 0})
    if not inv:
        raise ValueError("Jadwal AR tidak ditemukan untuk kuitansi ini.")
    items = inv["items"]
    by_id = {i["id"]: i for i in items}
    for alloc in rec.get("allocations") or []:
        it = by_id.get(alloc["item_id"])
        if not it:
            continue
        it["paid_amount"] = max(0, int(it.get("paid_amount") or 0) - int(alloc["amount"]))
        it["status"] = ("paid" if it["paid_amount"] >= it["amount"]
                        else ("partial" if it["paid_amount"] > 0 else "unpaid"))
    ts = now_iso()
    paid, outstanding, status = await fin._recalc_invoice(inv, items, ts)  # noqa: SLF001
    applied = int(rec.get("applied") or rec.get("amount") or 0)
    if applied > 0:
        await db.contract_liabilities.update_one(
            {"org_id": org, "deal_id": rec["deal_id"]},
            {"$inc": {"balance": -applied}, "$set": {"updated_at": ts}})
        await gl.post_journal(org, f"Pembatalan penerimaan — {reason.strip()[:80]}", [
            {"account_code": GL_CONTRACT_LIABILITY, "debit": applied, "credit": 0},
            {"account_code": rec.get("cash_account_code") or GL_BANK, "debit": 0, "credit": applied}],
            source_type="receipt_void", source_id=receipt_id,
            source_event=f"receipt.void:{receipt_id}", posted_by=actor, auto=False)
    await db.receipts.update_one({"id": receipt_id}, {"$set": {
        "status": "void", "void_reason": reason.strip(), "void_by": actor, "void_at": ts}})
    await add_activity(entity_type="deal", entity_id=rec["deal_id"], type="finance",
                       actor=actor, org_id=org,
                       body=(f"Penerimaan Rp {applied:,} DIBATALKAN — {reason.strip()}"
                             .replace(",", ".")))
    return {"receipt_id": receipt_id, "applied_reversed": applied,
            "invoice": {"paid": paid, "outstanding": outstanding, "status": status}}


async def unmatch(org: str = ORG_ID, txn_id: str = None, actor: str = "system",
                  reason: str = None) -> dict:
    """Batalkan pencocokan + balikkan dampaknya (beralasan, berjejak)."""
    if len((reason or "").strip()) < MIN_REASON:
        raise ValueError(f"Alasan pembatalan minimal {MIN_REASON} huruf.")
    txn = await txn_or_error(org, txn_id)
    if txn.get("match_state") != "matched" or not txn.get("match_id"):
        raise ValueError("Mutasi ini belum dicocokkan.")
    m = await db.bank_matches.find_one({"id": txn["match_id"], "org_id": org}, {"_id": 0})
    if not m:
        raise ValueError("Catatan pencocokan tidak ditemukan.")
    if m["kind"] not in UNMATCHABLE_KINDS:
        raise ValueError(
            f"Pencocokan '{m.get('kind_label')}' tidak bisa dibatalkan dari layar "
            "rekonsiliasi karena menyentuh dokumen lain. Batalkan dari halaman "
            "asalnya (tagihan vendor / rekap upah) agar tidak ada dua kebenaran.")
    ts = now_iso()
    detail = {}
    if m["kind"] in ("ar_deal", "payment_intake"):
        rid = (m.get("result") or {}).get("receipt_id")
        if rid:
            detail = await void_receipt(org, rid, actor, reason)
        if m["kind"] == "payment_intake":
            import payment_intake as intake
            await intake.revert_verification(org, m["target_id"], actor, reason)
    else:
        jid = (m.get("result") or {}).get("journal_id")
        je = await db.journal_entries.find_one({"id": jid, "org_id": org}, {"_id": 0}) if jid \
            else None
        if je:
            rev = [{"account_code": ln["account_code"], "debit": ln["credit"],
                    "credit": ln["debit"]} for ln in je["lines"]]
            back = await gl.post_journal(
                org, f"Pembalikan {je['entry_no']} — {reason.strip()[:70]}", rev,
                date=je.get("date"), source_type="bank_txn_void", source_id=txn["id"],
                source_event=f"bank.unmatch:{m['id']}", posted_by=actor, auto=False)
            detail = {"reversal_entry": back["entry_no"]}
    await db.bank_matches.update_one({"id": m["id"]}, {"$set": {
        "state": "reversed", "reversed_at": ts, "reversed_by": actor,
        "reverse_reason": reason.strip(), "reverse_detail": detail}})
    await db.bank_transactions.update_one({"id": txn["id"]}, {"$set": {
        "match_state": "unmatched", "match_id": None, "match_kind": None,
        "matched_at": None, "matched_by": None, "updated_at": ts},
        "$push": {"history": {"at": ts, "by": actor, "action": "unmatch",
                              "reason": reason.strip(), "kind": m["kind"]}}})
    await emit("bank.unmatched", "bank_txn", txn["id"], {"kind": m["kind"]}, org_id=org)
    return {"txn": await txn_or_error(org, txn["id"]), "reversed": detail,
            "message": "Pencocokan dibatalkan dan dampaknya dibalik."}


async def ignore(org: str, txn_id: str, actor: str, reason: str) -> dict:
    """Tandai mutasi yang memang bukan urusan perusahaan — tetap terlihat & beralasan."""
    if len((reason or "").strip()) < MIN_REASON:
        raise ValueError(f"Alasan minimal {MIN_REASON} huruf.")
    txn = await txn_or_error(org, txn_id)
    if txn.get("match_state") == "matched":
        raise ValueError("Mutasi sudah dicocokkan — batalkan pencocokan lebih dulu.")
    ts = now_iso()
    await db.bank_transactions.update_one({"id": txn_id}, {"$set": {
        "match_state": "ignored", "ignore_reason": reason.strip(), "updated_at": ts,
        "matched_by": actor}, "$push": {"history": {"at": ts, "by": actor,
                                                    "action": "ignore",
                                                    "reason": reason.strip()}}})
    return await txn_or_error(org, txn_id)


def _rp(value) -> str:
    """Format rupiah gaya Indonesia (1.500.000).

    Ditulis sebagai fungsi karena pola lama `f"...{x:,}...".replace(",", ".")` MENGUBAH
    KOMA KALIMAT menjadi titik, sehingga pesan penyebab selisih terbaca sebagai kumpulan
    kalimat terpotong ("...rekening. transaksi kas lain..."). Yang diformat seharusnya
    ANGKANYA, bukan seluruh kalimat.
    """
    return f"Rp {int(value or 0):,}".replace(",", ".")


async def reconciliation(org: str = ORG_ID, account_id: str = None) -> dict:
    """Ringkasan rekonsiliasi: saldo buku (GL) vs saldo rekening + selisih + penyebabnya."""
    acc = await db.bank_accounts.find_one({"id": account_id, "org_id": org}, {"_id": 0}) \
        if account_id else None
    txns = await db.bank_transactions.find(
        {"org_id": org, **({"account_id": account_id} if account_id else {})},
        {"_id": 0}).sort("date", -1).to_list(2000)
    unmatched = [t for t in txns if t.get("match_state") == "unmatched"]
    ignored = [t for t in txns if t.get("match_state") == "ignored"]
    balances = await gl.account_balances(org)
    code = (acc or {}).get("gl_account_code") or GL_BANK
    book = int((balances.get(code) or {}).get("balance") or 0)
    with_balance = [t for t in txns if t.get("balance") is not None]
    latest = sorted(with_balance, key=lambda t: (t["date"], t.get("created_at") or ""))[-1] \
        if with_balance else None
    statement_balance = int(latest["balance"]) if latest else None
    unmatched_in = sum(int(t["amount"]) for t in unmatched if t["direction"] == "in")
    unmatched_out = sum(int(t["amount"]) for t in unmatched if t["direction"] == "out")
    missing = []
    if statement_balance is None:
        # JUJUR: tanpa kolom saldo, selisih tidak bisa dihitung — jangan tulis 0.
        missing.append("saldo_rekening")
    causes = []
    if unmatched:
        causes.append({"code": "unmatched", "count": len(unmatched),
                       "amount": unmatched_in - unmatched_out,
                       "detail": (f"{len(unmatched)} mutasi belum dicocokkan "
                                  f"(masuk {_rp(unmatched_in)}, keluar {_rp(unmatched_out)})")})
    # Selisih yang TIDAK dijelaskan oleh mutasi belum cocok harus DIKATAKAN, bukan dibiarkan
    # tersembunyi di balik satu angka besar. Tanpa baris ini layar rekonsiliasi memancing
    # kesimpulan salah ("selisihnya karena belum dicocokkan") padahal sisanya bisa berasal
    # dari kas/bank lain yang memakai akun GL sama, saldo awal yang belum dicatat, atau
    # transaksi yang belum pernah masuk rekening.
    unexplained = None
    if statement_balance is not None:
        unexplained = statement_balance - (book + unmatched_in - unmatched_out)
        if unexplained:
            causes.append({
                "code": "unexplained", "count": None, "amount": unexplained,
                "detail": (f"{_rp(abs(unexplained))} BELUM bisa dijelaskan oleh mutasi yang "
                           "belum dicocokkan — telusuri saldo awal rekening, transaksi kas "
                           f"lain pada akun {code}, atau mutasi yang belum diimpor.")})
    return {
        "account": acc, "gl_account_code": code, "book_balance": book,
        "statement_balance": statement_balance,
        "statement_balance_at": (latest or {}).get("date"),
        "difference": (None if statement_balance is None else statement_balance - book),
        "unexplained": unexplained,
        "unmatched_count": len(unmatched), "unmatched_in": unmatched_in,
        "unmatched_out": unmatched_out, "ignored_count": len(ignored),
        "matched_count": len([t for t in txns if t.get("match_state") == "matched"]),
        "txn_total": len(txns), "missing": missing,
        "causes": causes,
        "as_of": now_iso(),
    }
