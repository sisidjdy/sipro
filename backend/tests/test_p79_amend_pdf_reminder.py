"""Fase 79 — amandemen skema all-in (alasan + persetujuan), PDF INB/KWB, pengingat tahap cair."""
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
def fin():
    return _sess("finance@sipro.co.id")


@pytest.fixture(scope="module")
def finlead():
    return _sess("finlead@sipro.co.id")


def _new_unit(s, project_id, prefix):
    code = s.post(f"{BASE_URL}/api/projects/{project_id}/units", json={
        "prefix": prefix, "start_index": 1, "count": 1, "type": "Tipe Uji 45", "price": 650_000_000}).json()["data"]["created"][0]
    units = s.get(f"{BASE_URL}/api/units", params={"project_id": project_id, "limit": 500}).json()["data"]
    return next(x for x in units if x["code"] == code)


@pytest.fixture(scope="module")
def ctx(s):
    proj = s.get(f"{BASE_URL}/api/projects", params={"limit": 1}).json()["data"][0]
    schemes = {x["code"]: x for x in s.get(f"{BASE_URL}/api/allin-schemes").json()["data"]}
    u = _new_unit(s, proj["id"], f"UJI79{TAG}")
    lead = s.post(f"{BASE_URL}/api/leads", json={"name": f"Uji Amandemen {TAG}", "phone": f"0818{TAG}5", "source": "walk_in"}).json()["data"]
    d = s.post(f"{BASE_URL}/api/deals/reserve", json={"unit_id": u["id"], "lead_id": lead["id"], "booking_fee": 5_000_000,
                                                      "allin_scheme_id": schemes["EXCLUDE"]["id"]}).json()["data"]
    s.post(f"{BASE_URL}/api/booking-fee/deals/{d['id']}/pay", json={"amount": 5_000_000, "method": "transfer"})
    s.post(f"{BASE_URL}/api/deals/{d['id']}/book", json={"note": "uji"})
    r = s.post(f"{BASE_URL}/api/deals/{d['id']}/convert", json={"scheme": "kpr"}).json()["data"]
    return {"schemes": schemes, "deal": d, "cid": r["contract"]["id"], "proj": proj["id"]}


def test_direct_costs_edit_locked(s, ctx):
    cid = ctx["cid"]
    s.post(f"{BASE_URL}/api/contracts/{cid}/activate", json={})
    r = s.post(f"{BASE_URL}/api/contracts/{cid}/costs", json={"bphtb": 1})
    assert r.status_code == 409 and "AMANDEMEN" in r.json()["detail"]
    # pph_seller (pajak penjual, bukan skema) tetap boleh
    assert s.post(f"{BASE_URL}/api/contracts/{cid}/costs", json={"pph_seller": 1_000_000}).status_code == 200


def test_amendment_flow_pdfs(s, fin, finlead, ctx):
    cid = ctx["cid"]
    # invoice biaya belum dibayar → ikut void saat amandemen disetujui
    inv = s.post(f"{BASE_URL}/api/contracts/{cid}/cost-invoices").json()["data"]
    assert s.get(f"{BASE_URL}/api/cost-invoices/{inv['id']}/pdf").headers["content-type"].startswith("application/pdf")
    r = fin.post(f"{BASE_URL}/api/contracts/{cid}/allin-amendments", json={"scheme_id": ctx["schemes"]["ALLIN_STD"]["id"], "reason": "pendek"})
    assert r.status_code == 400
    r = fin.post(f"{BASE_URL}/api/contracts/{cid}/allin-amendments",
                 json={"scheme_id": ctx["schemes"]["ALLIN_STD"]["id"], "reason": "Negosiasi: developer tanggung BPHTB & notaris"})
    assert r.status_code == 200, r.text
    am = r.json()["data"]
    assert am["status"] == "pending" and am["to"]["scheme_code"] == "ALLIN_STD"
    # tidak boleh 2 pending
    assert fin.post(f"{BASE_URL}/api/contracts/{cid}/allin-amendments",
                    json={"scheme_id": ctx["schemes"]["EXCLUDE"]["id"], "reason": "coba lagi dua kali"}).status_code == 400
    # finance (bukan manager) tidak boleh memutuskan → 403
    assert fin.post(f"{BASE_URL}/api/allin-amendments/{am['id']}/decide", json={"approve": True}).status_code == 403
    # tolak tanpa alasan → 400
    assert finlead.post(f"{BASE_URL}/api/allin-amendments/{am['id']}/decide", json={"approve": False}).status_code == 400
    r = finlead.post(f"{BASE_URL}/api/allin-amendments/{am['id']}/decide", json={"approve": True, "note": "ok"})
    assert r.status_code == 200, r.text
    assert r.json()["data"]["status"] == "approved"
    c = s.get(f"{BASE_URL}/api/contracts/{cid}").json()["data"]
    assert c["costs"]["scheme_code"] == "ALLIN_STD" and c["costs"]["amendment_id"] == am["id"]
    assert c["costs"]["pph_seller"] == 1_000_000
    assert c["breakdown"]["allin_scheme_code"] == "ALLIN_STD"
    rows = {x["code"]: x for x in c["breakdown"]["rows"]}
    assert rows["BPHTB"]["finance_treatment"] == "developer_borne"
    led = s.get(f"{BASE_URL}/api/contracts/{cid}/costs-ledger").json()["data"]
    assert all(i["status"] == "void" for i in led["invoices"])
    hist = s.get(f"{BASE_URL}/api/contracts/{cid}/allin-amendments").json()["data"]
    assert hist[0]["status"] == "approved" and hist[0]["decided_by"] == "finlead@sipro.co.id"
    assert s.post(f"{BASE_URL}/api/allin-amendments/{am['id']}/decide", json={"approve": True}).status_code == 400


