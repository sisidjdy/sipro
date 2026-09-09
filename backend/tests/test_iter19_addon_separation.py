"""Iter 19: add-on = komponen pembayaran TERPISAH (bukan harga unit, bukan dasar termin/KPR)."""
import os
import time
import pytest
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8001").rstrip("/") + "/api"
PW = "Sipro#2026"
ADDON = 18_500_000


def _login(email):
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": PW}, timeout=15)
    r.raise_for_status()
    j = r.json()
    tok = j.get("access_token") or j.get("token") or (j.get("data") or {}).get("token")
    assert tok, f"No token for {email}: {j}"
    return tok


def _h(t):
    return {"Authorization": f"Bearer {t}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def tokens():
    return {r: _login(f"{r}@sipro.co.id") for r in ("manager", "finance", "owner")}


@pytest.fixture(scope="module")
def ctx(tokens):
    tm = tokens["manager"]
    opts = requests.get(f"{BASE}/quotations/options", headers=_h(tm)).json()["data"]
    avail = [u for u in opts["units"] if u.get("price") == 850_000_000]
    assert len(avail) >= 2, "need >=2 available 850jt units"
    promos = requests.get(f"{BASE}/pricing/promos", headers=_h(tm)).json()
    promos = promos.get("data", promos)
    pid = next(p["id"] for p in promos if p["code"] == "PROMO-ALLIN27")
    schemes = requests.get(f"{BASE}/allin-schemes", headers=_h(tm)).json()
    schemes = schemes.get("data", schemes)
    exclude_id = next(s["id"] for s in schemes if s.get("code") == "EXCLUDE")
    kpr_id = next(s["id"] for s in opts["schemes"] if "KPR" in s["name"] and "DP 20" in s["name"])
    leads = requests.get(f"{BASE}/leads?limit=100", headers=_h(tm)).json()["data"]
    free_leads = [l for l in leads if not l.get("unit_id") and l.get("stage") not in ("booking", "won")]
    assert len(free_leads) >= 1
    return {"units": avail, "promo_id": pid, "allin_id": exclude_id, "scheme_id": kpr_id, "leads": free_leads}


def _sim_payload(unit_id, ctx):
    return {"unit_id": unit_id, "addons": [{"code": "ADD-DAPUR", "qty": 1}], "scheme_id": ctx["scheme_id"],
            "promo_id": ctx["promo_id"], "allin_scheme_id": ctx["allin_id"], "booking_fee": 5_000_000}


class TestSimulate:
    def test_addon_separated(self, tokens, ctx):
        unit = ctx["units"][0]
        r = requests.post(f"{BASE}/quotations/simulate", headers=_h(tokens["manager"]), json=_sim_payload(unit["id"], ctx))
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        assert d["gross_price"] == d["base_price"] == 850_000_000
        assert d["net_price"] == d["base_price"]
        assert d["addon_total"] == ADDON and d["addon_net_total"] == ADDON
        assert d["terms_total"] == d["net_price"]
        bphtb = next(c for c in d["costs"]["components"] if c["code"] == "BPHTB")
        assert bphtb["discount"] == 27_000_000 and bphtb["amount"] == 11_500_000
        buyer_costs = sum(c["amount"] for c in d["costs"]["components"] if c.get("treatment") != "developer_borne")
        assert d["buyer_total"] == d["net_price"] + ADDON + buyer_costs == 887_500_000
        pb = d["payment_breakdown"]
        assert [x["code"] for x in pb["rows"]] == [
            "UNIT_PRICE", "NET_PRICE", "ADDON:ADD-DAPUR", "ADDON_TOTAL", "COST:BPHTB", "COSTDISC:BPHTB",
            "COST:NOTARY_FEE", "COST_TOTAL", "TOTAL", "BOOKING_FEE", "AFTER_BOOKING_FEE"]
        assert pb["kpr_base"] == d["net_price"]
        assert next(x for x in pb["rows"] if x["code"] == "COSTDISC:BPHTB")["amount"] == -27_000_000

    def test_regression_plain(self, tokens, ctx):
        r = requests.post(f"{BASE}/quotations/simulate", headers=_h(tokens["manager"]),
                          json={"unit_id": ctx["units"][0]["id"], "scheme_id": ctx["scheme_id"]})
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        assert d["payment_breakdown"]["has_costs"] is False
        assert d["addon_total"] == 0 and d["buyer_total"] == d["net_price"]
        s = requests.get(f"{BASE}/settings/effective?keys=addon.due_days", headers=_h(tokens["manager"])).json()
        assert s["data"]["addon.due_days"] == 30


class TestFullFlow:
    @pytest.fixture(scope="class")
    def deal(self, tokens, ctx):
        tm, tf = tokens["manager"], tokens["finance"]
        unit, lead = ctx["units"][0], ctx["leads"][0]
        payload = _sim_payload(unit["id"], ctx)
        payload.update({"lead_id": lead["id"], "limit_override_reason": "uji perhitungan booking all-in"})
        r = requests.post(f"{BASE}/deals/reserve", headers=_h(tm), json=payload)
        assert r.status_code == 200, r.text
        deal = r.json()["data"]
        assert deal["price"] == 850_000_000
        assert deal["pricing"]["addon_net_total"] == ADDON
        assert deal["pricing"]["buyer_total"] == 887_500_000
        did = deal["id"]
        rp = requests.post(f"{BASE}/booking-fee/deals/{did}/pay", headers=_h(tf), json={"amount": 5_000_000, "method": "transfer"})
        assert rp.status_code == 200, rp.text
        rb = requests.post(f"{BASE}/deals/{did}/book", headers=_h(tm), json={})
        assert rb.status_code == 200, rb.text
        time.sleep(3)
        yield {"id": did, "unit": unit}
        requests.delete(f"{BASE}/deals/{did}?reason=cleanup%20test%20teardown%20iter19", headers=_h(tokens["owner"]))

    def test_ar_detail(self, tokens, deal):
        j = requests.get(f"{BASE}/finance/ar/{deal['id']}", headers=_h(tokens["finance"])).json()
        d = j["data"]
        assert d["price"] == 850_000_000 and d["unit_total"] == 850_000_000
        assert d["addon_total"] == ADDON and d["total"] == 850_000_000 + ADDON
        unit_items = [i for i in d["items"] if not i.get("kpr_excluded")]
        addon_items = [i for i in d["items"] if i.get("kpr_excluded")]
        assert len(unit_items) == 4 and len(addon_items) == 1
        assert addon_items[0]["label"] == "Add-on · Kitchen set" and addon_items[0]["basis"] == "addon"
        assert sum(i["amount"] for i in unit_items) == 850_000_000
        b = d["breakdown"]
        assert b["kpr_base"] == 850_000_000
        assert b["buyer_total"] == 850_000_000 + ADDON + b["cost_total"] == 887_500_000
        ci = j["cost_invoices"]
        assert len(ci) == 1 and ci[0]["number"].startswith("INB/")
        bp = next(it for it in ci[0]["items"] if it["code"] == "BPHTB")
        assert (bp["gross"], bp["discount"], bp["amount"]) == (38_500_000, 27_000_000, 11_500_000)
        assert next(it for it in ci[0]["items"] if it["code"] == "NOTARY_FEE")["amount"] == 7_500_000

    def test_ar_list(self, tokens, deal):
        rows = requests.get(f"{BASE}/finance/ar?limit=100", headers=_h(tokens["finance"])).json()["data"]
        row = next(x for x in rows if x.get("deal_id") == deal["id"])
        assert row["unit_total"] == 850_000_000 and row["addon_total"] == ADDON
        assert row["cost_total"] == 19_000_000 and row["buyer_total"] == 887_500_000

    def test_contract(self, tokens, deal):
        r = requests.post(f"{BASE}/deals/{deal['id']}/convert", headers=_h(tokens["manager"]), json={})
        assert r.status_code == 200, r.text
        time.sleep(1)
        c = requests.get(f"{BASE}/contracts/by-deal/{deal['id']}", headers=_h(tokens["finance"])).json()["data"]
        amt = {x["code"]: x["amount"] for x in c["breakdown"]["rows"]}
        assert amt["UNIT_PRICE"] == 850_000_000 and amt["ADDON_SPEC"] == ADDON
        assert amt["BPHTB"] == 11_500_000 and amt["NOTARY_FEE"] == 7_500_000 and amt["COST_DISCOUNT"] == 27_000_000
        assert c["breakdown"]["total_bill"] == 887_500_000

    def test_force_delete(self, tokens, deal):
        rd = requests.delete(f"{BASE}/deals/{deal['id']}?reason=uji%20hapus%20paksa%20deal%20lengkap", headers=_h(tokens["owner"]))
        assert rd.status_code == 200, rd.text
        units = requests.get(f"{BASE}/units?limit=200", headers=_h(tokens["manager"])).json()["data"]
        assert next(u for u in units if u["id"] == deal["unit"]["id"])["status"] == "available"
        assert requests.get(f"{BASE}/finance/ar/{deal['id']}", headers=_h(tokens["finance"])).status_code == 404
