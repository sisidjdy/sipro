"""Fase 100 iter146 — integration test via public API for wa/setup wizard endpoints (read-only)."""
import os
import re

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
                break

PWD = "Sipro#2026"
SUPER = "superadmin@sipro.co.id"
SALES = "sales@sipro.co.id"


def _login(email: str) -> requests.Session:
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": PWD}, timeout=20)
    assert r.status_code == 200, f"login {email} → {r.status_code} {r.text[:200]}"
    tok = r.json().get("token") or r.json().get("access_token")
    if tok:
        s.headers["Authorization"] = f"Bearer {tok}"
    return s


@pytest.fixture(scope="module")
def sadm():
    return _login(SUPER)


@pytest.fixture(scope="module")
def sales():
    return _login(SALES)


def _cred_set(sadm, key):
    cfg = sadm.get(f"{BASE_URL}/api/wa/config", timeout=20).json()["data"]
    return bool(cfg["credentials"][key]["set"])


@pytest.fixture(scope="module")
def live_token(sadm):
    """Diagnose memanggil Graph API Meta sungguhan — hanya bermakna dengan token live."""
    if not (_cred_set(sadm, "token") and _cred_set(sadm, "phone_id")):
        pytest.skip("butuh WHATSAPP_TOKEN + WHATSAPP_PHONE_ID live (panggilan nyata ke Meta)")


@pytest.fixture(scope="module")
def local_webhook_secret(sadm):
    """Handshake & panduan webhook hanya butuh verify_token/app_secret LOKAL (tidak menyentuh Meta).
    Bila belum ada, pasang nilai uji sementara dan bersihkan lagi — mode tetap simulasi."""
    need = [k for k in ("verify_token", "app_secret") if not _cred_set(sadm, k)]
    if need:
        r = sadm.put(f"{BASE_URL}/api/wa/config", json={k: f"uji-{k}-iter146" for k in need}, timeout=20)
        assert r.status_code == 200, r.text[:200]
    yield
    if need:
        sadm.put(f"{BASE_URL}/api/wa/config", json={k: "__clear__" for k in need}, timeout=20)


# ---------- checklist via GET /api/wa/config ----------
def test_wa_config_checklist_structure(sadm):
    r = sadm.get(f"{BASE_URL}/api/wa/config", timeout=20)
    assert r.status_code == 200, r.text[:200]
    data = r.json().get("data") or r.json()
    checklist = data["checklist"]
    keys = [c["key"] for c in checklist]
    assert keys == ["creds", "probe", "number", "subscribed", "webhook", "template", "quality", "mode"], keys
    for c in checklist:
        assert set(["label", "ok", "blocking", "fix"]).issubset(c.keys())
        assert isinstance(c["ok"], bool)
        assert isinstance(c["blocking"], bool)
        if not c["ok"]:
            assert isinstance(c["fix"], str) and c["fix"].strip(), c
    q = next(c for c in checklist if c["key"] == "quality")
    m = next(c for c in checklist if c["key"] == "mode")
    assert q["blocking"] is False and m["blocking"] is False
    assert isinstance(data.get("diagnose"), dict)
    assert isinstance(data["go_live_ready"], bool)


# ---------- diagnose (read-only call to Meta) ----------
def test_wa_setup_diagnose(sadm, live_token):
    r = sadm.post(f"{BASE_URL}/api/wa/setup/diagnose", timeout=45)
    assert r.status_code == 200, r.text[:400]
    d = r.json()["data"]
    tok = d["token"]
    assert tok["ok"] is True, tok
    assert tok["type"] == "SYSTEM_USER"
    assert tok["permanent"] is True
    assert tok["missing_scopes"] == []
    ph = d["phone"]
    assert ph["status"] == "PENDING"
    assert ph["registered"] is False
    assert isinstance(ph.get("hint"), str) and ph["hint"].strip()
    wb = d["waba"]
    assert wb.get("account_review_status") == "APPROVED"
    assert d["subscribed"] is True
    assert any("Sipro WA" in str(a) for a in d["subscribed_apps"])
    probs = " ".join(d.get("problems") or [])
    assert "belum terdaftar" in probs.lower()


