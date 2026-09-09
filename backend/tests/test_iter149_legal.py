"""Backend tests for iteration 149: Legal pages + RBAC + users + coa + WA guide."""
import os
import re
import pytest
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://legal-pages-16.preview.emergentagent.com").rstrip("/")
PW = "Sipro#2026"


def login(email):
    r = requests.post(f"{BASE}/api/auth/login", json={"email": email, "password": PW}, timeout=30)
    assert r.status_code == 200, f"login failed {email}: {r.status_code} {r.text}"
    return r.json()["access_token"]


def H(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def sa():
    return login("superadmin@sipro.co.id")


@pytest.fixture(scope="module")
def legal_user(sa):
    # Ensure legal@sipro.co.id exists with role legal_admin
    r = requests.get(f"{BASE}/api/admin/users", headers=H(sa), timeout=30)
    if r.status_code == 200:
        users = r.json().get("data", r.json()) if isinstance(r.json(), dict) else r.json()
        if isinstance(users, dict) and "items" in users:
            users = users["items"]
        found = next((u for u in users if u.get("email") == "legal@sipro.co.id"), None)
        if not found:
            requests.post(f"{BASE}/api/admin/users", headers=H(sa),
                          json={"email": "legal@sipro.co.id", "password": PW,
                                "name": "Legal Admin", "role": "legal_admin"}, timeout=30)
    return login("legal@sipro.co.id")


# ---------- Public legal ----------
def test_legal_public_id():
    r = requests.get(f"{BASE}/api/legal/public?lang=id", timeout=30)
    assert r.status_code == 200
    d = r.json().get("data", r.json())
    assert "identity" in d
    pages = d["pages"]
    assert "Kebijakan Privasi" in pages["privacy"]["content"]
    for p in ("privacy", "terms", "deletion"):
        assert "{company}" not in pages[p]["content"], f"unresolved placeholder in {p}"


def test_legal_public_en():
    r = requests.get(f"{BASE}/api/legal/public?lang=en", timeout=30)
    assert r.status_code == 200
    d = r.json().get("data", r.json())
    assert "Privacy Policy" in d["pages"]["privacy"]["content"]


def test_deletion_request_ok():
    r = requests.post(f"{BASE}/api/legal/public/deletion-requests",
                      json={"name": "Tester Uji", "contact": "tester@example.com",
                            "reason": "Ingin data dihapus", "lang": "id"}, timeout=30)
    assert r.status_code == 200, r.text
    d = r.json().get("data", r.json())
    ticket = d["ticket"]
    assert re.match(r"^DEL-\d{8}-[A-Z0-9]{4}$", ticket), ticket
    pytest.deletion_ticket = ticket


def test_deletion_request_honeypot():
    r = requests.post(f"{BASE}/api/legal/public/deletion-requests",
                      json={"name": "Bot", "contact": "bot@x.com", "reason": "spam",
                            "website": "http://spam.com", "lang": "id"}, timeout=30)
    assert r.status_code == 400


def test_deletion_request_short_name():
    r = requests.post(f"{BASE}/api/legal/public/deletion-requests",
                      json={"name": "A", "contact": "x@y.com", "reason": "x", "lang": "id"}, timeout=30)
    # App normalizes 422 → 400 globally; accept either
    assert r.status_code in (400, 422)


# ---------- RBAC legal ----------
def test_legal_settings_rbac():
    r = requests.get(f"{BASE}/api/legal/settings", timeout=30)
    assert r.status_code == 401
    r = requests.get(f"{BASE}/api/legal/settings", headers=H(login("sales@sipro.co.id")), timeout=30)
    assert r.status_code == 403


def test_legal_settings_sa_and_legal(sa, legal_user):
    for tok in (sa, legal_user):
        r = requests.get(f"{BASE}/api/legal/settings", headers=H(tok), timeout=30)
        assert r.status_code == 200


def test_legal_settings_put_reflect_public(sa):
    r = requests.get(f"{BASE}/api/legal/settings", headers=H(sa), timeout=30)
    cur = r.json().get("data", r.json())
    identity = dict(cur.get("identity", {}))
    new_email = "kontak-uji@harmony.example"
    identity["email"] = new_email
    payload = {"identity": identity}
    r = requests.put(f"{BASE}/api/legal/settings", headers=H(sa), json=payload, timeout=30)
    assert r.status_code == 200, r.text
    r = requests.get(f"{BASE}/api/legal/public?lang=id", timeout=30)
    body = r.text
    assert new_email in body


def test_deletion_requests_list_and_patch(sa):
    r = requests.get(f"{BASE}/api/legal/deletion-requests", headers=H(sa), timeout=30)
    assert r.status_code == 200
    d = r.json().get("data", r.json())
    items = d if isinstance(d, list) else d.get("items", [])
    assert len(items) >= 1
    rid = items[0]["id"]
    # invalid status
    r = requests.patch(f"{BASE}/api/legal/deletion-requests/{rid}",
                       headers=H(sa), json={"status": "weird"}, timeout=30)
    assert r.status_code == 400
    # valid
    r = requests.patch(f"{BASE}/api/legal/deletion-requests/{rid}",
                       headers=H(sa), json={"status": "done", "note": "ok"}, timeout=30)
    assert r.status_code == 200
    # unknown id
    r = requests.patch(f"{BASE}/api/legal/deletion-requests/nonexistent-id-xyz",
                       headers=H(sa), json={"status": "done"}, timeout=30)
    assert r.status_code == 404


# ---------- Permissions matrix ----------
def test_permissions_matrix(sa):
    r = requests.get(f"{BASE}/api/admin/permissions", headers=H(sa), timeout=30)
    assert r.status_code == 200
    d = r.json().get("data", r.json())
    assert "legal_admin" in d["roles"]
    for res in ("legal", "coa", "organizations"):
        assert res in d["resources"], f"missing {res}"
    assert d["resource_meta"]["coa"]["label"] == "Bagan Akun (CoA)"
    assert "group_order" in d
    assert "manage" in d["effective"]["legal"]["legal_admin"]["perms"]


# ---------- CoA RBAC ----------
def test_coa_rbac(legal_user):
    fin = login("finance@sipro.co.id")
    sales = login("sales@sipro.co.id")
    assert requests.get(f"{BASE}/api/gl/accounts", headers=H(fin), timeout=30).status_code == 200
    assert requests.get(f"{BASE}/api/gl/accounts", headers=H(sales), timeout=30).status_code == 403
    assert requests.get(f"{BASE}/api/gl/accounts", headers=H(legal_user), timeout=30).status_code == 403


# ---------- Update user ----------
def test_admin_update_user(sa):
    import time
    email = f"uji-legal-tmp-{int(time.time())}@sipro.co.id"  # unik per run; dibersihkan di akhir
    # cleanup if exists
    r = requests.get(f"{BASE}/api/admin/users", headers=H(sa), timeout=30)
    users = r.json().get("data", r.json())
    if isinstance(users, dict):
        users = users.get("items", [])
    ex = next((u for u in users if u.get("email") == email), None)
    if ex:
        requests.delete(f"{BASE}/api/admin/users/{ex['id']}", headers=H(sa), timeout=30)
    r = requests.post(f"{BASE}/api/admin/users", headers=H(sa),
                      json={"email": email, "password": PW, "name": "Uji Legal",
                            "role": "legal_admin"}, timeout=30)
    assert r.status_code in (200, 201), r.text
    uid = (r.json().get("data") or r.json()).get("id") or r.json().get("id")
    r = requests.put(f"{BASE}/api/admin/users/{uid}", headers=H(sa),
                     json={"role": "sales", "name": "Uji Sales", "phone": "+628110000001"}, timeout=30)
    assert r.status_code == 200, r.text
    r = requests.put(f"{BASE}/api/admin/users/{uid}", headers=H(sa),
                     json={"role": "legal_admin"}, timeout=30)
    assert r.status_code == 200
    # Tidak ada endpoint hapus pengguna (by design: nonaktifkan, bukan hapus) — akun uji
    # dinonaktifkan lewat API lalu dibuang langsung di DB agar tidak tercecer ke daftar pengguna.
    requests.put(f"{BASE}/api/admin/users/{uid}", headers=H(sa), json={"is_active": False}, timeout=30)
    from _testdata import _db
    _db().users.delete_many({"email": {"$regex": r"^uji-legal-tmp"}})


# ---------- WA guide legal urls ----------
def test_wa_webhook_guide_legal_urls(sa):
    r = requests.get(f"{BASE}/api/wa/setup/webhook-guide?public_base={BASE}",
                     headers=H(sa), timeout=30)
    assert r.status_code == 200, r.text
    d = r.json().get("data", r.json())
    lu = d["legal_urls"]
    for k in ("privacy", "terms", "deletion"):
        assert k in lu and lu[k], f"missing legal_urls.{k}"
