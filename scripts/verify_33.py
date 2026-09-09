#!/usr/bin/env python3
"""verify_33.py — GATE Fase 33: uang subkon hanya mengalir mengikuti bukti.

Melengkapi `poc_33.py` (aturan bisnis lewat API) dengan cek yang menahan pembusukan
diam-diam:

  A. Tidak ada endpoint Fase 33 yatim — lingkup SPK, opname, dan kendali biaya RAB
     HARUS punya jalan masuk di frontend (kalau tidak, fitur ini cuma ada di API).
  B. Tidak ada `data-testid` Fase 33 yang mati.
  C. Penjaga tetap terpasang di KODE: index unik satu-pekerjaan-satu-SPK, larangan
     progres SPK diketik manual, pemisahan tugas opname, ledger anti bayar ganda,
     dan UI tidak lagi mengirim persen untuk SPK berbasis item.
  D. Kontrak API: bentuk data lingkup/opname/kendali biaya sesuai yang dirender UI.
  E. Invarian data hidup: progres = nilai terverifikasi ÷ nilai lingkup, tagihan ≤
     kontrak, dan tiap termin disetujui punya tagihan AP dengan nilai yang sama.

Jalankan: python3 scripts/verify_33.py
"""
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError

ROOT = Path(__file__).resolve().parent.parent
BE = ROOT / "backend"
FE = ROOT / "frontend" / "src"
BASE = os.environ.get("SIPRO_BASE", "http://localhost:8001/api")
PW = "Sipro#2026"
load_dotenv(ROOT / "backend" / ".env")

_DB = None


def db():
    """Koneksi Mongo dibuat sekali dan HANYA untuk memeriksa kenyataan (index, sisipan uji).

    Pelajaran Fase 50 (Q6b): penjaga integritas harus diuji pada DATABASE, bukan pada teks
    sumber. Pemeriksaan berbasis string membuat gate rapuh dua arah — ia merah saat kode
    diperbaiki (mis. index unik biasa menjadi PARTIAL) dan tetap hijau saat aturannya
    sebenarnya dijatuhkan lewat jalur lain.
    """
    global _DB
    if _DB is None:
        _DB = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    return _DB

ok_n, fail_n = 0, 0


def check(cond, label, detail=""):
    global ok_n, fail_n
    if cond:
        ok_n += 1
        print(f"  PASS  {label}")
    else:
        fail_n += 1
        print(f"  FAIL  {label} {detail}")


def fe_sources() -> str:
    out = []
    for p in FE.rglob("*.js"):
        if "components/ui/" in p.as_posix():
            continue
        out.append(p.read_text(encoding="utf-8", errors="ignore"))
    return "\n".join(out)


def login(email):
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": PW}, timeout=30)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def head(t):
    print(f"\n{t}")


# ---------------------------------------------------------------- A. endpoint dipakai UI
def audit_orphan_endpoints(fe: str):
    head("A. Endpoint Fase 33 punya jalan masuk di frontend")
    pairs = [
        ("/scope/candidates", "kandidat lingkup dipakai dialog tambah pekerjaan"),
        ("/scope`", "daftar lingkup SPK dirender"),
        ("/opname`", "pratinjau opname dipakai saat mengajukan termin"),
        ("/boq/control", "kendali biaya RAB dirender"),
        ("/boq/steps", "daftar langkah jadwal dipakai pemetaan RAB"),
        ("/steps`", "penyimpanan pemetaan RAB → langkah"),
    ]
    for needle, label in pairs:
        check(needle in fe, label, f"-> '{needle}' tidak ditemukan di frontend")


# ---------------------------------------------------------------- B. testId hidup
def audit_dead_testids(fe: str):
    head("B. testId Fase 33 tidak ada yang mati")
    src = (FE / "constants" / "testIds" / "opname.js").read_text(encoding="utf-8")
    names = [line.split(":")[0].strip() for line in src.splitlines()
             if ":" in line and line.strip().endswith(",") and "//" not in line]
    consts = {"SCOPE", "OPNAME", "COST"}
    dead = []
    for key in names:
        if key in ("export const SCOPE", "export const OPNAME", "export const COST"):
            continue
        if not any(f"{c}.{key}" in fe for c in consts):
            dead.append(key)
    check(not dead, "semua testId Fase 33 dipakai komponen", f"-> mati: {dead}")
    check((FE / "constants" / "testIds" / "index.js").read_text(encoding="utf-8")
          .find("./opname") > 0, "testIds Fase 33 terdaftar di index")


