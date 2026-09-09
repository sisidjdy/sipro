import os
import pytest
import requests
from dotenv import dotenv_values

_base = os.environ.get("REACT_APP_BACKEND_URL") or dotenv_values("/app/frontend/.env").get("REACT_APP_BACKEND_URL")
if not _base:
    raise RuntimeError("REACT_APP_BACKEND_URL wajib tersedia untuk pengujian end-to-end.")
BASE_URL = _base.rstrip("/")
# Banyak modul uji lama menyimpan URL pratinjau pod yang sudah mati sebagai bawaan; conftest
# dimuat lebih dulu, jadi env ini menjadi SATU sumber URL untuk seluruh suite.
os.environ.setdefault("REACT_APP_BACKEND_URL", BASE_URL)
PASS = "Sipro#2026"


def _login(email: str):
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": email, "password": PASS}, timeout=15)
    if r.status_code != 200:
        pytest.skip(f"login {email} failed: {r.status_code} {r.text[:200]}")
    return r.json()["access_token"]


@pytest.fixture(scope="session")
def base_url():
    return BASE_URL


@pytest.fixture(scope="session", autouse=True)
def _lepaskan_reservasi_unit_uji():
    """Akhir sesi: reservasi yang masih menggantung pada UNIT UJI (kode UJI*) dibatalkan lewat
    API supaya tidak menyesatkan kartu Master Proyek/BI; begitu pula reservasi oleh LEAD UJI
    (nama UJI*/Uji */TEST_*) pada unit demo. Reservasi pembeli demo asli tidak disentuh."""
    yield
    try:
        r = requests.post(f"{BASE_URL}/api/auth/login",
                          json={"email": "superadmin@sipro.co.id", "password": PASS}, timeout=15)
        if r.status_code != 200:
            return
        h = {"Authorization": f"Bearer {r.json()['access_token']}"}
        deals = requests.get(f"{BASE_URL}/api/deals", params={"status": "reserved", "limit": 500},
                             headers=h, timeout=60).json().get("data") or []
        import re
        uji = re.compile(r"^(UJI|Uji|TEST_|Test )")
        for d in deals:
            if str(d.get("unit_code") or "").upper().startswith("UJI") or uji.match(str(d.get("lead_name") or "")):
                requests.post(f"{BASE_URL}/api/deals/{d['id']}/cancel", headers=h,
                              json={"note": "cleanup akhir sesi uji"}, timeout=30)
    except Exception:  # noqa: BLE001
        pass


@pytest.fixture(scope="session")
def tok_finance():
    return _login("finance@sipro.co.id")


@pytest.fixture(scope="session")
def tok_finlead():
    return _login("finlead@sipro.co.id")


@pytest.fixture(scope="session")
def tok_sales():
    return _login("sales@sipro.co.id")


@pytest.fixture(scope="session")
def tok_owner():
    return _login("owner@sipro.co.id")


def _sess(tok):
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {tok}", "Content-Type": "application/json"})
    return s


@pytest.fixture
def s_finance(tok_finance):
    return _sess(tok_finance)


@pytest.fixture
def s_finlead(tok_finlead):
    return _sess(tok_finlead)


@pytest.fixture
def s_sales(tok_sales):
    return _sess(tok_sales)


@pytest.fixture
def s_owner(tok_owner):
    return _sess(tok_owner)
