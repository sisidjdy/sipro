"""Uji SPR vs Tagihan Finance + tombol SPR resmi + jalur lama ditutup (iteration 21)."""
import os
import time

import pytest
import requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
PW = "Sipro#2026"


def _login(email):
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": PW}, timeout=30)
    assert r.status_code == 200, r.text
    j = r.json()
    tok = j.get("token") or j.get("access_token") or (j.get("data") or {}).get("token") or (j.get("data") or {}).get("access_token")
    return {"Authorization": f"Bearer {tok}"}


def _j(r):
    try:
        return r.json()
    except Exception:  # noqa: BLE001
        return {}


@pytest.fixture(scope="module")
def ctx():
    sa = _login("superadmin@sipro.co.id")
    fin = _login("finance@sipro.co.id")
    tanda = str(int(time.time()))[-6:]
    lead = _j(requests.post(f"{BASE}/leads", headers=sa, json={
        "name": f"IT21 Uji SPR {tanda}", "phone": f"+62812{tanda}21", "source": "walk_in"},
        timeout=30))["data"]
    units = _j(requests.get(f"{BASE}/units", headers=sa, params={"status": "available", "limit": 30},
                            timeout=30))["data"]
    from pymongo import MongoClient
    load_dotenv("/app/backend/.env")
    db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    sched = set(db.build_schedules.distinct("unit_id"))
    unit = next(u for u in units if u["id"] not in sched)
    schemes = _j(requests.get(f"{BASE}/payment-schemes", headers=sa, timeout=30))["data"]
    stg = next(s for s in schemes if s["kind"] == "cash_bertahap" and s.get("active", True))
    deal = _j(requests.post(f"{BASE}/deals/reserve", headers=sa, json={
        "lead_id": lead["id"], "unit_id": unit["id"], "booking_fee": 5000000,
        "scheme_id": stg["id"], "notes": "iter21"}, timeout=30))["data"]
    requests.post(f"{BASE}/booking-fee/deals/{deal['id']}/pay", headers=sa,
                  json={"amount": 5000000, "method": "transfer"}, timeout=30)
    r = requests.post(f"{BASE}/deals/{deal['id']}/book", headers=sa, json={}, timeout=30)
    assert r.status_code == 200, r.text
    yield {"sa": sa, "fin": fin, "deal": deal, "lead": lead, "tanda": tanda, "stg": stg, "db": db}
    requests.delete(f"{BASE}/deals/{deal['id']}", headers=sa,
                    params={"reason": "bersih-bersih uji iteration 21"}, timeout=60)
    requests.delete(f"{BASE}/leads/{lead['id']}", headers=sa,
                    params={"force": "true", "reason": "bersih-bersih uji iteration 21"}, timeout=60)


def test_legacy_spr_closed(ctx):
    r = requests.post(f"{BASE}/documents", headers=ctx["sa"],
                      json={"template_code": "SPR", "deal_id": ctx["deal"]["id"]}, timeout=30)
    assert r.status_code == 400 and "kontrak" in _j(r)["detail"].lower(), r.text


def test_compare_without_contract(ctx):
    r = requests.get(f"{BASE}/finance/ar/{ctx['deal']['id']}/spr-compare", headers=ctx["fin"], timeout=30)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["state"] == "tanpa_kontrak"


def test_official_spr_then_compare(ctx):
    sa, deal = ctx["sa"], ctx["deal"]
    cv = _j(requests.post(f"{BASE}/deals/{deal['id']}/convert", headers=sa, json={
        "nik": f"3201{ctx['tanda']}0001", "address": "Jl. Uji 21"}, timeout=60))
    cid = cv["data"]["contract"]["id"]
    ctx["cid"] = cid
    av = _j(requests.get(f"{BASE}/contracts/{cid}/documents/available", headers=sa, timeout=30))
    code = av["recommended_code"]
    assert code == "SPR_CASH_STAGED"
    tpl = next(t for t in av["data"] if t["code"] == code)
    assert tpl["can_generate"], tpl["blocks"]
    r = requests.post(f"{BASE}/contracts/{cid}/documents", headers=sa, json={"template_code": code}, timeout=60)
    assert r.status_code == 200, r.text
    doc = r.json()["data"]
    ctx["doc"] = doc
    assert doc["amounts_snapshot"]["terms"], "snapshot angka SPR harus ada"
    # jalur lama tetap tertutup walau kontrak sudah ada
    r = requests.post(f"{BASE}/documents", headers=sa,
                      json={"template_code": "SPR", "deal_id": deal["id"]}, timeout=30)
    assert r.status_code == 400
    cmp = _j(requests.get(f"{BASE}/finance/ar/{deal['id']}/spr-compare", headers=ctx["fin"], timeout=30))["data"]
    assert cmp["state"] == "cocok", cmp["verdict"]
    assert cmp["all_match"] is True and cmp["spr_source"] == "snapshot"
    assert cmp["document"]["id"] == doc["id"]
    keys = {r["key"] for r in cmp["rows"]}
    assert {"nett_price", "booking_fee", "terms_count", "terms_total", "total_bill"} <= keys
    ar = _j(requests.get(f"{BASE}/finance/ar/{deal['id']}", headers=ctx["fin"], timeout=30))["data"]
    tot = next(r for r in cmp["rows"] if r["key"] == "terms_total")
    assert tot["finance"] == ar["unit_total"] == tot["spr"]


