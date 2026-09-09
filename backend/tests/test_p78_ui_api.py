"""Fase 76–78 — verifikasi API ringan pendukung pengujian UI (iterasi 126).

Cakupan:
- master skema pencairan KPR (POST tanpa `is_active` harus tetap aktif/terlihat di daftar aktif)
- master komponen biaya & skema all-in (pratinjau nominal)
- jurnal GL kuitansi biaya (source_type=cost_receipt) & neraca saldo balanced
- RBAC: sales tidak boleh mengetik biaya bebas / manual pada POST /deals/reserve
"""
import os
import time

import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
base_url = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base_url:
    raise RuntimeError("REACT_APP_BACKEND_URL is missing from the process environment and /app/frontend/.env")
BASE_URL = base_url.rstrip("/")
PWD = "Sipro#2026"
TAG = str(int(time.time()))[-6:]


def _client(email):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": PWD})
    if r.status_code != 200 or "access_token" not in r.json():
        pytest.fail(f"Login {email} gagal: {r.status_code} {r.text[:300]}")
    s.headers.update({"Authorization": f"Bearer {r.json()['access_token']}"})
    return s


@pytest.fixture(scope="module")
def admin():
    return _client("superadmin@sipro.co.id")


@pytest.fixture(scope="module")
def sales():
    return _client("sales2@sipro.co.id")


# --- master komponen biaya & skema all-in -------------------------------------------------
class TestAllinMasters:
    def test_cost_components_seeded(self, admin):
        r = admin.get(f"{BASE_URL}/api/cost-components")
        assert r.status_code == 200
        codes = {c["code"] for c in r.json()["data"]}
        assert {"BPHTB", "NOTARY_FEE", "BANK_FEE", "INSURANCE"} <= codes
        bphtb = next(c for c in r.json()["data"] if c["code"] == "BPHTB")
        assert bphtb["calc_method"] == "rumus_bphtb"
        assert bphtb["gl_liability"] == "2-1470"
        assert bphtb["gl_expense"] == "6-1700"

    def test_allin_scheme_preview_bphtb(self, admin):
        schemes = {s["code"]: s for s in admin.get(f"{BASE_URL}/api/allin-schemes").json()["data"]}
        assert {"ALLIN_STD", "EXCLUDE"} <= set(schemes)
        sid = schemes["EXCLUDE"]["id"]
        r = admin.get(f"{BASE_URL}/api/allin-schemes/{sid}/preview", params={"price": 650_000_000})
        assert r.status_code == 200
        comps = {c["code"]: c for c in r.json()["data"]["components"]}
        assert comps["BPHTB"]["amount"] == 28_500_000  # 5% x (650jt - 80jt NPOPTKP)
        assert all(c["treatment"] == "customer_pass_through" for c in comps.values())


# --- master skema pencairan KPR ------------------------------------------------------------
class TestKprSchemeMaster:
    def test_reject_when_pct_not_100(self, admin):
        r = admin.post(f"{BASE_URL}/api/kpr-disbursement-schemes", json={
            "name": f"UJI_TOLAK_{TAG}", "tolerance_pct": 1, "is_active": True,
            "tranches": [{"code": "T1", "name": "Akad", "pct": 60, "condition": "akad"}]})
        assert r.status_code == 400
        assert "100%" in r.json()["detail"]

    def test_create_without_is_active_stays_active(self, admin):
        """BUG P78: validate_scheme memakai payload.get('is_active', True) padahal Pydantic
        mengirim None → skema tersimpan is_active=None sehingga hilang dari daftar aktif."""
        r = admin.post(f"{BASE_URL}/api/kpr-disbursement-schemes", json={
            "name": f"UJI_DEFAULT_{TAG}", "tolerance_pct": 1,
            "tranches": [{"code": "T1", "name": "Akad", "pct": 100, "condition": "akad"}]})
        assert r.status_code == 200, r.text[:300]
        created = r.json()["data"]
        assert created["is_active"] is True, f"is_active={created['is_active']} (harus True secara default)"
        active = [x["id"] for x in admin.get(f"{BASE_URL}/api/kpr-disbursement-schemes").json()["data"]]
        assert created["id"] in active, "skema baru tidak muncul di daftar aktif"


