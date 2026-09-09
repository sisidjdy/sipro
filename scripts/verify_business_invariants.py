#!/usr/bin/env python3
"""verify_business_invariants.py — gate INVARIAN BISNIS (uang & status).

`verify_data_integrity.py` menjaga bentuk data (FK, tipe, integer). Gate ini
menjaga **kebenaran logika**: apakah angka & status saling konsisten antar
subledger dan buku besar.

Cakupan:
  AR   paid = Σ item.paid_amount = Σ receipts.applied ; outstanding = total - paid ;
       status item konsisten (unpaid/partial/paid) ; tidak ada item paid_amount > amount
  AP   retention_held = round(claimed × pct%) ; net = claimed - retention ;
       paid = Σ payments_out ; outstanding = net - paid ; status konsisten
  KOM  amount = round(base × rate%) ; approved/paid punya jejak approver
  KPR  disbursed_total = Σ disbursements ≤ plafon ; status selaras hasil SLIK
  UNIT unit.status ↔ deal (reserved/booked/sold) dua arah, tidak ada hold hantu
  GL   2-1400 Uang Muka = Σ contract_liabilities.balance (belum diakui)
       2-1100 Utang Usaha = Σ (net - paid) tagihan yang sudah disetujui
       2-1200 Utang Retensi = Σ retensi tagihan disetujui yang belum dilepas
       2-1600 Utang Komisi = Σ komisi approved yang belum dibayar
Exit != 0 bila ada pelanggaran.
"""
import os
import sys

from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv("/app/backend/.env")
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
errors, warns = [], []


def err(m):
    errors.append(m)
    print(f"  [ERROR] {m}")


def warn(m):
    warns.append(m)
    print(f"  [WARN] {m}")


def ok(m):
    print(f"  [OK] {m}")


def head(t):
    print(f"\n{t}\n" + "-" * len(t))


def gl_balance(code):
    """Saldo akun (sisi normal) dari journal_entries."""
    dr = cr = 0
    for je in db.journal_entries.find({}, {"_id": 0, "lines": 1}):
        for ln in je.get("lines", []):
            if ln.get("account_code") == code:
                dr += int(ln.get("debit", 0) or 0)
                cr += int(ln.get("credit", 0) or 0)
    return dr, cr


