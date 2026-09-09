"""Fase 89 — skor lead berbasis event terkonfigurasi, kupon bersasaran, rapikan nomor telepon."""
import os
import random
import subprocess

import pytest
import requests
from dotenv import dotenv_values

fe = dotenv_values("/app/frontend/.env")
BASE = (os.environ.get("REACT_APP_BACKEND_URL") or fe.get("REACT_APP_BACKEND_URL")).rstrip("/")
API = f"{BASE}/api"
PASSWORD = "Sipro#2026"

SYSTEM_KEYS = {"base", "source", "new_24h", "first_contact", "stage_nurturing", "stage_appointment",
               "stage_booking", "stage_won", "activity", "appointment_scheduled",
               "appointment_done", "inbound_reply", "disposition_positive", "disposition_negative",
               "disposition_no_response", "idle", "closed"}


def _login(email):
    ses = requests.Session()
    r = ses.post(f"{API}/auth/login", json={"email": email, "password": PASSWORD}, timeout=60)
    if r.status_code != 200:
        pytest.fail(f"login {email} gagal {r.status_code}: {r.text[:300]}")
    tok = (r.json().get("data") or {}).get("token") or r.json().get("token")
    if tok:
        ses.headers.update({"Authorization": f"Bearer {tok}"})
    return ses


@pytest.fixture(scope="session")
def s():
    return _login("superadmin@sipro.co.id")


@pytest.fixture(scope="session")
def sales():
    return _login("sales@sipro.co.id")


@pytest.fixture(scope="session")
def a_lead(s):
    r = s.get(f"{API}/leads", params={"limit": 5}, timeout=60)
    assert r.status_code == 200, r.text[:300]
    d = r.json().get("data")
    items = d.get("items") if isinstance(d, dict) else d
    assert items, "tidak ada lead untuk diuji"
    return items[0]


# ------------------------------------------------- konfigurasi event skor
class TestLeadScoreEvents:
    def test_get_events(self, s):
        r = s.get(f"{API}/lead-score/events", timeout=60)
        assert r.status_code == 200, r.text[:300]
        d = r.json()["data"]
        keys = {e["key"] for e in d["events"]}
        assert SYSTEM_KEYS <= keys, f"event sistem kurang: {SYSTEM_KEYS - keys}"
        assert len([e for e in d["events"] if e["kind"] == "system"]) >= 17
        assert d["bands"] and "hot_min" in d["bands"] and "warm_min" in d["bands"]
        assert len(d["defaults"]) == 17
        for e in d["events"]:
            assert {"key", "label", "points", "active", "kind", "params"} <= set(e)

    def test_put_events_and_custom(self, s):
        r = s.get(f"{API}/lead-score/events", timeout=60)
        events = r.json()["data"]["events"]
        payload = [{"key": e["key"], "label": e["label"], "points": e["points"],
                    "active": e.get("active", True), "desc": e.get("desc") or "",
                    "params": e.get("params") or {}} for e in events if e["kind"] == "system"]
        for e in payload:
            if e["key"] == "idle":
                e["points"] = -8
                e["params"] = {"threshold_days": 5, "cap": 40}
        payload.append({"key": "open_house", "label": "Hadir open house", "points": 12,
                        "active": True, "params": {"window_days": 0, "cap": 0}})
        r = s.put(f"{API}/lead-score/events", json={"events": payload}, timeout=60)
        assert r.status_code == 200, r.text[:400]

        r = s.get(f"{API}/lead-score/events", timeout=60)
        by = {e["key"]: e for e in r.json()["data"]["events"]}
        assert by["idle"]["points"] == -8
        assert by["idle"]["params"]["threshold_days"] == 5
        assert by["idle"]["params"]["cap"] == 40
        assert by["open_house"]["kind"] == "custom"
        assert by["open_house"]["points"] == 12
        assert by["open_house"]["label"] == "Hadir open house"

    def test_put_invalid_custom_key(self, s):
        bad = [{"key": "Open House!", "label": "Salah", "points": 5, "active": True, "params": {}}]
        r = s.put(f"{API}/lead-score/events", json={"events": bad}, timeout=60)
        assert r.status_code == 400, f"harus 400, dapat {r.status_code}: {r.text[:300]}"

    def test_put_duplicate_key(self, s):
        dup = [{"key": "open_house", "label": "A", "points": 5, "active": True, "params": {}},
               {"key": "open_house", "label": "B", "points": 6, "active": True, "params": {}}]
        r = s.put(f"{API}/lead-score/events", json={"events": dup}, timeout=60)
        assert r.status_code == 400, f"harus 400, dapat {r.status_code}: {r.text[:300]}"

    def test_log_custom_event_on_lead(self, s, a_lead):
        lid = a_lead["id"]
        r = s.get(f"{API}/leads/{lid}/score", timeout=60)
        assert r.status_code == 200, r.text[:300]
        d = r.json()["data"]
        assert any(e["key"] == "open_house" for e in d.get("custom_events") or []), \
            "custom_events tidak memuat open_house"
        before = next((x["points"] for x in d["score_breakdown"] if x["key"] == "open_house"), 0)

        r = s.post(f"{API}/leads/{lid}/score-events",
                   json={"event_key": "open_house", "note": "x"}, timeout=60)
        assert r.status_code == 200, r.text[:400]
        rows = r.json()["data"]["score_breakdown"]
        row = next((x for x in rows if x["key"] == "open_house"), None)
        assert row, f"breakdown tanpa open_house: {rows}"
        assert row["points"] - before == 12, f"delta poin salah: {before} -> {row['points']}"

    def test_log_unknown_event(self, s, a_lead):
        r = s.post(f"{API}/leads/{a_lead['id']}/score-events",
                   json={"event_key": "tidak_ada_event"}, timeout=60)
        assert r.status_code == 400, f"harus 400, dapat {r.status_code}: {r.text[:300]}"

    def test_rescore_all(self, s):
        r = s.post(f"{API}/lead-score/rescore-all", timeout=180)
        assert r.status_code == 200, r.text[:400]
        assert "message" in r.json()
        assert "total" in r.json()["data"]

    def test_reset_events(self, s):
        r = s.post(f"{API}/lead-score/events/reset", timeout=60)
        assert r.status_code == 200, r.text[:300]
        r = s.get(f"{API}/lead-score/events", timeout=60)
        by = {e["key"]: e for e in r.json()["data"]["events"]}
        assert "open_house" not in by, "event kustom masih ada setelah reset"
        assert by["idle"]["points"] == -5

    def test_rbac_sales_cannot_manage(self, sales):
        r = sales.put(f"{API}/lead-score/events", json={"events": []}, timeout=60)
        assert r.status_code == 403, f"harus 403, dapat {r.status_code}"


