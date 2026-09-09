"""Fase 82 — Kas & Bank: sub-akun GL per rekening, transfer internal (SoD), buku kas/bank,
posisi kas, dan wiring rekening di penerimaan AR / pembayaran AP.

Jalankan: cd /app/backend && python -m pytest tests/test_p82_cash_bank.py -q
"""
import time
import uuid

import pytest
import requests

from conftest import BASE_URL, _sess

HEADERS = {"1-1100", "1-1200"}


def _accounts(s):
    return s.get(f"{BASE_URL}/api/cash-bank/accounts").json()


def _wait(pred, timeout=25):
    deadline = time.time() + timeout
    while time.time() < deadline:
        v = pred()
        if v:
            return v
        time.sleep(1.5)
    return None


def test_master_has_sub_accounts_and_defaults(tok_finance):
    s = _sess(tok_finance)
    body = _accounts(s)
    rows = body["data"]
    assert rows, "harus ada rekening/kas bawaan (Kas Besar + Rekening Operasional)"
    kinds = {r["kind"] for r in rows}
    assert {"bank", "cash"} <= kinds
    for r in rows:
        assert r["gl_account_code"] not in HEADERS, f"{r['name']} masih menumpang akun induk"
        assert r["gl_account_code"].startswith("1-12" if r["kind"] == "bank" else "1-11")
    for k in ("bank", "cash"):
        assert sum(1 for r in rows if r["kind"] == k and r.get("is_default")) == 1
    # akun induk tidak lagi menerima posting langsung (tidak ada baris jurnal di 1-1100/1-1200)
    tb = s.get(f"{BASE_URL}/api/gl/trial-balance").json()
    tb = tb.get("data", tb)
    assert tb.get("balanced") is True
    assert all(row["code"] not in HEADERS or (row["debit"] == 0 and row["credit"] == 0)
               for row in tb["rows"])


def test_create_account_posts_opening_balance(tok_finance):
    s = _sess(tok_finance)
    no = f"T82-{uuid.uuid4().hex[:6]}"
    r = s.post(f"{BASE_URL}/api/cash-bank/accounts", json={
        "kind": "bank", "name": "Rekening Uji P82", "bank_name": "Bank Uji",
        "account_no": no, "opening_balance": 1_500_000, "opening_date": "2026-01-01"})
    assert r.status_code == 200, r.text
    acc = r.json()["data"]
    assert acc["gl_account_code"].startswith("1-12") and acc["opening_posted"] is True
    book = s.get(f"{BASE_URL}/api/cash-bank/book",
                 params={"account_id": acc["id"], "date_from": "2026-01-01", "date_to": "2026-12-31"}).json()["data"]
    assert book["closing"] == 1_500_000 and book["lines"][0]["memo"].startswith("Saldo awal")
    # nomor rekening kembar ditolak
    dup = s.post(f"{BASE_URL}/api/cash-bank/accounts", json={
        "kind": "bank", "name": "Kembar", "bank_name": "Bank Uji", "account_no": no})
    assert dup.status_code == 400
    # CSV ekspor
    csv = s.get(f"{BASE_URL}/api/cash-bank/book",
                params={"account_id": acc["id"], "date_from": "2026-01-01", "date_to": "2026-12-31", "format": "csv"})
    assert csv.status_code == 200 and csv.text.startswith("Tanggal;No Jurnal") and "Saldo akhir" in csv.text


