"""Fase 82 ext — RBAC, validasi transfer, reject, AP payment rekening, trial balance 3-1950,
posisi kas & seed demo. Jalankan: cd /app/backend && python -m pytest tests/test_p82_ext.py -q
"""
import time
import uuid

import pytest

from conftest import BASE_URL, _sess

HEADERS = {"1-1100", "1-1200"}


def _accounts(s):
    return s.get(f"{BASE_URL}/api/cash-bank/accounts").json()["data"]


def _wait(pred, timeout=30):
    end = time.time() + timeout
    while time.time() < end:
        v = pred()
        if v:
            return v
        time.sleep(2)
    return None


# ---------------------------------------------------------------- RBAC
class TestRbac:
    def test_sales_forbidden(self, tok_sales):
        s = _sess(tok_sales)
        for path in ("/api/cash-bank/position", "/api/cash-bank/accounts",
                     "/api/cash-bank/transfers", "/api/cash-bank/book"):
            r = s.get(f"{BASE_URL}{path}")
            assert r.status_code == 403, f"{path} → {r.status_code}"

    def test_finance_cannot_approve(self, tok_finance, tok_owner):
        fin, own = _sess(tok_finance), _sess(tok_owner)
        rows = _accounts(fin)
        bank = next(r for r in rows if r["kind"] == "bank" and r["is_default"])
        kas = next(r for r in rows if r["kind"] == "cash" and r["is_default"])
        tr = fin.post(f"{BASE_URL}/api/cash-bank/transfers", json={
            "kind": "tarik_tunai", "from_account_id": bank["id"], "to_account_id": kas["id"],
            "amount": 50_000, "note": "QA rbac"}).json()["data"]
        assert fin.post(f"{BASE_URL}/api/cash-bank/transfers/{tr['id']}/approve").status_code == 403
        assert fin.post(f"{BASE_URL}/api/cash-bank/transfers/{tr['id']}/reject",
                        json={"reason": "x"}).status_code == 403
        # bersihkan: owner tolak
        rj = own.post(f"{BASE_URL}/api/cash-bank/transfers/{tr['id']}/reject",
                      json={"reason": "QA cleanup"})
        assert rj.status_code == 200, rj.text
        assert rj.json()["data"]["status"] == "rejected"
        assert rj.json()["data"]["reject_reason"] == "QA cleanup"


# ---------------------------------------------------------------- validasi transfer
class TestTransferValidation:
    def test_rules(self, tok_finance, tok_owner):
        fin, own = _sess(tok_finance), _sess(tok_owner)
        rows = _accounts(fin)
        bank = next(r for r in rows if r["kind"] == "bank" and r["is_default"])
        kas = next(r for r in rows if r["kind"] == "cash" and r["is_default"])
        # sama
        r1 = fin.post(f"{BASE_URL}/api/cash-bank/transfers", json={
            "kind": "transfer", "from_account_id": kas["id"], "to_account_id": kas["id"],
            "amount": 1000})
        assert r1.status_code == 400 and "sama" in r1.json()["detail"].lower()
        # setor_tunai dari bank
        r2 = fin.post(f"{BASE_URL}/api/cash-bank/transfers", json={
            "kind": "setor_tunai", "from_account_id": bank["id"], "to_account_id": bank["id"],
            "amount": 1000})
        assert r2.status_code == 400
        # saldo tidak cukup
        r3 = fin.post(f"{BASE_URL}/api/cash-bank/transfers", json={
            "kind": "tarik_tunai", "from_account_id": bank["id"], "to_account_id": kas["id"],
            "amount": 10 ** 15})
        assert r3.status_code == 400 and "tidak" in r3.json()["detail"].lower() \
            and "cukup" in r3.json()["detail"].lower()
        # nominal 0
        r4 = fin.post(f"{BASE_URL}/api/cash-bank/transfers", json={
            "kind": "transfer", "from_account_id": bank["id"], "to_account_id": kas["id"],
            "amount": 0})
        assert r4.status_code in (400, 422)
        # isi_kas_kecil tujuan harus kas
        r5 = fin.post(f"{BASE_URL}/api/cash-bank/transfers", json={
            "kind": "isi_kas_kecil", "from_account_id": bank["id"], "to_account_id": bank["id"],
            "amount": 1000})
        assert r5.status_code == 400

    def test_sod_self_approve(self, tok_owner):
        own = _sess(tok_owner)
        rows = _accounts(own)
        bank = next(r for r in rows if r["kind"] == "bank" and r["is_default"])
        kas = next(r for r in rows if r["kind"] == "cash" and r["is_default"])
        tr = own.post(f"{BASE_URL}/api/cash-bank/transfers", json={
            "kind": "tarik_tunai", "from_account_id": bank["id"], "to_account_id": kas["id"],
            "amount": 25_000, "note": "QA sod"}).json()["data"]
        r = own.post(f"{BASE_URL}/api/cash-bank/transfers/{tr['id']}/approve")
        assert r.status_code == 400, r.text
        assert "Pembuat transaksi tidak boleh menyetujui" in r.json()["detail"]
        own.post(f"{BASE_URL}/api/cash-bank/transfers/{tr['id']}/reject",
                 json={"reason": "QA cleanup sod"})


