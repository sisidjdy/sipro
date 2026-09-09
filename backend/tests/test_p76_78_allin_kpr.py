"""Fase 76-78 — alur penuh: skema all-in (master) → reservasi → kontrak → invoice/kuitansi biaya
(titipan) → penyaluran → skema pencairan KPR → pencairan bertahap → AR 0 → pembatalan → GL seimbang."""
import os
import time

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
TAG = str(int(time.time()))[-6:]
PASS = "Sipro#2026"


def _sess(email):
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": PASS}, timeout=20)
    if r.status_code != 200:
        pytest.skip(f"login {email} gagal")
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {r.json()['access_token']}"})
    return s


@pytest.fixture(scope="module")
def s():
    return _sess("superadmin@sipro.co.id")


@pytest.fixture(scope="module")
def sales():
    return _sess("sales@sipro.co.id")


def _new_unit(s, project_id, prefix):
    r = s.post(f"{BASE_URL}/api/projects/{project_id}/units", json={
        "prefix": prefix, "start_index": 1, "count": 1, "type": "Tipe Uji 45", "price": 650_000_000})
    assert r.status_code in (200, 201), r.text
    code = r.json()["data"]["created"][0]
    units = s.get(f"{BASE_URL}/api/units", params={"project_id": project_id, "limit": 500}).json()["data"]
    u = next(x for x in units if x["code"] == code)
    u["project_id"] = project_id
    return u


@pytest.fixture(scope="module")
def unit(s):
    """Unit uji khusus (prefix UJI76) agar unit demo tidak habis."""
    proj = s.get(f"{BASE_URL}/api/projects", params={"limit": 5}).json()["data"][0]
    return _new_unit(s, proj["id"], f"UJI76A{TAG}")


@pytest.fixture(scope="module")
def schemes(s):
    r = s.get(f"{BASE_URL}/api/allin-schemes")
    assert r.status_code == 200, r.text
    rows = {x["code"]: x for x in r.json()["data"]}
    assert "ALLIN_STD" in rows and "EXCLUDE" in rows
    return rows


def test_master_components_seeded(s):
    r = s.get(f"{BASE_URL}/api/cost-components")
    assert r.status_code == 200
    codes = {c["code"]: c for c in r.json()["data"]}
    assert codes["BPHTB"]["calc_method"] == "rumus_bphtb"
    assert codes["BPHTB"]["gl_liability"] == "2-1470"


def test_preview_bphtb_uses_npoptkp(s, schemes, unit):
    r = s.get(f"{BASE_URL}/api/allin-schemes/{schemes['EXCLUDE']['id']}/preview",
              params={"price": 650_000_000, "project_id": unit["project_id"]})
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    bphtb = next(c for c in d["components"] if c["code"] == "BPHTB")
    assert bphtb["amount"] == round((650_000_000 - d["npoptkp"]) * 0.05)
    assert bphtb["treatment"] == "customer_pass_through"


def test_sales_cannot_type_free_costs(sales, unit):
    lead = sales.post(f"{BASE_URL}/api/leads", json={"name": f"Uji Bebas {TAG}", "phone": f"0813{TAG}11",
                                                      "source": "walk_in"}).json()["data"]
    r = sales.post(f"{BASE_URL}/api/deals/reserve", json={
        "unit_id": unit["id"], "lead_id": lead["id"], "booking_fee": 5_000_000,
        "costs": {"bphtb": 1_000_000}})
    assert r.status_code == 403, r.text
    r = sales.post(f"{BASE_URL}/api/deals/reserve", json={
        "unit_id": unit["id"], "lead_id": lead["id"], "booking_fee": 5_000_000,
        "costs_manual": [{"code": "X", "amount": 1}], "costs_manual_reason": "alasan cukup panjang"})
    assert r.status_code == 403, r.text


def test_gl_journals_source_id_filter(s):
    r = s.get(f"{BASE_URL}/api/gl/journals", params={"source_type": "receipt", "source_id": "tidak-ada"})
    assert r.status_code == 200 and r.json()["total"] == 0


@pytest.fixture(scope="module")
def deal(s, unit, schemes):
    lead = s.post(f"{BASE_URL}/api/leads", json={"name": f"Uji Exclude {TAG}", "phone": f"0814{TAG}22",
                                                  "source": "walk_in"}).json()["data"]
    r = s.post(f"{BASE_URL}/api/deals/reserve", json={
        "unit_id": unit["id"], "lead_id": lead["id"], "booking_fee": 5_000_000,
        "allin_scheme_id": schemes["EXCLUDE"]["id"]})
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["costs"]["scheme_code"] == "EXCLUDE" and d["costs"]["components"]
    return d


