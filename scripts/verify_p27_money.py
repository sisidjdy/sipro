#!/usr/bin/env python3
"""verify_p27_money.py — POC/verifikasi INTI Fase 27: kebenaran uang 4 modul baru.

Diuji lewat HTTP nyata (bukan akses DB langsung), pada backend hidup di :8001.

  A. Validasi SSOT      nilai enum liar ditolak 400 dengan pesan Indonesia + grup baru terdaftar
  B. Kas Bon            SoD, pencairan (Dr 1-1500 / Cr kas), pertanggungjawaban (beban + sisa),
                        guard urutan status, akun uang muka kembali NOL setelah settle
  C. Aset Tetap         perolehan, penyusutan bulanan IDEMPOTEN per periode, jadwal,
                        pelepasan dengan LABA dan dengan RUGI, guard fiskal bangunan
  D. Pembiayaan         Σ pokok jadwal == pokok pinjaman (3 metode amortisasi), pencairan
                        netto + provisi, angsuran memisah pokok vs bunga, guard overpay
  E. Marketing Fee      hitung persen/nominal, guard duplikasi & agen nonaktif, approve
                        (utang + PPh), bayar, tie-out 2-1500
  F. Integritas GL      neraca saldo & neraca tetap seimbang + gate invarian bisnis LULUS

Jalankan: python3 scripts/verify_p27_money.py
"""
import json
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

BASE = "http://localhost:8001/api"
PW = "Sipro#2026"
PASS, FAIL = [], []


def call(method, path, token=None, body=None):
    req = urllib.request.Request(BASE + path, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    data = json.dumps(body).encode() if body is not None else None
    try:
        with urllib.request.urlopen(req, data, timeout=60) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw or "{}")
        except json.JSONDecodeError:
            return e.code, {"detail": raw}


def login(email):
    s, r = call("POST", "/auth/login", body={"email": email, "password": PW})
    if s != 200:
        print(f"FATAL: login {email} gagal ({s}): {r}")
        sys.exit(2)
    return r["access_token"]


def check(name, cond, info=""):
    (PASS if cond else FAIL).append(name)
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  → {info}" if info else ""))


def rp(n):
    return f"Rp {int(n or 0):,}"


def tb(token) -> dict:
    """{kode: (debit, kredit)} dari neraca saldo. Fase 82: 1-1100/1-1200 = Σ sub-akun rekening."""
    _s, r = call("GET", "/gl/trial-balance", token)
    book = {row["code"]: (int(row["debit"]), int(row["credit"]))
            for row in (r.get("data") or {}).get("rows", [])}
    for head in ("1-1100", "1-1200"):
        subs = [v for k, v in book.items() if k.startswith(head[:4]) and k != head]
        if subs:
            base = book.get(head, (0, 0))
            book[head] = (base[0] + sum(s[0] for s in subs), base[1] + sum(s[1] for s in subs))
    return book


def bal(book, code, side):
    return book.get(code, (0, 0))[0 if side == "debit" else 1]


def current_period():
    return datetime.now(timezone.utc).strftime("%Y-%m")


