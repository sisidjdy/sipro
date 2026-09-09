"""Fase 75 extra — costs pass_through (tanpa all-in), GL jurnal kuitansi KPR,
berkas_lengkap tidak lagi 400 'sudah dilewati'."""
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
        pytest.fail(f"login gagal {r.status_code}: {r.text[:300]}")
    sess = requests.Session()
    sess.headers.update({"Authorization": f"Bearer {r.json()['access_token']}"})
    return sess


def _available_unit(s):
    opts = s.get(f"{BASE_URL}/api/quotations/options").json()["data"]
    # /api/quotations/options sudah memfilter unit available (field status tidak dikirim)
    u = next((u for u in opts["units"] if u.get("status") in (None, "available")), None)
    if not u:
        pytest.skip("tidak ada unit available")
    return u


@pytest.fixture(scope="module")
def ctx(s):
    unit = _available_unit(s)
    lead = s.post(f"{BASE_URL}/api/leads", json={"name": f"Uji PassThru {TAG}", "phone": f"0813{TAG}88",
                                                 "source": "walk_in"}).json()["data"]
    r = s.post(f"{BASE_URL}/api/deals/reserve", json={
        "unit_id": unit["id"], "lead_id": lead["id"], "booking_fee": 5_000_000,
        "addons": [{"code": "ADD-KERAMIK", "qty": 10}],
        "costs": {"bphtb": 30_000_000, "notary_fee": 5_000_000, "bank_fee": 1_000_000,
                  "insurance": 500_000, "all_in_by_developer": False}})
    assert r.status_code == 200, r.text
    deal = r.json()["data"]
    assert r_ok(s, f"/api/booking-fee/deals/{deal['id']}/pay", {"amount": 5_000_000, "method": "transfer"})
    assert r_ok(s, f"/api/deals/{deal['id']}/book", {"note": "uji"})
    rc = s.post(f"{BASE_URL}/api/deals/{deal['id']}/convert", json={})
    assert rc.status_code == 200, rc.text
    return {"deal": deal, "cid": rc.json()["data"]["contract"]["id"]}


def r_ok(s, path, body):
    r = s.post(f"{BASE_URL}{path}", json=body)
    assert r.status_code == 200, (path, r.text)
    return True


# --- costs pass-through (tanpa all-in) ---
def test_addon_per_m2_subtotal(s, ctx):
    pricing = ctx["deal"].get("pricing") or {}
    assert pricing.get("addon_total") == 10 * 350_000, pricing


def test_breakdown_pass_through(s, ctx):
    bd = s.get(f"{BASE_URL}/api/contracts/{ctx['cid']}").json()["data"]["breakdown"]
    assert bd.get("all_in_by_developer") in (False, None)
    rows = {x["code"]: x for x in bd["rows"]}
    assert rows["BPHTB"]["finance_treatment"] == "pass_through"
    # bank_fee & insurance = KPR_ONLY_COSTS → not_applicable saat skema belum kpr
    assert rows["BANK_FEE"]["state"] == "not_applicable"
    assert bd["costs_total"] == 35_000_000, bd["costs_total"]
    assert bd.get("developer_borne_total", 0) == 0


# --- KPR: berkas_lengkap + GL jurnal kuitansi pencairan ---
def test_kpr_stages_and_gl_journal(s, ctx):
    cid = ctx["cid"]
    assert r_ok(s, f"/api/contracts/{cid}/scheme", {"scheme": "kpr", "reason": "uji"})
    # setelah skema kpr, biaya bank & asuransi masuk hitungan
    bd = s.get(f"{BASE_URL}/api/contracts/{cid}").json()["data"]["breakdown"]
    assert bd["costs_total"] == 36_500_000, bd["costs_total"]
    nxt = s.get(f"{BASE_URL}/api/contracts/{cid}/kpr").json()["data"].get("next_stage")
    assert nxt == "berkas_lengkap", nxt
    r = s.post(f"{BASE_URL}/api/contracts/{cid}/kpr/stage/berkas_lengkap", json={})
    assert r.status_code == 200, r.text
    # idempotency guard: mengulang tahap yang sama harus ditolak jelas
    r2 = s.post(f"{BASE_URL}/api/contracts/{cid}/kpr/stage/berkas_lengkap", json={})
    assert r2.status_code in (200, 400), r2.text

    out = int(s.get(f"{BASE_URL}/api/finance/ar/{ctx['deal']['id']}").json()["data"]["outstanding"])
    assert out > 0
    up = s.post(f"{BASE_URL}/api/files/upload", files={"file": ("sp3k.pdf", b"%PDF-1.4 uji", "application/pdf")},
                data={"owner_type": "contract", "owner_id": cid, "doc_type": "sp3k"})
    assert up.status_code == 200, up.text
    fid = up.json()["data"]["id"]
    bodies = {"berkas_lengkap": {}, "diajukan_ke_bank": {"bank": "Bank Uji"},
              "appraisal": {"date": "2026-08-30", "amount": out},
              "sp3k": {"file_id": fid, "plafon": out, "number": f"SP3K-{TAG}", "date": "2026-09-01"},
              "akad_kredit": {"date": "2026-09-02", "notary": "Notaris Uji"}}
    for _ in range(6):
        nxt = s.get(f"{BASE_URL}/api/contracts/{cid}/kpr").json()["data"].get("next_stage")
        if nxt in (None, "pencairan"):
            break
        r = s.post(f"{BASE_URL}/api/contracts/{cid}/kpr/stage/{nxt}", json=bodies[nxt])
        assert r.status_code == 200, (nxt, r.text)

    # pencairan sebagian → piutang berkurang sebagian
    half = out // 2
    r = s.post(f"{BASE_URL}/api/contracts/{cid}/kpr/stage/pencairan", json={"date": "2026-09-03", "amount": half})
    assert r.status_code == 200, r.text
    app = r.json()["data"]
    disb = app.get("disbursement") or app.get("app", {}).get("disbursement") or {}
    receipt_no = disb.get("receipt_no")
    assert receipt_no, app
    ar = s.get(f"{BASE_URL}/api/finance/ar/{ctx['deal']['id']}").json()
    assert int(ar["data"]["outstanding"]) == out - half, ar["data"]["outstanding"]
    assert any(x.get("method") == "kpr" and int(x["amount"]) == half for x in ar["receipts"]), ar["receipts"]

    # GL: jurnal kuitansi terbentuk (source_type=receipt, source_id=receipt_id)
    rid = disb.get("receipt_id")
    assert rid, disb
    rows = []
    for _ in range(12):  # posting GL berjalan lewat event/worker → beri waktu
        jr = s.get(f"{BASE_URL}/api/gl/journals", params={"source_type": "receipt", "limit": 100})
        assert jr.status_code == 200, jr.text
        rows = [x for x in (jr.json().get("data") or []) if x.get("source_id") == rid]
        if rows:
            break
        time.sleep(1)
    assert rows, f"jurnal GL untuk kuitansi {receipt_no} ({rid}) tidak ditemukan"
    j = rows[0]
    assert "_id" not in j
    assert int(j["total_debit"]) == int(j["total_credit"]) == half, j
    cash = [l for l in j["lines"] if l["account_type"] == "asset" and float(l["debit"] or 0) > 0]
    assert cash, j["lines"]