@pytest.fixture(scope="module")
def contract(s, deal):
    assert s.post(f"{BASE_URL}/api/booking-fee/deals/{deal['id']}/pay", json={"amount": 5_000_000, "method": "transfer"}).status_code == 200
    assert s.post(f"{BASE_URL}/api/deals/{deal['id']}/book", json={"note": "uji"}).status_code == 200
    r = s.post(f"{BASE_URL}/api/deals/{deal['id']}/convert", json={"scheme": "kpr"})
    assert r.status_code == 200, r.text
    cid = r.json()["data"]["contract"]["id"]
    # AR SINKRON: langsung ada setelah convert
    ar = s.get(f"{BASE_URL}/api/finance/ar/{deal['id']}").json()["data"]
    assert int(ar["outstanding"]) > 0
    return s.get(f"{BASE_URL}/api/contracts/{cid}").json()["data"]


def test_breakdown_pass_through_not_in_ar(s, deal, contract):
    bd = contract["breakdown"]
    rows = {r["code"]: r for r in bd["rows"]}
    assert rows["BPHTB"]["finance_treatment"] == "pass_through"
    assert rows["BPHTB"]["amount"] == next(c["amount"] for c in deal["costs"]["components"] if c["code"] == "BPHTB")
    assert bd["allin_scheme_code"] == "EXCLUDE" and bd["all_in_by_developer"] is False
    ar = s.get(f"{BASE_URL}/api/finance/ar/{deal['id']}").json()["data"]
    assert int(ar["total"]) == int(deal["price"])  # piutang = harga, biaya TIDAK masuk


def test_cost_invoice_receipt_titipan_disburse(s, contract):
    cid = contract["id"]
    r = s.post(f"{BASE_URL}/api/contracts/{cid}/cost-invoices")
    assert r.status_code == 200, r.text
    inv = r.json()["data"]
    assert inv["number"].startswith("INB")
    assert s.post(f"{BASE_URL}/api/contracts/{cid}/cost-invoices").status_code == 400  # tidak 2×
    r = s.post(f"{BASE_URL}/api/cost-invoices/{inv['id']}/pay", json={"amount": inv["total"] + 1})
    assert r.status_code == 400
    r = s.post(f"{BASE_URL}/api/cost-invoices/{inv['id']}/pay", json={"amount": inv["total"], "method": "transfer"})
    assert r.status_code == 200, r.text
    rc = r.json()["data"]["receipt"]
    assert rc["receipt_no"].startswith("KWB")
    je = s.get(f"{BASE_URL}/api/gl/journals", params={"source_type": "cost_receipt", "source_id": rc["id"]}).json()
    assert je["total"] == 1
    lines = {("1-1200" if ln["account_code"].startswith("1-12") else ln["account_code"]): ln
             for ln in je["data"][0]["lines"]}
    assert lines["1-1200"]["debit"] == inv["total"] and lines["2-1470"]["credit"] == inv["total"]
    led = s.get(f"{BASE_URL}/api/contracts/{cid}/costs-ledger").json()["data"]
    assert led["titipan_balance"] == inv["total"]
    r = s.post(f"{BASE_URL}/api/contracts/{cid}/cost-disbursements",
               json={"component_code": "BPHTB", "amount": inv["total"] + 1, "payee": "BPN"})
    assert r.status_code == 400
    bphtb = next(i["amount"] for i in inv["items"] if i["code"] == "BPHTB")
    r = s.post(f"{BASE_URL}/api/contracts/{cid}/cost-disbursements",
               json={"component_code": "BPHTB", "amount": bphtb, "payee": "BPN Kota"})
    assert r.status_code == 200, r.text
    assert r.json()["data"]["titipan_balance"] == inv["total"] - bphtb
    # kuitansi biaya tidak tercampur di AR unit
    ar = s.get(f"{BASE_URL}/api/finance/ar/{contract['deal_id']}").json()
    assert all(not x.get("receipt_no", "").startswith("KWB") for x in ar["receipts"])


