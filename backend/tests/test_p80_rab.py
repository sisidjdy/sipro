"""Fase 80 — RAB terstruktur & SPK dari RAB (API)."""
import os

import pytest
import requests
from dotenv import dotenv_values

BASE = (os.environ.get("REACT_APP_BACKEND_URL") or dotenv_values("/app/frontend/.env").get("REACT_APP_BACKEND_URL")).rstrip("/") + "/api"
PWD = "Sipro#2026"


@pytest.fixture(scope="module")
def su():
    s = requests.Session()
    r = s.post(f"{BASE}/auth/login", json={"email": "superadmin@sipro.co.id", "password": PWD})
    assert r.status_code == 200, r.text[:200]
    return s


@pytest.fixture(scope="module")
def ctx(su):
    # Cari unit tipe uji di seluruh proyek: fixture lain bisa membuat proyek kosong yang
    # muncul lebih dulu di daftar, jadi "proyek pertama" bukan acuan yang stabil.
    units = su.get(f"{BASE}/units", params={"limit": 500}).json()["data"]
    unit = next((u for u in units if u.get("unit_type_code") == "TIPE-45-90"), None)
    if not unit:
        pytest.skip("tidak ada unit TIPE-45-90 di lingkungan ini")
    steps = su.get(f"{BASE}/build/templates").json()["data"][0]["steps"]
    return {"pid": unit["project_id"], "unit": unit, "step": steps[0]["code"]}


def test_save_type_template_and_margin(su, ctx):
    items = [{"code": "STR", "description": "TEST_Struktur & pondasi", "category": "struktur", "uom": "unit", "qty": 1, "unit_price": 150_000_000, "step_code": ctx["step"]},
             {"code": "ARS", "description": "TEST_Arsitektur & finishing", "category": "finishing", "uom": "m2", "qty": 45, "unit_price": 2_000_000}]
    r = su.put(f"{BASE}/rab/templates/unit_type/TIPE-45-90", json={"items": items})
    assert r.status_code == 200, r.text[:200]
    assert r.json()["data"]["total"] == 240_000_000
    row = next(x for x in su.get(f"{BASE}/rab/templates/unit_type").json()["data"] if x["ref_code"] == "TIPE-45-90")
    assert row["total"] == 240_000_000 and row["margin"] == row["base_price"] - 240_000_000
    r = su.put(f"{BASE}/rab/templates/unit_type/TIPE-XXX", json={"items": items})
    assert r.status_code == 400
    r = su.put(f"{BASE}/rab/templates/unit_type/TIPE-45-90", json={"items": [{"qty": 1, "unit_price": 5}]})
    assert r.status_code == 400 and "uraian" in r.text.lower()


def test_save_addon_template(su, ctx):
    r = su.put(f"{BASE}/rab/templates/addon/ADD-KANOPI", json={"items": [{"description": "TEST_Rangka + atap kanopi", "qty": 1, "unit_price": 8_000_000}]})
    assert r.status_code == 200 and r.json()["data"]["total"] == 8_000_000


def test_fasum_item_requires_facility_and_summary(su, ctx):
    r = su.post(f"{BASE}/boq/items", json={"project_id": ctx["pid"], "description": "TEST_Jalan paving", "category": "infrastruktur",
                                            "uom": "m2", "quantity": 100, "unit_price": 250_000, "scope": "fasum"})
    assert r.status_code == 400 and "fasilitas" in r.text.lower()
    r = su.post(f"{BASE}/boq/items", json={"project_id": ctx["pid"], "cost_code": f"FAS-{int(__import__('time').time()) % 100000}", "description": "TEST_Jalan paving", "category": "infrastruktur",
                                            "uom": "m2", "quantity": 100, "unit_price": 250_000, "scope": "fasum", "facility": "jalan"})
    assert r.status_code == 200, r.text[:200]
    fid = r.json()["data"]["id"]
    r = su.post(f"{BASE}/boq/items", json={"project_id": ctx["pid"], "description": "TEST_IMB & perizinan", "category": "lainnya",
                                            "uom": "unit", "quantity": 1, "unit_price": 50_000_000, "scope": "umum", "facility": "perizinan"})
    assert r.status_code == 200
    rows = su.get(f"{BASE}/boq/items", params={"project_id": ctx["pid"], "scope": "fasum"}).json()["data"]
    assert any(x["id"] == fid for x in rows) and all(x.get("scope") == "fasum" for x in rows)
    s = su.get(f"{BASE}/rab/projects/{ctx['pid']}/summary").json()["data"]
    assert s["fasum"] >= 25_000_000 and s["umum"] >= 50_000_000
    t = next(x for x in s["per_type"] if x["unit_type_code"] == "TIPE-45-90")
    assert t["rab_per_unit"] == 240_000_000 and t["rab_total"] == 240_000_000 * t["units"]
    assert s["total_rab"] == s["unit_rab"] + s["addon_rab"] + s["shared"]
    u = next(x for x in s["per_unit"] if x["unit_id"] == ctx["unit"]["id"])
    assert u["hpp"] == u["rab_type"] + u["shared"] and u["margin"] == u["price"] - u["hpp"]
    assert abs(sum(x["shared"] for x in s["per_unit"]) - s["shared"]) <= len(s["per_unit"])
    r = su.put(f"{BASE}/rab/projects/{ctx['pid']}/allocation", json={"method": "rata"})
    assert r.status_code == 200
    s2 = su.get(f"{BASE}/rab/projects/{ctx['pid']}/summary").json()["data"]
    assert s2["allocation"] == "rata"
    shares = {x["shared"] for x in s2["per_unit"]}
    assert max(shares) - min(shares) <= 1
    assert su.put(f"{BASE}/rab/projects/{ctx['pid']}/allocation", json={"method": "ngawur"}).status_code == 400
    su.put(f"{BASE}/rab/projects/{ctx['pid']}/allocation", json={"method": "luas_tanah"})


