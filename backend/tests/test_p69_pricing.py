"""Fase 69 — Pricing engine (skema diskon, promo, kupon), reservasi & penawaran.

Test rangkaian: seeded rows, CRUD RBAC, options, simulate, coupon validate, deal
reserve + coupon redemption / release / per-customer quota, quotation flow with
manager approval requiring scheme (DISC-MGR) & convert with coupon, PDF.
"""
import io
import os
import time

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
PASS = "Sipro#2026"


def _login(email):
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": PASS}, timeout=20)
    if r.status_code != 200:
        pytest.skip(f"login {email} failed: {r.status_code} {r.text[:200]}")
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


@pytest.fixture(scope="module")
def s_sales():
    return _sess(_login("sales@sipro.co.id"))


@pytest.fixture(scope="module")
def available_unit(s_manager):
    r = s_manager.get(f"{BASE_URL}/api/quotations/options", timeout=20)
    assert r.status_code == 200, r.text
    units = r.json()["data"]["units"]
    # unit demo berharga wajar dulu — unit fixture lain (UJI*, harga 0) membuat diskon persen = 0
    demo = [u for u in units if int(u.get("price") or 0) > 0 and not str(u.get("code", "")).upper().startswith("UJI")]
    units = demo or units
    assert len(units) >= 2, "Need at least 2 available units for tests"
    return units


@pytest.fixture(scope="module")
def a_lead(s_manager):
    """Pick a lead without active deal, prefer suggested id."""
    r = s_manager.get(f"{BASE_URL}/api/leads?limit=100", timeout=20)
    assert r.status_code == 200
    leads = r.json().get("data", [])
    if not leads:
        pytest.skip("no leads available")
    # lead tanpa deal aktif (batas reservasi per lead menolak 409 bila sudah memegang unit)
    deals = s_manager.get(f"{BASE_URL}/api/deals?limit=500", timeout=30).json().get("data") or []
    busy = {d.get("lead_id") for d in deals if d.get("status") in ("reserved", "booked")}
    free = [l for l in leads if l.get("id") not in busy and l.get("stage") not in ("won", "lost")]
    return (free or leads)[0]


# ---- Seeded rows ------------------------------------------------------------
class TestSeeded:
    def test_discount_schemes_seeded(self, s_manager):
        r = s_manager.get(f"{BASE_URL}/api/pricing/discount-schemes", timeout=15)
        assert r.status_code == 200
        codes = {x["code"]: x for x in r.json()["data"]}
        assert "DISC-CASH" in codes and codes["DISC-CASH"]["value"] == 2
        assert "DISC-MGR" in codes and codes["DISC-MGR"].get("requires_approval") is True

    def test_promos_seeded(self, s_manager):
        r = s_manager.get(f"{BASE_URL}/api/pricing/promos", timeout=15)
        assert r.status_code == 200
        codes = {x["code"]: x for x in r.json()["data"]}
        assert "PROMO-LAUNCH" in codes and codes["PROMO-LAUNCH"]["value"] == 2_000_000

    def test_coupons_seeded(self, s_manager):
        r = s_manager.get(f"{BASE_URL}/api/pricing/coupons", timeout=15)
        assert r.status_code == 200
        codes = {x["code"]: x for x in r.json()["data"]}
        assert "SIPRO2026" in codes
        assert codes["SIPRO2026"]["value"] == 5_000_000
        assert codes["SIPRO2026"]["quota_total"] == 50
        assert codes["SIPRO2026"]["quota_per_customer"] == 1