def test_kpr_disbursement_scheme_tranches_cancel(s, contract):
    cid, did = contract["id"], contract["deal_id"]
    # pencairan sebelum akad/skema → ditolak dengan jelas
    out = int(s.get(f"{BASE_URL}/api/finance/ar/{did}").json()["data"]["outstanding"])
    up = s.post(f"{BASE_URL}/api/files/upload", files={"file": ("sp3k.pdf", b"%PDF-1.4 uji", "application/pdf")},
                data={"owner_type": "contract", "owner_id": cid, "doc_type": "sp3k"})
    fid = up.json()["data"]["id"]
    bodies = {"berkas_lengkap": {}, "diajukan_ke_bank": {"bank": "Bank Uji"},
              "appraisal": {"date": "2026-08-30", "amount": out},
              "sp3k": {"file_id": fid, "plafon": out, "number": "SP3K-76", "date": "2026-09-01"},
              "akad_kredit": {"date": "2026-09-02", "notary": "Notaris Uji"}}
    for _ in range(6):
        nxt = s.get(f"{BASE_URL}/api/contracts/{cid}/kpr").json()["data"].get("next_stage")
        if nxt in (None, "pencairan"):
            break
        r = s.post(f"{BASE_URL}/api/contracts/{cid}/kpr/stage/{nxt}", json=bodies[nxt])
        assert r.status_code == 200, (nxt, r.text)
    # skema 2 tahap 80/20
    r = s.post(f"{BASE_URL}/api/kpr-disbursement-schemes", json={
        "name": f"Uji 80-20 {TAG}", "bank": "Bank Uji", "tolerance_pct": 1,
        "tranches": [{"code": "T1", "name": "Akad", "pct": 80, "condition": "akad"},
                     {"code": "T2", "name": "Retensi", "pct": 20, "condition": "akad"}]})
    assert r.status_code == 200, r.text
    sid = r.json()["data"]["id"]
    bad = s.post(f"{BASE_URL}/api/kpr-disbursement-schemes", json={
        "name": "salah", "tranches": [{"code": "T1", "name": "x", "pct": 90, "condition": "akad"}]})
    assert bad.status_code == 400
    r = s.post(f"{BASE_URL}/api/contracts/{cid}/kpr/disbursement-scheme", json={"scheme_id": sid})
    assert r.status_code == 200, r.text
    tr = r.json()["data"]["tranches"]
    assert sum(t["amount"] for t in tr) == out and tr[0]["amount"] == round(out * 0.8)
    # tanpa tranche → ditolak; nominal bebas ditolak
    r = s.post(f"{BASE_URL}/api/contracts/{cid}/kpr/stage/pencairan", json={"date": "2026-09-03", "amount": 1000})
    assert r.status_code == 400 and "tahap" in r.json()["detail"].lower()
    # tahap 1
    r = s.post(f"{BASE_URL}/api/contracts/{cid}/kpr/stage/pencairan", json={"date": "2026-09-03", "tranche_code": "T1"})
    assert r.status_code == 200, r.text
    app = r.json()["data"]
    assert app["disbursements"][0]["receipt_no"] and app["disbursements"][0]["status"] == "dicatat"
    assert int(s.get(f"{BASE_URL}/api/finance/ar/{did}").json()["data"]["outstanding"]) == out - tr[0]["amount"]
    # tahap 1 lagi → ditolak 2×
    r = s.post(f"{BASE_URL}/api/contracts/{cid}/kpr/stage/pencairan", json={"tranche_code": "T1"})
    assert r.status_code == 400 and "2" in r.json()["detail"]
    # tahap 2 koreksi di luar toleransi → ditolak
    r = s.post(f"{BASE_URL}/api/contracts/{cid}/kpr/stage/pencairan",
               json={"tranche_code": "T2", "amount": tr[1]["amount"] + int(tr[1]["amount"] * 0.05)})
    assert r.status_code == 400 and "toleransi" in r.json()["detail"]
    # tahap 2 penuh → AR 0
    r = s.post(f"{BASE_URL}/api/contracts/{cid}/kpr/stage/pencairan", json={"tranche_code": "T2"})
    assert r.status_code == 200, r.text
    assert int(s.get(f"{BASE_URL}/api/finance/ar/{did}").json()["data"]["outstanding"]) == 0
    # outstanding 0 → pencairan berikutnya ditolak 409
    r = s.post(f"{BASE_URL}/api/contracts/{cid}/kpr/stage/pencairan", json={"tranche_code": "T2"})
    assert r.status_code in (400, 409)
    # pembatalan tahap 2 oleh sales → 403; oleh superadmin → jurnal balik, AR kembali
    d2 = r.json if False else s.get(f"{BASE_URL}/api/contracts/{cid}/kpr").json()["data"]["application"]["disbursements"][1]
    sales = _sess("sales@sipro.co.id")
    r = sales.post(f"{BASE_URL}/api/contracts/{cid}/kpr/disbursements/{d2['id']}/cancel", json={"reason": "salah input nominal"})
    assert r.status_code == 403
    r = s.post(f"{BASE_URL}/api/contracts/{cid}/kpr/disbursements/{d2['id']}/cancel", json={"reason": "salah input nominal bank"})
    assert r.status_code == 200, r.text
    app = r.json()["data"]
    assert app["disbursements"][1]["status"] == "dibatalkan"
    assert next(t for t in app["tranches"] if t["code"] == "T2")["status"] == "open"
    assert int(s.get(f"{BASE_URL}/api/finance/ar/{did}").json()["data"]["outstanding"]) == tr[1]["amount"]
    je = s.get(f"{BASE_URL}/api/gl/journals", params={"source_type": "receipt_void", "source_id": d2["receipt_id"]}).json()
    assert je["total"] == 1
    tb = s.get(f"{BASE_URL}/api/gl/trial-balance").json()["data"]
    assert tb["balanced"] is True