# ============================== A. SSOT ==============================
def test_ssot(owner):
    print("\nA. Validasi SSOT nilai enum baru")
    _s, r = call("GET", "/reference", owner)
    reg = r.get("data") or {}
    need = ["cashbon_status", "cashbon_category", "cash_source", "asset_category",
            "asset_tax_group", "depreciation_method", "asset_status", "asset_funding",
            "lender", "lender_type", "loan_type", "amortization_method", "loan_status",
            "installment_status", "agent_type", "agent_status", "marketing_fee_status",
            "marketing_fee_trigger"]
    missing = [g for g in need if g not in reg]
    check("18 grup SSOT Fase 27 terdaftar di /api/reference", not missing, f"hilang={missing}")
    check("grup punya label Indonesia (bukan nama teknis)",
          reg.get("asset_tax_group", {}).get("label") == "Kelompok Fiskal Penyusutan",
          reg.get("asset_tax_group", {}).get("label"))

    s, r = call("POST", "/petty-cash/advances", owner,
                {"purpose": "Uji enum liar", "amount": 100000, "category": "makan-makan"})
    check("kategori kas bon liar ditolak 400 + pesan Indonesia",
          s == 400 and "Kategori Pengeluaran Kas Bon" in str(r.get("detail")),
          f"{s} {r.get('detail')}")
    s, r = call("POST", "/fixed-assets/assets", owner,
                {"name": "Aset uji", "category": "kendaraan", "tax_group": "kelompok_2",
                 "method": "metode_acak", "cost": 1000000})
    check("metode penyusutan liar ditolak 400", s == 400 and "Metode Penyusutan" in str(r.get("detail")),
          f"{s} {r.get('detail')}")
    s, r = call("POST", "/corp-financing/loans", owner,
                {"lender": "BCA", "lender_type": "bank", "loan_type": "kredit_ngawur",
                 "principal": 1000000, "interest_rate_pct": 10, "tenor_months": 12,
                 "amortization_method": "anuitas"})
    check("jenis fasilitas liar ditolak 400",
          s == 400 and "Jenis Fasilitas Pembiayaan" in str(r.get("detail")), f"{s} {r.get('detail')}")
    s, r = call("POST", "/marketing/agents", owner,
                {"name": "Agen Uji Enum", "agent_type": "makelar_gelap"})
    check("jenis agen liar ditolak 400", s == 400 and "Jenis Agen" in str(r.get("detail")),
          f"{s} {r.get('detail')}")


