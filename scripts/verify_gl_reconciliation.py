#!/usr/bin/env python3
"""
GATE 70 — Rekonsiliasi buku besar sampai SUMBER BARIS (backlog P1 "audit GL/BI").

Gate lama (`verify_data_integrity`, `verify_closing`, `verify_card_drilldown`) memeriksa
Dr = Cr dan kartu = drilldown. Gate ini menutup celah berikutnya: SETIAP angka laporan GL
(neraca saldo, neraca, laba-rugi, arus kas) dihitung ulang dari baris jurnal/ledger yang
dikembalikan API — bukan mempercayai flag `balanced`/`reconciled` — dan saldo GL
dicocokkan dengan buku pembantunya (AP, retensi, kewajiban kontrak, komisi, kas/bank).
Selisih yang SAH (tagihan vendor belum disetujui belum berjurnal) harus bisa disebut
sampai rupiahnya, bukan diterima sebagai "beda pembulatan".

Hanya membaca. Tidak membuat/menghapus data.
"""
import os
import pathlib
import sys

import requests
from dotenv import load_dotenv
from pymongo import MongoClient

ROOT = pathlib.Path(__file__).resolve().parent.parent
load_dotenv(ROOT / "backend" / ".env")
API = "http://localhost:8001/api"
PW = "Sipro#2026"
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
ORG = os.environ.get("DEFAULT_ORG_ID", "org-sipro")

FAIL, PASSED = [], 0


def check(ok, label, detail=""):
    global PASSED
    if ok:
        PASSED += 1
        print(f"  OK    {label}")
    else:
        FAIL.append(label)
        print(f"  GAGAL {label} — {detail}")
    return bool(ok)


def head(t):
    print(f"\n{t}\n" + "-" * len(t))


def rp(n):
    return "Rp " + f"{int(n or 0):,}".replace(",", ".")


def login(email):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": PW}, timeout=25)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def get(path, hdr, **params):
    r = requests.get(f"{API}{path}", headers=hdr, params=params or None, timeout=90)
    if r.status_code != 200:
        raise RuntimeError(f"GET {path} -> {r.status_code} {r.text[:120]}")
    return r.json().get("data")


DEBIT_NORMAL = {"asset", "expense"}


def signed(row):
    d, c = int(row.get("debit", 0)), int(row.get("credit", 0))
    return (d - c) if row["type"] in DEBIT_NORMAL else (c - d)