def test_amendment_blocked_after_cost_receipt(s, fin, ctx):
    """Kontrak lain: kuitansi biaya sudah diterima → amandemen ditolak sistem; PDF KWB tercetak."""
    u = _new_unit(s, ctx["proj"], f"UJI79B{TAG}")
    lead = s.post(f"{BASE_URL}/api/leads", json={"name": f"Uji Kwitansi Biaya {TAG}", "phone": f"0819{TAG}6", "source": "walk_in"}).json()["data"]
    d = s.post(f"{BASE_URL}/api/deals/reserve", json={"unit_id": u["id"], "lead_id": lead["id"], "booking_fee": 5_000_000,
                                                      "allin_scheme_id": ctx["schemes"]["EXCLUDE"]["id"]}).json()["data"]
    s.post(f"{BASE_URL}/api/booking-fee/deals/{d['id']}/pay", json={"amount": 5_000_000, "method": "transfer"})
    s.post(f"{BASE_URL}/api/deals/{d['id']}/book", json={"note": "uji"})
    cid = s.post(f"{BASE_URL}/api/deals/{d['id']}/convert", json={"scheme": "cash_keras"}).json()["data"]["contract"]["id"]
    inv = s.post(f"{BASE_URL}/api/contracts/{cid}/cost-invoices").json()["data"]
    rc = s.post(f"{BASE_URL}/api/cost-invoices/{inv['id']}/pay", json={"amount": 1_000_000}).json()["data"]["receipt"]
    pdf = s.get(f"{BASE_URL}/api/cost-receipts/{rc['id']}/pdf")
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"
    r = fin.post(f"{BASE_URL}/api/contracts/{cid}/allin-amendments",
                 json={"scheme_id": ctx["schemes"]["ALLIN_STD"]["id"], "reason": "sudah ada kuitansi, harus ditolak"})
    assert r.status_code == 400 and "kuitansi" in r.json()["detail"].lower()


def test_tranche_reminders(s, ctx):
    cid, did = ctx["cid"], ctx["deal"]["id"]
    out = int(s.get(f"{BASE_URL}/api/finance/ar/{did}").json()["data"]["outstanding"])
    fid = s.post(f"{BASE_URL}/api/files/upload", files={"file": ("sp3k.pdf", b"%PDF-1.4 uji", "application/pdf")},
                 data={"owner_type": "contract", "owner_id": cid, "doc_type": "sp3k"}).json()["data"]["id"]
    bodies = {"berkas_lengkap": {}, "diajukan_ke_bank": {"bank": "Bank Uji"}, "appraisal": {"date": "2026-08-30", "amount": out},
              "sp3k": {"file_id": fid, "plafon": out, "number": f"SP3K-79{TAG}", "date": "2026-09-01"},
              "akad_kredit": {"date": "2026-09-02", "notary": "Notaris Uji"}}
    for _ in range(6):
        nxt = s.get(f"{BASE_URL}/api/contracts/{cid}/kpr").json()["data"].get("next_stage")
        if nxt in (None, "pencairan"):
            break
        assert s.post(f"{BASE_URL}/api/contracts/{cid}/kpr/stage/{nxt}", json=bodies[nxt]).status_code == 200
    sch = s.post(f"{BASE_URL}/api/kpr-disbursement-schemes", json={
        "name": f"Uji 79 {TAG}", "tranches": [{"code": "T1", "name": "Akad", "pct": 70, "condition": "akad"},
                                              {"code": "T2", "name": "Serah terima", "pct": 30, "condition": "serah_terima"}]}).json()["data"]
    assert s.post(f"{BASE_URL}/api/contracts/{cid}/kpr/disbursement-scheme", json={"scheme_id": sch["id"]}).status_code == 200
    ready = s.get(f"{BASE_URL}/api/kpr/tranche-reminders").json()["data"]
    mine = [x for x in ready if x["contract_id"] == cid]
    assert [x["tranche_code"] for x in mine] == ["T1"]  # T2 (serah_terima) belum terpenuhi
    r = s.post(f"{BASE_URL}/api/kpr/tranche-reminders/run").json()["data"]
    assert r["notified"] >= 1
    r2 = s.post(f"{BASE_URL}/api/kpr/tranche-reminders/run").json()["data"]
    assert r2["notified"] == 0  # tidak berulang
    notifs = s.get(f"{BASE_URL}/api/notifications", params={"limit": 50}).json()["data"]
    assert any(n.get("related_entity_type") == "kpr_tranche" and "siap dicairkan" in n["title"] for n in notifs)
    # cairkan T1 → tidak lagi siap
    assert s.post(f"{BASE_URL}/api/contracts/{cid}/kpr/stage/pencairan", json={"tranche_code": "T1"}).status_code == 200
    ready = s.get(f"{BASE_URL}/api/kpr/tranche-reminders").json()["data"]
    assert not [x for x in ready if x["contract_id"] == cid]
