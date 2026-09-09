"""General Ledger engine (Phase 13 — EPIC 3.4): CoA + double-entry journals + reports.

This is the GL layer that upgrades the worksheet-level finance engine to full
double-entry bookkeeping. Journals are auto-posted from the existing event outbox
(no changes to finance_engine): a subledger event -> a balanced journal entry.

Posting map (Indonesian property developer, PSAK-aligned; contract liability model):
  payment.received     Dr 1-1200 Bank            / Cr 2-1400 Uang Muka Penjualan
  ap.approved          Dr 1-1400/1-1600/6-1300   / Cr 2-1100 Utang Usaha (+ 2-1200 Retensi)
  ap.paid              Dr 2-1100 Utang Usaha      / Cr 1-1200 Bank
  commission.approved  Dr 6-1100 Beban Komisi     / Cr 2-1600 Utang Komisi
  revenue.recognized   Dr 2-1400 + Dr 1-1300 AR   / Cr 4-1100 Pendapatan ; Dr 5-1100 HPP / Cr 1-1600 WIP

Idempotent per event via source_event = "ev:<event_id>" (safe across dispatcher retries).
Money = IDR integer; every journal must balance (total_debit == total_credit).
"""
import logging

import sequences as seq
import gl_periods
import reference as ref
from db import db, ORG_ID
from core_utils import new_id, now_iso
from reference_p48 import DEDUCTION_GL

logger = logging.getLogger("sipro.gl")

# code, name, type  (type: asset|liability|equity|revenue|expense)
STANDARD_COA = [
    ("1-1100", "Kas", "asset"),
    ("1-1200", "Bank", "asset"),
    ("1-1300", "Piutang Usaha", "asset"),
    ("1-1400", "Persediaan Material", "asset"),
    ("1-1500", "Uang Muka Karyawan (Kas Bon)", "asset"),
    ("1-1600", "Aset Proyek dalam Penyelesaian (WIP)", "asset"),
    ("1-1700", "Piutang Retensi", "asset"),
    # Fase 48C: uang muka yang DIBAYARKAN ke subkon/vendor adalah HAK TAGIH kita (aset),
    # bukan biaya. Tanpa akun ini, uang muka dulu terpaksa dicatat sebagai tagihan biasa
    # sehingga biaya proyek terhitung dua kali (saat uang muka & saat termin).
    ("1-1800", "Uang Muka Subkontraktor & Vendor", "asset"),
    ("1-2100", "Aset Tetap", "asset"),
    ("1-2200", "Akumulasi Penyusutan", "asset"),
    ("2-1100", "Utang Usaha", "liability"),
    ("2-1200", "Utang Retensi", "liability"),
    ("2-1300", "Utang Pajak", "liability"),
    ("2-1400", "Uang Muka Penjualan (Kewajiban Kontrak)", "liability"),
    ("2-1450", "Titipan Pelanggan (Kelebihan Bayar)", "liability"),
    # Fase 56C: uang pembeli yang WAJIB dikembalikan setelah kontraknya dibatalkan. Tanpa
    # akun ini, keputusan pembatalan tidak punya tempat mendarat: saldo `2-1400` (uang muka
    # penjualan) tetap berdiri untuk kontrak yang sudah tidak ada, dan pembeli yang menunggu
    # uangnya tidak terlihat di neraca sama sekali.
    ("2-1460", "Utang Refund Pembatalan", "liability"),
    ("2-1500", "Utang Marketing Fee", "liability"),
    ("2-1600", "Utang Komisi", "liability"),
    ("2-2100", "Utang Bank / Leasing", "liability"),
    ("3-1100", "Modal Disetor", "equity"),
    ("3-1900", "Laba Ditahan", "equity"),
    ("4-1100", "Pendapatan Penjualan Unit", "revenue"),
    ("4-1200", "Pendapatan Lain-lain", "revenue"),
    ("4-1300", "Laba Pelepasan Aset Tetap", "revenue"),
    # Fase 58: denda keterlambatan pembayaran termin. Tanpa akun sendiri, denda hanya bisa
    # menumpang "Pendapatan Lain-lain" dan tidak ada satu laporan pun yang bisa menjawab
    # "berapa denda yang kita tagihkan (dan berapa yang kita ringankan)" — padahal itu
    # angka yang paling sering ditanya saat rapat penagihan.
    ("4-1400", "Pendapatan Denda Keterlambatan", "revenue"),
    ("5-1100", "Beban Pokok Penjualan", "expense"),
    ("6-1100", "Beban Komisi", "expense"),
    ("6-1200", "Beban Pemasaran", "expense"),
    ("6-1300", "Beban Umum & Administrasi", "expense"),
    ("6-1400", "Beban Pajak", "expense"),
    ("6-1500", "Beban Penyusutan", "expense"),
    ("6-1600", "Beban Bunga & Provisi Bank", "expense"),
    ("6-1800", "Kerugian Pelepasan Aset Tetap", "expense"),
]
DEBIT_NORMAL = ("asset", "expense")
# SSOT: tipe akun hanya didefinisikan di reference.py (dulu daftar ini duplikat).
VALID_TYPES = tuple(ref.values("account_type"))
_ENSURED = set()


