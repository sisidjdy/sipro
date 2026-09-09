"""Fase 99 iter144 — regresi integrasi via public backend URL.

Cakupan:
 - Template WA header dokumen (document_delivery) & CRUD header_type & submit tanpa handle
 - Reference groups task_related_type, wa_template_header
 - Doc-history route + send-wa untuk customer memiliki pdf_url
 - Balasan Cerdas (playbook + keyword) via /wa/contacts/{id}/suggestions
 - RBAC pricing:approve & finance:manage
"""
import os
import re
import pytest
import requests

def _load_base():
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if not v:
        for line in open("/app/frontend/.env"):
            if line.startswith("REACT_APP_BACKEND_URL="):
                v = line.split("=", 1)[1].strip()
                break
    assert v, "REACT_APP_BACKEND_URL tidak diset"
    return v.rstrip("/")


BASE = _load_base()
API = f"{BASE}/api"
PWD = "Sipro#2026"


def _login(email: str) -> str:
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": PWD}, timeout=30)
    assert r.status_code == 200, f"login {email}: {r.status_code} {r.text[:200]}"
    return r.json()["access_token"]


def _hdr(tok: str):
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="module")
def sa_token():
    return _login("superadmin@sipro.co.id")


@pytest.fixture(scope="module")
def sa(sa_token):
    s = requests.Session()
    s.headers.update(_hdr(sa_token))
    return s


# -------------------- Template WA --------------------
class TestTemplatesDocument:
    def test_document_delivery_seeded(self, sa):
        r = sa.get(f"{API}/wa-templates", timeout=30)
        assert r.status_code == 200
        items = r.json().get("data", r.json())
        if isinstance(items, dict):
            items = items.get("items", [])
        doc = next((t for t in items if t.get("code") == "document_delivery"), None)
        assert doc, f"template document_delivery tidak ada. sample={items[:2]}"
        assert doc.get("header_type") == "document"
        assert doc.get("category") == "utility"
        assert doc.get("status") == "approved"
        # meta preview
        rp = sa.get(f"{API}/wa-templates/{doc['id']}/meta-preview", timeout=30)
        assert rp.status_code == 200
        comps = rp.json().get("data", {}).get("components") or rp.json().get("components")
        assert comps and comps[0].get("type") == "HEADER" and comps[0].get("format") == "DOCUMENT"
        body = next((c for c in comps if c.get("type") == "BODY"), None)
        assert body and re.search(r"\{\{1\}\}", body.get("text", ""))
        for i in (2, 3, 4):
            assert f"{{{{{i}}}}}" in body["text"], f"var {{{{{i}}}}} tidak ada di body: {body['text']}"

    def test_crud_header_type(self, sa):
        payload = {
            "code": f"tst_p99_hdr_{os.urandom(3).hex()}",
            "name": "Uji Header Doc",
            "language": "id",
            "category": "utility",
            "body": "Halo {{nama}}",
            "variables": ["nama"],
            "header_type": "document",
            "header_sample_handle": "4::sample_handle",
        }
        r = sa.post(f"{API}/wa-templates", json=payload, timeout=30)
        assert r.status_code in (200, 201), r.text[:300]
        tid = (r.json().get("data") or r.json()).get("id") or (r.json().get("data") or r.json()).get("_id")
        assert tid
        # bad header_type
        bad = dict(payload)
        bad["code"] = payload["code"] + "_bad"
        bad["header_type"] = "video"
        rb = sa.post(f"{API}/wa-templates", json=bad, timeout=30)
        assert rb.status_code == 400, f"video harus 400, dapat {rb.status_code} {rb.text[:200]}"
        # update to text
        ru = sa.put(f"{API}/wa-templates/{tid}", json={"header_type": "text", "header_text": "Header teks"}, timeout=30)
        assert ru.status_code == 200, ru.text[:200]

        # submit tanpa handle: buat template baru header=document tanpa header_sample_handle
        payload2 = dict(payload)
        payload2["code"] = payload["code"] + "_noh"
        payload2.pop("header_sample_handle", None)
        r2 = sa.post(f"{API}/wa-templates", json=payload2, timeout=30)
        assert r2.status_code in (200, 201), r2.text[:200]
        tid2 = (r2.json().get("data") or r2.json()).get("id")
        rs = sa.post(f"{API}/wa-templates/{tid2}/submit", timeout=30)
        # jujur: ok=false not_live (either 200 dgn ok=false atau 400)
        body_js = rs.json() if rs.headers.get("content-type", "").startswith("application/json") else {}
        assert rs.status_code in (200, 400)
        ok = body_js.get("ok", body_js.get("data", {}).get("ok"))
        err = body_js.get("error_code") or body_js.get("data", {}).get("error_code") or (body_js.get("detail") or "")
        assert ok is False or "not_live" in str(err).lower() or rs.status_code == 400, f"expected honest failure: {rs.status_code} {rs.text[:300]}"

        # cleanup
        sa.delete(f"{API}/wa-templates/{tid}", timeout=30)
        sa.delete(f"{API}/wa-templates/{tid2}", timeout=30)


