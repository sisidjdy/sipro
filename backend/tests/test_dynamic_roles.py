"""Peran dinamis: CRUD /admin/roles, pemakaian di users, login, izin efektif, dan lingkup."""
import os
import uuid

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8001").rstrip("/")
API = f"{BASE_URL}/api"
PW = "Sipro#2026"
CODE = f"uji_{uuid.uuid4().hex[:6]}"


def _login(email, pw=PW):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pw}, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["access_token"], r.json().get("data") or {}


@pytest.fixture(scope="module")
def sa():
    tok, _ = _login("superadmin@sipro.co.id")
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="module", autouse=True)
def cleanup(sa):
    yield
    users = requests.get(f"{API}/admin/users", headers=sa, timeout=30).json().get("data", [])
    for u in users:
        if u.get("role") == CODE:
            requests.put(f"{API}/admin/users/{u['id']}", headers=sa, json={"role": "site_engineer", "is_active": False}, timeout=30)
    requests.delete(f"{API}/admin/roles/{CODE}", headers=sa, timeout=30)


def test_builtin_roles_listed(sa):
    d = requests.get(f"{API}/admin/roles", headers=sa, timeout=30).json()
    codes = {r["code"] for r in d["data"]}
    assert {"super_admin", "owner", "sales", "site_engineer"} <= codes
    assert "sales" in d["base_options"] and "owner" not in d["base_options"]
    assert set(d["scope_meta"]) == {"all", "own", "project"}


def test_reject_bad_code_and_duplicate(sa):
    r = requests.post(f"{API}/admin/roles", headers=sa, json={"code": "Bad Code", "label": "Salah"}, timeout=30)
    assert r.status_code == 400
    r = requests.post(f"{API}/admin/roles", headers=sa, json={"code": "sales", "label": "Sales lagi"}, timeout=30)
    assert r.status_code == 400 and "sudah dipakai" in r.text
    r = requests.post(f"{API}/admin/roles", headers=sa, json={"code": "abc_x", "label": "Induk salah", "inherits": "owner"}, timeout=30)
    assert r.status_code == 400


def test_create_role_appears_everywhere(sa):
    r = requests.post(f"{API}/admin/roles", headers=sa, json={
        "code": CODE, "label": "Peran Uji", "inherits": "site_engineer", "scope": "project"}, timeout=30)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["custom"] is True
    perms = requests.get(f"{API}/admin/permissions", headers=sa, timeout=30).json()["data"]
    assert CODE in perms["roles"]
    assert perms["role_meta"][CODE]["label"] == "Peran Uji"
    assert perms["inherits"][CODE] == "site_engineer"
    # izin efektif diwarisi dari site_engineer
    assert perms["effective"]["projects"][CODE]["perms"]  # diwarisi dari site_engineer
    ref = requests.get(f"{API}/reference", headers=sa, timeout=30).json()
    groups = ref.get("data", ref)
    groups = groups.get("groups", groups)
    opts = {o["value"]: o["label"] for o in groups["user_role"]["options"]}
    assert opts.get(CODE) == "Peran Uji"


def test_assign_user_login_and_scope(sa):
    email = f"{CODE}@sipro.co.id"
    r = requests.post(f"{API}/admin/users", headers=sa, json={
        "name": "Peran Uji", "email": email, "password": PW, "role": CODE}, timeout=30)
    assert r.status_code == 200, r.text
    tok, me = _login(email)
    assert me["role"] == CODE and me["nav_role"] == "site_engineer"
    assert me["role_label"] == "Peran Uji" and me["role_scope"] == "project"
    h = {"Authorization": f"Bearer {tok}"}
    assert requests.get(f"{API}/projects", headers=h, timeout=30).status_code == 200
    assert requests.get(f"{API}/work/home", headers=h, timeout=30).status_code == 200
    assert requests.get(f"{API}/admin/users", headers=h, timeout=30).status_code == 403
    # matriks bisa menimpa warisan: cabut `projects` → 403
    perms = requests.get(f"{API}/admin/permissions", headers=sa, timeout=30).json()["data"]
    matrix = perms["matrix"]
    matrix.setdefault("projects", {})[CODE] = []
    r = requests.put(f"{API}/admin/permissions", headers=sa, json={"matrix": matrix}, timeout=30)
    assert r.status_code == 200, r.text
    assert requests.get(f"{API}/projects", headers=h, timeout=30).status_code == 403
    matrix["projects"].pop(CODE)
    requests.put(f"{API}/admin/permissions", headers=sa, json={"matrix": matrix}, timeout=30)
    # hapus ditolak selagi masih dipakai
    r = requests.delete(f"{API}/admin/roles/{CODE}", headers=sa, timeout=30)
    assert r.status_code == 400 and "dipakai" in r.text