async def ensure_coa(org_id=ORG_ID):
    """Seed CoA standar untuk sebuah org — idempoten PER KODE AKUN.

    Fase 26: dulu hanya menyemai bila koleksi accounts kosong, sehingga akun baru
    (mis. `2-1450 Titipan Pelanggan`) tidak pernah muncul di database yang sudah ada.
    """
    if org_id in _ENSURED:
        return
    existing = set(await db.accounts.distinct("code", {"org_id": org_id}))
    missing = [(c, n, t) for c, n, t in STANDARD_COA if c not in existing]
    if missing:
        ts = now_iso()
        await db.accounts.insert_many([
            {"id": new_id(), "org_id": org_id, "code": c, "name": n, "type": t,
             "parent_code": None, "is_active": True, "created_at": ts}
            for c, n, t in missing])
        logger.info("CoA dilengkapi: %s", [c for c, _n, _t in missing])
    _ENSURED.add(org_id)


async def post_journal(org_id, memo, lines, *, date=None, source_type=None, source_id=None,
                       source_event=None, posted_by="system", auto=True,
                       source_deal_id=None, allow_closed=False) -> dict:
    """Insert one balanced journal entry. Idempotent when source_event is provided.

    `source_deal_id` opsional: dipakai bila `source_id` menunjuk dokumen turunan (mis.
    kuitansi) tetapi jurnalnya masih perlu bisa ditelusuri per transaksi penjualan.

    `allow_closed` HANYA untuk jurnal penutup/balik tahun buku (Fase 49B): jurnal penutup
    tahun memang HARUS bertanggal 31 Desember tahun itu, padahal bulan Desember sudah
    ditutup. Tanpa jalan keluar ini, tanggalnya akan digeser ke periode terbuka dan laba
    tahun lalu masuk ke tahun berikutnya — laporan jadi salah. Selain kasus itu, aturan
    Fase 25 tetap berlaku penuh.
    """
    if source_event:
        existing = await db.journal_entries.find_one(
            {"org_id": org_id, "source_event": source_event}, {"_id": 0})
        if existing:
            return existing
    await ensure_coa(org_id)
    acct_map = {a["code"]: a for a in await db.accounts.find({"org_id": org_id}, {"_id": 0}).to_list(500)}
    norm, td, tc = [], 0, 0
    for ln in lines:
        code = ln["account_code"]
        acct = acct_map.get(code)
        if not acct:
            raise ValueError(f"Akun {code} tidak ada dalam CoA.")
        dr, cr = int(ln.get("debit", 0) or 0), int(ln.get("credit", 0) or 0)
        if dr < 0 or cr < 0:
            raise ValueError("Nilai debit/kredit tidak boleh negatif.")
        if dr == 0 and cr == 0:
            continue
        td += dr
        tc += cr
        norm.append({"account_id": acct["id"], "account_code": code, "account_name": acct["name"],
                     "account_type": acct["type"], "debit": dr, "credit": cr, "memo": ln.get("memo")})
    if not norm:
        raise ValueError("Jurnal harus memiliki minimal satu baris bernilai.")
    if td != tc:
        raise ValueError(f"Jurnal tidak seimbang: debit Rp {td:,} != kredit Rp {tc:,}.")
    ts = now_iso()
    d = date or ts
    # Tutup periode (P25): jurnal manual di periode tertutup ditolak; posting otomatis
    # digeser ke periode terbuka agar transaksi nyata tidak pernah hilang.
    d, shifted_from = (d, None) if allow_closed else await gl_periods.resolve_post_date(org_id, d, auto)
    if shifted_from:
        memo = f"{memo} · posting digeser (periode {shifted_from} ditutup)"
    entry_no = await seq.next_number("journal", org_id, prefix="JV", width=5, year=ts[:4])
    doc = {
        "id": new_id(), "org_id": org_id, "entry_no": entry_no, "date": d,
        "memo": memo, "lines": norm, "total_debit": td, "total_credit": tc,
        "source_type": source_type, "source_id": source_id, "source_event": source_event,
        "auto": auto, "posted_by": posted_by, "created_at": ts,
    }
    if source_deal_id:
        doc["source_deal_id"] = source_deal_id
    await db.journal_entries.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


