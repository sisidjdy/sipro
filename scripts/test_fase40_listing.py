#!/usr/bin/env python3
"""test_fase40_listing.py — bukti kontrak daftar Fase 40 (server-side cari/filter/sort/aging).

Dijalankan langsung terhadap backend yang hidup. Menguji hal-hal yang MUDAH dibohongi:
  1. sort=asc vs desc benar-benar mengubah urutan SELURUH hasil (bukan halaman aktif),
  2. filter multi (koma) mengembalikan gabungan, bukan salah satu,
  3. pencarian tahan karakter regex (mis. '+62', '(' ) — tidak 500,
  4. kolom aging (age_hours & stage_age_hours) ada dan konsisten (umur tahap <= umur total),
  5. sort field ngawur tidak menjatuhkan endpoint (jatuh ke default),
  6. paginasi stabil: halaman 1 dan 2 tidak berbagi baris.
"""
import os
import sys

import requests

BASE = os.environ.get("SIPRO_API", "http://localhost:8001/api")
PWD = "Sipro#2026"
ok = 0
fails = []


def check(cond, label, detail=""):
    global ok
    if cond:
        ok += 1
        print(f"  PASS  {label}")
    else:
        fails.append(label)
        print(f"  FAIL  {label} — {detail}")


def login(email):
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": PWD}, timeout=30)
    r.raise_for_status()
    return r.json()["access_token"]


def get(token, path, **params):
    r = requests.get(f"{BASE}{path}", params=params,
                     headers={"Authorization": f"Bearer {token}"}, timeout=60)
    return r


def main():
    token = login("superadmin@sipro.co.id")

    print("\n[1] leads — sort server-side")
    a = get(token, "/leads", sort="name", direction="asc", limit=100)
    d = get(token, "/leads", sort="name", direction="desc", limit=100)
    check(a.status_code == 200 and d.status_code == 200, "GET /leads sort 200",
          f"{a.status_code}/{d.status_code}")
    if a.status_code == 200:
        names_a = [r["name"] for r in a.json()["data"]]
        names_d = [r["name"] for r in d.json()["data"]]
        check(names_a == sorted(names_a, key=str.lower) or names_a == sorted(names_a),
              "sort asc benar-benar terurut", names_a[:5])
        check(names_a == list(reversed(names_d)), "desc = kebalikan asc",
              f"{names_a[:3]} vs {names_d[:3]}")

    print("\n[2] leads — filter multi (koma)")
    one = get(token, "/leads", stage="nurturing", limit=100).json()
    two = get(token, "/leads", stage="nurturing,booking", limit=100).json()
    check(two["total"] >= one["total"], "filter multi >= filter tunggal",
          f'{two["total"]} vs {one["total"]}')
    stages = {r["stage"] for r in two["data"]}
    check(stages <= {"nurturing", "booking"}, "hanya tahap yang diminta", stages)

    print("\n[3] pencarian tahan regex")
    for needle in ["+62", "(", "a.*", "["]:
        r = get(token, "/leads", q=needle, limit=10)
        check(r.status_code == 200, f"cari '{needle}' tidak error", r.status_code)

    print("\n[4] aging pada payload")
    rows = get(token, "/leads", limit=100).json()["data"]
    check(bool(rows), "ada lead untuk diuji", len(rows))
    if rows:
        has = all("age_hours" in r and "stage_age_hours" in r and "stage_entered_at" in r
                  for r in rows)
        check(has, "setiap baris punya age_hours/stage_age_hours/stage_entered_at")
        sane = all((r["stage_age_hours"] or 0) <= (r["age_hours"] or 0) + 0.02 for r in rows)
        check(sane, "umur tahap <= umur total",
              [(r["name"], r["age_hours"], r["stage_age_hours"]) for r in rows[:3]])

    print("\n[5] sort field ngawur → default, bukan 500")
    r = get(token, "/leads", sort="__proto__; drop", direction="desc")
    check(r.status_code == 200, "sort ngawur tetap 200", r.status_code)

    print("\n[6] paginasi stabil (tanpa baris kembar antar halaman)")
    p1 = get(token, "/units", limit=5, skip=0, sort="status", direction="asc").json()["data"]
    p2 = get(token, "/units", limit=5, skip=5, sort="status", direction="asc").json()["data"]
    ids1 = {r["id"] for r in p1}
    ids2 = {r["id"] for r in p2}
    check(bool(ids1) and not (ids1 & ids2), "halaman 1 & 2 tidak berbagi baris",
          ids1 & ids2)

    print("\n[7] endpoint daftar lain menerima sort/cari")
    cases = [
        ("/units", {"q": "A-", "sort": "price", "direction": "desc"}),
        ("/deals", {"sort": "price", "direction": "desc"}),
        ("/customers", {"sort": "name", "direction": "asc", "q": "a"}),
        ("/work/tasks", {"scope": "all", "sort": "priority", "direction": "desc", "q": "a"}),
        ("/finance/ar", {"sort": "outstanding", "direction": "desc"}),
        ("/documents", {"sort": "doc_number", "direction": "asc"}),
        ("/complaints", {"sort": "priority", "direction": "desc", "limit": 10}),
    ]
    for path, params in cases:
        r = get(token, path, **params)
        body = r.json() if r.status_code == 200 else r.text[:120]
        check(r.status_code == 200 and isinstance(body, dict) and "data" in body,
              f"GET {path} {params} → 200 + data", f"{r.status_code} {body}")

    print("\n[8] scope sales tetap ditegakkan (regresi RBAC)")
    stoken = login("sales@sipro.co.id")
    mine = get(stoken, "/leads", limit=100).json()["data"]
    check(all(r.get("assigned_to") == "sales@sipro.co.id" for r in mine),
          "sales hanya melihat lead miliknya",
          {r.get("assigned_to") for r in mine})

    print("\n" + "=" * 60)
    print(f"PASS {ok} · FAIL {len(fails)}")
    for f in fails:
        print(f"  - {f}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
