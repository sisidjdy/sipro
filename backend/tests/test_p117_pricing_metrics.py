"""Fase 69 follow-up (iterasi 117) — Metrik BI Potongan Harga (PRC-01..04)
dan aturan multi-proyek/tipe-unit pada skema diskon/promo/kupon.
"""
import os
import time

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
PASS = "Sipro#2026"


def _login(email):
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": email, "password": PASS}, timeout=20)
    if r.status_code != 200:
        pytest.skip(f"login {email} failed {r.status_code}")
    return r.json()["access_token"]


def _sess(tok):
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {tok}", "Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def s_owner():
    return _sess(_login("owner@sipro.co.id"))


@pytest.fixture(scope="module")
def s_manager():
    return _sess(_login("manager@sipro.co.id"))


# ---- 1. Kamus metrik & endpoints PRC-01..04 --------------------------------
class TestPricingMetrics:
    def test_catalog_lists_prc(self, s_manager):
        r = s_manager.get(f"{BASE_URL}/api/analytics/metrics", timeout=15)
        assert r.status_code == 200, r.text
        rows = r.json().get("data") or r.json()
        codes = {row["code"]: row for row in rows}
        for code in ("PRC-01", "PRC-02", "PRC-03", "PRC-04"):
            assert code in codes, f"{code} tidak ada di catalog"
            assert codes[code].get("formula")
            assert isinstance(codes[code].get("requires"), list)

    @pytest.mark.parametrize("code", ["PRC-01", "PRC-02", "PRC-03", "PRC-04"])
    def test_metric_endpoint_ok(self, s_manager, code):
        r = s_manager.get(f"{BASE_URL}/api/analytics/metric/{code}?period=all", timeout=20)
        assert r.status_code == 200, r.text
        payload = r.json().get("data") or r.json()
        assert payload.get("code") == code
        # value dapat None jika belum ada data; state harus ada
        assert "state" in payload
        assert "breakdown" in payload

    def _codes_from(self, metrics):
        if isinstance(metrics, dict):
            return set(metrics.keys())
        return {m.get("code") for m in (metrics or []) if isinstance(m, dict)}

    def test_sales_funnel_includes_prc(self, s_manager):
        r = s_manager.get(f"{BASE_URL}/api/analytics/sales/funnel?period=all", timeout=25)
        assert r.status_code == 200, r.text
        data = r.json().get("data") or r.json()
        metrics = data.get("metrics")
        codes = self._codes_from(metrics)
        for code in ("PRC-01", "PRC-02", "PRC-03", "PRC-04"):
            assert code in codes, f"{code} tidak ada di sales/funnel — got {sorted(codes)}"

    def test_executive_includes_prc01(self, s_manager):
        r = s_manager.get(f"{BASE_URL}/api/analytics/executive?period=all", timeout=25)
        assert r.status_code == 200, r.text
        data = r.json().get("data") or r.json()
        codes = self._codes_from(data.get("metrics"))
        assert "PRC-01" in codes, f"PRC-01 not in executive metrics: {sorted(codes)}"


