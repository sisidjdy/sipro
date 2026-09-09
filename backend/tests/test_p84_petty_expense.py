"""Fase 84 — Kas kecil imprest: pengeluaran langsung berbukti (Dr beban / Cr sub-akun kas),
batas satu pengeluaran, void SoD dengan jurnal balik, keadaan imprest & usulan pengisian.

Jalankan: cd /app/backend && python -m pytest tests/test_p84_petty_expense.py -q -n 0
"""
import io
import uuid

import pytest

from conftest import BASE_URL, _sess


@pytest.fixture(scope="module")
def kas(tok_finance):
    """Kas kecil uji dengan saldo awal 2 jt & batas imprest 3 jt (dijurnal saat dibuat)."""
    s = _sess(tok_finance)
    r = s.post(f"{BASE_URL}/api/cash-bank/accounts", json={
        "kind": "cash", "name": f"Kas Uji P84 {uuid.uuid4().hex[:4]}", "account_no": f"KAS-P84-{uuid.uuid4().hex[:6]}",
        "opening_balance": 2_000_000, "imprest_limit": 3_000_000})
    assert r.status_code == 200, r.text
    acc = r.json()["data"]
    assert acc["imprest_limit"] == 3_000_000
    yield acc
    s.put(f"{BASE_URL}/api/cash-bank/accounts/{acc['id']}", json={"is_active": False})


def _balance(s, acc_id):
    rows = s.get(f"{BASE_URL}/api/cash-bank/accounts").json()["data"]
    return next(r["balance"] for r in rows if r["id"] == acc_id)


def _imprest(s, acc_id):
    body = s.get(f"{BASE_URL}/api/petty-cash/imprest").json()["data"]
    return body, next(r for r in body["accounts"] if r["account_id"] == acc_id)


