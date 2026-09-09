"""Pembiayaan korporat: kredit bank / leasing + jadwal & monitoring angsuran
(Fase 27 — menutup gap kompetitor #8).

Jurnal (idempoten via `source_event`):
    Pencairan  Dr 1-1200 Bank (netto) + Dr 6-1600 (provisi)  / Cr 2-2100 Utang Bank/Leasing
    Angsuran   Dr 2-2100 (porsi pokok) + Dr 6-1600 (bunga)   / Cr 1-1200 Bank | 1-1100 Kas

Invarian: 2-2100 = Σ (pokok − pokok terbayar) fasilitas aktif; Σ jadwal.pokok = pokok
fasilitas TEPAT (angsuran terakhir menyerap pembulatan).
"""
import logging

import gl_engine as gl
import sequences as seq
from core_utils import new_id, now_iso
from db import db, ORG_ID
from engine import add_activity, auto_create_task
from finance_engine import notify_finance
from p27_utils import (cash_account, current_period, days_overdue, month_add, period_of, rp)

logger = logging.getLogger("sipro.loans")
LOAN_ACC = "2-2100"
INTEREST_ACC = "6-1600"


async def _get(loan_id: str, org_id: str) -> dict:
    doc = await db.loans.find_one({"id": loan_id, "org_id": org_id}, {"_id": 0})
    if not doc:
        raise ValueError("Fasilitas pembiayaan tidak ditemukan.")
    return doc


def build_schedule(principal: int, annual_rate_pct: float, tenor: int, method: str,
                   start_date: str) -> list:
    """Bangkitkan jadwal angsuran integer. Σ pokok DIJAMIN == principal."""
    principal = int(principal)
    tenor = int(tenor)
    i = float(annual_rate_pct or 0) / 1200.0
    flat_base = principal // tenor
    flat_interest = round(principal * i) if i else 0
    annuity = 0
    if method == "anuitas" and i > 0:
        annuity = round(principal * i / (1 - (1 + i) ** (-tenor)))
    balance = principal
    rows = []
    for k in range(1, tenor + 1):
        interest = round(balance * i) if i else 0
        if method == "flat":
            interest = flat_interest
        if k == tenor:
            princ = balance
        elif method == "anuitas":
            princ = (annuity - interest) if i > 0 else flat_base
            princ = max(0, min(int(princ), balance))
        else:  # pokok_tetap & flat: pokok rata
            princ = min(flat_base, balance)
        balance -= princ
        rows.append({
            "no": k, "due_date": month_add(start_date, k), "principal": int(princ),
            "interest": int(interest), "total": int(princ) + int(interest),
            "paid_principal": 0, "paid_interest": 0, "paid_total": 0,
            "status": "unpaid", "paid_at": None,
        })
    return rows


async def create_loan(payload, actor: str, org_id=ORG_ID) -> dict:
    if int(payload.provision_fee or 0) >= int(payload.principal):
        raise ValueError("Biaya provisi tidak boleh sebesar atau melebihi pokok pinjaman.")
    ts = now_iso()
    no = await seq.next_number("loan", org_id, prefix="PBY", width=4)
    doc = {
        "id": new_id(), "org_id": org_id, "no": no, "status": "draft",
        "lender": payload.lender, "lender_type": payload.lender_type,
        "loan_type": payload.loan_type, "principal": int(payload.principal),
        "interest_rate_pct": float(payload.interest_rate_pct),
        "tenor_months": int(payload.tenor_months),
        "amortization_method": payload.amortization_method,
        "start_date": payload.start_date or ts, "provision_fee": int(payload.provision_fee or 0),
        "collateral": payload.collateral, "note": payload.note,
        "schedule": [], "paid_principal": 0, "paid_interest": 0,
        "outstanding_principal": 0, "disbursed_at": None, "activated_by": None,
        "journal_ids": [], "created_by": actor, "created_at": ts, "updated_at": ts,
    }
    await db.loans.insert_one(dict(doc))
    doc.pop("_id", None)
    await add_activity(entity_type="loan", entity_id=doc["id"], type="system",
                       body=f"Fasilitas {no} dari {payload.lender} {rp(payload.principal)} "
                            f"({payload.tenor_months} bln, {payload.interest_rate_pct}%/th) dicatat.",
                       actor=actor, org_id=org_id)
    return doc


