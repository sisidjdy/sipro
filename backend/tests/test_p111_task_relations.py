"""Iteration 111 — spot-checks for POST /api/work/tasks related-entity validation (customer)."""
import os

import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
base_url = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base_url:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
BASE_URL = base_url.rstrip("/")
API = f"{BASE_URL}/api"


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": "superadmin@sipro.co.id", "password": "Sipro#2026"})
    if r.status_code != 200:
        pytest.fail(f"login failed {r.status_code}: {r.text[:300]}")
    token = r.json().get("access_token") or r.json().get("token")
    if not token:
        pytest.fail(f"no token in login response: {r.text[:300]}")
    s.headers.update({"Authorization": f"Bearer {token}"})
    return s


def _first(client, path):
    r = client.get(f"{API}{path}")
    assert r.status_code == 200, f"{path} -> {r.status_code} {r.text[:200]}"
    data = r.json().get("data") or []
    assert data, f"no seed data at {path}"
    return data[0]


def test_create_task_with_customer_relation(client):
    cust = _first(client, "/customers?limit=5")
    r = client.post(f"{API}/work/tasks", json={
        "title": "TEST_P111 relasi customer",
        "type": "todo", "priority": "medium",
        "related_entity_type": "customer", "related_entity_id": cust["id"],
    })
    assert r.status_code == 200, r.text[:400]
    body = r.json()
    task = body.get("data") or body
    assert task.get("related_entity_type") == "customer"
    assert task.get("related_entity_id") == cust["id"]
    # verify persistence
    tid = task.get("id")
    g = client.get(f"{API}/work/tasks/{tid}")
    assert g.status_code == 200, g.text[:300]
    payload = g.json().get("data") or g.json()
    gt = payload.get("task") or payload
    assert gt.get("related_entity_id") == cust["id"]
    assert gt.get("related_entity_type") == "customer"


def test_create_task_with_fake_customer_id_404(client):
    r = client.post(f"{API}/work/tasks", json={
        "title": "TEST_P111 relasi customer palsu",
        "type": "todo", "priority": "medium",
        "related_entity_type": "customer", "related_entity_id": "does-not-exist-111",
    })
    assert r.status_code == 404, f"expected 404, got {r.status_code}: {r.text[:300]}"


def test_create_task_jobdesk_with_lead_relation(client):
    lead = _first(client, "/leads?limit=5")
    r = client.post(f"{API}/work/tasks", json={
        "title": "TEST_P111 jobdesk SM-10 + lead",
        "type": "todo", "priority": "medium",
        "jobdesk_code": "SM-10",
        "related_entity_type": "lead", "related_entity_id": lead["id"],
    })
    assert r.status_code == 200, r.text[:400]
    task = r.json().get("data") or r.json()
    assert task.get("related_entity_id") == lead["id"]


@pytest.mark.parametrize("path", ["/leads?limit=5", "/deals?limit=5", "/units?limit=5",
                                 "/customers?limit=5", "/projects?limit=5"])
def test_dropdown_source_endpoints(client, path):
    r = client.get(f"{API}{path}")
    assert r.status_code == 200, r.text[:200]
    assert isinstance(r.json().get("data"), list)
