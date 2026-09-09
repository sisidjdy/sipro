"""Fase 75 — SPR: biaya transaksi (all-in) ikut ke kontrak; pencairan KPR dibukukan
sebagai kuitansi (piutang berkurang, GL kas masuk); add-on master berharga."""
import os
import time

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
TAG = str(int(time.time()))[-6:]


@pytest.fixture(scope="module")
def s():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": "superadmin@sipro.co.id", "password": "Sipro#2026"}, timeout=20)
    if r.status_code != 200:
        pytest.skip("login gagal")
    sess = requests.Session()
    sess.headers.update({"Authorization": f"Bearer {r.json()['access_token']}"})
    return sess


@pytest.fixture(scope="module")
def deal(s):
    opts = s.get(f"{BASE_URL}/api/quotations/options").json()["data"]
    unit = next((u for u in opts["units"] if u.get("status") == "available"), opts["units"][0])
    lead = s.post(f"{BASE_URL}/api/leads", json={"name": f"Uji Allin {TAG}", "phone": f"0812{TAG}99",
                                                  "source": "walk_in"}).json()["data"]
    r = s.post(f"{BASE_URL}/api/deals/reserve", json={
        "unit_id": unit["id"], "lead_id": lead["id"], "booking_fee": 5_000_000,
        "addons": [{"code": "ADD-DAPUR", "qty": 1}],
        "costs": {"bphtb": 42_500_000, "notary_fee": 7_500_000, "bank_fee": "", "all_in_by_developer": True}})
    assert r.status_code == 200, r.text
    return r.json()["data"]


def test_addon_master_has_prices(s):
    addons = s.get(f"{BASE_URL}/api/quotations/options").json()["data"]["addons"]
    zero = [a["code"] for a in addons if not a.get("unit_price")]
    assert not zero, f"add-on tanpa harga: {zero}"


def test_costs_saved_on_deal_and_price_includes_addon(s, deal):
    # Fase 76: `costs` bebas (superadmin) dipetakan ke komponen LEGACY — nilai lama tetap ada.
    assert {k: deal["costs"][k] for k in ("bphtb", "notary_fee", "all_in_by_developer")} == {
        "bphtb": 42_500_000, "notary_fee": 7_500_000, "all_in_by_developer": True}
    assert deal["costs"]["scheme_code"] == "LEGACY" and len(deal["costs"]["components"]) == 2
    pricing = deal.get("pricing") or {}
    assert pricing.get("addon_total", 0) >= 18_500_000  # Kitchen set punya harga di master


def test_costs_flow_to_contract_breakdown_all_in(s, deal):
    r = s.post(f"{BASE_URL}/api/booking-fee/deals/{deal['id']}/pay", json={"amount": 5_000_000, "method": "transfer"})
    assert r.status_code == 200, r.text
    r = s.post(f"{BASE_URL}/api/deals/{deal['id']}/book", json={"note": "uji"})
    assert r.status_code == 200, r.text
    r = s.post(f"{BASE_URL}/api/deals/{deal['id']}/convert", json={})
    assert r.status_code == 200, r.text
    cid = r.json()["data"]["contract"]["id"]
    bd = s.get(f"{BASE_URL}/api/contracts/{cid}").json()["data"]["breakdown"]
    assert bd["all_in_by_developer"] is True
    rows = {x["code"]: x for x in bd["rows"]}
    assert rows["BPHTB"]["finance_treatment"] == "developer_borne" and rows["BPHTB"]["amount"] == 42_500_000
    assert "ditanggung developer" in rows["BPHTB"]["note"]
    assert bd["costs_total"] == 0 and bd["developer_borne_total"] == 50_000_000
    os.environ["P75_CID"] = cid


def test_kpr_disbursement_books_receipt_and_reduces_ar(s, deal):
    cid = os.environ["P75_CID"]
    r = s.post(f"{BASE_URL}/api/contracts/{cid}/scheme", json={"scheme": "kpr", "reason": "uji"})
    assert r.status_code == 200, r.text
    inv_before = s.get(f"{BASE_URL}/api/finance/ar/{deal['id']}").json()["data"]
    out_before = int(inv_before["outstanding"])
    assert out_before > 0
    up = s.post(f"{BASE_URL}/api/files/upload", files={"file": ("sp3k.pdf", b"%PDF-1.4 uji", "application/pdf")},
                data={"owner_type": "contract", "owner_id": cid, "doc_type": "sp3k"})
    assert up.status_code == 200, up.text
    fid = up.json()["data"]["id"]
    bodies = {"berkas_lengkap": {}, "diajukan_ke_bank": {"bank": "Bank Uji"},
              "appraisal": {"date": "2026-08-30", "amount": out_before},
              "sp3k": {"file_id": fid, "plafon": out_before, "number": "SP3K-1", "date": "2026-09-01"},
              "akad_kredit": {"date": "2026-09-02", "notary": "Notaris Uji"}}
    for _ in range(6):
        nxt = s.get(f"{BASE_URL}/api/contracts/{cid}/kpr").json()["data"].get("next_stage")
        if nxt in (None, "pencairan"):
            break
        r = s.post(f"{BASE_URL}/api/contracts/{cid}/kpr/stage/{nxt}", json=bodies[nxt])
        assert r.status_code == 200, (nxt, r.text)
    # pencairan tanpa nominal → ditolak (bukan catatan kosong)
    r = s.post(f"{BASE_URL}/api/contracts/{cid}/kpr/stage/pencairan", json={"date": "2026-09-03"})
    assert r.status_code == 400 and "Nominal" in r.json()["detail"]
    amount = out_before
    r = s.post(f"{BASE_URL}/api/contracts/{cid}/kpr/stage/pencairan", json={"date": "2026-09-03", "amount": amount})
    assert r.status_code == 200, r.text
    app = r.json()["data"]
    disb = app.get("disbursement") or app.get("app", {}).get("disbursement") or {}
    assert disb.get("receipt_id") and disb.get("receipt_no")
    ar = s.get(f"{BASE_URL}/api/finance/ar/{deal['id']}").json()
    assert int(ar["data"]["outstanding"]) == 0
    recs = ar["receipts"]
    kpr_rc = [x for x in recs if x.get("method") == "kpr"]
    assert kpr_rc and int(kpr_rc[0]["amount"]) == amount
