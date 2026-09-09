#!/usr/bin/env python3
"""Audit Fase 48 — memetakan APA YANG SUDAH ADA vs APA YANG BELUM di pengadaan & subkon.

Dipakai sekali untuk menyusun rencana Fase 48 supaya tidak membangun ulang fitur yang
sudah jalan (dok: CODEBASE_MAP Fase 12/16/17/33). Tidak menulis data apa pun.
"""
import json
import os
import sys

import requests

BASE = os.environ.get("SIPRO_API", "http://localhost:8001/api")
PW = "Sipro#2026"


def login(email):
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": PW}, timeout=30)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def probe(h, method, path, **kw):
    try:
        r = requests.request(method, f"{BASE}{path}", headers=h, timeout=30, **kw)
        body = r.text[:180].replace("\n", " ")
        return r.status_code, body
    except Exception as e:  # noqa: BLE001
        return "ERR", str(e)[:120]


def show(title, rows):
    print(f"\n=== {title} ===")
    for label, (code, body) in rows.items():
        print(f"  {str(code):>4}  {label:<52} {body[:110]}")


def main():
    sa = login("superadmin@sipro.co.id")

    # 1. Master vendor: apakah ada koleksi/endpoint vendor pemasok (bukan subkontraktor)?
    show("MASTER VENDOR / DAFTAR HARGA", {
        "GET /vendors": probe(sa, "GET", "/vendors"),
        "GET /master/vendors": probe(sa, "GET", "/master/vendors"),
        "GET /procurement/vendors": probe(sa, "GET", "/procurement/vendors"),
        "GET /procurement/price-list": probe(sa, "GET", "/procurement/price-list"),
        "GET /procurement/rfq": probe(sa, "GET", "/procurement/rfq"),
        "GET /reference?group=vendor": probe(sa, "GET", "/reference/vendor"),
    })

    # 2. Evaluasi vendor / subkon
    show("EVALUASI & PENILAIAN", {
        "GET /procurement/evaluations": probe(sa, "GET", "/procurement/evaluations"),
        "GET /subcon/evaluations": probe(sa, "GET", "/subcon/evaluations"),
        "GET /subcon/subcontractors (cek field rating)":
            probe(sa, "GET", "/subcon/subcontractors"),
    })

    # 3. PO -> GRN -> 3 way -> AP
    show("PO / GRN / 3-WAY / AP", {
        "GET /procurement/pos": probe(sa, "GET", "/procurement/pos"),
        "GET /procurement/grns": probe(sa, "GET", "/procurement/grns"),
        "GET /procurement/threeway": probe(sa, "GET", "/procurement/threeway"),
        "GET /procurement/returns (retur barang)": probe(sa, "GET", "/procurement/returns"),
        "GET /ap/bills": probe(sa, "GET", "/ap/bills"),
        "GET /ap/invoices": probe(sa, "GET", "/ap/invoices"),
    })

    # 4. Permintaan material -> PO
    show("PERMINTAAN MATERIAL (MR) -> PO", {
        "GET /materials/requisitions": probe(sa, "GET", "/materials/requisitions"),
        "POST /materials/requisitions/{id}/to-po (ada rute?)":
            probe(sa, "POST", "/materials/requisitions/x/to-po", json={}),
        "GET /procurement/pos?requisition_id=x":
            probe(sa, "GET", "/procurement/pos", params={"requisition_id": "x"}),
    })

    # 5. Stok/gudang
    show("STOK / GUDANG", {
        "GET /materials/project/{id}": probe(sa, "GET", "/projects"),
        "GET /materials/transfers": probe(sa, "GET", "/materials/transfers"),
        "GET /materials/stock-alerts": probe(sa, "GET", "/materials/stock-alerts"),
        "GET /materials/valuation": probe(sa, "GET", "/materials/valuation"),
    })

    # 6. Subkon: retensi, uang muka, denda
    show("SUBKON LANJUTAN", {
        "GET /subcon/spk": probe(sa, "GET", "/subcon/spk"),
        "GET /subcon/claims": probe(sa, "GET", "/subcon/claims"),
        "GET /subcon/retentions (pencairan retensi)":
            probe(sa, "GET", "/subcon/retentions"),
        "GET /subcon/advances (uang muka)": probe(sa, "GET", "/subcon/advances"),
        "GET /subcon/penalties (denda)": probe(sa, "GET", "/subcon/penalties"),
    })

    # 7. Isi nyata: cek field pada satu SPK & satu PO
    r = requests.get(f"{BASE}/subcon/spk", headers=sa, timeout=30)
    spks = r.json().get("data", []) if r.ok else []
    print("\n=== FIELD SPK NYATA ===")
    if spks:
        print("  jumlah SPK:", len(spks))
        print("  field:", sorted(spks[0].keys()))
    else:
        print("  (tidak ada SPK)")

    r = requests.get(f"{BASE}/procurement/pos", headers=sa, timeout=30)
    pos = r.json().get("data", []) if r.ok else []
    print("\n=== FIELD PO NYATA ===")
    if pos:
        print("  jumlah PO:", len(pos))
        print("  field:", sorted(pos[0].keys()))
        print("  contoh item:", json.dumps((pos[0].get("items") or [{}])[0], ensure_ascii=False)[:300])
    else:
        print("  (tidak ada PO)")

    r = requests.get(f"{BASE}/materials/requisitions", headers=sa, timeout=30)
    reqs = r.json().get("data", []) if r.ok else []
    print("\n=== FIELD PERMINTAAN MATERIAL NYATA ===")
    if reqs:
        print("  jumlah:", len(reqs))
        print("  field:", sorted(reqs[0].keys()))
        print("  status:", sorted({x.get("status") for x in reqs}))
    else:
        print("  (tidak ada permintaan)")

    r = requests.get(f"{BASE}/subcon/subcontractors", headers=sa, timeout=30)
    subs = r.json().get("data", []) if r.ok else []
    print("\n=== FIELD SUBKONTRAKTOR NYATA ===")
    if subs:
        print("  jumlah:", len(subs))
        print("  field:", sorted(subs[0].keys()))
    else:
        print("  (tidak ada subkontraktor)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
