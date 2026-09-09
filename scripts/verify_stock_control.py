#!/usr/bin/env python3
"""verify_stock_control.py — GATE 36 (Fase 48E).

Menjaga gudang: barang tidak boleh tercipta atau menguap, peringatan harus menyala sebelum
stok habis, dan nilai persediaan tidak boleh dikarang.

  S1  Transfer melebihi stok asal DITOLAK.
  S2  Transfer menulis SEPASANG mutasi: stok asal turun, stok tujuan naik dengan jumlah sama.
  S3  Batas minimum menyalakan peringatan `below_min` beserta kekurangannya.
  S4  Material tanpa batas minimum dilaporkan `no_min`/`empty` — bukan dianggap aman.
  S5  Nilai persediaan = stok × harga rata-rata bergerak dari penerimaan berharga.
  S6  Material tanpa harga masuk dilaporkan `missing_price` (nilai None), ringkasan `partial`.
  S7  RBAC: peran lapangan tidak boleh memindahkan material antar proyek.
"""
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import _fixture48 as fx  # noqa: E402

FAIL = []
PASSED = 0


def check(ok: bool, label: str, detail: str = ""):
    global PASSED
    if ok:
        PASSED += 1
        print(f"  OK    {label}")
    else:
        FAIL.append(label)
        print(f"  MERAH {label} — {detail}")
    return ok


def main() -> int:
    print("=" * 78)
    print("GATE 36 — kendali stok: transfer, peringatan minimum, nilai persediaan")
    print("=" * 78)
    pm = fx.login("pm@sipro.co.id")
    fin = fx.login("finance@sipro.co.id")
    site = fx.login("site@sipro.co.id")
    a = fx.make_project("Gate48 Stok A", f"G36A-{fx.new_id()[:4].upper()}")
    b = fx.make_project("Gate48 Stok B", f"G36B-{fx.new_id()[:4].upper()}")
    mat = fx.make_material(a["id"], "G36-SMN", "Semen gate36", "sak")
    kosong = fx.make_material(a["id"], "G36-PSR", "Pasir gate36", "m3")
    try:
        vendor = fx.api("POST", "/vendors", pm, json={
            "code": "G36-V1", "name": "PT Gate36 Supply", "category": "material"}).json()["data"]
        fx.db.vendors.update_one({"id": vendor["id"]}, {"$set": {fx.TAG: True}})
        po = fx.api("POST", "/procurement/pos", pm, json={
            "project_id": a["id"], "po_type": "material", "vendor": vendor["name"],
            "vendor_id": vendor["id"], "due_date": fx.day(2),
            "items": [{"description": "Semen gate36", "material_id": mat["id"], "uom": "sak",
                       "qty": 100, "unit_price": 90_000}]}).json()["data"]
        fx.api("POST", f"/procurement/pos/{po['id']}/approve", fin, json={"note": "gate"})
        fx.api("POST", "/procurement/grns", pm, json={
            "po_id": po["id"], "items": [{"po_item_index": 0, "qty_received": 100}]})

        too_much = fx.api("POST", "/materials/transfers", pm, json={
            "from_project_id": a["id"], "to_project_id": b["id"], "material_id": mat["id"],
            "qty": 500, "reason": "mencoba memindahkan lebih banyak daripada stok yang ada"})
        check(too_much.status_code == 400, "S1 transfer melebihi stok ditolak", too_much.text[:90])

        by_site = fx.api("POST", "/materials/transfers", site, json={
            "from_project_id": a["id"], "to_project_id": b["id"], "material_id": mat["id"],
            "qty": 5, "reason": "peran lapangan mencoba memindahkan antar proyek sendiri"})
        check(by_site.status_code == 403, "S7 peran lapangan tidak boleh transfer antar proyek",
              by_site.text[:90])

        t = fx.api("POST", "/materials/transfers", pm, json={
            "from_project_id": a["id"], "to_project_id": b["id"], "material_id": mat["id"],
            "qty": 30, "reason": "pengecoran proyek sebelah dimajukan, stok dipinjam"})
        doc = t.json().get("data", {}) if t.ok else {}
        check(t.ok and doc.get("stock_from_after") == 70 and doc.get("stock_to_after") == 30,
              "S2 transfer memindahkan tanpa menciptakan barang",
              f"{doc.get('stock_from_after')} / {doc.get('stock_to_after')} · {t.text[:60]}")

        fx.api("PUT", f"/materials/{mat['id']}/min-stock", pm, json={"min_qty": 100})
        al = fx.api("GET", "/materials/stock-alerts", pm,
                    params={"project_id": a["id"]}).json()
        row = next((r for r in al["data"] if r["material_id"] == mat["id"]), {})
        check(row.get("state") == "below_min" and row.get("shortfall") == 30,
              "S3 batas minimum menyalakan peringatan + kekurangan", str(row)[:100])
        empty_row = next((r for r in al["data"] if r["material_id"] == kosong["id"]), {})
        check(empty_row.get("state") in ("no_min", "empty"),
              "S4 material tanpa batas/stok dilaporkan apa adanya", str(empty_row)[:100])

        val = fx.api("GET", "/materials/valuation", pm, params={"project_id": a["id"]}).json()
        semen = next((r for r in val["data"] if r["material_id"] == mat["id"]), {})
        pasir = next((r for r in val["data"] if r["material_id"] == kosong["id"]), {})
        check(semen.get("avg_cost") == 90_000 and semen.get("value") == 6_300_000,
              "S5 nilai persediaan = stok × harga rata-rata bergerak", str(semen)[:110])
        check(pasir.get("state") == "missing_price" and pasir.get("value") is None
              and val["summary"]["state"] == "partial",
              "S6 material tanpa harga masuk tidak dikarang nilainya",
              str(val["summary"])[:110])
    finally:
        fx.settle()
        fx.purge()
        left = fx.orphans()
        check(all(v == 0 for v in left.values()), "Bahan uji gate dibuang bersih", str(left))

    print("-" * 78)
    if FAIL:
        print(f"GATE 36 MERAH — {len(FAIL)} gagal / {PASSED + len(FAIL)} pemeriksaan")
        for f in FAIL:
            print(f"  - {f}")
        return 1
    print(f"GATE 36 HIJAU — {PASSED} pemeriksaan")
    return 0


if __name__ == "__main__":
    sys.exit(main())