# ============================== B. Kas Bon ==============================
def test_petty_cash(owner, finance, site):
    print("\nB. Kas Bon (petty cash) — siklus penuh & jurnal")
    before = tb(owner)
    s, r = call("POST", "/petty-cash/advances", site,
                {"purpose": "Beli material kecil & retribusi lapangan", "amount": 5000000,
                 "category": "biaya_proyek", "note": "POC Fase 27"})
    adv = (r.get("data") or {})
    check("site engineer bisa mengajukan kas bon", s == 200 and adv.get("status") == "submitted",
          f"{s} no={adv.get('no')}")
    aid = adv.get("id")

    s, _r = call("POST", f"/petty-cash/advances/{aid}/approve", site, {"note": "coba"})
    check("pemohon (site) TIDAK boleh menyetujui (RBAC 403)", s == 403, str(s))

    s, r = call("POST", f"/petty-cash/advances/{aid}/settle", finance,
                {"items": [{"category": "transport", "description": "BBM", "amount": 100000}]})
    check("pertanggungjawaban sebelum dicairkan ditolak 400", s == 400, f"{s} {r.get('detail')}")

    s, r = call("POST", f"/petty-cash/advances/{aid}/approve", finance, {"note": "OK"})
    check("finance menyetujui kas bon", s == 200 and (r.get("data") or {}).get("status") == "approved",
          str(s))

    s, r = call("POST", f"/petty-cash/advances/{aid}/disburse", finance,
                {"amount": 9000000, "source": "kas"})
    check("pencairan melebihi nominal disetujui ditolak 400",
          s == 400 and "melebihi" in str(r.get("detail")), f"{s} {r.get('detail')}")

    s, r = call("POST", f"/petty-cash/advances/{aid}/disburse", finance,
                {"amount": 5000000, "source": "kas"})
    check("finance mencairkan kas bon Rp 5.000.000",
          s == 200 and (r.get("data") or {}).get("status") == "disbursed", str(s))
    mid = tb(owner)
    check("jurnal pencairan: Dr 1-1500 naik 5jt",
          bal(mid, "1-1500", "debit") - bal(before, "1-1500", "debit") == 5000000,
          rp(bal(mid, "1-1500", "debit") - bal(before, "1-1500", "debit")))
    check("jurnal pencairan: Cr 1-1100 Kas naik 5jt",
          bal(mid, "1-1100", "credit") - bal(before, "1-1100", "credit") == 5000000)
    net_advance = (bal(mid, "1-1500", "debit") - bal(mid, "1-1500", "credit")) - \
                  (bal(before, "1-1500", "debit") - bal(before, "1-1500", "credit"))
    check("saldo uang muka karyawan bertambah tepat 5jt", net_advance == 5000000, rp(net_advance))

    s, r = call("GET", "/petty-cash/summary", finance)
    check("ringkasan mencatat kas bon berjalan",
          s == 200 and (r.get("data") or {}).get("outstanding_amount", 0) >= 5000000,
          rp((r.get("data") or {}).get("outstanding_amount")))

    s, r = call("POST", f"/petty-cash/advances/{aid}/settle", site,
                {"items": [{"category": "transport", "description": "BBM & parkir", "amount": 1200000},
                           {"category": "biaya_proyek", "description": "Semen & pasir",
                            "amount": 3000000}],
                 "note": "sisa dikembalikan tunai"})
    doc = r.get("data") or {}
    check("pemohon mengisi pertanggungjawaban 2 item",
          s == 200 and doc.get("status") == "settled" and doc.get("expense_total") == 4200000,
          f"{s} total={rp(doc.get('expense_total'))}")
    check("sisa kas bon dihitung otomatis Rp 800.000",
          doc.get("returned_amount") == 800000 and doc.get("reimburse_amount") == 0,
          rp(doc.get("returned_amount")))
    after = tb(owner)
    check("jurnal pertanggungjawaban: Dr 6-1300 (transport) naik 1,2jt",
          bal(after, "6-1300", "debit") - bal(mid, "6-1300", "debit") == 1200000)
    check("jurnal pertanggungjawaban: Dr 1-1600 WIP (biaya proyek) naik 3jt",
          bal(after, "1-1600", "debit") - bal(mid, "1-1600", "debit") == 3000000)
    check("jurnal pertanggungjawaban: Dr 1-1100 Kas (sisa kembali) naik 800rb",
          bal(after, "1-1100", "debit") - bal(mid, "1-1100", "debit") == 800000)
    net_after = (bal(after, "1-1500", "debit") - bal(after, "1-1500", "credit")) - \
                (bal(before, "1-1500", "debit") - bal(before, "1-1500", "credit"))
    check("akun 1-1500 KEMBALI NOL untuk kas bon ini (tidak ada uang menggantung)",
          net_after == 0, rp(net_after))

    s, r = call("POST", f"/petty-cash/advances/{aid}/settle", site,
                {"items": [{"category": "transport", "description": "dobel", "amount": 1000}]})
    check("pertanggungjawaban dobel ditolak 400", s == 400, f"{s} {r.get('detail')}")

    # SoD: penyetuju tidak boleh menyetujui pengajuannya sendiri
    s, r = call("POST", "/petty-cash/advances", finance,
                {"purpose": "Uji pemisahan tugas kas bon", "amount": 250000,
                 "category": "konsumsi_rapat"})
    own = (r.get("data") or {}).get("id")
    s, r = call("POST", f"/petty-cash/advances/{own}/approve", finance, {})
    check("finance tidak boleh menyetujui kas bon miliknya sendiri (SoD)",
          s == 400 and "Pemisahan tugas" in str(r.get("detail")), f"{s} {r.get('detail')}")
    s, r = call("POST", f"/petty-cash/advances/{own}/cancel", finance)
    check("pemohon dapat membatalkan kas bon yang belum cair",
          s == 200 and (r.get("data") or {}).get("status") == "cancelled", str(s))


