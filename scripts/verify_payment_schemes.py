#!/usr/bin/env python3
"""verify_payment_schemes.py — GATE 48 (Fase 57A): termin pembayaran WAJIB tetap bisa
dikonfigurasi pemakai, dan skema yang tidak menagih seluruh harga WAJIB ditolak.

## Kenapa gate ini ada

Sampai Fase 56 termin `cash keras / cash bertahap / KPR` disusun di dalam KODE. Untuk produk
SaaS itu berarti setiap pengembang dengan kebiasaan berbeda (DP nominal, 12× cicilan,
pelunasan menyusul AJB) harus menunggu rilis. Fase 57A memindahkannya menjadi DATA.

Yang dijaga di sini — dan tidak bisa dijaga oleh uji perilaku biasa:

  * **Satu mesin termin.** Nominal per termin tetap dihitung `finance_engine.compute_scheme_items`
    (fungsi yang sama dengan yang menagih). Kalau layar/mesin skema mulai menghitung sendiri,
    yang dijanjikan di penawaran akan berbeda dari yang ditagihkan.
  * **Jumlah termin = harga jual.** Skema 95% (sisa 5% tidak pernah tertagih) DITOLAK, bukan
    disimpan diam-diam. Ini kelas kesalahan yang baru terlihat saat tutup buku.
  * **Kalimat jatuh tempo disusun MESIN.** Pembeli membacanya di dokumen SPR; kalimat yang
    diketik bebas bisa menjanjikan aturan yang berbeda dari yang ditagihkan.
  * **Tanggal yang belum pasti diakui belum pasti** (`event_based`).
  * **Skema bawaan tidak menimpa suntingan pemakai** — cacat kelas ini pernah ada: setiap
    aktivasi kontrak menulis ulang termin dari termin bawaan.
  * **Jenis skema tetap jujur**: akad kredit/biaya bank hanya pada jenis KPR.
  * **Skema kontrak beruang tidak boleh diganti diam-diam** (jadwal yang sudah dibayar
    sebagian ditulis ulang tanpa jejak).

Jalankan: python3 scripts/verify_payment_schemes.py
"""
import pathlib
import re
import sys
import time

import requests

ROOT = pathlib.Path(__file__).resolve().parent.parent
BE = ROOT / "backend"
FE = ROOT / "frontend" / "src"
BASE = "http://localhost:8001/api"
PW = "Sipro#2026"
FAIL = []
PASSED = 0


def check(ok: bool, label: str, detail: str = "") -> bool:
    global PASSED
    if ok:
        PASSED += 1
        print(f"  OK    {label}")
    else:
        FAIL.append(label)
        print(f"  MERAH {label} — {detail}")
    return bool(ok)


def head(t: str) -> None:
    print(f"\n{t}\n" + "-" * len(t))


def read(p: pathlib.Path) -> str:
    return p.read_text(encoding="utf-8", errors="ignore") if p.exists() else ""


def strip_comments(src: str) -> str:
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    src = re.sub(r'"""(?:.|\n)*?"""', "", src)
    return "\n".join(ln for ln in src.split("\n")
                     if not ln.strip().startswith(("//", "#")))


def fungsi(src: str, nama: str) -> str:
    m = re.search(rf"^(?:async )?def {re.escape(nama)}\(", src, re.M)
    if not m:
        return ""
    ekor = src[m.end():]
    m2 = re.search(r"^(?:async def |def |class )", ekor, re.M)
    return src[m.start(): m.end() + (m2.start() if m2 else len(ekor))]


def opsi_kamus(ref_src: str, grup: str) -> set:
    m = re.search(rf'"{grup}":\s*\{{', ref_src)
    if not m:
        return set()
    seg = ref_src[m.end():].split("\n    },")[0]
    return set(re.findall(r'_o\("([a-z_0-9]+)"', seg))


def j(r):
    try:
        return r.json()
    except Exception:  # noqa: BLE001
        return {}


def d(r) -> str:
    return f"HTTP {r.status_code} {str(j(r))[:200]}"


def login(email: str) -> dict:
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": PW}, timeout=30)
    if r.status_code != 200:
        raise SystemExit(f"login {email} gagal: {d(r)}")
    return {"Authorization": f"Bearer {j(r)['access_token']}"}