def check_ar():
    head("AR — jadwal termin, penerimaan, dan status")
    invs = list(db.ar_invoices.find({}, {"_id": 0}))
    if not invs:
        ok("belum ada AR (lewati)")
        return
    for inv in invs:
        items = inv.get("items") or []
        tag = f"AR {inv.get('unit_code') or inv['id'][:6]}"
        item_paid = sum(int(i.get("paid_amount", 0) or 0) for i in items)
        total = int(inv.get("total", 0) or 0)
        paid = int(inv.get("paid", 0) or 0)
        outstanding = int(inv.get("outstanding", 0) or 0)
        # Fase 56: AR yang DIBATALKAN sah berbeda bentuknya — termin yang belum dibayar
        # ditutup tanpa pernah dibayar, jadi `outstanding` 0 sementara `total > paid`.
        # Menuntut status "paid" di situ memaksa sistem berbohong bahwa pembeli melunasi
        # rumah yang justru ia batalkan.
        if inv.get("status") == "cancelled":
            if not inv.get("cancellation_id"):
                err(f"{tag}: invoice 'cancelled' tanpa `cancellation_id` (tidak bisa "
                    "dipertanggungjawabkan ke pengajuan pembatalan mana)")
            if outstanding != 0:
                err(f"{tag}: invoice dibatalkan tetapi outstanding {outstanding:,} != 0")
            if paid != item_paid:
                err(f"{tag}: paid={paid:,} != Σ item.paid_amount={item_paid:,}")
            for i in items:
                amt, pd = int(i.get("amount", 0)), int(i.get("paid_amount", 0) or 0)
                harap = "paid" if pd >= amt and amt > 0 else "cancelled"
                if i.get("status") != harap:
                    err(f"{tag}/{i.get('label')}: status '{i.get('status')}' pada AR "
                        f"dibatalkan seharusnya '{harap}'")
            continue
        if paid != item_paid:
            err(f"{tag}: paid={paid:,} != Σ item.paid_amount={item_paid:,}")
        if outstanding != total - paid:
            err(f"{tag}: outstanding={outstanding:,} != total-paid={total - paid:,}")
        if sum(int(i.get("amount", 0)) for i in items) != total:
            err(f"{tag}: Σ item.amount != total ({total:,})")
        for i in items:
            amt, pd = int(i.get("amount", 0)), int(i.get("paid_amount", 0) or 0)
            if pd > amt:
                err(f"{tag}/{i.get('label')}: paid_amount {pd:,} > amount {amt:,} (kelebihan bayar tak tercatat)")
            # Fase 58: denda yang DIRINGANKAN Manajer Keuangan bernilai 0 dan berstatus
            # `cancelled` — ia bukan "tagihan Rp 0 yang belum dibayar". Jejaknya (nominal
            # semula, alasan, jurnal balik) tetap ada di baris itu, jadi keringanan bisa
            # diaudit tanpa menyamarkannya sebagai tagihan biasa.
            expect = "cancelled" if i.get("waived") else (
                "paid" if pd >= amt and amt > 0 else ("partial" if pd > 0 else "unpaid"))
            if i.get("status") != expect:
                err(f"{tag}/{i.get('label')}: status '{i.get('status')}' seharusnya '{expect}'")
        rec_applied = sum(int(r.get("applied", 0) or 0)
                          for r in db.receipts.find({"deal_id": inv["deal_id"]}, {"_id": 0, "applied": 1}))
        if rec_applied != paid:
            err(f"{tag}: Σ receipts.applied={rec_applied:,} != invoice.paid={paid:,}")
        rec_amount = sum(int(r.get("amount", 0) or 0)
                         for r in db.receipts.find({"deal_id": inv["deal_id"]},
                                                   {"_id": 0, "amount": 1}))
        # Fase 26: kas yang diterima = yang teralokasi ke termin + yang masuk titipan.
        # Penerimaan berdana titipan (funding="deposit") TIDAK membawa kas baru (amount=0).
        cash_recs = [r for r in db.receipts.find({"deal_id": inv["deal_id"]}, {"_id": 0})
                     if (r.get("funding") or "cash") == "cash"]
        dep_recs = [r for r in db.receipts.find({"deal_id": inv["deal_id"]}, {"_id": 0})
                    if r.get("funding") == "deposit"]
        cash_in = sum(int(r.get("amount", 0) or 0) for r in cash_recs)
        cash_expected = sum(int(r.get("applied", 0) or 0) + int(r.get("deposit_amount", 0) or 0)
                            for r in cash_recs)
        if cash_in != cash_expected:
            err(f"{tag}: kas diterima {cash_in:,} != teralokasi+titipan {cash_expected:,} "
                f"-> selisih {cash_in - cash_expected:,} HILANG (kelebihan bayar tidak dibukukan)")
        for r in dep_recs:
            if int(r.get("amount", 0) or 0) != 0:
                err(f"{tag}: penerimaan dari titipan {r['id'][:6]} mencatat kas {r.get('amount'):,} "
                    f"(seharusnya 0 — tidak ada uang baru masuk)")
        if rec_amount < 0:
            err(f"{tag}: total kas penerimaan negatif ({rec_amount:,})")
        expect_inv = "paid" if outstanding <= 0 else ("partial" if paid > 0 else "unpaid")
        if inv.get("status") != expect_inv:
            err(f"{tag}: status invoice '{inv.get('status')}' seharusnya '{expect_inv}'")
    if not errors:
        ok(f"{len(invs)} AR konsisten (item, penerimaan, status)")


