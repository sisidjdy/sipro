"""
Iteration 151 tests: lead KPI cards, drilldown SLA/idle, numbering rules, doc config gates,
PDF layout order, allin RBAC, reservation limit override, session ui.table_page_size,
site plan background.
"""
import io
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/") or "http://localhost:8001"
API = BASE_URL + "/api"
PWD = "Sipro#2026"


def _login(email):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": PWD}, timeout=30)
    assert r.status_code == 200, f"login {email}: {r.status_code} {r.text}"
    tok = r.json().get("access_token")
    return tok, r.json()


@pytest.fixture(scope="module")
def super_hdr():
    tok, _ = _login("superadmin@sipro.co.id")
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="module")
def sales_hdr():
    tok, _ = _login("sales@sipro.co.id")
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="module")
def fin_hdr():
    tok, _ = _login("finance@sipro.co.id")
    return {"Authorization": f"Bearer {tok}"}


# ---------- 1) Lead KPI summary ----------
def test_lead_kpi_summary(super_hdr):
    r = requests.get(f"{API}/drilldown/_summary/leads", headers=super_hdr, timeout=30)
    assert r.status_code == 200, r.text
    body = r.json()
    cards = body.get("data") if isinstance(body, dict) else body
    m = {c["key"]: c["value"] for c in cards}
    for k in ("total", "active", "won", "recycle", "lost"):
        assert k in m, f"missing key {k} in {m}"
    total = int(m["total"])
    parts = int(m["active"]) + int(m["won"]) + int(m["recycle"]) + int(m["lost"])
    assert parts == total, f"parts {parts} != total {total} (cards={m})"

    r2 = requests.get(f"{API}/leads?limit=1", headers=super_hdr, timeout=30)
    assert r2.status_code == 200
    j2 = r2.json()
    lead_total = j2.get("total") if isinstance(j2, dict) else None
    if lead_total is None:
        d = j2.get("data") if isinstance(j2, dict) else None
        if isinstance(d, dict):
            lead_total = d.get("total")
    assert lead_total == total, f"lead_total {lead_total} != summary total {total}"


# ---------- 2) SLA & idle drilldown ----------
def test_drilldown_sla_and_idle(super_hdr):
    r = requests.get(f"{API}/drilldown/leads?sla=breached", headers=super_hdr, timeout=30)
    assert r.status_code == 200, r.text

    r2 = requests.get(f"{API}/drilldown/leads?idle_days=7&limit=20", headers=super_hdr, timeout=30)
    assert r2.status_code == 200
    body = r2.json()
    data = body.get("data") if isinstance(body, dict) else body
    rows = (data or {}).get("rows") if isinstance(data, dict) else (body.get("rows") or body.get("items") or [])
    if rows:
        import datetime as dt
        cutoff = dt.datetime.utcnow() - dt.timedelta(days=7)
        for row in list(rows)[:5]:
            lid = row.get("id") or row.get("_id")
            if not lid:
                continue
            g = requests.get(f"{API}/leads/{lid}", headers=super_hdr, timeout=15)
            if g.status_code != 200:
                continue
            gj = g.json()
            created = gj.get("created_at") or (gj.get("data") or {}).get("created_at")
            if not created:
                continue
            created_dt = dt.datetime.fromisoformat(created.replace("Z", "").split("+")[0])
            assert created_dt <= cutoff, f"lead {lid} created_at {created} within last 7d but returned as idle"


# ---------- 3) Numbering rules for SPR types ----------
def test_numbering_rules_and_override(super_hdr):
    r = requests.get(f"{API}/numbering", headers=super_hdr, timeout=30)
    assert r.status_code == 200, r.text
    items = r.json().get("data") or []
    keys = {x.get("key") for x in items}
    for k in ("docnum", "docnum:SPR-CASH", "docnum:SPR-CASHB", "docnum:SPR-KPR", "docnum:SPKT"):
        assert k in keys, f"missing numbering key {k}; got {keys}"

    try:
        pr = requests.put(
            f"{API}/numbering/docnum:SPR-KPR",
            headers=super_hdr,
            json={"pattern": "KPR-{SEQ:3}/{PROJECT_CODE}/{YYYY}", "reset": "yearly"},
            timeout=30,
        )
        assert pr.status_code == 200, pr.text
        pj = pr.json()
        preview = pj.get("preview") or pj.get("data", {}).get("preview") or ""
        overridden = pj.get("overridden") or pj.get("data", {}).get("overridden")
        assert overridden is True, f"overridden not True: {pj}"
        assert "KPR-001" in preview or "KPR-0001" in preview or preview.startswith("KPR-"), f"preview: {preview}"
        assert "2026" in preview, f"preview should include 2026: {preview}"

        r3 = requests.get(f"{API}/numbering", headers=super_hdr, timeout=30)
        rules3 = r3.json().get("data") or []
        cash = next((x for x in rules3 if x.get("key") == "docnum:SPR-CASH"), None)
        if cash is not None:
            assert not cash.get("overridden"), f"SPR-CASH should stay default: {cash}"
    finally:
        requests.delete(f"{API}/numbering/docnum:SPR-KPR", headers=super_hdr, timeout=30)


