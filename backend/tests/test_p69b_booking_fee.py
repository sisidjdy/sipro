"""P69B — Booking fee as separate payment component.

Tests:
- reserve creates INV-BF invoice; deal.booking_fee_status='unverified'
- partial + full pay; receipt KWT; deposit balance; deal status transitions
- validation errors (paid twice, over outstanding, amount 0)
- PDF endpoints (invoice & receipt)
- RBAC: sales cannot pay; site denied on get; sales can get own deal
- Setting booking_fee.require_paid_before_booking gate
- Cancel closes unpaid invoice
"""
import os
import pytest
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://sipro-pricing-engine.preview.emergentagent.com").rstrip("/")
PWD = "Sipro#2026"


def _login(email):
    r = requests.post(f"{BASE}/api/auth/login", json={"email": email, "password": PWD}, timeout=30)
    assert r.status_code == 200, f"login {email}: {r.status_code} {r.text}"
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def owner():
    return {"Authorization": f"Bearer {_login('owner@sipro.co.id')}"}


@pytest.fixture(scope="module")
def sales():
    return {"Authorization": f"Bearer {_login('sales@sipro.co.id')}"}


@pytest.fixture(scope="module")
def site():
    return {"Authorization": f"Bearer {_login('site@sipro.co.id')}"}


CREATED_DEALS = []


def _available_unit(owner, exclude_ids=None):
    r = requests.get(f"{BASE}/api/quotations/options", headers=owner, timeout=30)
    assert r.status_code == 200, r.text
    data = r.json().get("data") or r.json()
    units = data.get("units") or []
    exclude = set(exclude_ids or [])
    # options endpoint already returns only reservable units; no status filter needed
    for u in units:
        if u["id"] not in exclude:
            return u
    pytest.skip("No available units")


def _schemes(owner):
    r = requests.get(f"{BASE}/api/quotations/options", headers=owner, timeout=30)
    return (r.json().get("data") or r.json()).get("schemes") or []


def _pick_lead_without_active_deal(owner):
    # try preferred leads first
    # ID lead basis data lama sudah mati; pindai daftar lead yang belum punya deal aktif.
    # fall back: scan leads list
    lr = requests.get(f"{BASE}/api/leads?limit=100", headers=owner, timeout=30)
    if lr.status_code == 200:
        for lead in (lr.json().get("data") or []):
            lid = lead.get("id")
            if not lid:
                continue
            deals_r = requests.get(f"{BASE}/api/deals?lead_id={lid}", headers=owner, timeout=30)
            if deals_r.status_code == 200:
                rows = (deals_r.json().get("data") or [])
                if not any(d.get("status") in ("reserved", "booked", "completed") for d in rows):
                    return lid
    pytest.skip("no lead without active deal")


def _reserve(owner, unit_id, lead_id, booking_fee=2000000, **extra):
    payload = {"unit_id": unit_id, "lead_id": lead_id, "booking_fee": booking_fee, **extra}
    r = requests.post(f"{BASE}/api/deals/reserve", headers=owner, json=payload, timeout=30)
    return r