def test_scheme_change_makes_mismatch_and_blocks_sign(ctx):
    sa, fin, deal, cid, doc = ctx["sa"], ctx["fin"], ctx["deal"], ctx["cid"], ctx["doc"]
    finlead = _login("owner@sipro.co.id")
    # skema baru berjenis sama dengan termin berbeda
    terms = [{"label": "DP 30%", "basis": "percent", "value": 30},
             {"label": "Cicilan 1", "basis": "percent", "value": 35},
             {"label": "Pelunasan", "basis": "remaining", "value": 0}]
    sch = _j(requests.post(f"{BASE}/payment-schemes", headers=sa, json={
        "name": f"IT21 tiga termin {ctx['tanda']}", "kind": "cash_bertahap", "terms": terms}, timeout=30))
    assert sch.get("data"), sch
    ctx["sch"] = sch["data"]
    r = requests.post(f"{BASE}/payment-schemes/contracts/{cid}", headers=finlead,
                      json={"scheme_id": sch["data"]["id"], "reason": "uji iteration 21 ganti skema"}, timeout=60)
    assert r.status_code == 200, r.text
    ar = _j(requests.get(f"{BASE}/finance/ar/{deal['id']}", headers=fin, timeout=30))["data"]
    assert ar["scheme_id"] == sch["data"]["id"] and len([i for i in ar["items"] if i.get("basis") != "addon"]) == 3
    assert ar["paid"] == 5000000, "booking fee tetap teralokasi"
    cmp = _j(requests.get(f"{BASE}/finance/ar/{deal['id']}/spr-compare", headers=fin, timeout=30))["data"]
    assert cmp["state"] == "beda" and cmp["mismatch_count"] > 0
    assert next(r for r in cmp["rows"] if r["key"] == "term_2")["match"] is False
    # tanda tangan ditolak
    requests.post(f"{BASE}/documents/{doc['id']}/finalize", headers=sa, timeout=30)
    r = requests.post(f"{BASE}/documents/{doc['id']}/sign", headers=sa,
                      json={"role": "buyer", "name": "Uji"}, timeout=30)
    assert r.status_code == 400 and "berbeda" in _j(r)["detail"], r.text
    # terbitkan ulang → cocok lagi → boleh ditandatangani
    r = requests.post(f"{BASE}/contracts/{cid}/documents", headers=sa,
                      json={"template_code": "SPR_CASH_STAGED"}, timeout=60)
    assert r.status_code == 200, r.text
    doc2 = r.json()["data"]
    cmp = _j(requests.get(f"{BASE}/finance/ar/{deal['id']}/spr-compare", headers=fin, timeout=30))["data"]
    assert cmp["state"] == "cocok" and cmp["document"]["id"] == doc2["id"] and cmp["older_documents"] == 1
    requests.post(f"{BASE}/documents/{doc2['id']}/finalize", headers=sa, timeout=30)
    r = requests.post(f"{BASE}/documents/{doc2['id']}/sign", headers=sa,
                      json={"role": "buyer", "name": "Uji"}, timeout=30)
    assert r.status_code == 200, r.text


