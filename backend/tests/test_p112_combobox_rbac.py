"""P112 — task relations from record pages, refresh list, RBAC matrix + effective perms."""
import copy
import os

import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
base_url = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base_url:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
BASE = base_url.rstrip("/") + "/api"
PW = "Sipro#2026"


def _mongo():
    from pymongo import MongoClient
    env = dotenv_values("/app/backend/.env")
    cli = MongoClient(os.environ.get("MONGO_URL") or env["MONGO_URL"])
    return cli, cli[os.environ.get("DB_NAME") or env["DB_NAME"]]


def purge_test_tasks():
    """API tidak punya DELETE /work/tasks, jadi tugas uji dibersihkan di lapisan DB."""
    cli, dbh = _mongo()
    n = dbh.tasks.delete_many({"title": {"$regex": "^TEST_P112"}}).deleted_count
    cli.close()
    return n


def purge_test_leads():
    """Bersihkan lead uji (prefix TEST_P112) langsung di DB — API tidak punya DELETE lead."""
    cli, dbh = _mongo()
    n = dbh.leads.delete_many({"name": {"$regex": "^TEST_P112"}}).deleted_count
    cli.close()
    return n


def login(email):
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": PW}, timeout=60)
    if r.status_code != 200:
        pytest.fail(f"login {email} -> {r.status_code}: {r.text[:300]}")
    token = r.json().get("access_token") or r.json().get("token")
    if not token:
        pytest.fail(f"no token in login response: {r.text[:300]}")
    return token


@pytest.fixture(scope="module")
def su():
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {login('superadmin@sipro.co.id')}"})
    return s


@pytest.fixture(scope="module")
def created(su):
    ids = []
    yield ids
    purge_test_tasks()


# --- Related record sources used by the combobox ---------------------------------
@pytest.mark.parametrize("path", [
    "/leads?limit=300&sort=created_at&direction=desc", "/deals?limit=200", "/units?limit=500",
    "/customers?limit=300", "/projects?limit=100",
])
def test_related_sources_ok(su, path):
    r = su.get(f"{BASE}{path}", timeout=60)
    assert r.status_code == 200, r.text[:300]
    assert isinstance(r.json().get("data"), list)


# --- Task creation with relation presets (unit/customer/project) -----------------
@pytest.mark.parametrize("kind,listpath", [
    ("unit", "/units?limit=1"), ("customer", "/customers?limit=1"), ("project", "/projects?limit=1"),
])
def test_create_task_with_relation(su, created, kind, listpath):
    rec = su.get(f"{BASE}{listpath}", timeout=60).json()["data"]
    assert rec, f"no seed data for {kind}"
    rid = rec[0]["id"]
    r = su.post(f"{BASE}/work/tasks", json={
        "title": f"TEST_P112 kaitan {kind}", "type": "todo", "priority": "medium",
        "related_entity_type": kind, "related_entity_id": rid,
    }, timeout=60)
    assert r.status_code in (200, 201), r.text[:400]
    tid = r.json()["data"]["id"]
    created.append(tid)
    d = su.get(f"{BASE}/work/tasks/{tid}", timeout=60)
    assert d.status_code == 200, d.text[:300]
    rel = d.json()["data"].get("related")
    assert rel and rel["type"] == kind and rel["id"] == rid, rel
    assert rel.get("label")


def test_create_task_without_relation(su, created):
    r = su.post(f"{BASE}/work/tasks", json={"title": "TEST_P112 tanpa kaitan", "type": "todo"},
                timeout=60)
    assert r.status_code in (200, 201), r.text[:300]
    created.append(r.json()["data"]["id"])


def test_create_task_bad_relation_id_404(su):
    r = su.post(f"{BASE}/work/tasks", json={
        "title": "TEST_P112 palsu", "related_entity_type": "customer",
        "related_entity_id": "does-not-exist-000",
    }, timeout=60)
    assert r.status_code == 404, f"expected 404, got {r.status_code}: {r.text[:300]}"


# --- Refresh list: newly created lead must be returned by list endpoint ----------
def test_new_lead_appears_in_list(su):
    import random
    suffix = random.randint(100000, 999999)
    name = f"TEST_P112_LEAD_{suffix}"
    c = su.post(f"{BASE}/leads", json={"name": name, "phone": f"0811{suffix}99",
                                       "source": "walk_in"}, timeout=60)
    assert c.status_code in (200, 201), c.text[:400]
    lid = c.json()["data"]["id"]
    try:
        lst = su.get(f"{BASE}/leads?limit=300&sort=created_at&direction=desc", timeout=60).json()["data"]
        assert any(x["id"] == lid for x in lst), "lead baru tidak muncul di 300 teratas"
    finally:
        # Tidak ada endpoint DELETE /leads (by design), jadi data uji dibersihkan langsung
        # dari koleksi supaya pipeline demo tidak tercemar prefix TEST_P112.
        purge_test_leads()


# --- RBAC matrix + effective permissions ----------------------------------------
def test_permissions_matrix_shape(su):
    r = su.get(f"{BASE}/admin/permissions", timeout=60)
    assert r.status_code == 200, r.text[:300]
    d = r.json()["data"]
    for k in ("matrix", "effective", "roles", "resources", "actions"):
        assert k in d, k
    assert "leads" in d["resources"]
    sales_eff = d["effective"]["leads"]["sales"]["perms"]
    assert any(a in sales_eff for a in ("view", "view_all", "view_own")), sales_eff


def test_revoke_and_restore_leads_for_sales(su):
    r = su.get(f"{BASE}/admin/permissions", timeout=60).json()["data"]
    original = copy.deepcopy(r["matrix"])
    revoked = copy.deepcopy(original)
    revoked.setdefault("leads", {})["sales"] = []
    try:
        p = su.put(f"{BASE}/admin/permissions", json={"matrix": revoked}, timeout=60)
        assert p.status_code == 200, p.text[:400]
        eff = p.json()["data"]["effective"]["leads"]["sales"]
        assert eff["perms"] == [] and eff["revoked"] is True, eff
        # sales /auth/me must not include leads view
        s = requests.Session()
        s.headers.update({"Authorization": f"Bearer {login('sales@sipro.co.id')}"})
        me = s.get(f"{BASE}/auth/me", timeout=60)
        assert me.status_code == 200, me.text[:300]
        perms = me.json()["data"].get("permissions") or {}
        assert not (perms.get("leads") or []), perms.get("leads")
        assert s.get(f"{BASE}/leads?limit=5", timeout=60).status_code == 403
    finally:
        back = su.put(f"{BASE}/admin/permissions", json={"matrix": original}, timeout=60)
        assert back.status_code == 200, back.text[:300]
    eff2 = su.get(f"{BASE}/admin/permissions", timeout=60).json()["data"]["effective"]["leads"]["sales"]["perms"]
    assert any(a in eff2 for a in ("view", "view_all", "view_own")), eff2
    s2 = requests.Session()
    s2.headers.update({"Authorization": f"Bearer {login('sales@sipro.co.id')}"})
    assert s2.get(f"{BASE}/leads?limit=5", timeout=60).status_code == 200


def test_sales_cannot_manage_permissions(su):
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {login('sales@sipro.co.id')}"})
    assert s.get(f"{BASE}/admin/permissions", timeout=60).status_code == 403