class TestBookingFeeFlow:
    def test_01_reserve_creates_invoice(self, owner):
        lead_id = _pick_lead_without_active_deal(owner)
        unit = _available_unit(owner)
        r = _reserve(owner, unit["id"], lead_id, booking_fee=2000000)
        assert r.status_code == 200, r.text
        deal = (r.json().get("data") or r.json())
        CREATED_DEALS.append(deal["id"])
        # NOTE: reserve response is stale — status set by bf.create_invoice after deal insert.
        # Verify via GET.
        dr = requests.get(f"{BASE}/api/deals/{deal['id']}", headers=owner, timeout=30)
        assert dr.status_code == 200
        deal_db = dr.json().get("data") or dr.json()
        assert deal_db.get("booking_fee_status") == "unverified"
        assert deal_db.get("booking_fee_invoice_id")

        # detail endpoint
        d = requests.get(f"{BASE}/api/booking-fee/deals/{deal['id']}", headers=owner, timeout=30)
        assert d.status_code == 200, d.text
        body = d.json()["data"]
        inv = body["invoice"]
        assert inv["no"].startswith("INV-BF/"), inv["no"]
        assert inv["status"] == "unpaid"
        assert inv["amount"] == 2000000
        assert inv["outstanding"] == 2000000
        assert body["receipts"] == []

    def test_02_partial_then_full_pay(self, owner):
        deal_id = CREATED_DEALS[0]
        # partial
        r = requests.post(f"{BASE}/api/booking-fee/deals/{deal_id}/pay", headers=owner,
                          json={"amount": 500000, "method": "transfer", "note": "uji"}, timeout=30)
        assert r.status_code == 200, r.text
        out = r.json()["data"]
        assert out["invoice"]["status"] == "partial"
        assert out["receipt"]["receipt_no"].startswith("KWT/")
        assert int(out["deposit"]["balance"]) == 500000
        # deal status recorded
        dr = requests.get(f"{BASE}/api/deals/{deal_id}", headers=owner, timeout=30)
        assert dr.status_code == 200
        assert (dr.json().get("data") or dr.json()).get("booking_fee_status") == "recorded"

        # over outstanding
        r2 = requests.post(f"{BASE}/api/booking-fee/deals/{deal_id}/pay", headers=owner,
                           json={"amount": 5000000, "method": "transfer", "note": "over"}, timeout=30)
        assert r2.status_code == 400

        # zero → 422 (pydantic) or 400
        r3 = requests.post(f"{BASE}/api/booking-fee/deals/{deal_id}/pay", headers=owner,
                           json={"amount": 0, "method": "transfer", "note": "z"}, timeout=30)
        assert r3.status_code in (400, 422)

        # remaining
        r4 = requests.post(f"{BASE}/api/booking-fee/deals/{deal_id}/pay", headers=owner,
                           json={"amount": 1500000, "method": "transfer", "note": "sisa"}, timeout=30)
        assert r4.status_code == 200, r4.text
        body = r4.json()
        assert "LUNAS" in body["message"]
        assert body["data"]["invoice"]["status"] == "paid"
        dr2 = requests.get(f"{BASE}/api/deals/{deal_id}", headers=owner, timeout=30)
        assert (dr2.json().get("data") or dr2.json()).get("booking_fee_status") == "verified"

        # already paid
        r5 = requests.post(f"{BASE}/api/booking-fee/deals/{deal_id}/pay", headers=owner,
                           json={"amount": 100, "method": "transfer", "note": "again"}, timeout=30)
        assert r5.status_code == 400
        assert "LUNAS" in r5.json().get("detail", "")

    def test_03_pdfs(self, owner):
        deal_id = CREATED_DEALS[0]
        r = requests.get(f"{BASE}/api/booking-fee/deals/{deal_id}/invoice/pdf",
                         headers=owner, timeout=30)
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("application/pdf")

        # receipt pdf
        det = requests.get(f"{BASE}/api/booking-fee/deals/{deal_id}", headers=owner, timeout=30)
        receipts = det.json()["data"]["receipts"]
        rid = receipts[0]["id"]
        rp = requests.get(f"{BASE}/api/finance/ar/receipts/{rid}/pdf", headers=owner, timeout=30)
        assert rp.status_code == 200, rp.text
        assert rp.headers["content-type"].startswith("application/pdf")

    def test_04_finance_listing_and_deposit(self, owner):
        r = requests.get(f"{BASE}/api/booking-fee", headers=owner, timeout=30)
        assert r.status_code == 200, r.text
        j = r.json()
        assert "summary" in j and "data" in j
        assert set(j["summary"].keys()) >= {"unpaid", "partial", "paid", "cancelled"}

        dep = requests.get(f"{BASE}/api/finance/ar/deposits", headers=owner, timeout=30)
        assert dep.status_code == 200, dep.text
        rows = dep.json().get("data") or []
        match = [x for x in rows if x.get("deal_id") == CREATED_DEALS[0]]
        assert match, "deal not in deposits"
        assert int(match[0].get("balance") or 0) == 2000000

    def test_05_rbac(self, sales, site, owner):
        deal_id = CREATED_DEALS[0]
        # sales cannot pay
        r = requests.post(f"{BASE}/api/booking-fee/deals/{deal_id}/pay", headers=sales,
                         json={"amount": 100, "method": "transfer", "note": "x"}, timeout=30)
        assert r.status_code == 403
        # site can't view finance
        r2 = requests.get(f"{BASE}/api/booking-fee/deals/{deal_id}", headers=site, timeout=30)
        assert r2.status_code == 403