# ---------------------------------------------------------------- master rekening
class TestMaster:
    def test_update_and_set_default(self, tok_finance):
        s = _sess(tok_finance)
        no = f"QA82-{uuid.uuid4().hex[:6]}"
        acc = s.post(f"{BASE_URL}/api/cash-bank/accounts", json={
            "kind": "bank", "name": "Rekening Uji QA", "bank_name": "Bank BNI",
            "account_no": no, "opening_balance": 2_000_000}).json()["data"]
        assert acc["gl_account_code"].startswith("1-12")
        # update nama
        up = s.put(f"{BASE_URL}/api/cash-bank/accounts/{acc['id']}",
                   json={"name": "Rekening Uji QA2"})
        assert up.status_code == 200, up.text
        assert up.json()["data"]["name"] == "Rekening Uji QA2"
        fresh = next(r for r in _accounts(s) if r["id"] == acc["id"])
        assert fresh["name"] == "Rekening Uji QA2" and fresh["balance"] == 2_000_000
        # set default lalu kembalikan
        prev = next(r for r in _accounts(s) if r["kind"] == "bank" and r["is_default"])
        sd = s.post(f"{BASE_URL}/api/cash-bank/accounts/{acc['id']}/set-default")
        assert sd.status_code == 200, sd.text
        rows = _accounts(s)
        assert sum(1 for r in rows if r["kind"] == "bank" and r["is_default"]) == 1
        assert next(r for r in rows if r["id"] == acc["id"])["is_default"] is True
        assert s.post(f"{BASE_URL}/api/cash-bank/accounts/{prev['id']}/set-default").status_code == 200
        # nonaktifkan rekening uji
        assert s.put(f"{BASE_URL}/api/cash-bank/accounts/{acc['id']}",
                     json={"is_active": False}).status_code == 200

    def test_seed_demo_rows_present(self, tok_finance):
        rows = _accounts(_sess(tok_finance))
        names = {r["name"] for r in rows}
        for expected in ("Rekening Operasional", "Rekening Escrow", "Kas Besar", "Kas Kecil Site"):
            assert expected in names, f"seed {expected} hilang; ada: {sorted(names)}"


