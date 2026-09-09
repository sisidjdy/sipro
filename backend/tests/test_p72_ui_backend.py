"""Fase 72 — regresi backend tambahan: pratinjau penomoran per proyek & kode master opsional."""
import os

import pytest
import requests
from dotenv import dotenv_values

BASE = (os.environ.get("REACT_APP_BACKEND_URL")
        or dotenv_values("/app/frontend/.env").get("REACT_APP_BACKEND_URL"))
if not BASE:
    raise RuntimeError("REACT_APP_BACKEND_URL tidak ditemukan")
BASE = BASE.rstrip("/")
PASS = "Sipro#2026"


@pytest.fixture(scope="module")
def h():
    r = requests.post(f"{BASE}/api/auth/login",
                      json={"email": "owner@sipro.co.id", "password": PASS}, timeout=30)
    assert r.status_code == 200, r.text[:300]
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(scope="module")
def project(h):
    r = requests.get(f"{BASE}/api/projects", headers=h, params={"limit": 200}, timeout=30)
    assert r.status_code == 200
    items = r.json().get("data") or []
    p = next((x for x in items if x.get("name") == "Uji Studio UI"), None)
    if not p:
        cr = requests.post(f"{BASE}/api/projects", headers=h,
                           json={"name": "Uji Studio UI", "code": "", "location": "Bandung",
                                 "status": "active"}, timeout=30)
        assert cr.status_code == 200, cr.text[:300]
        p = cr.json()["data"]
    assert p.get("code"), "kode proyek harus terisi otomatis walau dikirim kosong"
    return p


# ---- numbering: konteks proyek
def test_numbering_list_with_project_context(h, project):
    plain = requests.get(f"{BASE}/api/numbering", headers=h, timeout=30)
    ctx = requests.get(f"{BASE}/api/numbering", headers=h,
                       params={"project_id": project["id"]}, timeout=30)
    assert plain.status_code == 200 and ctx.status_code == 200, ctx.text[:300]
    rows = {r["key"]: r for r in ctx.json()["data"]}
    assert "spk" in rows and "master:cluster" in rows
    for r in rows.values():
        assert isinstance(r.get("preview"), str) and r["preview"]
    # next_seq dihitung per proyek untuk aturan berlingkup proyek
    assert any("next_seq" in r for r in rows.values())


def test_spk_preview_contains_project_code(h, project):
    r = requests.post(f"{BASE}/api/numbering/spk/preview", headers=h,
                      json={"pattern": "{PREFIX}/{PROJECT_CODE}/{SEQ}",
                            "project_id": project["id"]}, timeout=30)
    assert r.status_code == 200, r.text[:400]
    d = r.json()["data"]
    assert project["code"] in d["preview"], d
    assert isinstance(d.get("next_seq"), int) and d["next_seq"] >= 1


def test_spk_preview_invalid_token_rejected(h, project):
    r = requests.post(f"{BASE}/api/numbering/spk/preview", headers=h,
                      json={"pattern": "{PREFIX}/{TIDAKADA}/{SEQ}",
                            "project_id": project["id"]}, timeout=30)
    assert r.status_code == 400, r.text[:300]


# ---- kode master opsional (kosong → otomatis)
def test_cluster_and_block_blank_codes(h, project):
    pid = project["id"]
    c = requests.post(f"{BASE}/api/masterplan/projects/{pid}/clusters", headers=h,
                      json={"code": "", "name": "Uji Cluster Studio"}, timeout=30)
    assert c.status_code == 200, c.text[:400]
    cl = c.json().get("data") or c.json()
    assert cl.get("code"), "kode cluster kosong harus dibuat otomatis"
    b = requests.post(f"{BASE}/api/masterplan/clusters/{cl['id']}/blocks", headers=h,
                      json={"code": ""}, timeout=30)
    assert b.status_code == 200, b.text[:400]
    blk = b.json().get("data") or b.json()
    assert blk.get("code"), "kode blok kosong harus dibuat otomatis"
    # verifikasi tersimpan
    g = requests.get(f"{BASE}/api/masterplan/projects/{pid}/tree", headers=h, timeout=30)
    assert g.status_code == 200, g.text[:300]
    assert cl["code"] in g.text


def test_studio_payload_ready(h, project):
    r = requests.get(f"{BASE}/api/site-plan-studio/{project['id']}", headers=h, timeout=30)
    assert r.status_code == 200, r.text[:300]
    d = r.json()["data"]
    assert set(["plan", "units", "blocks", "clusters", "unit_types"]).issubset(d.keys())
    assert d["unit_types"], "minimal satu tipe unit aktif diperlukan untuk uji UI"