def check_ap():
    head("AP — retensi, pembayaran, status")
    bills = list(db.ap_invoices.find({}, {"_id": 0}))
    if not bills:
        ok("belum ada AP (lewati)")
        return
    bad = 0
    for b in bills:
        tag = f"AP {b.get('vendor')} {b['id'][:6]}"
        claimed = int(b.get("claimed", 0))
        pct = float(b.get("retention_pct", 0) or 0)
        held = int(b.get("retention_held", 0) or 0)
        net = int(b.get("net", 0) or 0)
        paid = int(b.get("paid", 0) or 0)
        outstanding = int(b.get("outstanding", 0) or 0)
        if held != round(claimed * pct / 100):
            err(f"{tag}: retensi {held:,} != round({claimed:,}×{pct}%)"); bad += 1
        if net != claimed - held:
            err(f"{tag}: net {net:,} != claimed-retensi {claimed - held:,}"); bad += 1
        if paid > net:
            err(f"{tag}: paid {paid:,} > net {net:,}"); bad += 1
        if outstanding != max(0, net - paid):
            err(f"{tag}: outstanding {outstanding:,} != net-paid {max(0, net - paid):,}"); bad += 1
        pay_sum = sum(int(p.get("amount", 0))
                      for p in db.payments_out.find({"bill_id": b["id"]}, {"_id": 0, "amount": 1}))
        if pay_sum != paid:
            err(f"{tag}: Σ payments_out {pay_sum:,} != paid {paid:,}"); bad += 1
        if b.get("status") == "paid" and outstanding > 0:
            err(f"{tag}: status 'paid' tapi outstanding {outstanding:,}"); bad += 1
        if b.get("status") in ("approved", "partial", "paid") and not b.get("approved_by"):
            err(f"{tag}: status '{b.get('status')}' tanpa approved_by (jejak approval hilang)"); bad += 1
    if not bad:
        ok(f"{len(bills)} tagihan AP konsisten (retensi/net/pembayaran/status)")


def check_commissions():
    head("Komisi — perhitungan & jejak approval")
    coms = list(db.commissions.find({}, {"_id": 0}))
    if not coms:
        ok("belum ada komisi (lewati)")
        return
    bad = 0
    for c in coms:
        tag = f"Komisi {c.get('unit_code') or c['id'][:6]}"
        base, rate, amt = int(c.get("base", 0)), float(c.get("rate_pct", 0) or 0), int(c.get("amount", 0))
        if amt != round(base * rate / 100):
            err(f"{tag}: amount {amt:,} != round({base:,}×{rate}%) = {round(base * rate / 100):,}"); bad += 1
        if c.get("status") in ("approved", "paid") and not c.get("approved_by"):
            err(f"{tag}: status '{c.get('status')}' tanpa approved_by"); bad += 1
        if c.get("status") == "paid" and not c.get("paid_at"):
            warn(f"{tag}: status 'paid' tanpa paid_at")
    if not bad:
        ok(f"{len(coms)} komisi konsisten (amount = base × rate)")


def check_deposits():
    head("Titipan pelanggan — saldo, mutasi & pemakaian (Fase 26)")
    deps = list(db.customer_deposits.find({}, {"_id": 0}))
    if not deps:
        ok("belum ada titipan pelanggan (lewati)")
        return
    bad = 0
    for d in deps:
        tag = f"Titipan {d.get('unit_code') or d.get('deal_id', '')[:6]}"
        entries = d.get("entries") or []
        got_in = sum(int(e.get("amount", 0)) for e in entries if e.get("type") == "in")
        got_apply = sum(int(e.get("amount", 0)) for e in entries if e.get("type") == "apply")
        got_refund = sum(int(e.get("amount", 0)) for e in entries if e.get("type") == "refund")
        bal = int(d.get("balance", 0) or 0)
        if bal < 0:
            err(f"{tag}: saldo titipan negatif ({bal:,})"); bad += 1
        if bal != got_in - got_apply - got_refund:
            err(f"{tag}: saldo {bal:,} != masuk {got_in:,} - dipakai {got_apply:,} - "
                f"dikembalikan {got_refund:,}"); bad += 1
        for field, val in (("received_total", got_in), ("applied_total", got_apply),
                           ("refunded_total", got_refund)):
            if int(d.get(field, 0) or 0) != val:
                err(f"{tag}: {field} {d.get(field):,} != Σ mutasi {val:,}"); bad += 1
        # pemakaian titipan wajib punya penerimaan berdana titipan yang seimbang
        applied_recs = sum(int(r.get("applied", 0) or 0)
                           for r in db.receipts.find({"deal_id": d.get("deal_id"),
                                                      "funding": "deposit"}, {"_id": 0, "applied": 1}))
        if applied_recs != got_apply:
            err(f"{tag}: titipan dipakai {got_apply:,} != Σ penerimaan berdana titipan {applied_recs:,}")
            bad += 1
    if not bad:
        ok(f"{len(deps)} titipan konsisten (saldo = masuk - dipakai - dikembalikan)")


