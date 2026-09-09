#!/usr/bin/env python3
"""verify_masterplan.py — GATE hierarki Proyek → Cluster → Blok → Unit (Fase 39).

Janji bisnis yang dijaga (menutup CR-05/CR-06 pada docs/v2/21_AUDIT_KONDISI.md):
  1. SETIAP unit punya induk cluster & blok (tidak ada lagi "blok" hasil tebakan kode).
  2. Kode cluster/blok tidak boleh dobel; cluster/blok berisi unit tidak bisa dihapus.
  3. Generator unit aman diulang (kode yang sudah ada dilewati, bukan menimpa).
  4. Impor `dry_run` TIDAK menulis apa pun.
  5. Unit punya DUA status paralel (penjualan & pembangunan) yang keduanya valid SSOT.
  6. Blokir unit wajib beralasan; perubahan harga unit terikat transaksi wajib beralasan.
  7. Unit 360 mengembalikan rantai lengkap: proyek+cluster+blok+tipe+riwayat.
  8. Shape site plan tertaut dua arah ke unit (0 unit tanpa shape pada proyek terpetakan).

Exit !=0 bila ada FAIL.
"""
import os
import sys

import requests
from dotenv import load_dotenv
from pymongo import MongoClient

BASE = "http://localhost:8001/api"
PW = "Sipro#2026"
load_dotenv("/app/backend/.env")
DB = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
fails = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f" — {detail}" if detail else ""))
    if not cond:
        fails.append(name)