# ------------------------------------------------- kesehatan nomor telepon
class TestPhoneHealth:
    EXPECTED = {"leads", "customers", "portal_users", "conversations",
                "broadcast_recipients", "users", "vendors"}

    def test_phone_health_shape(self, s):
        r = s.get(f"{API}/master/phone-health", timeout=90)
        assert r.status_code == 200, r.text[:300]
        d = r.json()["data"]
        colls = {row["collection"] for row in d["rows"]}
        assert self.EXPECTED <= colls, f"koleksi kurang: {self.EXPECTED - colls}"
        for row in d["rows"]:
            assert {"pending", "duplicate", "invalid", "field"} <= set(row)
        assert isinstance(d["total_pending"], int)

    def test_normalize_phones(self, s, a_lead):
        lid = a_lead["id"]
        # nomor acak supaya bentuk +62-nya tidak bentrok dengan data lain (kalau bentrok,
        # baris dihitung sebagai `duplicate`, bukan `pending`).
        raw = "08" + str(random.randint(1000000000, 1999999999))
        norm = "+62" + raw[1:]
        out = subprocess.run(
            ["mongosh", "--quiet", "test_database", "--eval",
             f'db.leads.updateOne({{id:"{lid}"}},{{$set:{{phone:"{raw}"}}}}).modifiedCount'],
            capture_output=True, text=True, timeout=60)
        assert out.returncode == 0, out.stderr[:300]

        r = s.get(f"{API}/master/phone-health", timeout=90)
        assert r.json()["data"]["total_pending"] >= 1, "total_pending harus >= 1"

        r = s.post(f"{API}/master/normalize-phones", timeout=180)
        assert r.status_code == 200, r.text[:400]
        assert "nomor dirapikan ke +62" in r.json()["message"], r.json()["message"]

        chk = subprocess.run(
            ["mongosh", "--quiet", "test_database", "--eval",
             f'db.leads.findOne({{id:"{lid}"}}).phone'],
            capture_output=True, text=True, timeout=60)
        assert norm in chk.stdout, f"phone tidak dinormalisasi: {chk.stdout[:200]}"

    def test_normalize_phones_forbidden_for_sales(self, sales):
        r = sales.post(f"{API}/master/normalize-phones", timeout=90)
        assert r.status_code == 403, f"harus 403, dapat {r.status_code}: {r.text[:200]}"


# ------------------------------------------------- kupon bersasaran potongan
class TestCouponTarget:
    """Fase 89: kupon punya sasaran potongan (price/dp/booking_fee/cost)."""

    def _create(self, s, **extra):
        payload = {"code": f"UJI-DP-89-{random.randint(1000, 9999)}", "name": "TEST_Uji DP 89",
                   "kind": "amount", "value": 5000000, "target": "dp", "active": True}
        payload.update(extra)
        return payload, s.post(f"{API}/pricing/coupons", json=payload, timeout=60)

    def test_create_coupon_with_target_dp(self, s):
        payload, r = self._create(s)
        assert r.status_code in (200, 201), r.text[:400]
        row = r.json()["data"]
        assert row["target"] == "dp"
        rid = row["id"]
        lst = s.get(f"{API}/pricing/coupons", timeout=60)
        assert lst.status_code == 200
        found = next((x for x in lst.json()["data"] if x["id"] == rid), None)
        assert found and found["target"] == "dp", "kupon target dp tidak persist"
        assert found["code"] == payload["code"]

    def test_coupon_target_cost_requires_component(self, s):
        _, r = self._create(s, target="cost")
        assert r.status_code in (400, 422), f"harus ditolak, dapat {r.status_code}"
        _, r = self._create(s, target="cost", target_component="SEMEN")
        assert r.status_code in (200, 201), r.text[:300]
        assert r.json()["data"]["target_component"] == "SEMEN"

    def test_coupon_invalid_target(self, s):
        _, r = self._create(s, target="tidak_ada")
        assert r.status_code in (400, 422), f"harus ditolak, dapat {r.status_code}"
