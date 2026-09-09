"""Audit Tahap 1–2 + fitur tahapan (2026-09-06). Jalan terhadap server hidup (conftest BASE_URL)."""
import uuid

import pytest
import requests

from conftest import BASE_URL, _login, _sess


@pytest.fixture(scope="module")
def s_admin():
    return _sess(_login("superadmin@sipro.co.id"))


def _api(s, method, path, **kw):
    return getattr(s, method)(f"{BASE_URL}/api{path}", timeout=30, **kw)


# ---------------------------------------------------------------- WA-02 / DOC-01
def test_doc01_invoice_pdf_paid_per_item(s_admin):
    invs = _api(s_admin, "get", "/finance/ar").json()["data"]
    partial = [i for i in invs if i["status"] == "partial"]
    if not partial:
        pytest.skip("tidak ada invoice partial di data")
    inv = partial[0]
    r = _api(s_admin, "get", f"/finance/ar/{inv['deal_id']}/invoice/pdf")
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/pdf")
    import fitz  # pymupdf
    text = fitz.open(stream=r.content, filetype="pdf")[0].get_text()
    paid_items = [it for it in inv["items"] if it.get("paid_amount")]
    assert paid_items, "invoice partial harus punya termin yang sudah dibayar"
    for it in paid_items:
        rp = f"Rp {int(it['paid_amount']):,}".replace(",", ".")
        idx = text.index(it["label"])
        assert rp in text[idx: idx + 200], f"kolom Dibayar termin {it['label']} harus {rp}"


def test_wa02_reminder_candidates_skip_paid_items(s_admin):
    r = _api(s_admin, "get", "/reminders/candidates")
    if r.status_code == 404:
        pytest.skip("endpoint kandidat tidak ada di route ini")
    assert r.status_code == 200
    rows = r.json().get("data") or r.json().get("rows") or []
    invs = {i["id"]: i for i in _api(s_admin, "get", "/finance/ar").json()["data"]}
    for c in rows:
        if c["kind"] not in ("installment_due", "installment_overdue"):
            continue
        inv = invs.get(c["entity_id"])
        if not inv:
            continue
        item = next((it for it in inv["items"] if it["label"] == c["vars"]["termin"]), None) if c.get("vars") else None
        if item:
            assert item["status"] != "paid", f"termin lunas {item['label']} tidak boleh jadi kandidat"
            assert c["amount"] == item["amount"] - item.get("paid_amount", 0)


# ---------------------------------------------------------------- WA-04 / WA-13 / WA-12
def test_wa04_variables_mismatch_rejected(s_admin):
    name = f"Uji Var {uuid.uuid4().hex[:6]}"
    r = _api(s_admin, "post", "/wa-templates", json={
        "name": name, "category": "utility", "body": "Halo {{nama}}, unit {{unit}}", "variables": ["nama"]})
    assert r.status_code == 400 and "{{unit}}" in r.json()["detail"]
    r = _api(s_admin, "post", "/wa-templates", json={
        "name": name, "category": "utility", "body": "Halo {{nama}}", "variables": ["nama", "unit"]})
    assert r.status_code == 400 and "unit" in r.json()["detail"]
    r = _api(s_admin, "post", "/wa-templates", json={
        "name": name, "category": "utility", "body": "Halo {{nama}}, unit {{unit}}",
        "variables": ["nama", "unit"], "examples": {"nama": "Budi", "unit": "A-01"}})
    assert r.status_code == 200, r.text
    t = r.json()["data"]
    assert t["examples"] == {"nama": "Budi", "unit": "A-01"}
    r = _api(s_admin, "put", f"/wa-templates/{t['id']}", json={"body": "Halo {{nama}} saja"})
    assert r.status_code == 400
    prev = _api(s_admin, "get", f"/wa-templates/{t['id']}/meta-preview")
    if prev.status_code == 200:
        body = [c for c in prev.json()["data"]["components"] if c["type"] == "BODY"][0]
        assert body["example"]["body_text"] == [["Budi", "A-01"]]
        assert "{{1}}" in body["text"] and "{{2}}" in body["text"]
    _api(s_admin, "delete", f"/wa-templates/{t['id']}")


def test_wa01_reminder_templates_distinct(s_admin):
    codes = {t["code"]: t for t in _api(s_admin, "get", "/wa-templates").json()["data"]}
    need = ["reminder_installment_due", "reminder_installment_overdue", "reminder_arrears_warning",
            "reminder_warranty_expiring", "reminder_booking_fee_due"]
    for c in need:
        assert c in codes, f"template {c} harus ter-seed"
        assert codes[c]["status"] in ("approved", "pending", "rejected")
    bodies = {codes[c]["body"] for c in need}
    assert len(bodies) == len(need), "isi template pengingat harus berbeda per jenis"