# ---------------------------------------------------------------- C. penjaga di kode
# ---------------------------------------------------------------- C. penjaga di kode
def audit_unique_scope_index():
    """INV-33-3 diuji pada KENYATAAN: satu item pekerjaan tidak boleh diklaim dua SPK.

    Aturannya dijaga index unik PARTIAL pada `spk_scope_items` — partial karena lingkup
    borongan/manual memang tidak menunjuk item jadwal, dan di MongoDB `null == null`
    sehingga index unik biasa (versi lama) diam-diam melarang baris borongan KEDUA di
    seluruh organisasi. Karena itu gate memeriksa tiga hal sekaligus:
      1. index unik atas (org_id, build_item_id) benar-benar ADA di database,
      2. ia PARTIAL (hanya berlaku bila `build_item_id` bertipe string),
      3. ia BERGIGI: sisipan kembar langsung ke database ditolak, sedangkan dua baris
         borongan tanpa item pekerjaan tetap diterima.
    """
    coll = db().spk_scope_items
    info = coll.index_information()
    unique = [n for n, spec in info.items()
              if spec.get("unique")
              and [k for k, _ in spec.get("key", [])] == ["org_id", "build_item_id"]]
    check(bool(unique),
          "INV-33-3 index unik satu pekerjaan satu SPK berlaku di DATABASE",
          f"-> index yang ada: {sorted(info)}")
    if not unique:
        return
    check(any(info[n].get("partialFilterExpression") for n in unique),
          "index unik lingkup PARTIAL (lingkup borongan tanpa item tidak saling menabrak)",
          "-> index unik biasa melarang baris borongan kedua di seluruh organisasi")

    org = os.environ.get("DEFAULT_ORG_ID", "org-sipro")
    tag = "gate33-index"
    coll.delete_many({"spk_id": tag})
    bitten, borongan_ok = False, False
    try:
        twin = {"org_id": org, "spk_id": tag, "build_item_id": f"{tag}-item"}
        coll.insert_one(dict(twin, id=f"{tag}-1"))
        try:
            coll.insert_one(dict(twin, id=f"{tag}-2"))
        except DuplicateKeyError:
            bitten = True
        # Dua baris borongan (tanpa item pekerjaan) HARUS boleh hidup bersama.
        coll.insert_one({"org_id": org, "spk_id": tag, "id": f"{tag}-b1",
                         "build_item_id": None})
        coll.insert_one({"org_id": org, "spk_id": tag, "id": f"{tag}-b2",
                         "build_item_id": None})
        borongan_ok = True
    except DuplicateKeyError:
        borongan_ok = False
    finally:
        coll.delete_many({"spk_id": tag})
    check(bitten, "database MENOLAK item pekerjaan kembar (bukan hanya pemeriksaan aplikasi)",
          "-> sisipan kedua lolos: aturan satu-pekerjaan-satu-SPK tidak berlaku")
    check(borongan_ok, "dua lingkup borongan tanpa item pekerjaan tetap boleh disimpan",
          "-> index terlalu lebar: pekerjaan borongan kedua ditolak database")


def audit_guards(fe: str):
    head("C. Penjaga anti-kecurangan masih terpasang di kode")
    op = (BE / "opname.py").read_text(encoding="utf-8")
    audit_unique_scope_index()
    check("claim_id" in op and "settle_lines" in op,
          "INV-33-2 ledger pekerjaan yang sudah dibayar ada")
    check("pending_claim_id" in op and "release_lines" in op,
          "pekerjaan dalam pengajuan ditahan & dilepas saat termin ditolak")
    sr = (BE / "routers" / "subcon_router.py").read_text(encoding="utf-8")
    check("dihitung otomatis" in sr and "progress_pct" in sr,
          "INV-33-5 progres SPK mode item tidak bisa diketik manual")
    cr = (BE / "routers" / "subcon_claims_router.py").read_text(encoding="utf-8")
    check("_create_item_claim" in cr and "opname_preview" in cr,
          "termin berbasis item dihitung dari pratinjau opname")
    check("Opname harus dilakukan orang lain" in cr,
          "INV-33-7 pengaju termin tidak boleh meng-opname sendiri")
    check("MENGURANGI" in cr, "INV-33-6 opname tidak bisa menambah baris")
    check("revalidate" in cr, "baris divalidasi ulang sebelum tagihan AP dibuat")
    sub = (FE / "components" / "subcon" / "SubmitClaimDialog.js").read_text(encoding="utf-8")
    check("itemBased ? undefined : Number(pct)" in sub,
          "UI tidak mengirim persen manual untuk SPK berbasis item")
    check("SpkScopeSection" in (FE / "components" / "subcon" / "SPKDetailSheet.js")
          .read_text(encoding="utf-8"), "panel lingkup terpasang di detail SPK")
    check("ClaimOpnameSheet" in (FE / "components" / "subcon" / "ClaimsPanel.js")
          .read_text(encoding="utf-8"), "lembar opname per baris terpasang di daftar termin")
    check("CostControlPanel" in (FE / "pages" / "BoQPage.js").read_text(encoding="utf-8"),
          "panel kendali biaya terpasang di halaman RAB")
    check("item.contract" in (FE / "components" / "construction" / "BuildItemCard.js")
          .read_text(encoding="utf-8"),
          "kartu pekerjaan konstruksi menampilkan nilai borongan & status tagih")