def check_financing():
    head("KPR — pencairan & status SLIK")
    apps = list(db.financing_apps.find({}, {"_id": 0}))
    if not apps:
        ok("belum ada pengajuan KPR (lewati)")
        return
    bad = 0
    for f in apps:
        tag = f"KPR {f.get('bank_name')} {f['id'][:6]}"
        ds = f.get("disbursements") or []
        total = sum(int(d.get("amount", 0)) for d in ds)
        if int(f.get("disbursed_total", 0) or 0) != total:
            err(f"{tag}: disbursed_total {f.get('disbursed_total'):,} != Σ pencairan {total:,}"); bad += 1
        if total > int(f.get("plafon", 0) or 0):
            err(f"{tag}: total pencairan {total:,} > plafon {f.get('plafon'):,}"); bad += 1
        if f.get("slik_status") == "clear" and f.get("status") not in ("approved", "disbursing", "done"):
            err(f"{tag}: SLIK clear tapi status '{f.get('status')}'"); bad += 1
        if f.get("slik_status") == "rejected" and f.get("status") != "rejected":
            err(f"{tag}: SLIK rejected tapi status '{f.get('status')}'"); bad += 1
        # Fase 26: dana KPR yang cair adalah kas masuk -> wajib ada jejak penerimaan AR,
        # kecuali memang sengaja tidak dibukukan (dulu SEMUA pencairan tidak terbukukan).
        for ds_entry in ds:
            if not ds_entry.get("receipt_id"):
                warn(f"{tag}: pencairan Rp {int(ds_entry.get('amount', 0)):,} "
                     f"({ds_entry.get('milestone')}) belum punya jejak penerimaan AR")
            elif not db.receipts.find_one({"id": ds_entry["receipt_id"]}, {"_id": 0, "id": 1}):
                err(f"{tag}: receipt_id pencairan menunjuk penerimaan yang tidak ada"); bad += 1
    if not bad:
        ok(f"{len(apps)} pengajuan KPR konsisten")


