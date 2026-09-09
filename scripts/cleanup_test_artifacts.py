#!/usr/bin/env python3
"""
Pembersih artefak fixture legacy (P1 "fixture legacy mandiri").

Membuang HANYA master uji yang jelas berlabel uji dan tidak terkait transaksi:
  proyek  : nama diawali "Uji " / "Proyek uji" / "Bumi Indah Permai <tag>" tanpa deal/kontrak/SPK
  vendor  : "Vendor Uji <tag>", "Vendor Manual <tag>", kode VMAN1 tanpa PO/tagihan
  subkon  : "Subkon Uji <tag>" tanpa SPK
  tipe    : "Tipe Uji <tag>" tanpa unit
  add-on  : "Addon Uji <tag>" (harga nol yang bocor ke katalog penawaran)
Bawaan DRY-RUN (hanya melaporkan). Tambahkan --apply untuk menghapus.
"""
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / "backend" / ".env")
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
APPLY = "--apply" in sys.argv
RX_PROJECT = re.compile(r"^(Uji |Proyek uji|Bumi Indah Permai \d+)", re.I)


def act(label, n):
    print(f"  {'HAPUS' if APPLY else 'AKAN '} {label}: {n}")


def main():
    print("== Artefak fixture legacy" + (" (APPLY)" if APPLY else " (dry-run)"))
    kept = []
    for p in db.projects.find({"name": {"$regex": RX_PROJECT.pattern, "$options": "i"}}, {"id": 1, "name": 1}):
        pid = p["id"]
        unit_ids = [u["id"] for u in db.units.find({"project_id": pid}, {"id": 1})]
        terkait = (db.deals.count_documents({"unit_id": {"$in": unit_ids}})
                   + db.contracts.count_documents({"project_id": pid})
                   + db.spk.count_documents({"project_id": pid})
                   + db.ar_invoices.count_documents({"unit_id": {"$in": unit_ids}}))
        if terkait:
            kept.append(f"{p['name']} (terkait {terkait} transaksi)")
            continue
        act(f"proyek {p['name']} + {len(unit_ids)} unit", 1)
        if APPLY:
            db.units.delete_many({"project_id": pid})
            for cl in db.clusters.find({"project_id": pid}, {"id": 1}):
                db.blocks.delete_many({"cluster_id": cl["id"]})
            db.clusters.delete_many({"project_id": pid})
            db.construction_phases.delete_many({"project_id": pid})
            db.projects.delete_one({"id": pid})
    for k in kept:
        print(f"  DIPERTAHANKAN {k}")

    q_vendor = {"$or": [{"name": {"$regex": r"^Vendor (Uji|Manual) \d+$"}}, {"code": "VMAN1"}]}
    vids = [v["id"] for v in db.vendors.find(q_vendor, {"id": 1})
            if db.purchase_orders.count_documents({"vendor_id": v["id"]}) == 0
            and db.ap_invoices.count_documents({"vendor_id": v["id"]}) == 0]
    act("vendor uji", len(vids))
    if APPLY and vids:
        db.vendors.delete_many({"id": {"$in": vids}})

    sids = [s["id"] for s in db.subcontractors.find({"name": {"$regex": r"^Subkon Uji \d+$"}}, {"id": 1})
            if db.spk.count_documents({"subcontractor_id": s["id"]}) == 0]
    act("subkontraktor uji", len(sids))
    if APPLY and sids:
        db.subcontractors.delete_many({"id": {"$in": sids}})

    codes = [t["code"] for t in db.unit_types.find({"name": {"$regex": r"^Tipe Uji \d+$"}}, {"code": 1})
             if db.units.count_documents({"unit_type_code": t["code"]}) == 0]
    act("tipe unit uji", len(codes))
    if APPLY and codes:
        db.unit_types.delete_many({"code": {"$in": codes}})

    q_addon = {"name": {"$regex": r"^Addon Uji \d+$"}}
    act("add-on uji (harga nol)", db.addon_items.count_documents(q_addon))
    if APPLY:
        db.addon_items.delete_many(q_addon)
    print("selesai." if APPLY else "dry-run selesai — jalankan dengan --apply untuk menghapus.")


if __name__ == "__main__":
    main()
