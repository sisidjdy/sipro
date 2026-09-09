"""Fase 90 — phone-health duplicate/invalid samples, POST /master/phone-fix, kalender kupon (backend save)."""
import os
import uuid

import pytest
import requests
from dotenv import dotenv_values
from pymongo import MongoClient

fe = dotenv_values("/app/frontend/.env")
be = dotenv_values("/app/backend/.env")
BASE = (os.environ.get("REACT_APP_BACKEND_URL") or fe.get("REACT_APP_BACKEND_URL")).rstrip("/")
API = f"{BASE}/api"
PASSWORD = "Sipro#2026"
ORG = "org-sipro"

mc = MongoClient(be["MONGO_URL"])
mdb = mc[be["DB_NAME"]]


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


@pytest.fixture(scope="module")
def leads():
    """Suntik 3 lead uji: A (08129998877 → akan ganda), B ('0812-ABC' invalid), C (+628129998877)."""
    ids = {k: f"TEST-P90-{k}-{uuid.uuid4().hex[:8]}" for k in ("A", "B", "C")}
    mdb.leads.delete_many({"phone": {"$in": ["08129998877", "+628129998877", "0812-ABCxy"]},
                           "id": {"$regex": "^TEST-P90"}})
    docs = [
        {"id": ids["A"], "org_id": ORG, "name": "TEST_P90 Lead A", "phone": "08129998877",
         "stage": "new", "source": "walk_in"},
        {"id": ids["B"], "org_id": ORG, "name": "TEST_P90 Lead B", "phone": "0812-ABCxy",
         "stage": "new", "source": "walk_in"},
        {"id": ids["C"], "org_id": ORG, "name": "TEST_P90 Lead C", "phone": "+628129998877",
         "stage": "new", "source": "walk_in"},
    ]
    mdb.leads.insert_many(docs)
    yield ids
    mdb.leads.delete_many({"id": {"$in": list(ids.values())}})


@pytest.fixture(scope="module")
def free_phone():
    """Nomor 08xx yang belum dipakai lead mana pun."""
    for i in range(1000):
        cand = f"0813777{70000 + i}"
        if not mdb.leads.find_one({"phone": {"$in": [cand, "+62" + cand[1:]]}}):
            return cand
    pytest.fail("tidak menemukan nomor bebas")


def _health(s):
    r = s.get(f"{API}/master/phone-health", timeout=60)
    assert r.status_code == 200, r.text[:300]
    return r.json()["data"]


def _row(data, coll="leads"):
    return next(r for r in data["rows"] if r["collection"] == coll)


# ------------------------------------------------- GET /master/phone-health
class TestPhoneHealth:
    def test_structure(self, s):
        d = _health(s)
        for k in ("total_pending", "total_duplicate", "total_invalid", "rows"):
            assert k in d, f"field {k} hilang"
        assert d["rows"], "rows kosong"
        for r in d["rows"]:
            assert isinstance(r.get("duplicate_samples"), list), f"{r['collection']} duplicate_samples bukan list"
            assert isinstance(r.get("invalid_samples"), list), f"{r['collection']} invalid_samples bukan list"
            assert len(r["invalid_samples"]) <= 20 and len(r["duplicate_samples"]) <= 20

    def test_duplicate_and_invalid_samples(self, s, leads):
        d = _health(s)
        row = _row(d)
        assert row["duplicate"] >= 1, row
        dup = next((x for x in row["duplicate_samples"] if x["id"] == leads["A"]), None)
        assert dup, f"lead A tidak ada di duplicate_samples: {row['duplicate_samples']}"
        assert dup["normalized"] == "+628129998877"
        assert dup["clash_id"] == leads["C"], dup
        assert dup["clash_name"] == "TEST_P90 Lead C"
        assert row["invalid"] >= 1
        inv = next((x for x in row["invalid_samples"] if x["id"] == leads["B"]), None)
        assert inv, f"lead B tidak ada di invalid_samples: {row['invalid_samples']}"
        assert inv["phone"] == "0812-ABCxy"

    def test_invalid_not_counted_as_pending(self, s, leads):
        """'0812-ABC' harus masuk invalid, bukan pending."""
        d = _health(s)
        row = _row(d)
        ids_pending_free = {x["id"] for x in row["duplicate_samples"]} | {x["id"] for x in row["invalid_samples"]}
        assert leads["B"] in ids_pending_free


# ------------------------------------------------- POST /master/normalize-phones
class TestNormalize:
    def test_skips_duplicate_and_invalid(self, s, leads):
        r = s.post(f"{API}/master/normalize-phones", timeout=120)
        assert r.status_code == 200, r.text[:300]
        rep = r.json()["data"]["report"]
        lead_rep = rep.get("leads.phone", {})
        assert lead_rep.get("skipped_duplicate", 0) >= 1, rep
        a = mdb.leads.find_one({"id": leads["A"]}, {"_id": 0, "phone": 1})
        b = mdb.leads.find_one({"id": leads["B"]}, {"_id": 0, "phone": 1})
        assert a["phone"] == "08129998877", f"lead A seharusnya dilewati: {a}"
        assert b["phone"] == "0812-ABCxy", f"lead B (invalid) tidak boleh diubah: {b}"


