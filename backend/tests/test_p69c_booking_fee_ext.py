"""P69C — Booking fee extensions:
- enforced require_paid_before_booking (default True)
- portal proof upload/submit + finance verify/reject
- refund flow (partial + finalize forfeit + PDF)
- WA reminder booking_fee_due kind + sales notification
- Settings expose booking_fee.* keys
"""
import io
import os
import datetime as dt
import pytest
import requests
from motor.motor_asyncio import AsyncIOMotorClient
import asyncio

BASE = (os.environ.get("REACT_APP_BACKEND_URL")
        or "https://sipro-pricing-engine.preview.emergentagent.com").rstrip("/")
PWD = "Sipro#2026"

CREATED_DEALS = []


def _login(email):
    r = requests.post(f"{BASE}/api/auth/login", json={"email": email, "password": PWD}, timeout=30)
    assert r.status_code == 200, f"login {email}: {r.text}"
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def owner():
    return {"Authorization": f"Bearer {_login('owner@sipro.co.id')}"}


@pytest.fixture(scope="module")
def finance():
    return {"Authorization": f"Bearer {_login('finance@sipro.co.id')}"}


@pytest.fixture(scope="module")
def sales():
    return {"Authorization": f"Bearer {_login('sales@sipro.co.id')}"}


def _available_unit(owner, exclude=None):
    r = requests.get(f"{BASE}/api/quotations/options", headers=owner, timeout=30)
    data = r.json().get("data") or r.json()
    units = data.get("units") or []
    exclude = set(exclude or [])
    for u in units:
        if u["id"] not in exclude:
            return u
    pytest.skip("No available units")


def _pick_lead(owner):
    # ID lead basis data lama sudah mati; pindai daftar lead yang belum punya deal aktif.
    lr = requests.get(f"{BASE}/api/leads?limit=200", headers=owner, timeout=30)
    if lr.status_code == 200:
        for lead in lr.json().get("data") or []:
            lid = lead.get("id")
            if not lid:
                continue
            r = requests.get(f"{BASE}/api/deals?lead_id={lid}", headers=owner, timeout=30)
            if r.status_code == 200:
                rows = r.json().get("data") or []
                if not any(d.get("status") in ("reserved", "booked", "completed") for d in rows):
                    return lid
    pytest.skip("No lead without active deal")


def _reserve(owner, unit_id, lead_id, fee=2000000):
    r = requests.post(f"{BASE}/api/deals/reserve", headers=owner,
                      json={"unit_id": unit_id, "lead_id": lead_id, "booking_fee": fee},
                      timeout=30)
    return r


# ---------------- Settings ----------------
class TestSettings:
    def test_settings_expose_booking_fee_keys(self, owner):
        r = requests.get(f"{BASE}/api/settings", headers=owner, timeout=30)
        assert r.status_code == 200, r.text
        data = r.json().get("data") or r.json()
        # settings may be dict of {key: {...}} or list; find keys
        keys_present = set()
        if isinstance(data, dict):
            keys_present = set(data.keys())
        elif isinstance(data, list):
            keys_present = {row.get("key") for row in data}
        needed = {"booking_fee.require_paid_before_booking", "booking_fee.due_days",
                  "booking_fee.reminder_days_before", "booking_fee.reminder_template"}
        assert needed.issubset(keys_present), f"missing: {needed - keys_present}"

    def test_require_paid_default_true(self, owner):
        r = requests.get(f"{BASE}/api/settings/effective?keys=booking_fee.require_paid_before_booking",
                         headers=owner, timeout=30)
        assert r.status_code == 200, r.text
        data = r.json().get("data") or r.json()
        val = data.get("booking_fee.require_paid_before_booking")
        assert val is True, f"expected True got {val}"


