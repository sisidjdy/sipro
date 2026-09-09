#!/usr/bin/env python3
"""verify_p75-78.py — GATE 60: biaya all-in terkonfigurasi + penagihan biaya (titipan/beban) +
pencairan KPR bertahap (Fase 75b–78).

  K   — KODE: tidak ada input biaya bebas untuk sales (deals_router memaksa skema/peran), komponen
        breakdown lahir dari snapshot `costs.components`, akun 2-1470 & 6-1700 di CoA, seri nomor
        `cost_invoice`/`cost_receipt` terdaftar, pencairan lewat `kpr_disburse` (guard AR, plafon,
        toleransi, pembatalan), QuotationBreakdown tanpa sisa ekspresi JSX + punya uji render.
  D   — PERILAKU (server hidup): master ter-seed, preview BPHTB memakai NPOPTKP, sales ditolak 403 saat
        mengetik biaya bebas, GET /gl/journals?source_id= bekerja, skema pencairan ≠100% ditolak.

Jalankan: python3 scripts/verify_p75-78.py
"""
import re
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
BE = ROOT / "backend"
FE = ROOT / "frontend" / "src"
API = "http://localhost:8001/api"
PASSWORD = "Sipro#2026"
ok, fails = 0, []


def check(cond, label, detail=None):
    global ok
    if cond:
        ok += 1
        print(f"  OK    {label}")
    else:
        fails.append(label)
        print(f"  GAGAL {label}" + (f" — {detail}" if detail else ""))
    return cond


def head(t):
    print(f"\n{t}\n" + "-" * len(t))


def read(p):
    return p.read_text(encoding="utf-8", errors="ignore") if p.exists() else ""


head("K — kode")
ae = read(BE / "allin_engine.py")
kd = read(BE / "kpr_disburse.py")
dr = read(BE / "routers" / "deals_router.py")
ce = read(BE / "contracts_engine.py")
gl = read(BE / "gl_engine.py")
ke = read(BE / "kpr_engine.py")
qb = read(FE / "components" / "quotations" / "QuotationBreakdown.js")
check("rumus_bphtb" in ae and "npoptkp" in ae, "komponen BPHTB memakai rumus × (harga − NPOPTKP) dari master")
check("MANUAL_ROLES" in dr and "Input biaya bebas sudah ditutup" in dr, "sales tidak boleh mengetik biaya bebas (deals_router)")
check("addon_zero_override" in dr and "diskon 100%" in dr, "add-on Rp0 diblokir + override manajer = diskon 100%")
check('costs.get("components")' in ce, "breakdown membaca snapshot komponen kontrak")
check('"2-1470"' in gl and '"6-1700"' in gl, "akun Titipan Biaya Customer & Beban Penjualan di CoA")
check('"cost_invoice"' in read(BE / "numbering_registry.py") and '"cost_receipt"' in read(BE / "numbering_registry.py"),
      "seri nomor invoice/kuitansi biaya terdaftar di /api/numbering")
check("LookupError" in kd and "Jadwal tagihan (AR) belum terbit" in kd, "pencairan tanpa tagihan → ditolak (409), bukan titipan diam-diam")
check("melebihi plafon SP3K" in kd and "toleransi" in kd and "tidak bisa dicatat 2×" in kd, "validasi plafon/toleransi/tahap ganda")
check("void_receipt" in kd and "dibatalkan" in kd, "pembatalan = jurnal balik + status dibatalkan (tanpa hapus)")
check("kpr_disburse" in ke, "kpr_engine mendelegasikan pencairan ke mesin tahapan")
check("create_ar_for_deal" in read(BE / "customer_convert.py"), "jadwal tagihan sinkron saat convert")
check("source_id" in read(BE / "routers" / "gl_router.py"), "GET /gl/journals?source_id=")
check(") : null}\n" not in qb.replace("      ) : null}\n", "") or "quotation-tax-note" in qb, "QuotationBreakdown: catatan pajak berkondisi")
check((FE / "components" / "quotations" / "QuotationBreakdown.test.js").exists(), "uji render ringan QuotationBreakdown ada")
check("DatePickerField" in read(FE / "components" / "contracts" / "KprPanel.js"), "KprPanel memakai date picker shadcn")
check("reserve-recalc-hint" in read(FE / "constants" / "testIds" / "p75.js"), "hint hitung ulang di ReserveDialog")