# ---------- 4) Doc config gates for SPR_KPR ----------
def _find_kpr_contract(hdr):
    """Kontrak KPR yang SPR-nya masih tertahan gerbang konfigurasi (booking fee / SLIK).

    Gate 46 kini melahirkan kontrak KPR yang sudah lolos SLIK & booking fee, jadi kontrak
    KPR pertama belum tentu tertahan — cari yang memang tertahan, atau skip bila tidak ada."""
    r = requests.get(f"{API}/contracts?limit=200", headers=hdr, timeout=30)
    assert r.status_code == 200, r.text
    items = r.json().get("items") or r.json().get("data") or []
    for c in items:
        if (c.get("scheme") or c.get("payment_scheme") or "").lower() != "kpr":
            continue
        cid = c.get("id") or c.get("_id")
        av = requests.get(f"{API}/contracts/{cid}/documents/available", headers=hdr, timeout=30)
        docs = av.json().get("items") or av.json().get("data") or []
        spr = next((d for d in docs if d.get("code") == "SPR_KPR"), None) if isinstance(docs, list) else None
        bs = " ".join(str(b) for b in ((spr or {}).get("blocks") or []))
        if "booking_fee_belum" in bs and "slik_belum" in bs:
            return cid
    return None


def test_doc_config_gates(super_hdr):
    cid = _find_kpr_contract(super_hdr)
    if not cid:
        pytest.skip("Tidak ada kontrak KPR yang tertahan gerbang booking fee + SLIK")
    r = requests.get(f"{API}/contracts/{cid}/documents/available", headers=super_hdr, timeout=30)
    assert r.status_code == 200, r.text
    docs = r.json().get("items") or r.json().get("data") or r.json()
    spr = None
    if isinstance(docs, list):
        spr = next((d for d in docs if d.get("code") == "SPR_KPR"), None)
    assert spr is not None, f"SPR_KPR not in available docs: {docs}"
    blocks = spr.get("blocks") or spr.get("gates") or []
    block_str = " ".join([str(b) for b in blocks])
    assert "booking_fee_belum" in block_str, f"expected booking_fee_belum in {blocks}"
    assert "slik_belum" in block_str, f"expected slik_belum in {blocks}"

    try:
        for key, val in [("reservation.require_booking_fee_before_spr", False), ("slik.gate", "off")]:
            pr = requests.put(f"{API}/settings/{key}", headers=super_hdr, json={"value": val, "reason": "uji"}, timeout=30)
            assert pr.status_code == 200, f"set {key}: {pr.text}"

        r2 = requests.get(f"{API}/contracts/{cid}/documents/available", headers=super_hdr, timeout=30)
        docs2 = r2.json().get("items") or r2.json().get("data") or r2.json()
        spr2 = next((d for d in docs2 if d.get("code") == "SPR_KPR"), None)
        blocks2 = spr2.get("blocks") or spr2.get("gates") or []
        bs2 = " ".join(str(b) for b in blocks2)
        assert "booking_fee_belum" not in bs2, f"booking_fee_belum still present: {blocks2}"
        assert "slik_belum" not in bs2, f"slik_belum still present: {blocks2}"
    finally:
        for key in ("reservation.require_booking_fee_before_spr", "slik.gate"):
            requests.post(f"{API}/settings/{key}/reset", headers=super_hdr, timeout=15)