# ============================================================ K. tingkat KODE
def bagian_k():
    head("K. Kode: konfigurasi termin tidak boleh bisa dilumpuhkan tanpa gate ini merah")
    psx = strip_comments(read(BE / "payment_scheme_engine.py"))
    fin = strip_comments(read(BE / "finance_engine.py"))
    cx = strip_comments(read(BE / "contracts_engine.py"))
    router = read(BE / "routers" / "payment_scheme_router.py")
    models = strip_comments(read(BE / "models_p57.py"))
    ref57 = read(BE / "reference_p57.py")

    sim = fungsi(psx, "simulate")
    check("fin.compute_scheme_items(" in sim,
          "K1 pratinjau memakai MESIN TERMIN YANG SAMA dengan penagihan (bukan rumus kedua)")
    hit = fungsi(fin, "compute_scheme_items")
    check('basis == "remaining"' in hit and 'int(price) - sum(x["amount"] for x in out)' in hit,
          "K2 dasar 'sisa harga' dihitung dari harga − termin lain (menutup selisih tanpa "
          "mengarang)")
    due = fungsi(fin, "_due_date")
    check('mode == "monthly_day"' in due and "min(int(t.get(\"due_day\") or 1), 28)" in due,
          "K3 jatuh tempo bulanan memakai tanggal yang dikonfigurasi (dibatasi 28)")

    blk = fungsi(psx, "blocks")
    check('abs(pct - 100) > 0.01' in blk and "persen_bukan_100" in blk,
          "K4 skema yang jumlah persennya bukan 100% DITOLAK (bagian harga tidak tertagih)")
    check("sisa_bukan_terakhir" in blk and "sisa_ganda" in blk,
          "K4b termin 'sisa harga' hanya satu dan wajib paling akhir")
    check("nominal_tanpa_sisa" in blk,
          "K4c campuran nominal tanpa termin 'sisa harga' ditolak")
    check("nilai_tidak_wajar" in blk,
          "K4d termin bernilai nol/negatif ditolak (tagihan yang tidak menagih)")
    kode_blk = set(re.findall(r'_blk\("([a-z_0-9]+)"', psx))
    check(bool(kode_blk) and kode_blk <= opsi_kamus(ref57, "scheme_block"),
          "K5 setiap sebab penolakan terdaftar di Kamus Data",
          f"tak terdaftar: {sorted(kode_blk - opsi_kamus(ref57, 'scheme_block'))}")

    kal = fungsi(psx, "due_sentence")
    check("ref.label_of(\"term_due_event\"" in kal and "masih perkiraan" in kal,
          "K6 kalimat jatuh tempo DISUSUN MESIN & mengakui tanggal peristiwa masih perkiraan")
    norm = fungsi(psx, "normalize_terms")
    check('row["due_rule"] = due_sentence(row)' in norm and '"event"' in norm,
          "K6b setiap termin membawa kalimat aturan + penanda berbasis peristiwa")
    check("due_rule" not in models,
          "K6c pemakai TIDAK bisa mengirim kalimat aturannya sendiri (model menolaknya)")

    ens = fungsi(cx, "ensure_payment_scheme")
    check("if doc:\n        return doc" in ens,
          "K7 skema yang sudah ada TIDAK ditimpa termin bawaan saat kontrak diaktifkan")
    spec = fungsi(cx, "scheme_terms_spec")
    check("psx.resolve_for_contract(" in spec and '"configurable": True' in spec,
          "K7b termin kontrak dibaca dari skema TERSIMPAN, bawaan hanya jaring terakhir")
    res = fungsi(psx, "resolve_for_contract")
    check('"reason":' in res and "Belum ada skema pembayaran aktif" in res,
          "K7c bila tak ada skema cocok, sebabnya DIKATAKAN (bukan termin karangan)")

    simpan = fungsi(psx, "save")
    check("_contracts_with_money(" in simpan and "skema BARU" in simpan,
          "K8 skema yang dipakai kontrak BERUANG tidak bisa diubah termin-nya diam-diam")
    setk = fungsi(psx, "set_for_contract")
    check('doc.get("kind") != contract.get("scheme")' in setk,
          "K9 jenis skema wajib sama dengan jenis kontrak (akad kredit tidak muncul di tunai)")
    check("applies_project_ids" in setk and "tidak berlaku untuk proyek" in setk,
          "K9b skema yang tidak berlaku di proyek kontrak ditolak")
    check('"funding": {"$ne": "deposit"}' in setk and "adendum" in setk,
          "K9c kontrak yang sudah ada penerimaan KAS nyata tidak boleh ganti skema (wajib adendum); "
          "booking fee yang dialihkan otomatis (funding=deposit) bukan penghalang")
    check("create_ar_for_deal(" in setk and "replace=True" in setk,
          "K9d ganti skema kontrak menyusun ulang AR (SPR = skema = piutang)")
    check('require_permission("payment_scheme", "assign")' in router
          and 'require_permission("payment_scheme", "create")' in router,
          "K10 menyusun skema dan MENETAPKANNYA pada kontrak memakai izin yang berbeda")
    check("MIN_REASON = 10" in models and "alasan penggantian skema" in models,
          "K10b penggantian skema kontrak wajib beralasan (jadwal orang lain berubah)")
    check("1 <= int(v) <= 28" in models,
          "K11 tanggal jatuh tempo bulanan dibatasi 1–28 (Februari tidak membuat meleset)")
    gen = fungsi(psx, "build_installments")
    check("percent_total) - per * (count - 1)" in gen,
          "K12 sisa pembulatan cicilan dipikul baris terakhir (jumlah persen tetap tepat)")

    # -------------------------------------------------------------- layar
    ids = read(FE / "constants" / "testIds" / "p57.js")
    panel = read(FE / "components" / "config" / "PaymentSchemePanel.js")
    page = read(FE / "pages" / "ConfigCenterPage.js")
    picker = read(FE / "components" / "contracts" / "ContractSchemePicker.js")
    kontrak = read(FE / "components" / "contracts" / "ContractPanel.js")
    layar = panel + page + picker + kontrak

    check("<PaymentSchemePanel />" in page and 'value="scheme"' in page,
          "K13 tab 'Skema Pembayaran' DIRENDER di Pusat Konfigurasi")
    check("<ContractSchemePicker contract={contract}" in kontrak,
          "K13b skema yang dipakai kontrak TERLIHAT di layar Kontrak & Legal")
    mati = [n for n, t in re.findall(r"(\w+):\s*\"([a-z0-9-]+)\"", ids)
            if f'"{t}"' not in layar and f"P57.{n}" not in layar]
    check(not mati, "K14 tidak ada testId Fase 57 yang MATI", str(mati))
    check('group="term_basis"' in panel and 'group="term_due_mode"' in panel
          and 'group="term_due_event"' in panel and 'group="payment_scheme_kind"' in panel,
          "K15 semua pilihan pada editor berasal dari Kamus Data (bukan diketik layar)")
    check("/payment-schemes/simulate" in panel and "previewRow" in panel,
          "K16 layar menampilkan PRATINJAU jadwal sebelum skema menagih pembeli sungguhan")
    check("disabled={!!(preview?.blocks || []).length}" in panel,
          "K16b tombol simpan mati selama pratinjau masih menyebut sebab penolakan")
    check("t.due_rule ||" in panel and "due_rule" not in panel.split("const KOSONG")[0],
          "K16c layar MENAMPILKAN kalimat aturan dari server, tidak mengarangnya")
    check("Beri nama setiap termin dahulu" in panel and "belum diberi nama" in panel,
          "K16d termin yang masih diisi dikatakan 'belum diberi nama' (bukan galat teknis "
          "berisi jalur field seperti `terms.0.label`)")
    check("asal:" in picker and "termin bawaan" in picker,
          "K17 layar mengaku bila kontrak masih memakai termin BAWAAN sistem")
    check("Sudah ada penerimaan pada kontrak ini" in picker,
          "K17b layar menyebutkan sebab skema tidak bisa diganti (bukan tombol diam)")