def test_addendum_auto_after_signed_spr(ctx):
    """SPR sudah ditandatangani → skema diganti → adendum otomatis (draft) dengan tabel selisih."""
    sa, fin, deal, cid = ctx["sa"], ctx["fin"], ctx["deal"], ctx["cid"]
    finlead = _login("owner@sipro.co.id")
    cmp0 = _j(requests.get(f"{BASE}/contracts/{cid}/spr-compare", headers=sa, timeout=30))["data"]
    assert cmp0["state"] == "cocok" and cmp0["signed"] is True
    sch = _j(requests.post(f"{BASE}/payment-schemes", headers=sa, json={
        "name": f"IT21 adendum {ctx['tanda']}", "kind": "cash_bertahap", "terms": [
            {"label": "DP 50%", "basis": "percent", "value": 50},
            {"label": "Pelunasan", "basis": "remaining", "value": 0}]}, timeout=30))["data"]
    ctx["sch2"] = sch
    r = requests.post(f"{BASE}/payment-schemes/contracts/{cid}", headers=finlead,
                      json={"scheme_id": sch["id"], "reason": "uji adendum otomatis iteration 21"}, timeout=60)
    assert r.status_code == 200, r.text
    docs = _j(requests.get(f"{BASE}/documents", headers=sa, params={"limit": 100}, timeout=30))["data"]
    add = [d for d in docs if d.get("template_code") == "ADENDUM_SPR" and d.get("deal_id") == deal["id"]]
    assert len(add) == 1, "tepat satu adendum lahir"
    a = _j(requests.get(f"{BASE}/documents/{add[0]['id']}", headers=sa, timeout=30))["data"]
    assert a["status"] == "draft" and a["parent_doc_number"] and a["diff_rows"]
    assert "→" in a["content"] and "Skema pembayaran baru" in a["content"]
    assert any(r["key"] == "terms_count" for r in a["diff_rows"])
    # compare (jalur kontrak, Sales) kini memakai adendum sebagai dokumen berlaku → cocok
    cmp = _j(requests.get(f"{BASE}/contracts/{cid}/spr-compare", headers=sa, timeout=30))["data"]
    assert cmp["state"] == "cocok" and cmp["document"]["is_addendum"] is True
    assert cmp["document"]["parent_doc_number"] == a["parent_doc_number"]
    # idempoten: ganti ke skema LAIN lagi → adendum draft yang sama diperbarui, bukan kembar
    sch3 = _j(requests.post(f"{BASE}/payment-schemes", headers=sa, json={
        "name": f"IT21 adendum2 {ctx['tanda']}", "kind": "cash_bertahap", "terms": [
            {"label": "DP 20%", "basis": "percent", "value": 20},
            {"label": "Cicilan", "basis": "percent", "value": 30},
            {"label": "Cicilan 2", "basis": "percent", "value": 30},
            {"label": "Pelunasan", "basis": "remaining", "value": 0}]}, timeout=30))["data"]
    ctx["sch3"] = sch3
    r = requests.post(f"{BASE}/payment-schemes/contracts/{cid}", headers=finlead,
                      json={"scheme_id": sch3["id"], "reason": "uji adendum kedua iteration 21"}, timeout=60)
    assert r.status_code == 200, r.text
    docs = _j(requests.get(f"{BASE}/documents", headers=sa, params={"limit": 100}, timeout=30))["data"]
    add2 = [d for d in docs if d.get("template_code") == "ADENDUM_SPR" and d.get("deal_id") == deal["id"]]
    assert len(add2) == 1 and add2[0]["id"] == add[0]["id"]
    a2 = _j(requests.get(f"{BASE}/documents/{add[0]['id']}", headers=sa, timeout=30))["data"]
    assert len(a2["amounts_snapshot"]["terms"]) == 4, "snapshot adendum mengikuti skema terbaru"
    # PDF adendum bisa dibuka
    pdf = requests.get(f"{BASE}/documents/{add[0]['id']}/pdf", headers=sa, timeout=60)
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"
    # adendum bisa difinalisasi & ditandatangani (angkanya = Finance)
    requests.post(f"{BASE}/documents/{add[0]['id']}/finalize", headers=sa, timeout=30)
    r = requests.post(f"{BASE}/documents/{add[0]['id']}/sign", headers=sa,
                      json={"role": "buyer", "name": "Uji"}, timeout=30)
    assert r.status_code == 200, r.text


def test_addendum_draft_removed_when_numbers_revert(ctx):
    """Skema kembali ke skema SPR/adendum yang ditandatangani → adendum draft baru tidak tersisa."""
    sa, deal, cid = ctx["sa"], ctx["deal"], ctx["cid"]
    finlead = _login("owner@sipro.co.id")
    # ganti ke skema lain → adendum draft #2 lahir (adendum #1 sudah ditandatangani)
    r = requests.post(f"{BASE}/payment-schemes/contracts/{cid}", headers=finlead,
                      json={"scheme_id": ctx["sch2"]["id"], "reason": "uji adendum revert iteration 21"}, timeout=60)
    assert r.status_code == 200, r.text
    docs = _j(requests.get(f"{BASE}/documents", headers=sa, params={"limit": 100}, timeout=30))["data"]
    adds = [d for d in docs if d.get("template_code") == "ADENDUM_SPR" and d.get("deal_id") == deal["id"]]
    assert len(adds) == 2 and sum(1 for d in adds if d["status"] == "draft") == 1
    # kembali ke skema adendum #1 yang ditandatangani → draft #2 dibatalkan otomatis
    r = requests.post(f"{BASE}/payment-schemes/contracts/{cid}", headers=finlead,
                      json={"scheme_id": ctx["sch3"]["id"], "reason": "uji adendum revert kembali"}, timeout=60)
    assert r.status_code == 200, r.text
    docs = _j(requests.get(f"{BASE}/documents", headers=sa, params={"limit": 100}, timeout=30))["data"]
    adds = [d for d in docs if d.get("template_code") == "ADENDUM_SPR" and d.get("deal_id") == deal["id"]]
    assert len(adds) == 1 and adds[0]["status"] == "signed"
    cmp = _j(requests.get(f"{BASE}/contracts/{cid}/spr-compare", headers=sa, timeout=30))["data"]
    assert cmp["state"] == "cocok" and cmp["document"]["is_addendum"] is True


def test_cleanup_scheme(ctx):
    for k in ("sch", "sch2", "sch3"):
        if ctx.get(k):
            ctx["db"].payment_schemes.delete_one({"id": ctx[k]["id"]})