# ---------------- Gate enforcement + due_date ----------------
class TestGateAndDue:
    def test_reserve_book_blocked_and_then_allowed(self, owner):
        # ensure setting ON
        requests.put(f"{BASE}/api/settings/booking_fee.require_paid_before_booking",
                     headers=owner, json={"value": True, "reason": "p69c", "scope": "org"},
                     timeout=30)
        lead_id = _pick_lead(owner)
        unit = _available_unit(owner)
        rv = _reserve(owner, unit["id"], lead_id, 2000000)
        assert rv.status_code == 200, rv.text
        deal_id = (rv.json().get("data") or rv.json())["id"]
        CREATED_DEALS.append(deal_id)

        d = requests.get(f"{BASE}/api/booking-fee/deals/{deal_id}", headers=owner, timeout=30)
        inv = d.json()["data"]["invoice"]
        assert inv["status"] == "unpaid"
        # due_date roughly today+3
        today = dt.date.today()
        due = dt.date.fromisoformat(inv["due_date"][:10])
        assert 0 <= (due - today).days <= 4, f"due_date={inv['due_date']}"

        b1 = requests.post(f"{BASE}/api/deals/{deal_id}/book", headers=owner,
                           json={"note": "x"}, timeout=30)
        assert b1.status_code == 400
        assert "LUNAS" in b1.json().get("detail", "")

        p = requests.post(f"{BASE}/api/booking-fee/deals/{deal_id}/pay", headers=owner,
                          json={"amount": 2000000, "method": "transfer", "note": "lunas"},
                          timeout=30)
        assert p.status_code == 200, p.text
        b2 = requests.post(f"{BASE}/api/deals/{deal_id}/book", headers=owner,
                           json={"note": "ok"}, timeout=30)
        assert b2.status_code == 200, b2.text
        dr = requests.get(f"{BASE}/api/deals/{deal_id}", headers=owner, timeout=30)
        assert (dr.json().get("data") or dr.json()).get("status") == "booked"


# ---------------- Portal proof flow ----------------
class TestPortalProof:
    def test_portal_login_and_proof(self, owner, finance):
        lead_id = _pick_lead(owner)
        lead_r = requests.get(f"{BASE}/api/leads/{lead_id}", headers=owner, timeout=30)
        lead = lead_r.json().get("data") or lead_r.json()
        phone = lead.get("phone")
        assert phone, "lead has no phone"

        # reserve a new deal for the lead
        unit = _available_unit(owner)
        rv = _reserve(owner, unit["id"], lead_id, 1500000)
        assert rv.status_code == 200, rv.text
        deal_id = (rv.json().get("data") or rv.json())["id"]
        CREATED_DEALS.append(deal_id)

        # portal OTP
        r = requests.post(f"{BASE}/api/portal/auth/request-otp", json={"identifier": phone},
                         timeout=30)
        assert r.status_code == 200, r.text
        r2 = requests.post(f"{BASE}/api/portal/auth/verify-otp",
                           json={"identifier": phone, "code": "000000"}, timeout=30)
        assert r2.status_code == 200, r2.text
        tok = r2.json().get("token") or r2.json().get("access_token")
        assert tok
        pheaders = {"Authorization": f"Bearer {tok}"}

        # payments list
        pay = requests.get(f"{BASE}/api/portal/payments", headers=pheaders, timeout=30)
        assert pay.status_code == 200, pay.text
        rows = pay.json().get("data") or []
        row = next((x for x in rows if x["deal_id"] == deal_id), None)
        assert row and row.get("booking_fee")
        assert row["booking_fee"]["invoice"]["status"] == "unpaid"

        # upload PNG (unique bytes each run to avoid sha256 dedup)
        import os as _os
        png = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
               b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0"
               b"\x00\x00\x00\x03\x00\x01\xd7c\xe4X\x00\x00\x00\x00IEND\xaeB`\x82"
               + _os.urandom(24))
        up = requests.post(f"{BASE}/api/portal/payments/proof/upload",
                          headers=pheaders,
                          files={"file": ("bukti.png", png, "image/png")},
                          data={"deal_id": deal_id}, timeout=30)
        assert up.status_code == 200, up.text
        fid = up.json()["data"]["id"]

        # submit proof
        sp = requests.post(f"{BASE}/api/portal/booking-fee/proof", headers=pheaders,
                           json={"deal_id": deal_id, "amount": 1500000,
                                 "transfer_date": dt.date.today().isoformat(),
                                 "file_ids": [fid], "bank_name": "BCA", "note": "t"},
                           timeout=30)
        assert sp.status_code == 200, sp.text
        assert "menunggu verifikasi" in sp.json().get("message", "").lower()

        # duplicate pending → 400
        sp2 = requests.post(f"{BASE}/api/portal/booking-fee/proof", headers=pheaders,
                            json={"deal_id": deal_id, "amount": 1500000,
                                  "transfer_date": dt.date.today().isoformat(),
                                  "file_ids": [fid]}, timeout=30)
        assert sp2.status_code == 400

        # finance detail shows proof pending
        det = requests.get(f"{BASE}/api/booking-fee/deals/{deal_id}", headers=finance, timeout=30)
        assert det.status_code == 200, det.text
        proofs = det.json()["data"]["proofs"]
        assert proofs and proofs[0]["state"] == "pending"
        intake_id = proofs[0]["id"]

        # verify → paid
        v = requests.post(f"{BASE}/api/booking-fee/deals/{deal_id}/proofs/{intake_id}/verify",
                          headers=finance, json={}, timeout=30)
        assert v.status_code == 200, v.text
        assert v.json()["data"]["invoice"]["status"] == "paid"

        # portal now shows receipts + state_label
        pay2 = requests.get(f"{BASE}/api/portal/payments", headers=pheaders, timeout=30)
        row2 = next(x for x in pay2.json()["data"] if x["deal_id"] == deal_id)
        assert row2["booking_fee"]["receipts"]
        assert row2["booking_fee"]["proofs"][0]["state_label"] == "Terverifikasi"

    def test_reject_flow(self, owner, finance):
        # Create another deal + proof, then reject
        lead_id = _pick_lead(owner)
        lead = (requests.get(f"{BASE}/api/leads/{lead_id}", headers=owner, timeout=30).json()
                .get("data") or {})
        phone = lead.get("phone")
        if not phone:
            pytest.skip("no phone")
        unit = _available_unit(owner)
        rv = _reserve(owner, unit["id"], lead_id, 1000000)
        assert rv.status_code == 200, rv.text
        deal_id = (rv.json().get("data") or rv.json())["id"]
        CREATED_DEALS.append(deal_id)
        tok = requests.post(f"{BASE}/api/portal/auth/verify-otp",
                            json={"identifier": phone, "code": "000000"}, timeout=30
                            ).json().get("token")
        ph = {"Authorization": f"Bearer {tok}"}
        import os as _os
        png = b"\x89PNG\r\n\x1a\n" + _os.urandom(64)  # unique per run
        up = requests.post(f"{BASE}/api/portal/payments/proof/upload", headers=ph,
                           files={"file": ("b2.png", png, "image/png")},
                           data={"deal_id": deal_id}, timeout=30)
        fid = up.json()["data"]["id"]
        sp = requests.post(f"{BASE}/api/portal/booking-fee/proof", headers=ph,
                           json={"deal_id": deal_id, "amount": 1000000,
                                 "transfer_date": dt.date.today().isoformat(),
                                 "file_ids": [fid]}, timeout=30)
        assert sp.status_code == 200, sp.text
        det = requests.get(f"{BASE}/api/booking-fee/deals/{deal_id}", headers=finance, timeout=30)
        intake_id = det.json()["data"]["proofs"][0]["id"]

        # short reason → 400/422
        r_short = requests.post(
            f"{BASE}/api/booking-fee/deals/{deal_id}/proofs/{intake_id}/reject",
            headers=finance, json={"reason": "no"}, timeout=30)
        assert r_short.status_code in (400, 422), r_short.text
        # valid
        r_ok = requests.post(
            f"{BASE}/api/booking-fee/deals/{deal_id}/proofs/{intake_id}/reject",
            headers=finance, json={"reason": "bukti tidak jelas foto blur"}, timeout=30)
        assert r_ok.status_code == 200, r_ok.text
        det2 = requests.get(f"{BASE}/api/booking-fee/deals/{deal_id}", headers=finance, timeout=30)
        proofs2 = det2.json()["data"]["proofs"]
        st = next(p for p in proofs2 if p["id"] == intake_id)
        assert st["state"] == "rejected"
        assert "blur" in (st.get("reject_reason") or "")