# --- GL kuitansi biaya ---------------------------------------------------------------------
class TestCostReceiptJournal:
    def test_cost_receipt_journal_and_trial_balance(self, admin):
        found = None
        for c in admin.get(f"{BASE_URL}/api/contracts", params={"limit": 100}).json()["data"]:
            led = admin.get(f"{BASE_URL}/api/contracts/{c['id']}/costs-ledger")
            if led.status_code != 200:
                continue
            recs = (led.json()["data"] or {}).get("receipts") or []
            if recs:
                found = recs[0]
                break
        if not found:
            pytest.skip("Belum ada kuitansi biaya (KWB) — jalankan seed_p78_ui.py + bayar invoice biaya")
        r = admin.get(f"{BASE_URL}/api/gl/journals",
                      params={"source_type": "cost_receipt", "source_id": found["id"]})
        assert r.status_code == 200
        rows = r.json()["data"]
        assert len(rows) == 1, f"harus 1 jurnal, dapat {len(rows)}"
        lines = {("1-1200" if l["account_code"].startswith("1-12") else l["account_code"]): l
                 for l in rows[0]["lines"]}
        assert lines["1-1200"]["debit"] == found["amount"]
        assert lines["2-1470"]["credit"] == found["amount"]

    def test_trial_balance_balanced(self, admin):
        r = admin.get(f"{BASE_URL}/api/gl/trial-balance")
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["balanced"] is True
        assert data["total_debit"] == data["total_credit"]


# --- RBAC input biaya ----------------------------------------------------------------------
class TestReserveCostsRbac:
    def _unit_and_lead(self, admin, slug):
        proj = admin.get(f"{BASE_URL}/api/projects", params={"limit": 1}).json()["data"][0]
        r = admin.post(f"{BASE_URL}/api/projects/{proj['id']}/units", json={
            "prefix": f"UJI{slug}{TAG}", "start_index": 1, "count": 1,
            "type": "Tipe Uji 45", "price": 650_000_000})
        codes = r.json()["data"]["created"]
        assert codes, f"gagal membuat unit uji: {r.status_code} {r.text[:200]}"
        unit = next(u for u in admin.get(f"{BASE_URL}/api/units",
                                        params={"project_id": proj["id"], "limit": 800}).json()["data"]
                    if u["code"] == codes[0])
        lead = admin.post(f"{BASE_URL}/api/leads", json={
            "name": f"UJI {slug} {TAG}", "phone": f"0813{TAG}{ord(slug[0])}", "source": "walk_in",
            "owner_email": "sales2@sipro.co.id"}).json()["data"]
        return unit, lead

    def test_sales_cannot_type_free_costs(self, admin, sales):
        unit, lead = self._unit_and_lead(admin, "RBAC")
        # lead uji dimiliki sales2 (fixture `sales`); pastikan kepemilikan itu benar-benar tersimpan,
        # kalau tidak penolakan yang muncul adalah "bukan lead Anda", bukan aturan biaya.
        if lead.get("assigned_to") != "sales2@sipro.co.id":
            admin.put(f"{BASE_URL}/api/leads/{lead['id']}", json={"assigned_to": "sales2@sipro.co.id"})
        r = sales.post(f"{BASE_URL}/api/deals/reserve", json={
            "unit_id": unit["id"], "lead_id": lead["id"], "booking_fee": 5_000_000,
            "costs": {"bphtb": 1}})
        assert r.status_code == 403
        assert "skema all-in" in r.json()["detail"]

        r2 = sales.post(f"{BASE_URL}/api/deals/reserve", json={
            "unit_id": unit["id"], "lead_id": lead["id"], "booking_fee": 5_000_000,
            "costs_manual": [{"code": "BPHTB", "amount": 1, "treatment": "customer_pass_through"}],
            "costs_manual_reason": "uji manual sebagai sales"})
        assert r2.status_code == 403
        assert "finance_manager" in r2.json()["detail"]

    def test_scheme_snapshot_persisted_on_reserve(self, admin):
        unit, lead = self._unit_and_lead(admin, "SNAP")
        sid = next(s["id"] for s in admin.get(f"{BASE_URL}/api/allin-schemes").json()["data"]
                   if s["code"] == "EXCLUDE")
        r = admin.post(f"{BASE_URL}/api/deals/reserve", json={
            "unit_id": unit["id"], "lead_id": lead["id"], "booking_fee": 5_000_000,
            "allin_scheme_id": sid})
        assert r.status_code == 200, r.text[:300]
        deal_id = r.json()["data"]["id"]
        got = admin.get(f"{BASE_URL}/api/deals/{deal_id}").json()["data"]["costs"]
        assert got["scheme_code"] == "EXCLUDE"
        comps = {c["code"]: c for c in got["components"]}
        assert comps["BPHTB"]["amount"] == 28_500_000
        assert comps["BPHTB"]["treatment"] == "customer_pass_through"