# ============================================================ D. perilaku HTTP
def bagian_d():  # noqa: C901
    head("D. Perilaku: skema disusun pemakai, dipakai kontrak, dan menolak yang tidak jujur")
    sa = login("superadmin@sipro.co.id")
    fin = login("finance@sipro.co.id")
    finlead = login("finlead@sipro.co.id")
    tanda = str(int(time.time()))[-6:]
    dibuat = []

    r = requests.get(f"{BASE}/payment-schemes", headers=sa, timeout=30)
    rows = j(r).get("data") or []
    check(r.status_code == 200 and len(rows) >= 3,
          "D1 skema bawaan tersedia sebagai DATA yang bisa disunting", d(r))
    kinds = {x.get("kind") for x in rows}
    check({"cash_keras", "cash_bertahap", "kpr"} <= kinds,
          "D1b ketiga jenis skema punya barisnya sendiri", str(sorted(kinds)))
    check(all(t.get("due_rule") for x in rows for t in (x.get("terms") or [])),
          "D1c setiap termin membawa kalimat aturan jatuh tempo")

    tolak = requests.post(f"{BASE}/payment-schemes", headers=sa, json={
        "name": f"POC57 Timpang {tanda}", "kind": "cash_keras",
        "terms": [{"label": "DP 80%", "basis": "percent", "value": 80},
                  {"label": "Pelunasan 15%", "basis": "percent", "value": 15}]}, timeout=30)
    check(tolak.status_code == 400 and "100%" in str(j(tolak).get("detail")),
          "D2 skema 95% DITOLAK — 5% harga rumah tidak boleh tidak tertagih", d(tolak))
    tolak = requests.post(f"{BASE}/payment-schemes", headers=sa, json={
        "name": f"POC57 Nominal {tanda}", "kind": "cash_bertahap",
        "terms": [{"label": "DP nominal", "basis": "amount", "value": 50000000}]}, timeout=30)
    check(tolak.status_code == 400 and "sisa harga" in str(j(tolak).get("detail")),
          "D2b nominal tanpa termin 'sisa harga' ditolak", d(tolak))
    tolak = requests.post(f"{BASE}/payment-schemes", headers=sa, json={
        "name": f"POC57 Sisa awal {tanda}", "kind": "cash_bertahap",
        "terms": [{"label": "Sisa harga", "basis": "remaining", "value": 0},
                  {"label": "DP 20%", "basis": "percent", "value": 20}]}, timeout=30)
    check(tolak.status_code == 400 and "paling akhir" in str(j(tolak).get("detail")),
          "D2c termin 'sisa harga' wajib paling akhir", d(tolak))
    tolak = requests.post(f"{BASE}/payment-schemes", headers=sa, json={
        "name": f"POC57 Sisa ganda {tanda}", "kind": "cash_bertahap",
        "terms": [{"label": "DP 20%", "basis": "percent", "value": 20},
                  {"label": "Sisa A", "basis": "remaining", "value": 0},
                  {"label": "Sisa B", "basis": "remaining", "value": 0}]}, timeout=30)
    check(tolak.status_code == 400 and "SATU termin" in str(j(tolak).get("detail")),
          "D2e dua termin 'sisa harga' ditolak (yang kedua akan selalu Rp 0)", d(tolak))
    tolak = requests.post(f"{BASE}/payment-schemes", headers=sa, json={
        "name": f"POC57 Nol {tanda}", "kind": "cash_bertahap",
        "terms": [{"label": "DP 100%", "basis": "percent", "value": 100},
                  {"label": "Termin kosong", "basis": "percent", "value": 0}]}, timeout=30)
    check(tolak.status_code == 400
          and "lebih besar dari nol" in str(j(tolak).get("detail")),
          "D2f termin bernilai nol ditolak (tagihan yang tidak menagih apa pun)", d(tolak))
    tolak = requests.post(f"{BASE}/payment-schemes", headers=sa, json={
        "name": f"POC57 Tanggal 31 {tanda}", "kind": "cash_bertahap",
        "terms": [{"label": "Cicilan", "basis": "percent", "value": 100,
                   "due_mode": "monthly_day", "due_day": 31}]}, timeout=30)
    check(tolak.status_code in (400, 422) and "1–28" in str(j(tolak).get("detail")),
          "D2d tanggal jatuh tempo 31 ditolak (Februari membuat tagihan meleset)", d(tolak))

    gen = requests.post(f"{BASE}/payment-schemes/installments", headers=sa, json={
        "count": 12, "percent_total": 20, "start_month": 1, "due_day": 10,
        "grace_days": 5}, timeout=30)
    cicilan = j(gen).get("data") or []
    check(gen.status_code == 200 and len(cicilan) == 12
          and abs(sum(c["value"] for c in cicilan) - 20) < 0.001,
          "D3 pembantu 'buat 12 cicilan' membagi persen tepat (sisa pembulatan di akhir)",
          str(sum(c["value"] for c in cicilan) if cicilan else None))
    check(all(c["due_rule"] == "tanggal 10 setiap bulan · toleransi 5 hari" for c in cicilan),
          "D3b kalimat aturan cicilan mengikuti konfigurasi (tanggal & toleransi)",
          str(cicilan[0]["due_rule"] if cicilan else None))

    terms = ([{"label": "DP nominal", "basis": "amount", "value": 50000000,
               "due_mode": "offset_days", "due_offset_days": 0}]
             + cicilan
             + [{"label": "Pelunasan sisa", "basis": "remaining", "value": 0,
                 "due_mode": "event", "event_code": "build_complete",
                 "due_offset_days": 30, "grace_days": 7}])
    sim = requests.post(f"{BASE}/payment-schemes/simulate", headers=sa, json={
        "price": 850000000, "terms": terms}, timeout=30)
    s = j(sim).get("data") or {}
    check(sim.status_code == 200 and s.get("balanced") is True
          and s["rows"][0]["amount"] == 50000000,
          "D4 pratinjau: DP nominal + 12 cicilan + sisa = TEPAT harga jual",
          f"{s.get('total')} vs {s.get('price')}")
    check(s["rows"][-1]["event_based"] is True
          and "perkiraan" in str(s["rows"][-1]["due_rule"]),
          "D4b termin peristiwa ditandai perkiraan (tanggalnya belum pasti)")
    tgl = [r["due_date"][:10] for r in s["rows"][1:4]]
    check(all(t.endswith("-10") for t in tgl),
          "D4c tanggal cicilan mengikuti tanggal yang dikonfigurasi", str(tgl))

    # Kontrak uji DIBUAT SENDIRI (belum ada penerimaan). Menumpang kontrak demo membuat
    # gate bergantung pada kebetulan data — dan kontrak demo yang sudah dibayar tidak boleh
    # dipakai untuk menguji penggantian skema.
    ctrs = j(requests.get(f"{BASE}/contracts", headers=sa,
                          params={"limit": 50}, timeout=30)).get("data") or []
    jenis = "cash_bertahap"
    target = None
    lead = j(requests.post(f"{BASE}/leads", headers=sa, json={
        "name": f"POC57 Gate Bapak Uji {tanda}", "phone": f"+62813{tanda}57",
        "source": "walk_in", "notes": "bahan uji gate 48"}, timeout=30)).get("data") or {}
    units = [u for u in (j(requests.get(f"{BASE}/units", headers=sa, params={
        "status": "available", "limit": 30}, timeout=30)).get("data") or [])]
    # Unit yang SUDAH punya jadwal pembangunan tidak boleh dipakai bahan uji: booking &
    # pembersihannya menyentuh jadwal milik cerita demo unit itu (mis. "unit telat" Fase 46),
    # dan gate lain akan merah karena bahan uji fase ini — bukan karena produknya salah.
    units = [u for u in units if u["id"] not in _units_with_schedule()]
    if lead.get("id") and units:
        unit = units[0]
        deal = (j(requests.post(f"{BASE}/deals/reserve", headers=sa, json={
            "lead_id": lead["id"], "unit_id": unit["id"], "booking_fee": 5000000,
            "notes": "gate 48"}, timeout=30)).get("data") or {})
        requests.post(f"{BASE}/booking-fee/deals/{deal.get('id')}/pay", headers=sa, timeout=30,
                      json={"amount": 5000000, "method": "transfer"})
        requests.post(f"{BASE}/deals/{deal.get('id')}/book", headers=sa, json={}, timeout=30)
        cv = j(requests.post(f"{BASE}/deals/{deal.get('id')}/convert", headers=sa, json={
            "scheme": jenis, "nik": f"3299{tanda}000057",
            "address": "Jl. Gate 48 No. 1"}, timeout=30)).get("data") or {}
        cid = (cv.get("contract") or {}).get("id")
        if cid:
            target = j(requests.get(f"{BASE}/contracts/{cid}", headers=sa,
                                    timeout=30)).get("data") or None
    buat = requests.post(f"{BASE}/payment-schemes", headers=sa, json={
        "name": f"POC57 DP nominal + 12 cicilan {tanda}", "kind": jenis,
        "terms": terms}, timeout=30)
    doc = j(buat).get("data") or {}
    if not check(buat.status_code == 200 and len(doc.get("terms") or []) == 14,
                 "D5 skema buatan pemakai tersimpan (14 termin)", d(buat)):
        return dibuat
    dibuat.append(doc["id"])
    check(doc.get("code") and doc.get("kind") == "cash_bertahap",
          "D5b skema tersimpan berkode & berjenis", str(doc.get("code")))
    kembar = requests.post(f"{BASE}/payment-schemes", headers=sa, json={
        "name": f"POC57 DP nominal + 12 cicilan {tanda}", "kind": jenis,
        "terms": terms}, timeout=30)
    check(kembar.status_code == 400 and "sudah dipakai" in str(j(kembar).get("detail")),
          "D5c kode skema kembar ditolak", d(kembar))
    if kembar.status_code == 200:
        dibuat.append((j(kembar).get("data") or {}).get("id"))

    r = requests.get(f"{BASE}/payment-schemes", headers=fin, timeout=30)
    check(r.status_code == 200, "D6 Keuangan boleh MELIHAT skema", d(r))
    r = requests.post(f"{BASE}/payment-schemes", headers=fin, json={
        "name": f"POC57 Tanpa wewenang {tanda}", "kind": "kpr",
        "terms": [{"label": "Pencairan", "basis": "percent", "value": 100}]}, timeout=30)
    check(r.status_code == 403, "D6b kasir Keuangan TIDAK boleh menyusun skema", d(r))

    if target:
        # Booking fee (5jt) sudah DIALIHKAN otomatis ke termin saat AR lahir — itu bukan cicilan
        # atas jadwal ini, jadi skema masih boleh diganti: AR disusun ulang & titipan dialokasikan
        # ulang ke termin baru. Penerimaan kas nyata yang menolak (D7f).
        ar0 = j(requests.get(f"{BASE}/finance/ar/{deal.get('id')}", headers=fin,
                             timeout=30)).get("data") or {}
        paid0 = int(ar0.get("paid") or 0)
        r = requests.post(f"{BASE}/payment-schemes/contracts/{target['id']}", headers=finlead,
                          json={"scheme_id": doc["id"], "reason": "uji gate 48 skema baru"},
                          timeout=30)
        check(r.status_code == 200, "D7 Manajer Keuangan menetapkan skema pada kontrak "
                                    "(booking fee yang dialihkan otomatis tidak menghalangi)", d(r))
        det = j(requests.get(f"{BASE}/contracts/{target['id']}", headers=sa,
                             timeout=30)).get("data") or {}
        dipakai = ((det.get("payment_plan") or {}).get("scheme") or {})
        check(dipakai.get("id") == doc["id"] and dipakai.get("source") == "kontrak",
              "D7b rencana bayar kontrak MENYEBUT skema yang dipilih & asalnya", str(dipakai))
        check(len((det.get("payment_plan") or {}).get("rules") or []) == 14,
              "D7c aturan termin di layar mengikuti skema pilihan (14 baris)",
              str(len((det.get("payment_plan") or {}).get("rules") or [])))
        ar1 = j(requests.get(f"{BASE}/finance/ar/{deal.get('id')}", headers=fin,
                             timeout=30)).get("data") or {}
        unit_items = [i for i in (ar1.get("items") or []) if i.get("basis") != "addon"]
        check(ar1.get("scheme_id") == doc["id"] and len(unit_items) == 14,
              "D7g AR disusun ulang mengikuti skema kontrak (14 termin unit)",
              f"scheme_id={ar1.get('scheme_id')} termin={len(unit_items)}")
        check(int(ar1.get("paid") or 0) == paid0 and paid0 > 0,
              "D7h booking fee yang sudah dialihkan tetap terhitung setelah ganti skema",
              f"sebelum={paid0} sesudah={ar1.get('paid')}")
        dl = j(requests.get(f"{BASE}/deals/{deal.get('id')}", headers=sa, timeout=30)).get("data") or {}
        check(dl.get("scheme_id") == doc["id"],
              "D7i deal menunjuk skema yang sama (SPR = skema = piutang)", str(dl.get("scheme_id")))
        r = requests.post(f"{BASE}/payment-schemes/contracts/{target['id']}", headers=finlead,
                          json={"scheme_id": doc["id"], "reason": "singkat"}, timeout=30)
        check(r.status_code in (400, 422) and "10 huruf" in str(j(r).get("detail")),
              "D7d alasan penggantian sepotong ditolak", d(r))
        # Penerimaan KAS nyata → ganti skema DITOLAK (jadwal berjalan tidak boleh ditimpa).
        rc = requests.post(f"{BASE}/finance/ar/receipts", headers=fin, json={
            "deal_id": deal.get("id"), "amount": 1000000, "method": "transfer",
            "note": "uji gate 48 penerimaan nyata"}, timeout=30)
        if rc.status_code == 200:
            r = requests.post(f"{BASE}/payment-schemes/contracts/{target['id']}", headers=finlead,
                              json={"scheme_id": doc["id"], "reason": "mencoba ganti setelah bayar"},
                              timeout=30)
            check(r.status_code == 400 and "penerimaan" in str(j(r).get("detail")).lower(),
                  "D7f ganti skema DITOLAK setelah ada penerimaan kas nyata", d(r))
        else:
            check(False, "D7f penerimaan kas uji bisa dicatat", d(rc))
        # Skema yang hanya berlaku di proyek LAIN tidak boleh dipasang di sini.
        lainp = requests.post(f"{BASE}/payment-schemes", headers=sa, json={
            "name": f"POC57 Proyek lain {tanda}", "kind": jenis, "terms": terms,
            "applies_project_ids": ["proyek-yang-tidak-ada"]}, timeout=30)
        if lainp.status_code == 200:
            dibuat.append((j(lainp).get("data") or {}).get("id"))
            r = requests.post(f"{BASE}/payment-schemes/contracts/{target['id']}",
                              headers=finlead,
                              json={"scheme_id": (j(lainp).get("data") or {})["id"],
                                    "reason": "mencoba skema milik proyek lain"}, timeout=30)
            check(r.status_code == 400 and "proyek" in str(j(r).get("detail")),
                  "D7e skema yang dibatasi ke proyek LAIN ditolak pada kontrak ini", d(r))
        else:
            check(False, "D7e skema berbatas proyek bisa dibuat untuk diuji", d(lainp))
    else:
        check(False, "D7 ada kontrak tanpa penerimaan untuk diuji penetapan skema",
              "tidak ditemukan di data demo")

    lain = "kpr" if jenis != "kpr" else "cash_keras"
    kpr = next((c for c in ctrs if c.get("scheme") == lain), None)
    if kpr:
        r = requests.post(f"{BASE}/payment-schemes/contracts/{kpr['id']}", headers=finlead,
                          json={"scheme_id": doc["id"],
                                "reason": "mencoba memasang skema tunai pada kontrak KPR"},
                          timeout=30)
        check(r.status_code == 400 and "berjenis" in str(j(r).get("detail")),
              "D8 skema berjenis lain TIDAK bisa dipasang pada kontrak ini", d(r))

    berbayar = None
    for c in ([target] if target else []) + ctrs:
        det = j(requests.get(f"{BASE}/finance/ar/{c['deal_id']}", headers=fin, timeout=30))
        i = det.get("data") or {}
        nyata = [x for x in (det.get("receipts") or []) if x.get("funding") != "deposit"]
        # Hanya kontrak dengan penerimaan KAS nyata (booking fee yang dialihkan otomatis
        # bukan penghalang ganti skema — lihat D7).
        if int(i.get("paid") or 0) > 0 and nyata and c.get("scheme") == jenis:
            berbayar = c
            break
    if berbayar:
        r = requests.post(f"{BASE}/payment-schemes/contracts/{berbayar['id']}", headers=finlead,
                          json={"scheme_id": doc["id"],
                                "reason": "mencoba mengganti skema yang sudah dibayar"},
                          timeout=30)
        check(r.status_code == 400 and "adendum" in str(j(r).get("detail")),
              "D9 kontrak yang sudah ada penerimaan menolak ganti skema (wajib adendum)",
              d(r))
        # Dan skema yang DIPAKAI kontrak beruang tidak boleh diubah termin-nya. Keadaan ini
        # tidak bisa dicapai lewat HTTP (D9 memblokirnya), jadi dipasang sebagai fixture.
        dbm = _db()
        dbm.contracts.update_one({"id": berbayar["id"]},
                                 {"$set": {"payment_scheme_id": doc["id"]}})
        ubah = requests.put(f"{BASE}/payment-schemes/{doc['id']}", headers=sa, json={
            "name": doc["name"], "kind": jenis,
            "terms": [{"label": "DP 100% (diubah)", "basis": "percent", "value": 100}]},
            timeout=30)
        check(ubah.status_code == 400 and "skema BARU" in str(j(ubah).get("detail")),
              "D9b termin skema yang dipakai kontrak BERUANG tidak bisa diubah diam-diam",
              d(ubah))
        dbm.contracts.update_one({"id": berbayar["id"]},
                                 {"$unset": {"payment_scheme_id": ""}})
    return dibuat


