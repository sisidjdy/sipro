"""Fase 73 ekstra — latar PNG tetap source='image', halaman PDF di luar rentang, undo titik via PUT."""
import io
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
        pytest.fail(f"login gagal: {r.status_code} {r.text[:200]}")
    sess = requests.Session()
    sess.headers.update({"Authorization": f"Bearer {r.json()['access_token']}"})
    return sess


@pytest.fixture(scope="module")
def project(s):
    proj = s.post(f"{BASE_URL}/api/projects", json={"name": f"Uji Studio Extra {TAG}", "code": ""}).json()["data"]
    yield proj
    s.delete(f"{BASE_URL}/api/site-plan/{proj['id']}/plan")


def _png_bytes(w=800, h=500):
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (220, 230, 240)).save(buf, format="PNG")
    return buf.getvalue()


def _pdf_bytes(pages=2):
    import pymupdf
    doc = pymupdf.open()
    for i in range(pages):
        pg = doc.new_page(width=600, height=400)
        pg.insert_text((100, 100), f"HAL-{i + 1}")
    return doc.tobytes()


def test_png_background_still_image_source(s, project):
    pid = project["id"]
    r = s.post(f"{BASE_URL}/api/site-plan-studio/{pid}/background",
               files={"file": ("latar.png", _png_bytes(), "image/png")}, data={"page": "2"})
    assert r.status_code == 200, r.text
    bg = r.json()["data"]["plan"]["background"]
    assert bg["source"] == "image"
    assert bg.get("pdf_page") in (None, 1) or "pdf_page" not in bg
    assert bg["width"] == 800 and bg["height"] == 500
    # GET verifikasi persistensi
    got = s.get(f"{BASE_URL}/api/site-plan-studio/{pid}").json()["data"]["plan"]["background"]
    assert got["file_id"] == bg["file_id"] and got["source"] == "image"



def test_pdf_page_out_of_range(s, project):
    pid = project["id"]
    r = s.post(f"{BASE_URL}/api/site-plan-studio/{pid}/background",
               files={"file": ("plan.pdf", _pdf_bytes(2), "application/pdf")}, data={"page": "9"})
    assert r.status_code in (200, 400), r.text
    if r.status_code == 200:
        bg = r.json()["data"]["plan"]["background"]
        assert bg["source"] == "pdf" and bg["pdf_pages"] == 2 and 1 <= bg["pdf_page"] <= 2


def test_shape_points_roundtrip_undo(s, project):
    pid = project["id"]
    r = s.post(f"{BASE_URL}/api/site-plan-studio/{pid}/shapes", json={"items": [
        {"points": [[20, 20], [120, 20], [120, 100], [20, 100]], "kind": "lot", "label": "U-99"}]})
    assert r.status_code == 200, r.text
    sid = r.json()["data"]["added"][0]["shape_id"]
    orig = s.get(f"{BASE_URL}/api/site-plan-studio/{pid}").json()["data"]["plan"]["shapes"]
    orig_pts = next(x for x in orig if x["shape_id"] == sid)["geom"]["points"]
    # edit titik
    s.put(f"{BASE_URL}/api/site-plan-studio/{pid}/shapes/{sid}", json={"points": [[0, 0], [130, 10], [125, 105], [15, 95]]})
    moved = next(x for x in s.get(f"{BASE_URL}/api/site-plan-studio/{pid}").json()["data"]["plan"]["shapes"] if x["shape_id"] == sid)
    assert moved["geom"]["points"] != orig_pts
    # undo (kembalikan titik semula)
    s.put(f"{BASE_URL}/api/site-plan-studio/{pid}/shapes/{sid}", json={"points": [[20, 20], [120, 20], [120, 100], [20, 100]]})
    back = next(x for x in s.get(f"{BASE_URL}/api/site-plan-studio/{pid}").json()["data"]["plan"]["shapes"] if x["shape_id"] == sid)
    assert back["geom"]["points"] == orig_pts
    # hapus bentuk lalu pastikan hilang
    assert s.delete(f"{BASE_URL}/api/site-plan-studio/{pid}/shapes/{sid}").status_code == 200
    after = s.get(f"{BASE_URL}/api/site-plan-studio/{pid}").json()["data"]["plan"]["shapes"]
    assert all(x["shape_id"] != sid for x in after)


def test_palette_roundtrip_and_validation(s):
    r = s.put(f"{BASE_URL}/api/site-plan-studio/palette", json={"palette": {
        "sales": {"booked": {"fill": "#ffd6a5", "stroke": "#zz0000", "label": "Booking Fee"}},
        "foo": {"x": {"fill": "#000000"}}, "build": {"b50": {"stroke": "#ff0000"}}}})
    assert r.status_code == 200
    d = r.json()["data"]
    assert d["sales"]["booked"] == {"fill": "#ffd6a5", "label": "Booking Fee"}  # stroke tak sah dibuang
    assert "foo" not in d and d["build"]["b50"] == {"stroke": "#ff0000"}
    assert s.get(f"{BASE_URL}/api/site-plan-studio/palette").json()["data"] == d
    r = s.put(f"{BASE_URL}/api/site-plan-studio/palette", json={"palette": {}})
    assert r.json()["data"] == {}