# ============================================================ A. konsistensi internal GL
def bagian_a(owner):
    head("A. Laporan GL dihitung ulang dari barisnya sendiri")
    tb = get("/gl/trial-balance", owner)
    rows = tb["rows"]
    td, tc = sum(int(r["debit"]) for r in rows), sum(int(r["credit"]) for r in rows)
    check(rows and td == tc and td == tb["total_debit"] == tb["total_credit"],
          "A1 neraca saldo: Σ debit baris = Σ kredit baris = total yang dilaporkan",
          f"Σ Dr {rp(td)} Σ Cr {rp(tc)} lapor {rp(tb['total_debit'])}/{rp(tb['total_credit'])}")
    check(all(signed(r) == int(r["balance"]) for r in rows),
          "A2 saldo tiap akun = Dr−Cr (atau Cr−Dr) sesuai saldo normal jenisnya")

    # A3 setiap akun neraca saldo ditelusuri ke ledger: jumlah baris = angka neraca saldo
    salah = []
    for r in rows:
        led = get("/gl/ledger", owner, account_code=r["code"])
        ld = sum(int(x["debit"]) for x in led["lines"])
        lc = sum(int(x["credit"]) for x in led["lines"])
        if ld != int(r["debit"]) or lc != int(r["credit"]) or int(led["balance"]) != int(r["balance"]):
            salah.append(f"{r['code']} TB {r['debit']}/{r['credit']} vs ledger {ld}/{lc}")
        elif led["lines"] and int(led["lines"][-1]["balance"]) != int(r["balance"]):
            salah.append(f"{r['code']} saldo berjalan akhir ≠ saldo akun")
    check(not salah, f"A3 {len(rows)} akun neraca saldo = jumlah baris ledger-nya (sumber baris)",
          "; ".join(salah[:3]))

    # A4 setiap jurnal seimbang & Σ semua jurnal = neraca saldo
    js, skip = [], 0
    while True:
        page = get("/gl/journals", owner, skip=skip, limit=200) or []
        js.extend(page)
        if len(page) < 200:
            break
        skip += 200
    tidak_seimbang = [j["entry_no"] for j in js
                      if sum(int(l["debit"]) for l in j["lines"]) != sum(int(l["credit"]) for l in j["lines"])]
    check(js and not tidak_seimbang, f"A4 {len(js)} jurnal masing-masing seimbang",
          f"tidak seimbang: {tidak_seimbang[:3]}")
    jd = sum(int(l["debit"]) for j in js for l in j["lines"])
    check(jd == td, "A5 Σ debit seluruh jurnal = Σ debit neraca saldo (tidak ada jurnal tercecer)",
          f"jurnal {rp(jd)} vs TB {rp(td)}")
    no_dobel = len({j["entry_no"] for j in js}) == len(js)
    check(no_dobel, "A6 nomor jurnal tidak kembar")

    # A7 neraca: aset = kewajiban + ekuitas + laba berjalan, dihitung ulang dari TB per jenis
    bs = get("/gl/balance-sheet", owner)
    by = {}
    for r in rows:
        by[r["type"]] = by.get(r["type"], 0) + int(r["balance"])
    ni = by.get("revenue", 0) - by.get("expense", 0)
    check(by.get("asset", 0) == by.get("liability", 0) + by.get("equity", 0) + ni,
          "A7 aset = kewajiban + ekuitas + laba berjalan (dihitung ulang dari neraca saldo)",
          f"aset {rp(by.get('asset'))} vs {rp(by.get('liability', 0) + by.get('equity', 0) + ni)}")
    check(int(bs["total_assets"]) == by.get("asset", 0)
          and int(bs["total_liabilities"]) == by.get("liability", 0)
          and int(bs["net_income"]) == ni,
          "A8 angka neraca yang dilaporkan = hasil hitung ulang (aset, kewajiban, laba)",
          f"lapor aset {rp(bs['total_assets'])} kewajiban {rp(bs['total_liabilities'])} laba {rp(bs['net_income'])}")
    ist = get("/gl/income-statement", owner)
    check(int(ist["net_income"]) == ni and int(ist["total_revenue"]) == by.get("revenue", 0),
          "A9 laba-rugi kumulatif = pendapatan − beban neraca saldo, dan = laba di neraca",
          f"L/R {rp(ist['net_income'])} vs {rp(ni)}")

    # A10 arus kas: kas akhir = Σ saldo akun kas/bank neraca saldo; awal + perubahan = akhir
    cf = get("/gl/reports/cash-flow", owner)
    kas_tb = sum(int(r["balance"]) for r in rows if r["code"] in set(cf.get("cash_accounts") or []))
    check(int(cf["closing_cash"]) == kas_tb,
          "A10 kas akhir laporan arus kas = Σ saldo akun kas/bank di neraca saldo",
          f"arus kas {rp(cf['closing_cash'])} vs TB {rp(kas_tb)}")
    total_seksi = sum(int(cf[s]["total"]) for s in ("operating", "investing", "financing"))
    check(int(cf["opening_cash"]) + total_seksi == int(cf["closing_cash"])
          and total_seksi == int(cf["net_change"]),
          "A11 kas awal + operasi + investasi + pendanaan = kas akhir (bukan flag `reconciled`)",
          f"awal {rp(cf['opening_cash'])} + {rp(total_seksi)} ≠ akhir {rp(cf['closing_cash'])}")
    return {r["code"]: int(r["balance"]) for r in rows}


