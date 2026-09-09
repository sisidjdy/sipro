"""Iterasi 5: regresi terfokus rich editor + layout/PDF + RBAC endpoint."""

import os

import fitz
import pytest
import requests
from dotenv import dotenv_values


# auth + base URL fixtures
frontend_env = dotenv_values("/app/frontend/.env")
raw_base = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not raw_base:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
BASE_URL = raw_base.rstrip("/")
API = f"{BASE_URL}/api"


def _login(email: str, password: str = "Sipro#2026") -> requests.Session:
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login {email} gagal: {r.status_code} {r.text[:160]}"
    token = r.json().get("access_token") or r.json().get("token")
    assert token
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def admin():
    return _login("superadmin@sipro.co.id")


@pytest.fixture(scope="module")
def sales():
    return _login("sales@sipro.co.id")


def _pdf_text(blob: bytes) -> str:
    doc = fitz.open(stream=blob, filetype="pdf")
    return "\n".join(page.get_text() for page in doc)


# doc-layout list + preview coverage
def test_targets_registered_and_all_previewable(admin):
    r = admin.get(f"{API}/doc-layouts", timeout=40)
    assert r.status_code == 200, r.text[:300]
    rows = r.json().get("data") or []
    failures = []
    for row in rows:
        code = row["code"]
        p = admin.post(f"{API}/doc-layouts/{code}/preview", json={}, timeout=60)
        if p.status_code != 200 or not p.headers.get("content-type", "").startswith("application/pdf"):
            failures.append((code, p.status_code, p.text[:120]))
    # Cover real document families, not an invented minimum number of documents.
    expected = {"__default__", "SPR", "SPR_CASH", "SPR_CASH_STAGED", "SPR_KPR", "PPJB", "AJB",
                "SPKT", "BAP", "BAST", "KWITANSI", "BKM", "BKK", "PENAWARAN", "FAKTUR",
                "BUPOT", "SPK", "PO", "SP", "BA_OPNAME", "PUNCHLIST", "LAPORAN", "INVOICE"}
    assert expected <= {row["code"] for row in rows}
    assert not failures, failures


# script sanitize + unknown placeholders
def test_script_sanitize_and_unknown_placeholder(admin):
    code = "KWITANSI"
    cur = admin.get(f"{API}/doc-layouts/{code}/script", timeout=30)
    assert cur.status_code == 200
    original = cur.json()["data"]["content"]
    try:
        payload = {
            "content": "<p><strong>Judul</strong></p><script>alert(1)</script><img src='x'/><p>{{doc_number}}</p>"
        }
        put = admin.put(f"{API}/doc-layouts/{code}/script", json=payload, timeout=30)
        assert put.status_code == 200, put.text[:300]
        got = admin.get(f"{API}/doc-layouts/{code}/script", timeout=30).json()["data"]["content"]
        assert "<script" not in got.lower()
        assert "<img" not in got.lower()
        assert "{{doc_number}}" in got

        bad = admin.put(f"{API}/doc-layouts/{code}/script", json={"content": "Halo {{token_ngawur}}"}, timeout=30)
        assert bad.status_code == 400
    finally:
        admin.put(f"{API}/doc-layouts/{code}/script", json={"content": original}, timeout=30)


# table config validation + table placeholders
def test_table_validation_and_placeholders_render(admin):
    bad_align = admin.put(f"{API}/doc-layouts/SPR_KPR", json={"table": {"alignment": "justify"}}, timeout=30)
    assert bad_align.status_code in (400, 422)
    bad_width = admin.put(f"{API}/doc-layouts/SPR_KPR", json={"table": {"width_pct": 20}}, timeout=30)
    assert bad_width.status_code in (400, 422)

    p = admin.post(
        f"{API}/doc-layouts/SPR_KPR/preview",
        json={"script": "<p>Uji tabel</p><p>{{tabel_biaya}}</p><p>{{tabel_rincian}}</p>"},
        timeout=60,
    )
    assert p.status_code == 200
    txt = _pdf_text(p.content)
    assert "{{tabel_biaya}}" not in txt
    assert "{{tabel_rincian}}" not in txt


# RBAC for script/layout/preview edit actions
def test_sales_cannot_write_layout_script_or_preview(sales):
    a = sales.put(f"{API}/doc-layouts/SPR_KPR/script", json={"content": "x"}, timeout=30)
    b = sales.put(f"{API}/doc-layouts/SPR_KPR", json={"table": {"grid": "none"}}, timeout=30)
    c = sales.post(f"{API}/doc-layouts/SPR_KPR/preview", json={}, timeout=30)
    assert a.status_code == 403
    assert b.status_code == 403
    assert c.status_code == 403


# issued/real PDF smoke checks with existing records
def test_real_receipt_invoice_and_quotation_pdf(admin):
    ar = admin.get(f"{API}/finance/ar", timeout=50)
    assert ar.status_code == 200
    rows = ar.json().get("data") or []
    if rows:
        deal_id = rows[0]["deal_id"]
        inv = admin.get(f"{API}/finance/ar/{deal_id}/invoice/pdf", timeout=60)
        assert inv.status_code == 200
        assert inv.content[:4] == b"%PDF"
        detail = admin.get(f"{API}/finance/ar/{deal_id}", timeout=50)
        assert detail.status_code == 200
        receipts = detail.json().get("receipts") or []
        if receipts:
            rec = admin.get(f"{API}/finance/ar/receipts/{receipts[0]['id']}/pdf", timeout=60)
            assert rec.status_code == 200
            assert rec.content[:4] == b"%PDF"

    q = admin.get(f"{API}/quotations?limit=5", timeout=40)
    if q.status_code == 200 and (q.json().get("data") or []):
        qid = q.json()["data"][0]["id"]
        qp = admin.get(f"{API}/quotations/{qid}/pdf", timeout=60)
        assert qp.status_code == 200
        assert qp.content[:4] == b"%PDF"
