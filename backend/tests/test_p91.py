"""Fase 91: finance drilldown, doc-history, PDF download."""
import urllib.parse

import pytest
import requests
from dotenv import dotenv_values

BASE_URL = (dotenv_values("/app/frontend/.env").get("REACT_APP_BACKEND_URL") or "").rstrip("/")
API = f"{BASE_URL}/api"
PASS = "Sipro#2026"
# ID pembeli/lead demo unit A-01 diselesaikan dari API (bukan ID basis data lama yang mati).
CUST_ID = None
LEAD_ID = None
KEYS = ["ar_outstanding", "ar_overdue", "ap_outstanding", "ap_pending",
        "contract_liability", "customer_deposits", "revenue_recognized"]


def _sess(email):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": PASS}, timeout=20)
    assert r.status_code == 200, f"login failed {r.status_code} {r.text[:200]}"
    tok = r.json().get("access_token")
    if tok:
        s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


@pytest.fixture(scope="module")
def sa():
    s = _sess("superadmin@sipro.co.id")
    global CUST_ID, LEAD_ID
    deals = s.get(f"{API}/deals", params={"limit": 200}, timeout=40).json().get("data") or []
    demo = next((d for d in deals if d.get("unit_code") == "A-01" and d.get("customer_id")), None)
    if not demo:
        pytest.skip("deal demo A-01 dengan pembeli tidak ada di lingkungan ini")
    CUST_ID, LEAD_ID = demo["customer_id"], demo["lead_id"]
    return s


@pytest.fixture(scope="module")
def sales():
    return _sess("sales@sipro.co.id")


# --- finance drilldown ---
class TestDrilldown:
    @pytest.mark.parametrize("key", KEYS)
    def test_keys(self, sa, key):
        r = sa.get(f"{API}/finance/drilldown/{key}", timeout=30)
        assert r.status_code == 200, r.text[:300]
        d = r.json().get("data", r.json())
        assert d["key"] == key
        assert isinstance(d["title"], str) and d["title"]
        assert isinstance(d["rows"], list)
        assert d["count"] == len(d["rows"])
        assert d["total"] == sum(x["amount"] for x in d["rows"])
        assert d["href_all"]
        for row in d["rows"]:
            assert row["id"] and row["title"] and row["href"] is not None
            assert isinstance(row["amount"], int)

    def test_ar_bucket(self, sa):
        r = sa.get(f"{API}/finance/drilldown/ar_bucket", params={"bucket": "1-30"}, timeout=30)
        assert r.status_code == 200, r.text[:300]
        d = r.json().get("data", r.json())
        assert "1-30" in d["title"]

    def test_ap_bucket_encoded(self, sa):
        url = f"{API}/finance/drilldown/ap_bucket?bucket={urllib.parse.quote('>90')}"
        r = sa.get(url, timeout=30)
        assert r.status_code == 200, r.text[:300]
        d = r.json().get("data", r.json())
        assert ">90" in d["title"]

    def test_totals_match_summary(self, sa):
        s = sa.get(f"{API}/finance/summary", timeout=30)
        assert s.status_code == 200, s.text[:300]
        sm = s.json().get("data", s.json())
        for key in ("ar_outstanding", "ar_overdue"):
            d = sa.get(f"{API}/finance/drilldown/{key}", timeout=30).json()
            d = d.get("data", d)
            assert d["total"] == int(sm[key]), f"{key}: drilldown {d['total']} vs summary {sm[key]}"

    def test_unknown_key_404(self, sa):
        r = sa.get(f"{API}/finance/drilldown/bogus_key", timeout=30)
        assert r.status_code == 404, r.status_code


# --- doc history ---
@pytest.fixture(scope="module")
def cust_history(sa):
    r = sa.get(f"{API}/doc-history/customer/{CUST_ID}", timeout=40)
    assert r.status_code == 200, r.text[:300]
    return r.json().get("data", r.json())


def _booked_deal(hist):
    """Deal demo yang sudah booked (fixture lain bisa menambah reservasi pada lead yang sama)."""
    return next(d for d in hist["deals"] if d.get("deal_status") == "booked")


class TestDocHistory:
    def test_stages(self, cust_history):
        deals = cust_history["deals"]
        assert deals, "no deals for customer"
        d0 = _booked_deal(cust_history)
        assert d0["unit_code"] == "A-01", d0["unit_code"]
        keys = [s["key"] for s in d0["stages"]]
        assert keys == ["booking", "spr", "billing", "tax", "legal", "bast"], keys
        for s in d0["stages"]:
            assert s["state"] in ("done", "active", "locked", "blocked"), s
            for doc in s["docs"]:
                for f in ("kind", "label", "number", "status", "issued_at", "actor", "pdf_url"):
                    assert f in doc, (s["key"], f)
            for a in s["actions"]:
                assert set(["key", "label", "enabled", "reason"]).issubset(a.keys())

    def test_bast_blocked_reason(self, cust_history):
        st = next(s for s in _booked_deal(cust_history)["stages"] if s["key"] == "bast")
        act = next(a for a in st["actions"] if a["key"] == "bast")
        assert act["enabled"] is False
        assert "Sisa tagihan" in (act["reason"] or "") and "belum lunas" in (act["reason"] or ""), act["reason"]

    def test_spr_stage(self, cust_history):
        st = next(s for s in _booked_deal(cust_history)["stages"] if s["key"] == "spr")
        numbers = [d["number"] for d in st["docs"]]
        assert "SPR/2026/0001" in numbers, numbers
        act = next((a for a in st["actions"] if "Surat Pesanan Rumah" in a["label"] and "KPR" in a["label"]), None)
        assert act is not None, [a["label"] for a in st["actions"]]
        assert act["enabled"] is True or "Sudah terbit" in (act["reason"] or ""), act

    def test_lead_history_same(self, sa, cust_history):
        r = sa.get(f"{API}/doc-history/lead/{LEAD_ID}", timeout=40)
        assert r.status_code == 200, r.text[:300]
        d = r.json().get("data", r.json())
        assert [x["deal_id"] for x in d["deals"]] == [x["deal_id"] for x in cust_history["deals"]]

    def test_bad_entity_type(self, sa):
        r = sa.get(f"{API}/doc-history/project/{CUST_ID}", timeout=30)
        assert r.status_code == 400, r.status_code

    def test_sales_can_read_lead(self, sales):
        r = sales.get(f"{API}/doc-history/lead/{LEAD_ID}", timeout=40)
        assert r.status_code == 200, f"{r.status_code} {r.text[:200]}"


# --- pdf downloads referenced by doc-history ---
class TestPdfs:
    def test_all_pdf_urls(self, sa, cust_history):
        urls = []
        for d in cust_history["deals"]:
            for s in d["stages"]:
                for doc in s["docs"]:
                    if doc.get("pdf_url"):
                        urls.append((s["key"], doc["label"], doc["pdf_url"]))
        assert urls, "no pdf_url found in doc history"
        failures = []
        for stage, label, u in urls:
            r = sa.get(f"{API}{u}", timeout=60)
            ct = r.headers.get("content-type", "")
            if r.status_code != 200 or "application/pdf" not in ct:
                failures.append(f"{stage}/{label} {u} -> {r.status_code} {ct} {r.text[:120] if r.status_code!=200 else ''}")
        assert not failures, failures