# ---------------------------------------------------------------- posisi & buku
class TestPositionBook:
    def test_position_shape(self, tok_finance):
        s = _sess(tok_finance)
        data = s.get(f"{BASE_URL}/api/cash-bank/position").json()["data"]
        assert len(data["accounts"]) >= 4
        assert data["total"] == data["total_cash"] + data["total_bank"]
        for r in data["accounts"]:
            assert r["gl_account_code"] not in HEADERS
            assert isinstance(r["balance"], int)

    def test_book_csv_and_range(self, tok_finance):
        s = _sess(tok_finance)
        acc = next(r for r in _accounts(s) if r["kind"] == "bank" and r["is_default"])
        b = s.get(f"{BASE_URL}/api/cash-bank/book", params={
            "account_id": acc["id"], "date_from": "2026-01-01", "date_to": "2026-12-31"}).json()["data"]
        assert b["account"]["id"] == acc["id"]
        assert b["closing"] == b["opening"] + b["total_in"] - b["total_out"]
        if b["lines"]:
            assert b["lines"][-1]["balance"] == b["closing"]
        csv = s.get(f"{BASE_URL}/api/cash-bank/book", params={
            "account_id": acc["id"], "date_from": "2026-01-01", "date_to": "2026-12-31",
            "format": "csv"})
        assert csv.status_code == 200
        assert "text/csv" in csv.headers.get("content-type", "")
        assert csv.text.startswith("Tanggal;No Jurnal")
        bad = s.get(f"{BASE_URL}/api/cash-bank/book", params={
            "account_id": "tidak-ada", "date_from": "2026-01-01", "date_to": "2026-12-31"})
        assert bad.status_code == 400
        rng = s.get(f"{BASE_URL}/api/cash-bank/book", params={
            "account_id": acc["id"], "date_from": "2026-05-01", "date_to": "2026-01-01"})
        assert rng.status_code == 400


# ---------------------------------------------------------------- AP payment
class TestApPayment:
    def test_ap_pay_uses_chosen_account(self, tok_finance):
        s = _sess(tok_finance)
        rows = _accounts(s)
        target = next((r for r in rows if r["kind"] == "bank" and not r["is_default"]
                       and r["is_active"] and r["balance"] > 100_000), None)
        if not target:
            pytest.skip("tidak ada rekening bank non-default bersaldo")
        bills = s.get(f"{BASE_URL}/api/finance/ap/bills").json()
        bills = bills.get("data", bills)
        bill = next((b for b in bills if (b.get("outstanding") or 0) > 10_000
                     and b.get("status") in ("approved", "partial", "unpaid", "open")), None)
        if not bill:
            pytest.skip(f"tidak ada tagihan AP terbuka (total {len(bills)})")
        r = s.post(f"{BASE_URL}/api/finance/ap/bills/{bill['id']}/pay", json={
            "amount": 10_000, "method": "transfer", "cash_account_id": target["id"],
            "note": "QA p82 ap"})
        assert r.status_code == 200, r.text
        def _payment_je():
            rows = s.get(f"{BASE_URL}/api/gl/journals", params={
                "source_type": "ap_bill", "source_id": bill["id"]}).json().get("data") or []
            pays = [j for j in rows if "pembayaran" in (j.get("memo") or "").lower()]
            return pays[-1] if pays else None

        je = _wait(_payment_je)
        assert je, "jurnal pembayaran AP tidak terbit"
        credits = {ln["account_code"] for ln in je["lines"] if int(ln.get("credit") or 0) > 0}
        assert target["gl_account_code"] in credits, f"kredit di {credits}"
        assert not (credits & HEADERS)


# ---------------------------------------------------------------- trial balance
class TestTrialBalance:
    def test_headers_zero_and_opening_equity(self, tok_owner, tok_finance):
        own = _sess(tok_owner)
        tb = own.get(f"{BASE_URL}/api/gl/trial-balance").json()
        tb = tb.get("data", tb)
        assert tb.get("balanced") is True
        by_code = {r["code"]: r for r in tb["rows"]}
        for h in HEADERS:
            row = by_code.get(h)
            assert row is None or (row["debit"] == 0 and row["credit"] == 0), f"{h} masih terisi"
        opening = by_code.get("3-1950")
        assert opening, "akun 3-1950 Saldo Awal Kas & Bank tidak ada di neraca saldo"
        expected = sum(int(a.get("opening_balance") or 0) for a in _accounts(_sess(tok_finance))
                       if a.get("opening_posted"))
        credit = opening["credit"] - opening["debit"]
        assert credit == expected, f"3-1950 {credit} != Σ saldo awal {expected}"
        # saldo tiap sub-akun kas/bank di TB = balance yang dilaporkan modul
        for a in _accounts(_sess(tok_finance)):
            row = by_code.get(a["gl_account_code"])
            if row:
                assert row["debit"] - row["credit"] == a["balance"], a["name"]