# ---- 2. PRC-01/PRC-04 bereaksi terhadap deal baru ---------------------------
class TestPRCReactsToDeal:
    state = {}

    def _get_metric(self, s, code):
        r = s.get(f"{BASE_URL}/api/analytics/metric/{code}?period=all", timeout=20)
        assert r.status_code == 200, r.text
        return r.json().get("data") or r.json()

    def test_reserve_increases_prc01_prc04(self, s_manager):
        # 1) snapshot awal
        prc01_before = self._get_metric(s_manager, "PRC-01")
        prc04_before = self._get_metric(s_manager, "PRC-04")

        # 2) siapkan unit + lead + skema
        opts = s_manager.get(f"{BASE_URL}/api/quotations/options", timeout=15).json()["data"]
        units = opts["units"]
        # unit demo berharga wajar — unit fixture lain (UJI*, harga 0) membuat diskon = 0
        units = [u for u in units if int(u.get("price") or 0) > 0
                 and not str(u.get("code", "")).upper().startswith("UJI")] or units
        assert units, "butuh unit available"
        unit = units[0]

        # cari lead tanpa deal aktif — HINDARI preferred (sudah punya demo deal + kupon)
        leads = s_manager.get(f"{BASE_URL}/api/leads?limit=200", timeout=15).json().get("data", [])
        preferred = "0f7242a2-ef93-47b2-9673-cd3df9ea17c5"
        # cari lead lain (bukan preferred) yang tidak punya deal aktif — pakai heuristik: cek /leads yang tidak seluruhnya
        candidate_lead = None
        for l in leads:
            if l.get("id") == preferred:
                continue
            candidate_lead = l
            # quick check: apakah lead ini punya deal aktif?
            dresp = s_manager.get(f"{BASE_URL}/api/deals?lead_id={l['id']}", timeout=15)
            if dresp.status_code == 200:
                items = (dresp.json().get("data") or [])
                active = [d for d in items if d.get("status") in ("reserved", "booked", "completed")]
                if not active:
                    break
        assert candidate_lead, "butuh lead lain tanpa deal aktif"
        lead = candidate_lead

        promos = s_manager.get(f"{BASE_URL}/api/pricing/promos", timeout=15).json()["data"]
        promo = next((p for p in promos if p["code"] == "PROMO-LAUNCH"), None)

        payload = {
            "unit_id": unit["id"], "lead_id": lead["id"], "booking_fee": 1_000_000,
            "coupon_code": "SIPRO2026",
        }
        if promo:
            payload["promo_id"] = promo["id"]

        r = s_manager.post(f"{BASE_URL}/api/deals/reserve", json=payload, timeout=30)
        if r.status_code == 400 and "persetujuan" in r.text.lower():
            # coba kupon saja
            payload.pop("promo_id", None)
            r = s_manager.post(f"{BASE_URL}/api/deals/reserve", json=payload, timeout=30)
        assert r.status_code == 200, r.text
        deal = r.json()["data"]
        TestPRCReactsToDeal.state["deal_id"] = deal["id"]
        TestPRCReactsToDeal.state["project_id"] = deal.get("project_id")
        discount = int(deal.get("discount") or 0)
        assert discount > 0
        TestPRCReactsToDeal.state["discount"] = discount

        # kecil delay agar snapshot database up to date (bukan cache)
        time.sleep(1)

        prc01_after = self._get_metric(s_manager, "PRC-01")
        prc04_after = self._get_metric(s_manager, "PRC-04")

        # PRC-01 nilai bertambah minimal sebesar discount
        v_before = int(prc01_before.get("value") or 0)
        v_after = int(prc01_after.get("value") or 0)
        assert v_after >= v_before + discount, (
            f"PRC-01 tidak naik cukup: before={v_before} after={v_after} discount={discount}"
        )

        # PRC-01 breakdown memuat proyek deal
        pid = deal.get("project_id")
        keys = {row["key"] for row in prc01_after.get("breakdown") or []}
        assert pid in keys or "(tanpa proyek)" in keys

        # PRC-04 hitung kupon SIPRO2026 bertambah minimal 1
        b_before = {r["key"]: r["value"] for r in (prc04_before.get("breakdown") or [])}
        b_after = {r["key"]: r["value"] for r in (prc04_after.get("breakdown") or [])}
        assert b_after.get("SIPRO2026", 0) >= b_before.get("SIPRO2026", 0) + 1

    def test_cancel_releases_and_prc04_decreases(self, s_manager):
        did = TestPRCReactsToDeal.state.get("deal_id")
        if not did:
            pytest.skip("no deal created")
        prc04_before = self._get_metric(s_manager, "PRC-04")
        r = s_manager.post(f"{BASE_URL}/api/deals/{did}/cancel",
                           json={"note": "cleanup test117"}, timeout=25)
        assert r.status_code == 200, r.text
        time.sleep(1)
        prc04_after = self._get_metric(s_manager, "PRC-04")
        b_before = {r["key"]: r["value"] for r in (prc04_before.get("breakdown") or [])}
        b_after = {r["key"]: r["value"] for r in (prc04_after.get("breakdown") or [])}
        assert b_after.get("SIPRO2026", 0) <= b_before.get("SIPRO2026", 0) - 1


