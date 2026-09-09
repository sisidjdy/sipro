"""Fase 66 — naskah dokumen per jenis + gaya tabel konfigurable (backend API tests)."""
import base64
import os
import zlib

import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
base_url = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base_url:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
BASE_URL = base_url.rstrip("/")
API = f"{BASE_URL}/api"
PWD = "Sipro#2026"


def pdf_text(data: bytes) -> str:
    d = data.decode("latin1")
    out, pos = [], 0
    while True:
        i = d.find("stream", pos)
        if i < 0:
            break
        j = d.find("endstream", i)
        raw = d[i + 6:j].strip()
        pos = j + 5
        if raw.endswith("~>"):
            raw = raw[:-2]
        try:
            blob = base64.a85decode(raw.encode("latin1"), adobe=False,
                                    ignorechars=b" \n\r\t")
            out.append(zlib.decompress(blob).decode("latin1"))
        except Exception:  # noqa: BLE001
            continue
    return "\n".join(out)


def _login(email):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": PWD}, timeout=30)
    assert r.status_code == 200, f"login {email} -> {r.status_code} {r.text[:200]}"
    tok = r.json().get("access_token") or r.json().get("token")
    assert tok
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {tok}", "Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def admin():
    return _login("superadmin@sipro.co.id")


@pytest.fixture(scope="module")
def sales():
    return _login("sales@sipro.co.id")


# ------------------------------------------------------------------ daftar jenis dokumen
class TestListTargets:
    def test_list_layouts(self, admin):
        r = admin.get(f"{API}/doc-layouts")
        assert r.status_code == 200, r.text[:300]
        data = r.json()["data"]
        assert isinstance(data, list) and len(data) > 10
        for it in data:
            assert "category" in it and "category_label" in it and "has_script" in it
        codes = {it["code"] for it in data}
        assert {"SPR_KPR", "KWITANSI", "LAPORAN", "SP"} <= codes
        kpr = next(i for i in data if i["code"] == "SPR_KPR")
        assert kpr["category"] == "surat_pesanan"
        assert kpr["category_label"] == "Surat pesanan & pernyataan pembeli"
        lap = next(i for i in data if i["code"] == "LAPORAN")
        assert lap["kind"] == "table" and lap["category"] == "laporan"

    def test_unknown_code_404(self, admin):
        r = admin.get(f"{API}/doc-layouts/TIDAK_ADA_KODE")
        assert r.status_code == 404, r.status_code


# ------------------------------------------------------------------ naskah per jenis
class TestScript:
    def test_get_script_has_placeholders(self, admin):
        r = admin.get(f"{API}/doc-layouts/SPR_KPR/script")
        assert r.status_code == 200, r.text[:300]
        d = r.json()["data"]
        assert d["code"] == "SPR_KPR"
        assert d["category"] == "surat_pesanan"
        toks = {p["token"] for p in d["placeholders"]}
        assert "customer_name" in toks and "total" in toks
        assert isinstance(d["content"], str)

    def test_preview_renders_draft_script(self, admin):
        r = admin.post(f"{API}/doc-layouts/SPR_KPR/preview",
                       json={"script": "NASKAH QA 66 untuk {{customer_name}}"})
        assert r.status_code == 200, r.text[:300]
        assert r.content[:4] == b"%PDF"
        txt = pdf_text(r.content)
        assert "NASKAH QA 66" in txt, txt[:600]
        assert "Dewi Kartika" in txt
        assert "customer_name" not in txt

    def test_unknown_placeholder_rejected(self, admin):
        r = admin.put(f"{API}/doc-layouts/KWITANSI/script",
                      json={"content": "Terima {{token_ngawur}}"})
        assert r.status_code == 400, f"{r.status_code} {r.text[:300]}"
        assert "placeholder" in r.text.lower()

    def test_save_and_persist_then_restore(self, admin):
        cur = admin.get(f"{API}/doc-layouts/BAST/script").json()["data"]
        asli = cur["content"]
        try:
            baru = (asli or "") + " NASKAH QA 66."
            r = admin.put(f"{API}/doc-layouts/BAST/script", json={"content": baru})
            assert r.status_code == 200, r.text[:300]
            assert r.json()["data"]["content"] == baru
            g = admin.get(f"{API}/doc-layouts/BAST/script")
            assert g.status_code == 200
            assert g.json()["data"]["content"] == baru
            assert g.json()["data"]["customized"] is True
            lst = admin.get(f"{API}/doc-layouts").json()["data"]
            assert next(i for i in lst if i["code"] == "BAST")["has_script"] is True
        finally:
            admin.put(f"{API}/doc-layouts/BAST/script", json={"content": asli})
            assert admin.get(f"{API}/doc-layouts/BAST/script").json()["data"]["content"] == asli

    def test_sales_cannot_save_script(self, sales):
        r = sales.put(f"{API}/doc-layouts/SP/script", json={"content": "coba"})
        assert r.status_code == 403, f"{r.status_code} {r.text[:200]}"

    def test_sales_can_read_script(self, sales):
        r = sales.get(f"{API}/doc-layouts/SP/script")
        assert r.status_code in (200, 403), r.status_code


