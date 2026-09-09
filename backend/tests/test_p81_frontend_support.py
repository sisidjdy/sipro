"""Fase 81 — dukungan uji frontend: validasi ekstensi impor RAB, kendali fasum, fasum-cap SPK."""
import os

import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
base = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
BASE_URL = base.rstrip("/")


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": "superadmin@sipro.co.id", "password": "Sipro#2026"})
    assert r.status_code == 200, r.text[:300]
    token = r.json().get("access_token")
    assert token
    s.headers.update({"Authorization": f"Bearer {token}"})
    return s


@pytest.fixture(scope="module")
def project_id(client):
    r = client.get(f"{BASE_URL}/api/projects")
    assert r.status_code == 200
    data = r.json().get("data", r.json())
    projects = data if isinstance(data, list) else data.get("items", [])
    caa = [p for p in projects if "Cluster Asri Blok A" in (p.get("name") or "")]
    assert caa, "project CAA not found"
    return caa[0]["id"]


# --- Impor RAB: validasi ekstensi ---
def test_import_rejects_non_xlsx(client):
    files = {"file": ("bad.csv", b"code,description\nA,B\n", "text/csv")}
    r = client.post(f"{BASE_URL}/api/rab/templates/unit_type/TIPE-36-72/import", files=files)
    assert r.status_code == 400, r.text[:300]
    assert "xlsx" in r.json().get("detail", "").lower()


def test_import_template_download(client):
    r = client.get(f"{BASE_URL}/api/rab/import-template.xlsx", params={"kind": "unit_type"})
    assert r.status_code == 200
    assert r.content[:2] == b"PK"


# --- Kendali fasum di ringkasan ---
def test_fasum_control_rows(client, project_id):
    r = client.get(f"{BASE_URL}/api/rab/projects/{project_id}/summary")
    assert r.status_code == 200, r.text[:300]
    data = r.json()["data"]
    rows = data.get("fasum_control")
    assert isinstance(rows, list), f"fasum_control missing: {list(data.keys())}"
    print("FASUM_CONTROL:", rows)
    for row in rows:
        for key in ("spk_id", "spk_number", "cap_pct", "billed_pct", "over", "phases", "facilities"):
            assert key in row, f"missing {key} in {row}"


# --- fasum-cap per SPK ---
def test_fasum_cap_endpoint(client, project_id):
    r = client.get(f"{BASE_URL}/api/rab/projects/{project_id}/summary")
    rows = r.json()["data"].get("fasum_control") or []
    if not rows:
        pytest.skip("no fasum SPK to check")
    sid = rows[0]["spk_id"]
    cap = client.get(f"{BASE_URL}/api/rab/spk/{sid}/fasum-cap")
    assert cap.status_code == 200, cap.text[:300]
    d = cap.json()["data"]
    print("FASUM_CAP:", d)
    assert "applies" in d and "cap_pct" in d


# --- Versi RAB tersedia untuk tipe yang diuji UI ---
def test_versions_listed(client):
    r = client.get(f"{BASE_URL}/api/rab/templates/unit_type/TIPE-36-72/versions")
    assert r.status_code == 200
    versions = r.json()["data"]["versions"]
    assert len(versions) >= 2
    assert versions[0]["current"] is True
    assert all("_id" not in v for v in versions)