# ---------------- Refund flow ----------------
class TestRefund:
    def test_refund_partial_finalize(self, owner, finance, sales):
        lead_id = _pick_lead(owner)
        unit = _available_unit(owner)
        rv = _reserve(owner, unit["id"], lead_id, 3000000)
        assert rv.status_code == 200, rv.text
        deal_id = (rv.json().get("data") or rv.json())["id"]
        CREATED_DEALS.append(deal_id)

        # refund on reserved (not cancelled) → 400
        rf_reserved = requests.post(f"{BASE}/api/booking-fee/deals/{deal_id}/refund",
                                    headers=owner,
                                    json={"amount": 100, "method": "transfer"}, timeout=30)
        assert rf_reserved.status_code == 400

        # pay full
        p = requests.post(f"{BASE}/api/booking-fee/deals/{deal_id}/pay", headers=owner,
                          json={"amount": 3000000, "method": "transfer"}, timeout=30)
        assert p.status_code == 200

        # cancel
        c = requests.post(f"{BASE}/api/deals/{deal_id}/cancel", headers=owner,
                          json={"reason": "test refund"}, timeout=30)
        assert c.status_code == 200, c.text

        det = requests.get(f"{BASE}/api/booking-fee/deals/{deal_id}", headers=owner, timeout=30)
        rd = det.json()["data"]["refund"]
        assert rd["eligible"] is True
        assert rd["refundable"] == 3000000

        # sales → 403
        rf_sales = requests.post(f"{BASE}/api/booking-fee/deals/{deal_id}/refund",
                                 headers=sales,
                                 json={"amount": 1000000, "method": "transfer",
                                       "finalize": True}, timeout=30)
        assert rf_sales.status_code == 403

        # refund 2000000, forfeit 1000000
        rf = requests.post(f"{BASE}/api/booking-fee/deals/{deal_id}/refund", headers=finance,
                           json={"amount": 2000000, "method": "transfer",
                                 "note": "cust cancel", "finalize": True}, timeout=30)
        assert rf.status_code == 200, rf.text
        body = rf.json()["data"]
        assert body["refund"]["receipt_no"].startswith("RF-BF/")
        assert body["refund"]["forfeited"] == 1000000
        assert body["invoice"]["status"] == "refunded"

        dr = requests.get(f"{BASE}/api/deals/{deal_id}", headers=owner, timeout=30)
        assert (dr.json().get("data") or dr.json()).get("booking_fee_status") == "refunded"

        # second refund → 400 (nothing left)
        rf2 = requests.post(f"{BASE}/api/booking-fee/deals/{deal_id}/refund", headers=finance,
                            json={"amount": 100, "method": "transfer"}, timeout=30)
        assert rf2.status_code == 400

        # PDF
        refund_id = body["refund"]["id"]
        pdf = requests.get(
            f"{BASE}/api/booking-fee/deals/{deal_id}/refunds/{refund_id}/pdf",
            headers=owner, timeout=30)
        assert pdf.status_code == 200
        assert pdf.headers["content-type"].startswith("application/pdf")