# ------------------------------------------------- POST /master/phone-fix
class TestPhoneFix:
    def test_invalid_phone_400(self, s, leads):
        r = s.post(f"{API}/master/phone-fix",
                   json={"collection": "leads", "id": leads["B"], "phone": "xyz"}, timeout=60)
        assert r.status_code == 400, f"{r.status_code} {r.text[:300]}"

    def test_clash_409(self, s, leads):
        r = s.post(f"{API}/master/phone-fix",
                   json={"collection": "leads", "id": leads["B"], "phone": "+628129998877"}, timeout=60)
        assert r.status_code == 409, f"{r.status_code} {r.text[:300]}"

    def test_unknown_collection_400(self, s, leads):
        r = s.post(f"{API}/master/phone-fix",
                   json={"collection": "nope", "id": leads["B"], "phone": "081377776666"}, timeout=60)
        assert r.status_code == 400, r.text[:300]

    def test_missing_id_404(self, s):
        r = s.post(f"{API}/master/phone-fix",
                   json={"collection": "leads", "id": "no-such-id", "phone": "081377776666"}, timeout=60)
        assert r.status_code == 404, r.text[:300]

    def test_sales_forbidden(self, sales, leads):
        r = sales.post(f"{API}/master/phone-fix",
                       json={"collection": "leads", "id": leads["B"], "phone": "081377776666"}, timeout=60)
        assert r.status_code == 403, f"{r.status_code} {r.text[:300]}"

    def test_fix_success_and_persist(self, s, leads, free_phone):
        r = s.post(f"{API}/master/phone-fix",
                   json={"collection": "leads", "id": leads["B"], "phone": free_phone}, timeout=90)
        assert r.status_code == 200, r.text[:300]
        body = r.json()
        expect = "+62" + free_phone[1:]
        assert body["message"] == f"Nomor diperbarui menjadi {expect}.", body["message"]
        after = body["data"]["after"]
        assert "rows" in after and "total_invalid" in after
        row = _row(after)
        assert all(x["id"] != leads["B"] for x in row["invalid_samples"]), row["invalid_samples"]
        doc = mdb.leads.find_one({"id": leads["B"]}, {"_id": 0, "phone": 1})
        assert doc["phone"] == expect, doc

    def test_clear_phone(self, s, leads):
        r = s.post(f"{API}/master/phone-fix",
                   json={"collection": "leads", "id": leads["B"], "phone": ""}, timeout=90)
        assert r.status_code == 200, r.text[:300]
        assert r.json()["message"] == "Nomor dihapus dari baris."
        doc = mdb.leads.find_one({"id": leads["B"]}, {"_id": 0, "phone": 1})
        assert doc["phone"] is None, doc

    def test_fix_duplicate_lead_a(self, s, leads):
        """Lead A yang 'akan ganda' bisa diselesaikan dengan nomor unik."""
        r = s.post(f"{API}/master/phone-fix",
                   json={"collection": "leads", "id": leads["A"], "phone": "081355554" + "444"}, timeout=90)
        assert r.status_code == 200, r.text[:300]
        row = _row(r.json()["data"]["after"])
        assert all(x["id"] != leads["A"] for x in row["duplicate_samples"]), row["duplicate_samples"]


# ------------------------------------------------- kupon dengan tanggal (dipakai UI DatePickerField)
class TestCouponDates:
    def test_create_and_update_coupon_with_dates(self, s):
        payload = {"code": "UJI-P90-BE", "name": "TEST_P90 Kupon", "kind": "percent",
                   "value": 5, "valid_from": "2026-06-15", "valid_until": "2026-07-15",
                   "active": True}
        mdb.coupons.delete_many({"code": "UJI-P90-BE"})
        r = s.post(f"{API}/pricing/coupons", json=payload, timeout=60)
        assert r.status_code in (200, 201), r.text[:400]
        rid = r.json()["data"]["id"]
        g = s.get(f"{API}/pricing/coupons", timeout=60)
        assert g.status_code == 200
        d = g.json()["data"]
        items = d.get("items") if isinstance(d, dict) else d
        mine = next((x for x in items if x["id"] == rid), None)
        assert mine, "kupon baru tidak ditemukan di listing"
        assert mine["valid_from"].startswith("2026-06-15"), mine["valid_from"]
        assert mine["valid_until"].startswith("2026-07-15"), mine["valid_until"]
        u = s.put(f"{API}/pricing/coupons/{rid}", json={"active": False}, timeout=60)
        assert u.status_code == 200, u.text[:300]
        mdb.coupons.delete_one({"id": rid})