def test_spk_from_rab_unit_with_override(su, ctx):
    sub = su.get(f"{BASE}/subcon/subcontractors", params={"active": "true"}).json()["data"][0]
    d = su.post(f"{BASE}/rab/spk-draft", json={"project_id": ctx["pid"], "mode": "unit", "unit_ids": [ctx["unit"]["id"]]}).json()["data"]
    lines = d["units"][0]["lines"]
    assert len(lines) == 2 and d["total"] == 240_000_000
    lines[1] = {**lines[1], "value": 80_000_000}
    r = su.post(f"{BASE}/subcon/spk/from-rab", json={"subcontractor_id": sub["id"], "project_id": ctx["pid"], "title": "TEST_SPK unit dari RAB",
                                                      "spk_kind": "unit", "unit_ids": [ctx["unit"]["id"]], "lines": lines})
    assert r.status_code == 400 and "alasan" in r.text.lower()
    lines[1]["override_reason"] = "Harga borongan nego turun"
    r = su.post(f"{BASE}/subcon/spk/from-rab", json={"subcontractor_id": sub["id"], "project_id": ctx["pid"], "title": "TEST_SPK unit dari RAB",
                                                      "spk_kind": "unit", "unit_ids": [ctx["unit"]["id"]], "lines": lines})
    assert r.status_code == 200, r.text[:300]
    spk = r.json()["data"]
    assert spk["contract_value"] == 230_000_000 and spk["rab_total"] == 240_000_000 and spk["override_count"] == 1
    assert spk["spk_kind"] == "unit" and spk["unit_codes"] == [ctx["unit"]["code"]]
    got = su.get(f"{BASE}/subcon/spk/{spk['id']}").json()["data"]
    assert len(got["rab_lines"]) == 2 and got["rab_lines"][1]["override"] is True
    ctrl = next(c for c in su.get(f"{BASE}/rab/projects/{ctx['pid']}/summary").json()["data"]["control"] if c["scope"] == "unit")
    assert ctrl["contracted"] >= 230_000_000 and ctrl["spk"] >= 1


def test_spk_addon_only_draft(su, ctx):
    units = su.get(f"{BASE}/units", params={"project_id": ctx["pid"], "limit": 500}).json()["data"]
    d = su.post(f"{BASE}/rab/spk-draft", json={"project_id": ctx["pid"], "mode": "addon", "unit_ids": [units[0]["id"]]}).json()["data"]
    assert d["mode"] == "addon" and "warnings" in d["units"][0]
    assert all(ln["source"] == "addon" for ln in d["units"][0]["lines"])


def test_spk_from_rab_fasum(su, ctx):
    sub = su.get(f"{BASE}/subcon/subcontractors", params={"active": "true"}).json()["data"][0]
    import time
    new = su.post(f"{BASE}/boq/items", json={"project_id": ctx["pid"], "description": f"TEST_Drainase {int(time.time())}", "category": "infrastruktur",
                                              "uom": "m", "quantity": 10, "unit_price": 1_000_000, "scope": "fasum", "facility": "drainase"}).json()["data"]
    items = [new]
    d = su.post(f"{BASE}/rab/spk-draft", json={"project_id": ctx["pid"], "mode": "fasum", "boq_item_ids": [items[0]["id"]]}).json()["data"]
    assert d["lines"][0]["boq_item_id"] == items[0]["id"] and d["total"] == items[0]["amount"]
    r = su.post(f"{BASE}/subcon/spk/from-rab", json={"subcontractor_id": sub["id"], "project_id": ctx["pid"], "title": "TEST_SPK fasum jalan",
                                                      "spk_kind": "fasum", "lines": d["lines"]})
    assert r.status_code == 200, r.text[:300]
    ctrl = next(c for c in su.get(f"{BASE}/rab/projects/{ctx['pid']}/summary").json()["data"]["control"] if c["scope"] == "fasum")
    assert ctrl["contracted"] >= items[0]["amount"]
    # item RAB yang sama tidak boleh dikontrakkan dua kali
    r = su.post(f"{BASE}/subcon/spk/from-rab", json={"subcontractor_id": sub["id"], "project_id": ctx["pid"], "title": "TEST_SPK fasum ganda",
                                                      "spk_kind": "fasum", "lines": d["lines"]})
    assert r.status_code == 400 and "sudah dikontrakkan" in r.text.lower(), r.text[:200]