async def activate_loan(loan_id: str, source: str, date, note, actor: str,
                        org_id=ORG_ID) -> dict:
    """Pencairan fasilitas: kas masuk (netto provisi), utang bank terbentuk, jadwal terbit."""
    loan = await _get(loan_id, org_id)
    if loan["status"] != "draft":
        raise ValueError("Hanya fasilitas berstatus 'Draf' yang dapat dicairkan.")
    principal = int(loan["principal"])
    provision = int(loan.get("provision_fee", 0))
    net = principal - provision
    ts = now_iso()
    start = date or loan.get("start_date") or ts
    rows = build_schedule(principal, loan["interest_rate_pct"], loan["tenor_months"],
                          loan["amortization_method"], start)
    if sum(r["principal"] for r in rows) != principal:
        raise ValueError("Kesalahan internal: jumlah pokok jadwal tidak sama dengan pokok pinjaman.")
    lines = [{"account_code": cash_account(source), "debit": net, "credit": 0,
              "memo": "pencairan fasilitas"}]
    if provision:
        lines.append({"account_code": INTEREST_ACC, "debit": provision, "credit": 0,
                      "memo": "biaya provisi & administrasi"})
    lines.append({"account_code": LOAN_ACC, "debit": 0, "credit": principal})
    je = await gl.post_journal(
        org_id, f"Pencairan pembiayaan {loan['no']} — {loan['lender']}", lines,
        date=start, source_type="loan", source_id=loan_id,
        source_event=f"loan.activate:{loan_id}", posted_by=actor)
    await db.loans.update_one({"id": loan_id}, {"$set": {
        "status": "active", "schedule": rows, "outstanding_principal": principal,
        "disbursed_at": start, "activated_by": actor, "activate_note": note,
        "start_date": start, "updated_at": ts}, "$push": {"journal_ids": je["id"]}})
    await add_activity(entity_type="loan", entity_id=loan_id, type="system",
                       body=f"Fasilitas {loan['no']} dicairkan {rp(net)} (provisi {rp(provision)}). "
                            f"{len(rows)} angsuran terjadwal. Jurnal {je['entry_no']}.",
                       actor=actor, org_id=org_id)
    await notify_finance(org_id, "Pembiayaan dicairkan",
                         f"{loan['lender']} — {loan['no']} {rp(principal)} cair, angsuran "
                         f"pertama jatuh tempo {rows[0]['due_date'][:10]}.",
                         "finance", "loan", loan_id)
    return await _get(loan_id, org_id)


async def pay_installment(loan_id: str, no: int, amount: int, source: str, date, note,
                          actor: str, org_id=ORG_ID) -> dict:
    """Bayar angsuran: alokasi ke bunga dulu, sisanya pokok (mengurangi utang bank)."""
    loan = await _get(loan_id, org_id)
    if loan["status"] != "active":
        raise ValueError("Angsuran hanya dapat dibayar untuk fasilitas berstatus 'Aktif'.")
    rows = list(loan.get("schedule") or [])
    idx = next((k for k, r in enumerate(rows) if int(r["no"]) == int(no)), None)
    if idx is None:
        raise ValueError(f"Angsuran nomor {no} tidak ada pada jadwal fasilitas ini.")
    item = rows[idx]
    remaining = int(item["total"]) - int(item.get("paid_total", 0))
    if remaining <= 0:
        raise ValueError(f"Angsuran ke-{no} sudah lunas.")
    amount = int(amount)
    if amount > remaining:
        raise ValueError(f"Pembayaran {rp(amount)} melebihi sisa angsuran ke-{no} "
                         f"sebesar {rp(remaining)}.")
    rem_interest = int(item["interest"]) - int(item.get("paid_interest", 0))
    pay_interest = min(amount, max(0, rem_interest))
    pay_principal = amount - pay_interest
    ts = now_iso()
    payment_id = new_id()
    lines = []
    if pay_principal:
        lines.append({"account_code": LOAN_ACC, "debit": pay_principal, "credit": 0,
                      "memo": "pokok angsuran"})
    if pay_interest:
        lines.append({"account_code": INTEREST_ACC, "debit": pay_interest, "credit": 0,
                      "memo": "bunga angsuran"})
    lines.append({"account_code": cash_account(source), "debit": 0, "credit": amount})
    je = await gl.post_journal(
        org_id, f"Angsuran ke-{no} pembiayaan {loan['no']} — {loan['lender']}", lines,
        date=date or ts, source_type="loan_payment", source_id=payment_id,
        source_event=f"loan.pay:{payment_id}", posted_by=actor)
    item["paid_principal"] = int(item.get("paid_principal", 0)) + pay_principal
    item["paid_interest"] = int(item.get("paid_interest", 0)) + pay_interest
    item["paid_total"] = int(item.get("paid_total", 0)) + amount
    item["status"] = "paid" if item["paid_total"] >= int(item["total"]) else "partial"
    item["paid_at"] = ts if item["status"] == "paid" else item.get("paid_at")
    rows[idx] = item
    paid_principal = sum(int(r.get("paid_principal", 0)) for r in rows)
    paid_interest = sum(int(r.get("paid_interest", 0)) for r in rows)
    outstanding = int(loan["principal"]) - paid_principal
    status = "paid_off" if all(r["status"] == "paid" for r in rows) else "active"
    await db.loans.update_one({"id": loan_id}, {"$set": {
        "schedule": rows, "paid_principal": paid_principal, "paid_interest": paid_interest,
        "outstanding_principal": outstanding, "status": status, "updated_at": ts},
        "$push": {"journal_ids": je["id"]}})
    await db.loan_payments.insert_one({
        "id": payment_id, "org_id": org_id, "loan_id": loan_id, "loan_no": loan["no"],
        "lender": loan["lender"], "installment_no": int(no), "amount": amount,
        "principal_part": pay_principal, "interest_part": pay_interest, "source": source,
        "note": note, "journal_id": je["id"], "entry_no": je["entry_no"],
        "paid_by": actor, "paid_at": date or ts, "created_at": ts})
    await add_activity(entity_type="loan", entity_id=loan_id, type="system",
                       body=f"Angsuran ke-{no} dibayar {rp(amount)} (pokok {rp(pay_principal)}, "
                            f"bunga {rp(pay_interest)}). Sisa pokok {rp(outstanding)}.",
                       actor=actor, org_id=org_id)
    if status == "paid_off":
        await notify_finance(org_id, "Fasilitas pembiayaan lunas",
                             f"{loan['lender']} — {loan['no']} telah lunas.",
                             "finance", "loan", loan_id)
    return await _get(loan_id, org_id)


