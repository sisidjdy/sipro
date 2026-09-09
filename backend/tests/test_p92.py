"""Fase 92 — Drill-down KPI lintas modul (Beranda, Lead, Pembangunan) + RBAC."""
import os

import pytest
import requests
from dotenv import dotenv_values

fe = dotenv_values("/app/frontend/.env")
BASE = (os.environ.get("REACT_APP_BACKEND_URL") or fe.get("REACT_APP_BACKEND_URL")).rstrip("/")
API = f"{BASE}/api"


def _login(email, password):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=60)
    assert r.status_code == 200, f"login {email} -> {r.status_code} {r.text[:300]}"
    return s


@pytest.fixture(scope="module")
def admin():
    return _login("superadmin@sipro.co.id", "Sipro#2026")


@pytest.fixture(scope="module")
def sales():
    return _login("sales@sipro.co.id", "Sipro#2026")


# ---------- Beranda: /api/work/home KPI membawa drill_key/drill_params ----------
class TestHomeKpis:
    def test_home_kpis_have_drill(self, admin):
        r = admin.get(f"{API}/work/home", timeout=60)
        assert r.status_code == 200, r.text[:300]
        kpis = r.json()["data"]["kpis"]
        assert isinstance(kpis, list) and len(kpis) > 0
        for k in kpis:
            assert isinstance(k.get("drill_key"), str) and k["drill_key"], f"kpi tanpa drill_key: {k}"
            assert isinstance(k.get("drill_params"), dict), f"drill_params bukan obj: {k}"

    def test_home_drill_keys_resolve(self, admin):
        r = admin.get(f"{API}/work/home", timeout=60)
        for k in r.json()["data"]["kpis"]:
            params = {str(a): str(b) for a, b in (k.get("drill_params") or {}).items()}
            d = admin.get(f"{API}/drilldown/{k['drill_key']}", params=params, timeout=60)
            assert d.status_code == 200, f"{k['drill_key']} {params} -> {d.status_code} {d.text[:200]}"
            data = d.json()["data"]
            assert isinstance(data["rows"], list)
            assert data["count"] == len(data["rows"])
            assert data.get("href_all")


# ---------- Tasks ----------
class TestTasksDrill:
    def test_tasks_overdue_all(self, admin):
        r = admin.get(f"{API}/drilldown/tasks", params={"scope": "all", "bucket": "overdue"}, timeout=60)
        assert r.status_code == 200, r.text[:300]
        d = r.json()["data"]
        assert d["title"] == "Tugas terlambat", d["title"]
        assert d["count"] == len(d["rows"])
        assert d["href_all"].startswith("/tasks?tab=tasks")
        for row in d["rows"]:
            assert row.get("task_id"), row
            assert str(row.get("href", "")).startswith("/tasks?tab=tasks"), row

    def test_tasks_mine_sla_breached(self, admin):
        r = admin.get(f"{API}/drilldown/tasks", params={"scope": "mine", "sla": "breached"}, timeout=60)
        assert r.status_code == 200, r.text[:300]
        assert r.json()["data"]["title"] == "Tugas melewati SLA"


# ---------- Leads ----------
class TestLeadsDrill:
    @pytest.mark.parametrize("params", [
        {"stage": "acquisition"}, {"band": "hot"}, {"sla": "breached"},
        {"idle_days": "7"}, {"new_hours": "24"},
    ])
    def test_leads_variants(self, admin, params):
        r = admin.get(f"{API}/drilldown/leads", params=params, timeout=60)
        assert r.status_code == 200, f"{params} -> {r.status_code} {r.text[:300]}"
        d = r.json()["data"]
        assert d["count"] == len(d["rows"])
        for row in d["rows"]:
            assert row["href"] == f"/leads/{row['id']}", row
            assert "score" in row and "score_band" in row, row

    def test_leads_summary(self, admin):
        r = admin.get(f"{API}/drilldown/_summary/leads", timeout=90)
        assert r.status_code == 200, r.text[:300]
        data = r.json()["data"]
        # Audit Tahap 1 (2026-06): kartu Pipeline Lead = PARTISI (total = aktif + menang + daur ulang + hilang),
        # menggantikan kartu lama new24/hot/sla/idle7/won yang saling tumpang tindih.
        assert [x["key"] for x in data] == ["total", "active", "won", "recycle", "lost"], data
        for x in data:
            assert isinstance(x["value"], int), x
            assert isinstance(x["params"], dict) and x.get("drill"), x
        val = {x["key"]: x["value"] for x in data}
        assert val["total"] == val["active"] + val["won"] + val["recycle"] + val["lost"], val

    def test_summary_partition_matches_rows(self, admin):
        s = admin.get(f"{API}/drilldown/_summary/leads", timeout=90).json()["data"]
        for card in s:
            if not card["params"]:
                continue
            rows = admin.get(f"{API}/drilldown/leads", params=card["params"], timeout=60).json()["data"]["count"]
            assert card["value"] == rows, f"kartu {card['key']}={card['value']} vs rincian={rows}"