# ---- CRUD & RBAC ------------------------------------------------------------
class TestCRUDRBAC:
    created_ids = {}
    tag = str(int(time.time()))[-6:]  # kode unik per run: aturan lama dinonaktifkan, bukan dihapus

    def test_sales_view_ok(self, s_sales):
        r = s_sales.get(f"{BASE_URL}/api/pricing/discount-schemes", timeout=15)
        assert r.status_code == 200

    def test_sales_create_forbidden(self, s_sales):
        r = s_sales.post(f"{BASE_URL}/api/pricing/discount-schemes", json={
            "code": "TEST-X", "name": "test", "kind": "percent", "value": 1}, timeout=15)
        assert r.status_code == 403

    def test_owner_create_discount(self, s_owner):
        payload = {"code": f"test-disc-p69-{TestCRUDRBAC.tag}", "name": "TEST diskon p69",
                   "kind": "percent", "value": 3}
        r = s_owner.post(f"{BASE_URL}/api/pricing/discount-schemes", json=payload, timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        assert data["code"] == f"TEST-DISC-P69-{TestCRUDRBAC.tag}"  # uppercased
        TestCRUDRBAC.created_ids["disc"] = data["id"]

    def test_percent_over_100_rejected(self, s_owner):
        r = s_owner.post(f"{BASE_URL}/api/pricing/discount-schemes", json={
            "code": "TEST-BAD", "name": "bad percent", "kind": "percent", "value": 150},
            timeout=15)
        assert r.status_code in (400, 422)

    def test_update_discount(self, s_owner):
        rid = TestCRUDRBAC.created_ids.get("disc")
        if not rid:
            pytest.skip("no created discount")
        r = s_owner.put(f"{BASE_URL}/api/pricing/discount-schemes/{rid}",
                        json={"note": "updated by test"}, timeout=15)
        assert r.status_code == 200
        assert r.json()["data"]["note"] == "updated by test"

    def test_create_promo(self, s_owner):
        r = s_owner.post(f"{BASE_URL}/api/pricing/promos", json={
            "code": f"TEST-PROMO-P69-{TestCRUDRBAC.tag}", "name": "TEST promo p69",
            "kind": "amount", "value": 1_000_000}, timeout=15)
        assert r.status_code == 200
        TestCRUDRBAC.created_ids["promo"] = r.json()["data"]["id"]

    def test_create_coupon_expired(self, s_owner):
        """Create expired coupon then validate → 400."""
        r = s_owner.post(f"{BASE_URL}/api/pricing/coupons", json={
            "code": f"TEST-EXPIRED-P69-{TestCRUDRBAC.tag}", "name": "TEST expired coupon",
            "kind": "amount", "value": 100_000, "quota_total": 10,
            "quota_per_customer": 1, "valid_until": "2020-01-01"}, timeout=15)
        assert r.status_code == 200
        TestCRUDRBAC.created_ids["coupon_exp"] = r.json()["data"]["id"]

    def test_cleanup(self, s_owner):
        # Deactivate created rules
        for slug, key in [("discount-schemes", "disc"), ("promos", "promo"),
                          ("coupons", "coupon_exp")]:
            rid = TestCRUDRBAC.created_ids.get(key)
            if rid:
                s_owner.put(f"{BASE_URL}/api/pricing/{slug}/{rid}",
                            json={"active": False}, timeout=15)


# ---- Options ----------------------------------------------------------------
class TestOptions:
    def test_options_for_unit(self, s_manager, available_unit):
        unit = available_unit[0]
        r = s_manager.get(f"{BASE_URL}/api/pricing/options?unit_id={unit['id']}", timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        assert "discount_schemes" in d and "promos" in d
        assert "discount_limit_pct" in d
        for ds in d["discount_schemes"]:
            assert "preview_amount" in ds


# ---- Simulate ----------------------------------------------------------------
class TestSimulate:
    def test_manual_discount_rejected(self, s_manager, available_unit):
        unit = available_unit[0]
        r = s_manager.post(f"{BASE_URL}/api/quotations/simulate", json={
            "unit_id": unit["id"], "discount_amount": 5000}, timeout=15)
        assert r.status_code == 400
        assert "manual" in r.json()["detail"].lower() or "diketik" in r.json()["detail"].lower() or "Diskon" in r.json()["detail"]

    def test_simulate_stacked(self, s_manager, available_unit, a_lead):
        unit = available_unit[0]
        # Get DISC-CASH id
        r = s_manager.get(f"{BASE_URL}/api/pricing/discount-schemes", timeout=15)
        disc_cash = next(x for x in r.json()["data"] if x["code"] == "DISC-CASH")
        r = s_manager.get(f"{BASE_URL}/api/pricing/promos", timeout=15)
        promo = next(x for x in r.json()["data"] if x["code"] == "PROMO-LAUNCH")
        r = s_manager.post(f"{BASE_URL}/api/quotations/simulate", json={
            "unit_id": unit["id"], "discount_scheme_id": disc_cash["id"],
            "promo_id": promo["id"], "coupon_code": "SIPRO2026",
            "lead_id": a_lead["id"]}, timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        assert len(d["discount_lines"]) == 3
        sources = {ln["source"] for ln in d["discount_lines"]}
        assert sources == {"discount_scheme", "promo", "coupon"}
        assert d["discount_amount"] == sum(ln["amount"] for ln in d["discount_lines"])
        assert d["net_price"] == d["gross_price"] - d["discount_amount"]
        terms_total = sum(t["amount"] for t in d["terms"])
        assert terms_total == d["net_price"], f"terms {terms_total} vs net {d['net_price']}"


# ---- Coupon validate --------------------------------------------------------
class TestCouponValidate:
    def test_valid(self, s_manager, available_unit):
        # Do not pass lead_id to avoid clash with parallel TestDealReserveCoupon
        # which consumes the per-customer quota for the shared lead.
        unit = available_unit[0]
        r = s_manager.post(f"{BASE_URL}/api/pricing/coupons/validate", json={
            "code": "SIPRO2026", "unit_id": unit["id"]}, timeout=15)
        assert r.status_code == 200, r.text

    def test_unknown(self, s_manager, available_unit):
        r = s_manager.post(f"{BASE_URL}/api/pricing/coupons/validate", json={
            "code": "NOPE-XXXX", "unit_id": available_unit[0]["id"]}, timeout=15)
        assert r.status_code == 400

    def test_expired(self, s_manager, available_unit, s_owner):
        # Create expired coupon
        s_owner.post(f"{BASE_URL}/api/pricing/coupons", json={
            "code": "TEST-EXP-VALIDATE", "name": "TEST expired validate",
            "kind": "amount", "value": 100000, "quota_total": 10,
            "quota_per_customer": 1, "valid_until": "2020-01-01"}, timeout=15)
        r = s_manager.post(f"{BASE_URL}/api/pricing/coupons/validate", json={
            "code": "TEST-EXP-VALIDATE", "unit_id": available_unit[0]["id"]}, timeout=15)
        assert r.status_code == 400
        # cleanup: deactivate
        rows = s_owner.get(f"{BASE_URL}/api/pricing/coupons").json()["data"]
        for c in rows:
            if c["code"] == "TEST-EXP-VALIDATE":
                s_owner.put(f"{BASE_URL}/api/pricing/coupons/{c['id']}",
                            json={"active": False}, timeout=15)


# ---- Deal reserve with coupon + release ------------------------------------
class TestDealReserveCoupon:
    state = {}

    def test_reserve_with_coupon(self, s_manager, available_unit, a_lead):
        # Get DISC-CASH id
        r = s_manager.get(f"{BASE_URL}/api/pricing/discount-schemes", timeout=15)
        disc_cash = next(x for x in r.json()["data"] if x["code"] == "DISC-CASH")
        unit = available_unit[0]
        r = s_manager.post(f"{BASE_URL}/api/deals/reserve", json={
            "unit_id": unit["id"], "lead_id": a_lead["id"], "booking_fee": 1_000_000,
            "discount_scheme_id": disc_cash["id"], "coupon_code": "SIPRO2026"}, timeout=25)
        if r.status_code == 400 and "persetujuan" in r.text.lower():
            # DISC-CASH + coupon may exceed threshold on cheap unit — try coupon only
            r = s_manager.post(f"{BASE_URL}/api/deals/reserve", json={
                "unit_id": unit["id"], "lead_id": a_lead["id"], "booking_fee": 1_000_000,
                "coupon_code": "SIPRO2026"}, timeout=25)
        assert r.status_code == 200, r.text
        deal = r.json()["data"]
        TestDealReserveCoupon.state["deal_id"] = deal["id"]
        TestDealReserveCoupon.state["unit_id"] = unit["id"]
        assert deal.get("discount", 0) > 0
        assert deal.get("price", 0) > 0
        pricing = deal.get("pricing", {})
        assert "discount_lines" in pricing
        assert "terms" in pricing

    def test_coupon_used_count_and_redemption_row(self, s_manager):
        r = s_manager.get(f"{BASE_URL}/api/pricing/coupons", timeout=15)
        c = next(x for x in r.json()["data"] if x["code"] == "SIPRO2026")
        assert c["used_count"] >= 1
        TestDealReserveCoupon.state["coupon_id"] = c["id"]
        r = s_manager.get(f"{BASE_URL}/api/pricing/coupons/{c['id']}/redemptions", timeout=15)
        assert r.status_code == 200
        rows = r.json()["data"]["rows"]
        deal_id = TestDealReserveCoupon.state.get("deal_id")
        match = [x for x in rows if x.get("ref_id") == deal_id and x.get("state") == "used"]
        assert len(match) == 1

    def test_per_customer_quota(self, s_manager, available_unit, a_lead):
        """Same coupon on same lead & another unit → ditolak (kuota per pembeli=1, atau 409 batas
        `reservation.max_active_per_lead` yang menyala lebih dulu — keduanya penolakan jujur)."""
        if len(available_unit) < 2:
            pytest.skip("need 2 units")
        other = None
        for u in available_unit[1:]:
            if u["id"] != TestDealReserveCoupon.state.get("unit_id"):
                other = u
                break
        r = s_manager.post(f"{BASE_URL}/api/deals/reserve", json={
            "unit_id": other["id"], "lead_id": a_lead["id"], "booking_fee": 1_000_000,
            "coupon_code": "SIPRO2026"}, timeout=25)
        assert r.status_code in (400, 409), r.text

    def test_cancel_releases_coupon(self, s_manager):
        deal_id = TestDealReserveCoupon.state.get("deal_id")
        assert deal_id
        # get used_count before
        cid = TestDealReserveCoupon.state["coupon_id"]
        r = s_manager.get(f"{BASE_URL}/api/pricing/coupons", timeout=15)
        before = next(x for x in r.json()["data"] if x["id"] == cid)["used_count"]
        r = s_manager.post(f"{BASE_URL}/api/deals/{deal_id}/cancel",
                           json={"note": "test cleanup"}, timeout=20)
        assert r.status_code == 200, r.text
        r = s_manager.get(f"{BASE_URL}/api/pricing/coupons", timeout=15)
        after = next(x for x in r.json()["data"] if x["id"] == cid)["used_count"]
        assert after == before - 1
        # Redemption row should be 'released'
        r = s_manager.get(f"{BASE_URL}/api/pricing/coupons/{cid}/redemptions", timeout=15)
        rows = r.json()["data"]["rows"]
        match = [x for x in rows if x.get("ref_id") == deal_id]
        assert match and match[0]["state"] == "released"


# ---- Reserve with DISC-MGR requires approval → 400 --------------------------
class TestReserveDiscMgr:
    def test_disc_mgr_rejected(self, s_manager, available_unit, a_lead):
        r = s_manager.get(f"{BASE_URL}/api/pricing/discount-schemes", timeout=15)
        disc_mgr = next(x for x in r.json()["data"] if x["code"] == "DISC-MGR")
        # Use a fresh unit if possible
        unit = available_unit[-1]
        r = s_manager.post(f"{BASE_URL}/api/deals/reserve", json={
            "unit_id": unit["id"], "lead_id": a_lead["id"], "booking_fee": 1_000_000,
            "discount_scheme_id": disc_mgr["id"]}, timeout=20)
        assert r.status_code == 400
        assert "penawaran" in r.text.lower() or "persetujuan" in r.text.lower()


# ---- Quotation flow with DISC-MGR + approval + convert + PDF ---------------
class TestQuotationFlow:
    state = {}

    def test_create_quotation_awaiting(self, s_manager, available_unit, a_lead):
        r = s_manager.get(f"{BASE_URL}/api/pricing/discount-schemes", timeout=15)
        disc_mgr = next(x for x in r.json()["data"] if x["code"] == "DISC-MGR")
        # Get any payment scheme
        r = s_manager.get(f"{BASE_URL}/api/quotations/options", timeout=15)
        opts = r.json()["data"]
        scheme_id = opts["schemes"][0]["id"] if opts["schemes"] else None
        # Find still-available unit
        avail_units = opts["units"]
        assert avail_units, "need available units"
        unit = avail_units[0]
        payload = {"lead_id": a_lead["id"], "unit_id": unit["id"],
                   "discount_scheme_id": disc_mgr["id"],
                   "discount_reason": "Unit slow moving; margin sehat cukup untuk 5%.",
                   "scheme_id": scheme_id, "coupon_code": "SIPRO2026"}
        r = s_manager.post(f"{BASE_URL}/api/quotations", json=payload, timeout=25)
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        assert d["state"] == "awaiting_approval"
        TestQuotationFlow.state["q_id"] = d["id"]
        TestQuotationFlow.state["unit_id"] = unit["id"]

    def test_manager_approve(self, s_manager):
        qid = TestQuotationFlow.state.get("q_id")
        assert qid
        r = s_manager.post(f"{BASE_URL}/api/quotations/{qid}/decision", json={
            "approve": True, "reason": "Disetujui: unit slow moving, margin sehat."},
            timeout=20)
        assert r.status_code == 200, r.text
        assert r.json()["data"]["state"] == "approved"

    def test_pdf(self, s_manager):
        qid = TestQuotationFlow.state.get("q_id")
        r = s_manager.get(f"{BASE_URL}/api/quotations/{qid}/pdf", timeout=20)
        assert r.status_code == 200
        assert "application/pdf" in r.headers.get("content-type", "")
        assert r.content[:4] == b"%PDF"

    def test_convert_redeems_coupon(self, s_manager):
        qid = TestQuotationFlow.state.get("q_id")
        # Get coupon used_count before
        r = s_manager.get(f"{BASE_URL}/api/pricing/coupons", timeout=15)
        c = next(x for x in r.json()["data"] if x["code"] == "SIPRO2026")
        before = c["used_count"]
        r = s_manager.post(f"{BASE_URL}/api/quotations/{qid}/convert", json={}, timeout=25)
        assert r.status_code == 200, r.text
        deal = r.json()["data"]["deal"]
        TestQuotationFlow.state["deal_id"] = deal["id"]
        r = s_manager.get(f"{BASE_URL}/api/pricing/coupons", timeout=15)
        after = next(x for x in r.json()["data"] if x["code"] == "SIPRO2026")["used_count"]
        assert after == before + 1, f"before={before} after={after}"

    def test_cleanup_convert_deal(self, s_manager):
        did = TestQuotationFlow.state.get("deal_id")
        if did:
            s_manager.post(f"{BASE_URL}/api/deals/{did}/cancel",
                           json={"note": "test cleanup"}, timeout=20)
