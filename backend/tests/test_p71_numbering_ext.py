"""Fase 71 — verifikasi tambahan (T1): jumlah aturan 41, katalog token, regresi kode manual."""
import os
import time

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
PASS = "Sipro#2026"
TAG = str(int(time.time()))[-6:]


def _sess(email):
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": PASS}, timeout=30)
    if r.status_code != 200:
        pytest.fail(f"login {email} gagal: {r.status_code} {r.text[:200]}")
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {r.json()['access_token']}",
                      "Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def s_owner():
    return _sess("owner@sipro.co.id")


@pytest.fixture(scope="module")
def s_super():
    return _sess("superadmin@sipro.co.id")


@pytest.fixture(scope="module")
def s_sales():
    return _sess("sales@sipro.co.id")


@pytest.fixture(scope="module", autouse=True)
def _bersihkan_data_uji():
    """Proyek/cluster/blok/vendor uji manual tidak punya endpoint hapus — bersihkan langsung
    di DB agar suite tidak meninggalkan proyek contoh (fixture mandiri)."""
    yield
    from _testdata import purge_tagged
    purge_tagged(TAG, project_names=(f"Uji Manual {TAG}",), vendor_names=(f"Vendor Manual {TAG}",))


# --- GET /api/numbering : struktur & jumlah aturan
def test_list_rules_shape(s_owner):
    r = s_owner.get(f"{BASE_URL}/api/numbering")
    assert r.status_code == 200
    body = r.json()
    rows = body["data"]
    # Registry bertambah seiring fase (41 pada Fase 71); yang dijaga: tidak berkurang & kunci unik.
    assert len(rows) >= 41, f"harusnya >= 41 aturan, dapat {len(rows)}"
    assert len({row["key"] for row in rows}) == len(rows), "kunci aturan penomoran kembar"
    fields = {"key", "label", "group", "pattern", "prefix", "width", "reset", "seq_scope",
              "start", "overridden", "default", "preview", "next_seq"}
    for row in rows:
        missing = fields - set(row)
        assert not missing, f"{row.get('key')} kehilangan field {missing}"
        assert isinstance(row["next_seq"], int) and row["next_seq"] >= 1
        assert row["preview"], f"{row['key']} preview kosong"
    for meta in ("groups", "reset_options", "seq_scope_options", "global_tokens", "context_tokens"):
        assert body.get(meta), f"meta {meta} kosong"
    # MM_ROMAN token tersedia global
    assert any(t["token"] == "MM_ROMAN" for t in body["global_tokens"])


# --- GET /api/numbering/{key}/tokens
@pytest.mark.parametrize("key", ["spk", "master:unit"])
def test_tokens_catalog(s_owner, key):
    r = s_owner.get(f"{BASE_URL}/api/numbering/{key}/tokens")
    assert r.status_code == 200, r.text
    rows = r.json()["data"]
    kinds = {x["kind"] for x in rows}
    assert "umum" in kinds and "konteks" in kinds
    assert all({"token", "desc", "example", "kind"} <= set(x) for x in rows)


def test_tokens_unknown_key_404(s_owner):
    assert s_owner.get(f"{BASE_URL}/api/numbering/entah-apa/tokens").status_code == 404


# --- POST preview
def test_preview_spk_pattern(s_owner):
    r = s_owner.post(f"{BASE_URL}/api/numbering/spk/preview", json={
        "pattern": "{PREFIX}/{PROJECT_CODE}/{MM_ROMAN}/{YYYY}/{SEQ}",
        "sample": {"project_code": "GRY"}})
    assert r.status_code == 200, r.text
    prev = r.json()["data"]["preview"]
    parts = prev.split("/")
    assert parts[0] == "SPK" and parts[1] == "GRY"
    assert parts[2] in ("IX", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "X", "XI", "XII")
    assert parts[3].isdigit() and len(parts[3]) == 4
    assert parts[4].isdigit()