# -------------------- Reference --------------------
class TestReference:
    def test_reference_groups(self, sa):
        r = sa.get(f"{API}/reference", timeout=30)
        assert r.status_code == 200
        data = r.json().get("data", r.json())
        # Bisa berbentuk dict grup atau list
        keys = list(data.keys()) if isinstance(data, dict) else [g.get("code") or g.get("group") for g in data]
        assert "task_related_type" in keys, f"task_related_type hilang. keys={keys[:20]}"
        assert "wa_template_header" in keys, f"wa_template_header hilang. keys={keys[:20]}"


# -------------------- Doc history & send-wa --------------------
def _walk_pdf(node, path=None):
    """Cari (pdf_url, label) rekursif."""
    path = path or []
    if isinstance(node, dict):
        pdf = node.get("pdf_url")
        if pdf:
            yield pdf, node.get("label") or node.get("kind") or node.get("type") or "Dokumen"
        for k, v in node.items():
            yield from _walk_pdf(v, path + [k])
    elif isinstance(node, list):
        for x in node:
            yield from _walk_pdf(x, path)


class TestDocHistoryWa:
    def test_route_and_send(self, sa):
        # pilih customer pertama yang memiliki pdf_url pada doc-history
        rc = sa.get(f"{API}/customers", timeout=30)
        assert rc.status_code == 200
        clist = rc.json().get("data", rc.json())
        if isinstance(clist, dict):
            clist = clist.get("items", [])
        chosen = None
        chosen_pdf = None
        chosen_label = None
        for c in clist[:30]:
            cid = c.get("id") or c.get("_id")
            if not cid:
                continue
            rd = sa.get(f"{API}/doc-history/customer/{cid}", timeout=30)
            if rd.status_code != 200:
                continue
            data = rd.json().get("data", rd.json())
            # route present?
            wa = data.get("wa_send") or {}
            route = wa.get("route") or {}
            if not route:
                continue
            assert route.get("via") in {"session", "template", "blocked"}, route
            assert route.get("template_code") == "document_delivery", route
            assert route.get("note"), route
            # cari pdf
            for pdf, label in _walk_pdf(data.get("deals", [])):
                chosen = cid
                chosen_pdf = pdf
                chosen_label = label
                break
            if chosen:
                break
        if not chosen:
            pytest.skip("tidak ada customer dengan pdf_url di doc-history/deals")

        # panggil ulang route final utk customer terpilih
        rd = sa.get(f"{API}/doc-history/customer/{chosen}", timeout=30)
        route_via = rd.json()["data"]["wa_send"]["route"]["via"]

        # kirim
        payload = {
            "entity_type": "customer",
            "entity_id": chosen,
            "pdf_url": chosen_pdf,
            "label": chosen_label,
            "number": "+628139900321",
        }
        rs = sa.post(f"{API}/doc-history/send-wa", json=payload, timeout=45)
        assert rs.status_code == 200, rs.text[:400]
        js = rs.json().get("data", rs.json())
        msg = js.get("message") or {}
        share = js.get("share") or {}
        assert msg.get("status") == "simulated", msg
        # body rendered
        body_text = msg.get("body") or msg.get("text") or ""
        assert "{" not in body_text, f"body masih ada placeholder: {body_text!r}"
        if route_via == "template":
            assert msg.get("is_template") is True
            assert msg.get("template_code") == "document_delivery"
            assert share.get("via") == "template"