# ============================== C. Aset tetap ==============================
def test_assets(owner, finance):
    print("\nC. Aset Tetap — perolehan, penyusutan idempoten, pelepasan")
    before = tb(owner)
    s, r = call("POST", "/fixed-assets/assets", finance,
                {"name": "Mobil operasional pemasaran POC", "category": "kendaraan",
                 "tax_group": "kelompok_2", "method": "garis_lurus", "cost": 240000000,
                 "salvage_value": 0, "funding": "bank", "location": "Kantor pemasaran"})
    a1 = r.get("data") or {}
    check("aset kendaraan tercatat (umur otomatis 96 bln dari kelompok 2)",
          s == 200 and a1.get("useful_life_months") == 96, f"{s} {a1.get('code')}")
    mid = tb(owner)
    check("jurnal perolehan: Dr 1-2100 naik 240jt",
          bal(mid, "1-2100", "debit") - bal(before, "1-2100", "debit") == 240000000)
    check("jurnal perolehan: Cr 1-1200 Bank naik 240jt",
          bal(mid, "1-1200", "credit") - bal(before, "1-1200", "credit") == 240000000)

    s, r = call("POST", "/fixed-assets/assets", finance,
                {"name": "Aset residu salah", "category": "komputer_it", "tax_group": "kelompok_1",
                 "method": "garis_lurus", "cost": 5000000, "salvage_value": 5000000})
    check("nilai residu ≥ harga perolehan ditolak 400",
          s == 400 and "residu" in str(r.get("detail")), f"{s} {r.get('detail')}")
    s, r = call("POST", "/fixed-assets/assets", finance,
                {"name": "Gudang saldo menurun", "category": "bangunan",
                 "tax_group": "bangunan_permanen", "method": "saldo_menurun", "cost": 500000000})
    check("bangunan dengan saldo menurun ditolak 400 (Pasal 11 UU PPh)",
          s == 400 and "garis lurus" in str(r.get("detail")), f"{s} {r.get('detail')}")

    period = current_period()
    s, r = call("POST", "/fixed-assets/depreciation/run", finance, {"period": period})
    run1 = r.get("data") or {}
    check(f"penyusutan periode {period} diposting", s == 200 and run1.get("posted", 0) >= 1,
          f"posted={run1.get('posted')} total={rp(run1.get('total_amount'))}")
    dep = tb(owner)
    delta_exp = bal(dep, "6-1500", "debit") - bal(mid, "6-1500", "debit")
    check("jurnal penyusutan: Dr 6-1500 == total run", delta_exp == run1.get("total_amount"),
          rp(delta_exp))
    check("jurnal penyusutan: Cr 1-2200 == total run",
          bal(dep, "1-2200", "credit") - bal(mid, "1-2200", "credit") == run1.get("total_amount"))

    s, r = call("POST", "/fixed-assets/depreciation/run", finance, {"period": period})
    run2 = r.get("data") or {}
    check("penyusutan periode SAMA dijalankan ulang → 0 jurnal baru (IDEMPOTEN)",
          s == 200 and run2.get("posted") == 0, f"posted={run2.get('posted')}")
    dep2 = tb(owner)
    check("buku besar tidak berubah setelah run kedua",
          bal(dep2, "6-1500", "debit") == bal(dep, "6-1500", "debit"))

    s, r = call("POST", "/fixed-assets/depreciation/run", finance, {"period": "2099-01"})
    check("periode masa depan ditolak 400", s == 400 and "belum berjalan" in str(r.get("detail")),
          f"{s} {r.get('detail')}")
    s, r = call("POST", "/fixed-assets/depreciation/run", finance, {"period": "2026-13"})
    check("format periode salah ditolak 400", s == 400, f"{s} {r.get('detail')}")

    s, r = call("GET", f"/fixed-assets/assets/{a1['id']}", finance)
    d = r.get("data") or {}
    check("beban penyusutan bulanan garis lurus = 2,5jt (240jt / 96)",
          d.get("accumulated_depreciation") == 2500000 and d.get("book_value") == 237500000,
          f"akum={rp(d.get('accumulated_depreciation'))} nilai buku={rp(d.get('book_value'))}")
    check("jadwal penyusutan sisa 95 bulan", len(r.get("schedule") or []) == 95,
          str(len(r.get("schedule") or [])))
    check("riwayat penyusutan aset tercatat 1 entri", len(r.get("history") or []) == 1)

    # Pelepasan dengan LABA
    pre = tb(owner)
    s, r = call("POST", f"/fixed-assets/assets/{a1['id']}/dispose", finance,
                {"proceeds": 250000000, "source": "bank", "note": "dijual ke pihak ketiga"})
    dd = r.get("data") or {}
    gain = 250000000 - 237500000
    check("pelepasan aset dengan LABA dihitung benar",
          s == 200 and dd.get("status") == "disposed" and dd.get("disposal_gain_loss") == gain,
          f"{s} laba={rp(dd.get('disposal_gain_loss'))}")
    post = tb(owner)
    check("jurnal pelepasan: Cr 1-2100 == harga perolehan 240jt",
          bal(post, "1-2100", "credit") - bal(pre, "1-2100", "credit") == 240000000)
    check("jurnal pelepasan: Dr 1-2200 == akumulasi 2,5jt",
          bal(post, "1-2200", "debit") - bal(pre, "1-2200", "debit") == 2500000)
    check("jurnal pelepasan: Cr 4-1300 == laba 12,5jt",
          bal(post, "4-1300", "credit") - bal(pre, "4-1300", "credit") == gain,
          rp(bal(post, "4-1300", "credit") - bal(pre, "4-1300", "credit")))
    s, r = call("POST", f"/fixed-assets/assets/{a1['id']}/dispose", finance, {"proceeds": 1})
    check("pelepasan dua kali ditolak 400", s == 400, f"{s} {r.get('detail')}")

    # Pelepasan dengan RUGI
    s, r = call("POST", "/fixed-assets/assets", finance,
                {"name": "Laptop desain POC", "category": "komputer_it", "tax_group": "kelompok_1",
                 "method": "garis_lurus", "cost": 12000000, "funding": "kas"})
    a2 = r.get("data") or {}
    check("aset komputer kelompok 1 = 48 bulan", a2.get("useful_life_months") == 48)
    pre2 = tb(owner)
    s, r = call("POST", f"/fixed-assets/assets/{a2['id']}/dispose", finance,
                {"proceeds": 8000000, "source": "kas"})
    dd2 = r.get("data") or {}
    check("pelepasan aset dengan RUGI dihitung benar (12jt → 8jt = rugi 4jt)",
          s == 200 and dd2.get("disposal_gain_loss") == -4000000,
          rp(dd2.get("disposal_gain_loss")))
    post2 = tb(owner)
    check("jurnal pelepasan: Dr 6-1800 == rugi 4jt",
          bal(post2, "6-1800", "debit") - bal(pre2, "6-1800", "debit") == 4000000)

    s, r = call("GET", "/fixed-assets/summary", finance)
    sm = r.get("data") or {}
    check("ringkasan aset: nilai buku = perolehan − akumulasi",
          s == 200 and sm.get("total_book_value") == sm.get("total_cost") - sm.get("total_accumulated"),
          f"cost={rp(sm.get('total_cost'))} book={rp(sm.get('total_book_value'))}")