def check_unit_deal():
    head("Unit ↔ Deal — konsistensi dua arah (anti hold hantu)")
    deals = {d["id"]: d for d in db.deals.find({}, {"_id": 0})}
    bad = 0
    for u in db.units.find({}, {"_id": 0}):
        st = u.get("status")
        rid, bid = u.get("reserved_by_deal"), u.get("booked_by_deal")
        tag = f"Unit {u.get('code')}"
        if st == "available" and (rid or bid):
            err(f"{tag}: status available tapi masih menunjuk deal (rid={rid}, bid={bid})"); bad += 1
        if st == "reserved":
            d = deals.get(rid)
            if not d:
                err(f"{tag}: status reserved tapi reserved_by_deal tidak valid -> HOLD HANTU"); bad += 1
            elif d.get("status") not in ("reserved",):
                err(f"{tag}: reserved tapi deal berstatus '{d.get('status')}'"); bad += 1
        if st == "booked":
            d = deals.get(bid)
            if not d:
                err(f"{tag}: status booked tapi booked_by_deal tidak valid"); bad += 1
            elif d.get("status") not in ("booked", "completed"):
                err(f"{tag}: booked tapi deal berstatus '{d.get('status')}'"); bad += 1
        if st == "sold":
            d = deals.get(bid) or deals.get(rid)
            if not d:
                err(f"{tag}: status sold tanpa deal terkait"); bad += 1
            elif d.get("legal_stage") not in ("ajb",) and d.get("status") != "completed":
                err(f"{tag}: sold tapi deal belum AJB/completed (legal_stage={d.get('legal_stage')})"); bad += 1
    for d in deals.values():
        u = db.units.find_one({"id": d.get("unit_id")}, {"_id": 0, "status": 1, "code": 1,
                                                        "reserved_by_deal": 1, "booked_by_deal": 1})
        if not u:
            err(f"Deal {d['id'][:6]}: unit_id tidak valid"); bad += 1
            continue
        if d.get("status") == "reserved" and u.get("reserved_by_deal") != d["id"]:
            err(f"Deal {d['id'][:6]} reserved tapi unit {u.get('code')} tidak menunjuk balik"); bad += 1
        if d.get("status") in ("booked", "completed") and u.get("booked_by_deal") != d["id"]:
            err(f"Deal {d['id'][:6]} {d.get('status')} tapi unit {u.get('code')} tidak menunjuk balik"); bad += 1
    if not bad:
        ok("semua unit & deal saling konsisten")


def check_gl_tieout():
    head("Tie-out subledger ↔ buku besar")
    if db.journal_entries.count_documents({}) == 0:
        ok("belum ada jurnal (lewati)")
        return
    # 2-1400 Uang Muka Penjualan
    cl = sum(int(c.get("balance", 0) or 0)
             for c in db.contract_liabilities.find({"recognized": {"$ne": True}}, {"_id": 0, "balance": 1}))
    dr, cr = gl_balance("2-1400")
    if cr - dr != cl:
        err(f"GL 2-1400 Uang Muka {cr - dr:,} != Σ contract_liabilities {cl:,}")
    else:
        ok(f"2-1400 Uang Muka = Σ kewajiban kontrak (Rp {cl:,})")
    # 2-1100 Utang Usaha (tagihan disetujui yang belum lunas)
    ap_open = sum(int(b.get("net", 0)) - int(b.get("paid", 0))
                  for b in db.ap_invoices.find({"status": {"$in": ["approved", "partial", "paid"]}}, {"_id": 0}))
    dr, cr = gl_balance("2-1100")
    if cr - dr != ap_open:
        err(f"GL 2-1100 Utang Usaha {cr - dr:,} != Σ (net-paid) tagihan disetujui {ap_open:,}")
    else:
        ok(f"2-1100 Utang Usaha = Σ sisa tagihan disetujui (Rp {ap_open:,})")
    # 2-1200 Utang Retensi
    ret = sum(int(b.get("retention_held", 0))
              for b in db.ap_invoices.find({"status": {"$in": ["approved", "partial", "paid"]},
                                            "retention_released": {"$ne": True}}, {"_id": 0}))
    dr, cr = gl_balance("2-1200")
    if cr - dr != ret:
        err(f"GL 2-1200 Utang Retensi {cr - dr:,} != Σ retensi ditahan {ret:,}")
    else:
        ok(f"2-1200 Utang Retensi = Σ retensi ditahan (Rp {ret:,})")
    # 2-1600 Utang Komisi (approved belum dibayar)
    com_open = sum(int(c.get("amount", 0))
                   for c in db.commissions.find({"status": "approved"}, {"_id": 0, "amount": 1}))
    dr, cr = gl_balance("2-1600")
    if cr - dr != com_open:
        err(f"GL 2-1600 Utang Komisi {cr - dr:,} != Σ komisi disetujui belum dibayar {com_open:,}")
    else:
        ok(f"2-1600 Utang Komisi = Σ komisi disetujui belum dibayar (Rp {com_open:,})")

    # 2-1450 Titipan Pelanggan (Fase 26) — kas kelebihan bayar tidak boleh hilang
    dep_bal = sum(int(d.get("balance", 0) or 0)
                  for d in db.customer_deposits.find({}, {"_id": 0, "balance": 1}))
    dr, cr = gl_balance("2-1450")
    if cr - dr != dep_bal:
        err(f"GL 2-1450 Titipan Pelanggan {cr - dr:,} != Σ saldo titipan {dep_bal:,}")
    else:
        ok(f"2-1450 Titipan Pelanggan = Σ saldo titipan (Rp {dep_bal:,})")