def _db():
    import os

    from dotenv import load_dotenv
    from pymongo import MongoClient
    load_dotenv(ROOT / "backend" / ".env")
    return MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def _units_with_schedule() -> set:
    return set(_db().build_schedules.distinct("unit_id"))


def bersihkan(ids):
    """Buang SEMUA jejak gate ini: skema uji, kontrak uji, dan unit yang dipakainya.

    Unit WAJIB dilepas kembali ke stok — unit yang tertinggal "booked" oleh kontrak uji
    adalah rumah yang hilang dari ketersediaan, dan itu temuan gate lain (invarian bisnis).
    """
    db = _db()
    # Jurnal penerimaan lahir dari antrean peristiwa — tunggu antrean kosong dulu supaya
    # jurnal kas uji (D7f) ikut terbuang, bukan tertinggal sebagai jurnal yatim 2-1400.
    for _ in range(60):
        try:
            if int((j(requests.get(f"{BASE}/health", timeout=10)) or {}).get("events_pending") or 0) == 0:
                break
        except Exception:  # noqa: BLE001
            pass
        time.sleep(0.5)
    n = db.payment_schemes.delete_many(
        {"$or": [{"id": {"$in": [i for i in ids if i]}},
                 {"name": {"$regex": "^POC57"}}]}).deleted_count
    leads = [x["id"] for x in db.leads.find({"name": {"$regex": "^POC57"}}, {"id": 1})]
    custs = [x["id"] for x in db.customers.find({"name": {"$regex": "^POC57"}}, {"id": 1})]
    deals = [x for x in db.deals.find({"lead_id": {"$in": leads}}, {"id": 1, "unit_id": 1})]
    deal_ids = [x["id"] for x in deals]
    import _purge_cascade as _cascade
    _cascade.purge_deal_children(db, deal_ids, leads)
    for uid in {x.get("unit_id") for x in deals if x.get("unit_id")}:
        db.units.update_one({"id": uid}, {"$set": {
            "status": "available", "reserved_by_deal": None, "booked_by_deal": None,
            "deal_id": None, "contract_id": None, "customer_id": None,
            "lead_id": None}})
    # Booking melahirkan JADWAL PEMBANGUNAN per unit. Membuang deal-nya tanpa membuang
    # jadwalnya meninggalkan referensi YATIM (lead/deal/customer) — 100+ temuan CRITICAL di
    # `forensic_audit` yang membuat gate lain merah tanpa hubungan dengan fase ini. Kelas
    # cacat yang sama pernah terjadi pada `_fixture56` (akun portal yatim).
    # Jadwal yang LAHIR dari booking uji dibuang; jadwal milik unit demo tidak pernah
    # tersentuh karena bahan uji hanya memakai unit yang belum punya jadwal.
    scheds = [x["id"] for x in db.build_schedules.find({"deal_id": {"$in": deal_ids}},
                                                       {"id": 1})]
    db.build_items.delete_many({"schedule_id": {"$in": scheds}})
    db.build_schedules.delete_many({"id": {"$in": scheds}})
    db.contracts.delete_many({"deal_id": {"$in": deal_ids}})
    db.ar_invoices.delete_many({"deal_id": {"$in": deal_ids}})
    db.contract_liabilities.delete_many({"deal_id": {"$in": deal_ids}})
    db.commissions.delete_many({"deal_id": {"$in": deal_ids}})
    db.customer_deposits.delete_many({"deal_id": {"$in": deal_ids}})
    db.journal_entries.delete_many({"source_event": {"$regex": "|".join(deal_ids)}}) \
        if deal_ids else None
    db.deals.delete_many({"id": {"$in": deal_ids}})
    db.customers.delete_many({"id": {"$in": custs}})
    db.leads.delete_many({"id": {"$in": leads}})
    db.documents.delete_many({"deal_id": {"$in": deal_ids}})
    # Konversi pembeli menerbitkan CATATAN PAJAK (PPN/PPh per transaksi) dan tugas tindak
    # lanjut. Keduanya menyimpan `deal_id`/`related_entity_id` — bila deal-nya dibuang tanpa
    # mereka, gate integritas data & forensik merah karena referensi yatim.
    db.tax_records.delete_many({"deal_id": {"$in": deal_ids}})
    db.tasks.delete_many({"related_entity_id": {"$in": deal_ids + custs + leads}})
    db.activities.delete_many({"entity_id": {"$in": custs + deal_ids + leads}})
    db.tasks.delete_many({"related_entity_id": {"$in": deal_ids + custs}})
    m = db.contracts.update_many({"payment_scheme_id": {"$in": [i for i in ids if i]}},
                                 {"$unset": {"payment_scheme_id": "", "payment_scheme_name": ""}})
    sisa = (db.build_schedules.count_documents({"deal_id": {"$in": deal_ids}})
            + db.units.count_documents({"lead_id": {"$in": leads}})
            + db.tax_records.count_documents({"deal_id": {"$in": deal_ids}})
            + db.payment_schemes.count_documents({"name": {"$regex": "^POC57"}})
            + db.leads.count_documents({"name": {"$regex": "^POC57"}})
            + db.customers.count_documents({"name": {"$regex": "^POC57"}}))
    return n, m.modified_count, sisa


def main() -> int:
    print("=" * 78)
    print("GATE 48 — SKEMA PEMBAYARAN YANG BISA DIKONFIGURASI (Fase 57A)")
    print("=" * 78)
    try:
        requests.get(f"{BASE}/health", timeout=10)
    except Exception as e:  # noqa: BLE001
        print(f"Backend tidak menjawab: {e}")
        return 1
    bagian_k()
    ids = []
    try:
        ids = bagian_d() or []
    finally:
        head("Bahan uji dibuang tanpa sisa")
        n, m, sisa = bersihkan(ids)
        check(sisa == 0, "D10 skema uji (POC57) dibuang bersih",
              f"dibuang={n} kontrak dilepas={m} sisa={sisa}")

    print("\n" + "-" * 78)
    if FAIL:
        print(f"GATE 48 MERAH — {len(FAIL)} gagal / {PASSED + len(FAIL)} pemeriksaan")
        for f in FAIL:
            print(f"  - {f}")
        return 1
    print(f"GATE 48 HIJAU — {PASSED} pemeriksaan")
    return 0


if __name__ == "__main__":
    sys.exit(main())