def annotate_schedule(rows: list) -> list:
    """Tambahkan `amount_due` (sisa angsuran) saat menyajikan jadwal.

    Field turunan (tidak disimpan) agar tidak ada dua sumber kebenaran: konsumen API
    tidak perlu menghitung sendiri `total − paid_total`, sehingga tidak salah kirim
    nominal saat membayar angsuran.
    """
    out = []
    for r in rows or []:
        item = dict(r)
        item["amount_due"] = int(item.get("total", 0)) - int(item.get("paid_total", 0))
        out.append(item)
    return out


def loan_metrics(loan: dict) -> dict:
    rows = loan.get("schedule") or []
    unpaid = [r for r in rows if r["status"] != "paid"]
    overdue = [r for r in unpaid if days_overdue(r["due_date"]) > 0]
    nxt = unpaid[0] if unpaid else None
    return {
        "next_due_date": (nxt or {}).get("due_date"),
        "next_due_amount": int((nxt or {}).get("total", 0)) - int((nxt or {}).get("paid_total", 0)),
        "next_installment_no": (nxt or {}).get("no"),
        "overdue_count": len(overdue),
        "overdue_amount": sum(int(r["total"]) - int(r.get("paid_total", 0)) for r in overdue),
        "installments_paid": sum(1 for r in rows if r["status"] == "paid"),
        "installments_total": len(rows),
        "interest_remaining": sum(int(r["interest"]) - int(r.get("paid_interest", 0))
                                  for r in rows),
    }


async def summary(org_id=ORG_ID) -> dict:
    loans = await db.loans.find({"org_id": org_id}, {"_id": 0}).to_list(2000)
    active = [l for l in loans if l["status"] == "active"]
    period = current_period()
    due_this_month, overdue_amount, overdue_count = 0, 0, 0
    for l in active:
        for r in l.get("schedule") or []:
            rem = int(r["total"]) - int(r.get("paid_total", 0))
            if rem <= 0:
                continue
            if period_of(r["due_date"]) == period:
                due_this_month += rem
            if days_overdue(r["due_date"]) > 0:
                overdue_amount += rem
                overdue_count += 1
    return {
        "count": len(loans), "active_count": len(active),
        "paid_off_count": sum(1 for l in loans if l["status"] == "paid_off"),
        "draft_count": sum(1 for l in loans if l["status"] == "draft"),
        "outstanding_principal": sum(int(l.get("outstanding_principal", 0)) for l in active),
        "principal_total": sum(int(l["principal"]) for l in active),
        "interest_paid_total": sum(int(l.get("paid_interest", 0)) for l in loans),
        "due_this_month": due_this_month, "overdue_amount": overdue_amount,
        "overdue_count": overdue_count, "current_period": period,
        "loan_account": LOAN_ACC, "interest_account": INTEREST_ACC,
    }


async def installment_reminder(org_id=ORG_ID) -> int:
    """Ingatkan finance untuk angsuran jatuh tempo ≤7 hari / terlambat (idempoten)."""
    loans = await db.loans.find({"org_id": org_id, "status": "active"}, {"_id": 0}).to_list(500)
    hit = 0
    for l in loans:
        for r in l.get("schedule") or []:
            if r["status"] == "paid":
                continue
            aging = days_overdue(r["due_date"])
            if aging < -7:
                continue
            task = await auto_create_task(
                source_event=f"loan_due:{l['id']}:{r['no']}",
                title=f"Bayar angsuran ke-{r['no']} — {l['lender']} ({l['no']})",
                type="follow_up", related_entity_type="loan", related_entity_id=l["id"],
                due_date=r["due_date"], priority="urgent" if aging > 0 else "high",
                description=f"Angsuran {rp(r['total'])} jatuh tempo {r['due_date'][:10]}"
                            + (f" (terlambat {aging} hari)" if aging > 0 else ""),
                org_id=org_id)
            if task:
                hit += 1
                await notify_finance(
                    org_id, "Angsuran pembiayaan jatuh tempo",
                    f"{l['lender']} {l['no']} angsuran ke-{r['no']} {rp(r['total'])} "
                    f"jatuh tempo {r['due_date'][:10]}.", "finance", "loan", l["id"])
            break  # cukup satu pengingat per fasilitas per siklus
    return hit
