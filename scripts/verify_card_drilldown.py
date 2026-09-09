#!/usr/bin/env python3
"""verify_card_drilldown.py — GATE 62 (Audit Tahap 7 §2): ANGKA KARTU = JUMLAH BARIS RINCIANNYA.

Pola A audit (aturan hidup di docstring, mati di kode) paling sering lahir di kartu KPI:
kartu dihitung dengan satu query, dialog rinciannya dengan query lain, dan tidak ada yang
membandingkan keduanya (FIN-01: `outstanding` invoice yang basi vs sisa per termin).
Gate ini MEMBANDINGKAN, dengan server hidup:

  A — Beranda (`/work/home`): setiap kartu ber-`drill_key` nilainya SAMA dengan
      `total`/`count` mesin drill-down `/drilldown/{key}` — diuji per PERAN (owner, sales,
      sales_manager, finance, project_manager), karena kartunya berbeda per peran.
  B — Pipeline Lead (`/drilldown/_summary/leads`): kartu adalah PARTISI —
      Aktif + Menang + Daur ulang + Hilang = Total; tiap kartu = count rinciannya.
  C — Keuangan (`/finance/summary`): AR/AP/kewajiban kontrak/titipan/pendapatan diakui
      = `total` `/finance/drilldown/{key}`; tiap ember aging = rincian ember itu.
  D — BI: setiap metrik punya rumus tertulis, dan dua metrik yang memakai NAMA yang sama
      tidak boleh punya rumus berbeda (Pola C untuk angka: BI-02 win rate).
  K — Kode: `work_home` menyinkronkan kartu lewat `_sync_with_drilldown` (FIN-02), dan
      drill-down AR membaca sisa per termin (FIN-01), bukan field invoice yang bisa basi.

Jalankan: python3 scripts/verify_card_drilldown.py
"""
import re
import sys
from collections import defaultdict
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
BE = ROOT / "backend"
API = "http://localhost:8001/api"
PASSWORD = "Sipro#2026"
ROLES = {
    "owner": "owner@sipro.co.id", "sales": "sales@sipro.co.id",
    "sales_manager": "manager@sipro.co.id", "finance": "finance@sipro.co.id",
    "project_manager": "pm@sipro.co.id", "super_admin": "superadmin@sipro.co.id",
}

ok, fails = 0, []


def check(cond, label, detail=None):
    global ok
    if cond:
        ok += 1
        print(f"  OK    {label}")
        return True
    fails.append(label)
    print(f"  GAGAL {label}" + (f" — {detail}" if detail else ""))
    return False


def head(t):
    print(f"\n{t}\n" + "-" * len(t))


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="ignore") if p.exists() else ""


def login(email):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": PASSWORD}, timeout=30)
    body = r.json() if r.status_code == 200 else {}
    tok = body.get("token") or body.get("access_token")
    return {"Authorization": f"Bearer {tok}"} if tok else None


def get(h, path, **params):
    r = requests.get(f"{API}{path}", headers=h, params=params, timeout=60)
    return r.status_code, (r.json().get("data") if r.status_code == 200 else r.text[:160])


def bagian_beranda():
    head("A. Beranda: kartu KPI = mesin drill-down yang sama, per peran")
    for role, email in ROLES.items():
        h = login(email)
        if not check(h is not None, f"A0 masuk sebagai {role}"):
            continue
        sc, home = get(h, "/work/home")
        if not check(sc == 200, f"A1 [{role}] /work/home terbaca", home):
            continue
        kpis = home.get("kpis") or []
        check(bool(kpis) and all(k.get("drill_key") for k in kpis),
              f"A2 [{role}] setiap kartu membawa `drill_key` (angka yang tidak bisa dirinci = angka yang tidak bisa diperiksa)",
              str([k.get("label") for k in kpis if not k.get("drill_key")]))
        for k in kpis:
            if not k.get("drill_key"):
                continue
            sc2, d = get(h, f"/drilldown/{k['drill_key']}", **(k.get("drill_params") or {}))
            if not check(sc2 == 200, f"A3 [{role}] rincian `{k['drill_key']}` untuk kartu '{k['label']}' terbuka", d):
                continue
            rincian = (d.get("total") or 0) if k.get("format") == "idr" else d.get("count", 0)
            check(int(round(float(k.get("value") or 0))) == int(round(float(rincian or 0))),
                  f"A4 [{role}] kartu '{k['label']}' = rinciannya",
                  f"kartu {k.get('value')} vs rincian {rincian}")
            check(bool(k.get("drill")) and k["drill"].startswith("/"),
                  f"A5 [{role}] kartu '{k['label']}' punya tautan daftar terfilter")