def _upload_proof(s):
    import requests
    r = requests.post(f"{BASE_URL}/api/files/upload", headers={"Authorization": s.headers["Authorization"]},
                      data={"owner_type": "petty_expense", "optimize": "false"},
                      files={"file": ("nota.txt", io.BytesIO(b"nota toko fotokopi Rp 150.000"), "text/plain")},
                      timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["data"]["id"]


def test_expense_requires_proof_and_respects_max(tok_finance, kas):
    s = _sess(tok_finance)
    base = {"cash_account_id": kas["id"], "category": "atk_kantor", "description": "Materai & fotokopi", "amount": 150_000}
    r = s.post(f"{BASE_URL}/api/petty-cash/expenses", json=base)
    assert r.status_code == 400 and "Bukti" in r.json()["detail"]
    fid = _upload_proof(s)
    r = s.post(f"{BASE_URL}/api/petty-cash/expenses", json={**base, "amount": 1_000_001, "file_ids": [fid]})
    assert r.status_code == 400 and "melebihi batas" in r.json()["detail"]
    r = s.post(f"{BASE_URL}/api/petty-cash/expenses", json={**base, "category": "tidak_ada", "file_ids": [fid]})
    assert r.status_code == 400
    r = s.post(f"{BASE_URL}/api/petty-cash/expenses", json={**base, "amount": 5_000_000, "file_ids": [fid]})
    assert r.status_code == 400  # melebihi batas satu pengeluaran (sebelum cek saldo)


def test_expense_posts_journal_and_void_reverses(tok_finance, tok_finlead, kas):
    s, boss = _sess(tok_finance), _sess(tok_finlead)
    before = _balance(s, kas["id"])
    fid = _upload_proof(s)
    r = s.post(f"{BASE_URL}/api/petty-cash/expenses", json={
        "cash_account_id": kas["id"], "category": "transport", "description": "BBM survei lokasi",
        "amount": 150_000, "payee": "SPBU", "file_ids": [fid]})
    assert r.status_code == 200, r.text
    ex = r.json()["data"]
    assert ex["status"] == "posted" and ex["no"].startswith("KK") and ex["expense_account_code"] == "6-1300"
    assert ex["cash_account_code"] == kas["gl_account_code"] and ex["file_ids"] == [fid]
    je = s.get(f"{BASE_URL}/api/gl/journals/{ex['journal_id']}")
    if je.status_code == 200:
        lines = {(ln["account_code"], ln["debit"], ln["credit"]) for ln in je.json()["data"]["lines"]}
        assert ("6-1300", 150_000, 0) in lines and (kas["gl_account_code"], 0, 150_000) in lines
    assert _balance(s, kas["id"]) == before - 150_000
    _, st = _imprest(s, kas["id"])
    assert st["month_count"] >= 1 and st["month_spent"] >= 150_000

    # SoD: pencatat tidak boleh membatalkan sendiri
    r = s.post(f"{BASE_URL}/api/petty-cash/expenses/{ex['id']}/void", json={"reason": "salah input nominal"})
    assert r.status_code in (400, 403)
    r = boss.post(f"{BASE_URL}/api/petty-cash/expenses/{ex['id']}/void", json={"reason": "salah input nominal"})
    assert r.status_code == 200, r.text
    v = r.json()["data"]
    assert v["status"] == "voided" and v["void_journal_no"] and v["void_journal_id"] != ex["journal_id"]
    assert _balance(s, kas["id"]) == before
    r = boss.post(f"{BASE_URL}/api/petty-cash/expenses/{ex['id']}/void", json={"reason": "dua kali"})
    assert r.status_code == 400
    rows = s.get(f"{BASE_URL}/api/petty-cash/expenses", params={"account_id": kas["id"], "status": "voided"}).json()
    assert any(x["id"] == ex["id"] for x in rows["data"]) and rows["sum_posted"] == 0


def test_imprest_suggests_replenish_below_threshold(tok_finance, tok_finlead, kas):
    s = _sess(tok_finance)
    body, st = _imprest(s, kas["id"])
    assert st["imprest_limit"] == 3_000_000 and st["limit_source"] == "kas" and st["threshold"] == 900_000
    assert st["status"] == "cukup" and st["suggested_replenish"] == 0
    r = s.post(f"{BASE_URL}/api/petty-cash/imprest/{kas['id']}/replenish", json={})
    assert r.status_code == 400 and "ambang" in r.json()["detail"]
    fid = _upload_proof(s)
    for i in range(2):
        r = s.post(f"{BASE_URL}/api/petty-cash/expenses", json={
            "cash_account_id": kas["id"], "category": "perbaikan_pemeliharaan",
            "description": f"Perbaikan pompa air kantor #{i + 1}", "amount": 1_000_000, "file_ids": [fid]})
        assert r.status_code == 200, r.text
    assert _balance(s, kas["id"]) == 0
    r = s.post(f"{BASE_URL}/api/petty-cash/expenses", json={
        "cash_account_id": kas["id"], "category": "transport", "description": "Ojek kirim berkas",
        "amount": 50_000, "file_ids": [fid]})
    assert r.status_code == 400 and "tidak cukup" in r.json()["detail"]
    _, st = _imprest(s, kas["id"])
    assert st["status"] == "perlu_isi" and st["suggested_replenish"] == 3_000_000
    r = s.post(f"{BASE_URL}/api/petty-cash/imprest/{kas['id']}/replenish", json={})
    assert r.status_code == 200, r.text
    tr = r.json()["data"]
    assert tr["kind"] == "isi_kas_kecil" and tr["status"] == "pending" and tr["amount"] == 3_000_000
    assert tr["to_account_id"] == kas["id"]
    _, st = _imprest(s, kas["id"])
    assert st["status"] == "menunggu_isi" and st["pending_replenish"] == 3_000_000 and st["suggested_replenish"] == 0
    r = s.post(f"{BASE_URL}/api/petty-cash/imprest/{kas['id']}/replenish", json={})
    assert r.status_code == 400
    _sess(tok_finlead).post(f"{BASE_URL}/api/cash-bank/transfers/{tr['id']}/reject", json={"reason": "uji otomatis selesai"})


def test_rbac_and_bank_account_rejected(tok_sales, tok_finance):
    assert _sess(tok_sales).get(f"{BASE_URL}/api/petty-cash/imprest").status_code == 403
    s = _sess(tok_finance)
    bank = next(r for r in s.get(f"{BASE_URL}/api/cash-bank/accounts", params={"kind": "bank"}).json()["data"] if r["is_default"])
    r = s.post(f"{BASE_URL}/api/petty-cash/expenses", json={
        "cash_account_id": bank["id"], "category": "transport", "description": "Salah kas", "amount": 10_000, "file_ids": ["x"]})
    assert r.status_code == 400 and "rekening bank" in r.json()["detail"]