# ---------------------------------------------------------------- D/E. kontrak & invarian
def audit_runtime():
    head("D. Kontrak API lingkup / opname / kendali biaya")
    pm = login("pm@sipro.co.id")
    sales = login("sales@sipro.co.id")
    spks = requests.get(f"{BASE}/subcon/spk", headers=pm, timeout=60).json()
    rows = spks.get("data") or []
    for k in ("item_based", "verified_value", "billed_value", "claimable_value"):
        check(k in (spks.get("summary") or {}), f"ringkasan daftar SPK memuat '{k}'")
    item_spks = [s for s in rows if s.get("scope_mode") == "items"]
    if not item_spks:
        check(False, "ada SPK berbasis item untuk diuji",
              "-> jalankan seed (seed_phase33) atau buat lingkup SPK")
        return
    spk = max(item_spks, key=lambda s: int(s.get("scope_items") or 0))
    sid = spk["id"]
    sc = requests.get(f"{BASE}/subcon/spk/{sid}/scope", headers=pm, timeout=60).json()
    for k in ("data", "summary", "contract", "blockers", "spk"):
        check(k in sc, f"GET /subcon/spk/id/scope memuat '{k}'")
    s = sc.get("summary") or {}
    need = ("items", "scope_value", "verified_value", "billed_value", "claimable_value",
            "verified_items", "billed_items", "claimable_items", "regressed_items",
            "progress_pct", "billed_pct")
    check(all(k in s for k in need), "ringkasan lingkup memuat semua angka yang dirender UI",
          f"-> hilang: {[k for k in need if k not in s]}")
    row = (sc.get("data") or [{}])[0]
    need_row = ("unit_code", "step_code", "step_name", "value", "state", "state_label",
                "claimable", "verified", "claim_number", "cost_code")
    check(all(k in row for k in need_row), "baris lingkup memuat kolom tabel UI",
          f"-> hilang: {[k for k in need_row if k not in row]}")
    cand = requests.get(f"{BASE}/subcon/spk/{sid}/scope/candidates", headers=pm,
                        timeout=90).json().get("data") or {}
    check(all(k in cand for k in ("units", "contract_value", "allocated", "unallocated",
                                  "rab_mapped")), "kandidat memuat info alokasi kontrak")
    items = [it for u in (cand.get("units") or []) for it in u.get("items") or []]
    if items:
        need_c = ("build_item_id", "step_code", "step_name", "week", "weight", "verified",
                  "status", "suggested_value", "unit_id", "unit_code")
        check(all(k in items[0] for k in need_c), "kandidat memuat kolom dialog pemilihan",
              f"-> hilang: {[k for k in need_c if k not in items[0]]}")
    opn = requests.get(f"{BASE}/subcon/spk/{sid}/opname", headers=pm,
                       timeout=60).json().get("data") or {}
    need_o = ("lines", "gross", "retention_pct", "retention_est", "net_est", "summary",
              "blockers", "open_claim", "contract_value")
    check(all(k in opn for k in need_o), "pratinjau opname memuat semua bagian UI",
          f"-> hilang: {[k for k in need_o if k not in opn]}")
    check(opn.get("retention_est") == round(int(opn.get("gross") or 0)
                                            * float(opn.get("retention_pct") or 0) / 100),
          "retensi pada pratinjau dihitung dari % SPK")
    proj = spk["project_id"]
    cc = requests.get(f"{BASE}/boq/control", headers=pm, params={"project_id": proj},
                      timeout=90).json().get("data") or {}
    need_cc = ("totals", "categories", "cost_codes", "warnings", "unmapped_budget",
               "scope_lines")
    check(all(k in cc for k in need_cc), "kendali biaya memuat semua bagian UI",
          f"-> hilang: {[k for k in need_cc if k not in cc]}")
    t = cc.get("totals") or {}
    need_t = ("budget", "contracted", "verified", "billed", "variance", "unbilled_verified")
    check(all(k in t for k in need_t), "total kendali biaya lengkap",
          f"-> hilang: {[k for k in need_t if k not in t]}")
    if cc.get("cost_codes"):
        need_code = ("key", "label", "budget", "contracted", "verified", "billed", "steps",
                     "mapped", "over_commit")
        check(all(k in cc["cost_codes"][0] for k in need_code),
              "baris kode biaya memuat kolom UI (termasuk pemetaan langkah)",
              f"-> hilang: {[k for k in need_code if k not in cc['cost_codes'][0]]}")
    steps = requests.get(f"{BASE}/boq/steps", headers=pm, params={"project_id": proj},
                         timeout=60).json().get("data") or []
    check(bool(steps) and all(k in steps[0] for k in ("step_code", "step_name", "week",
                                                      "units", "weight")),
          "daftar langkah jadwal memuat kolom dialog pemetaan")
    unit_id = row.get("unit_id")
    if unit_id:
        ub = requests.get(f"{BASE}/build/unit/{unit_id}", headers=pm, timeout=90).json()
        with_contract = [i for i in (ub.get("items") or []) if i.get("contract")]
        check(bool(with_contract),
              "kartu pekerjaan menerima data borongan dari backend")
        if with_contract:
            need_ct = ("spk_number", "value", "billed", "subcontractor_name")
            check(all(k in with_contract[0]["contract"] for k in need_ct),
                  "data borongan pada pekerjaan lengkap")

    head("E. Invarian data hidup (bukan sekadar bentuk data)")
    verified, scope_v, billed = s["verified_value"], s["scope_value"], s["billed_value"]
    check(int(sc["spk"]["progress_pct"]) == int(round(verified / scope_v * 100)) if scope_v
          else True, "progres SPK = nilai terverifikasi ÷ nilai lingkup",
          f"-> {sc['spk']['progress_pct']} vs {verified}/{scope_v}")
    check(billed <= int(spk.get("contract_value") or 0),
          "INV-33-4 total tagihan tidak melebihi nilai kontrak")
    check(billed <= verified, "INV-33-1 nilai ditagih tidak melebihi nilai terverifikasi",
          f"-> ditagih {billed} vs terbukti {verified}")
    claims = requests.get(f"{BASE}/subcon/claims", headers=pm, timeout=60).json().get("data") or []
    fin = login("finance@sipro.co.id")
    bills = {b["id"]: b for b in (requests.get(f"{BASE}/finance/ap/bills", headers=fin,
                                               timeout=60).json().get("data") or [])}
    bad = []
    for c in claims:
        if c.get("status") != "approved":
            continue
        b = bills.get(c.get("ap_bill_id"))
        if not b or int(b.get("claimed") or 0) != int(c.get("gross") or 0):
            bad.append(c.get("claim_number"))
        if c.get("basis") == "items":
            inc = sum(int(l["value"]) for l in (c.get("lines") or []) if l.get("included"))
            if inc != int(c.get("gross") or 0):
                bad.append(f"{c.get('claim_number')}(baris≠nilai)")
    check(not bad, "tiap termin disetujui punya tagihan AP bernilai sama", f"-> {bad}")

    head("F. Guard runtime & RBAC (aman diulang)")
    r = requests.put(f"{BASE}/subcon/spk/{sid}", headers=pm, json={"progress_pct": 99},
                     timeout=60)
    check(r.status_code == 400, "progres SPK berbasis item ditolak saat diketik",
          f"-> {r.status_code}")
    r = requests.get(f"{BASE}/subcon/spk/{sid}/scope", headers=sales, timeout=60)
    check(r.status_code == 403, "sales tidak bisa melihat lingkup SPK", f"-> {r.status_code}")
    r = requests.get(f"{BASE}/boq/control", headers=sales, params={"project_id": proj},
                     timeout=60)
    check(r.status_code == 403, "sales tidak bisa melihat kendali biaya",
          f"-> {r.status_code}")
    site = login("site@sipro.co.id")
    r = requests.post(f"{BASE}/subcon/spk/{sid}/scope", headers=site, json={"lines": []},
                      timeout=60)
    check(r.status_code == 403, "pelaksana tidak bisa mengubah lingkup SPK",
          f"-> {r.status_code}")


def main():
    fe = fe_sources()
    audit_orphan_endpoints(fe)
    audit_dead_testids(fe)
    audit_guards(fe)
    audit_runtime()
    print("-" * 60)
    print(f"HASIL: {ok_n} PASS, {fail_n} FAIL")
    if fail_n:
        sys.exit(1)
    print("VERIFY 33 PASSED")


if __name__ == "__main__":
    main()
