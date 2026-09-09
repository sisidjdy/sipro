#!/usr/bin/env python3
"""verify_p59.py — GATE 50: laporan keringanan denda, kandidat tunggakan, utang refund.

Tiga utang Fase 58 dibayar Fase 59. Gate ini menjaga agar ketiganya tidak bisa dilumpuhkan
tanpa membuat berkas ini merah:

  K — KODE: satu sumber angka (laporan membaca baris denda yang sama dengan jurnal), mesin
      tunggakan MENGUSULKAN dan tidak pernah membatalkan, jatuh tempo refund dibaca dari
      Pusat Konfigurasi, dan yang tertahan SPR tidak diberi tanggal karangan.
  K-UI — LAYAR: panel & testId benar-benar dirender (bukan komponen mati), ekspor CSV & PDF
      ada di layar keringanan, dan halaman Keuangan punya tab-nya.
  D — PERILAKU (server hidup): endpoint menjawab bentuk yang dijanjikan, pemisahan tugas
      dipaksakan (yang MENITIPKAN tugas tunggakan = Manajer Keuangan), lingkup baris sales
      dihormati, sweep IDEMPOTEN, dan laporan utang refund cocok dengan buku besar.

Jalankan: python3 scripts/verify_p59.py
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
        return True
    fails.append(label)
    print(f"  GAGAL {label}" + (f" — {detail}" if detail else ""))
    return False


def head(t):
    print(f"\n{t}\n" + "-" * len(t))


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="ignore") if p.exists() else ""


def fungsi(src: str, name: str) -> str:
    """Ambil satu fungsi (sampai def berikutnya di kolom 0) — pemeriksaan per fungsi."""
    m = re.search(rf"^(async def|def) {re.escape(name)}\(", src, re.M)
    if not m:
        return ""
    rest = src[m.start():]
    nxt = re.search(r"^(async def|def) ", rest[10:], re.M)
    return rest[:nxt.start() + 10] if nxt else rest


def login(email: str) -> str:
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": PASSWORD},
                      timeout=20)
    r.raise_for_status()
    return r.json()["access_token"]


def hdr(tok: str) -> dict:
    return {"Authorization": f"Bearer {tok}"}


# ============================================================ K. kode
def bagian_k():
    head("K. Kode: satu sumber angka, mengusulkan bukan membatalkan")
    lfr = read(BE / "late_fee_report.py")
    arr = read(BE / "arrears_engine.py")
    rd = read(BE / "refund_debt.py")
    rt = read(BE / "routers" / "p59_router.py")
    ref59 = read(BE / "reference_p59.py")
    st = read(BE / "settings_store.py")
    sch = read(BE / "scheduler_p59.py")

    w = fungsi(lfr, "waivers")
    check('it.get("waived_amount")' in w and 'it.get("waived_reason")' in w,
          "K1 laporan keringanan membaca NOMINAL & ALASAN dari baris denda (bukan hitung ulang)")
    check('it.get("waived_by")' in w and 'it.get("waived_at")' in w
          and 'it.get("waiver_journal_id")' in w,
          "K2 siapa & kapan & jurnal baliknya ikut dilaporkan (bisa diaudit)")
    check("by_actor" in w and "amount" in w,
          "K3 rekapitulasi per PEMBERI keputusan ada (pertanyaan rapat direksi)")
    check("own_email" in w and 'query["assigned_to"] = own_email' in w,
          "K4 lingkup baris sales dipaksa SERVER, bukan disaring peramban")
    check("await lfr.waivers(" in rt or "lfr.waivers(" in rt,
          "K5 endpoint laporan memakai mesin laporan (tidak ada kueri kedua di router)")

    m = fungsi(arr, "months_in_arrears")
    check("by_terms" in m and "// 30" in m and "max(by_terms, by_days)" in m,
          "K6 tunggakan dihitung akumulatif DAN berurutan (SPR menyebut keduanya)")
    check('r["state"] == "terlambat"' in m,
          "K7 hanya termin LEWAT TOLERANSI yang dihitung menunggak (bukan H+1)")
    c = fungsi(arr, "candidates")
    check("KEY_THRESHOLD" in c and "cfg.get" in c,
          "K8 ambang bulan dibaca Pusat Konfigurasi (bukan angka mati di kode)")
    check("cx.blocks(" in c,
          "K9 setiap baris menyebut penghalang pengajuan (bukan tombol mati)")
    sw = fungsi(arr, "sweep")
    check("auto_create_task(" in sw and "arrears_review:" in sw,
          "K10 sweep hanya MENITIPKAN TUGAS, idempoten per (kontrak, bulan)")
    check("cx.request(" not in arr and "cx.decide(" not in arr
          and "_release_unit" not in arr,
          "K10b mesin tunggakan TIDAK PERNAH mengajukan/memutuskan/melepas unit sendiri")
    check("arrears_review_tick" in sch and "cron" in sch and "decide" not in sch,
          "K10c penjadwal harian pun hanya menerbitkan tugas peninjauan")

    r = fungsi(rd, "report")
    check("KEY_DUE_DAYS" in r and "timedelta(days=due_days)" in r,
          "K11 jatuh tempo refund = keputusan + ambang Pusat Konfigurasi")
    check('(d + timedelta(days=due_days)) if (d and not tertahan) else None' in r,
          "K12 refund yang TERTAHAN ketentuan SPR tidak diberi tanggal karangan")
    check("unscheduled" in r and "unscheduled_note" in rd,
          "K12b yang belum bisa dijadwalkan tetap dihitung & disebutkan sebabnya")
    check("_bucket(" in r and "refund_age_bucket" in rd,
          "K13 umur utang dipakai (bucket), dihitung dari tanggal KEPUTUSAN")
    check("gl.account_balances" in r and '"difference": gl_balance - total' in r,
          "K14 laporan diuji cocok dengan SALDO BUKU BESAR 2-1460 (bisa salah = bisa diperiksa)")
    check("cancellation.refund_due_days" in st,
          "K15 ambang jatuh tempo refund terdaftar di Pusat Konfigurasi (berjejak)")

    for grup in ("arrears_stage", "refund_due_state", "refund_age_bucket"):
        check(f'"{grup}"' in ref59, f"K16 kamus data `{grup}` terdaftar (layar tidak mengarang)")
    check('require_permission("cancellation", "approve")' in rt
          and 'require_permission("late_fee", "view")' in rt
          and 'require_permission("finance", "view")' in rt,
          "K17 izin per endpoint: menitipkan tugas ≠ membaca laporan")


# ============================================================ K-UI. layar
def bagian_kui():
    head("K-UI. Layar: panel benar-benar dirender, ekspor ada")
    wr = read(FE / "components" / "finance" / "LateFeeWaiverReport.js")
    ar = read(FE / "components" / "finance" / "ArrearsCandidatesPanel.js")
    rp = read(FE / "components" / "finance" / "RefundDebtPanel.js")
    panel = read(FE / "components" / "finance" / "LateFeePanel.js")
    fin = read(FE / "pages" / "FinancePage.js")
    cx = read(FE / "components" / "finance" / "CancellationsPanel.js")
    ids = read(FE / "constants" / "testIds" / "p59.js")
    idx = read(FE / "constants" / "testIds" / "index.js")

    check("P59.waiverPanel" in wr and "/finance/late-fee-waivers" in wr,
          "K18 laporan keringanan memanggil endpointnya & bertanda testId")
    check("downloadCsv(" in wr and "late-fee-waivers/pdf" in wr,
          "K19 ekspor CSV DAN PDF tersedia di layar keringanan (untuk rapat direksi)")
    check("waiverActorRow" in wr, "K19b rekapitulasi per pemberi keputusan tampil di layar")
    check("LateFeeWaiverReport" in panel and "P59.waiverTabReport" in panel,
          "K20 tab 'Riwayat keringanan' hidup di panel denda (Rencana Bayar)")
    check("LateFeeWaiverReport" in fin and 'key: "waivers"' in fin,
          "K20b laporan yang sama bisa dibuka dari halaman Keuangan (satu komponen)")
    check("ArrearsCandidatesPanel" in cx and "P59.arrearsPanel" in ar,
          "K21 kandidat tunggakan dirender di tab Pembatalan & Refund")
    check("arrearsSweepBtn" in ar and 'can("cancellation", "approve")' in ar,
          "K21b tombol 'Buat tugas peninjauan' hanya untuk yang berwenang")
    check('api.post("/cancellations' not in ar and "/decision" not in ar
          and "/refund" not in ar and ar.count("api.post(") == 1,
          "K21c layar kandidat tidak punya jalan MEMBATALKAN sendiri "
          "(satu-satunya POST = menitipkan tugas peninjauan)")
    check("RefundDebtPanel" in fin and 'key: "refund-debt"' in fin,
          "K22 tab 'Utang Refund' ada di halaman Keuangan")
    check("refundLedger" in rp and "refundUnscheduled" in rp and "refundProjection" in rp,
          "K22b layar utang refund menampilkan uji cocok GL, proyeksi, & yang tertahan")
    check("belum bisa dijadwalkan" in rp,
          "K22c refund tertahan ditulis 'belum bisa dijadwalkan', bukan tanggal/Rp 0 palsu")
    dipakai = set(re.findall(r"P59\.(\w+)", wr + ar + rp + panel + fin))
    terdaftar = set(re.findall(r"^\s{2}(\w+):", ids, re.M))
    mati = terdaftar - dipakai
    check(not mati, "K23 tidak ada testId Fase 59 yang MATI (terdaftar tapi tak dipakai)",
          f"mati: {sorted(mati)}")
    check("./p59" in idx, "K23b testId Fase 59 diekspor dari registry pusat")


# ============================================================ D. perilaku
def bagian_d():
    head("D. Perilaku: server hidup, pemisahan tugas & idempotensi")
    try:
        fin = login("finance@sipro.co.id")
        lead = login("finlead@sipro.co.id")
        sales = login("sales@sipro.co.id")
    except Exception as e:  # noqa: BLE001
        check(False, "D0 login peran uji", str(e))
        return

    r = requests.get(f"{API}/finance/late-fee-waivers", headers=hdr(lead), timeout=60)
    check(r.status_code == 200 and {"rows", "by_actor", "totals", "note"}
          <= set((r.json().get("data") or {}).keys()),
          "D1 laporan keringanan menjawab bentuk yang dijanjikan", r.text[:160])
    r2 = requests.get(f"{API}/finance/late-fee-waivers",
                      params={"date_from": "2099-01-01"}, headers=hdr(lead), timeout=60)
    check(r2.status_code == 200 and (r2.json()["data"]["totals"]["count"] == 0),
          "D2 saringan periode benar-benar menyaring (2099 = kosong)")
    rp = requests.get(f"{API}/finance/late-fee-waivers/pdf", headers=hdr(lead), timeout=90)
    check(rp.status_code == 200 and rp.content[:4] == b"%PDF",
          "D3 PDF laporan keringanan benar-benar berkas PDF", rp.text[:120])

    rc = requests.get(f"{API}/finance/arrears/candidates", headers=hdr(lead), timeout=120)
    check(rc.status_code == 200, "D4 kandidat tunggakan bisa dibaca Manajer Keuangan")
    data = rc.json().get("data") or {}
    check(int(data.get("threshold_months") or 0) >= 1,
          "D4b ambang bulan disebutkan (dari Pusat Konfigurasi)")
    baris = data.get("rows") or []
    check(all(r.get("stage") in ("aman", "perhatian", "kandidat_batal") for r in baris),
          "D4c setiap baris memakai kode kamus `arrears_stage`")
    check(all("rule_note" in r and r.get("blocks") is not None for r in baris),
          "D4d setiap baris menyebut ATURAN & penghalangnya")

    rs = requests.post(f"{API}/finance/arrears/sweep", headers=hdr(fin), json={}, timeout=60)
    check(rs.status_code == 403,
          "D5 Keuangan (bukan Manajer Keuangan) TIDAK boleh menitipkan tugas tunggakan",
          f"status {rs.status_code}")
    s1 = requests.post(f"{API}/finance/arrears/sweep", headers=hdr(lead), json={}, timeout=120)
    check(s1.status_code == 200, "D6 Manajer Keuangan bisa menitipkan tugas peninjauan",
          s1.text[:160])
    if s1.status_code == 200:
        s2 = requests.post(f"{API}/finance/arrears/sweep", headers=hdr(lead), json={},
                           timeout=120)
        check(s2.status_code == 200 and not (s2.json()["data"]["created"]),
              "D7 sweep kedua BUKAN tumpukan tugas kembar (idempoten per bulan)")

    rr = requests.get(f"{API}/finance/refund-debt", headers=hdr(fin), timeout=120)
    check(rr.status_code == 200, "D8 laporan utang refund bisa dibaca Keuangan")
    if rr.status_code == 200:
        d = rr.json()["data"]
        led = d.get("ledger") or {}
        check(led.get("account_code") == "2-1460" and "balance" in led,
              "D8b laporan menyandingkan dirinya dengan saldo akun 2-1460")
        check(led.get("worksheet") == d["totals"]["outstanding"],
              "D8c jumlah dokumen = total yang dilaporkan (tidak ada dua angka)")
        check(led.get("matched") is True,
              "D8d saldo buku besar COCOK dengan sisa refund dokumen",
              f"selisih {led.get('difference')}")
        semua = sum(p["outflow"] for p in d["projection"]["periods"]) \
            + d["projection"]["unscheduled"]
        check(semua == d["totals"]["outstanding"],
              "D9 proyeksi kas + yang belum bisa dijadwalkan = seluruh kewajiban "
              "(tidak ada rupiah yang hilang dari rencana)")
    rpdf = requests.get(f"{API}/finance/refund-debt/pdf", headers=hdr(fin), timeout=120)
    check(rpdf.status_code == 200 and rpdf.content[:4] == b"%PDF",
          "D10 PDF laporan utang refund benar-benar PDF")

    rsa = requests.get(f"{API}/finance/late-fee-waivers", headers=hdr(sales), timeout=60)
    check(rsa.status_code == 200
          and (rsa.json()["data"]["filter"]["scoped_to"] == "sales@sipro.co.id"),
          "D11 sales membaca laporan yang SUDAH dipersempit server ke transaksinya")
    rsc = requests.get(f"{API}/finance/refund-debt", headers=hdr(sales), timeout=60)
    check(rsc.status_code == 403,
          "D12 sales tidak boleh membaca utang refund organisasi",
          f"status {rsc.status_code}")


def main():
    print("=" * 78)
    print("GATE 50 — Fase 59: laporan keringanan, kandidat tunggakan, utang refund")
    print("=" * 78)
    bagian_k()
    bagian_kui()
    bagian_d()
    print("\n" + "-" * 78)
    if fails:
        print(f"GATE 50 MERAH — {len(fails)} gagal / {ok + len(fails)} pemeriksaan")
        for f in fails:
            print("  -", f)
        sys.exit(1)
    print(f"GATE 50 HIJAU — {ok} pemeriksaan")


if __name__ == "__main__":
    main()