def test_preview_unknown_token_400(s_owner):
    r = s_owner.post(f"{BASE_URL}/api/numbering/spk/preview", json={"pattern": "{FOO}/{SEQ}"})
    assert r.status_code == 400
    assert "FOO" in r.json()["detail"] and "tidak tersedia" in r.json()["detail"]


def test_preview_does_not_bump_counter(s_owner):
    before = next(x for x in s_owner.get(f"{BASE_URL}/api/numbering").json()["data"]
                  if x["key"] == "spk")["next_seq"]
    for _ in range(3):
        s_owner.post(f"{BASE_URL}/api/numbering/spk/preview", json={"pattern": "{PREFIX}/{SEQ}"})
    after = next(x for x in s_owner.get(f"{BASE_URL}/api/numbering").json()["data"]
                 if x["key"] == "spk")["next_seq"]
    assert before == after, "pratinjau seharusnya tidak menaikkan counter"


# --- RBAC
def test_sales_view_only(s_sales):
    assert s_sales.get(f"{BASE_URL}/api/numbering").status_code == 200
    assert s_sales.put(f"{BASE_URL}/api/numbering/spk",
                       json={"pattern": "{PREFIX}/{SEQ}"}).status_code == 403
    assert s_sales.delete(f"{BASE_URL}/api/numbering/spk").status_code == 403


def test_superadmin_can_edit(s_super):
    r = s_super.put(f"{BASE_URL}/api/numbering/quotation", json={"width": 5})
    assert r.status_code == 200, r.text
    assert r.json()["data"]["overridden"] is True and r.json()["data"]["width"] == 5
    r = s_super.delete(f"{BASE_URL}/api/numbering/quotation")
    assert r.status_code == 200 and r.json()["data"]["overridden"] is False


def test_put_invalid_pattern_rejected(s_owner):
    r = s_owner.put(f"{BASE_URL}/api/numbering/spk", json={"pattern": "{BOGUS}/{SEQ}"})
    assert r.status_code == 400, r.text
    r = s_owner.put(f"{BASE_URL}/api/numbering/master:unit", json={"pattern": "{BLOCK_CODE}"})
    assert r.status_code == 400, "kode unit tanpa {NO}/{SEQ} harus ditolak"


# --- regresi: kode manual dipakai apa adanya
def test_manual_codes_preserved(s_owner):
    code = f"UJI{TAG}"
    r = s_owner.post(f"{BASE_URL}/api/projects", json={"name": f"Uji Manual {TAG}", "code": code})
    assert r.status_code == 200, r.text
    proj = r.json()["data"]
    assert proj["code"] == code
    r = s_owner.post(f"{BASE_URL}/api/masterplan/projects/{proj['id']}/clusters",
                     json={"code": "CLMAN", "name": "Cluster Uji Manual"})
    assert r.status_code == 200, r.text
    cl = r.json()["data"]
    assert cl["code"] == "CLMAN"
    r = s_owner.post(f"{BASE_URL}/api/masterplan/clusters/{cl['id']}/blocks", json={"code": "ZZ"})
    assert r.status_code == 200, r.text
    blk = r.json()["data"]
    assert blk["code"] == "ZZ"
    r = s_owner.post(f"{BASE_URL}/api/vendors", json={"code": f"VM{TAG}", "name": f"Vendor Manual {TAG}",
                                                      "category": "material"})
    assert r.status_code == 200, r.text
    assert r.json()["data"]["code"] == f"VM{TAG}"


# --- reset aturan kembali ke bawaan
def test_reset_restores_default_pattern(s_owner):
    s_owner.put(f"{BASE_URL}/api/numbering/spk", json={
        "pattern": "{PREFIX}/{PROJECT_CODE}/{MM_ROMAN}/{YYYY}/{SEQ}", "width": 3})
    r = s_owner.delete(f"{BASE_URL}/api/numbering/spk")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["overridden"] is False and data["pattern"] == "{PREFIX}/{YYYY}/{SEQ}"