# ---------------------------------------------------------------- Tahapan pembangunan
def test_phase_template_crud_and_apply(s_admin):
    r = _api(s_admin, "get", "/construction/phase-templates")
    assert r.status_code == 200 and any(t["is_default"] for t in r.json()["data"])
    code = f"UJI{uuid.uuid4().hex[:4].upper()}"
    r = _api(s_admin, "post", "/construction/phase-templates", json={
        "code": code, "name": "Template uji 3 fase",
        "phases": [{"name": "Fase A", "weight": 50, "planned_pct": 100},
                   {"name": "Fase B", "weight": 30}, {"name": "Fase C", "weight": 10}]})
    assert r.status_code == 200, r.text
    tpl = r.json()["data"]
    assert [p["order"] for p in tpl["phases"]] == [1, 2, 3]
    assert any("90%" in w for w in r.json()["warnings"])
    # proyek uji
    pr = _api(s_admin, "post", "/projects", json={"code": f"PJ{uuid.uuid4().hex[:4].upper()}", "name": "Proyek uji fase",
                                                  "location": "Uji", "total_units": 0})
    if pr.status_code not in (200, 201):
        pytest.skip(f"tidak bisa membuat proyek uji: {pr.status_code} {pr.text[:120]}")
    pid = (pr.json().get("data") or pr.json())["id"]
    r = _api(s_admin, "post", f"/construction/project/{pid}/phases/apply", json={"template_id": tpl["id"]})
    assert r.status_code == 200, r.text
    assert len(r.json()["data"]) == 3 and r.json()["skipped"] == []
    r2 = _api(s_admin, "post", f"/construction/project/{pid}/phases/apply", json={"template_id": tpl["id"]})
    assert r2.json()["data"] == [] and len(r2.json()["skipped"]) == 3, "idempoten: nama yang ada dilewati"
    phases = _api(s_admin, "get", f"/construction/project/{pid}/phases").json()["data"]
    assert [p["name"] for p in phases] == ["Fase A", "Fase B", "Fase C"]
    r = _api(s_admin, "post", "/construction/phases", json={"project_id": pid, "name": "Fase D", "weight": 10, "order": 4})
    assert r.status_code == 200
    _api(s_admin, "delete", f"/construction/phase-templates/{tpl['id']}")


# ---------------------------------------------------------------- Tahapan survey
def test_survey_stages_config_and_wizard(s_admin):
    conf = _api(s_admin, "get", "/survey-stages").json()["data"]
    assert len(conf["stages"]) >= 1 and all(s["key"] for s in conf["stages"])
    stages = [{"name": "Tahap uji 1", "description": "d", "items": [{"label": "Poin wajib", "required": True}]},
              {"name": "Tahap uji 2", "items": [{"label": "Poin bebas", "required": False}]}]
    r = _api(s_admin, "put", "/survey-stages", json={"stages": stages})
    assert r.status_code == 200 and [s["order"] for s in r.json()["data"]["stages"]] == [1, 2]
    try:
        lead = _api(s_admin, "get", "/leads", params={"limit": 1}).json()["data"][0]
        r = _api(s_admin, "post", "/surveys", json={"lead_id": lead["id"], "location": "Uji"})
        assert r.status_code == 200, r.text
        sv = r.json()["data"]
        assert [s["name"] for s in sv["stages"]] == ["Tahap uji 1", "Tahap uji 2"]
        assert {c["stage_key"] for c in sv["checklist"]} == {s["key"] for s in sv["stages"]}
        assert sv["current_stage"] == 0
        r = _api(s_admin, "post", f"/surveys/{sv['id']}/result", json={"result": "recommended"})
        assert r.status_code == 400 and "Poin wajib" in r.json()["detail"]
        cl = [{**c, "status": "ok"} if c["required"] else c for c in sv["checklist"]]
        r = _api(s_admin, "put", f"/surveys/{sv['id']}", json={"checklist": cl, "current_stage": 1})
        assert r.status_code == 200 and r.json()["data"]["current_stage"] == 1
        assert all(c["stage_key"] for c in r.json()["data"]["checklist"]), "stage_key harus dipertahankan"
        r = _api(s_admin, "post", f"/surveys/{sv['id']}/result", json={"result": "recommended"})
        assert r.status_code == 200 and r.json()["data"]["status"] == "completed"
    finally:
        _api(s_admin, "put", "/survey-stages", json={"stages": [
            {"name": s["name"], "description": s.get("description"),
             "items": [{"label": i["label"], "required": i["required"], "hint": i.get("hint")} for i in s["items"]]}
            for s in conf["stages"]]})