# ---- 3. Multi proyek / multi tipe unit pada skema diskon --------------------
class TestMultiProjectRule:
    state = {}
    code = f"TEST-MULTI-P117-{int(time.time()) % 1000000}"  # unik per run (kode skema tidak boleh kembar)

    def test_create_scheme_with_multi_apply(self, s_owner, s_manager):
        projects = s_owner.get(f"{BASE_URL}/api/projects", timeout=15).json()
        projects = projects.get("data") or projects
        if not isinstance(projects, list) or len(projects) < 2:
            # Fallback: test dengan 1 proyek (masih valid coverage untuk multi-select 1 pilihan)
            if not projects:
                pytest.skip("tidak ada proyek")
            p_ids = [projects[0]["id"]]
        else:
            p_ids = [projects[0]["id"], projects[1]["id"]]

        unit_types = s_owner.get(f"{BASE_URL}/api/catalog/unit-types", timeout=15).json()
        unit_types = unit_types.get("data") or unit_types
        assert isinstance(unit_types, list) and len(unit_types) >= 1
        ut_codes = [ut.get("code") for ut in unit_types[:2] if ut.get("code")]

        TestMultiProjectRule.state["p_ids"] = p_ids
        TestMultiProjectRule.state["ut_codes"] = ut_codes

        payload = {
            "code": TestMultiProjectRule.code, "name": "TEST multi proyek P117",
            "kind": "percent", "value": 1,
            "applies_project_ids": p_ids,
            "applies_unit_types": ut_codes,
        }
        r = s_owner.post(f"{BASE_URL}/api/pricing/discount-schemes", json=payload, timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        assert data["code"] == TestMultiProjectRule.code
        assert set(data.get("applies_project_ids") or []) == set(p_ids)
        assert set(data.get("applies_unit_types") or []) == set([c for c in ut_codes if c])
        TestMultiProjectRule.state["id"] = data["id"]

    def test_options_filters_by_project_and_unit_type(self, s_manager):
        p_ids = TestMultiProjectRule.state["p_ids"]
        ut_codes = TestMultiProjectRule.state["ut_codes"]
        # temukan unit di p_ids[0] dgn tipe yg cocok, dan unit di proyek LAIN
        opts = s_manager.get(f"{BASE_URL}/api/quotations/options", timeout=15).json()["data"]
        units = opts["units"]

        # Ambil sample unit per proyek
        in_scope = None
        out_scope = None
        for u in units:
            pid = u.get("project_id")
            utc = u.get("type_code") or u.get("unit_type") or u.get("type")
            if pid == p_ids[0] and (not ut_codes or utc in ut_codes) and in_scope is None:
                in_scope = u
            if pid not in p_ids and out_scope is None:
                out_scope = u
        if not in_scope:
            pytest.skip("tidak ada unit yang cocok scope skema baru — data seed berbeda")

        r = s_manager.get(f"{BASE_URL}/api/pricing/options?unit_id={in_scope['id']}", timeout=15)
        assert r.status_code == 200, r.text
        codes = {d["code"] for d in r.json()["data"]["discount_schemes"]}
        assert TestMultiProjectRule.code in codes

        if out_scope:
            r2 = s_manager.get(f"{BASE_URL}/api/pricing/options?unit_id={out_scope['id']}", timeout=15)
            assert r2.status_code == 200
            codes2 = {d["code"] for d in r2.json()["data"]["discount_schemes"]}
            assert TestMultiProjectRule.code not in codes2, "skema seharusnya TIDAK berlaku di luar scope"

    def test_cleanup(self, s_owner):
        rid = TestMultiProjectRule.state.get("id")
        if rid:
            s_owner.put(f"{BASE_URL}/api/pricing/discount-schemes/{rid}",
                        json={"active": False}, timeout=15)
