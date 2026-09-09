"""Fase 88 — phone +62, lead scoring, promo bersasaran komponen, SPR per jenis, kebijakan pelunasan."""
import os
import re
import uuid

import pytest
import requests
from dotenv import dotenv_values

fe = dotenv_values("/app/frontend/.env")
BASE = (os.environ.get("REACT_APP_BACKEND_URL") or fe.get("REACT_APP_BACKEND_URL")).rstrip("/")
API = f"{BASE}/api"
PASSWORD = "Sipro#2026"


@pytest.fixture(scope="session")
def s():
    ses = requests.Session()
    r = ses.post(f"{API}/auth/login", json={"email": "superadmin@sipro.co.id",
                                            "password": PASSWORD}, timeout=60)
    if r.status_code != 200:
        pytest.fail(f"login gagal {r.status_code}: {r.text[:300]}")
    tok = r.json().get("data", {}).get("token") or r.json().get("token")
    if tok:
        ses.headers.update({"Authorization": f"Bearer {tok}"})
    yield ses
    # Reservasi uji (lead TEST_P88 *) dibatalkan lewat API agar unit demo kembali tersedia —
    # tanpa ini setiap run menghabiskan 2 unit demo dan menyesatkan kartu Master Proyek.
    try:
        deals = ses.get(f"{API}/deals", params={"status": "reserved", "limit": 500}, timeout=60).json().get("data") or []
        for d in deals:
            if str(d.get("lead_name") or d.get("customer_name") or "").startswith("TEST_P88"):
                ses.post(f"{API}/deals/{d['id']}/cancel", json={"note": "cleanup fixture p88"}, timeout=60)
    except Exception:  # noqa: BLE001
        pass


def _rows(payload):
    d = payload.get("data", payload)
    if isinstance(d, dict):
        return d.get("rows") or d.get("items") or []
    return d


# ------------------------------------------------- 88B: skor lead
@pytest.fixture(scope="session")
def a_lead(s):
    r = s.get(f"{API}/leads", params={"limit": 5}, timeout=60)
    assert r.status_code == 200, r.text[:300]
    rows = _rows(r.json())
    assert rows, "tidak ada lead untuk diuji"
    return rows[0]


def test_lead_score_detail(s, a_lead):
    r = s.get(f"{API}/leads/{a_lead['id']}/score", timeout=60)
    assert r.status_code == 200, r.text[:300]
    d = r.json()["data"]
    assert isinstance(d["score"], int) and 0 <= d["score"] <= 100, d.get("score")
    assert str(d["score_band"]).lower() in ("hot", "warm", "cold"), d.get("score_band")
    br = d["score_breakdown"]
    assert isinstance(br, list) and br
    for row in br:
        assert {"key", "label", "points"} <= set(row), row
    assert isinstance(d.get("score_bands"), dict), d.get("score_bands")


def test_lead_rescore(s, a_lead):
    r = s.post(f"{API}/leads/{a_lead['id']}/rescore", timeout=60)
    assert r.status_code == 200, r.text[:300]
    body = r.json()
    assert "message" in body and "Skor" in body["message"]
    score = body["data"]["score"]
    g = s.get(f"{API}/leads/{a_lead['id']}", timeout=60)
    assert g.status_code == 200
    lead = g.json().get("data", g.json())
    lead = lead.get("lead", lead) if isinstance(lead, dict) else lead
    assert lead.get("score") == score, f"stored={lead.get('score')} vs {score}"


# ------------------------------------------------- 88 settings keys
@pytest.mark.parametrize("key", ["lead.score.events", "lead.score.bands",
                                 "handover.settlement_policy",
                                 "handover.settlement_min_paid_pct"])
def test_settings_keys_exist(s, key):
    r = s.get(f"{API}/settings", timeout=60)
    assert r.status_code == 200, r.text[:300]
    rows = _rows(r.json())
    found = [x for x in rows if x.get("key") == key]
    assert found, f"setting {key} tidak ada di GET /api/settings"
    row = found[0]
    if key == "handover.settlement_policy":
        assert row["value"] in ("wajib_lunas", "minimal_persen", "peringatan")
        assert set(row.get("options") or []) == {"wajib_lunas", "minimal_persen", "peringatan"}
    if key.endswith("events"):
        assert isinstance(row["value"], list), row["value"]
    if key.endswith("bands"):
        assert isinstance(row["value"], dict), row["value"]


