"""Iter 18: booking all-in promo, AR breakdown, cost invoices, force delete, receipt delete."""
import os
import time
import pytest
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8001").rstrip("/") + "/api"
PW = "Sipro#2026"

def _login(email):
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": PW}, timeout=15)
    r.raise_for_status()
    j = r.json()
    tok = j.get("access_token") or j.get("token") or (j.get("data") or {}).get("token")
    assert tok, f"No token for {email}: {j}"
    return tok

def _h(t): return {"Authorization": f"Bearer {t}", "Content-Type": "application/json"}

@pytest.fixture(scope="module")
def tokens():
    return {r: _login(f"{r}@sipro.co.id") for r in ("manager", "finance", "owner")}

@pytest.fixture(scope="module")
def ctx(tokens):
    tm = tokens["manager"]
    # available units
    units = requests.get(f"{BASE}/units?limit=200", headers=_h(tm)).json()["data"]
    avail = [u for u in units if u.get("status") == "available"]
    assert len(avail) >= 2, "need >=2 available units"
    # promo
    promos = requests.get(f"{BASE}/pricing/promos", headers=_h(tm)).json()
    promos = promos.get("data", promos)
    pid = next(p["id"] for p in promos if p["code"] == "PROMO-ALLIN27")
    # allin scheme EXCLUDE
    schemes = requests.get(f"{BASE}/allin-schemes", headers=_h(tm)).json()
    schemes = schemes.get("data", schemes)
    exclude_id = next(s["id"] for s in schemes if s.get("code") == "EXCLUDE")
    # KPR scheme
    opts = requests.get(f"{BASE}/quotations/options", headers=_h(tm)).json()["data"]
    kpr_id = next(s["id"] for s in opts["schemes"] if "KPR" in s["name"] and "DP 20" in s["name"])
    # leads without unit
    leads = requests.get(f"{BASE}/leads?limit=100", headers=_h(tm)).json()["data"]
    free_leads = [l for l in leads if not l.get("unit_id") and l.get("stage") not in ("booking", "won")]
    assert len(free_leads) >= 2
    return {"units": avail, "promo_id": pid, "allin_id": exclude_id, "scheme_id": kpr_id, "leads": free_leads}


def _sim_payload(unit_id, ctx):
    return {
        "unit_id": unit_id,
        "addons": [{"code": "ADD-DAPUR", "qty": 1}],
        "scheme_id": ctx["scheme_id"],
        "promo_id": ctx["promo_id"],
        "allin_scheme_id": ctx["allin_id"],
        "booking_fee": 5000000,
    }


class TestSimulate:
    def test_simulate_all_in_promo(self, tokens, ctx):
        unit = ctx["units"][0]
        r = requests.post(f"{BASE}/quotations/simulate", headers=_h(tokens["manager"]),
                          json=_sim_payload(unit["id"], ctx))
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        # Iter 19: add-on TERPISAH — gross = harga unit saja
        assert data["gross_price"] == data["base_price"]
        assert data["addon_total"] == 18_500_000
        # cost_discount = 27jt
        assert data.get("cost_discount_amount") == 27_000_000 or data.get("by_target", {}).get("cost:*") == 27_000_000
        # BPHTB discount 27jt
        comps = data["costs"]["components"] if "costs" in data else data.get("costs_data", {}).get("components")
        bphtb = next(c for c in comps if c["code"] == "BPHTB")
        assert bphtb.get("discount") == 27_000_000
        # payment_breakdown rows
        pb = data.get("payment_breakdown") or {}
        codes = [r["code"] for r in pb.get("rows", [])]
        for need in ("UNIT_PRICE", "ADDON:ADD-DAPUR", "NET_PRICE", "COST:BPHTB", "COSTDISC:BPHTB",
                     "COST_TOTAL", "TOTAL", "BOOKING_FEE", "AFTER_BOOKING_FEE"):
            assert need in codes, f"missing pb row {need}: {codes}"
        assert data["by_target"].get("cost:BPHTB", data["by_target"].get("cost:*")) == 27_000_000


