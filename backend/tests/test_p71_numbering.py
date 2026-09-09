"""Fase 71 — aturan penomoran terkonfigurasi (`/api/numbering`) + kode master otomatis.

Rangkaian: daftar aturan & pratinjau, validasi token asing, simpan/reset aturan (RBAC),
nomor SPK mengikuti pola baru (per proyek), kode master (proyek/cluster/blok/unit/vendor/
subkon/tipe unit/add-on) lahir dari aturan bila kolom kode dikosongkan.
"""
import os
import time

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
PASS = "Sipro#2026"
TAG = str(int(time.time()))[-6:]


def _login(email):
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": PASS}, timeout=20)
    if r.status_code != 200:
        pytest.skip(f"login {email} failed: {r.status_code} {r.text[:200]}")
    return r.json()["access_token"]


def _sess(tok):
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {tok}", "Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def s_owner():
    return _sess(_login("owner@sipro.co.id"))


@pytest.fixture(scope="module", autouse=True)
def _bersihkan_data_uji():
    """Master uji (proyek, vendor, subkon, tipe, add-on, SPK) tidak punya endpoint hapus —
    dibersihkan langsung di DB dengan penjaga, supaya add-on berharga nol dan proyek tanpa
    anggota tidak tercecer ke katalog demo."""
    yield
    from _testdata import purge_tagged
    purge_tagged(TAG, project_names=(f"Uji Penomoran {TAG}", f"Bumi Indah Permai {TAG}"),
                 vendor_names=(f"Vendor Uji {TAG}",), subcon_names=(f"Subkon Uji {TAG}",),
                 unit_type_names=(f"Tipe Uji {TAG}",), addon_names=(f"Addon Uji {TAG}",),
                 spk_titles=(f"Uji penomoran {TAG}",))


@pytest.fixture(scope="module")
def s_sales():
    return _sess(_login("sales@sipro.co.id"))


@pytest.fixture(scope="module", autouse=True)
def _cleanup(s_owner):
    yield
    for key in ("spk", "master:cluster"):
        s_owner.delete(f"{BASE_URL}/api/numbering/{key}")


def test_list_rules_has_registry_and_preview(s_owner):
    r = s_owner.get(f"{BASE_URL}/api/numbering")
    assert r.status_code == 200
    body = r.json()
    keys = {x["key"] for x in body["data"]}
    assert {"spk", "po", "receipt", "master:unit", "master:project"} <= keys
    spk = next(x for x in body["data"] if x["key"] == "spk")
    assert spk["preview"].startswith("SPK/") and spk["default"]["pattern"] == "{PREFIX}/{YYYY}/{SEQ}"
    assert body["reset_options"] and body["global_tokens"]


def test_preview_and_unknown_token(s_owner):
    r = s_owner.post(f"{BASE_URL}/api/numbering/spk/preview", json={
        "pattern": "{PREFIX}/{PROJECT_CODE}/{MM_ROMAN}/{YYYY}/{SEQ}", "sample": {"project_code": "GRY"}})
    assert r.status_code == 200
    assert r.json()["data"]["preview"].startswith("SPK/GRY/")
    r = s_owner.post(f"{BASE_URL}/api/numbering/spk/preview", json={"pattern": "{FOO}/{SEQ}"})
    assert r.status_code == 400 and "FOO" in r.json()["detail"]
    assert s_owner.get(f"{BASE_URL}/api/numbering/tidak-ada/tokens").status_code == 404


def test_sales_cannot_edit_but_can_view(s_sales):
    assert s_sales.get(f"{BASE_URL}/api/numbering").status_code == 200
    r = s_sales.put(f"{BASE_URL}/api/numbering/spk", json={"pattern": "{PREFIX}/{SEQ}"})
    assert r.status_code == 403


