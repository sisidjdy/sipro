"""Fase 72 — Studio Site Plan: parser SVG kaya, latar gambar, bentuk manual, cocok otomatis,
usulan & pembuatan unit dari bentuk; pratinjau penomoran per proyek."""
import io
import os
import time

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
PASS = "Sipro#2026"
TAG = str(int(time.time()))[-5:]
SVG = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 900 600">
<g transform="translate(50,100)"><rect id="jalan-utama" x="0" y="130" width="800" height="60"/>
<rect x="100" y="0" width="80" height="120"/><text x="140" y="60">Q{TAG[-1]}-01</text>
<path d="M190 0 h80 v120 h-80 z"/><text x="230" y="60">Q{TAG[-1]} 2</text>
<rect x="280" y="0" width="80" height="120"/></g>
<rect x="0" y="0" width="900" height="600" fill="none"/></svg>'''


def _login(email):
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": PASS}, timeout=20)
    if r.status_code != 200:
        pytest.skip(f"login {email} failed: {r.status_code}")
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    sess.headers.update({"Authorization": f"Bearer {_login('owner@sipro.co.id')}"})
    return sess


@pytest.fixture(scope="module")
def project(s):
    r = s.post(f"{BASE_URL}/api/projects", json={"name": f"Uji Studio {TAG}", "code": ""})
    assert r.status_code == 200
    proj = r.json()["data"]
    yield proj
    s.delete(f"{BASE_URL}/api/site-plan/{proj['id']}/plan")


def test_svg_rich_parse_and_labels(s, project):
    r = s.post(f"{BASE_URL}/api/site-plan-studio/{project['id']}/svg", json={"svg": SVG, "filename": "uji.svg"})
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["detected"]["lots"] == 3 and d["detected"]["labeled"] == 2
    st = s.get(f"{BASE_URL}/api/site-plan-studio/{project['id']}").json()["data"]
    shapes = st["plan"]["shapes"]
    road = next(x for x in shapes if x["shape_id"] == "jalan-utama")
    assert road["kind"] == "road"
    # transform translate(50,100) diterapkan: rect pertama mulai x=150,y=100
    lot = next(x for x in shapes if x.get("label") == f"Q{TAG[-1]}-01")
    assert lot["geom"]["points"].startswith("150.0,100.0")
    assert any(x["kind"] == "boundary" for x in shapes)


def test_suggest_and_create_units_two_options(s, project):
    pid = project["id"]
    sug = s.get(f"{BASE_URL}/api/site-plan-studio/{pid}/suggest-units").json()["data"]
    parsed = [x for x in sug if x["parsed"]]
    assert len(parsed) == 2 and {x["no"] for x in parsed} == {"01", "02"}
    assert all(x["block_exists"] is False for x in parsed)
    items = [{"shape_id": x["shape_id"], "block_code": x["block_code"], "no": x["no"]} for x in parsed]
    r = s.post(f"{BASE_URL}/api/site-plan-studio/{pid}/create-units",
               json={"items": items, "create_blocks": False})
    assert r.status_code == 200
    d = r.json()["data"]
    assert d["created"] == 0 and d["failed"] == 2 and "belum ada" in d["results"][0]["error"]
    r = s.post(f"{BASE_URL}/api/site-plan-studio/{pid}/create-units",
               json={"items": items, "create_blocks": True})
    d = r.json()["data"]
    assert d["created"] == 2 and d["failed"] == 0 and d["results"][0]["block_created"] is True
    st = s.get(f"{BASE_URL}/api/site-plan-studio/{pid}").json()["data"]
    assert len(st["units"]) == 2 and st["plan"]["stats"]["coverage_pct"] == 100
    # pemetaan ulang unit yang sudah ada → reused, bukan duplikat
    r = s.post(f"{BASE_URL}/api/site-plan-studio/{pid}/create-units",
               json={"items": items[:1], "create_blocks": True})
    assert r.json()["data"]["results"][0]["error"] == "Bentuk sudah terpetakan."


def test_manual_shape_background_and_match(s, project):
    pid = project["id"]
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (640, 400), (240, 240, 230)).save(buf, format="PNG")
    r = s.post(f"{BASE_URL}/api/site-plan-studio/{pid}/background",
               files={"file": ("bg.png", buf.getvalue(), "image/png")})
    assert r.status_code == 200 and r.json()["data"]["plan"]["background"]["width"] == 640
    r = s.post(f"{BASE_URL}/api/site-plan-studio/{pid}/shapes", json={"items": [
        {"points": [[5, 5], [60, 5], [60, 40], [5, 40]], "kind": "lot", "label": f"Q{TAG[-1]}-3"}]})
    assert r.status_code == 200
    sid = r.json()["data"]["added"][0]["shape_id"]
    r = s.post(f"{BASE_URL}/api/site-plan-studio/{pid}/shapes", json={"items": [
        {"points": [[0, 0], [1, 1], [2, 2]], "kind": "lot"}]})
    assert r.status_code == 400
    # unit Q-03 lahir dari bentuk manual lalu auto-match menemukannya via label toleran
    s.put(f"{BASE_URL}/api/site-plan-studio/{pid}/shapes/{sid}", json={"unit_id": ""})
    r = s.post(f"{BASE_URL}/api/site-plan-studio/{pid}/create-units", json={
        "items": [{"shape_id": sid, "block_code": f"Q{TAG[-1]}", "no": "03"}], "create_blocks": True})
    assert r.json()["data"]["created"] == 1
    s.put(f"{BASE_URL}/api/site-plan/{pid}/mapping", json={"items": [{"shape_id": sid, "unit_id": ""}]})
    r = s.post(f"{BASE_URL}/api/site-plan-studio/{pid}/auto-match")
    assert r.json()["data"]["matched"] == 1
    r = s.put(f"{BASE_URL}/api/site-plan-studio/{pid}/shapes/{sid}", json={"kind": "green"})
    assert r.json()["data"]["kind"] == "green" and r.json()["data"]["unit_id"] is None
    assert s.delete(f"{BASE_URL}/api/site-plan-studio/{pid}/shapes/{sid}").status_code == 200
    assert s.delete(f"{BASE_URL}/api/site-plan-studio/{pid}/background").status_code == 200


def test_numbering_preview_per_project(s, project):
    r = s.get(f"{BASE_URL}/api/numbering", params={"project_id": project["id"]})
    assert r.status_code == 200
    rows = {x["key"]: x for x in r.json()["data"]}
    before = rows["master:cluster"]
    assert before["next_seq"] == 1  # proyek baru: counter cluster per proyek mulai dari 1
    r = s.post(f"{BASE_URL}/api/masterplan/projects/{project['id']}/clusters",
               json={"code": "", "name": "Cluster Studio"})
    assert r.status_code == 200 and r.json()["data"]["code"] == before["preview"]
    rows = {x["key"]: x for x in s.get(f"{BASE_URL}/api/numbering",
                                       params={"project_id": project["id"]}).json()["data"]}
    # counter cluster PER PROYEK: proyek ini kini di urutan 2 (pratinjau = nomor yang terbit)
    assert rows["master:cluster"]["next_seq"] == 2 and rows["master:cluster"]["preview"] != before["preview"]
    r = s.post(f"{BASE_URL}/api/numbering/spk/preview", json={
        "pattern": "{PREFIX}/{PROJECT_CODE}/{SEQ}", "project_id": project["id"]})
    assert r.status_code == 200 and r.json()["data"]["preview"].startswith(f"SPK/{project['code']}/")
