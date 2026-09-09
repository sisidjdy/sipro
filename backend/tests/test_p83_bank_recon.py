"""Fase 83 — Rekonsiliasi bank PER REKENING: saldo rekening vs sub-akun GL rekening itu pada
tanggal mutasi terakhir; selisih diurai (mutasi belum cocok, jurnal tanpa pasangan, saldo awal
tersirat, residu) dan item buku boleh diberi alasan.

Jalankan: cd /app/backend && python -m pytest tests/test_p83_bank_recon.py -q
"""
import pytest

from conftest import BASE_URL, _sess


def _default_bank(s):
    rows = s.get(f"{BASE_URL}/api/cash-bank/accounts", params={"kind": "bank"}).json()["data"]
    return next(r for r in rows if r["is_default"])


def test_overview_lists_every_bank_account_against_own_subaccount(tok_finance):
    s = _sess(tok_finance)
    body = s.get(f"{BASE_URL}/api/bank/reconciliation/overview").json()
    rows = body["data"]
    banks = s.get(f"{BASE_URL}/api/cash-bank/accounts", params={"kind": "bank"}).json()["data"]
    assert {r["account_id"] for r in rows} == {b["id"] for b in banks}
    for r in rows:
        assert r["gl_account_code"].startswith("1-12") and r["gl_account_code"] != "1-1200"
        assert r["status"] in ("seimbang", "dijelaskan", "belum_dijelaskan", "tanpa_data")
        if r["statement_balance"] is None:
            assert r["status"] == "tanpa_data" and r["residual"] is None
    assert sum(body["summary"].values()) == len(rows)


def test_reconcile_math_ties_out(tok_finance):
    s = _sess(tok_finance)
    acc = _default_bank(s)
    d = s.get(f"{BASE_URL}/api/bank/reconciliation", params={"account_id": acc["id"]}).json()["data"]
    assert d["gl_account_code"] == acc["gl_account_code"]
    if d["statement_balance"] is None:
        pytest.skip("rekening default belum punya mutasi berkolom saldo")
    # identitas rekonsiliasi: (rekening + item buku-saja) − (buku + item rekening-saja) − saldo awal = residu
    lhs = (d["statement_balance"] + d["book_only_total"]) - (d["book_balance"] + d["bank_only_total"]) \
        - (d["statement_opening"] or 0)
    assert lhs == d["residual"]
    assert d["difference"] == d["statement_balance"] - d["book_balance"]
    assert len(d["bank_only"]) == d["unmatched_count"]
    assert d["unexplained_count"] + d["explained_count"] == len(d["book_only"])
    codes = {c["code"] for c in d["causes"]}
    if d["unmatched_count"]:
        assert "unmatched" in codes
    if d["residual"]:
        assert "unexplained" in codes
    else:
        assert "unexplained" not in codes


def test_explain_book_item_is_documentation_only(tok_finance):
    s = _sess(tok_finance)
    acc = _default_bank(s)
    d = s.get(f"{BASE_URL}/api/bank/reconciliation", params={"account_id": acc["id"]}).json()["data"]
    pending = [l for l in d["book_only"] if not l["explained"]]
    if not pending:
        pytest.skip("tidak ada jurnal tanpa pasangan")
    row = pending[0]
    # 'other' tanpa catatan ditolak
    bad = s.post(f"{BASE_URL}/api/bank/reconciliation/explain", json={
        "account_id": acc["id"], "journal_id": row["journal_id"], "reason_code": "other"})
    assert bad.status_code == 400
    ok = s.post(f"{BASE_URL}/api/bank/reconciliation/explain", json={
        "account_id": acc["id"], "journal_id": row["journal_id"], "reason_code": "deposit_in_transit",
        "note": "uji p83"})
    assert ok.status_code == 200, ok.text
    d2 = s.get(f"{BASE_URL}/api/bank/reconciliation", params={"account_id": acc["id"]}).json()["data"]
    row2 = next(l for l in d2["book_only"] if l["journal_id"] == row["journal_id"])
    assert row2["explained"] and row2["reason_code"] == "deposit_in_transit" and row2["note"] == "uji p83"
    assert d2["unexplained_count"] == d["unexplained_count"] - 1
    assert d2["residual"] == d["residual"] and d2["book_only_total"] == d["book_only_total"]
    rm = s.post(f"{BASE_URL}/api/bank/reconciliation/unexplain", json={
        "account_id": acc["id"], "journal_id": row["journal_id"]})
    assert rm.status_code == 200
    d3 = s.get(f"{BASE_URL}/api/bank/reconciliation", params={"account_id": acc["id"]}).json()["data"]
    assert d3["unexplained_count"] == d["unexplained_count"]


def test_sales_cannot_view_reconciliation(tok_sales):
    s = _sess(tok_sales)
    assert s.get(f"{BASE_URL}/api/bank/reconciliation/overview").status_code == 403
