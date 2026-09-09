"""Fase 74 — palet warna per organisasi + dua status paralel (penjualan & pembangunan).

Cakupan:
  • GET/PUT /api/site-plan-studio/palette (validasi #rrggbb, grup tak dikenal dibuang, reset)
  • Route ordering: /palette tidak tertangkap /{project_id}
  • GET /api/site-plan-studio/{pid} memuat 'palette' & units punya 'construction_progress'
  • RBAC: sales (hanya view) tidak boleh PUT palette
"""
import os

import pytest
import requests

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or "").rstrip("/")
if not BASE_URL:
    from dotenv import dotenv_values
    BASE_URL = (dotenv_values("/app/frontend/.env").get("REACT_APP_BACKEND_URL") or "").rstrip("/")
PID = None  # diselesaikan dari API: proyek demo yang memiliki unit
PALETTE_URL = f"{BASE_URL}/api/site-plan-studio/palette"


def _login(email, password="Sipro#2026"):
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password}, timeout=30)
    if r.status_code != 200:
        pytest.fail(f"login {email} gagal: {r.status_code} {r.text[:300]}")
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {r.json()['access_token']}"})
    return s


@pytest.fixture(scope="module")
def owner():
    s = _login("owner@sipro.co.id")
    global PID
    units = s.get(f"{BASE_URL}/api/units", params={"limit": 500}, timeout=30).json().get("data") or []
    if not units:
        pytest.skip("tidak ada unit/proyek demo")
    from collections import Counter
    PID = Counter(u["project_id"] for u in units).most_common(1)[0][0]
    return s


@pytest.fixture(scope="module")
def sales():
    return _login("sales@sipro.co.id")


@pytest.fixture(scope="module", autouse=True)
def restore_palette(owner):
    yield
    r = owner.put(PALETTE_URL, json={"palette": {}}, timeout=30)
    assert r.status_code == 200 and r.json()["data"] == {}


# ---------------------------------------------------------------- palette GET/PUT
def test_palette_get_default_shape(owner):
    r = owner.get(PALETTE_URL, timeout=30)
    assert r.status_code == 200, r.text
    assert isinstance(r.json()["data"], dict)


def test_palette_put_validation_and_persistence(owner):
    payload = {"palette": {
        "sales": {"booked": {"fill": "#ffd6a5", "stroke": "not-a-color", "text": "#7c2d12",
                             "label": "  Booking Fee  ", "bogus": "#123456"}},
        "build": {"b100": {"fill": "#ABCDEF"}},
        "mapping": {"mapped": {"fill": "#00ff00"}},
        "unknown_group": {"x": {"fill": "#000000"}},
        "sales_bad": "string-instead-of-dict",
    }}
    r = owner.put(PALETTE_URL, json=payload, timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["sales"]["booked"]["fill"] == "#ffd6a5"
    assert "stroke" not in d["sales"]["booked"], "warna tak sah harus dibuang"
    assert d["sales"]["booked"]["text"] == "#7c2d12"
    assert d["sales"]["booked"]["label"] == "Booking Fee", "label harus di-trim"
    assert "bogus" not in d["sales"]["booked"]
    assert d["build"]["b100"]["fill"] == "#ABCDEF"
    assert d["mapping"]["mapped"]["fill"] == "#00ff00"
    assert "unknown_group" not in d and "sales_bad" not in d

    # GET → persistensi
    got = owner.get(PALETTE_URL, timeout=30).json()["data"]
    assert got == d


def test_studio_payload_has_palette_and_progress(owner):
    r = owner.get(f"{BASE_URL}/api/site-plan-studio/{PID}", timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert "palette" in data and isinstance(data["palette"], dict)
    units = data["units"]
    assert len(units) >= 11, f"seed diharapkan >= 11 unit, dapat {len(units)}"
    assert all("_id" not in u for u in units)
    assert any("construction_progress" in u for u in units)
    booked = [u for u in units if u.get("status") == "booked"]
    assert booked, "seed harus punya unit booked (A-01/A-02)"
    progresses = {u["code"]: u.get("construction_progress") for u in units}
    assert progresses.get("A-01") == 33, progresses
    assert progresses.get("A-02") == 10, progresses


def test_palette_reset_empty(owner):
    owner.put(PALETTE_URL, json={"palette": {"sales": {"booked": {"fill": "#ffd6a5"}}}}, timeout=30)
    r = owner.put(PALETTE_URL, json={"palette": {}}, timeout=30)
    assert r.status_code == 200 and r.json()["data"] == {}
    assert owner.get(PALETTE_URL, timeout=30).json()["data"] == {}
    # payload studio ikut kembali kosong
    data = owner.get(f"{BASE_URL}/api/site-plan-studio/{PID}", timeout=30).json()["data"]
    assert data["palette"] == {}


def test_palette_missing_body_rejected(owner):
    r = owner.put(PALETTE_URL, json={}, timeout=30)
    assert r.status_code in (400, 422), r.text
    assert "palette" in r.text


# ---------------------------------------------------------------- RBAC
def test_sales_can_read_but_not_write_palette(sales):
    r = sales.get(PALETTE_URL, timeout=30)
    assert r.status_code == 200, r.text
    w = sales.put(PALETTE_URL, json={"palette": {"sales": {"booked": {"fill": "#111111"}}}}, timeout=30)
    assert w.status_code == 403, f"sales harus dilarang menulis palet, dapat {w.status_code}"


def test_unauthenticated_palette_blocked():
    r = requests.get(PALETTE_URL, timeout=30)
    assert r.status_code in (401, 403), r.status_code