# ------------------------------------------------- 88E: kebijakan pelunasan
def _unit_with_outstanding(s):
    """Cari unit yang punya deal & AR outstanding sehingga item pelunasan tidak lunas."""
    r = s.get(f"{API}/deals", params={"limit": 100}, timeout=90)
    if r.status_code != 200:
        return None
    for d in _rows(r.json()):
        uid = d.get("unit_id")
        if not uid:
            continue
        c = s.get(f"{API}/handover/check", params={"unit_id": uid}, timeout=90)
        if c.status_code != 200:
            continue
        items = c.json()["data"].get("items", [])
        hit = [i for i in items if "pelunasan" in str(i.get("code", ""))]
        if hit and hit[0].get("state") == "blocking":
            return uid, hit[0]
    return None


def test_settlement_policy_warning(s):
    found = _unit_with_outstanding(s)
    if not found:
        pytest.skip("tidak ada unit dengan AR outstanding untuk uji kebijakan pelunasan")
    uid, item0 = found
    try:
        p = s.put(f"{API}/settings/handover.settlement_policy",
                  json={"value": "peringatan", "reason": "TEST_p88"}, timeout=60)
        assert p.status_code == 200, p.text[:300]
        c = s.get(f"{API}/handover/check", params={"unit_id": uid}, timeout=90)
        assert c.status_code == 200, c.text[:300]
        items = c.json()["data"]["items"]
        it = [i for i in items if "pelunasan" in str(i.get("code", ""))][0]
        assert it["state"] == "warning", f"state={it['state']} item={it}"
    finally:
        s.put(f"{API}/settings/handover.settlement_policy",
              json={"value": "wajib_lunas", "reason": "TEST_p88 restore"}, timeout=60)
    back = s.get(f"{API}/settings", timeout=60)
    row = [x for x in _rows(back.json()) if x["key"] == "handover.settlement_policy"][0]
    assert row["value"] == "wajib_lunas"


# ------------------------------------------------- 88C: promo bersasaran
@pytest.fixture(scope="session")
def promos(s):
    r = s.get(f"{API}/pricing/promos", timeout=60)
    assert r.status_code == 200, r.text[:300]
    return {p["code"]: p for p in _rows(r.json())}


@pytest.mark.parametrize("code,target,comp", [("PROMO-DP", "dp", None),
                                              ("PROMO-BF", "booking_fee", None),
                                              ("PROMO-BPHTB", "cost", "BPHTB")])
def test_promo_seed_targets(promos, code, target, comp):
    assert code in promos, f"{code} tidak ada di seed promo"
    p = promos[code]
    assert p.get("target") == target, p
    if comp:
        assert p.get("target_component") == comp, p


def test_promo_cost_without_component_rejected(s):
    r = s.post(f"{API}/pricing/promos", json={
        "code": f"TEST_P88_{uuid.uuid4().hex[:6].upper()}", "name": "TEST promo cost",
        "kind": "percent", "value": 10, "target": "cost"}, timeout=60)
    if r.status_code in (200, 201):  # bug: nonaktifkan data uji yang lolos validasi
        s.put(f"{API}/pricing/promos/{r.json()['data']['id']}", json={"active": False}, timeout=60)
    assert r.status_code in (400, 422), f"{r.status_code}: {r.text[:300]}"


def test_promo_put_cost_without_component_rejected(s, promos):
    """PUT target=cost tanpa target_component juga harus ditolak."""
    p = promos["PROMO-DP"]
    r = s.put(f"{API}/pricing/promos/{p['id']}", json={"target": "cost"}, timeout=60)
    if r.status_code == 200:  # kembalikan seed bila lolos
        s.put(f"{API}/pricing/promos/{p['id']}", json={"target": "dp"}, timeout=60)
    assert r.status_code in (400, 422), f"{r.status_code}: {r.text[:300]}"


def test_promo_put_target_dp(s, promos):
    p = promos["PROMO-DP"]
    r = s.put(f"{API}/pricing/promos/{p['id']}",
              json={"target": "dp", "note": p.get("note") or "seed"}, timeout=60)
    assert r.status_code == 200, r.text[:300]
    assert r.json()["data"]["target"] == "dp"


def test_reference_discount_target_group(s):
    r = s.get(f"{API}/reference", timeout=60)
    assert r.status_code == 200, r.text[:300]
    data = r.json().get("data", r.json())
    assert "discount_target" in data, list(data)[:40]
    grp = data["discount_target"]
    opts = grp.get("options") if isinstance(grp, dict) else grp
    codes = [x.get("value") or x.get("code") if isinstance(x, dict) else x for x in opts]
    for c in ("price", "dp", "booking_fee", "cost"):
        assert c in codes, codes