head("D — perilaku (server hidup)")
lead = {}
try:
    tok = requests.post(f"{API}/auth/login", json={"email": "superadmin@sipro.co.id", "password": PASSWORD}, timeout=15).json()["access_token"]
    sales = requests.post(f"{API}/auth/login", json={"email": "sales@sipro.co.id", "password": PASSWORD}, timeout=15).json()["access_token"]
    H = {"Authorization": f"Bearer {tok}"}
    HS = {"Authorization": f"Bearer {sales}"}
    comps = requests.get(f"{API}/cost-components", headers=H, timeout=15).json()["data"]
    check(any(c["code"] == "BPHTB" and c["calc_method"] == "rumus_bphtb" for c in comps), "master komponen ter-seed")
    sch = {s["code"]: s for s in requests.get(f"{API}/allin-schemes", headers=H, timeout=15).json()["data"]}
    check("ALLIN_STD" in sch and "EXCLUDE" in sch, "skema all-in bawaan ter-seed")
    pv = requests.get(f"{API}/allin-schemes/{sch['EXCLUDE']['id']}/preview", params={"price": 650_000_000}, headers=H, timeout=15).json()["data"]
    b = next(c for c in pv["components"] if c["code"] == "BPHTB")
    check(b["amount"] == round((650_000_000 - pv["npoptkp"]) * 0.05), "preview BPHTB = 5% × (harga − NPOPTKP)")
    units = requests.get(f"{API}/units", params={"status": "available", "limit": 1}, headers=H, timeout=15).json()["data"]
    # Lead BARU (bukan lead pertama, yang bisa sudah memegang 1 unit aktif → 409 batas booking,
    # bukan aturan yang sedang diuji). Probe ini menguji "sales tidak boleh mengetik biaya bebas".
    import time as _t
    lead_r = requests.post(f"{API}/leads", headers=HS, timeout=15, json={
        "name": f"Gate P75 biaya bebas {int(_t.time())}", "phone": f"62811{int(_t.time()) % 10_000_000:07d}",
        "source": "walk_in"})
    lead = (lead_r.json().get("data") or {}) if lead_r.status_code == 200 else {}
    if units and lead.get("id"):
        r = requests.post(f"{API}/deals/reserve", headers=HS, timeout=15,
                          json={"unit_id": units[0]["id"], "lead_id": lead["id"], "costs": {"bphtb": 1}})
        check(r.status_code in (403, 404), "sales mengetik biaya bebas → ditolak", f"{r.status_code} {r.text[:80]}")
    else:
        check(False, "fixture: unit tersedia + lead baru untuk probe biaya bebas", f"{lead_r.status_code} {lead_r.text[:80]}")
    r = requests.get(f"{API}/gl/journals", params={"source_type": "receipt", "source_id": "x"}, headers=H, timeout=15)
    check(r.status_code == 200 and r.json()["total"] == 0, "filter source_id jurnal")
    r = requests.post(f"{API}/kpr-disbursement-schemes", headers=H, timeout=15,
                      json={"name": "gate salah", "tranches": [{"code": "T1", "name": "x", "pct": 60, "condition": "akad"}]})
    check(r.status_code == 400, "skema pencairan ≠ 100% ditolak")
    acc = {a["code"] for a in requests.get(f"{API}/gl/accounts", headers=H, timeout=15).json()["data"]}
    check({"2-1470", "6-1700"} <= acc, "akun GL baru ada di CoA organisasi")
except Exception as e:  # noqa: BLE001
    check(False, "server hidup", str(e))
finally:
    if lead.get("id"):
        from gate_cleanup import cleanup_p75_lead
        cleanup_p75_lead(lead["id"])

print(f"\n{ok} OK, {len(fails)} GAGAL")
sys.exit(1 if fails else 0)