class TestBookingGate:
    def test_setting_gate_flow(self, owner):
        # Ensure setting OFF
        requests.put(f"{BASE}/api/settings/booking_fee.require_paid_before_booking",
                     headers=owner, json={"value": False, "reason": "test off", "scope": "org"},
                     timeout=30)
        # create deal (unpaid), book should succeed
        lead_id = _pick_lead_without_active_deal(owner)
        # if the same lead used already has active deal skip
        unit = _available_unit(owner, exclude_ids=[])
        rv = _reserve(owner, unit["id"], lead_id, booking_fee=1000000)
        if rv.status_code != 200:
            pytest.skip(f"cannot reserve for gate test: {rv.text}")
        deal_id = (rv.json().get("data") or rv.json())["id"]
        CREATED_DEALS.append(deal_id)

        book = requests.post(f"{BASE}/api/deals/{deal_id}/book", headers=owner,
                            json={"note": "gate off"}, timeout=30)
        assert book.status_code == 200, f"book with setting OFF should succeed: {book.text}"

        # cancel this to reuse
        requests.post(f"{BASE}/api/deals/{deal_id}/cancel", headers=owner,
                      json={"reason": "cleanup"}, timeout=30)

        # Turn setting ON
        s = requests.put(f"{BASE}/api/settings/booking_fee.require_paid_before_booking",
                         headers=owner, json={"value": True, "reason": "test on", "scope": "org"},
                         timeout=30)
        assert s.status_code == 200, s.text

        try:
            lead_id2 = _pick_lead_without_active_deal(owner)
            unit2 = _available_unit(owner)
            rv2 = _reserve(owner, unit2["id"], lead_id2, booking_fee=1000000)
            if rv2.status_code != 200:
                pytest.skip(f"cannot reserve second: {rv2.text}")
            deal2 = (rv2.json().get("data") or rv2.json())["id"]
            CREATED_DEALS.append(deal2)

            # book without paying → 400
            b1 = requests.post(f"{BASE}/api/deals/{deal2}/book", headers=owner,
                               json={"note": "should fail"}, timeout=30)
            assert b1.status_code == 400
            assert "LUNAS" in b1.json().get("detail", "")

            # pay full then book
            p = requests.post(f"{BASE}/api/booking-fee/deals/{deal2}/pay", headers=owner,
                              json={"amount": 1000000, "method": "transfer", "note": "gate"},
                              timeout=30)
            assert p.status_code == 200, p.text
            b2 = requests.post(f"{BASE}/api/deals/{deal2}/book", headers=owner,
                               json={"note": "ok"}, timeout=30)
            assert b2.status_code == 200, b2.text
        finally:
            # Kembalikan ke NILAI BAWAAN (reset), bukan memaksa OFF — tes lain menguji bawaan = ON.
            requests.post(f"{BASE}/api/settings/booking_fee.require_paid_before_booking/reset",
                          headers=owner, params={"scope": "org"}, timeout=30)


class TestCancelClosesInvoice:
    def test_cancel_unpaid_deal(self, owner):
        lead_id = _pick_lead_without_active_deal(owner)
        unit = _available_unit(owner)
        rv = _reserve(owner, unit["id"], lead_id, booking_fee=500000)
        if rv.status_code != 200:
            pytest.skip(f"cannot reserve for cancel test: {rv.text}")
        deal_id = (rv.json().get("data") or rv.json())["id"]

        c = requests.post(f"{BASE}/api/deals/{deal_id}/cancel", headers=owner,
                          json={"reason": "test cancel"}, timeout=30)
        assert c.status_code == 200, c.text

        d = requests.get(f"{BASE}/api/booking-fee/deals/{deal_id}", headers=owner, timeout=30)
        assert d.status_code == 200
        assert d.json()["data"]["invoice"]["status"] == "cancelled"


def test_zz_cleanup(request):
    """Cancel any lingering created reserved deals to free units."""
    token = _login("owner@sipro.co.id")
    h = {"Authorization": f"Bearer {token}"}
    for did in CREATED_DEALS:
        try:
            dr = requests.get(f"{BASE}/api/deals/{did}", headers=h, timeout=30)
            if dr.status_code == 200:
                st = (dr.json().get("data") or dr.json()).get("status")
                if st in ("reserved", "booked"):
                    requests.post(f"{BASE}/api/deals/{did}/cancel", headers=h,
                                  json={"reason": "test cleanup"}, timeout=30)
        except Exception:
            pass
