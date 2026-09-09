"""Audit Tahap 5 (DOC-02, CFG-03/04, UI-02) + WA-09 kode eksplisit — 2026-09-06. Server hidup."""
import uuid

import pytest

from conftest import BASE_URL, _login, _sess


@pytest.fixture(scope="module")
def s():
    return _sess(_login("superadmin@sipro.co.id"))


def _api(s, method, path, **kw):
    return getattr(s, method)(f"{BASE_URL}/api{path}", timeout=30, **kw)


def test_doc02_invoice_has_own_layout_target(s):
    r = _api(s, "get", "/doc-layouts")
    assert r.status_code == 200
    inv = [x for x in r.json()["data"] if x["code"] == "INVOICE"]
    assert inv and inv[0]["kind"] == "table" and inv[0]["category"] == "penagihan"
    p = _api(s, "post", "/doc-layouts/INVOICE/preview", json={})
    assert p.status_code == 200 and p.headers["content-type"].startswith("application/pdf")


def test_cfg03_enum_settings_carry_ref_group_and_labels(s):
    r = _api(s, "get", "/settings")
    assert r.status_code == 200
    enums = [x for x in r.json()["data"] if x["type"] == "enum"]
    assert enums
    for row in enums:
        assert row.get("ref_group"), row["key"]
        assert row["options"], row["key"]
        labels = row.get("option_labels") or {}
        for o in row["options"]:
            assert labels.get(o) and labels[o] != o, (row["key"], o)


def test_cfg04_reference_has_new_groups(s):
    r = _api(s, "get", "/reference")
    assert r.status_code == 200
    reg = r.json().get("data", r.json())
    for g in ("lead_won_trigger", "slik_gate", "attribution_model", "docnum_scope",
              "docnum_reset_policy", "deletion_request_status"):
        assert g in reg and reg[g]["options"], g


def test_wa09_explicit_code_respected(s):
    code = f"tst_t5_{uuid.uuid4().hex[:6]}"
    body = {"code": code, "name": "Uji Kode Eksplisit", "category": "utility",
            "body": "Halo {{nama}}", "variables": ["nama"], "examples": {"nama": "Budi"}}
    r = _api(s, "post", "/wa-templates", json=body)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["code"] == code
    _api(s, "delete", f"/wa-templates/{r.json()['data']['id']}")
