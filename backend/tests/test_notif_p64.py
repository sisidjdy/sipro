"""Tests for Fase 64 — pusat notifikasi (state, kategori, auto-resolve, dismiss).

Isolasi: WAJIB memulihkan data demo persis seperti semula bila mengubah dokumen.
Test ini melakukan snapshot & restore secara eksplisit. Akses DB memakai pymongo (sync)
untuk menghindari konflik event-loop dengan motor.
"""
import os
import requests
import pytest
from pymongo import MongoClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL",
                          "https://warning-letters-1.preview.emergentagent.com").rstrip("/")
PW = "Sipro#2026"

# ambil MONGO_URL / DB_NAME dari backend/.env (source of truth)
def _load_env():
    with open("/app/backend/.env") as f:
        for line in f:
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"'))

_load_env()
MONGO = MongoClient(os.environ["MONGO_URL"])
DB = MONGO[os.environ["DB_NAME"]]


def login(email: str) -> str:
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": email, "password": PW}, timeout=30)
    assert r.status_code == 200, f"login {email}: {r.status_code} {r.text}"
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def owner_headers():
    return {"Authorization": f"Bearer {login('owner@sipro.co.id')}"}


@pytest.fixture(scope="module")
def sales_headers():
    return {"Authorization": f"Bearer {login('sales@sipro.co.id')}"}


# ---------------------------------------------------------------- kontrak dasar
def test_notifications_shape(owner_headers):
    r = requests.get(f"{BASE_URL}/api/notifications", headers=owner_headers,
                     params={"state": "all", "limit": 50}, timeout=30)
    assert r.status_code == 200, r.text
    j = r.json()
    assert set(["data", "total", "unread", "summary", "auto_resolved"]).issubset(j.keys())
    s = j["summary"]
    assert set(["per_category", "unread", "read", "needs_action", "total"]).issubset(s.keys())
    for k in ("tugas", "keuangan", "penjualan", "proyek", "layanan", "sebutan", "sistem"):
        assert k in s["per_category"]
    for row in j["data"][:20]:
        assert "category" in row and row["category"]
        assert "needs_action" in row
        assert "link" in row


def test_state_tab_action_only_needs_action(owner_headers):
    r = requests.get(f"{BASE_URL}/api/notifications", headers=owner_headers,
                     params={"state": "action", "limit": 100}, timeout=30)
    assert r.status_code == 200
    for row in r.json()["data"]:
        assert row["needs_action"] is True
        assert not row.get("resolved_at")
        assert row["read"] is False


def test_state_tab_read_only_read(owner_headers):
    r = requests.get(f"{BASE_URL}/api/notifications", headers=owner_headers,
                     params={"state": "read", "limit": 100}, timeout=30)
    assert r.status_code == 200
    for row in r.json()["data"]:
        assert row["read"] is True


def test_category_filter(owner_headers):
    r = requests.get(f"{BASE_URL}/api/notifications", headers=owner_headers,
                     params={"state": "all", "category": "keuangan", "limit": 100},
                     timeout=30)
    assert r.status_code == 200
    for row in r.json()["data"]:
        assert row["category"] == "keuangan"


def test_search_filter(owner_headers):
    r = requests.get(f"{BASE_URL}/api/notifications", headers=owner_headers,
                     params={"state": "all", "q": "tugas", "limit": 20}, timeout=30)
    assert r.status_code == 200
    for row in r.json()["data"]:
        blob = (row.get("title", "") + " " + row.get("body", "")).lower()
        assert "tugas" in blob


def test_unread_only_still_supported(owner_headers):
    r = requests.get(f"{BASE_URL}/api/notifications", headers=owner_headers,
                     params={"unread_only": "true", "limit": 20}, timeout=30)
    assert r.status_code == 200
    for row in r.json()["data"]:
        assert row["read"] is False


def test_link_by_type(owner_headers):
    r = requests.get(f"{BASE_URL}/api/notifications", headers=owner_headers,
                     params={"state": "all", "limit": 200}, timeout=30)
    rows = r.json()["data"]
    task_rows = [x for x in rows if x.get("type") == "task"]
    if task_rows:
        assert all(x["link"] == "/tasks" for x in task_rows)
    for x in rows:
        if x.get("link"):
            assert x["link"].startswith("/")


def test_mark_read_then_shows_in_read_tab(owner_headers):
    r = requests.get(f"{BASE_URL}/api/notifications", headers=owner_headers,
                     params={"state": "unread", "limit": 5}, timeout=30)
    unread = r.json()["data"]
    if not unread:
        pytest.skip("no unread")
    target = unread[0]
    r2 = requests.post(f"{BASE_URL}/api/notifications/{target['id']}/read",
                       headers=owner_headers, timeout=30)
    assert r2.status_code == 200
    r3 = requests.get(f"{BASE_URL}/api/notifications", headers=owner_headers,
                      params={"state": "read", "limit": 500}, timeout=30)
    ids = [x["id"] for x in r3.json()["data"]]
    assert target["id"] in ids
    # PULIHKAN
    DB.notifications.update_one({"id": target["id"]},
                                {"$set": {"read": False, "read_at": None}})