# ---------- 5) PDF section order (biaya) ----------
def test_doc_pdf_biaya_order(super_hdr):
    cid = _find_kpr_contract(super_hdr)
    if not cid:
        pytest.skip("No KPR contract")
    # turn off gates
    for key, val in [("reservation.require_booking_fee_before_spr", False), ("slik.gate", "off")]:
        requests.put(f"{API}/settings/{key}", headers=super_hdr, json={"value": val, "reason": "uji"}, timeout=30)
    doc_id = None
    try:
        # get current layout
        lr = requests.get(f"{API}/doc-layouts/SPR_KPR", headers=super_hdr, timeout=15)
        assert lr.status_code == 200, lr.text
        layout = lr.json().get("data") or lr.json()
        sections = layout.get("sections") or []
        money_rows = layout.get("money_rows") or []
        options = layout.get("options") or {}

        def _set_biaya(visible, order):
            new_sections = []
            found = False
            for s in sections:
                s2 = dict(s)
                if s2.get("key") == "biaya":
                    s2["visible"] = visible
                    s2["order"] = order
                    found = True
                new_sections.append(s2)
            if not found:
                new_sections.append({"key": "biaya", "visible": visible, "order": order})
            body = {"sections": new_sections, "money_rows": money_rows, "options": options}
            pr = requests.put(f"{API}/doc-layouts/SPR_KPR", headers=super_hdr, json=body, timeout=30)
            assert pr.status_code == 200, pr.text

        # set biaya visible=True order=-5 BEFORE creating doc
        _set_biaya(True, -5)

        cr = requests.post(f"{API}/contracts/{cid}/documents", headers=super_hdr, json={"code": "SPR_KPR"}, timeout=30)
        assert cr.status_code in (200, 201), cr.text
        cj = cr.json().get("data") or cr.json()
        doc_id = cj.get("id") or cj.get("_id")
        assert doc_id, cj

        pdf = requests.get(f"{API}/documents/{doc_id}/pdf", headers=super_hdr, timeout=60)
        assert pdf.status_code == 200, pdf.text[:400]
        assert "application/pdf" in pdf.headers.get("content-type", "").lower()
        try:
            import fitz  # pymupdf
            doc = fitz.open(stream=pdf.content, filetype="pdf")
            text_on = "\n".join(p.get_text() for p in doc)
            doc.close()
        except Exception as e:
            pytest.skip(f"pymupdf unavailable: {e}")
        assert "Rincian biaya" in text_on or "Rincian Biaya" in text_on, "'Rincian biaya' missing in PDF with biaya visible"

        # biaya invisible
        _set_biaya(False, 50)
        pdf2 = requests.get(f"{API}/documents/{doc_id}/pdf", headers=super_hdr, timeout=60)
        assert pdf2.status_code == 200
        import fitz
        d2 = fitz.open(stream=pdf2.content, filetype="pdf")
        text_off = "\n".join(p.get_text() for p in d2)
        d2.close()
        assert "Rincian biaya" not in text_off and "Rincian Biaya" not in text_off, "'Rincian biaya' still in PDF when biaya invisible"
    finally:
        requests.delete(f"{API}/doc-layouts/SPR_KPR", headers=super_hdr, timeout=15)
        for key in ("reservation.require_booking_fee_before_spr", "slik.gate"):
            requests.post(f"{API}/settings/{key}/reset", headers=super_hdr, timeout=15)


# ---------- 6) RBAC catalog on /api/cost-components ----------
def test_cost_components_rbac(sales_hdr, fin_hdr, super_hdr):
    r = requests.get(f"{API}/cost-components", headers=sales_hdr, timeout=15)
    assert r.status_code == 200, r.text

    payload = {"code": f"TEST_CC_{int(time.time())}", "name": "TEST komponen", "gl_expense": "", "gl_titipan": "", "gl_ap": ""}
    r2 = requests.post(f"{API}/cost-components", headers=sales_hdr, json=payload, timeout=15)
    assert r2.status_code == 403, f"sales should be 403 got {r2.status_code} {r2.text}"
    assert "catalog" in r2.text.lower(), f"403 message should mention catalog: {r2.text}"

    r3 = requests.post(f"{API}/cost-components", headers=fin_hdr, json=payload, timeout=15)
    if r3.status_code in (200, 201):
        cid = r3.json().get("id") or r3.json().get("_id")
        if cid:
            requests.put(f"{API}/cost-components/{cid}", headers=fin_hdr, json={"is_active": False}, timeout=15)
    else:
        # If failure is due to missing GL requirement etc., allow but assert not 403
        assert r3.status_code != 403, f"finance should not be 403 for catalog: {r3.text}"