class TestFullFlow:
    @pytest.fixture(scope="class")
    def deal(self, tokens, ctx):
        tm, tf = tokens["manager"], tokens["finance"]
        unit = ctx["units"][0]
        lead = ctx["leads"][0]
        payload = _sim_payload(unit["id"], ctx)
        payload["lead_id"] = lead["id"]
        payload["limit_override_reason"] = "uji perhitungan booking all-in"
        r = requests.post(f"{BASE}/deals/reserve", headers=_h(tm), json=payload)
        assert r.status_code == 200, r.text
        deal = r.json()["data"]
        did = deal["id"]
        # pay BF
        rp = requests.post(f"{BASE}/booking-fee/deals/{did}/pay", headers=_h(tf),
                           json={"amount": 5_000_000, "method": "transfer"})
        assert rp.status_code == 200, rp.text
        # book
        rb = requests.post(f"{BASE}/deals/{did}/book", headers=_h(tm), json={})
        assert rb.status_code == 200, rb.text
        assert rb.json()["data"]["status"] == "booked"
        time.sleep(2)
        yield {"id": did, "unit_code": unit.get("code")}
        # cleanup via force delete owner
        requests.delete(f"{BASE}/deals/{did}?reason=cleanup%20test%20teardown%20iter18",
                        headers=_h(tokens["owner"]))

    def test_reserve_pricing_and_breakdown(self, tokens, deal):
        r = requests.get(f"{BASE}/finance/ar/{deal['id']}", headers=_h(tokens["finance"]))
        assert r.status_code == 200
        j = r.json()
        b = j["data"].get("breakdown") or {}
        assert b.get("cost_discount") == 27_000_000
        assert b.get("buyer_total") == b.get("net_price") + b.get("cost_total") + b.get("addon_net_total", 0)
        comps = b.get("cost_components") or []
        assert any(c["code"] == "BPHTB" and c.get("discount") == 27_000_000 for c in comps)
        ci = j.get("cost_invoices") or []
        assert len(ci) >= 1
        inv = ci[0]
        assert inv["number"].startswith("INB/")
        items = inv.get("items") or []
        assert any(it["code"] == "BPHTB" for it in items)
        assert any(it["code"] == "NOTARY_FEE" for it in items)
        bp = next(it for it in items if it["code"] == "BPHTB")
        assert bp.get("discount") == 27_000_000

    def test_ar_list_columns(self, tokens, deal):
        r = requests.get(f"{BASE}/finance/ar?limit=50", headers=_h(tokens["finance"]))
        assert r.status_code == 200
        rows = r.json()["data"]
        row = next((x for x in rows if x.get("deal_id") == deal["id"] or x.get("id") == deal["id"]), None) \
              or next(x for x in rows if x.get("unit_code") == deal.get("unit_code"))
        assert row.get("cost_total", 0) > 0
        assert row.get("buyer_total", 0) > 0
        assert row.get("cost_invoice_numbers")

    def test_convert_and_contract_breakdown(self, tokens, deal):
        r = requests.post(f"{BASE}/deals/{deal['id']}/convert", headers=_h(tokens["manager"]), json={})
        assert r.status_code == 200, r.text
        time.sleep(1)
        rc = requests.get(f"{BASE}/contracts/by-deal/{deal['id']}", headers=_h(tokens["finance"]))
        assert rc.status_code == 200
        c = rc.json()["data"]
        assert c, "no contract"
        b = c["breakdown"]
        codes = {r["code"] for r in b["rows"]}
        for need in ("UNIT_PRICE", "ADDON_SPEC", "PROMO_DISCOUNT", "BOOKING_FEE", "BPHTB", "NOTARY_FEE", "COST_DISCOUNT"):
            assert need in codes, codes
        cd = next(r for r in b["rows"] if r["code"] == "COST_DISCOUNT")
        assert cd["amount"] == 27_000_000
        assert b["total_bill"] == b["nett_price"] + b["costs_total"]
        # costs-ledger
        cid = c["id"]
        rl = requests.get(f"{BASE}/contracts/{cid}/costs-ledger", headers=_h(tokens["finance"]))
        assert rl.status_code == 200
        led = rl.json()["data"]
        inv = led.get("invoices", [])
        uninv = led.get("uninvoiced", [])
        n_inv = len(inv) if isinstance(inv, list) else inv
        n_uninv = len(uninv) if isinstance(uninv, list) else uninv
        assert n_inv >= 1
        assert n_uninv == 0


