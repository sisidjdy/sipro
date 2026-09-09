"""Iteration 17: RAB fuzzy template pickup + Marketing Office field on Projects."""
import os
import uuid
import pytest
import requests

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{BASE}/api/auth/login",
                      json={"email": "superadmin@sipro.co.id", "password": "Sipro#2026"},
                      timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def hdr(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ---------------- RAB fuzzy template pickup ----------------

@pytest.fixture(scope="module")
def unit_type_rt(hdr):
    payload = {
        "code": "RT-30-60", "name": "Rumah Tapak 30/60",
        "building_area": 30, "land_area_std": 60, "base_price": 100000000,
    }
    r = requests.post(f"{BASE}/api/catalog/unit-types", json=payload, headers=hdr, timeout=30)
    # Might already exist; fall through
    if r.status_code == 400 and "sudah" in r.text.lower():
        # find by list
        lst = requests.get(f"{BASE}/api/catalog/unit-types", headers=hdr, timeout=30).json()["data"]
        row = next((x for x in lst if x.get("code") == "RT-30-60"), None)
        assert row, "existing RT-30-60 not found"
        return row
    assert r.status_code in (200, 201), r.text
    return r.json()["data"]


@pytest.fixture(scope="module")
def build_tpl(hdr, unit_type_rt):
    payload = {
        "code": "QA-3060", "name": "QA 30/60",
        "unit_types": ["30/60"],
        "steps": [
            {"code": "S1", "name": "Persiapan", "week": 1,
             "day_from": 1, "day_to": 6, "weight": 50},
            {"code": "S2", "name": "Pondasi", "week": 2,
             "day_from": 7, "day_to": 12, "weight": 50},
        ],
    }
    r = requests.post(f"{BASE}/api/build/templates", json=payload, headers=hdr, timeout=30)
    if r.status_code == 400 and "sudah" in r.text.lower():
        lst = requests.get(f"{BASE}/api/build/templates", headers=hdr, timeout=30).json()
        rows = lst.get("data", lst) if isinstance(lst, dict) else lst
        row = next((x for x in rows if x.get("code") == "QA-3060"), None)
        assert row, "existing QA-3060 not found"
        yield row
    else:
        assert r.status_code in (200, 201), r.text
        row = r.json().get("data", r.json())
        yield row
    # Cleanup
    tid = row.get("id")
    if tid:
        requests.delete(f"{BASE}/api/build/templates/{tid}", headers=hdr, timeout=30)


def test_rab_templates_unit_type_lists_has_schedule(hdr, unit_type_rt, build_tpl):
    r = requests.get(f"{BASE}/api/rab/templates/unit_type", headers=hdr, timeout=30)
    assert r.status_code == 200, r.text
    rows = r.json().get("data", r.json())
    row = next((x for x in rows if x.get("ref_code") == "RT-30-60"
                or x.get("code") == "RT-30-60"), None)
    assert row, f"RT-30-60 not in rows: {[x.get('ref_code') or x.get('code') for x in rows]}"
    assert row.get("has_schedule_template") is True, row
    assert row.get("steps_without_rab") == 2, row


def test_rab_sync_check_lists_missing_steps(hdr, unit_type_rt, build_tpl):
    r = requests.get(f"{BASE}/api/rab/templates/unit_type/RT-30-60/sync-check",
                     headers=hdr, timeout=30)
    assert r.status_code == 200, r.text
    body = r.json().get("data", r.json())
    assert body.get("has_template") is True, body
    codes = [s.get("code") if isinstance(s, dict) else s for s in body.get("steps_without_rab", [])]
    assert "S1" in codes and "S2" in codes, body


def test_build_templates_filter_by_master_name(hdr, build_tpl):
    r = requests.get(f"{BASE}/api/build/templates",
                     params={"unit_type": "Rumah Tapak 30/60"}, headers=hdr, timeout=30)
    assert r.status_code == 200, r.text
    rows = r.json().get("data", r.json())
    assert any(x.get("code") == "QA-3060" for x in rows), [x.get("code") for x in rows]


def test_build_templates_filter_by_code(hdr, build_tpl):
    r = requests.get(f"{BASE}/api/build/templates",
                     params={"unit_type": "RT-30-60"}, headers=hdr, timeout=30)
    assert r.status_code == 200, r.text
    rows = r.json().get("data", r.json())
    assert any(x.get("code") == "QA-3060" for x in rows), [x.get("code") for x in rows]


def test_build_templates_negative_filter(hdr, build_tpl):
    r = requests.get(f"{BASE}/api/build/templates",
                     params={"unit_type": "Ruko"}, headers=hdr, timeout=30)
    assert r.status_code == 200, r.text
    rows = r.json().get("data", r.json())
    assert not any(x.get("code") == "QA-3060" for x in rows), [x.get("code") for x in rows]


# ---------------- Marketing Office API ----------------

def test_project_marketing_office_crud(hdr):
    # find a project to PUT on (Harmony Land 5 exists per prompt)
    lst = requests.get(f"{BASE}/api/projects", headers=hdr, timeout=30).json()
    projects = lst.get("data", lst) if isinstance(lst, dict) else lst
    target = next((p for p in projects if "Harmony Land 5" in (p.get("name") or "")), None)
    if not target and projects:
        target = projects[0]  # fall back to first available project
    assert target, "no projects available"
    pid = target["id"]

    mo = "Marketing Gallery Jl. Uji No. 1"
    r = requests.put(f"{BASE}/api/projects/{pid}",
                     json={"marketing_office": mo}, headers=hdr, timeout=30)
    assert r.status_code == 200, r.text

    got = requests.get(f"{BASE}/api/projects/{pid}", headers=hdr, timeout=30).json()
    body = got.get("data", got)
    project_row = body.get("project", body)
    assert project_row.get("marketing_office") == mo, project_row

    # POST + DELETE
    code = f"QAMO{uuid.uuid4().hex[:4].upper()}"
    payload = {"name": "QA MO", "code": code, "location": "Kota Uji",
               "marketing_office": "Kantor Uji 2"}
    r = requests.post(f"{BASE}/api/projects", json=payload, headers=hdr, timeout=30)
    assert r.status_code in (200, 201), r.text
    new = r.json().get("data", r.json())
    assert new.get("marketing_office") == "Kantor Uji 2", new
    nid = new["id"]
    d = requests.delete(f"{BASE}/api/projects/{nid}", headers=hdr, timeout=30)
    assert d.status_code in (200, 204), d.text