# ============================================================ B. GL ↔ buku pembantu
def bagian_b(owner, bal):
    head("B. Saldo GL = buku pembantunya; selisih sah disebut sampai rupiahnya")
    fs = get("/finance/summary", owner)
    bills = list(db.ap_invoices.find({"org_id": ORG}, {"_id": 0}))
    berjurnal = [b for b in bills if b.get("status") not in ("pending_approval", "paid", "rejected", "cancelled")]
    pending = [b for b in bills if b.get("status") == "pending_approval"]
    ap_gl = bal.get("2-1100", 0)
    ap_sub = sum(int(b.get("outstanding", 0) or 0) for b in berjurnal)
    check(ap_gl == ap_sub, "B1 Utang Usaha (2-1100) = Σ sisa tagihan vendor yang SUDAH disetujui",
          f"GL {rp(ap_gl)} vs pembantu {rp(ap_sub)}")
    ap_pending = sum(int(b.get("outstanding", 0) or 0) for b in pending)
    check(int(fs["ap_outstanding"]) == ap_gl + ap_pending,
          "B2 kartu AP Keuangan = GL Utang Usaha + tagihan menunggu approval (selisih SAH, tersebut)",
          f"kartu {rp(fs['ap_outstanding'])} ≠ GL {rp(ap_gl)} + pending {rp(ap_pending)}")
    dril = get("/finance/drilldown/ap_pending", owner)
    drow = sum(int(r.get("amount", 0) or 0) for r in (dril.get("rows") or []))
    check(len(dril.get("rows") or []) == len(pending),
          "B3 baris drilldown 'menunggu approval' = jumlah tagihan pending di pembantu",
          f"{len(dril.get('rows') or [])} vs {len(pending)}; nominal drilldown {rp(drow)}")

    ret_gl = bal.get("2-1200", 0)
    ret_sub = sum(int(b.get("retention_held", 0) or 0) for b in bills
                  if b.get("status") not in ("pending_approval", "rejected", "cancelled") and not b.get("retention_released"))
    ret_reg = sum(int(r.get("amount", 0) or 0) for r in (get("/subcon/retentions", owner) or [])
                  if r.get("state") == "held")
    check(ret_gl == ret_sub, "B4 Utang Retensi (2-1200) = Σ retensi ditahan pada tagihan berjurnal",
          f"GL {rp(ret_gl)} vs pembantu {rp(ret_sub)}")
    check(ret_reg == ret_gl or ret_reg <= ret_sub,
          "B5 register retensi subkon (state=held) tidak melebihi saldo GL retensi",
          f"register {rp(ret_reg)} vs GL {rp(ret_gl)}")
    check(int(fs["ap_retention_held"]) >= ret_gl,
          "B6 kartu retensi ditahan ≥ GL (kartu memuat tagihan pending yang belum berjurnal)",
          f"kartu {rp(fs['ap_retention_held'])} GL {rp(ret_gl)}")

    liab_gl = bal.get("2-1400", 0)
    check(liab_gl == int(fs["contract_liability"]),
          "B7 Uang Muka Penjualan (2-1400) = kewajiban kontrak pada kartu Keuangan",
          f"GL {rp(liab_gl)} vs kartu {rp(fs['contract_liability'])}")
    liabs = list(db.contract_liabilities.find({"org_id": ORG}, {"_id": 0, "balance": 1}))
    check(sum(int(l.get("balance", 0) or 0) for l in liabs) == liab_gl,
          "B8 Σ saldo baris kewajiban kontrak (per transaksi) = GL 2-1400")

    kom_gl = bal.get("2-1600", 0)
    kom = get("/finance/commissions", owner) or []
    kom_sub = sum(int(c.get("amount", 0) or 0) for c in kom if c.get("status") == "approved")
    check(kom_gl == kom_sub, "B9 Utang Komisi (2-1600) = Σ komisi disetujui belum dibayar",
          f"GL {rp(kom_gl)} vs pembantu {rp(kom_sub)}")

    pos = get("/cash-bank/position", owner) or {}
    salah = []
    for a in pos.get("accounts") or []:
        code = a.get("gl_account_code")
        if not code or not a.get("is_active", True):
            continue
        if int(a.get("balance", 0) or 0) != bal.get(code, 0):
            salah.append(f"{a.get('name')} {rp(a.get('balance'))} ≠ GL {code} {rp(bal.get(code, 0))}")
    check((pos.get("accounts") or []) and not salah,
          "B10 saldo setiap rekening kas/bank = saldo akun GL pasangannya", "; ".join(salah[:3]))


# ============================================================ K. penjaga kode
def bagian_k():
    head("K. Kode: saldo selalu dihitung dari jurnal; jurnal tak seimbang ditolak")
    eng = (ROOT / "backend" / "gl_engine.py").read_text(encoding="utf-8")
    check("db.journal_entries.find" in eng.split("async def account_balances")[1].split("async def trial_balance")[0],
          "K1 account_balances menjumlah baris journal_entries (bukan kolom saldo tersimpan)")
    check("Jurnal tidak seimbang" in eng, "K2 post_journal menolak jurnal Dr ≠ Cr")
    check("source_event" in eng and "existing" in eng, "K3 jurnal otomatis idempoten per source_event")
    fe = (ROOT / "backend" / "finance_engine.py").read_text(encoding="utf-8")
    check('b.get("status") != "paid"' in fe,
          "K4 kartu AP memang memuat tagihan pending (definisi tertulis; B2 menjaga selisihnya)")
    check("WORKSHEET_NOTE" in fe, "K5 kartu Keuangan membawa catatan worksheet (tidak mengaku GL penuh)")


def main():
    print("=" * 78)
    print("GATE 70 — Rekonsiliasi GL sampai sumber baris & buku pembantu")
    print("=" * 78)
    owner = login("owner@sipro.co.id")
    try:
        bal = bagian_a(owner)
        bagian_b(owner, bal)
    except Exception as e:  # noqa: BLE001
        check(False, "eksekusi bagian A/B", f"{type(e).__name__}: {e}")
    bagian_k()
    total = PASSED + len(FAIL)
    print("\n" + "-" * 78)
    if FAIL:
        print(f"GATE 70 MERAH — {len(FAIL)} gagal / {total} pemeriksaan")
        for f in FAIL:
            print(f"  - {f}")
        sys.exit(1)
    print(f"GATE 70 HIJAU — {total} pemeriksaan PASSED")


if __name__ == "__main__":
    main()