# ---------- 7) Session ui.table_page_size ----------
def test_session_ui_table_page_size():
    _, body = _login("superadmin@sipro.co.id")
    tok = body["access_token"]
    hdr = {"Authorization": f"Bearer {tok}"}
    ui = (body.get("data") or {}).get("ui") or body.get("ui") or {}
    assert int(ui.get("table_page_size", 0)) == 25, f"default table_page_size expected 25, got {ui}"
    try:
        pr = requests.put(f"{API}/settings/ui.table_page_size", headers=hdr, json={"value": 50, "reason": "uji"}, timeout=15)
        assert pr.status_code == 200, pr.text
        me = requests.get(f"{API}/auth/me", headers=hdr, timeout=15)
        assert me.status_code == 200
        mj = me.json()
        ui2 = (mj.get("data") or {}).get("ui") or mj.get("ui") or {}
        assert int(ui2.get("table_page_size", 0)) == 50, f"expected 50 after PUT, got {ui2}"
    finally:
        requests.post(f"{API}/settings/ui.table_page_size/reset", headers=hdr, timeout=15)


# ---------- 8) Site plan background ----------
def test_site_plan_background(super_hdr):
    # find a project
    r = requests.get(f"{API}/projects?limit=5", headers=super_hdr, timeout=15)
    assert r.status_code == 200, r.text
    items = r.json().get("items") or r.json().get("data") or []
    if not items:
        pytest.skip("no projects seeded")
    pid = items[0].get("id") or items[0].get("_id")

    try:
        from PIL import Image
        buf = io.BytesIO()
        Image.new("RGB", (32, 32), (240, 200, 100)).save(buf, format="PNG")
        buf.seek(0)
    except Exception as e:
        pytest.skip(f"PIL unavailable: {e}")

    up = requests.post(
        f"{API}/site-plan-studio/{pid}/background",
        headers=super_hdr,
        files={"file": ("bg.png", buf.getvalue(), "image/png")},
        timeout=30,
    )
    assert up.status_code == 200, up.text
    try:
        pl = requests.get(f"{API}/site-plan/{pid}", headers=super_hdr, timeout=15)
        assert pl.status_code == 200, pl.text
        pj = pl.json().get("data") or pl.json()
        svg_plan = pj.get("svg_plan") or pj.get("plan") or {}
        bg = svg_plan.get("background") or {}
        url = bg.get("url", "")
        assert url.startswith("/api/files/"), f"expected /api/files/... got {url!r}; svg_plan={svg_plan}"
        fr = requests.get(f"{BASE_URL}{url}", headers=super_hdr, timeout=15)
        assert fr.status_code == 200
        assert "image" in fr.headers.get("content-type", "").lower()
    finally:
        requests.delete(f"{API}/site-plan-studio/{pid}/background", headers=super_hdr, timeout=15)


# ---------- 9) Reservation limit override ----------
def test_reservation_limit_override(super_hdr):
    # find a lead that currently has an active deal
    r = requests.get(f"{API}/deals?limit=200", headers=super_hdr, timeout=30)
    assert r.status_code == 200
    deals = r.json().get("items") or r.json().get("data") or []
    active = [d for d in deals if (d.get("status") in ("reserved", "booked"))]
    if not active:
        pytest.skip("no active deals seeded")
    lead_id = active[0].get("lead_id") or active[0].get("lead", {}).get("id")
    if not lead_id:
        pytest.skip("cannot resolve lead_id from deal")

    # find available unit not tied to this lead
    ur = requests.get(f"{API}/units?status=available&limit=20", headers=super_hdr, timeout=30)
    units = []
    if ur.status_code == 200:
        units = ur.json().get("items") or ur.json().get("data") or []
    if not units:
        pytest.skip("no available units")
    unit_id = units[0].get("id") or units[0].get("_id")

    body = {"unit_id": unit_id, "lead_id": lead_id, "booking_fee": 0}
    r1 = requests.post(f"{API}/deals/reserve", headers=super_hdr, json=body, timeout=30)
    if r1.status_code != 409 or "batas" not in r1.text.lower():
        pytest.skip(f"lead likely not at limit (got {r1.status_code} {r1.text[:200]}); needs seeded fixture")
    body["limit_override_reason"] = "uji override batas reservasi"
    r2 = requests.post(f"{API}/deals/reserve", headers=super_hdr, json=body, timeout=30)
    # accept either success or a different 4xx not about 'batas'
    if r2.status_code not in (200, 201):
        assert "batas" not in r2.text.lower(), f"still 'batas' error after override: {r2.text}"
