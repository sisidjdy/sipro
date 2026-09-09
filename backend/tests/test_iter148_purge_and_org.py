"""Iteration 148 — Bulk purge (Hapus Massal) + organization rename tests."""
import os
import time
import pytest
import requests

# DESTRUKTIF: menghapus seluruh data demo dan MEMATIKAN seed ulang (`demo_seed_disabled`).
# Hanya dijalankan bila diminta eksplisit — bila ikut suite biasa, semua gate & tes lain
# kehilangan datanya (terjadi 2026-09-06: units = 0 sesudah suite penuh).
if os.environ.get("SIPRO_ALLOW_PURGE_TEST") != "1":
    pytest.skip("Tes purge destruktif — set SIPRO_ALLOW_PURGE_TEST=1 lalu jalankan scripts/seed_reset.sh sesudahnya",
                allow_module_level=True)

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
API = f"{BASE_URL}/api"

EMAIL = "superadmin@sipro.co.id"
PASSWORD = "Sipro#2026"

session = requests.Session()


def _login():
    r = session.post(f"{API}/auth/login", json={"email": EMAIL, "password": PASSWORD}, timeout=30)
    assert r.status_code == 200, f"login failed {r.status_code}: {r.text}"
    tok = r.json().get("access_token")
    assert tok
    session.headers.update({"Authorization": f"Bearer {tok}"})
    return r.json()


def test_00_health():
    r = requests.get(f"{API}/health", timeout=10)
    assert r.status_code == 200


def test_01_login():
    data = _login()
    u = data.get("user") or data.get("data") or {}
    assert u.get("email") == EMAIL
    assert u.get("active_org", {}).get("name") == "Harmony Land 5"


# --- Organization rename ---
def test_10_org_list_and_rename():
    _login()
    r = session.get(f"{API}/admin/orgs", timeout=15)
    assert r.status_code == 200
    orgs = r.json()["data"]
    assert orgs, "no orgs"
    target = next((o for o in orgs if o["id"] == "org-sipro"), orgs[0])
    org_id = target["id"]
    original = target["name"]
    # rename
    r = session.put(f"{API}/admin/orgs/{org_id}", json={"name": "Harmony Land 5 Test"}, timeout=15)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["name"] == "Harmony Land 5 Test"
    # verify via list
    r = session.get(f"{API}/admin/orgs", timeout=15)
    got = [o for o in r.json()["data"] if o["id"] == org_id][0]
    assert got["name"] == "Harmony Land 5 Test"
    # restore back
    r = session.put(f"{API}/admin/orgs/{org_id}", json={"name": "Harmony Land 5"}, timeout=15)
    assert r.status_code == 200
    assert r.json()["data"]["name"] == "Harmony Land 5"


# --- Purge preview & validation errors ---
def test_20_purge_preview_shape():
    _login()
    r = session.get(f"{API}/data-mgmt/purge/preview", timeout=20)
    assert r.status_code == 200, r.text
    body = r.json()
    for g in ("transaksi", "proyek", "mitra"):
        assert g in body["groups"]
        assert "total" in body["groups"][g]
    assert "keep" in body
    assert "demo_seed_disabled" in body


def test_21_purge_bad_confirm():
    _login()
    r = session.post(f"{API}/data-mgmt/purge",
                     json={"groups": ["transaksi"], "confirm": "no", "snapshot": False}, timeout=20)
    assert r.status_code == 400


def test_22_purge_unknown_group():
    _login()
    r = session.post(f"{API}/data-mgmt/purge",
                     json={"groups": ["foobar"], "confirm": "HAPUS", "snapshot": False}, timeout=20)
    assert r.status_code == 400


