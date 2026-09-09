"""Audit Tahap 6 (CFG-01, FIN-01/02/03, PRJ-01/02, BI-01/02) — angka pembukuan & BI berkata satu hal.

Unit (tanpa server): period_of satu definisi WIB, win rate satu definisi, sampel minimum sumber.
Server hidup: kartu Beranda = drill-down, AR summary = drill-down, LED-13 tidak dimenangkan sampel kecil.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from conftest import BASE_URL, _login, _sess  # noqa: E402
from core_utils import period_of  # noqa: E402
from metrics import leads as ml  # noqa: E402
from metrics.base import pct  # noqa: E402


# ------------------------------------------------------------------ CFG-01
@pytest.mark.parametrize("value,expected", [
    ("2026-08-31", "2026-08"),
    ("2026-08-31T18:00:00+00:00", "2026-09"),      # 01:00 WIB tanggal 1 September
    ("2026-08-31T16:59:59Z", "2026-08"),           # 23:59 WIB masih Agustus
    ("2026-08-31T23:00:00", "2026-09"),            # naif = UTC → WIB
    ("", None), (None, None), ("ngawur", None), ("31/08/2026", None),
])
def test_cfg01_period_of_single_definition_wib(value, expected):
    assert period_of(value) == expected


def test_cfg01_no_second_period_of():
    import re
    be = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    owners = []
    for root, _, files in os.walk(be):
        if "tests" in root or "node_modules" in root:
            continue
        for f in files:
            if f.endswith(".py"):
                src = open(os.path.join(root, f), encoding="utf-8", errors="ignore").read()
                if re.search(r"^def period_of\(", src, re.M):
                    owners.append(f)
    assert owners == ["core_utils.py"], owners


# ------------------------------------------------------------------ BI-01 / BI-02
def test_bi02_win_rate_same_definition():
    won, lost, active = 3, 1, 10
    assert pct(won, won + lost) == 75.0
    assert pct(won, won + lost + active) != pct(won, won + lost)
    src = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "metrics", "leads.py"), encoding="utf-8").read()
    assert 'row["win_pct"] = pct(row["won"], row["won"] + row["lost"])' in src
    assert 'row["conversion_pct"] = pct(row["won"], row["value"])' in src


def test_bi01_min_source_sample_is_enforced():
    assert ml.MIN_SOURCE_SAMPLE >= 3
    src = open(ml.__file__, encoding="utf-8").read()
    assert 'row["eligible"] = row["value"] >= MIN_SOURCE_SAMPLE' in src
    assert 'r["eligible"]' in src and "default=None" in src


# ------------------------------------------------------------------ server hidup
@pytest.fixture(scope="module")
def su():
    return _sess(_login("superadmin@sipro.co.id"))


@pytest.fixture(scope="module")
def fin():
    return _sess(_login("finance@sipro.co.id"))


def _api(s, path, **params):
    r = s.get(f"{BASE_URL}/api{path}", params=params, timeout=60)
    assert r.status_code == 200, (path, r.status_code, r.text[:200])
    return r.json()["data"]


def test_fin02_home_cards_equal_drilldown(su, fin):
    for s in (su, fin):
        kpis = _api(s, "/work/home")["kpis"]
        assert kpis
        for k in kpis:
            assert k.get("drill_key"), k
            d = _api(s, f"/drilldown/{k['drill_key']}", **(k.get("drill_params") or {}))
            rincian = (d.get("total") or 0) if k.get("format") == "idr" else d.get("count", 0)
            assert int(round(float(k["value"]))) == int(round(float(rincian))), (k["label"], k["value"], rincian)


def test_fin01_ar_summary_equals_drilldown(fin):
    s = _api(fin, "/finance/summary")
    for key in ("ar_outstanding", "ar_overdue", "ap_outstanding"):
        d = _api(fin, f"/finance/drilldown/{key}")
        assert int(d["total"]) == int(s[key] or 0), (key, s[key], d["total"])
    assert sum(int(v) for v in s["ar_buckets"].values()) == int(s["ar_outstanding"])
    for bk, val in s["ar_buckets"].items():
        d = _api(fin, "/finance/drilldown/ar_bucket", bucket=bk)
        assert int(d["total"]) == int(val), (bk, val, d["total"])


def test_fin03_no_fake_dso(fin):
    s = _api(fin, "/finance/summary")
    assert "ar_outstanding_pct" in s and "ar_total_value" in s
    assert not any("dso" in k.lower() for k in s.keys()), list(s.keys())
    if s["ar_total_value"]:
        assert s["ar_outstanding_pct"] == round(s["ar_outstanding"] / s["ar_total_value"] * 100, 1)


def test_bi01_best_source_never_small_sample(su):
    d = _api(su, "/analytics/metric/LED-13", period="all")
    rows = d.get("breakdown") or []
    best = (d.get("inputs") or {}).get("sumber_terbaik")
    assert (d.get("inputs") or {}).get("sampel_minimum") == ml.MIN_SOURCE_SAMPLE
    for r in rows:
        assert "eligible" in r and "win_pct" in r and "conversion_pct" in r
        if not r["eligible"]:
            assert r["label"] != best, (r, best)


def test_prj01_units_progress_denominator_all_units(su):
    projects = _api(su, "/projects")
    rows = projects if isinstance(projects, list) else projects.get("rows") or projects.get("items") or []
    assert rows
    for p in rows:
        if "units_total" not in p:
            continue
        assert p["units_total"] >= p.get("units_scheduled", 0)
        assert 0 <= (p.get("units_progress") or 0) <= 100
        if p["units_total"] and p.get("units_scheduled", 0) < p["units_total"]:
            # unit yang belum dijadwalkan = 0%, jadi rekap tidak boleh 100 selama masih ada yang belum dijadwalkan
            assert (p.get("units_progress") or 0) < 100, p
