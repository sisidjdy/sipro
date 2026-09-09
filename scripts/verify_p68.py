#!/usr/bin/env python3
"""verify_p68.py — GATE 59: denda terjadwal + pengingat tunggakan pra-SP (Fase 68).

Dua janji fase ini yang tidak boleh dilumpuhkan diam-diam:

  K — KODE: opsi & remnya hidup di Pusat Konfigurasi (bukan angka mati), TIDAK ada mesin
      denda kedua (yang menagihkan tetap `late_fee_engine.apply`), penjadwal terdaftar
      (termasuk p59 yang dulu lupa didaftarkan), jenis pengingat baru masuk SSOT, dan
      pengiriman WA tetap pola jujur (wa.me untuk manusia / status simulasi).
  KUI — LAYAR: panel denda terjadwal dirender di tab Penagihan dengan testId-nya, dan
      tautan kirim manual WA ada di panel pengingat.
  D — PERILAKU (server hidup): bentuk endpoint, RBAC (sales tidak boleh menjalankan),
      bawaan MATI, rem nominal benar-benar menahan (run dengan ambang tinggi = 0 tagihan),
      dan kandidat pengingat pra-SP lahir dari data tunggakan yang nyata.

Jalankan: python3 scripts/verify_p68.py
"""
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
        return True
    fails.append(label)
    print(f"  GAGAL {label}" + (f" — {detail}" if detail else ""))
    return False


def head(t):
    print(f"\n{t}\n" + "-" * len(t))


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="ignore") if p.exists() else ""


def login(email):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": PASSWORD},
                      timeout=30)
    tok = (r.json() or {}).get("token") or (r.json() or {}).get("access_token")
    return {"Authorization": f"Bearer {tok}"}


def bagian_kode():
    head("K. Kode: kebijakan di Pusat Konfigurasi, satu mesin, penjadwal terdaftar")
    st = read(BE / "settings_store.py")
    for key in ("payment.late.auto_apply", "payment.late.auto_min_days",
                "payment.late.auto_min_amount", "reminder.arrears_enabled",
                "reminder.arrears_min_amount", "reminder.arrears_min_months",
                "reminder.arrears_every_days", "reminder.template_arrears"):
        check(f'"{key}"' in st, f"K1 setting `{key}` terdaftar di Pusat Konfigurasi")
    lfa = read(BE / "late_fee_auto.py")
    check("lf.apply(" in lfa and "post_journal" not in lfa,
          "K2 penjadwal menagihkan lewat `late_fee_engine.apply` — TIDAK ada mesin kedua "
          "yang menjurnal sendiri")
    check("waive" not in lfa.replace("Keringanan", "").replace("meringankan", ""),
          "K3 penjadwal tidak pernah MERINGANKAN denda (tetap milik Manajer Keuangan)")
    check('mode == "auto" and not conf["enabled"]' in lfa,
          "K4 mode otomatis menghormati saklar `payment.late.auto_apply` (bawaan MATI)")
    eng = read(BE / "engine.py")
    check("sched_p68.register(_scheduler)" in eng,
          "K5 penjadwal Fase 68 didaftarkan di engine")
    check("sched_p59.register(_scheduler)" in eng,
          "K6 penjadwal p59 (peninjauan tunggakan) IKUT didaftarkan — bug laten ditutup")
    wre = read(BE / "wa_reminder_engine.py")
    check('"arrears_warning"' in wre and "arrears_min_amount" in wre
          and "arrears_min_months" in wre,
          "K7 pengingat pra-SP lahir dari mesin pengingat yang sama, dengan rem nominal & "
          "bulan yang bisa disetel")
    check("months_in_arrears" in wre,
          "K8 bulan tunggakan dihitung mesin yang SAMA dengan SP & kandidat pembatalan")
    check("wa_url(" in wre,
          "K9 tautan `wa.me` disiapkan untuk pengiriman MANUAL (pola jujur Fase 62)")
    ref = read(BE / "reference_p51.py")
    check('_o("arrears_warning"' in ref, "K10 jenis pengingat baru masuk SSOT reference")
    rt = read(BE / "routers" / "p68_router.py")
    check('require_permission("late_fee",' in rt and '"create"' in rt and '"view"' in rt,
          "K11 RBAC router: membaca = late_fee:view, menjalankan = late_fee:create")


def bagian_ui():
    head("KUI. Layar")
    panel = read(FE / "components" / "finance" / "LateFeeAutoPanel.js")
    for tid in ("autoPanel", "autoState", "autoRunBtn", "autoPreviewRow", "autoRunRow",
                "autoRule"):
        check(f"T.{tid}" in panel, f"KUI1 testId `{tid}` dirender di panel denda terjadwal")
    fin = read(FE / "pages" / "FinancePage.js")
    check("LateFeeAutoPanel" in fin, "KUI2 panel denda terjadwal hidup di halaman Keuangan "
                                     "(tab Penagihan)")
    rem = read(FE / "components" / "omni" / "RemindersPanel.js")
    check("P68.reminderWaLink" in rem and "wa_link" in rem,
          "KUI3 panel pengingat punya tautan kirim manual lewat WhatsApp")