# ----------------------------- Balances + reports -----------------------------
async def account_balances(org_id=ORG_ID) -> dict:
    accts = await db.accounts.find({"org_id": org_id}, {"_id": 0}).sort("code", 1).to_list(500)
    bal = {a["code"]: {"code": a["code"], "name": a["name"], "type": a["type"],
                       "debit": 0, "credit": 0, "balance": 0} for a in accts}
    for je in await db.journal_entries.find({"org_id": org_id}, {"_id": 0, "lines": 1}).to_list(100000):
        for ln in je.get("lines", []):
            b = bal.get(ln["account_code"])
            if not b:
                continue
            b["debit"] += int(ln.get("debit", 0))
            b["credit"] += int(ln.get("credit", 0))
    for b in bal.values():
        b["balance"] = (b["debit"] - b["credit"]) if b["type"] in DEBIT_NORMAL else (b["credit"] - b["debit"])
    return bal


async def trial_balance(org_id=ORG_ID) -> dict:
    bal = await account_balances(org_id)
    rows = sorted([b for b in bal.values() if b["debit"] or b["credit"]], key=lambda x: x["code"])
    td = sum(b["debit"] for b in rows)
    tc = sum(b["credit"] for b in rows)
    return {"rows": rows, "total_debit": td, "total_credit": tc, "balanced": td == tc}


async def income_statement(org_id=ORG_ID) -> dict:
    bal = await account_balances(org_id)
    revenue = sorted([b for b in bal.values() if b["type"] == "revenue" and b["balance"]], key=lambda x: x["code"])
    expenses = sorted([b for b in bal.values() if b["type"] == "expense" and b["balance"]], key=lambda x: x["code"])
    tr = sum(b["balance"] for b in revenue)
    te = sum(b["balance"] for b in expenses)
    return {"revenue": revenue, "expenses": expenses, "total_revenue": tr,
            "total_expense": te, "net_income": tr - te}


async def balance_sheet(org_id=ORG_ID) -> dict:
    bal = await account_balances(org_id)
    ist = await income_statement(org_id)
    ni = ist["net_income"]
    assets = sorted([b for b in bal.values() if b["type"] == "asset" and b["balance"]], key=lambda x: x["code"])
    liabilities = sorted([b for b in bal.values() if b["type"] == "liability" and b["balance"]], key=lambda x: x["code"])
    equity = sorted([b for b in bal.values() if b["type"] == "equity" and b["balance"]], key=lambda x: x["code"])
    ta = sum(b["balance"] for b in assets)
    tl = sum(b["balance"] for b in liabilities)
    teq = sum(b["balance"] for b in equity)
    return {"assets": assets, "liabilities": liabilities, "equity": equity,
            "total_assets": ta, "total_liabilities": tl, "total_equity": teq, "net_income": ni,
            "total_liab_equity": tl + teq + ni, "balanced": ta == (tl + teq + ni)}