def bagian_lead():
    head("B. Pipeline Lead: kartu = partisi, tiap kartu = count rinciannya")
    h = login(ROLES["super_admin"])
    sc, cards = get(h, "/drilldown/_summary/leads")
    if not check(sc == 200 and isinstance(cards, list) and cards, "B1 ringkasan kartu lead terbaca", cards):
        return
    by = {c["key"]: c for c in cards}
    total = by.get("total", {}).get("value")
    bagian = sum(by.get(k, {}).get("value") or 0 for k in ("active", "won", "recycle", "lost"))
    check(total is not None and total == bagian,
          "B2 Aktif + Menang + Daur ulang + Hilang = Total (kartu tidak tumpang tindih, tidak bocor)",
          f"total {total} vs Σ bagian {bagian}")
    for c in cards:
        sc2, d = get(h, "/drilldown/leads", **(c.get("params") or {}))
        check(sc2 == 200 and d.get("count") == c.get("value"),
              f"B3 kartu '{c['label']}' = jumlah baris rinciannya",
              f"kartu {c.get('value')} vs {d.get('count') if isinstance(d, dict) else d}")


def bagian_keuangan():
    head("C. Keuangan: ringkasan = drill-down, ember aging = rincian embernya")
    h = login(ROLES["finance"])
    sc, s = get(h, "/finance/summary")
    if not check(sc == 200, "C1 /finance/summary terbaca oleh finance", s):
        return
    for key in ("ar_outstanding", "ar_overdue", "ap_outstanding", "contract_liability",
                "customer_deposits", "revenue_recognized"):
        sc2, d = get(h, f"/finance/drilldown/{key}")
        check(sc2 == 200 and int(d.get("total") or 0) == int(s.get(key) or 0),
              f"C2 kartu `{key}` = Σ baris rinciannya",
              f"kartu {s.get(key)} vs rincian {d.get('total') if isinstance(d, dict) else d}")
    for side, kunci in (("ar", "ar_bucket"), ("ap", "ap_bucket")):
        ember = s.get(f"{side}_buckets") or {}
        check(sum(int(v or 0) for v in ember.values()) == int(s.get(f"{side}_outstanding") or 0),
              f"C3 Σ ember aging {side.upper()} = total {side.upper()} belum lunas",
              f"{ember} vs {s.get(f'{side}_outstanding')}")
        for bk, val in ember.items():
            sc3, d = get(h, f"/finance/drilldown/{kunci}", bucket=bk)
            check(sc3 == 200 and int(d.get("total") or 0) == int(val or 0),
                  f"C4 ember {side.upper()} '{bk}' = rincian embernya",
                  f"{val} vs {d.get('total') if isinstance(d, dict) else d}")
    # Kartu AR di Beranda finance dan kartu AR di dashboard Keuangan harus satu angka.
    sc4, home = get(h, "/work/home")
    ar_home = next((k for k in (home.get("kpis") or []) if k.get("drill_key") == "ar_outstanding"), None)
    check(sc4 == 200 and ar_home is not None
          and int(round(float(ar_home.get("value") or 0))) == int(s.get("ar_outstanding") or 0),
          "C5 'AR Outstanding' di Beranda = 'ar_outstanding' di dashboard Keuangan (satu angka, dua layar)",
          f"{ar_home and ar_home.get('value')} vs {s.get('ar_outstanding')}")
    sales = login(ROLES["sales"])
    sc5, _ = get(sales, "/finance/drilldown/ar_outstanding")
    check(sc5 == 403, "C6 sales TIDAK boleh membuka rincian keuangan (drill-down ikut RBAC, bukan pintu belakang)",
          str(sc5))


