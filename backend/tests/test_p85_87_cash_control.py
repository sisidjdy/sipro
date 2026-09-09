"""Fase 85–87 — kunci periode kas per rekening, giro mundur (PDC), bukti kas BKM/BKK.

Jalankan: cd /app/backend && python -m pytest tests/test_p85_87_cash_control.py -q -n 0
"""
import io
import time
import uuid
from datetime import date

import pytest
import requests

from conftest import BASE_URL, _sess


def _prev_month() -> str:
    d = date.today().replace(day=1)
    y, m = (d.year, d.month - 1) if d.month > 1 else (d.year - 1, 12)
    return f"{y:04d}-{m:02d}"


def _upload(s):
    r = requests.post(f"{BASE_URL}/api/files/upload", headers={"Authorization": s.headers["Authorization"]},
                      data={"owner_type": "petty_expense", "optimize": "false"},
                      files={"file": ("nota.txt", io.BytesIO(b"nota"), "text/plain")}, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["data"]["id"]


@pytest.fixture(scope="module")
def kas(tok_finance):
    s = _sess(tok_finance)
    pm = _prev_month()
    r = s.post(f"{BASE_URL}/api/cash-bank/accounts", json={
        "kind": "cash", "name": f"Kas Uji P85 {uuid.uuid4().hex[:4]}", "account_no": f"KAS-P85-{uuid.uuid4().hex[:6]}",
        "opening_balance": 1_000_000, "opening_date": f"{pm}-15", "imprest_limit": 50_000_000})
    assert r.status_code == 200, r.text
    acc = r.json()["data"]
    yield acc
    s.put(f"{BASE_URL}/api/cash-bank/accounts/{acc['id']}", json={"is_active": False})


# ------------------------------------------------------------------ Fase 85
def test_lock_requires_eligibility_and_blocks_manual_journal(tok_finance, tok_finlead, kas):
    s, boss = _sess(tok_finance), _sess(tok_finlead)
    pm = _prev_month()
    pv = s.get(f"{BASE_URL}/api/cash-bank/locks/preview", params={"account_id": kas["id"], "period": pm}).json()["data"]
    assert pv["closing_balance"] == 1_000_000 and pv["eligible"] is False and any("opname" in r for r in pv["reasons"])
    pv = s.get(f"{BASE_URL}/api/cash-bank/locks/preview",
               params={"account_id": kas["id"], "period": pm, "counted_balance": 999_000}).json()["data"]
    assert pv["eligible"] is False and any("≠" in r for r in pv["reasons"])
    pv = s.get(f"{BASE_URL}/api/cash-bank/locks/preview",
               params={"account_id": kas["id"], "period": pm, "counted_balance": 1_000_000}).json()["data"]
    assert pv["eligible"] is True and pv["account"]["kind"] == "cash"
    cur = date.today().strftime("%Y-%m")
    pv = s.get(f"{BASE_URL}/api/cash-bank/locks/preview",
               params={"account_id": kas["id"], "period": cur, "counted_balance": 1_000_000}).json()["data"]
    assert pv["eligible"] is False  # bulan berjalan tidak boleh dikunci

    body = {"account_id": kas["id"], "period": pm, "counted_balance": 1_000_000, "note": "BA opname uji"}
    assert s.post(f"{BASE_URL}/api/cash-bank/locks", json=body).status_code == 403  # finance biasa
    r = boss.post(f"{BASE_URL}/api/cash-bank/locks", json=body)
    assert r.status_code == 200, r.text
    lock = r.json()["data"]
    assert lock["status"] == "locked" and lock["closing_balance"] == 1_000_000
    assert boss.post(f"{BASE_URL}/api/cash-bank/locks", json=body).status_code == 400  # sudah terkunci

    # jurnal MANUAL bertanggal di periode terkunci → ditolak
    fid = _upload(s)
    r = s.post(f"{BASE_URL}/api/petty-cash/expenses", json={
        "cash_account_id": kas["id"], "category": "transport", "description": "Backdate ke periode terkunci",
        "amount": 20_000, "date": f"{pm}-20", "file_ids": [fid]})
    assert r.status_code == 400 and "dikunci" in r.json()["detail"], r.text
    # tanggal hari ini tetap boleh; saldo penutup terkunci tidak berubah
    r = s.post(f"{BASE_URL}/api/petty-cash/expenses", json={
        "cash_account_id": kas["id"], "category": "transport", "description": "Ojek kirim berkas",
        "amount": 20_000, "file_ids": [fid]})
    assert r.status_code == 200, r.text
    ov = s.get(f"{BASE_URL}/api/cash-bank/locks").json()["data"]
    row = next(a for a in ov["accounts"] if a["account_id"] == kas["id"])
    assert row["locked_through"] == pm and row["closing_balance"] == 1_000_000 and row["balance"] == 980_000

    # Fase 87: pengeluaran tadi menerbitkan BKK bernomor untuk kas ini
    vs = s.get(f"{BASE_URL}/api/cash-bank/vouchers", params={"kind": "BKK", "account_id": kas["id"]}).json()
    assert vs["total"] >= 1 and vs["data"][0]["amount"] == 20_000 and vs["data"][0]["no"].startswith("BKK/")
    assert vs["data"][0]["entry_no"] == r.json()["data"]["journal_no"]
    pdf = s.get(f"{BASE_URL}/api/cash-bank/vouchers/{vs['data'][0]['id']}/pdf")
    assert pdf.status_code == 200 and pdf.headers["content-type"].startswith("application/pdf")

    r = boss.post(f"{BASE_URL}/api/cash-bank/locks/{lock['id']}/unlock", json={"reason": "uji otomatis dibuka"})
    assert r.status_code == 200 and r.json()["data"]["status"] == "unlocked"
    ov = s.get(f"{BASE_URL}/api/cash-bank/locks").json()["data"]
    assert next(a for a in ov["accounts"] if a["account_id"] == kas["id"])["locked_through"] is None


# ------------------------------------------------------------------ Fase 86
def _open_ar(s):
    rows = s.get(f"{BASE_URL}/api/finance/ar", params={"status": "unpaid,partial", "limit": 20}).json()["data"]
    rows = [r for r in rows if int(r.get("outstanding") or 0) >= 200_000]
    if not rows:
        pytest.skip("tidak ada tagihan AR terbuka ≥ 200rb")
    return rows[0]


def test_pdc_receive_clear_reduces_ar_only_on_clearing(tok_finance, tok_sales):
    s = _sess(tok_finance)
    assert _sess(tok_sales).get(f"{BASE_URL}/api/pdc").status_code == 403
    inv = _open_ar(s)
    amt = min(int(inv["outstanding"]), 200_000)
    no = f"BG-{uuid.uuid4().hex[:6]}"
    body = {"kind": "bg", "bank_name": "Bank Uji", "instrument_no": no, "amount": amt,
            "due_date": date.today().isoformat(), "deal_id": inv["deal_id"]}
    r = s.post(f"{BASE_URL}/api/pdc", json=body)
    assert r.status_code == 200, r.text
    g = r.json()["data"]
    assert g["status"] == "received" and g["no"].startswith("GIRO") and g["unit_code"] == inv["unit_code"]
    je = s.get(f"{BASE_URL}/api/gl/journals/{g['journal_id']}").json()["data"]
    lines = {(ln["account_code"], ln["debit"], ln["credit"]) for ln in je["lines"]}
    assert ("1-1350", amt, 0) in lines and ("2-1480", 0, amt) in lines
    assert s.post(f"{BASE_URL}/api/pdc", json=body).status_code == 400  # warkat kembar
    # AR belum berkurang
    inv2 = next(x for x in s.get(f"{BASE_URL}/api/finance/ar", params={"q": inv["unit_code"], "limit": 20}).json()["data"]
                if x["deal_id"] == inv["deal_id"])
    assert int(inv2["outstanding"]) == int(inv["outstanding"])

    bank = next(b for b in s.get(f"{BASE_URL}/api/cash-bank/accounts", params={"kind": "bank"}).json()["data"] if b["is_default"])
    bal_before = bank["balance"]
    r = s.post(f"{BASE_URL}/api/pdc/{g['id']}/clear", json={"cash_account_id": bank["id"]})
    assert r.status_code == 200, r.text
    c = r.json()["data"]
    assert c["status"] == "cleared" and c["receipt_no"] and c["receipt_no"].startswith("KWT") and c["cash_account_id"] == bank["id"]
    inv3 = next(x for x in s.get(f"{BASE_URL}/api/finance/ar", params={"q": inv["unit_code"], "limit": 20}).json()["data"]
                if x["deal_id"] == inv["deal_id"])
    assert int(inv3["outstanding"]) == int(inv["outstanding"]) - amt
    bank2 = None
    for _ in range(12):  # jurnal kwitansi diposting lewat dispatcher event (≤ 8 detik)
        bank2 = next(b for b in s.get(f"{BASE_URL}/api/cash-bank/accounts", params={"kind": "bank"}).json()["data"] if b["id"] == bank["id"])
        if bank2["balance"] == bal_before + amt:
            break
        time.sleep(2)
    assert bank2["balance"] == bal_before + amt
    assert s.post(f"{BASE_URL}/api/pdc/{g['id']}/clear", json={"cash_account_id": bank["id"]}).status_code == 400
    # BKM terbit untuk uang masuk ke bank dari kwitansi giro
    vs = s.get(f"{BASE_URL}/api/cash-bank/vouchers", params={"kind": "BKM", "account_id": bank["id"], "limit": 5}).json()
    assert any(v["amount"] == amt for v in vs["data"])


def test_pdc_bounce_and_cancel_reverse_memorandum(tok_finance):
    s = _sess(tok_finance)
    mk = lambda: s.post(f"{BASE_URL}/api/pdc", json={  # noqa: E731
        "kind": "cek", "bank_name": "Bank Uji", "instrument_no": f"CK-{uuid.uuid4().hex[:6]}", "amount": 150_000,
        "due_date": date.today().isoformat(), "issuer_name": "Pihak Luar"}).json()["data"]
    a, b = mk(), mk()
    assert a["deal_id"] is None
    r = s.post(f"{BASE_URL}/api/pdc/{a['id']}/bounce", json={"reason": "saldo penerbit tidak cukup"})
    assert r.status_code == 200 and r.json()["data"]["status"] == "bounced" and r.json()["data"]["reverse_journal_no"]
    r = s.post(f"{BASE_URL}/api/pdc/{b['id']}/cancel", json={"reason": "dikembalikan ke pembeli"})
    assert r.status_code == 200 and r.json()["data"]["status"] == "cancelled"
    assert s.post(f"{BASE_URL}/api/pdc/{b['id']}/bounce", json={"reason": "sudah batal"}).status_code == 400
    lst = s.get(f"{BASE_URL}/api/pdc", params={"status": "bounced"}).json()
    assert any(x["id"] == a["id"] for x in lst["data"]) and lst["summary"]["bounced_count"] >= 1
    # rekonsiliasi memorandum: seluruh giro yang tidak lagi 'received' harus bersaldo nol di 1-1350
    tb = s.get(f"{BASE_URL}/api/gl/trial-balance").json()["data"]
    rows = tb if isinstance(tb, list) else tb.get("rows") or tb.get("accounts") or []
    g = next((x for x in rows if x.get("code") == "1-1350" or x.get("account_code") == "1-1350"), None)
    k = next((x for x in rows if x.get("code") == "2-1480" or x.get("account_code") == "2-1480"), None)
    if g and k:
        gb = int(g.get("balance", (g.get("debit") or 0) - (g.get("credit") or 0)))
        kb = int(k.get("balance", (k.get("credit") or 0) - (k.get("debit") or 0)))
        assert abs(gb) == abs(kb)
