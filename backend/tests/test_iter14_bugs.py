"""Backend tests for iteration 14: BUG1 (build schedules) & BUG3 (custom roles)."""
import os
import pytest
import requests

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
CREDS = {"email": "superadmin@sipro.co.id", "password": "Sipro#2026"}


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{BASE}/auth/login", json=CREDS, timeout=30)
    assert r.status_code == 200, r.text
    return r.json().get("token") or r.json().get("data", {}).get("token") or r.json().get("access_token")


@pytest.fixture(scope="module")
def h(token):
    return {"Authorization": f"Bearer {token}"}


# ---------- BUG1: Build templates matching + unscheduled ----------
def test_login(token):
    assert token


def test_templates_filter_by_unit_type_code(h):
    r = requests.get(f"{BASE}/build/templates", params={"unit_type": "TIPE-36-72"}, headers=h, timeout=30)
    assert r.status_code == 200, r.text
    body = r.json()
    items = body.get("data") if isinstance(body, dict) else body
    codes = [t.get("code") for t in items]
    assert "RUMAH-9W" in codes, f"expected RUMAH-9W in {codes}"


def test_templates_filter_case_insensitive_name(h):
    r = requests.get(f"{BASE}/build/templates", params={"unit_type": "tipe 36/72"}, headers=h, timeout=30)
    assert r.status_code == 200
    items = r.json().get("data") if isinstance(r.json(), dict) else r.json()
    codes = [t.get("code") for t in items]
    assert "RUMAH-9W" in codes


def test_templates_filter_ruko(h):
    r = requests.get(f"{BASE}/build/templates", params={"unit_type": "Ruko"}, headers=h, timeout=30)
    assert r.status_code == 200
    items = r.json().get("data") if isinstance(r.json(), dict) else r.json()
    codes = [t.get("code") for t in items]
    assert codes == ["RUKO-14W"], f"expected only RUKO-14W got {codes}"


def test_reference_unit_type_includes_catalog(h):
    r = requests.get(f"{BASE}/reference/unit_type", headers=h, timeout=30)
    assert r.status_code == 200
    body = r.json()
    data = body.get("data") if isinstance(body, dict) else body
    opts = data.get("options") if isinstance(data, dict) and "options" in data else data
    labels = [o.get("label") or o.get("value") for o in opts]
    assert any("Tipe" in l for l in labels), f"labels: {labels}"
    assert any("Ruko" in l or "Kavling" in l for l in labels)


@pytest.fixture(scope="module")
def unscheduled_tipe(h):
    r = requests.get(f"{BASE}/build/unscheduled", headers=h, timeout=30)
    assert r.status_code == 200, r.text
    body = r.json()
    items = body.get("data") if isinstance(body, dict) else body
    # find a Tipe unit and a Kavling unit
    tipe = None
    kavling = None
    for u in items:
        t = (u.get("type") or "").lower()
        if not tipe and "tipe" in t:
            tipe = u
        if not kavling and "kavling" in t:
            kavling = u
    return {"tipe": tipe, "kavling": kavling, "all": items}


def test_unit_bundle_unscheduled_tipe_buildable(h, unscheduled_tipe):
    u = unscheduled_tipe["tipe"]
    if not u:
        pytest.skip("no unscheduled Tipe unit")
    r = requests.get(f"{BASE}/build/unit/{u['id']}", headers=h, timeout=30)
    assert r.status_code == 200, r.text
    body = r.json()
    data_container = body.get("data") if "data" in body else body
    # data may be None (no schedule); other keys sit at top or in body
    assert data_container is None or data_container == {} or "schedule" in data_container or body.get("data") is None
    matching = body.get("matching_templates") or (data_container or {}).get("matching_templates")
    buildable = body.get("buildable") if "buildable" in body else (data_container or {}).get("buildable")
    assert buildable is True, f"buildable expected True, body={body}"
    assert matching, f"matching_templates empty, body={body}"


def test_unit_bundle_kavling_not_buildable(h, unscheduled_tipe):
    u = unscheduled_tipe["kavling"]
    if not u:
        pytest.skip("no kavling unit")
    r = requests.get(f"{BASE}/build/unit/{u['id']}", headers=h, timeout=30)
    assert r.status_code == 200
    body = r.json()
    buildable = body.get("buildable")
    if buildable is None:
        buildable = (body.get("data") or {}).get("buildable")
    assert buildable is False, f"kavling buildable={buildable}, body={body}"


def test_create_schedule_auto_template(h, unscheduled_tipe):
    # find a fresh unscheduled Tipe unit each run
    r = requests.get(f"{BASE}/build/unscheduled", headers=h, timeout=30)
    items = r.json().get("data") if isinstance(r.json(), dict) else r.json()
    u = next((x for x in items if "tipe" in (x.get("type") or "").lower()), None)
    if not u:
        pytest.skip("no unscheduled Tipe unit")
    payload = {"unit_id": u["id"], "start_date": "2026-02-01"}
    r = requests.post(f"{BASE}/build/schedules", json=payload, headers=h, timeout=60)
    assert r.status_code in (200, 201), r.text
    body = r.json()
    data = body.get("data") if isinstance(body, dict) and "data" in body else body
    tc = data.get("template_code") or data.get("template_name") or ""
    assert "RUMAH" in tc.upper() or "9W" in tc.upper(), f"template mismatch: {data}"


# ---------- BUG3: Custom roles ----------
def test_custom_role_lifecycle(h):
    # clean up if exists
    requests.delete(f"{BASE}/admin/roles/qa_api_role", headers=h, timeout=15)

    r = requests.post(f"{BASE}/admin/roles",
                      json={"code": "qa_api_role", "label": "QA API Role", "inherits": "sales", "scope": "own"},
                      headers=h, timeout=30)
    assert r.status_code in (200, 201), r.text

    r = requests.put(f"{BASE}/admin/roles/qa_api_role", json={"scope": "project"}, headers=h, timeout=30)
    assert r.status_code == 200, r.text
    body = r.json()
    data = body.get("data") if isinstance(body, dict) and "data" in body else body
    assert data.get("scope") == "project", data

    r = requests.get(f"{BASE}/reference/user_role", headers=h, timeout=30)
    assert r.status_code == 200
    body = r.json()
    data = body.get("data") if isinstance(body, dict) else body
    opts = data.get("options") if isinstance(data, dict) and "options" in data else data
    values = [o.get("value") for o in opts]
    labels = {o.get("value"): o.get("label") for o in opts}
    assert "qa_api_role" in values, f"values: {values}"
    assert labels.get("qa_api_role") == "QA API Role"

    r = requests.delete(f"{BASE}/admin/roles/qa_api_role", headers=h, timeout=30)
    assert r.status_code == 200, r.text
