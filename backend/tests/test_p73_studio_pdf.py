"""Fase 73 — Studio: PDF → latar, edit titik poligon (manual flag terjaga), payload project_name."""
import os
import time

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
TAG = str(int(time.time()))[-5:]


@pytest.fixture(scope="module")
def s():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": "owner@sipro.co.id", "password": "Sipro#2026"}, timeout=20)
    if r.status_code != 200:
        pytest.skip("login gagal")
    sess = requests.Session()
    sess.headers.update({"Authorization": f"Bearer {r.json()['access_token']}"})
    return sess


@pytest.fixture(scope="module")
def project(s):
    proj = s.post(f"{BASE_URL}/api/projects", json={"name": f"Uji Studio PDF {TAG}", "code": ""}).json()["data"]
    yield proj
    s.delete(f"{BASE_URL}/api/site-plan/{proj['id']}/plan")


def _pdf_bytes(pages=2):
    import pymupdf
    doc = pymupdf.open()
    for i in range(pages):
        pg = doc.new_page(width=600, height=400)
        pg.draw_rect(pymupdf.Rect(50, 50, 200, 150))
        pg.insert_text((100, 100), f"HAL-{i + 1}")
    return doc.tobytes()


def test_pdf_background_render_page(s, project):
    pid = project["id"]
    r = s.post(f"{BASE_URL}/api/site-plan-studio/{pid}/background",
               files={"file": ("plan.pdf", _pdf_bytes(), "application/pdf")}, data={"page": "2"})
    assert r.status_code == 200, r.text
    bg = r.json()["data"]["plan"]["background"]
    assert bg["source"] == "pdf" and bg["pdf_page"] == 2 and bg["pdf_pages"] == 2
    assert bg["width"] == 3000 and bg["height"] == 2000 and bg["filename"].endswith("-hal2.png")
    assert r.json()["data"]["project_name"] == project["name"]
    assert r.json()["data"]["plan"]["view_box"] == "0 0 3000 2000"
    r = s.post(f"{BASE_URL}/api/site-plan-studio/{pid}/background",
               files={"file": ("rusak.pdf", b"%PDF-bukan", "application/pdf")})
    assert r.status_code == 400


def test_vertex_edit_keeps_flags(s, project):
    pid = project["id"]
    r = s.post(f"{BASE_URL}/api/site-plan-studio/{pid}/shapes", json={"items": [
        {"points": [[10, 10], [110, 10], [110, 90], [10, 90]], "kind": "lot", "label": "X-01"}]})
    sid = r.json()["data"]["added"][0]["shape_id"]
    r = s.put(f"{BASE_URL}/api/site-plan-studio/{pid}/shapes/{sid}",
              json={"points": [[0, 0], [120, 5], [115, 95], [5, 90]]})
    assert r.status_code == 200
    d = r.json()["data"]
    assert d["manual"] is True and d["label"] == "X-01" and d["geom"]["points"].startswith("0.0,0.0 120.0,5.0")
    assert d["centroid"]["x"] == 60.0
    # SVG upload → bentuk hasil parser bukan manual; edit titik tidak mengubahnya jadi manual
    svg = '<svg viewBox="0 0 300 200"><rect x="10" y="10" width="80" height="60"/></svg>'
    s.post(f"{BASE_URL}/api/site-plan-studio/{pid}/svg", json={"svg": svg + " " * 40, "filename": "a.svg"})
    plan = s.get(f"{BASE_URL}/api/site-plan-studio/{pid}").json()["data"]["plan"]
    rect = plan["shapes"][0]
    r = s.put(f"{BASE_URL}/api/site-plan-studio/{pid}/shapes/{rect['shape_id']}",
              json={"points": [[10, 10], [95, 12], [90, 70], [10, 70]]})
    assert r.json()["data"]["manual"] is False
    # latar tetap terpasang setelah unggah SVG (tracing di atas PDF + SVG boleh berdampingan)
    assert plan["background"]["source"] == "pdf"