def test_create_promo_target_dp_and_cleanup(s):
    code = f"TEST_P88_{uuid.uuid4().hex[:6].upper()}"
    r = s.post(f"{API}/pricing/promos", json={
        "code": code, "name": "TEST promo dp", "kind": "amount", "value": 1_000_000,
        "target": "dp"}, timeout=60)
    assert r.status_code in (200, 201), r.text[:300]
    rid = r.json()["data"]["id"]
    assert r.json()["data"]["target"] == "dp"
    d = s.put(f"{API}/pricing/promos/{rid}", json={"active": False}, timeout=60)
    assert d.status_code == 200, d.text[:200]


# ------------------------------------------------- 88C: simulate promo DP
@pytest.fixture(scope="session")
def avail_unit(s):
    r = s.get(f"{API}/units", params={"status": "available", "limit": 20}, timeout=90)
    assert r.status_code == 200, r.text[:300]
    rows = _rows(r.json())
    assert rows, "tidak ada unit available"
    return rows[0]


def test_simulate_promo_dp(s, avail_unit, promos):
    opt = s.get(f"{API}/pricing/options", params={"unit_id": avail_unit["id"]}, timeout=60)
    assert opt.status_code == 200, opt.text[:300]
    sc = s.get(f"{API}/quotations/options", timeout=60)
    scheme_id = None
    if sc.status_code == 200:
        data = sc.json().get("data", {})
        schemes = data.get("payment_schemes") or data.get("schemes") or []
        for x in schemes:
            if isinstance(x, dict):
                scheme_id = x.get("id")
                break
    body = {"unit_id": avail_unit["id"], "promo_id": promos["PROMO-DP"]["id"]}
    if scheme_id:
        body["scheme_id"] = scheme_id
    r = s.post(f"{API}/quotations/simulate", json=body, timeout=90)
    assert r.status_code == 200, r.text[:400]
    d = r.json()["data"]
    assert d["discount_amount"] == 5_000_000, d.get("discount_amount")
    assert d.get("by_target", {}).get("dp") == 5_000_000, d.get("by_target")
    terms = d.get("terms") or []
    assert terms, d
    assert terms[0].get("discount") == 5_000_000, terms[0]
    assert sum(t.get("amount", 0) for t in terms) == d["net_price"], \
        (sum(t.get("amount", 0) for t in terms), d["net_price"])


# ------------------------------------------------- 88C: reserve promo BF / BPHTB
def _new_lead(s):
    # nomor unik berdigit (hex bisa memuat huruf → nomor tak sah → dulu jatuh ke nomor tetap yang
    # kemudian ditolak 409 sebagai duplikat lead run sebelumnya)
    r = s.post(f"{API}/leads", json={"name": f"TEST_P88 {uuid.uuid4().hex[:5]}",
                                     "phone": "+62812900" + f"{uuid.uuid4().int % 10000:04d}",
                                     "source": "walk_in"}, timeout=60)
    if r.status_code not in (200, 201):
        r = s.post(f"{API}/leads", json={"name": f"TEST_P88 {uuid.uuid4().hex[:5]}",
                                         "phone": "+62812901" + f"{uuid.uuid4().int % 10000:04d}",
                                         "source": "walk_in"}, timeout=60)
    assert r.status_code in (200, 201), r.text[:400]
    return r.json()["data"]["id"]


def _fresh_unit(s):
    r = s.get(f"{API}/units", params={"status": "available", "limit": 200}, timeout=90)
    rows = _rows(r.json())
    # Unit demo berharga wajar dulu; unit fixture lain (kode UJI*, harga 0) membuat BPHTB = 0
    # sehingga promo tidak punya apa-apa untuk dipotong.
    demo = [u for u in rows if int(u.get("price") or 0) > 0 and not str(u.get("code", "")).upper().startswith("UJI")]
    return demo or rows


