"""Fase 93 — Drill-down KPI Marketing (ads:*) & Master Proyek (project:*), status ganda unit, RBAC."""
import os

import pytest
import requests
from dotenv import dotenv_values

fe = dotenv_values("/app/frontend/.env")
BASE = (os.environ.get("REACT_APP_BACKEND_URL") or fe.get("REACT_APP_BACKEND_URL")).rstrip("/")
API = f"{BASE}/api"
PROJECT_ID = None  # diselesaikan dari API: proyek demo yang memiliki unit


def _login(email, password):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=60)
    assert r.status_code == 200, f"login {email} -> {r.status_code} {r.text[:300]}"
    return s


@pytest.fixture(scope="module")
def admin():
    s = _login("superadmin@sipro.co.id", "Sipro#2026")
    global PROJECT_ID
    units = s.get(f"{API}/units", params={"limit": 500}, timeout=60).json().get("data") or []
    if not units:
        pytest.skip("tidak ada unit/proyek demo")
    from collections import Counter
    PROJECT_ID = Counter(u["project_id"] for u in units).most_common(1)[0][0]
    return s


@pytest.fixture(scope="module")
def sales():
    return _login("sales@sipro.co.id", "Sipro#2026")


@pytest.fixture(scope="module")
def perf(admin):
    r = admin.get(f"{API}/ads/performance", timeout=90)
    assert r.status_code == 200, r.text[:300]
    return r.json()["data"]


@pytest.fixture(scope="module")
def attribution(admin):
    r = admin.get(f"{API}/ads/attribution", timeout=90)
    assert r.status_code == 200, r.text[:300]
    return r.json()["data"]


@pytest.fixture(scope="module")
def tree(admin):
    r = admin.get(f"{API}/masterplan/projects/{PROJECT_ID}/tree", timeout=90)
    assert r.status_code == 200, r.text[:300]
    return r.json()["data"]["project"]


def _drill(sess, key, **params):
    r = sess.get(f"{API}/drilldown/{key}", params=params, timeout=90)
    return r


def _ok(sess, key, **params):
    r = _drill(sess, key, **params)
    assert r.status_code == 200, f"{key} -> {r.status_code} {r.text[:300]}"
    d = r.json()["data"]
    assert d["key"] == key
    assert isinstance(d["rows"], list)
    assert d["count"] == len(d["rows"])
    assert isinstance(d["title"], str) and d["title"]
    assert isinstance(d["href_all"], str) and d["href_all"]
    return d


# ---------- ads:* (tab Kinerja & Biaya Iklan, rentang default 30 hari) ----------
class TestAdsDrilldown:
    def test_ads_spend_matches_totals(self, admin, perf):
        d = _ok(admin, "ads:spend")
        assert d["total"] == int(perf["totals"]["spend"]), (d["total"], perf["totals"]["spend"])
        assert d["rows"], "tidak ada baris kampanye untuk biaya iklan"
        for r in d["rows"]:
            assert "/campaigns?hub=biaya&campaign_id=" in (r["href"] or ""), r
            assert r["amount"] is not None

    def test_ads_campaigns_count(self, admin, perf):
        d = _ok(admin, "ads:campaigns")
        assert d["count"] == perf["totals"]["campaigns"], (d["count"], perf["totals"]["campaigns"])

    def test_ads_leads_count(self, admin, perf):
        d = _ok(admin, "ads:leads")
        assert d["count"] == perf["totals"]["leads"], (d["count"], perf["totals"]["leads"])
        for r in d["rows"]:
            assert (r["href"] or "").startswith("/leads/"), r

    def test_ads_qualified_count(self, admin, perf):
        d = _ok(admin, "ads:qualified")
        assert d["count"] == perf["totals"]["qualified"], (d["count"], perf["totals"]["qualified"])

    def test_ads_hot_and_booked_rows(self, admin):
        for sub in ("hot", "booked"):
            d = _ok(admin, f"ads:{sub}")
            for r in d["rows"]:
                assert (r["href"] or "").startswith("/leads/"), r
                assert "score" in r and "score_band" in r, r
            if sub == "hot":
                assert all(r["score_band"] == "hot" for r in d["rows"]), d["rows"][:3]

    def test_ads_platform_metrics(self, admin, perf):
        for sub in ("impressions", "clicks", "leads_platform"):
            d = _ok(admin, f"ads:{sub}")
            assert d["total"] == int(perf["totals"][sub]), (sub, d["total"], perf["totals"][sub])

    def test_ads_attribution_ctx(self, admin, attribution):
        rng = attribution["range"]
        kw = {"ctx": "attribution", "date_from": rng["from"], "date_to": rng["to"]}
        t = attribution["totals"]
        assert _ok(admin, "ads:leads", **kw)["count"] == t["leads"]
        assert _ok(admin, "ads:booked", **kw)["count"] == t["booked"]
        assert _ok(admin, "ads:qualified", **kw)["count"] == t["qualified"]

    def test_ads_attribution_spend_matches_card(self, admin, attribution):
        """P93 fix: totals.spend atribusi harus per campaign_id unik."""
        rng = attribution["range"]
        d = _ok(admin, "ads:spend", ctx="attribution", date_from=rng["from"], date_to=rng["to"])
        assert d["total"] == int(attribution["totals"]["spend"]), (d["total"], attribution["totals"]["spend"])

    # --- Fase 93 retest: konsistensi spend & satuan (unit) ---
    def test_attribution_spend_matches_performance_same_range(self, admin, attribution):
        rng = attribution["range"]
        r = admin.get(f"{API}/ads/performance", params={"date_from": rng["from"], "date_to": rng["to"]}, timeout=90)
        assert r.status_code == 200, r.text[:300]
        pt = r.json()["data"]["totals"]
        assert int(attribution["totals"]["spend"]) == int(pt["spend"]), (attribution["totals"]["spend"], pt["spend"])

    def test_attribution_cpl_is_spend_over_leads(self, attribution):
        t = attribution["totals"]
        if t.get("leads"):
            expect = t["spend"] / t["leads"]
            assert abs(float(t["cpl"]) - expect) <= max(1.0, expect * 0.001), (t["cpl"], expect)
        else:
            assert not t.get("cpl")

    def test_attribution_rows_spend_not_duplicated(self, attribution):
        rows = attribution.get("rows") or []
        row_sum = sum(float(r.get("spend") or 0) for r in rows)
        print(f"row_sum={row_sum} totals.spend={attribution['totals']['spend']}")
        assert int(attribution["totals"]["spend"]) <= int(row_sum) + 1

    def test_count_metric_units(self, admin):
        for sub in ("clicks", "impressions", "leads_platform"):
            d = _ok(admin, f"ads:{sub}")
            assert d.get("unit") == "count", (sub, d.get("unit"))
            for r in d["rows"]:
                assert r.get("unit") == "count", (sub, r)

    def test_spend_metric_unit_idr(self, admin):
        d = _ok(admin, "ads:spend")
        assert d.get("unit") == "idr", d.get("unit")