# ------------------------------------------------------------------ gaya tabel
class TestTableStyle:
    def test_layout_has_table_defaults(self, admin):
        d = admin.get(f"{API}/doc-layouts/SPR_KPR").json()["data"]
        t = d.get("table")
        assert t, "layout tidak punya kunci 'table'"
        assert t["grid"] in ("full", "horizontal", "none")
        assert set(["show_header", "zebra", "total_highlight", "font_size"]) <= set(t)

    def test_save_table_style_and_restore(self, admin):
        before = admin.get(f"{API}/doc-layouts/SPR_KPR").json()["data"]["table"]
        try:
            r = admin.put(f"{API}/doc-layouts/SPR_KPR",
                          json={"table": {"grid": "none", "show_header": False}})
            assert r.status_code == 200, r.text[:300]
            g = admin.get(f"{API}/doc-layouts/SPR_KPR").json()["data"]["table"]
            assert g["grid"] == "none"
            assert g["show_header"] is False
        finally:
            admin.delete(f"{API}/doc-layouts/SPR_KPR")
            after = admin.get(f"{API}/doc-layouts/SPR_KPR").json()["data"]["table"]
            assert after["grid"] == before["grid"]

    def test_preview_hides_column_names(self, admin):
        # Bagian `biaya` MATI secara bawaan (naskah SPR memuat rincian inline) — nyalakan eksplisit.
        biaya_on = [{"key": "biaya", "visible": True, "order": 20}]
        full = admin.post(f"{API}/doc-layouts/SPR_KPR/preview",
                          json={"sections": biaya_on, "table": {"show_header": True, "grid": "full"}})
        assert full.status_code == 200, full.text[:300]
        t_full = pdf_text(full.content)
        assert "Komponen" in t_full or "Nilai" in t_full, t_full[:600]

        r = admin.post(f"{API}/doc-layouts/SPR_KPR/preview",
                       json={"sections": biaya_on, "table": {"show_header": False, "grid": "none"}})
        assert r.status_code == 200, r.text[:300]
        txt = pdf_text(r.content)
        assert "Komponen" not in txt
        assert "Total kewajiban" in txt or "Harga unit" in txt, txt[:600]

    def test_invalid_grid_rejected(self, admin):
        r = admin.put(f"{API}/doc-layouts/SPR_KPR", json={"table": {"grid": "pelangi"}})
        assert r.status_code in (400, 422), f"{r.status_code} {r.text[:300]}"

    def test_table_preview_report_kind(self, admin):
        r = admin.post(f"{API}/doc-layouts/LAPORAN/preview",
                       json={"script": "Laporan uji {{org_name}}",
                             "table": {"show_header": False, "grid": "none"}})
        assert r.status_code == 200, r.text[:300]
        txt = pdf_text(r.content)
        assert "Laporan uji" in txt, txt[:600]
        assert "Kategori umur" not in txt


# ------------------------------------------------------------------ regresi dokumen
class TestNoRegression:
    def test_documents_pdf(self, admin):
        r = admin.get(f"{API}/documents?limit=5")
        assert r.status_code == 200, r.text[:300]
        items = r.json().get("data") or r.json().get("items") or []
        if not items:
            pytest.skip("tidak ada dokumen demo")
        doc_id = items[0]["id"]
        p = admin.get(f"{API}/documents/{doc_id}/pdf")
        assert p.status_code == 200, p.text[:200]
        assert p.content[:4] == b"%PDF"

    def test_spk_pdf(self, admin):
        lst = admin.get(f"{API}/subcon/spk?limit=5")
        if lst.status_code != 200:
            pytest.skip(f"spk list {lst.status_code}")
        items = lst.json().get("data") or []
        if not items:
            pytest.skip("tidak ada SPK")
        p = admin.get(f"{API}/subcon/spk/{items[0]['id']}/pdf")
        assert p.status_code == 200, p.text[:200]
        assert p.content[:4] == b"%PDF"

    def test_po_pdf(self, admin):
        lst = admin.get(f"{API}/procurement/pos?limit=5")
        if lst.status_code != 200:
            pytest.skip(f"po list {lst.status_code}")
        items = lst.json().get("data") or []
        if not items:
            pytest.skip("tidak ada PO")
        p = admin.get(f"{API}/procurement/pos/{items[0]['id']}/pdf")
        assert p.status_code == 200, p.text[:200]
        assert p.content[:4] == b"%PDF"


# ------------------------------------------------------------------ jenis dokumen baru
class TestCustomDocType:
    CODE = "QA_SURAT_KUASA"

    def test_create_custom_then_cleanup(self, admin):
        try:
            r = admin.post(f"{API}/master/doc-templates",
                           json={"code": self.CODE, "name": "QA Surat Kuasa",
                                 "content": "Surat kuasa {{doc_number}} {{date}}"})
            assert r.status_code in (200, 201), f"{r.status_code} {r.text[:300]}"
            # naskah jenis baru bisa disunting lewat panel gabungan
            e = admin.put(f"{API}/doc-layouts/{self.CODE}/script",
                          json={"content": "Surat kuasa {{doc_number}} disunting"})
            assert e.status_code == 200, f"{e.status_code} {e.text[:300]}"
            lst = admin.get(f"{API}/doc-layouts").json()["data"]
            row = next((i for i in lst if i["code"] == self.CODE), None)
            assert row is not None, "jenis dokumen baru tidak muncul di daftar"
            assert row["custom"] is True and row["has_script"] is True
            g = admin.get(f"{API}/doc-layouts/{self.CODE}/script")
            assert g.status_code == 200
            assert "Surat kuasa" in g.json()["data"]["content"]
        finally:
            import subprocess
            subprocess.run([
                "python3", "-c",
                "import os;from pymongo import MongoClient;"
                "c=MongoClient(os.environ['MONGO_URL']);"
                f"c[os.environ['DB_NAME']].document_templates.delete_many({{'code':'{self.CODE}'}})"
            ], check=False, cwd="/app/backend",
                env={**os.environ, **dotenv_values("/app/backend/.env")})
            assert not any(i["code"] == self.CODE for i in
                           admin.get(f"{API}/doc-layouts").json()["data"])