def bagian_bi():
    head("D. BI: setiap metrik berumus, nama yang sama = rumus yang sama")
    h = login(ROLES["super_admin"])
    sc, cat = get(h, "/analytics/metrics")
    if not check(sc == 200 and isinstance(cat, list) and len(cat) >= 40, "D1 kamus metrik terbaca", cat):
        return
    tanpa = [m["code"] for m in cat if not (m.get("formula") or "").strip()]
    check(not tanpa, "D2 setiap metrik punya rumus tertulis (angka tanpa rumus tidak bisa diperiksa)", tanpa[:5])
    by_label = defaultdict(set)
    for m in cat:
        by_label[re.sub(r"\s+", " ", (m.get("label") or "").strip().lower())].add(
            re.sub(r"\s+", " ", (m.get("formula") or "").strip().lower()))
    ganda = {lbl: sorted(f) for lbl, f in by_label.items() if len(f) > 1}
    check(not ganda, "D3 dua metrik dengan NAMA sama tidak punya RUMUS berbeda (BI-02: win rate satu definisi)",
          str(ganda)[:200])
    led07 = next((m for m in cat if m["code"] == "LED-07"), {})
    check("hilang" in (led07.get("formula") or "").lower() or "lost" in (led07.get("formula") or "").lower(),
          "D4 rumus win rate menyebut pembaginya (menang + hilang) — bukan 'total lead'",
          led07.get("formula"))
    sc2, led13 = get(h, "/analytics/metric/LED-13", period="all")
    if check(sc2 == 200, "D5 LED-13 (sumber lead terbaik) terbaca", led13):
        rows = led13.get("breakdown") or []
        kecil = [r for r in rows if not r.get("eligible")]
        best = (led13.get("inputs") or {}).get("sumber_terbaik")
        check(all(r.get("label") != best for r in kecil) or best is None,
              "D6 sumber bersampel kecil TIDAK pernah menjadi 'terbaik' (BI-01)",
              f"terbaik={best}, tidak layak={[r.get('label') for r in kecil][:4]}")
        check(all(("win_pct" in r and "conversion_pct" in r) for r in rows),
              "D7 per sumber membawa DUA angka bernama beda: win_pct (menang/(menang+hilang)) & conversion_pct (menang/semua)")


def bagian_kode():
    head("K. Kode: sinkronisasi kartu tidak boleh dicabut diam-diam")
    wr = read(BE / "routers" / "work_router.py")
    check("_sync_with_drilldown(user, await _kpis(" in wr,
          "K1 `work_home` mengambil angka kartu dari mesin drill-down (`_sync_with_drilldown`) — FIN-02")
    fd = read(BE / "finance_drilldown.py")
    check('it.get("paid_amount"' in fd or "paid_amount" in fd,
          "K2 drill-down AR membaca sisa per TERMIN (`paid_amount`), sama dengan kartu `ar_aging` — FIN-01")
    fe = read(BE / "finance_engine.py")
    check("dso" not in fe.lower().replace("fin-03", "").replace("bukan dso", ""),
          "K3 tidak ada angka bernama 'DSO' yang dihitung dengan rumus bukan-DSO (FIN-03: dinamai jujur `outstanding_pct`)")
    en = read(BE / "engine.py")
    check("units_total" in en and "max(units_total, len(scheds))" in en,
          "K4 progres unit proyek dibagi SEMUA unit (PRJ-01), bukan hanya yang dijadwalkan")
    cu = read(BE / "core_utils.py")
    salinan = [p for p in BE.rglob("*.py") if re.search(r"^def period_of\(", read(p), re.M)]
    check(salinan == [BE / "core_utils.py"] and "astimezone(WIB)" in cu,
          "K5 `period_of` SATU definisi (core_utils, WIB) — CFG-01", str([p.name for p in salinan]))


def main():
    print("GATE 62 — angka kartu = jumlah baris rinciannya (Audit Tahap 7 §2)")
    bagian_beranda()
    bagian_lead()
    bagian_keuangan()
    bagian_bi()
    bagian_kode()
    print("\n" + "=" * 78)
    if fails:
        print(f"GATE 62 MERAH — {len(fails)} gagal / {ok + len(fails)} pemeriksaan")
        for f in fails:
            print(f"  - {f}")
        sys.exit(1)
    print(f"GATE 62 PASSED — {ok} pemeriksaan: kartu, rincian, dan rumus berkata satu angka")


if __name__ == "__main__":
    main()