# ---------------- Reminder flow ----------------
class TestReminder:
    def test_booking_fee_due_reminder(self, owner):
        # Reserve a new deal
        lead_id = _pick_lead(owner)
        unit = _available_unit(owner)
        rv = _reserve(owner, unit["id"], lead_id, 500000)
        assert rv.status_code == 200, rv.text
        deal_id = (rv.json().get("data") or rv.json())["id"]
        CREATED_DEALS.append(deal_id)

        # Poke due_date to tomorrow directly via mongo
        from dotenv import load_dotenv
        load_dotenv("/app/backend/.env")
        mongo_url = os.environ["MONGO_URL"].strip('"')
        db_name = os.environ.get("DB_NAME", "sipro").strip('"')
        async def _poke():
            c = AsyncIOMotorClient(mongo_url)
            await c[db_name].booking_fee_invoices.update_one(
                {"deal_id": deal_id},
                {"$set": {"due_date": (dt.date.today() + dt.timedelta(days=1)).isoformat()}})
            c.close()
        asyncio.run(_poke())

        # candidates
        cand = requests.get(f"{BASE}/api/reminders/candidates?kind=booking_fee_due",
                            headers=owner, timeout=30)
        assert cand.status_code == 200, cand.text
        rows = cand.json().get("data") or []
        mine = [r for r in rows if r.get("entity_type") == "booking_fee_invoice"
                and r.get("unit_code") == unit.get("code")]
        assert mine, f"No booking_fee_due candidate for unit {unit.get('code')}"

        # run
        run = requests.post(f"{BASE}/api/reminders/run", headers=owner,
                            json={"kinds": ["booking_fee_due"]}, timeout=60)
        assert run.status_code == 200, run.text
        data = run.json()["data"]
        assert (data["simulated"] + data["sent"]) >= 1

        # run again → skipped (dedup)
        run2 = requests.post(f"{BASE}/api/reminders/run", headers=owner,
                             json={"kinds": ["booking_fee_due"]}, timeout=60)
        assert run2.status_code == 200
        d2 = run2.json()["data"]
        # candidates are blocked with already_sent → skipped
        per = d2.get("per_kind", {}).get("booking_fee_due", {})
        assert per.get("sent", 0) == 0
        assert per.get("simulated", 0) == 0


# ---------------- Cleanup ----------------
def test_zz_cleanup():
    tok = _login("owner@sipro.co.id")
    h = {"Authorization": f"Bearer {tok}"}
    for did in CREATED_DEALS:
        try:
            dr = requests.get(f"{BASE}/api/deals/{did}", headers=h, timeout=30)
            if dr.status_code == 200:
                st = (dr.json().get("data") or dr.json()).get("status")
                if st in ("reserved", "booked"):
                    requests.post(f"{BASE}/api/deals/{did}/cancel", headers=h,
                                  json={"reason": "cleanup p69c"}, timeout=30)
        except Exception:
            pass
    # ensure require_paid remains True
    requests.put(f"{BASE}/api/settings/booking_fee.require_paid_before_booking", headers=h,
                 json={"value": True, "reason": "restore end p69c", "scope": "org"}, timeout=30)