def test_reserve_with_promo_bf(s, promos):
    units = _fresh_unit(s)
    assert units, "tidak ada unit available"
    lead_id = _new_lead(s)
    body = {"unit_id": units[0]["id"], "lead_id": lead_id, "booking_fee": 4_000_000,
            "promo_id": promos["PROMO-BF"]["id"]}
    r = s.post(f"{API}/deals/reserve", json=body, timeout=120)
    assert r.status_code in (200, 201), f"{r.status_code}: {r.text[:500]}"
    d = r.json()["data"]
    deal = d.get("deal", d)
    assert deal.get("booking_fee") == 2_000_000, deal.get("booking_fee")
    assert deal.get("discount") == 2_000_000, deal.get("discount")
    pricing = d.get("pricing") or deal.get("pricing") or {}
    assert pricing.get("by_target", {}).get("booking_fee") == 2_000_000, pricing.get("by_target")


def test_reserve_bphtb_without_allin_scheme_400(s, promos):
    units = _fresh_unit(s)
    if len(units) < 2:
        pytest.skip("unit available kurang")
    lead_id = _new_lead(s)
    r = s.post(f"{API}/deals/reserve", json={
        "unit_id": units[-1]["id"], "lead_id": lead_id, "booking_fee": 1_000_000,
        "promo_id": promos["PROMO-BPHTB"]["id"]}, timeout=120)
    assert r.status_code == 400, f"{r.status_code}: {r.text[:400]}"
    detail = r.json().get("detail", "")
    assert re.search(r"BPHTB", detail), detail


def test_reserve_bphtb_with_allin_scheme(s, promos):
    al = s.get(f"{API}/allin-schemes", timeout=60)
    if al.status_code != 200:
        pytest.skip(f"GET /api/allin-schemes -> {al.status_code}")
    target = None
    for sch in _rows(al.json()):
        comps = sch.get("items") or sch.get("components") or []
        for c in comps:
            code = (c.get("component_code") or c.get("code") or "").upper()
            if code == "BPHTB":
                target = sch
                break
        if target:
            break
    if not target:
        pytest.skip("tidak ada skema all-in dengan komponen BPHTB")
    units = _fresh_unit(s)
    if not units:
        pytest.skip("tidak ada unit available")
    lead_id = _new_lead(s)
    r = s.post(f"{API}/deals/reserve", json={
        "unit_id": units[0]["id"], "lead_id": lead_id, "booking_fee": 1_000_000,
        "promo_id": promos["PROMO-BPHTB"]["id"], "allin_scheme_id": target["id"]}, timeout=120)
    assert r.status_code in (200, 201), f"{r.status_code}: {r.text[:500]}"
    d = r.json()["data"]
    comps = ((d.get("costs") or (d.get("deal") or {}).get("costs") or {}).get("components")) or []
    bp = [c for c in comps if (c.get("code") or "").upper() == "BPHTB"]
    assert bp, comps
    assert bp[0].get("amount") == 0, bp[0]
    assert bp[0].get("discount", 0) > 0, bp[0]


# ------------------------------------------------- 88D: template SPR per jenis
def test_spr_templates_distinct(s):
    r = s.get(f"{API}/master/doc-templates", timeout=60)
    assert r.status_code == 200, r.text[:300]
    rows = {t["code"]: t for t in _rows(r.json())}
    expect = {"SPR_CASH": "SPR-CASH", "SPR_CASH_STAGED": "SPR-CASHB", "SPR_KPR": "SPR-KPR"}
    for code, doc_code in expect.items():
        assert code in rows, f"template {code} tidak ada: {sorted(rows)}"
        assert rows[code].get("doc_code") == doc_code, rows[code].get("doc_code")
    contents = {c: (rows[c].get("content") or "") for c in expect}
    for c, txt in contents.items():
        assert txt.strip(), f"{c} konten kosong"
        assert "{{discount_rows}}" in txt or "{discount_rows}" in txt, \
            f"{c} tidak memuat token discount_rows"
    vals = list(contents.values())
    assert len(set(vals)) == 3, "konten template SPR tidak berbeda antar jenis pembayaran"


# ------------------------------------------------- 88A: normalisasi telepon +62
def test_lead_phone_normalized(s):
    name = f"TEST_P88 phone {uuid.uuid4().hex[:5]}"
    local = "08129" + str(uuid.uuid4().int)[:8]
    r = s.post(f"{API}/leads", json={"name": name, "phone": local,
                                     "source": "walk_in"}, timeout=60)
    assert r.status_code in (200, 201), r.text[:400]
    lead = r.json()["data"]
    expect = "+62" + local[1:]
    assert lead.get("phone") == expect, lead.get("phone")
    g = s.get(f"{API}/leads", params={"q": name}, timeout=60)
    assert g.status_code == 200
    rows = _rows(g.json())
    assert any(x.get("phone") == expect for x in rows), rows[:3]