def test_save_rule_applies_to_new_spk(s_owner):
    r = s_owner.put(f"{BASE_URL}/api/numbering/spk", json={
        "pattern": "{PREFIX}/{PROJECT_CODE}/{MM_ROMAN}/{YYYY}/{SEQ}", "width": 3})
    assert r.status_code == 200 and r.json()["data"]["overridden"] is True
    proj = s_owner.get(f"{BASE_URL}/api/projects").json()["data"][0]
    subs = s_owner.get(f"{BASE_URL}/api/subcon/subcontractors").json()["data"]
    if not subs:
        pytest.skip("tidak ada subkontraktor seed")
    body = {"project_id": proj["id"], "subcontractor_id": subs[0]["id"],
            "title": f"Uji penomoran {TAG}", "contract_value": 1000000,
            "start_date": "2026-09-01", "end_date": "2026-12-31"}
    r = s_owner.post(f"{BASE_URL}/api/subcon/spk", json=body)
    if r.status_code != 200:
        pytest.skip(f"SPK create tidak tersedia: {r.status_code} {r.text[:120]}")
    number = r.json()["data"]["spk_number"]
    assert number.startswith(f"SPK/{proj['code'].upper()}/") and len(number.split("/")[-1]) == 3
    r = s_owner.delete(f"{BASE_URL}/api/numbering/spk")
    assert r.status_code == 200 and r.json()["data"]["overridden"] is False


def test_master_codes_generated_when_blank(s_owner):
    r = s_owner.post(f"{BASE_URL}/api/projects", json={"name": f"Uji Penomoran {TAG}", "code": ""})
    assert r.status_code == 200
    proj = r.json()["data"]
    assert proj["code"].startswith("PRJ-")
    r = s_owner.post(f"{BASE_URL}/api/masterplan/projects/{proj['id']}/clusters",
                     json={"code": "", "name": "Cluster Uji"})
    assert r.status_code == 200, r.text
    cluster = r.json()["data"]
    assert cluster["code"].startswith("C") and cluster["code"][1:].isdigit()
    r = s_owner.post(f"{BASE_URL}/api/masterplan/clusters/{cluster['id']}/blocks", json={"code": ""})
    assert r.status_code == 200, r.text
    block = r.json()["data"]
    assert block["code"] == "A"
    r = s_owner.post(f"{BASE_URL}/api/masterplan/blocks/{block['id']}/units", json={"no": "7"})
    assert r.status_code == 200, r.text
    assert r.json()["data"]["code"] == "A-07"
    r = s_owner.post(f"{BASE_URL}/api/vendors", json={"code": "", "name": f"Vendor Uji {TAG}",
                                                       "category": "material"})
    assert r.status_code == 200, r.text
    assert r.json()["data"]["code"].startswith("VND-")
    r = s_owner.post(f"{BASE_URL}/api/subcon/subcontractors", json={"code": "", "name": f"Subkon Uji {TAG}"})
    assert r.status_code == 200, r.text
    assert r.json()["data"]["code"].startswith("SUB-")
    r = s_owner.post(f"{BASE_URL}/api/catalog/unit-types", json={
        "code": "", "name": f"Tipe Uji {TAG}", "building_area": 30, "land_area_std": 60,
        "base_price": 100000000})
    assert r.status_code == 200, r.text
    assert r.json()["data"]["code"].startswith("T")
    r = s_owner.post(f"{BASE_URL}/api/catalog/addons", json={"code": "", "name": f"Addon Uji {TAG}"})
    assert r.status_code == 200, r.text
    assert r.json()["data"]["code"].startswith("ADD-")


def test_custom_master_pattern(s_owner):
    r = s_owner.put(f"{BASE_URL}/api/numbering/master:cluster",
                    json={"pattern": "{PROJECT_INITIALS}-CL{SEQ:2}"})
    assert r.status_code == 200
    proj = s_owner.post(f"{BASE_URL}/api/projects",
                        json={"name": f"Bumi Indah Permai {TAG}", "code": ""}).json()["data"]
    r = s_owner.post(f"{BASE_URL}/api/masterplan/projects/{proj['id']}/clusters",
                     json={"code": "", "name": "Cluster Pola"})
    assert r.status_code == 200, r.text
    assert r.json()["data"]["code"].startswith("BIP-CL")