async def ledger(org_id, account_code) -> dict:
    if not account_code:
        return {"account": None, "lines": [], "balance": 0}
    acct = await db.accounts.find_one({"org_id": org_id, "code": account_code}, {"_id": 0})
    if not acct:
        return {"account": None, "lines": [], "balance": 0}
    entries = await db.journal_entries.find(
        {"org_id": org_id, "lines.account_code": account_code}, {"_id": 0}
    ).sort([("date", 1), ("created_at", 1)]).to_list(10000)
    running, out = 0, []
    debit_normal = acct["type"] in DEBIT_NORMAL
    for je in entries:
        for ln in je.get("lines", []):
            if ln["account_code"] != account_code:
                continue
            dr, cr = int(ln.get("debit", 0)), int(ln.get("credit", 0))
            running += (dr - cr) if debit_normal else (cr - dr)
            out.append({"date": je["date"], "entry_no": je["entry_no"], "memo": je["memo"],
                        "debit": dr, "credit": cr, "balance": running})
    return {"account": acct, "lines": out, "balance": running}


# ----------------------------- Event handlers (subledger -> GL) -----------------------------
async def _gl_payment_received(ev):
    """Jurnal penerimaan pembeli — HARUS menunjuk KUITANSINYA, bukan deal-nya.

    Cacat yang ditutup Fase 47 (ditemukan lewat invarian 2-1400): dulu `source_id` diisi
    `ev["entity_id"]` yang bernilai **deal_id**, padahal `source_type` mengaku "receipt".
    Akibatnya (a) dua penerimaan pada satu deal melahirkan dua jurnal yang TIDAK BISA
    dibedakan, dan (b) jurnal pembalik `receipt_void` (yang memakai `source_id=receipt_id`)
    tidak pernah bisa dipasangkan dengan jurnal aslinya — pembatalan penerimaan menjadi
    tidak bisa direkonstruksi. Sekarang kuitansinya yang ditunjuk, dan deal-nya tetap
    tercatat di `source_deal_id` supaya laporan per-deal tidak kehilangan jalur.
    """
    org = ev.get("org_id", ORG_ID)
    data = ev.get("data") or {}
    amt = int(data.get("amount", 0))
    if amt <= 0:
        return
    await post_journal(org, "Penerimaan pembayaran pembeli (uang muka)", [
        {"account_code": "1-1200", "debit": amt, "credit": 0},
        {"account_code": "2-1400", "debit": 0, "credit": amt},
    ], source_type="receipt", source_id=data.get("receipt_id") or ev["entity_id"],
        source_event=f"ev:{ev['id']}", source_deal_id=ev.get("entity_id"))


# --- Fase 26: titipan pelanggan (kelebihan bayar) tidak boleh hilang dari pembukuan ---
async def _gl_deposit_received(ev):
    """Kelebihan bayar masuk: kas bertambah, timbul kewajiban titipan (bukan pendapatan)."""
    org = ev.get("org_id", ORG_ID)
    amt = int((ev.get("data") or {}).get("amount", 0))
    if amt <= 0:
        return
    await post_journal(org, "Titipan pelanggan (kelebihan bayar) diterima", [
        {"account_code": "1-1200", "debit": amt, "credit": 0},
        {"account_code": "2-1450", "debit": 0, "credit": amt},
    ], source_type="deposit", source_id=ev["entity_id"], source_event=f"ev:{ev['id']}")


async def _gl_deposit_applied(ev):
    """Titipan dipakai untuk termin: pindah kewajiban titipan -> kewajiban kontrak."""
    org = ev.get("org_id", ORG_ID)
    amt = int((ev.get("data") or {}).get("amount", 0))
    if amt <= 0:
        return
    await post_journal(org, "Titipan pelanggan dipakai untuk termin", [
        {"account_code": "2-1450", "debit": amt, "credit": 0},
        {"account_code": "2-1400", "debit": 0, "credit": amt},
    ], source_type="deposit", source_id=ev["entity_id"], source_event=f"ev:{ev['id']}")


async def _gl_deposit_refunded(ev):
    """Titipan dikembalikan: kewajiban titipan turun, kas keluar."""
    org = ev.get("org_id", ORG_ID)
    amt = int((ev.get("data") or {}).get("amount", 0))
    if amt <= 0:
        return
    await post_journal(org, "Titipan pelanggan dikembalikan", [
        {"account_code": "2-1450", "debit": amt, "credit": 0},
        {"account_code": "1-1200", "debit": 0, "credit": amt},
    ], source_type="deposit", source_id=ev["entity_id"], source_event=f"ev:{ev['id']}")