# ============================== D. Pembiayaan ==============================
def test_loans(owner, finance):
    print("\nD. Pembiayaan korporat — jadwal, pencairan, angsuran")
    body = {"lender": "BCA", "lender_type": "bank", "loan_type": "kredit_investasi",
            "principal": 2400000000, "interest_rate_pct": 12, "tenor_months": 24,
            "amortization_method": "anuitas", "provision_fee": 24000000,
            "collateral": "Sertifikat HGB Cluster Asri"}
    s, r = call("POST", "/corp-financing/loans", finance, body)
    loan = r.get("data") or {}
    check("fasilitas kredit investasi tercatat (status draf)",
          s == 200 and loan.get("status") == "draft", f"{s} {loan.get('no')}")
    lid = loan.get("id")

    s, r = call("GET", f"/corp-financing/loans/{lid}", finance)
    prev = r.get("schedule_preview") or []
    check("pratinjau jadwal 24 angsuran tersedia sebelum pencairan", len(prev) == 24)
    check("Σ pokok pratinjau == pokok pinjaman TEPAT (anuitas)",
          sum(x["principal"] for x in prev) == 2400000000,
          rp(sum(x["principal"] for x in prev)))

    before = tb(owner)
    s, r = call("POST", f"/corp-financing/loans/{lid}/activate", finance,
                {"source": "bank", "note": "pencairan penuh"})
    act = r.get("data") or {}
    check("pencairan fasilitas → status aktif + jadwal terbit",
          s == 200 and act.get("status") == "active" and len(act.get("schedule") or []) == 24, str(s))
    mid = tb(owner)
    check("jurnal pencairan: Dr 1-1200 Bank naik netto 2.376.000.000",
          bal(mid, "1-1200", "debit") - bal(before, "1-1200", "debit") == 2376000000,
          rp(bal(mid, "1-1200", "debit") - bal(before, "1-1200", "debit")))
    check("jurnal pencairan: Dr 6-1600 provisi 24jt",
          bal(mid, "6-1600", "debit") - bal(before, "6-1600", "debit") == 24000000)
    check("jurnal pencairan: Cr 2-2100 Utang Bank 2,4 M",
          bal(mid, "2-2100", "credit") - bal(before, "2-2100", "credit") == 2400000000)
    check("Σ pokok jadwal tersimpan == pokok pinjaman",
          sum(x["principal"] for x in act["schedule"]) == 2400000000)

    inst1 = act["schedule"][0]
    s, r = call("POST", f"/corp-financing/loans/{lid}/pay", finance,
                {"installment_no": 1, "amount": inst1["total"] + 1, "source": "bank"})
    check("pembayaran melebihi sisa angsuran ditolak 400",
          s == 400 and "melebihi" in str(r.get("detail")), f"{s} {r.get('detail')}")
    s, r = call("POST", f"/corp-financing/loans/{lid}/pay", finance,
                {"installment_no": 99, "amount": 1000, "source": "bank"})
    check("angsuran nomor tidak ada ditolak 400", s == 400, f"{s} {r.get('detail')}")

    s, r = call("POST", f"/corp-financing/loans/{lid}/pay", finance,
                {"installment_no": 1, "amount": inst1["total"], "source": "bank"})
    paid = r.get("data") or {}
    after = tb(owner)
    check("angsuran ke-1 dibayar penuh → status lunas",
          s == 200 and paid["schedule"][0]["status"] == "paid", str(s))
    check("jurnal angsuran: Dr 2-2100 == porsi pokok",
          bal(after, "2-2100", "debit") - bal(mid, "2-2100", "debit") == inst1["principal"],
          rp(inst1["principal"]))
    check("jurnal angsuran: Dr 6-1600 == porsi bunga",
          bal(after, "6-1600", "debit") - bal(mid, "6-1600", "debit") == inst1["interest"],
          rp(inst1["interest"]))
    check("jurnal angsuran: Cr Bank == total angsuran",
          bal(after, "1-1200", "credit") - bal(mid, "1-1200", "credit") == inst1["total"])
    check("sisa pokok = pokok − pokok terbayar",
          paid.get("outstanding_principal") == 2400000000 - inst1["principal"],
          rp(paid.get("outstanding_principal")))
    check("bunga bulan pertama = 12%/12 × 2,4 M = 24jt", inst1["interest"] == 24000000,
          rp(inst1["interest"]))

    s, r = call("POST", f"/corp-financing/loans/{lid}/pay", finance,
                {"installment_no": 1, "amount": 1000, "source": "bank"})
    check("angsuran yang sudah lunas tidak bisa dibayar lagi (400)",
          s == 400 and "lunas" in str(r.get("detail")), f"{s} {r.get('detail')}")

    inst2 = paid["schedule"][1]
    s, r = call("POST", f"/corp-financing/loans/{lid}/pay", finance,
                {"installment_no": 2, "amount": inst2["interest"], "source": "bank"})
    part = r.get("data") or {}
    check("pembayaran sebagian dialokasikan ke BUNGA dulu",
          s == 200 and part["schedule"][1]["status"] == "partial"
          and part["schedule"][1]["paid_interest"] == inst2["interest"]
          and part["schedule"][1]["paid_principal"] == 0, str(s))

    # Metode lain: Σ pokok harus tetap tepat
    for method, tenor, rate in (("pokok_tetap", 36, 11.5), ("flat", 18, 9.75)):
        s, r = call("POST", "/corp-financing/loans", finance,
                    {"lender": "Adira Finance", "lender_type": "multifinance",
                     "loan_type": "leasing_kendaraan", "principal": 777777777,
                     "interest_rate_pct": rate, "tenor_months": tenor,
                     "amortization_method": method})
        nid = (r.get("data") or {}).get("id")
        _s2, r2 = call("GET", f"/corp-financing/loans/{nid}", finance)
        sched = r2.get("schedule_preview") or []
        check(f"Σ pokok jadwal metode '{method}' == pokok pinjaman TEPAT",
              len(sched) == tenor and sum(x["principal"] for x in sched) == 777777777,
              rp(sum(x["principal"] for x in sched)))

    s, r = call("GET", "/corp-financing/summary", finance)
    sm = r.get("data") or {}
    book = tb(owner)
    gl_out = bal(book, "2-2100", "credit") - bal(book, "2-2100", "debit")
    check("sisa pokok ringkasan == saldo GL 2-2100 (tie-out)",
          sm.get("outstanding_principal") == gl_out,
          f"subledger={rp(sm.get('outstanding_principal'))} GL={rp(gl_out)}")
    s, r = call("GET", "/corp-financing/payments", finance)
    check("riwayat pembayaran angsuran bisa ditelusuri", s == 200 and (r.get("total") or 0) >= 2,
          str(r.get("total")))


