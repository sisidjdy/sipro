"""P114: invoice PDF & kwitansi PDF (AR router) + regresi ringan dokumen."""
import os

import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
base_url = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base_url:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
BASE_URL = base_url.rstrip("/")
API = f"{BASE_URL}/api"

EMAIL = "superadmin@sipro.co.id"
PASSWORD = "Sipro#2026"


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": EMAIL, "password": PASSWORD}, timeout=60)
    if r.status_code != 200:
        pytest.fail(f"Login failed {r.status_code}: {r.text[:300]}")
    tok = r.json().get("access_token") or r.json().get("token")
    if not tok:
        pytest.fail(f"No token in login response: {r.text[:300]}")
    s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


@pytest.fixture(scope="module")
def deal_id(client):
    r = client.get(f"{API}/finance/ar?limit=200", timeout=60)
    assert r.status_code == 200, r.text[:300]
    rows = r.json().get("data") or []
    # kuitansi uji Rp 50.000 hanya sah pada tagihan yang masih punya sisa (bukan yang sudah lunas)
    rows = [x for x in rows if int(x.get("outstanding") or 0) >= 50000] or rows
    if not rows:
        pytest.fail("Tidak ada data AR untuk diuji")
    return rows[0]["deal_id"]


class TestInvoicePdf:
    def test_invoice_pdf_ok(self, client, deal_id):
        r = client.get(f"{API}/finance/ar/{deal_id}/invoice/pdf", timeout=90)
        assert r.status_code == 200, r.text[:300]
        assert r.headers.get("content-type", "").startswith("application/pdf")
        assert r.content[:4] == b"%PDF"
        assert len(r.content) > 1024, f"PDF too small: {len(r.content)}"

    def test_invoice_pdf_unknown_deal_404(self, client):
        r = client.get(f"{API}/finance/ar/TEST_NO_SUCH_DEAL/invoice/pdf", timeout=60)
        assert r.status_code == 404, r.status_code
        assert "jadwal tagihan" in r.json().get("detail", "").lower()


class TestReceiptPdf:
    def test_create_receipt_and_pdf(self, client, deal_id):
        r = client.post(f"{API}/finance/ar/receipts", json={
            "deal_id": deal_id, "amount": 50000, "method": "transfer", "note": "TEST_P114",
        }, timeout=90)
        assert r.status_code == 200, r.text[:400]
        data = r.json().get("data") or {}
        rid = data.get("id") or (data.get("receipt") or {}).get("id")
        assert rid, f"No receipt id: {str(data)[:300]}"
        p = client.get(f"{API}/finance/ar/receipts/{rid}/pdf", timeout=90)
        assert p.status_code == 200, p.text[:300]
        assert p.headers.get("content-type", "").startswith("application/pdf")
        assert p.content[:4] == b"%PDF"
        assert len(p.content) > 1024
        # persistensi: receipt tampil di detail AR
        d = client.get(f"{API}/finance/ar/{deal_id}", timeout=60)
        assert d.status_code == 200
        assert any(x.get("id") == rid for x in d.json().get("receipts", []))

    def test_receipt_pdf_fake_id_404(self, client):
        r = client.get(f"{API}/finance/ar/receipts/TEST_FAKE_RID/pdf", timeout=60)
        assert r.status_code == 404, r.status_code
        assert "tidak ditemukan" in r.json().get("detail", "").lower()


class TestDocumentsRegression:
    def test_contracts_list(self, client):
        r = client.get(f"{API}/contracts?limit=100", timeout=60)
        assert r.status_code == 200, r.text[:300]
        rows = r.json().get("data")
        assert isinstance(rows, list) and rows, "Kontrak kosong"
        assert "deal_id" in rows[0]

    def test_contract_detail(self, client):
        rows = client.get(f"{API}/contracts?limit=1", timeout=60).json()["data"]
        r = client.get(f"{API}/contracts/{rows[0]['id']}", timeout=60)
        assert r.status_code == 200, r.text[:300]
        assert r.json()["data"]["id"] == rows[0]["id"]

    def test_ar_list_counts(self, client):
        r = client.get(f"{API}/finance/ar?limit=5", timeout=60)
        assert r.status_code == 200
        body = r.json()
        assert "counts" in body and isinstance(body["total"], int)
