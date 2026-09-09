"""Fase 99 iter145 — verifikasi fix POST /api/wa/contacts/import first_message + smoke regresi."""
import os
import pytest
import requests


def _load_base():
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if not v:
        for line in open("/app/frontend/.env"):
            if line.startswith("REACT_APP_BACKEND_URL="):
                v = line.split("=", 1)[1].strip()
                break
    assert v
    return v.rstrip("/")


BASE = _load_base()
API = f"{BASE}/api"
PWD = "Sipro#2026"


def _login(email):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": PWD}, timeout=30)
    assert r.status_code == 200, r.text[:200]
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def sa():
    tok = _login("superadmin@sipro.co.id")
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


def _find_contact(sa, q):
    r = sa.get(f"{API}/wa/contacts", params={"q": q}, timeout=30)
    assert r.status_code == 200, r.text[:200]
    items = r.json().get("data", r.json())
    if isinstance(items, dict):
        items = items.get("items", [])
    return items


def _cleanup(sa, cid):
    try:
        sa.delete(f"{API}/wa/contacts/{cid}", timeout=30)
    except Exception:
        pass


class TestImportFirstMessage:
    def test_freeform_import_stores_first_message(self, sa):
        text = "+628139900781 Uji QA Impor\nharga dan kpr berapa?"
        r = sa.post(f"{API}/wa/contacts/import", json={"text": text, "label": "qa"}, timeout=30)
        assert r.status_code == 200, r.text[:300]
        js = r.json().get("data", r.json())
        assert js.get("added") == 1, js

        items = _find_contact(sa, "Uji QA Impor")
        assert items, "kontak tidak ditemukan setelah import"
        c = items[0]
        cid = c.get("id") or c.get("_id")
        try:
            assert c.get("first_message") == "harga dan kpr berapa?", c

            # suggestions harus punya playbook + keyword (price_info)
            rs = sa.get(f"{API}/wa/contacts/{cid}/suggestions", timeout=30)
            assert rs.status_code == 200, rs.text[:200]
            data = rs.json().get("data", rs.json())
            arr = data.get("items") if isinstance(data, dict) else data
            assert arr, "suggestions kosong"
            sources = {it.get("source") for it in arr}
            assert "playbook" in sources, sources
            assert "keyword" in sources, sources
            kw = [it for it in arr if it.get("source") == "keyword"]
            assert any(it.get("template_code") == "price_info" for it in kw), kw

            # Reimport dengan pesan berbeda: tidak menimpa first_message
            text2 = "+628139900781 Uji QA Impor\npesan baru yang beda"
            r2 = sa.post(f"{API}/wa/contacts/import", json={"text": text2, "label": "qa"}, timeout=30)
            assert r2.status_code == 200
            items2 = _find_contact(sa, "Uji QA Impor")
            c2 = items2[0]
            assert c2.get("first_message") == "harga dan kpr berapa?", f"first_message tertimpa: {c2.get('first_message')}"
        finally:
            _cleanup(sa, cid)

    def test_csv_import_still_works(self, sa):
        text = "nama,telp\nBudi Uji,+628139900782"
        r = sa.post(f"{API}/wa/contacts/import", json={"text": text, "label": "qa"}, timeout=30)
        assert r.status_code == 200, r.text[:300]
        js = r.json().get("data", r.json())
        assert js.get("added") == 1, js
        items = _find_contact(sa, "Budi Uji")
        assert items, "kontak CSV tidak ditemukan"
        c = items[0]
        cid = c.get("id") or c.get("_id")
        try:
            # first_message boleh null/empty utk CSV tanpa pesan
            fm = c.get("first_message")
            assert fm in (None, "", "nan"), f"expected empty first_message, got {fm!r}"
            assert (c.get("name") or "").strip() == "Budi Uji", c
        finally:
            _cleanup(sa, cid)

    def test_vcf_import_works(self, sa):
        vcf = "BEGIN:VCARD\nVERSION:3.0\nFN:Vcf Uji QA\nTEL;TYPE=CELL:+628139900783\nEND:VCARD"
        r = sa.post(f"{API}/wa/contacts/import", json={"text": vcf, "label": "qa"}, timeout=30)
        assert r.status_code == 200, r.text[:300]
        js = r.json().get("data", r.json())
        assert js.get("added", 0) >= 1, js
        items = _find_contact(sa, "Vcf Uji QA")
        if items:
            _cleanup(sa, items[0].get("id") or items[0].get("_id"))


class TestSmokeRegression:
    def test_wa_template_document_delivery(self, sa):
        r = sa.get(f"{API}/wa-templates", timeout=30)
        assert r.status_code == 200
        items = r.json().get("data", r.json())
        if isinstance(items, dict):
            items = items.get("items", [])
        doc = next((t for t in items if t.get("code") == "document_delivery"), None)
        assert doc, "template document_delivery hilang"
        assert doc.get("header_type") == "document"
        assert doc.get("status") == "approved"

    def test_reference_groups(self, sa):
        r = sa.get(f"{API}/reference", timeout=30)
        assert r.status_code == 200
        data = r.json().get("data", r.json())
        keys = list(data.keys()) if isinstance(data, dict) else [g.get("code") or g.get("group") for g in data]
        assert "task_related_type" in keys
        assert "wa_template_header" in keys

    def test_manager_pricing_approve(self):
        tok = _login("manager@sipro.co.id")
        r = requests.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {tok}"}, timeout=30)
        perms = (r.json().get("data") or r.json()).get("permissions") or {}
        assert "approve" in (perms.get("pricing") or [])

    def test_sales_no_pricing_approve(self):
        tok = _login("sales@sipro.co.id")
        r = requests.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {tok}"}, timeout=30)
        perms = (r.json().get("data") or r.json()).get("permissions") or {}
        assert "approve" not in (perms.get("pricing") or [])