async def _gl_ap_approved(ev):
    org = ev.get("org_id", ORG_ID)
    bill = await db.ap_invoices.find_one({"id": ev["entity_id"], "org_id": org}, {"_id": 0})
    if not bill:
        return
    claimed = int(bill.get("claimed", 0))
    net = int(bill.get("net", 0))
    ret = int(bill.get("retention_held", 0))
    dr_code = "1-1600"  # default: capitalize construction cost to WIP
    if bill.get("po_id"):
        po = await db.purchase_orders.find_one({"id": bill["po_id"], "org_id": org}, {"_id": 0, "po_type": 1})
        if po:
            dr_code = {"material": "1-1400", "subcon": "1-1600", "general": "6-1300"}.get(po.get("po_type"), "1-1600")
    lines = [{"account_code": dr_code, "debit": claimed, "credit": 0},
             {"account_code": "2-1100", "debit": 0, "credit": net}]
    if ret > 0:
        lines.append({"account_code": "2-1200", "debit": 0, "credit": ret})
    # Fase 48C: potongan termin (angsuran uang muka, denda, bon material) menjadi baris
    # KREDIT tersendiri. Nilai pekerjaan yang diakui (debit) tetap utuh, dan jurnal tetap
    # seimbang karena claimed = net + retensi + Σ potongan.
    for ded in (bill.get("deductions") or []):
        amt = int(ded.get("amount", 0) or 0)
        if amt > 0:
            lines.append({"account_code": DEDUCTION_GL.get(ded.get("kind"), "4-1200"),
                          "debit": 0, "credit": amt, "memo": ded.get("reason")})
    await post_journal(org, f"Tagihan AP disetujui — {bill.get('vendor')}", lines,
                       source_type="ap_bill", source_id=bill["id"], source_event=f"ev:{ev['id']}")


async def _gl_ap_paid(ev):
    org = ev.get("org_id", ORG_ID)
    data = ev.get("data") or {}
    amt = int(data.get("amount", 0))
    if amt <= 0:
        return
    # Fase 49F: pembayaran boleh MEMOTONG PPh (jasa konstruksi/PPh 23). Utang usaha lunas
    # sebesar nilai bruto, tetapi kas yang keluar hanya nilai netonya — sisanya menjadi
    # UTANG PAJAK yang wajib disetor. Tanpa baris ketiga ini, bukti potong yang kita
    # terbitkan tidak akan punya pasangan di pembukuan (mengarang kewajiban pajak).
    withheld = int(data.get("withheld", 0) or 0)
    lines = [{"account_code": "2-1100", "debit": amt, "credit": 0},
             {"account_code": "1-1200", "debit": 0, "credit": amt - withheld}]
    if withheld > 0:
        lines.append({"account_code": "2-1300", "debit": 0, "credit": withheld,
                      "memo": data.get("withheld_memo") or "Potongan PPh atas pembayaran"})
    await post_journal(org, "Pembayaran tagihan AP", lines,
                       source_type="ap_bill", source_id=ev["entity_id"], source_event=f"ev:{ev['id']}")


async def _gl_commission_approved(ev):
    org = ev.get("org_id", ORG_ID)
    com = await db.commissions.find_one({"org_id": org, "deal_id": ev["entity_id"]}, {"_id": 0})
    if not com:
        return
    amt = int(com.get("amount", 0))
    if amt <= 0:
        return
    await post_journal(org, f"Akrual komisi — {com.get('assigned_to') or ''}", [
        {"account_code": "6-1100", "debit": amt, "credit": 0},
        {"account_code": "2-1600", "debit": 0, "credit": amt},
    ], source_type="commission", source_id=com["id"], source_event=f"ev:{ev['id']}")


async def _gl_commission_paid(ev):
    org = ev.get("org_id", ORG_ID)
    amt = int((ev.get("data") or {}).get("amount", 0))
    if amt <= 0:
        return
    await post_journal(org, "Pembayaran komisi sales", [
        {"account_code": "2-1600", "debit": amt, "credit": 0},
        {"account_code": "1-1200", "debit": 0, "credit": amt},
    ], source_type="commission", source_id=ev["entity_id"], source_event=f"ev:{ev['id']}")