# ---------- webhook-guide ----------
def test_webhook_guide_with_base(sadm, local_webhook_secret):
    r = sadm.get(f"{BASE_URL}/api/wa/setup/webhook-guide",
                 params={"public_base": BASE_URL}, timeout=20)
    assert r.status_code == 200, r.text[:200]
    d = r.json()["data"]
    assert d["callback_url"] == f"{BASE_URL}/api/webhooks/wa"
    assert isinstance(d["verify_token"], str) and len(d["verify_token"]) > 0
    assert d["verify_token_set"] is True
    assert d["app_secret_set"] is True
    assert d["https"] is True
    assert len(d["fields"]) == 4
    assert len(d["steps"]) == 5


def test_webhook_guide_without_base(sadm):
    r = sadm.get(f"{BASE_URL}/api/wa/setup/webhook-guide", timeout=20)
    assert r.status_code == 200
    assert r.json()["data"]["callback_url"] == "/api/webhooks/wa"


def test_webhook_guide_invalid_base(sadm):
    r = sadm.get(f"{BASE_URL}/api/wa/setup/webhook-guide",
                 params={"public_base": "bukan-url"}, timeout=20)
    assert r.status_code == 400, r.text[:200]


# ---------- handshake ----------
def test_handshake_success(sadm, local_webhook_secret):
    r = sadm.post(f"{BASE_URL}/api/wa/setup/handshake",
                  json={"public_base": BASE_URL}, timeout=30)
    assert r.status_code == 200, r.text[:200]
    d = r.json()["data"]
    assert d["ok"] is True
    assert d["status_code"] == 200
    assert "berhasil" in d["detail"].lower()


def test_handshake_failure_honest(sadm, local_webhook_secret):
    r = sadm.post(f"{BASE_URL}/api/wa/setup/handshake",
                  json={"public_base": "https://tidak-ada.invalid"}, timeout=30)
    assert r.status_code == 200, r.text[:200]
    d = r.json()["data"]
    assert d["ok"] is False
    assert isinstance(d["detail"], str) and d["detail"].strip()


# ---------- local validation (safe, does not reach Meta) ----------
def test_register_pin_validation(sadm):
    r = sadm.post(f"{BASE_URL}/api/wa/setup/register", json={"pin": "12"}, timeout=15)
    assert r.status_code == 400, r.text[:200]
    assert "6 digit" in r.text or "PIN" in r.text


def test_verify_code_validation(sadm):
    r = sadm.post(f"{BASE_URL}/api/wa/setup/verify-code", json={"code": "ab"}, timeout=15)
    assert r.status_code == 400, r.text[:200]


def test_request_code_validation(sadm):
    r = sadm.post(f"{BASE_URL}/api/wa/setup/request-code", json={"method": "EMAIL"}, timeout=15)
    assert r.status_code == 400, r.text[:200]


# ---------- RBAC: sales denied ----------
@pytest.mark.parametrize("path,method,body", [
    ("/api/wa/setup/diagnose", "POST", None),
    ("/api/wa/setup/register", "POST", {"pin": "123456"}),
    ("/api/wa/setup/request-code", "POST", {"method": "SMS"}),
    ("/api/wa/setup/verify-code", "POST", {"code": "1234"}),
    ("/api/wa/setup/subscribe", "POST", None),
    ("/api/wa/setup/webhook-guide", "GET", None),
    ("/api/wa/setup/handshake", "POST", {"public_base": "https://x.example"}),
])
def test_rbac_sales_denied(sales, path, method, body):
    if method == "GET":
        r = sales.get(f"{BASE_URL}{path}", timeout=15)
    else:
        r = sales.post(f"{BASE_URL}{path}", json=(body or {}), timeout=15)
    assert r.status_code == 403, f"{path} → {r.status_code} {r.text[:200]}"