# ============================== E. Marketing fee ==============================
def test_marketing_fee(owner, finance, manager):
    print("\nE. Marketing Fee agen eksternal")
    s, r = call("POST", "/marketing/agents", manager,
                {"name": "PT Mitra Properti POC", "agent_type": "broker_kantor",
                 "company": "PT Mitra Properti", "phone": "08123456789",
                 "bank_name": "BCA", "bank_account": "1234567890"})
    agent = r.get("data") or {}
    check("sales manager mendaftarkan agen eksternal", s == 200 and agent.get("status") == "active",
          f"{s} {agent.get('code')}")
    s, r = call("POST", "/marketing/agents", manager,
                {"name": "PT Mitra Properti POC", "agent_type": "broker_kantor"})
    check("nama agen duplikat ditolak 400", s == 400 and "sudah terdaftar" in str(r.get("detail")),
          f"{s} {r.get('detail')}")

    _s, r = call("GET", "/deals", owner)
    deals = r.get("data") or []
    deal = next((d for d in deals if int(d.get("price", 0)) > 0), None)
    if not deal:
        check("ada deal untuk diuji marketing fee", False, "tidak ada deal berharga")
        return
    price = int(deal["price"])

    s, r = call("POST", "/marketing/fees", manager,
                {"agent_id": agent["id"], "deal_id": deal["id"], "basis": "percent",
                 "value": 2, "trigger": "ppjb", "pph_pct": 2})
    fee = r.get("data") or {}
    gross = round(price * 0.02)
    pph = round(gross * 0.02)
    check("fee 2% dari harga jual dihitung otomatis + PPh dipotong",
          s == 200 and fee.get("amount_gross") == gross and fee.get("pph_amount") == pph
          and fee.get("amount_net") == gross - pph,
          f"{s} bruto={rp(fee.get('amount_gross'))} netto={rp(fee.get('amount_net'))}")
    fid = fee.get("id")

    s, r = call("POST", "/marketing/fees", manager,
                {"agent_id": agent["id"], "deal_id": deal["id"], "basis": "percent",
                 "value": 2, "trigger": "ppjb"})
    check("pengajuan dobel (agen+deal+pemicu sama) ditolak 400",
          s == 400 and "sudah diajukan" in str(r.get("detail")), f"{s} {r.get('detail')}")

    s, r = call("POST", f"/marketing/fees/{fid}/pay", finance, {})
    check("bayar sebelum disetujui ditolak 400", s == 400 and "disetujui" in str(r.get("detail")),
          f"{s} {r.get('detail')}")

    before = tb(owner)
    s, r = call("POST", f"/marketing/fees/{fid}/approve", finance, {"note": "sesuai kontrak"})
    check("finance menyetujui fee", s == 200 and (r.get("data") or {}).get("status") == "approved",
          str(s))
    mid = tb(owner)
    check("jurnal approve: Dr 6-1200 Beban Pemasaran == bruto",
          bal(mid, "6-1200", "debit") - bal(before, "6-1200", "debit") == gross, rp(gross))
    check("jurnal approve: Cr 2-1500 Utang Marketing Fee == netto",
          bal(mid, "2-1500", "credit") - bal(before, "2-1500", "credit") == gross - pph)
    check("jurnal approve: Cr 2-1300 Utang Pajak == PPh dipotong",
          bal(mid, "2-1300", "credit") - bal(before, "2-1300", "credit") == pph, rp(pph))

    s, r = call("POST", f"/marketing/fees/{fid}/pay", finance,
                {"amount": gross, "source": "bank"})
    check("pembayaran melebihi netto ditolak 400", s == 400 and "melebihi" in str(r.get("detail")),
          f"{s} {r.get('detail')}")
    s, r = call("POST", f"/marketing/fees/{fid}/pay", finance, {"source": "bank"})
    paid = r.get("data") or {}
    check("fee dibayar penuh → status Dibayar",
          s == 200 and paid.get("status") == "paid" and paid.get("paid_amount") == gross - pph,
          f"{s} {rp(paid.get('paid_amount'))}")
    after = tb(owner)
    check("jurnal bayar: Dr 2-1500 == netto",
          bal(after, "2-1500", "debit") - bal(mid, "2-1500", "debit") == gross - pph)
    check("jurnal bayar: Cr 1-1200 Bank == netto",
          bal(after, "1-1200", "credit") - bal(mid, "1-1200", "credit") == gross - pph)

    s, r = call("GET", "/marketing/summary", finance)
    sm = r.get("data") or {}
    gl_payable = bal(after, "2-1500", "credit") - bal(after, "2-1500", "debit")
    check("utang marketing fee subledger == saldo GL 2-1500 (tie-out)",
          sm.get("payable_amount") == gl_payable,
          f"subledger={rp(sm.get('payable_amount'))} GL={rp(gl_payable)}")
    check("papan peringkat agen terisi",
          any(x["agent_id"] == agent["id"] for x in sm.get("leaderboard") or []))

    s, _r = call("PUT", f"/marketing/agents/{agent['id']}", manager, {"status": "inactive"})
    s, r = call("POST", "/marketing/fees", manager,
                {"agent_id": agent["id"], "deal_id": deal["id"], "basis": "fixed",
                 "value": 5000000, "trigger": "akad"})
    check("pengajuan untuk agen nonaktif ditolak 400",
          s == 400 and "tidak aktif" in str(r.get("detail")), f"{s} {r.get('detail')}")