async def _gl_revenue_recognized(ev):
    org = ev.get("org_id", ORG_ID)
    rr = await db.revenue_recognitions.find_one({"org_id": org, "deal_id": ev["entity_id"]}, {"_id": 0})
    if not rr:
        return
    rev = int(rr.get("revenue", 0))
    cogs = int(rr.get("cogs", 0))
    cleared = int(rr.get("contract_liability_cleared", 0))
    ar_part = max(0, rev - cleared)
    lines = []
    if cleared > 0:
        lines.append({"account_code": "2-1400", "debit": cleared, "credit": 0})
    if ar_part > 0:
        lines.append({"account_code": "1-1300", "debit": ar_part, "credit": 0})
    lines.append({"account_code": "4-1100", "debit": 0, "credit": rev})
    if cogs > 0:
        lines.append({"account_code": "5-1100", "debit": cogs, "credit": 0})
        lines.append({"account_code": "1-1600", "debit": 0, "credit": cogs})
    await post_journal(org, "Pengakuan pendapatan (BAST) + HPP", lines,
                       source_type="revrec", source_id=rr["id"], source_event=f"ev:{ev['id']}")


# ----------------------------- Tax -> GL (Phase 19 — EPIC 3.3 setoran) -----------------------------
TAX_LABEL = {"ppn": "PPN Keluaran", "pph": "PPh Final Ps.4(2)", "bphtb": "BPHTB"}


def _tax_memo_ctx(record) -> str:
    parts = [TAX_LABEL.get(record.get("type"), (record.get("type") or "Pajak").upper())]
    if record.get("unit_code"):
        parts.append(record["unit_code"])
    p = str(record.get("created_at") or "")[:7]
    if p:
        parts.append(p)
    return " — ".join(parts)


async def post_tax_accrual(org_id, record) -> dict:
    """Akui utang pajak saat catatan dilaporkan/disetor: Dr Beban Pajak / Cr Utang Pajak.
    Idempotent per catatan (source_event=tax.accrue:<id>)."""
    amt = int(record.get("amount", 0) or 0)
    if amt <= 0:
        return None
    return await post_journal(
        org_id, f"Akrual pajak — {_tax_memo_ctx(record)}",
        [{"account_code": "6-1400", "debit": amt, "credit": 0},
         {"account_code": "2-1300", "debit": 0, "credit": amt}],
        source_type="tax_accrual", source_id=record["id"],
        source_event=f"tax.accrue:{record['id']}")


async def post_tax_payment(org_id, record) -> dict:
    """Setoran pajak (dari 'reported'/'pending' -> 'paid'): Dr Utang Pajak / Cr Bank.
    Menjamin akrual sudah ter-posting lebih dulu; NTPN dicantumkan di memo.
    Idempotent per catatan (source_event=tax.setor:<id>)."""
    amt = int(record.get("amount", 0) or 0)
    if amt <= 0:
        return None
    await post_tax_accrual(org_id, record)  # pastikan utang pajak terbentuk
    ntpn = record.get("ntpn")
    memo = f"Setor pajak — {_tax_memo_ctx(record)}" + (f" · NTPN {ntpn}" if ntpn else "")
    return await post_journal(
        org_id, memo,
        [{"account_code": "2-1300", "debit": amt, "credit": 0},
         {"account_code": "1-1200", "debit": 0, "credit": amt}],
        date=(record.get("paid_date") or None),
        source_type="tax_setor", source_id=record["id"],
        source_event=f"tax.setor:{record['id']}")


def register_gl_handlers():
    """Attach GL posting handlers to the shared event bus (idempotent)."""
    import engine
    mapping = {
        "payment.received": _gl_payment_received,
        "deposit.received": _gl_deposit_received,
        "deposit.applied": _gl_deposit_applied,
        "deposit.refunded": _gl_deposit_refunded,
        "ap.approved": _gl_ap_approved,
        "ap.paid": _gl_ap_paid,
        "commission.approved": _gl_commission_approved,
        "commission.paid": _gl_commission_paid,
        "revenue.recognized": _gl_revenue_recognized,
    }
    for etype, handler in mapping.items():
        lst = engine.HANDLERS.setdefault(etype, [])
        if handler not in lst:
            lst.append(handler)


register_gl_handlers()