def test_copy_role_carries_effective_perms(sa):
    code = f"{CODE}_cp"
    r = requests.post(f"{API}/admin/roles", headers=sa, json={
        "code": code, "label": "Salinan Finance", "copy_from": "finance", "scope": "all"}, timeout=30)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["copied_from"] == "finance" and r.json()["data"]["copied_perms"] > 0
    perms = requests.get(f"{API}/admin/permissions", headers=sa, timeout=30).json()["data"]
    for res, roles in perms["effective"].items():
        assert sorted(roles[code]["perms"]) == sorted(roles["finance"]["perms"]), res
    # salinan Direksi ditolak
    r = requests.post(f"{API}/admin/roles", headers=sa, json={"code": f"{code}2", "label": "Salinan Owner", "copy_from": "owner"}, timeout=30)
    assert r.status_code == 400
    # has_role: peran kustom yang mewarisi finance_manager menembus cabang literal (kas bon boleh finance_manager)
    assert requests.delete(f"{API}/admin/roles/{code}", headers=sa, timeout=30).status_code == 200
    assert code not in requests.get(f"{API}/admin/permissions", headers=sa, timeout=30).json()["data"]["roles"]


def test_has_role_follows_parent_for_literal_branches(sa):
    """build/calendar `can.configure` hanya CONFIG_ROLES (owner/super_admin/project_manager) → peran
    kustom yang mewarisi project_manager harus mendapat configure=True, yang mewarisi sales tidak."""
    made = []
    try:
        for suffix, parent in (("pm", "project_manager"), ("sl", "sales")):
            code = f"{CODE}_{suffix}"
            assert requests.post(f"{API}/admin/roles", headers=sa, json={
                "code": code, "label": f"Uji {suffix}", "inherits": parent, "scope": "all"}, timeout=30).status_code == 200
            email = f"{code}@sipro.co.id"
            assert requests.post(f"{API}/admin/users", headers=sa, json={
                "name": code, "email": email, "password": PW, "role": code}, timeout=30).status_code == 200
            made.append((code, email))
        tok_pm, _ = _login(made[0][1])
        tok_sl, _ = _login(made[1][1])
        r = requests.get(f"{API}/build/calendar", headers={"Authorization": f"Bearer {tok_pm}"}, timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["can"]["configure"] is True
        r2 = requests.get(f"{API}/build/calendar", headers={"Authorization": f"Bearer {tok_sl}"}, timeout=30)
        assert r2.status_code in (403, 200)
        if r2.status_code == 200:
            assert r2.json()["can"]["configure"] is False
    finally:
        users = requests.get(f"{API}/admin/users", headers=sa, timeout=30).json().get("data", [])
        for code, email in made:
            for u in users:
                if u.get("email") == email:
                    requests.put(f"{API}/admin/users/{u['id']}", headers=sa, json={"role": "site_engineer", "is_active": False}, timeout=30)
            requests.delete(f"{API}/admin/roles/{code}", headers=sa, timeout=30)


def test_update_and_delete_role(sa):
    r = requests.put(f"{API}/admin/roles/{CODE}", headers=sa, json={"label": "Peran Uji 2", "scope": "all"}, timeout=30)
    assert r.status_code == 200 and r.json()["data"]["label"] == "Peran Uji 2"
    assert requests.put(f"{API}/admin/roles/sales", headers=sa, json={"label": "x"}, timeout=30).status_code == 400
    users = requests.get(f"{API}/admin/users", headers=sa, timeout=30).json()["data"]
    for u in users:
        if u["role"] == CODE:
            requests.put(f"{API}/admin/users/{u['id']}", headers=sa, json={"role": "site_engineer", "is_active": False}, timeout=30)
    assert requests.delete(f"{API}/admin/roles/{CODE}", headers=sa, timeout=30).status_code == 200
    perms = requests.get(f"{API}/admin/permissions", headers=sa, timeout=30).json()["data"]
    assert CODE not in perms["roles"]
    assert requests.delete(f"{API}/admin/roles/{CODE}", headers=sa, timeout=30).status_code == 404