def check_petty_cash():
    head("Kas Bon — uang muka karyawan (1-1500)")
    rows = list(db.cash_advances.find({}, {"_id": 0}))
    if not rows:
        ok("belum ada kas bon (lewati)")
        return
    for a in rows:
        tag = f"Kas bon {a.get('no') or a['id'][:6]}"
        disbursed = int(a.get("disbursed_amount", 0) or 0)
        if a["status"] == "disbursed" and int(a.get("outstanding", 0) or 0) != disbursed:
            err(f"{tag}: outstanding {a.get('outstanding'):,} != nominal cair {disbursed:,}")
        if a["status"] == "settled":
            exp = sum(int(i.get("amount", 0)) for i in a.get("expenses") or [])
            if exp != int(a.get("expense_total", 0) or 0):
                err(f"{tag}: expense_total != Σ item ({exp:,})")
            returned = max(0, disbursed - exp)
            reimburse = max(0, exp - disbursed)
            if int(a.get("returned_amount", 0) or 0) != returned:
                err(f"{tag}: sisa dikembalikan {a.get('returned_amount'):,} != {returned:,}")
            if int(a.get("reimburse_amount", 0) or 0) != reimburse:
                err(f"{tag}: penggantian {a.get('reimburse_amount'):,} != {reimburse:,}")
            if int(a.get("outstanding", 0) or 0) != 0:
                err(f"{tag}: sudah dipertanggungjawabkan tapi outstanding != 0")
        if disbursed and a["status"] in ("submitted", "approved", "rejected", "cancelled"):
            err(f"{tag}: status '{a['status']}' tetapi ada nominal cair {disbursed:,}")
    outstanding = sum(int(a.get("disbursed_amount", 0) or 0) for a in rows
                      if a["status"] == "disbursed")
    dr, cr = gl_balance("1-1500")
    if dr - cr != outstanding:
        err(f"GL 1-1500 Uang Muka Karyawan {dr - cr:,} != Σ kas bon cair belum "
            f"dipertanggungjawabkan {outstanding:,}")
    else:
        ok(f"1-1500 Uang Muka Karyawan = Σ kas bon berjalan (Rp {outstanding:,})")


def check_fixed_assets():
    head("Aset Tetap — perolehan (1-2100) & akumulasi penyusutan (1-2200)")
    rows = list(db.fixed_assets.find({}, {"_id": 0}))
    if not rows:
        ok("belum ada aset tetap (lewati)")
        return
    live = [a for a in rows if a.get("status") != "disposed"]
    for a in rows:
        tag = f"Aset {a.get('code') or a['id'][:6]}"
        cost = int(a.get("cost", 0))
        salvage = int(a.get("salvage_value", 0) or 0)
        accum = int(a.get("accumulated_depreciation", 0) or 0)
        posted = sum(int(d.get("amount", 0)) for d in
                     db.asset_depreciations.find({"asset_id": a["id"]}, {"_id": 0, "amount": 1}))
        if accum != posted:
            err(f"{tag}: akumulasi {accum:,} != Σ jurnal penyusutan {posted:,}")
        if accum > cost - salvage:
            err(f"{tag}: akumulasi {accum:,} melewati batas susut {cost - salvage:,}")
        if a.get("status") != "disposed" and int(a.get("book_value", 0)) != cost - accum:
            err(f"{tag}: nilai buku {a.get('book_value'):,} != perolehan-akumulasi "
                f"{cost - accum:,}")
        if a.get("funding") == "utang_usaha" and not a.get("ap_bill_id"):
            err(f"{tag}: dibeli secara utang tetapi tidak punya tagihan AP")
    cost_live = sum(int(a["cost"]) for a in live)
    accum_live = sum(int(a.get("accumulated_depreciation", 0) or 0) for a in live)
    dr, cr = gl_balance("1-2100")
    if dr - cr != cost_live:
        err(f"GL 1-2100 Aset Tetap {dr - cr:,} != Σ perolehan aset belum dilepas {cost_live:,}")
    else:
        ok(f"1-2100 Aset Tetap = Σ perolehan aset aktif (Rp {cost_live:,})")
    dr, cr = gl_balance("1-2200")
    if cr - dr != accum_live:
        err(f"GL 1-2200 Akumulasi Penyusutan {cr - dr:,} != Σ akumulasi aset belum dilepas "
            f"{accum_live:,}")
    else:
        ok(f"1-2200 Akumulasi Penyusutan = Σ akumulasi aset aktif (Rp {accum_live:,})")


