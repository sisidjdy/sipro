"""Iter19 extra: simulate breakdown + regression checks."""
import os, requests, pytest

BASE = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/") + "/api"
PWD = "Sipro#2026"


def _login(email):
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": PWD}, timeout=30)
    assert r.status_code == 200, r.text
    j = r.json()
    tok = j.get("token") or j.get("access_token") or (j.get("data") or {}).get("token") or (j.get("data") or {}).get("access_token")
    assert tok
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="module")
def mgr():
    return _login("manager@sipro.co.id")


def _get(headers, path):
    r = requests.get(f"{BASE}{path}", headers=headers, timeout=30)
    assert r.status_code == 200, f"{path} -> {r.status_code} {r.text[:200]}"
    return r.json().get("data", r.json())


def test_simulate_full_breakdown(mgr):
    opts = _get(mgr, "/quotations/options")
    units = opts.get("units") or []
    unit = next((u for u in units if (u.get("base_price") or u.get("price")) == 850_000_000), None)
    assert unit, f"No available 850jt unit; got prices={[u.get('price') for u in units]}"

    schemes = opts.get("schemes") or opts.get("payment_schemes") or []
    scheme = next((s for s in schemes if "Standar KPR" in (s.get("name") or "") and "20%" in (s.get("name") or "")), None)
    assert scheme, f"scheme not found: {[s.get('name') for s in schemes]}"

    promos = _get(mgr, "/pricing/promos")
    if isinstance(promos, dict):
        promos = promos.get("items") or promos.get("promos") or []
    promo = next((p for p in promos if p.get("code") == "PROMO-ALLIN27"), None)
    assert promo, "PROMO-ALLIN27 missing"

    allin = _get(mgr, "/allin-schemes")
    if isinstance(allin, dict):
        allin = allin.get("items") or allin.get("schemes") or []
    exclude = next((a for a in allin if (a.get("code") or "").upper() == "EXCLUDE"), None)
    assert exclude, "EXCLUDE allin missing"

    payload = {
        "unit_id": unit["id"],
        "addons": [{"code": "ADD-DAPUR", "qty": 1}],
        "scheme_id": scheme["id"],
        "promo_id": promo["id"],
        "allin_scheme_id": exclude["id"],
        "booking_fee": 5_000_000,
    }
    r = requests.post(f"{BASE}/quotations/simulate", json=payload, headers=mgr, timeout=30)
    assert r.status_code == 200, r.text
    d = r.json().get("data", r.json())

    assert d["gross_price"] == 850_000_000
    assert d["base_price"] == 850_000_000
    assert d["net_price"] == 850_000_000
    assert d["addon_total"] == 18_500_000
    assert d["addon_net_total"] == 18_500_000
    assert d["terms_total"] == 850_000_000
    assert d["buyer_total"] == 887_500_000

    comps = {c["code"]: c for c in (d.get("costs") or {}).get("components", [])}
    assert comps["BPHTB"]["amount"] == 11_500_000
    assert comps["BPHTB"]["discount"] == 27_000_000

    pb = d.get("payment_breakdown") or {}
    assert pb.get("kpr_base") == 850_000_000

    codes = [row.get("code") for row in pb.get("rows", [])]
    expected = ["UNIT_PRICE","NET_PRICE","ADDON:ADD-DAPUR","ADDON_TOTAL","COST:BPHTB","COSTDISC:BPHTB","COST:NOTARY_FEE","COST_TOTAL","TOTAL","BOOKING_FEE","AFTER_BOOKING_FEE"]
    assert codes == expected, f"rows order mismatch: {codes}"


def test_addon_due_days_setting(mgr):
    r = requests.get(f"{BASE}/settings/effective", params={"keys": "addon.due_days"}, headers=mgr, timeout=30)
    assert r.status_code == 200
    j = r.json().get("data", r.json())
    assert int(j.get("addon.due_days")) == 30


def test_simulate_minimal_no_addon_no_allin(mgr):
    opts = _get(mgr, "/quotations/options")
    units = opts.get("units") or []
    unit = units[0] if units else None
    assert unit
    schemes = opts.get("schemes") or opts.get("payment_schemes") or []
    scheme = schemes[0]
    r = requests.post(f"{BASE}/quotations/simulate", json={"unit_id": unit["id"], "scheme_id": scheme["id"]}, headers=mgr, timeout=30)
    assert r.status_code == 200, r.text
    d = r.json().get("data", r.json())
    pb = d.get("payment_breakdown") or {}
    assert pb.get("has_costs") is False