def bagian_perilaku():
    head("D. Perilaku (server hidup)")
    su = login("superadmin@sipro.co.id")
    sales = login("sales@sipro.co.id")

    r = requests.get(f"{API}/finance/late-fee-auto", headers=su, timeout=30)
    d = (r.json() or {}).get("data") or {}
    check(r.status_code == 200 and {"config", "preview", "runs"} <= set(d),
          "D1 GET /finance/late-fee-auto menjawab config + preview + runs")
    conf = d.get("config") or {}
    check(conf.get("enabled") is False,
          "D2 bawaan MATI — menagih otomatis adalah keputusan bisnis, bukan bawaan kode",
          f"enabled={conf.get('enabled')}")
    check("rule_sentence" in conf and str(conf.get("min_days")) in conf["rule_sentence"],
          "D3 kalimat aturan DISUSUN MESIN dari kebijakan yang berlaku")
    pv = d.get("preview") or {}
    check(all(("eligible" in x and ("hold_reason" in x)) for x in pv.get("rows") or []),
          "D4 pratinjau menyebut siapa yang memenuhi & siapa yang DITAHAN beserta sebabnya")

    r = requests.post(f"{API}/finance/late-fee-auto/run", headers=sales, timeout=30)
    check(r.status_code == 403, "D5 sales TIDAK boleh menjalankan penagihan otomatis",
          f"HTTP {r.status_code}")

    # Rem nominal benar-benar menahan: ambang dinaikkan, run manual menagih NOL, ambang
    # dikembalikan. Buku besar tidak berubah oleh gate ini.
    key = "payment.late.auto_min_amount"
    asal = requests.get(f"{API}/settings/effective", params={"keys": key}, headers=su,
                        timeout=30).json()["data"].get(key) or 0
    requests.put(f"{API}/settings/{key}", headers=su, timeout=30,
                 json={"value": 999999999999, "reason": "gate 59: uji rem nominal"})
    try:
        r = requests.post(f"{API}/finance/late-fee-auto/run", headers=su, timeout=60)
        out = (r.json() or {}).get("data") or {}
        check(r.status_code == 200 and out.get("charged_count") == 0,
              "D6 run dengan ambang nominal tinggi menagih NOL (rem bekerja, buku besar "
              "tidak disentuh gate)", f"HTTP {r.status_code} charged={out.get('charged_count')}")
        check(out.get("mode") == "manual" and out.get("actor") == "superadmin@sipro.co.id",
              "D7 putaran ditulis dengan MODE dan NAMA pelakunya")
        r2 = requests.get(f"{API}/finance/late-fee-auto", headers=su, timeout=30)
        runs = ((r2.json() or {}).get("data") or {}).get("runs") or []
        check(any(x.get("id") == out.get("id") for x in runs),
              "D8 riwayat putaran terbaca kembali dari layar")
    finally:
        requests.put(f"{API}/settings/{key}", headers=su, timeout=30,
                     json={"value": asal, "reason": "gate 59: kembalikan ambang"})
    now = requests.get(f"{API}/settings/effective", params={"keys": key}, headers=su,
                       timeout=30).json()["data"].get(key)
    check(now == asal, "D9 setelan dikembalikan seperti semula (gate bersih)")

    r = requests.get(f"{API}/reminders/candidates", params={"kind": "arrears_warning"},
                     headers=su, timeout=60)
    rows = (r.json() or {}).get("data") or []
    check(r.status_code == 200, "D10 kandidat pengingat pra-SP terbaca")
    check(all(x.get("kind") == "arrears_warning" and "SP" in (x.get("reason") or "")
              for x in rows),
          "D11 tiap kandidat menyebut keadaan Surat Peringatannya (pra-SP1 / tingkat "
          "berikutnya)")
    check(all(x.get("wa_link") or x.get("blocked_code") == "no_phone" for x in rows),
          "D12 tiap kandidat punya tautan wa.me — atau alasan jujur kenapa tidak bisa")
    r = requests.get(f"{API}/reminders/settings", headers=su, timeout=30)
    cfgr = ((r.json() or {}).get("data") or {})
    check("arrears_min_amount" in cfgr and "arrears_min_months" in cfgr
          and "arrears_every_days" in cfgr,
          "D13 layar pengingat membaca rem nominal & aturan dari server (bukan angka mati)")


def main():
    print("=" * 78)
    print("GATE 59 — Fase 68: denda terjadwal + pengingat tunggakan pra-SP")
    print("=" * 78)
    bagian_kode()
    bagian_ui()
    bagian_perilaku()
    print("\n" + "-" * 78)
    if fails:
        print(f"GATE 59 MERAH — {len(fails)} gagal / {ok + len(fails)} pemeriksaan")
        for f in fails:
            print("  -", f)
        sys.exit(1)
    print(f"GATE 59 HIJAU — {ok} pemeriksaan")


if __name__ == "__main__":
    main()