def test_dismiss_removes_from_list(owner_headers):
    r = requests.get(f"{BASE_URL}/api/notifications", headers=owner_headers,
                     params={"state": "read", "limit": 5}, timeout=30)
    rows = r.json()["data"]
    if not rows:
        pytest.skip("no read notifs")
    target = rows[0]
    snap = DB.notifications.find_one({"id": target["id"]},
                                     {"_id": 0, "dismissed_at": 1, "read": 1,
                                      "read_at": 1})
    r2 = requests.post(f"{BASE_URL}/api/notifications/{target['id']}/dismiss",
                       headers=owner_headers, timeout=30)
    assert r2.status_code == 200
    # verify not in list
    r3 = requests.get(f"{BASE_URL}/api/notifications", headers=owner_headers,
                      params={"state": "all", "limit": 500}, timeout=30)
    assert target["id"] not in [x["id"] for x in r3.json()["data"]]
    # PULIHKAN
    DB.notifications.update_one({"id": target["id"]}, {"$set": snap})


def test_auto_resolve_when_task_closed():
    """Tutup tugas milik owner yang punya notifikasi 'Tugas baru: …',
    panggil GET, verify auto_resolved >= 1, lalu PULIHKAN."""
    rows = list(DB.notifications.find(
        {"user_email": "owner@sipro.co.id", "type": "task",
         "resolved_at": None, "title": {"$regex": "^Tugas baru: "}},
        {"_id": 0, "id": 1, "title": 1}).limit(50))
    titles = list({r["title"][len("Tugas baru: "):].strip() for r in rows})
    if not titles:
        pytest.skip("no task notifs")
    task_snap = list(DB.tasks.find(
        {"assigned_to": "owner@sipro.co.id", "title": {"$in": titles},
         "status": {"$nin": ["done", "closed", "cancelled", "verified"]}},
        {"_id": 0, "id": 1, "status": 1}))
    if not task_snap:
        # Notifs exist but tasks all closed/missing → should already be resolved
        # panggil GET dan cek auto_resolved
        tok = login("owner@sipro.co.id")
        hdr = {"Authorization": f"Bearer {tok}"}
        r = requests.get(f"{BASE_URL}/api/notifications", headers=hdr,
                         params={"state": "action", "limit": 1}, timeout=30)
        # Auto-resolve mungkin sudah dijalankan sebelumnya; test lolos
        pytest.skip("no open tasks matching notif titles")

    DB.tasks.update_many({"id": {"$in": [t["id"] for t in task_snap]}},
                         {"$set": {"status": "done"}})
    notif_ids = [r["id"] for r in rows]
    try:
        tok = login("owner@sipro.co.id")
        hdr = {"Authorization": f"Bearer {tok}"}
        before = requests.get(f"{BASE_URL}/api/notifications", headers=hdr,
                              params={"state": "action", "limit": 1}, timeout=30).json()
        # panggil kedua untuk memicu resolve_done
        r = requests.get(f"{BASE_URL}/api/notifications", headers=hdr,
                         params={"state": "action", "limit": 1}, timeout=30)
        j = r.json()
        # auto_resolved bisa 0 pada panggilan kedua bila sudah tercabut di panggilan pertama.
        assert (before.get("auto_resolved", 0) >= 1) or (j.get("auto_resolved", 0) >= 1), \
            f"auto_resolved sum: {before.get('auto_resolved')} + {j.get('auto_resolved')}"
        # verifikasi notif di DB memang resolved dengan alasan yang benar
        resolved = DB.notifications.count_documents(
            {"id": {"$in": notif_ids},
             "resolved_reason": "tugasnya sudah tidak terbuka lagi"})
        assert resolved >= 1
    finally:
        # PULIHKAN persis seperti diminta pesan
        for t in task_snap:
            DB.tasks.update_one({"id": t["id"]}, {"$set": {"status": t["status"]}})
        DB.notifications.update_many(
            {"id": {"$in": notif_ids},
             "resolved_reason": "tugasnya sudah tidak terbuka lagi"},
            {"$set": {"resolved_at": None, "resolved_reason": None,
                      "read": False, "read_at": None}})


def test_user_isolation(sales_headers, owner_headers):
    r_sales = requests.get(f"{BASE_URL}/api/notifications", headers=sales_headers,
                           params={"state": "all", "limit": 200}, timeout=30)
    r_owner = requests.get(f"{BASE_URL}/api/notifications", headers=owner_headers,
                           params={"state": "all", "limit": 200}, timeout=30)
    sales_ids = {x["id"] for x in r_sales.json()["data"]}
    owner_ids = {x["id"] for x in r_owner.json()["data"]}
    assert not (sales_ids & owner_ids)


def test_clear_read_endpoint(owner_headers):
    before = list(DB.notifications.find(
        {"user_email": "owner@sipro.co.id", "read": True, "dismissed_at": None},
        {"_id": 0, "id": 1}))
    r = requests.post(f"{BASE_URL}/api/notifications/clear-read",
                      headers=owner_headers, timeout=30)
    assert r.status_code == 200
    cleared = r.json()["data"]["cleared"]
    assert cleared == len(before)
    # PULIHKAN
    ids = [x["id"] for x in before]
    if ids:
        DB.notifications.update_many({"id": {"$in": ids}},
                                     {"$set": {"dismissed_at": None}})