# --- Full purge flow ---
def test_30_full_purge():
    _login()
    pre = session.get(f"{API}/data-mgmt/purge/preview", timeout=20).json()
    print("pre totals:", {k: v["total"] for k, v in pre["groups"].items()})
    r = session.post(f"{API}/data-mgmt/purge", json={
        "groups": ["transaksi", "proyek", "mitra"],
        "confirm": "HAPUS", "snapshot": True}, timeout=120)
    assert r.status_code == 200, r.text
    res = r.json()
    assert res["demo_seed_disabled"] is True
    assert res["deleted"] >= 0
    assert res.get("snapshot_before"), "expected snapshot metadata"
    print("deleted:", res["deleted"], "snapshot:", res["snapshot_before"].get("filename"))

    # verify preview totals now near zero — audit_logs (from this purge action itself) and
    # auto-bootstrapped bank_accounts (Kas Besar / Rekening Operasional) are expected leftovers.
    post = session.get(f"{API}/data-mgmt/purge/preview", timeout=20).json()
    for g, gv in post["groups"].items():
        for row in gv["rows"]:
            assert row["collection"] in ("audit_logs", "bank_accounts"), (
                f"unexpected leftover in {g}: {row}")
    assert post["demo_seed_disabled"] is True

    # collections empty
    for path in ("/leads", "/deals", "/projects"):
        r = session.get(f"{API}{path}", timeout=20)
        assert r.status_code == 200, f"{path} {r.status_code} {r.text[:200]}"
        data = r.json()
        rows = data.get("data", data) if isinstance(data, dict) else data
        # rows could be list or dict wrapper
        if isinstance(rows, list):
            assert len(rows) == 0, f"{path} still has {len(rows)} rows"

    # configuration intact
    r = session.get(f"{API}/admin/users", timeout=15)
    assert r.status_code == 200
    users = r.json().get("data", r.json())
    if isinstance(users, dict):
        users = users.get("users", [])
    emails = [u.get("email") for u in users]
    assert EMAIL in emails, f"superadmin missing after purge: {emails}"

    # accounts endpoint (COA) still returns data
    r = session.get(f"{API}/gl/accounts", timeout=15)
    assert r.status_code == 200
    accts = r.json()
    accts_list = accts.get("data", accts) if isinstance(accts, dict) else accts
    assert isinstance(accts_list, list) and len(accts_list) > 0, "COA should be intact"

    # snapshot present in list
    r = session.get(f"{API}/data-mgmt/snapshots", timeout=15)
    assert r.status_code == 200
    snaps = r.json()
    snaps_list = snaps.get("data", snaps) if isinstance(snaps, dict) else snaps
    assert isinstance(snaps_list, list) and len(snaps_list) >= 1


# --- Restart & verify seed does not repopulate ---
def test_40_restart_and_no_reseed():
    _login()
    import subprocess
    subprocess.run(["sudo", "supervisorctl", "restart", "backend"], check=False)
    # wait for health
    ok = False
    for _ in range(60):
        try:
            r = requests.get(f"{API}/health", timeout=5)
            if r.status_code == 200:
                ok = True
                break
        except Exception:
            pass
        time.sleep(1)
    assert ok, "backend did not come back up"
    _login()
    r = session.get(f"{API}/data-mgmt/purge/preview", timeout=20)
    assert r.status_code == 200
    body = r.json()
    for g, gv in body["groups"].items():
        for row in gv["rows"]:
            assert row["collection"] in ("audit_logs", "bank_accounts"), (
                f"reseed happened, {g} has {row}")
    assert body["demo_seed_disabled"] is True
    # backend log message
    try:
        with open("/var/log/supervisor/backend.err.log", "r") as f:
            content = f.read()[-20000:]
        assert "Seed demo dilewati" in content, "expected 'Seed demo dilewati' in backend log"
    except FileNotFoundError:
        pass


def test_41_pages_load_after_purge():
    _login()
    for path in ("/leads", "/deals", "/projects", "/cash-bank/accounts"):
        r = session.get(f"{API}{path}", timeout=15)
        assert r.status_code in (200, 404), f"{path} => {r.status_code} {r.text[:200]}"