# ---------- Deals / lain ----------
class TestOtherKeys:
    def test_deals(self, admin):
        r = admin.get(f"{API}/drilldown/deals", params={"status": "booked,active,completed"}, timeout=60)
        assert r.status_code == 200, r.text[:300]
        d = r.json()["data"]
        for row in d["rows"]:
            assert str(row.get("href", "")).startswith("/customers?hub=deal"), row
            assert "amount" in row

    @pytest.mark.parametrize("key", ["projects", "units_qc_hold", "punch_open", "retention_held", "ar_outstanding"])
    def test_simple_keys(self, admin, key):
        r = admin.get(f"{API}/drilldown/{key}", timeout=60)
        assert r.status_code == 200, f"{key} -> {r.status_code} {r.text[:300]}"
        d = r.json()["data"]
        assert isinstance(d["rows"], list) and d["count"] == len(d["rows"])

    def test_projects_rows_href(self, admin):
        d = admin.get(f"{API}/drilldown/projects", timeout=60).json()["data"]
        assert d["rows"], "tidak ada proyek"
        for row in d["rows"]:
            assert row["href"] == f"/projects/{row['id']}"

    @pytest.mark.parametrize("sub", ["unscheduled", "awaiting_verification", "late_items",
                                     "blocked_items", "at_risk", "scheduled"])
    def test_build_keys(self, admin, sub):
        r = admin.get(f"{API}/drilldown/build:{sub}", timeout=60)
        assert r.status_code == 200, f"build:{sub} -> {r.status_code} {r.text[:300]}"
        d = r.json()["data"]
        for row in d["rows"]:
            assert str(row["href"]).startswith("/units/"), row

    @pytest.mark.parametrize("sub", ["all", "unscheduled", "running", "late", "ready", "progress", "awaiting"])
    def test_board_keys(self, admin, sub):
        r = admin.get(f"{API}/drilldown/board:{sub}", timeout=60)
        assert r.status_code == 200, f"board:{sub} -> {r.status_code} {r.text[:300]}"
        d = r.json()["data"]
        for row in d["rows"]:
            assert str(row["href"]).startswith("/units/"), row

    def test_board_counts_match_unit_board(self, admin):
        b = admin.get(f"{API}/build/board/units", params={"limit": 100}, timeout=60)
        assert b.status_code == 200, b.text[:300]
        bj = b.json()
        summary = bj.get("summary") or bj.get("data", {}).get("summary") or {}
        total = bj.get("total") if bj.get("total") is not None else summary.get("total")
        all_c = admin.get(f"{API}/drilldown/board:all", timeout=60).json()["data"]["count"]
        late_c = admin.get(f"{API}/drilldown/board:late", timeout=60).json()["data"]["count"]
        assert all_c == total, f"board:all={all_c} vs unit-board total={total} (summary={summary})"
        assert late_c == summary.get("late"), f"board:late={late_c} vs summary.late={summary.get('late')}"

    def test_unknown_key_rejected(self, admin):
        """Spesifikasi Fase 92 minta 404; implementasi menolak lewat `allowed()` -> 403.
        Keduanya menolak akses, tapi kode status berbeda dari spesifikasi (dilaporkan)."""
        r = admin.get(f"{API}/drilldown/tidak_ada_kunci", timeout=60)
        assert r.status_code in (403, 404), f"{r.status_code} {r.text[:200]}"
        assert r.status_code == 404 or "tidak boleh" in r.text


# ---------- RBAC (sales) ----------
class TestRbacSales:
    def test_sales_build_forbidden(self, sales):
        r = sales.get(f"{API}/drilldown/build:late_items", timeout=60)
        assert r.status_code == 403, f"{r.status_code} {r.text[:200]}"

    def test_sales_tasks_ok(self, sales):
        r = sales.get(f"{API}/drilldown/tasks", params={"scope": "mine", "bucket": "overdue"}, timeout=60)
        assert r.status_code == 200, r.text[:300]

    def test_sales_leads_ok(self, sales):
        r = sales.get(f"{API}/drilldown/leads", params={"band": "hot"}, timeout=60)
        assert r.status_code == 200, r.text[:300]

    def test_sales_finance_forbidden(self, sales):
        r = sales.get(f"{API}/drilldown/ar_outstanding", timeout=60)
        assert r.status_code == 403, f"sales bisa akses finance drilldown: {r.status_code}"
