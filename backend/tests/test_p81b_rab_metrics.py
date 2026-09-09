"""Fase 81b — metrik RAB terstruktur (RAB-01..06) di BI: angka = Ringkasan & HPP, kendali fasum, override SPK, revisi versi."""
import os

import pytest
import requests
from dotenv import dotenv_values

BASE = (os.environ.get("REACT_APP_BACKEND_URL") or dotenv_values("/app/frontend/.env").get("REACT_APP_BACKEND_URL")).rstrip("/") + "/api"


@pytest.fixture(scope="module")
def su():
    s = requests.Session()
    r = s.post(f"{BASE}/auth/login", json={"email": "superadmin@sipro.co.id", "password": "Sipro#2026"})
    assert r.status_code == 200, r.text[:200]
    return s


def _metric(su, code, **params):
    r = su.get(f"{BASE}/analytics/metric/{code}", params={"period": "all", **params})
    assert r.status_code == 200, r.text[:200]
    return r.json()["data"]


def test_catalog_and_dashboards_include_rab(su):
    cat = su.get(f"{BASE}/analytics/metrics").json()
    codes = {m["code"] for m in cat["data"]}
    assert {"RAB-01", "RAB-02", "RAB-03", "RAB-04", "RAB-05", "RAB-06"} <= codes
    assert {"RAB-02", "RAB-03"} <= set(cat["dashboards"]["eksekutif"])
    assert {"RAB-01", "RAB-04", "RAB-05", "RAB-06"} <= set(cat["dashboards"]["proyek"])
    assert "RAB-01" in cat["snapshot_codes"] and "RAB-06" not in cat["snapshot_codes"]
    for m in cat["data"]:
        if m["code"].startswith("RAB-"):
            assert m["drill"] and m["formula"] and m["requires"]


def test_rab_total_and_margin_match_summary(su):
    proj = su.get(f"{BASE}/projects", params={"limit": 1}).json()["data"][0]
    summ = su.get(f"{BASE}/rab/projects/{proj['id']}/summary").json()["data"]
    m1 = _metric(su, "RAB-01", project_id=proj["id"])
    assert m1["value"] == summ["total_rab"] and m1["unit"] == "idr"
    comp = {b["key"]: b["value"] for b in m1["breakdown"]}
    assert comp.get("unit_rab", 0) == summ["unit_rab"] and comp.get("fasum", 0) == summ["fasum"]
    if summ["units_without_template"]:
        assert m1["state"] == "sebagian" and m1["coverage"]["total"] == summ["units"]
    m2 = _metric(su, "RAB-02", project_id=proj["id"])
    assert m2["value"] == summ["margin"] and m2["breakdown"][0]["pct"] == summ["margin_pct"]
    m3 = _metric(su, "RAB-03", project_id=proj["id"])
    assert m3["unit"] == "pct" and len(m3["breakdown"]) == len(summ["per_type"])
    # BGT-06 kini memakai RAB terstruktur yang sama
    bgt = _metric(su, "BGT-06", project_id=proj["id"])
    assert bgt["breakdown"][0]["rab_total"] == summ["total_rab"]


def test_fasum_control_metric(su):
    proj = su.get(f"{BASE}/projects", params={"limit": 1}).json()["data"][0]
    rows = su.get(f"{BASE}/rab/projects/{proj['id']}/summary").json()["data"]["fasum_control"]
    m = _metric(su, "RAB-04", project_id=proj["id"])
    if not rows:
        assert m["value"] is None and m["state"] == "kosong"
        return
    assert m["value"] == sum(1 for r in rows if r["over"]) and m["inputs"]["spk_fasum"] == len(rows)
    by = {b["key"]: b for b in m["breakdown"]}
    for r in rows:
        assert by[r["spk_id"]]["value"] == r["billed_pct"] and by[r["spk_id"]]["over"] == r["over"]
    assert m["drill"] == "/subcon"


def test_spk_override_and_revisions(su):
    m5 = _metric(su, "RAB-05")
    if m5["value"] is not None:
        assert m5["value"] == m5["inputs"]["nilai_kontrak"] - m5["inputs"]["dasar_rab"]
        assert all("override_count" in b for b in m5["breakdown"])
    m6 = _metric(su, "RAB-06")
    vs = su.get(f"{BASE}/rab/templates/unit_type/TIPE-36-72/versions").json()["data"]["versions"]
    old = [v for v in vs if not v["current"]]
    if old:
        assert m6["value"] >= len(old) and m6["unit"] == "count"
        row = next(b for b in m6["breakdown"] if b["key"] == "unit_type:TIPE-36-72")
        assert row["value"] >= len(old) and "delta" in row and m6["series"]
    narrow = _metric(su, "RAB-06", date_from="2000-01-01", date_to="2000-01-02")
    assert narrow["value"] == 0 or narrow["value"] is None