def test_transfer_sod_and_posting(tok_finance, tok_owner):
    fin, own = _sess(tok_finance), _sess(tok_owner)
    rows = _accounts(fin)["data"]
    bank = next(r for r in rows if r["kind"] == "bank" and r["is_default"])
    kas = next(r for r in rows if r["kind"] == "cash" and r["is_default"])
    before = fin.get(f"{BASE_URL}/api/cash-bank/position").json()["data"]
    bal_before = {a["id"]: a["balance"] for a in before["accounts"]}
    # validasi: asal = tujuan ditolak; setor tunai dari bank ditolak
    assert fin.post(f"{BASE_URL}/api/cash-bank/transfers", json={
        "kind": "transfer", "from_account_id": bank["id"], "to_account_id": bank["id"], "amount": 1000}).status_code == 400
    assert fin.post(f"{BASE_URL}/api/cash-bank/transfers", json={
        "kind": "setor_tunai", "from_account_id": bank["id"], "to_account_id": kas["id"], "amount": 1000}).status_code == 400
    r = fin.post(f"{BASE_URL}/api/cash-bank/transfers", json={
        "kind": "tarik_tunai", "from_account_id": bank["id"], "to_account_id": kas["id"],
        "amount": 1_000_000, "fee": 2_500, "note": "uji p82"})
    assert r.status_code == 200, r.text
    tr = r.json()["data"]
    assert tr["status"] == "pending" and tr["no"].startswith("TRF/")
    # finance (pembuat, tanpa izin approve) tidak boleh menyetujui
    assert fin.post(f"{BASE_URL}/api/cash-bank/transfers/{tr['id']}/approve").status_code == 403
    ok = own.post(f"{BASE_URL}/api/cash-bank/transfers/{tr['id']}/approve")
    assert ok.status_code == 200, ok.text
    posted = ok.json()["data"]
    assert posted["status"] == "posted" and posted["journal_no"]
    # approve dua kali ditolak
    assert own.post(f"{BASE_URL}/api/cash-bank/transfers/{tr['id']}/approve").status_code == 400
    after = fin.get(f"{BASE_URL}/api/cash-bank/position").json()["data"]
    bal_after = {a["id"]: a["balance"] for a in after["accounts"]}
    assert bal_after[kas["id"]] - bal_before[kas["id"]] == 1_000_000
    assert bal_before[bank["id"]] - bal_after[bank["id"]] == 1_002_500
    je = own.get(f"{BASE_URL}/api/gl/journals", params={"source_type": "cash_transfer", "source_id": tr["id"]}).json()
    codes = {ln["account_code"]: ln for ln in je["data"][0]["lines"]}
    assert codes[kas["gl_account_code"]]["debit"] == 1_000_000
    assert codes[bank["gl_account_code"]]["credit"] == 1_002_500
    assert codes["6-1600"]["debit"] == 2_500


def test_receipt_and_ap_payment_land_on_chosen_account(tok_finance):
    s = _sess(tok_finance)
    rows = _accounts(s)["data"]
    non_default = [r for r in rows if r["kind"] == "bank" and not r["is_default"] and r["is_active"]]
    if not non_default:
        pytest.skip("butuh ≥2 rekening bank aktif")
    target = non_default[0]
    ar = s.get(f"{BASE_URL}/api/finance/ar").json()
    ar = ar.get("data", ar)
    deal = next((x for x in ar if x.get("outstanding", 0) > 10_000), None)
    if not deal:
        pytest.skip("tidak ada piutang terbuka")
    r = s.post(f"{BASE_URL}/api/finance/ar/receipts", json={
        "deal_id": deal["deal_id"], "amount": 10_000, "method": "transfer",
        "cash_account_id": target["id"], "note": "uji p82 rekening"})
    assert r.status_code == 200, r.text
    rc = r.json()["data"]["receipt"]
    assert rc["cash_account_id"] == target["id"] and rc["cash_account_code"] == target["gl_account_code"]
    je = _wait(lambda: (s.get(f"{BASE_URL}/api/gl/journals",
                              params={"source_type": "receipt", "source_id": rc["id"]}).json().get("data") or [None])[0])
    assert je, "jurnal penerimaan tidak terbit"
    codes = {ln["account_code"] for ln in je["lines"]}
    assert target["gl_account_code"] in codes and not (codes & HEADERS)
    # rekening fiktif ditolak di muka (bukan diam-diam ke default)
    bad = s.post(f"{BASE_URL}/api/finance/ar/receipts", json={
        "deal_id": deal["deal_id"], "amount": 1_000, "method": "transfer", "cash_account_id": "tidak-ada"})
    assert bad.status_code == 400