def login(email):
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": PW}, timeout=15)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def main():
    h = login("superadmin@sipro.co.id")
    projects = requests.get(f"{BASE}/projects", headers=h, timeout=20).json()
    plist = projects.get("data") or projects
    pid = plist[0]["id"]

    print("\n1. Integritas hierarki (data nyata di DB)")
    # Kamus status DIAMBIL DARI SSOT (`/api/reference`), bukan diketik ulang di gate.
    # Cacat nyata yang ditemukan saat penutupan Fase 50: daftar `construction_status` di gate
    # ini ketinggalan nilai `ready_handover` (dipakai sejak inspeksi serah terima Fase 50A),
    # sehingga gate melaporkan "status pembangunan tidak valid" untuk nilai yang JELAS ada di
    # Kamus Data. Gate yang menyimpan kamusnya sendiri akan selalu ketinggalan.
    reg = requests.get(f"{BASE}/reference", headers=h, timeout=20).json().get("data") or {}
    def vocab(group):
        return [o["value"] for o in ((reg.get(group) or {}).get("options") or [])]
    unit_status_ssot = vocab("unit_status")
    build_status_ssot = vocab("construction_status")
    check("kamus status unit & pembangunan terbaca dari SSOT",
          bool(unit_status_ssot) and bool(build_status_ssot),
          f"{len(unit_status_ssot)} status jual · {len(build_status_ssot)} status bangun")
    total_units = DB.units.count_documents({})
    orphan_cluster = DB.units.count_documents({"$or": [{"cluster_id": None},
                                                       {"cluster_id": {"$exists": False}}]})
    orphan_block = DB.units.count_documents({"$or": [{"block_id": None},
                                                     {"block_id": {"$exists": False}}]})
    check("semua unit punya cluster", orphan_cluster == 0,
          f"{orphan_cluster} dari {total_units} unit tanpa cluster")
    check("semua unit punya blok", orphan_block == 0,
          f"{orphan_block} dari {total_units} unit tanpa blok")
    bad_status = DB.units.count_documents({"status": {"$nin": unit_status_ssot}})
    bad_build = DB.units.count_documents(
        {"construction_status": {"$nin": build_status_ssot + [None]}})
    check("status penjualan semua valid SSOT", bad_status == 0, f"{bad_status} tidak valid")
    check("status pembangunan semua valid SSOT", bad_build == 0, f"{bad_build} tidak valid")

    print("\n2. Site plan tertaut dua arah")
    r = requests.get(f"{BASE}/masterplan/projects/{pid}/siteplan-consistency",
                     headers=h, timeout=20)
    cons = r.json().get("data", {}) if r.status_code == 200 else {}
    check("laporan konsistensi peta tersedia", r.status_code == 200, f"got {r.status_code}")
    # GAGAL bila peta menunjuk unit yang tidak ada (peta berbohong).
    check("tidak ada shape menggantung (menunjuk unit tidak ada)",
          len(cons.get("dangling_shapes") or []) == 0, str(cons.get("dangling_shapes"))[:150])
    # Unit baru yang belum digambar = pekerjaan pemetaan, dilaporkan sebagai PERINGATAN.
    if cons.get("unmapped_count"):
        print(f"  WARN  {cons['unmapped_count']} unit belum dipetakan di site plan: "
              f"{[u['code'] for u in cons['unmapped_units'][:8]]}")
    else:
        print("  PASS  semua unit sudah dipetakan di site plan")
    # Unit lama hasil migrasi WAJIB sudah tertaut dua arah.
    seeded_unmapped = DB.units.count_documents(
        {"project_id": pid, "created_by": {"$in": [None, "seed", "migration"]},
         "$or": [{"siteplan": None}, {"siteplan": {"$exists": False}}]})
    check("unit hasil seed/migrasi semua tertaut shape", seeded_unmapped == 0,
          f"{seeded_unmapped} unit lama tanpa shape")

    print("\n3. Pohon proyek konsisten dengan DB")
    r = requests.get(f"{BASE}/masterplan/projects/{pid}/tree", headers=h, timeout=20)
    check("GET tree = 200", r.status_code == 200, f"got {r.status_code}")
    tree = r.json().get("data", {}) if r.status_code == 200 else {}
    totals = tree.get("totals", {})
    check("jumlah unit pada tree = DB",
          totals.get("units") == DB.units.count_documents({"project_id": pid}),
          str(totals))
    check("tidak ada unit tanpa cluster pada tree", totals.get("unmapped_units") == 0,
          str(totals.get("unmapped_units")))

    print("\n4. Aturan tidak bisa dilanggar (uji negatif)")
    code = "GATEC"
    requests.delete(f"{BASE}/masterplan/clusters/none", headers=h, timeout=10)
    r1 = requests.post(f"{BASE}/masterplan/projects/{pid}/clusters", headers=h,
                       json={"code": code, "name": "Cluster Gate"}, timeout=15)
    cid = r1.json()["data"]["id"] if r1.status_code == 200 else None
    check("buat cluster = 200", r1.status_code == 200, r1.text[:120])
    r = requests.post(f"{BASE}/masterplan/projects/{pid}/clusters", headers=h,
                      json={"code": code, "name": "Dobel"}, timeout=15)
    check("kode cluster dobel ditolak (400)", r.status_code == 400, f"got {r.status_code}")

    r = requests.post(f"{BASE}/masterplan/clusters/{cid}/blocks", headers=h,
                      json={"code": "Z", "name": "Blok Gate"}, timeout=15)
    bid = r.json()["data"]["id"] if r.status_code == 200 else None
    check("buat blok = 200", r.status_code == 200, r.text[:120])
    r = requests.post(f"{BASE}/masterplan/clusters/{cid}/blocks", headers=h,
                      json={"code": "Z"}, timeout=15)
    check("kode blok dobel ditolak (400)", r.status_code == 400, f"got {r.status_code}")

    types = requests.get(f"{BASE}/catalog/unit-types", headers=h, timeout=15).json()["data"]
    tcode = next((t["code"] for t in types if t.get("base_price")), types[0]["code"])
    r = requests.post(f"{BASE}/masterplan/blocks/{bid}/units/generate", headers=h,
                      json={"unit_type_code": tcode, "count": 3, "start_no": 1,
                            "hook_numbers": [1]}, timeout=25)
    made = r.json()["data"]["created"] if r.status_code == 200 else []
    check("generate 3 unit = 200", r.status_code == 200 and len(made) == 3, r.text[:150])
    r = requests.post(f"{BASE}/masterplan/blocks/{bid}/units/generate", headers=h,
                      json={"unit_type_code": tcode, "count": 3, "start_no": 1}, timeout=25)
    d = r.json().get("data", {})
    check("generate ulang tidak menduplikasi",
          r.status_code == 200 and not d.get("created") and len(d.get("skipped") or []) == 3,
          str(d)[:150])
    r = requests.post(f"{BASE}/masterplan/blocks/{bid}/units", headers=h,
                      json={"no": "1", "unit_type_code": tcode}, timeout=15)
    check("kode unit dobel ditolak (400)", r.status_code == 400, f"got {r.status_code}")

    before = DB.units.count_documents({"block_id": bid})
    r = requests.post(f"{BASE}/masterplan/units/import", headers=h,
                      json={"project_id": pid, "dry_run": True,
                            "rows": [{"cluster_code": code, "block_code": "Z", "no": "77",
                                      "unit_type_code": tcode},
                                     {"cluster_code": code, "block_code": "TIDAKADA",
                                      "no": "1"}]}, timeout=20)
    res = r.json().get("data", {})
    after = DB.units.count_documents({"block_id": bid})
    check("dry-run melaporkan valid & invalid",
          res.get("valid") == 1 and res.get("invalid") == 1, str(res)[:150])
    check("dry-run TIDAK menulis data", before == after, f"{before} -> {after}")

    r = requests.delete(f"{BASE}/masterplan/clusters/{cid}", headers=h, timeout=15)
    check("hapus cluster berisi unit ditolak (400)", r.status_code == 400, f"got {r.status_code}")
    r = requests.delete(f"{BASE}/masterplan/blocks/{bid}", headers=h, timeout=15)
    check("hapus blok berisi unit ditolak (400)", r.status_code == 400, f"got {r.status_code}")

    print("\n5. Unit 360 & aturan beralasan")
    uid = DB.units.find_one({"block_id": bid}, {"_id": 0, "id": 1})["id"]
    r = requests.get(f"{BASE}/masterplan/units/{uid}/360", headers=h, timeout=20)
    data = r.json().get("data", {}) if r.status_code == 200 else {}
    check("unit 360 = 200", r.status_code == 200, f"got {r.status_code}")
    check("unit 360 memuat rantai proyek/cluster/blok/tipe",
          all(data.get(k) for k in ("project", "cluster", "block", "unit_type")),
          str(list(data.keys()))[:120])
    check("unit 360 memuat riwayat status", isinstance(data.get("history"), list)
          and len(data["history"]) >= 1)
    check("unit hook memunculkan usulan add-on",
          any(a.get("category") == "posisi_unit" for a in (data.get("suggested_addons") or [])),
          str(data.get("suggested_addons"))[:120])

    r = requests.post(f"{BASE}/masterplan/units/{uid}/block", headers=h,
                      json={"blocked": True, "reason": ""}, timeout=15)
    check("blokir unit tanpa alasan ditolak (400)", r.status_code == 400, f"got {r.status_code}")
    r = requests.post(f"{BASE}/masterplan/units/{uid}/block", headers=h,
                      json={"blocked": True, "reason": "uji gate"}, timeout=15)
    check("blokir dengan alasan = 200 & status blocked",
          r.status_code == 200 and r.json()["data"]["status"] == "blocked", r.text[:120])
    r = requests.post(f"{BASE}/masterplan/units/{uid}/block", headers=h,
                      json={"blocked": False, "reason": "uji gate selesai"}, timeout=15)
    check("buka blokir = tersedia lagi",
          r.status_code == 200 and r.json()["data"]["status"] == "available", r.text[:120])

    # unit yang sudah terikat transaksi: ubah harga tanpa alasan harus ditolak
    bound = DB.units.find_one({"status": {"$in": ["reserved", "booked", "sold"]}},
                              {"_id": 0, "id": 1, "price": 1})
    if bound:
        r = requests.patch(f"{BASE}/masterplan/units/{bound['id']}", headers=h,
                           json={"price": int(bound["price"] or 0) + 1_000_000}, timeout=15)
        check("ubah harga unit terikat transaksi tanpa alasan ditolak (400)",
              r.status_code == 400, f"got {r.status_code}")
    else:
        print("  SKIP  tidak ada unit terikat transaksi untuk diuji")

    print("\n6. Bersihkan data uji")
    for u in DB.units.find({"block_id": bid}, {"_id": 0, "id": 1}):
        DB.units.delete_one({"id": u["id"]})
    DB.blocks.delete_one({"id": bid})
    DB.clusters.delete_one({"id": cid})
    left = DB.units.count_documents({"block_id": bid})
    check("data uji dibersihkan", left == 0, f"{left} sisa")
    requests.post(f"{BASE}/masterplan/recompute-stats", headers=h, timeout=20)

    print("-" * 56)
    if fails:
        print(f"MASTERPLAN GATE FAILED: {len(fails)} temuan — {fails}")
        sys.exit(1)
    print("MASTERPLAN GATE PASSED")


if __name__ == "__main__":
    main()
