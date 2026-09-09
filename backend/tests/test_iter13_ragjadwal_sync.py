"""Iteration 13 — Cek Sinkron RAB–Jadwal + refactor split file regression."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL must be set"


def unwrap(body):
    if isinstance(body, dict) and "data" in body and not any(k in body for k in ("code", "id", "status")):
        return body["data"]
    return body


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": "superadmin@sipro.co.id",
        "password": "Sipro#2026",
    })
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def headers(token):
    return {"Authorization": f"Bearer {token}"}


# ---- Feature: Cek Sinkron RAB–Jadwal ----

def test_rab_unit_templates_have_sync_flags(headers):
    r = requests.get(f"{BASE_URL}/api/rab/templates/unit_type", headers=headers)
    assert r.status_code == 200, r.text
    rows = unwrap(r.json())
    assert isinstance(rows, list) and len(rows) > 0
    for row in rows:
        assert "has_schedule_template" in row, row
        assert "step_mismatch" in row, row
    target = next((x for x in rows if x.get("ref_code") == "TIPE-36-72" or x.get("code") == "TIPE-36-72"), None)
    assert target, [x.get("ref_code") for x in rows]
    assert target["step_mismatch"] == 1, target
    assert target["has_schedule_template"] is True


def test_rab_sync_check_tipe_36_72(headers):
    r = requests.get(f"{BASE_URL}/api/rab/templates/unit_type/TIPE-36-72/sync-check", headers=headers)
    assert r.status_code == 200, r.text
    data = unwrap(r.json())
    assert data.get("has_template") is True, data
    tmpl_codes = [t.get("code") for t in data.get("templates", [])]
    assert "RUMAH-9W" in tmpl_codes, tmpl_codes
    unknown = data.get("unknown_steps", [])
    assert any(u.get("step_code") == "ZZ-99" for u in unknown), unknown
    assert data.get("ok") is False
    assert "steps_without_rab" in data


def test_rab_sync_check_addon_not_found(headers):
    r = requests.get(f"{BASE_URL}/api/rab/templates/addon/X/sync-check", headers=headers)
    assert r.status_code == 404


def test_rab_put_returns_sync_field(headers):
    payload = {"items": [
        {"code": "Q1", "description": "Uji", "category": "struktur", "uom": "m3", "qty": 1, "unit_price": 1000, "step_code": "W1-02"},
        {"code": "Q2", "description": "Uji2", "category": "struktur", "uom": "m3", "qty": 1, "unit_price": 1000, "step_code": "NOPE-1"},
    ]}
    r = requests.put(f"{BASE_URL}/api/rab/templates/unit_type/TIPE-45-90", headers=headers, json=payload)
    assert r.status_code == 200, r.text
    body = r.json()  # do not unwrap: 'sync' is sibling of 'data'
    sync = body.get("sync")
    assert sync is not None, body
    unk = sync.get("unknown_steps")
    if isinstance(unk, list):
        assert len(unk) == 1, unk
    else:
        assert unk == 1, sync

    # Cleanup
    r2 = requests.put(f"{BASE_URL}/api/rab/templates/unit_type/TIPE-45-90", headers=headers, json={"items": []})
    assert r2.status_code == 200
    body2 = r2.json()
    sync2 = body2.get("sync")
    assert sync2 is not None
    unk2 = sync2.get("unknown_steps")
    if isinstance(unk2, list):
        assert len(unk2) == 0
    else:
        assert unk2 == 0
    assert sync2.get("ok") is True


def _get_build_templates(headers):
    r = requests.get(f"{BASE_URL}/api/build/templates", headers=headers)
    assert r.status_code == 200
    return unwrap(r.json())


def test_build_templates_list_has_rumah_9w(headers):
    tmpls = _get_build_templates(headers)
    assert isinstance(tmpls, list)
    target = next((t for t in tmpls if isinstance(t, dict) and t.get("code") == "RUMAH-9W"), None)
    assert target, [t.get("code") if isinstance(t, dict) else t for t in tmpls]
    uts = target.get("unit_types", [])
    ut_names = []
    for u in uts:
        if isinstance(u, dict):
            ut_names.append(u.get("name") or u.get("code") or "")
        else:
            ut_names.append(str(u))
    assert any("36/72" in n or "TIPE-36-72" in n for n in ut_names), ut_names


def test_build_template_detail_has_warning(headers):
    tmpls = _get_build_templates(headers)
    tid = next(t["id"] for t in tmpls if isinstance(t, dict) and t.get("code") == "RUMAH-9W")

    r2 = requests.get(f"{BASE_URL}/api/build/templates/{tid}", headers=headers)
    assert r2.status_code == 200, r2.text
    body = r2.json()
    warnings = body.get("warnings", [])
    msg = " || ".join(warnings) if isinstance(warnings, list) else str(warnings)
    assert "TIPE-36-72" in msg and "ZZ-99" in msg, warnings


def test_build_template_put_preserves_and_warns(headers):
    tmpls = _get_build_templates(headers)
    tid = next(t["id"] for t in tmpls if isinstance(t, dict) and t.get("code") == "RUMAH-9W")

    detail_body = requests.get(f"{BASE_URL}/api/build/templates/{tid}", headers=headers).json()
    detail = detail_body.get("data") if isinstance(detail_body, dict) and "data" in detail_body else detail_body
    payload = {
        "name": detail.get("name"),
        "description": detail.get("description"),
        "unit_types": detail.get("unit_types"),
        "project_id": detail.get("project_id"),
        "steps": detail.get("steps"),
        "code": detail.get("code"),
    }
    for k in ("category", "duration_days", "notes", "active"):
        if k in detail:
            payload[k] = detail[k]

    r3 = requests.put(f"{BASE_URL}/api/build/templates/{tid}", headers=headers, json=payload)
    assert r3.status_code == 200, r3.text
    body = r3.json()
    warnings = body.get("warnings") or []
    msg = " || ".join(warnings) if isinstance(warnings, list) else str(warnings)
    assert "TIPE-36-72" in msg and "ZZ-99" in msg, warnings


# ---- Refactor regression: finance_ap.py, engine_sweepers.py ----

def test_health():
    r = requests.get(f"{BASE_URL}/api/health")
    assert r.status_code == 200
    body = r.json()
    status = body.get("status") or (body.get("data") or {}).get("status")
    assert status == "ok", body


def test_ap_bill_flow(headers):
    vendors = unwrap(requests.get(f"{BASE_URL}/api/vendors", headers=headers).json())
    assert isinstance(vendors, list) and vendors
    vendor = vendors[0]
    vendor_id = vendor.get("id") or vendor.get("code")
    projects = unwrap(requests.get(f"{BASE_URL}/api/projects", headers=headers).json())
    assert isinstance(projects, list) and projects
    pid = projects[0]["id"]

    payload = {
        "vendor": vendor_id,
        "project_id": pid,
        "claimed": 100000,
        "retention_pct": 5,
        "due_date": "2026-12-31",
        "note": "QA iter13",
    }
    r = requests.post(f"{BASE_URL}/api/finance/ap/bills", headers=headers, json=payload)
    assert r.status_code == 200, r.text
    bill = unwrap(r.json())
    bill_id = bill.get("id") if isinstance(bill, dict) else None
    assert bill_id, bill

    r2 = requests.post(f"{BASE_URL}/api/finance/ap/bills/{bill_id}/approve", headers=headers, json={})
    assert r2.status_code == 200, r2.text

    r3 = requests.post(f"{BASE_URL}/api/finance/ap/bills/{bill_id}/pay", headers=headers, json={"amount": 1000, "method": "transfer"})
    assert r3.status_code == 200, r3.text


# ---- Prior session regression smoke ----

def test_doc_layout_invoice_bf(headers):
    r = requests.get(f"{BASE_URL}/api/doc-layouts/INVOICE_BF", headers=headers)
    assert r.status_code == 200
    body = unwrap(r.json())
    assert body.get("code") == "INVOICE_BF", body


def test_build_template_clone_overlap_409(headers):
    tmpls = _get_build_templates(headers)
    ruko = next((t for t in tmpls if isinstance(t, dict) and t.get("code") == "RUKO-14W"), None)
    if not ruko:
        pytest.skip("RUKO-14W not seeded")
    r = requests.post(f"{BASE_URL}/api/build/templates/clone", headers=headers, json={
        "clone_from": ruko["id"],
        "code": "QA-OVL-IT13",
        "name": "QA IT13",
        "unit_types": ["Ruko"],
    })
    assert r.status_code == 409, r.text