# ============================== F. Integritas GL ==============================
def test_gl(owner):
    print("\nF. Integritas buku besar & gate invarian")
    s, r = call("GET", "/gl/trial-balance", owner)
    d = r.get("data") or {}
    check("neraca saldo seimbang (debit == kredit)", s == 200 and d.get("balanced") is True,
          f"{rp(d.get('total_debit'))} vs {rp(d.get('total_credit'))}")
    s, r = call("GET", "/gl/balance-sheet", owner)
    d = r.get("data") or {}
    check("neraca seimbang (aset == kewajiban + ekuitas + laba)",
          s == 200 and d.get("balanced") is True,
          f"aset={rp(d.get('total_assets'))} pasiva={rp(d.get('total_liab_equity'))}")
    proc = subprocess.run([sys.executable, "/app/scripts/verify_business_invariants.py"],
                          capture_output=True, text=True, timeout=300)
    check("gate verify_business_invariants LULUS setelah semua transaksi Fase 27",
          proc.returncode == 0, (proc.stdout or "")[-400:] if proc.returncode else "")


def main():
    owner = login("owner@sipro.co.id")
    finance = login("finance@sipro.co.id")
    site = login("site@sipro.co.id")
    manager = login("manager@sipro.co.id")
    print("=" * 78)
    print("VERIFIKASI INTI FASE 27 — Kas Bon / Aset Tetap / Pembiayaan / Marketing Fee")
    print("=" * 78)
    test_ssot(owner)
    test_petty_cash(owner, finance, site)
    test_assets(owner, finance)
    test_loans(owner, finance)
    test_marketing_fee(owner, finance, manager)
    test_gl(owner)
    total = len(PASS) + len(FAIL)
    print("\n" + "=" * 78)
    print(f"HASIL: {len(PASS)}/{total} PASS, {len(FAIL)} FAIL")
    if FAIL:
        for f in FAIL:
            print(f"  - GAGAL: {f}")
    print("=" * 78)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