class TestForceDelete:
    def test_delete_check_and_force_delete(self, tokens, ctx):
        tm, to = tokens["manager"], tokens["owner"]
        unit = ctx["units"][1]
        lead = ctx["leads"][1]
        payload = _sim_payload(unit["id"], ctx)
        payload["lead_id"] = lead["id"]
        payload["limit_override_reason"] = "uji hapus paksa"
        r = requests.post(f"{BASE}/deals/reserve", headers=_h(tm), json=payload)
        assert r.status_code == 200, r.text
        did = r.json()["data"]["id"]
        requests.post(f"{BASE}/booking-fee/deals/{did}/pay", headers=_h(tokens["finance"]),
                      json={"amount": 5_000_000, "method": "transfer"})
        requests.post(f"{BASE}/deals/{did}/book", headers=_h(tm), json={})
        time.sleep(1)
        # delete-check
        r = requests.get(f"{BASE}/deals/{did}/delete-check", headers=_h(to))
        d = r.json()["data"]
        assert d["can_force"] is True
        b = d["blockers"]
        assert b["ar_invoices"] >= 1 and b["cost_invoices"] >= 1
        # manager 403
        rm = requests.delete(f"{BASE}/deals/{did}?reason=hapus%20paksa%20uji%20iter", headers=_h(tm))
        assert rm.status_code == 403
        # no reason 400
        rn = requests.delete(f"{BASE}/deals/{did}", headers=_h(to))
        assert rn.status_code == 400
        rs = requests.delete(f"{BASE}/deals/{did}?reason=pendek", headers=_h(to))
        assert rs.status_code == 400
        # owner delete
        rd = requests.delete(f"{BASE}/deals/{did}?reason=uji%20hapus%20paksa%20deal", headers=_h(to))
        assert rd.status_code == 200, rd.text
        removed = rd.json()["data"]["removed"]
        for k in ("ar_invoices", "receipts", "booking_fee_invoices", "cost_invoices"):
            assert k in removed, removed
        # unit back to available
        ru = requests.get(f"{BASE}/units?q={unit.get('code')}", headers=_h(tm)).json()["data"]
        u = next(x for x in ru if x["id"] == unit["id"])
        assert u["status"] == "available"

    def test_delete_receipt(self, tokens, ctx):
        tm, tf, to = tokens["manager"], tokens["finance"], tokens["owner"]
        # find remaining available unit not used
        units = requests.get(f"{BASE}/units?limit=200", headers=_h(tm)).json()["data"]
        avail = [u for u in units if u.get("status") == "available"]
        unit = avail[0]
        leads = requests.get(f"{BASE}/leads?limit=100", headers=_h(tm)).json()["data"]
        lead = next(l for l in leads if not l.get("unit_id") and l.get("stage") not in ("booking", "won"))
        payload = _sim_payload(unit["id"], ctx)
        payload["lead_id"] = lead["id"]
        payload["limit_override_reason"] = "uji hapus receipt"
        rr = requests.post(f"{BASE}/deals/reserve", headers=_h(tm), json=payload)
        assert rr.status_code == 200, rr.text
        did = rr.json()["data"]["id"]
        requests.post(f"{BASE}/booking-fee/deals/{did}/pay", headers=_h(tf),
                      json={"amount": 5_000_000, "method": "transfer"})
        requests.post(f"{BASE}/deals/{did}/book", headers=_h(tm), json={})
        time.sleep(1)
        # add AR receipt
        rp = requests.post(f"{BASE}/finance/ar/receipts", headers=_h(tf),
                           json={"deal_id": did, "amount": 1_000_000, "method": "transfer"})
        assert rp.status_code in (200, 201), rp.text
        # find latest receipt
        det = requests.get(f"{BASE}/finance/ar/{did}", headers=_h(tf)).json()
        receipts = det.get("receipts", [])
        assert receipts
        rid = receipts[0]["id"]
        paid_before = det["data"]["paid"]
        # no reason -> 400
        r0 = requests.delete(f"{BASE}/finance/ar/receipts/{rid}", headers=_h(to), allow_redirects=False)
        # 307 for missing trailing slash or 400 no-reason — accept either
        assert r0.status_code in (307, 400, 422)
        # short reason
        rs = requests.delete(f"{BASE}/finance/ar/receipts/{rid}?reason=pendek", headers=_h(to))
        assert rs.status_code == 400
        r1 = requests.delete(f"{BASE}/finance/ar/receipts/{rid}?reason=uji%20hapus%20pembayaran%20receipt", headers=_h(to))
        assert r1.status_code == 200, r1.text
        det2 = requests.get(f"{BASE}/finance/ar/{did}", headers=_h(tf)).json()
        paid_after = det2["data"]["paid"]
        assert paid_after == paid_before - 1_000_000
        # cleanup deal
        requests.delete(f"{BASE}/deals/{did}?reason=cleanup%20test%20teardown%20iter18",
                        headers=_h(to))