def check_loans():
    head("Pembiayaan korporat — utang bank/leasing (2-2100)")
    rows = list(db.loans.find({}, {"_id": 0}))
    if not rows:
        ok("belum ada fasilitas pembiayaan (lewati)")
        return
    for l in rows:
        tag = f"Fasilitas {l.get('no') or l['id'][:6]}"
        sched = l.get("schedule") or []
        if l["status"] in ("active", "paid_off"):
            if not sched:
                err(f"{tag}: berstatus {l['status']} tetapi tidak punya jadwal angsuran")
                continue
            if sum(int(r["principal"]) for r in sched) != int(l["principal"]):
                err(f"{tag}: Σ pokok jadwal != pokok pinjaman {int(l['principal']):,}")
            paid_p = sum(int(r.get("paid_principal", 0)) for r in sched)
            paid_i = sum(int(r.get("paid_interest", 0)) for r in sched)
            if int(l.get("paid_principal", 0)) != paid_p:
                err(f"{tag}: paid_principal != Σ jadwal {paid_p:,}")
            if int(l.get("outstanding_principal", 0)) != int(l["principal"]) - paid_p:
                err(f"{tag}: sisa pokok != pokok − pokok terbayar")
            pay_p = sum(int(p.get("principal_part", 0)) for p in
                        db.loan_payments.find({"loan_id": l["id"]}, {"_id": 0}))
            pay_i = sum(int(p.get("interest_part", 0)) for p in
                        db.loan_payments.find({"loan_id": l["id"]}, {"_id": 0}))
            if pay_p != paid_p or pay_i != paid_i:
                err(f"{tag}: riwayat pembayaran ({pay_p:,}/{pay_i:,}) != jadwal "
                    f"({paid_p:,}/{paid_i:,})")
            for r in sched:
                tot = int(r.get("paid_total", 0))
                if tot != int(r.get("paid_principal", 0)) + int(r.get("paid_interest", 0)):
                    err(f"{tag} angsuran ke-{r['no']}: paid_total != pokok+bunga terbayar")
                if tot > int(r["total"]):
                    err(f"{tag} angsuran ke-{r['no']}: dibayar melebihi nilai angsuran")
    outstanding = sum(int(l.get("outstanding_principal", 0)) for l in rows
                      if l["status"] == "active")
    dr, cr = gl_balance("2-2100")
    if cr - dr != outstanding:
        err(f"GL 2-2100 Utang Bank/Leasing {cr - dr:,} != Σ sisa pokok fasilitas aktif "
            f"{outstanding:,}")
    else:
        ok(f"2-2100 Utang Bank/Leasing = Σ sisa pokok fasilitas aktif (Rp {outstanding:,})")


