"""Backend tests for iteration 12: doc INVOICE_BF, AR receipt allocations, phase sync,
build template overlap, and financing disburse always-book-to-AR."""
import os, json, requests, pytest

BASE = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8001").rstrip("/")
HDRS = {"User-Agent": "curl/8", "Content-Type": "application/json"}
DEAL_ID = "3266be54-0961-4105-b543-9d7dae616bd6"


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{BASE}/api/auth/login",
                      json={"email": "superadmin@sipro.co.id", "password": "Sipro#2026"},
                      headers=HDRS, timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    tok = d.get("token") or d.get("access_token") or d.get("data", {}).get("token")
    assert tok
    return tok


@pytest.fixture(scope="module")
def api(token):
    s = requests.Session()
    s.headers.update({**HDRS, "Authorization": f"Bearer {token}"})
    return s


# --- INVOICE_BF layout & PDF ---
class TestInvoiceBF:
    def test_layout_get(self, api):
        r = api.get(f"{BASE}/api/doc-layouts/INVOICE_BF", timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["data"]["code"] == "INVOICE_BF"

    def test_layout_in_list(self, api):
        r = api.get(f"{BASE}/api/doc-layouts", timeout=30)
        assert r.status_code == 200
        codes = [x.get("code") for x in r.json().get("data", [])]
        assert "INVOICE_BF" in codes

    def test_bf_invoice_pdf(self, api):
        r = api.get(f"{BASE}/api/booking-fee/deals/{DEAL_ID}/invoice/pdf", timeout=30)
        # If the deal has no BF invoice, try to find any BF invoice deal
        if r.status_code != 200:
            inv = api.get(f"{BASE}/api/booking-fee/invoices", timeout=30).json().get("data", [])
            if inv:
                deal2 = inv[0].get("deal_id")
                r = api.get(f"{BASE}/api/booking-fee/deals/{deal2}/invoice/pdf", timeout=30)
        assert r.status_code == 200, r.text[:200]
        assert "pdf" in r.headers.get("content-type", "").lower()


# --- AR receipt allocations ---
class TestARAllocations:
    def test_get_ar(self, api):
        r = api.get(f"{BASE}/api/finance/ar/{DEAL_ID}", timeout=30)
        assert r.status_code == 200
        assert "items" in r.json()["data"]

    def test_allocate_to_termin_ii(self, api):
        ar = api.get(f"{BASE}/api/finance/ar/{DEAL_ID}", timeout=30).json()["data"]
        t2 = next((i for i in ar["items"] if i["label"].startswith("Termin II")), None)
        assert t2, "Termin II must exist"
        before_paid = t2.get("paid_amount", 0)
        remaining = t2["amount"] - before_paid
        amt = min(5_000_000, remaining) if remaining > 0 else 5_000_000
        assert remaining >= amt, f"Not enough remaining in Termin II ({remaining})"
        r = api.post(f"{BASE}/api/finance/ar/receipts", json={
            "deal_id": DEAL_ID, "amount": amt, "method": "transfer",
            "allocations": [{"item_id": t2["id"], "amount": amt}],
        }, timeout=30)
        assert r.status_code == 200, r.text
        allocs = r.json()["data"]["receipt"]["allocations"]
        assert any(a["item_id"] == t2["id"] and a["amount"] == amt for a in allocs)
        ar2 = api.get(f"{BASE}/api/finance/ar/{DEAL_ID}", timeout=30).json()["data"]
        t2b = next(i for i in ar2["items"] if i["id"] == t2["id"])
        assert t2b.get("paid_amount", 0) == before_paid + amt

    def test_overalloc_rejected(self, api):
        ar = api.get(f"{BASE}/api/finance/ar/{DEAL_ID}", timeout=30).json()["data"]
        t2 = next(i for i in ar["items"] if i["label"].startswith("Termin II"))
        r = api.post(f"{BASE}/api/finance/ar/receipts", json={
            "deal_id": DEAL_ID, "amount": 10_000_000, "method": "transfer",
            "allocations": [{"item_id": t2["id"], "amount": 999_999_999}],
        }, timeout=30)
        assert r.status_code == 400, r.text
        assert "melebihi" in r.text.lower() or "sisa" in r.text.lower()


# --- Phase sync ---
class TestPhaseSync:
    def test_first_project_synced_phase(self, api):
        projs = api.get(f"{BASE}/api/projects?limit=1", timeout=30).json().get("data", [])
        assert projs
        pid = projs[0]["id"]
        ph = api.get(f"{BASE}/api/construction/project/{pid}/phases", timeout=30).json()["data"]
        synced = [p for p in ph if p.get("progress_source") == "unit_schedules"]
        assert synced, "expected at least one synced phase"
        # ensure 'Persiapan Lahan' with work_category=persiapan
        pers = next((p for p in ph if p["name"] == "Persiapan Lahan"), None)
        if pers:
            assert pers.get("work_category") == "persiapan"
            assert pers.get("progress_source") == "unit_schedules"

    def test_manual_progress_on_synced_rejected(self, api):
        projs = api.get(f"{BASE}/api/projects?limit=1", timeout=30).json()["data"]
        pid = projs[0]["id"]
        ph = api.get(f"{BASE}/api/construction/project/{pid}/phases", timeout=30).json()["data"]
        synced = next(p for p in ph if p.get("progress_source") == "unit_schedules")
        r = api.post(f"{BASE}/api/construction/phases/{synced['id']}/progress",
                     json={"progress": 50}, timeout=30)
        assert r.status_code == 409, r.text

    def test_create_and_delete_phase(self, api):
        projs = api.get(f"{BASE}/api/projects?limit=1", timeout=30).json()["data"]
        pid = projs[0]["id"]
        r = api.post(f"{BASE}/api/construction/phases",
                     json={"project_id": pid, "name": "QA Fase Uji", "weight": 5}, timeout=30)
        assert r.status_code == 200, r.text
        new_id = r.json()["data"]["id"]
        rd = api.delete(f"{BASE}/api/construction/phases/{new_id}", timeout=30)
        assert rd.status_code == 200, rd.text


# --- Build template overlap ---
class TestBuildTemplateOverlap:
    def test_clone_overlap_rejected(self, api):
        tp = api.get(f"{BASE}/api/build/templates", timeout=30).json().get("data", [])
        src = next((x for x in tp if x.get("unit_types")), None)
        assert src, "need a template with unit_types"
        r = api.post(f"{BASE}/api/build/templates/clone", json={
            "clone_from": src["id"], "code": "QA-OVERLAP-IT12",
            "name": "QA overlap it12", "unit_types": src["unit_types"],
        }, timeout=30)
        assert r.status_code == 409, r.text
        assert "template" in r.text.lower()

    def test_clone_no_overlap_ok_then_delete(self, api):
        tp = api.get(f"{BASE}/api/build/templates", timeout=30).json().get("data", [])
        src = next(x for x in tp if x.get("unit_types"))
        # Use a unit_type value guaranteed not to overlap
        uniq = ["__QA_TYPE_IT12__"]
        r = api.post(f"{BASE}/api/build/templates/clone", json={
            "clone_from": src["id"], "code": "QA-NO-OVERLAP-IT12",
            "name": "QA no overlap it12", "unit_types": uniq,
        }, timeout=30)
        assert r.status_code == 200, r.text
        new_id = r.json()["data"]["id"]
        rd = api.delete(f"{BASE}/api/build/templates/{new_id}", timeout=30)
        assert rd.status_code == 200, rd.text


# --- Financing disburse always books to AR ---
class TestFinancingDisburse:
    def test_disburse_books_to_ar(self, api):
        # find a financing tied to a deal that has AR
        fins = api.get(f"{BASE}/api/financing", timeout=30)
        if fins.status_code != 200:
            pytest.skip(f"no /api/financing list: {fins.status_code}")
        data = fins.json().get("data", [])
        chosen = None
        for f in data:
            did = f.get("deal_id")
            if not did:
                continue
            ar = api.get(f"{BASE}/api/finance/ar/{did}", timeout=15)
            if ar.status_code == 200 and ar.json().get("data", {}).get("items"):
                chosen = f
                break
        if not chosen:
            pytest.skip("no financing with AR-issued deal found")
        r = api.post(f"{BASE}/api/financing/{chosen['id']}/disburse", json={
            "amount": 1_000_000, "milestone": "QA IT12",
        }, timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        arb = body.get("ar_booking") or body.get("data", {}).get("ar_booking") or {}
        assert arb.get("booked") is True, r.text