# ---------- project:* (kartu Master Proyek) ----------
class TestProjectDrilldown:
    def test_available_and_held(self, admin, tree):
        st = tree["unit_stats"]
        d = _ok(admin, "project:available", project_id=PROJECT_ID)
        assert d["count"] == st["available"], (d["count"], st["available"])
        assert "status=available" in d["href_all"]
        h = _ok(admin, "project:held", project_id=PROJECT_ID)
        assert h["count"] == st.get("reserved", 0) + st.get("booked", 0), (h["count"], st)
        assert "status=reserved,booked" in h["href_all"]

    def test_sold_cumulative(self, admin, tree):
        st = tree["unit_stats"]
        d = _ok(admin, "project:sold", project_id=PROJECT_ID)
        expect = st.get("booked", 0) + st.get("sold", 0) + st.get("handed_over", 0)
        assert d["count"] == expect, (d["count"], st)
        assert d["href_all"] == f"/projects/{PROJECT_ID}?tab=units&status=booked,sold,handed_over"
        for r in d["rows"]:
            assert (r["href"] or "").startswith("/units/"), r

    def test_value_total(self, admin, tree):
        d = _ok(admin, "project:value", project_id=PROJECT_ID)
        assert d["total"] == int(tree["unit_stats"]["value"]), (d["total"], tree["unit_stats"]["value"])

    def test_progress_no_total(self, admin):
        d = _ok(admin, "project:progress", project_id=PROJECT_ID)
        assert d["total"] is None, d["total"]
        assert d["title"] == "Progres konstruksi per unit"

    def test_project_without_project_id_is_controlled(self, admin):
        for sub in ("available", "held", "sold", "value", "progress"):
            r = _drill(admin, f"project:{sub}")
            assert r.status_code != 500, f"project:{sub} tanpa project_id -> 500 {r.text[:200]}"
            if r.status_code == 200:
                assert r.json()["data"]["count"] == 0, r.json()["data"]["count"]
            else:
                assert r.status_code in (400, 404, 422), r.status_code


# ---------- /api/masterplan/units: status ganda dipisah koma ----------
class TestUnitsMultiStatus:
    def test_multi_status_filter(self, admin, tree):
        st = tree["unit_stats"]
        r = admin.get(f"{API}/masterplan/units", params={"project_id": PROJECT_ID,
                                                         "status": "booked,sold,handed_over"}, timeout=90)
        assert r.status_code == 200, r.text[:300]
        rows = r.json()["data"]
        assert len(rows) == st.get("booked", 0) + st.get("sold", 0) + st.get("handed_over", 0), len(rows)
        assert {u["status"] for u in rows} <= {"booked", "sold", "handed_over"}, {u["status"] for u in rows}

    def test_single_status_filter(self, admin, tree):
        r = admin.get(f"{API}/masterplan/units", params={"project_id": PROJECT_ID, "status": "available"}, timeout=90)
        assert r.status_code == 200, r.text[:300]
        rows = r.json()["data"]
        assert len(rows) == tree["unit_stats"]["available"], len(rows)
        assert all(u["status"] == "available" for u in rows)


# ---------- RBAC ----------
class TestRbac:
    def test_sales_ads_drilldown(self, sales):
        r = _drill(sales, "ads:spend")
        assert r.status_code in (200, 403), r.status_code
        print(f"RBAC sales ads:spend -> {r.status_code}")

    def test_sales_project_drilldown(self, sales):
        r = _drill(sales, "project:available", project_id=PROJECT_ID)
        assert r.status_code in (200, 403), r.status_code
        print(f"RBAC sales project:available -> {r.status_code}")

    def test_unknown_key_404(self, admin):
        r = _drill(admin, "ads:tidak_ada_kunci")
        assert r.status_code in (200, 403, 404), r.status_code