def test_allin_developer_borne_expense(s, unit, schemes):
    """Skema all-in standar: BPHTB developer_borne → tidak ada invoice biaya; beban via AP."""
    proj = unit["project_id"]
    u = _new_unit(s, proj, f"UJI76B{TAG}")
    lead = s.post(f"{BASE_URL}/api/leads", json={"name": f"Uji Allin76 {TAG}", "phone": f"0815{TAG}33",
                                                  "source": "walk_in"}).json()["data"]
    r = s.post(f"{BASE_URL}/api/deals/reserve", json={
        "unit_id": u["id"], "lead_id": lead["id"], "booking_fee": 5_000_000,
        "allin_scheme_id": schemes["ALLIN_STD"]["id"]})
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    s.post(f"{BASE_URL}/api/booking-fee/deals/{d['id']}/pay", json={"amount": 5_000_000, "method": "transfer"})
    s.post(f"{BASE_URL}/api/deals/{d['id']}/book", json={"note": "uji"})
    cid = s.post(f"{BASE_URL}/api/deals/{d['id']}/convert", json={"scheme": "cash_keras"}).json()["data"]["contract"]["id"]
    bd = s.get(f"{BASE_URL}/api/contracts/{cid}").json()["data"]["breakdown"]
    rows = {r["code"]: r for r in bd["rows"]}
    assert rows["BPHTB"]["finance_treatment"] == "developer_borne" and bd["costs_total"] == 0
    assert bd["developer_borne_total"] == rows["BPHTB"]["amount"] + rows["NOTARY_FEE"]["amount"]
    assert s.post(f"{BASE_URL}/api/contracts/{cid}/cost-invoices").status_code == 400
    r = s.post(f"{BASE_URL}/api/contracts/{cid}/cost-expenses",
               json={"component_code": "BPHTB", "amount": rows["BPHTB"]["amount"], "vendor": "Notaris Uji"})
    assert r.status_code == 200, r.text
    bill = r.json()["data"]["ap_bill"]
    je = s.get(f"{BASE_URL}/api/gl/journals", params={"source_type": "ap_bill", "source_id": bill["id"]}).json()
    lines = {("1-1200" if ln["account_code"].startswith("1-12") else ln["account_code"]): ln
             for ln in je["data"][0]["lines"]}
    assert lines["6-1700"]["debit"] == rows["BPHTB"]["amount"] and lines["2-1100"]["credit"] == rows["BPHTB"]["amount"]
    assert s.post(f"{BASE_URL}/api/contracts/{cid}/cost-expenses",
                  json={"component_code": "BPHTB", "amount": 1}).status_code == 400  # tidak 2×


def test_addon_zero_blocked_and_override(s, unit):
    r = s.post(f"{BASE_URL}/api/catalog/addons", json={"code": f"ADD-NOL{TAG}", "name": "Add-on Nol", "unit_price": 0,
                                                       "pricing_mode": "lump_sum", "category": "spek"})
    if r.status_code not in (200, 201):
        pytest.skip(f"master add-on tidak bisa dibuat: {r.status_code} {r.text[:120]}")
    code = r.json()["data"]["code"]
    r_id = r.json()["data"]["id"]
    u = _new_unit(s, unit["project_id"], f"UJI76C{TAG}")
    lead = s.post(f"{BASE_URL}/api/leads", json={"name": f"Uji Nol {TAG}", "phone": f"0816{TAG}44",
                                                  "source": "walk_in"}).json()["data"]
    body = {"unit_id": u["id"], "lead_id": lead["id"], "booking_fee": 5_000_000, "addons": [{"code": code, "qty": 1}]}
    r = s.post(f"{BASE_URL}/api/deals/reserve", json=body)
    assert r.status_code == 409, r.text
    r = s.post(f"{BASE_URL}/api/deals/reserve", json={**body, "addon_zero_override": {
        "reason": "promo dapur gratis disetujui manajer", "prices": {code: 10_000_000}}})
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["price"] == 650_000_000  # net tetap
    assert any(l.get("source") == "override" and l["amount"] == 10_000_000 for l in d["pricing"]["discount_lines"])
    assert d["pricing"]["gross_price"] == 660_000_000
    # bersihkan: add-on uji dinonaktifkan agar master add-on demo tetap "semua berharga"
    s.put(f"{BASE_URL}/api/catalog/addons/{r_id}", json={"active": False, "unit_price": 10_000_000})
