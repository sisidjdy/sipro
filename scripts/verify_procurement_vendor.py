#!/usr/bin/env python3
"""verify_procurement_vendor.py — GATE 34 (Fase 48A/48B/48D).

Membuktikan janji pengadaan yang BERGIGI, memakai bahan uji buatan sendiri (`gate48`) yang
dibuang di akhir — bukan menumpang data seed (pelajaran Fase 46/47).

  V1  Vendor adalah MASTER: kode kembar ditolak.
  V2  Pembanding harga menunjuk penawaran termurah; tanpa data menjawab "belum ada data".
  V3  Harga di atas ambang diberi peringatan beralasan (bukan diam-diam lolos).
  V4  Permintaan lapangan → PO membawa jejak; PO kedua dari permintaan yang sama DITOLAK.
  V5  Retur menurunkan stok DAN nilai diterima; retur di bawah nilai tertagih ditolak.
  V6  3-way match MENAHAN tagihan melebihi barang diterima; hanya finance_manager boleh
      menerobos, dan terobosan itu berjejak (override_by + alasan).
  V7  Evaluasi vendor berbukti; vendor tanpa transaksi TIDAK diberi skor 0.
  V8  RBAC: peran lapangan tidak boleh menerobos tahanan 3-way.
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
    print("GATE 34 — pengadaan: vendor, harga, permintaan→PO, retur, 3-way menahan")
    print("=" * 78)
    pm = fx.login("pm@sipro.co.id")
    fin = fx.login("finance@sipro.co.id")
    finlead = fx.login("finlead@sipro.co.id")
    site = fx.login("site@sipro.co.id")
    proj = fx.make_project("Gate48 Pengadaan", f"G34-{fx.new_id()[:4].upper()}")
    mat = fx.make_material(proj["id"], "G34-SMN", "Semen gate34", "sak")
    req = fx.make_requisition(proj["id"], proj["name"], [fx.req_item(mat, 100)])
    try:
        v1 = fx.api("POST", "/vendors", pm, json={
            "code": "G34-V1", "name": "PT Gate34 Beton", "category": "material"}).json()["data"]
        v2 = fx.api("POST", "/vendors", pm, json={
            "code": "G34-V2", "name": "CV Gate34 Baja", "category": "material"}).json()["data"]
        fx.db.vendors.update_many({"id": {"$in": [v1["id"], v2["id"]]}}, {"$set": {fx.TAG: True}})

        dup = fx.api("POST", "/vendors", pm, json={
            "code": "G34-V1", "name": "kembar", "category": "material"})
        check(dup.status_code == 400, "V1 kode vendor kembar ditolak", dup.text[:80])

        empty = fx.api("GET", "/vendors/price-compare", pm,
                       params={"material_id": mat["id"]}).json()["data"]
        check(empty["state"] == "missing_data",
              "V2a pembanding tanpa data menjawab 'belum ada data'", str(empty)[:80])
        for vendor, price in ((v1, 100_000), (v2, 130_000)):
            fx.api("POST", "/vendors/price-list", pm, json={
                "vendor_id": vendor["id"], "material_id": mat["id"], "uom": "sak",
                "unit_price": price, "source": "penawaran", "valid_from": fx.day(-3)})
        cmp_ = fx.api("GET", "/vendors/price-compare", pm,
                      params={"material_id": mat["id"]}).json()["data"]
        check(cmp_["state"] == "complete" and cmp_["best"]["vendor_id"] == v1["id"],
              "V2b pembanding menunjuk penawaran termurah", str(cmp_.get("best"))[:80])

        chk = fx.api("GET", "/vendors/price-check", pm, params={
            "material_id": mat["id"], "unit_price": 200_000}).json()["data"]
        check(chk["state"] == "di_atas_acuan" and chk["variance_pct"] > 10,
              "V3 harga di atas ambang diberi peringatan", str(chk)[:90])

        r = fx.api("POST", f"/materials/requisitions/{req['id']}/to-po", pm, json={
            "vendor_id": v1["id"], "due_date": fx.day(2),
            "items": [{"material_id": mat["id"], "qty": 100, "unit_price": 100_000}]})
        po = r.json().get("data") if r.ok else {}
        check(r.ok and po.get("requisition_id") == req["id"],
              "V4a PO lahir dari permintaan & membawa jejaknya", r.text[:90])
        again = fx.api("POST", f"/materials/requisitions/{req['id']}/to-po", pm, json={
            "vendor_id": v1["id"],
            "items": [{"material_id": mat["id"], "qty": 100, "unit_price": 100_000}]})
        check(again.status_code == 400, "V4b PO kedua dari permintaan yang sama ditolak",
              again.text[:90])

        fx.api("POST", f"/procurement/pos/{po['id']}/approve", fin, json={"note": "gate"})
        grn = fx.api("POST", "/procurement/grns", pm, json={
            "po_id": po["id"], "items": [{"po_item_index": 0, "qty_received": 60}]}).json()["data"]
        ret = fx.api("POST", "/procurement/returns", pm, json={
            "grn_id": grn["id"], "kind": "rusak",
            "items": [{"grn_item_index": 0, "qty_returned": 10}],
            "reason": "sepuluh sak mengeras karena terkena air saat pengiriman"})
        po_now = fx.api("GET", f"/procurement/pos/{po['id']}", pm).json()["data"]
        stock = fx.api("GET", f"/materials/project/{proj['id']}", pm).json()["data"]
        semen = next((m for m in stock if m["id"] == mat["id"]), {})
        check(ret.ok and po_now["received_value"] == 5_000_000 and semen.get("stock") == 50,
              "V5a retur menurunkan stok DAN nilai diterima",
              f"{po_now.get('received_value')} / {semen.get('stock')}")

        over = fx.api("POST", "/procurement/bills", pm, json={
            "po_id": po["id"], "claimed": 9_000_000, "retention_pct": 0})
        check(over.status_code == 400 and "DITAHAN" in over.text,
              "V6a tagihan melebihi barang diterima DITAHAN", over.text[:90])
        ok_bill = fx.api("POST", "/procurement/bills", pm, json={
            "po_id": po["id"], "claimed": 5_000_000, "retention_pct": 0})
        check(ok_bill.ok and ok_bill.json()["match"]["state"] == "matched",
              "V6b tagihan sesuai barang diterima lolos", ok_bill.text[:80])

        site_force = fx.api("POST", "/procurement/bills", site, json={
            "po_id": po["id"], "claimed": 1_000_000, "retention_pct": 0,
            "override_hold": True, "override_reason": "peran lapangan mencoba menerobos"})
        check(site_force.status_code in (400, 403),
              "V8 peran lapangan tidak boleh menerobos tahanan", site_force.text[:90])

        forced = fx.api("POST", "/procurement/bills", finlead, json={
            "po_id": po["id"], "claimed": 1_000_000, "retention_pct": 0,
            "override_hold": True,
            "override_reason": "sisa barang dijamin surat jalan vendor tanggal 18 Agustus"})
        check(forced.ok and forced.json()["data"].get("override_by")
              and forced.json()["data"].get("match_state") == "overridden",
              "V6c terobosan manajer keuangan berjejak", forced.text[:90])

        blocked = fx.api("POST", "/procurement/returns", pm, json={
            "grn_id": grn["id"], "kind": "mutu",
            "items": [{"grn_item_index": 0, "qty_returned": 40}],
            "reason": "retur besar sesudah barang terlanjur ditagih hampir penuh"})
        check(blocked.status_code == 400,
              "V5b retur yang membuat diterima < tertagih ditolak", blocked.text[:90])

        ev1 = fx.api("GET", f"/vendors/{v1['id']}/evaluation", pm).json()["data"]
        ev2 = fx.api("GET", f"/vendors/{v2['id']}/evaluation", pm).json()["data"]
        check(ev1["state"] == "complete" and ev1["score"] is not None,
              "V7a vendor bertransaksi mendapat skor berbukti", str(ev1.get("score")))
        check(ev2["state"] == "missing_data" and ev2["score"] is None,
              "V7b vendor tanpa transaksi TIDAK diberi skor 0", str(ev2)[:90])
    finally:
        fx.settle()
        fx.purge()
        left = fx.orphans()
        check(all(v == 0 for v in left.values()), "Bahan uji gate dibuang bersih", str(left))

    print("-" * 78)
    if FAIL:
        print(f"GATE 34 MERAH — {len(FAIL)} gagal / {PASSED + len(FAIL)} pemeriksaan")
        for f in FAIL:
            print(f"  - {f}")
        return 1
    print(f"GATE 34 HIJAU — {PASSED} pemeriksaan")
    return 0


if __name__ == "__main__":
    sys.exit(main())