# -------------------- Balasan Cerdas --------------------
class TestSmartSuggestions:
    def test_suggestions(self, sa):
        # gunakan simulate/inbound agar first_message tersimpan (import biasa tidak seed first_message)
        phone = "+628139900777"
        sim = sa.post(
            f"{API}/wa/simulate/inbound",
            json={"phone": phone, "name": "Uji QA", "message": "harga dan kpr berapa?", "mtype": "text"},
            timeout=30,
        )
        assert sim.status_code == 200, sim.text[:200]
        # cari kontak
        rf = sa.get(f"{API}/wa/contacts", params={"q": "Uji QA"}, timeout=30)
        assert rf.status_code == 200
        items = rf.json().get("data", rf.json())
        if isinstance(items, dict):
            items = items.get("items", [])
        assert items, "kontak uji tidak ditemukan"
        cid = items[0].get("id") or items[0].get("_id")
        try:
            rs = sa.get(f"{API}/wa/contacts/{cid}/suggestions", timeout=30)
            assert rs.status_code == 200, rs.text[:200]
            data = rs.json().get("data", rs.json())
            arr = data.get("items") if isinstance(data, dict) else data
            assert arr, "suggestions kosong"
            for it in arr:
                for k in ("title", "template_code", "template_name", "ready", "body", "usable", "reason"):
                    assert k in it, f"field {k} hilang di item: {it}"
                assert "{" not in (it.get("body") or ""), f"body ada placeholder: {it['body']!r}"
            sources = {it.get("source") for it in arr}
            assert "playbook" in sources, f"no playbook source: {sources}"
            assert "keyword" in sources, f"no keyword source: {sources}"
            # keyword harus mengarah price_info
            kw = [it for it in arr if it.get("source") == "keyword"]
            assert any(it.get("template_code") == "price_info" for it in kw), kw

            # kontak tidak dikenal → 404
            r404 = sa.get(f"{API}/wa/contacts/deadbeefdeadbeef/suggestions", timeout=30)
            assert r404.status_code == 404
        finally:
            sa.delete(f"{API}/wa/contacts/{cid}", timeout=30)


# -------------------- RBAC --------------------
class TestRBAC:
    def test_manager_has_pricing_approve(self):
        tok = _login("manager@sipro.co.id")
        r = requests.get(f"{API}/auth/me", headers=_hdr(tok), timeout=30)
        assert r.status_code == 200
        perms = (r.json().get("data") or r.json()).get("permissions") or {}
        pricing = perms.get("pricing") or []
        assert "approve" in pricing, f"manager pricing perms: {pricing}"

    def test_sales_no_pricing_approve(self):
        tok = _login("sales@sipro.co.id")
        r = requests.get(f"{API}/auth/me", headers=_hdr(tok), timeout=30)
        assert r.status_code == 200
        perms = (r.json().get("data") or r.json()).get("permissions") or {}
        pricing = perms.get("pricing") or []
        assert "approve" not in pricing, f"sales seharusnya tidak punya pricing:approve: {pricing}"

    def test_finlead_finance_manage(self):
        try:
            tok = _login("finlead@sipro.co.id")
        except AssertionError:
            pytest.skip("finlead@sipro.co.id tidak ada")
        r = requests.get(f"{API}/auth/me", headers=_hdr(tok), timeout=30)
        assert r.status_code == 200
        perms = (r.json().get("data") or r.json()).get("permissions") or {}
        finance = perms.get("finance") or []
        assert "manage" in finance, f"finlead finance perms: {finance}"
