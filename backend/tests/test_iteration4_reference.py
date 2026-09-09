"""Iterasi 4: verifikasi grup registry baru wa_inbound_type & docgen_block."""
import os
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")


def _login():
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": "superadmin@sipro.co.id", "password": "Sipro#2026"},
        timeout=30,
    )
    assert r.status_code == 200, r.text
    j = r.json()
    return j.get("access_token") or j.get("data", {}).get("access_token") or j["data"]["token"]


def test_reference_contains_wa_inbound_type_and_docgen_block():
    token = _login()
    r = requests.get(
        f"{BASE_URL}/api/reference",
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    assert r.status_code == 200, r.text
    payload = r.json()
    data = payload.get("data", payload)
    # groups either dict {group: [options]} or list
    groups = data.get("groups") if isinstance(data, dict) and "groups" in data else data

    assert "wa_inbound_type" in groups, f"missing wa_inbound_type; keys sample={list(groups)[:20]}"
    wa_group = groups["wa_inbound_type"]
    wa_opts = wa_group["options"] if isinstance(wa_group, dict) and "options" in wa_group else wa_group
    # normalize option codes
    codes = set()
    for o in wa_opts:
        if isinstance(o, dict):
            codes.add(o.get("value") or o.get("code") or o.get("key"))
        else:
            codes.add(o)
    for expected in ("text", "image", "document", "location"):
        assert expected in codes, f"wa_inbound_type missing {expected}; got {codes}"

    assert "docgen_block" in groups, "missing docgen_block group"
    dg_group = groups["docgen_block"]
    dg_opts = dg_group["options"] if isinstance(dg_group, dict) and "options" in dg_group else dg_group
    dg_codes = set()
    for o in dg_opts:
        if isinstance(o, dict):
            dg_codes.add(o.get("value") or o.get("code") or o.get("key"))
        else:
            dg_codes.add(o)
    for expected in ("booking_fee_belum", "slik_belum", "demografi_belum_lengkap"):
        assert expected in dg_codes, f"docgen_block missing {expected}; got sample={list(dg_codes)[:20]}"


def test_reference_contains_key_dropdown_groups():
    """Verifikasi grup yang dipakai dropdown baru: po_status, po_type, stock_movement, lead_stage, integration_mode."""
    token = _login()
    r = requests.get(
        f"{BASE_URL}/api/reference",
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    assert r.status_code == 200
    data = r.json().get("data", r.json())
    groups = data.get("groups") if isinstance(data, dict) and "groups" in data else data

    for g in ("po_status", "po_type", "stock_movement", "lead_stage", "integration_mode"):
        assert g in groups, f"grup registry '{g}' hilang"
        opts = groups[g]["options"] if isinstance(groups[g], dict) and "options" in groups[g] else groups[g]
        assert len(opts) > 0, f"grup '{g}' kosong"