def check_marketing_fee():
    head("Marketing Fee agen — utang fee (2-1500)")
    rows = list(db.marketing_fees.find({}, {"_id": 0}))
    if not rows:
        ok("belum ada marketing fee (lewati)")
        return
    for f in rows:
        tag = f"Fee {f.get('no') or f['id'][:6]}"
        gross = int(f.get("amount_gross", 0))
        pph = int(f.get("pph_amount", 0) or 0)
        if int(f.get("amount_net", 0)) != gross - pph:
            err(f"{tag}: netto != bruto − PPh ({gross - pph:,})")
        # Fase 42 — fee dari ATURAN mitra: nominal yang dibukukan = porsi pemicu dari hasil
        # aturan, dan (bila gross-up) beban = netto + PPh. Diperiksa berlapis supaya angka
        # otomatis tidak bisa menyimpang dari aturan yang menerbitkannya.
        rule_basis = f.get("rule_basis")
        if rule_basis:
            if not f.get("rule_id"):
                err(f"{tag}: fee dari aturan tetapi tidak menyimpan rule_id (INV-09)")
            full = int(f.get("gross_full", 0))
            share = float(f.get("share_pct") or 0)
            if not full or not share:
                err(f"{tag}: fee dari aturan tanpa gross_full/share_pct (angka tak terlacak)")
            else:
                base_share = round(full * share / 100.0)
                expect = (round(base_share / (1 - float(f.get("pph_pct") or 0) / 100.0))
                          if f.get("gross_up") else base_share)
                if abs(gross - expect) > 1:
                    err(f"{tag}: beban {gross:,} != porsi {share}% dari hasil aturan "
                        f"({expect:,})")
            price_base = ((f.get("calc") or {}).get("detail") or {}).get("price_base", "gross")
            if rule_basis == "percent_price" and int(f.get("deal_price", 0)) \
                    and price_base == "gross":
                want_full = round(int(f["deal_price"]) * float(f.get("value", 0)) / 100.0)
                if abs(full - want_full) > 1:
                    err(f"{tag}: hasil aturan {full:,} != {f.get('value')}% × harga jual "
                        f"({want_full:,})")
        elif f.get("basis") == "percent" and int(f.get("deal_price", 0)):
            expect = round(int(f["deal_price"]) * float(f.get("value", 0)) / 100.0)
            if gross != expect:
                err(f"{tag}: bruto {gross:,} != {f.get('value')}% × harga jual ({expect:,})")
        if int(f.get("paid_amount", 0)) > int(f.get("amount_net", 0)):
            err(f"{tag}: dibayar melebihi netto")
        if f["status"] == "paid" and int(f.get("paid_amount", 0)) != int(f.get("amount_net", 0)):
            err(f"{tag}: berstatus Dibayar tetapi nominal belum penuh")
        if f["status"] in ("approved", "paid") and not f.get("approved_by"):
            err(f"{tag}: disetujui tanpa jejak penyetuju")
        if f["status"] in ("draft", "submitted", "rejected") and int(f.get("paid_amount", 0)):
            err(f"{tag}: status '{f['status']}' tetapi sudah ada pembayaran")
    payable = sum(int(f["amount_net"]) - int(f.get("paid_amount", 0)) for f in rows
                  if f["status"] in ("approved", "paid"))
    dr, cr = gl_balance("2-1500")
    if cr - dr != payable:
        err(f"GL 2-1500 Utang Marketing Fee {cr - dr:,} != Σ fee disetujui belum dibayar "
            f"{payable:,}")
    else:
        ok(f"2-1500 Utang Marketing Fee = Σ fee disetujui belum dibayar (Rp {payable:,})")


def main():
    print("INVARIAN BISNIS SIPRO (uang & status)")
    check_ar()
    check_ap()
    check_deposits()
    check_commissions()
    check_financing()
    check_unit_deal()
    check_petty_cash()
    check_fixed_assets()
    check_loans()
    check_marketing_fee()
    check_gl_tieout()
    print("\n" + "-" * 50)
    if errors:
        print(f"INVARIAN BISNIS GAGAL: {len(errors)} pelanggaran, {len(warns)} peringatan")
        return 1
    print(f"INVARIAN BISNIS LULUS ({len(warns)} peringatan)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
