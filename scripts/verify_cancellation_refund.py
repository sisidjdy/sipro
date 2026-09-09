#!/usr/bin/env python3
"""verify_cancellation_refund.py — GATE 47 (Fase 56C): janji pasal pembatalan SPR harus
tetap BISA DIJALANKAN, berjurnal, dan bisa dipertanggungjawabkan kepada pembeli.

## Kenapa gate ini ada

Dokumen SPR yang dicetak sistem ini menjanjikan angka kepada pembeli: potongan 35% bila
mundur sebelum pembangunan, 50% bila sedang dibangun, dan pengembalian dana menyusul
penjualan ulang unit. Sebelum Fase 56C tidak ada satu pun endpoint yang menjalankan janji
itu; sesudahnya, `poc/poc_56.py` membuktikan rantainya hidup — tetapi POC **tidak terdaftar**
di `run_all_gates.sh`. Pelajaran yang sama dengan utang Fase 53 (baru dibayar di Fase 54):
apa yang hanya dijaga POC bisa dirusak diam-diam sementara rangkaian gate tetap hijau.

Yang dibawa gate ini (dan POC memang tidak bisa lakukan):

  * **Penjaga tingkat KODE (K).** POC hanya melihat perilaku HTTP. Ia tidak bisa melihat
    persentase potongan mulai ditulis keras di kode (bukan dibaca Pusat Konfigurasi), layar
    mulai mengetik labelnya sendiri, panel pembatalan dicabut dari layar kontrak, tab
    Keuangan/portal menjadi komponen mati, atau nomor akun bocor ke mata pembeli.
  * **Kejujuran uang (D).** Jurnal WAJIB berimbang, kewajiban kepada pembeli WAJIB turun
    tepat sebesar uang yang diterima, dan utang refund WAJIB kembali nol setelah dibayar.
    "Rp 0" tanpa sebab dilarang: keadaan "belum ada penerimaan" harus berupa KALIMAT.

Gate ini tidak meninggalkan jejak: bahan ujinya berawalan `POC56` dan dibuang
`scripts/_fixture56.py` (termasuk akun portal yang lahir dari login OTP — akun portal yatim
adalah temuan CRITICAL di `forensic_audit.py`).

Jalankan: python3 scripts/verify_cancellation_refund.py
"""
import pathlib
import re
import sys
import time

import requests

ROOT = pathlib.Path(__file__).resolve().parent.parent
BE = ROOT / "backend"
FE = ROOT / "frontend" / "src"
sys.path.insert(0, str(ROOT / "scripts"))

BASE = "http://localhost:8001/api"
PW = "Sipro#2026"
OTP = "000000"
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
    """Buang komentar & docstring: cerita di dalam kode bukan bukti perilaku."""
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    src = re.sub(r'"""(?:.|\n)*?"""', "", src)
    return "\n".join(ln for ln in src.split("\n")
                     if not ln.strip().startswith(("//", "#")))


def strip_imports(src: str) -> str:
    """Nama yang HANYA diimpor adalah kode mati, bukan pemakaian."""
    return "\n".join(ln for ln in src.split("\n")
                     if not ln.strip().startswith("import ")
                     and not re.match(r"^\s*}?\s*from\s+[\"']", ln))


def fungsi(src: str, nama: str) -> str:
    """Badan SATU fungsi tingkat-modul — pelajaran uji-mutasi: memeriksa berkas UTUH
    membuat aturan bisa dimatikan di tempatnya sementara gate tetap hijau."""
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


def d(r) -> str:
    try:
        return f"HTTP {r.status_code} {str(r.json())[:200]}"
    except Exception:  # noqa: BLE001
        return f"HTTP {r.status_code} {r.text[:200]}"


def j(r):
    try:
        return r.json()
    except Exception:  # noqa: BLE001
        return {}


def login(email: str) -> dict:
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": PW}, timeout=30)
    if r.status_code != 200:
        raise SystemExit(f"login {email} gagal: {d(r)}")
    return {"Authorization": f"Bearer {j(r)['access_token']}"}


def akun(headers, code: str) -> int:
    """Saldo satu akun dari NERACA SALDO — pembukuan yang sama dengan laporan keuangan."""
    r = requests.get(f"{BASE}/gl/trial-balance", headers=headers, timeout=30)
    data = j(r)
    rows = (data.get("data") or {}).get("rows") if isinstance(data.get("data"), dict) \
        else (data.get("rows") or data.get("data") or [])
    for row in rows or []:
        if isinstance(row, dict) and code in (row.get("account_code"), row.get("code")):
            return int(row.get("balance") or 0)
    return 0


# ============================================================ K. penjaga tingkat KODE
def bagian_k():
    head("K. Kode: aturan Fase 56 tidak boleh bisa dimatikan tanpa gate ini merah")
    cx = strip_comments(read(BE / "cancellation_engine.py"))
    ref56 = read(BE / "reference_p56.py")
    router = strip_comments(read(BE / "routers" / "cancellation_router.py"))
    portal = strip_comments(read(BE / "routers" / "portal_router.py"))
    models = strip_comments(read(BE / "models_p56.py"))

    # --- hitungan datang dari KEADAAN NYATA + Pusat Konfigurasi, bukan angka karangan
    hitung = fungsi(cx, "compute")
    check("db.contract_liabilities.find_one" in hitung,
          "K1 uang yang diterima dibaca dari SALDO KEWAJIBAN KONTRAK (bukan hitungan kedua)")
    check('cfg.get(key' in hitung
          and 'cancellation.cut_before_build_pct' in hitung
          and 'cancellation.cut_during_build_pct' in hitung,
          "K2 persentase potongan DIBACA dari Pusat Konfigurasi (bukan ditulis keras di kode)")
    check(not re.search(r"(pct|persen)\s*=\s*(35|50)\b", hitung),
          "K2b tidak ada persentase potongan yang ditanam di kode",
          str(re.findall(r".*=\s*(?:35|50)\b.*", hitung)[:2]))
    basis = fungsi(cx, "_build_basis")
    check('unit.get("construction_status")' in basis
          and 'unit.get("construction_progress")' in basis,
          "K3 dasar potongan dibaca dari keadaan PEMBANGUNAN unit (bukan diketik pengaju)")
    check("Belum ada penerimaan yang tercatat" in hitung
          and 'if received + deposit == 0' in hitung,
          "K4b 'tidak ada refund' WAJIB berupa kalimat sebab, bukan Rp 0 tanpa penjelasan")
    rp = fungsi(cx, "_rp")
    check("belum ditetapkan" in rp and "if v is None" in rp,
          "K4c nominal yang belum diketahui dicetak 'belum ditetapkan' (bukan Rp 0)")

    # --- setiap sebab punya kode yang TERDAFTAR di Kamus Data (SSOT tidak bercabang)
    blk = fungsi(cx, "blocks")
    dipakai = set(re.findall(r'_blk\("([a-z_0-9]+)"', blk))
    terdaftar = opsi_kamus(ref56, "cancel_block")
    check(bool(dipakai) and dipakai <= terdaftar,
          "K5 setiap sebab 'belum bisa diajukan' terdaftar di Kamus Data",
          f"tak terdaftar: {sorted(dipakai - terdaftar)}")
    hold = fungsi(cx, "refund_hold")
    hold_kode = set(re.findall(r'"code":\s*"([a-z_0-9]+)"', hold))
    hold_terdaftar = opsi_kamus(ref56, "refund_hold")
    check(bool(hold_kode) and hold_kode <= hold_terdaftar,
          "K6 setiap sebab penahanan refund terdaftar di Kamus Data",
          f"tak terdaftar: {sorted(hold_kode - hold_terdaftar)}")
    # Keadaan yang ditulis pada dokumen PEMBATALAN (bukan pada kontrak/deal, yang punya
    # kamus sendiri) wajib terdaftar — kalau tidak, layar akan menampilkan kode mentah.
    tulis_cancel = fungsi(cx, "request") + "".join(
        seg[:300] for seg in cx.split("db.cancellations.update_one")[1:])
    state_kode = set(re.findall(r'"state":\s*"([a-z_0-9]+)"', tulis_cancel)) | set(
        re.findall(r'state = "([a-z_0-9]+)"', cx))
    state_terdaftar = opsi_kamus(ref56, "cancel_state")
    check(bool(state_kode) and state_kode <= state_terdaftar,
          "K6b setiap keadaan pembatalan yang ditulis mesin ada di Kamus Data",
          f"tak terdaftar: {sorted(state_kode - state_terdaftar)}")
    check('ref.label_of("cancel_block"' in fungsi(cx, "_blk"),
          "K6c sebab penahanan berlabel Kamus Data (layar tidak mengarang kalimatnya)")

    # --- pemisahan tugas & 'niat bukan peristiwa uang'
    decide = fungsi(cx, "decide")
    check(re.search(r'cancel\.get\("requested_by"\)\s*==\s*actor', decide) is not None
          and "raise ValueError" in decide,
          "K7 pengaju TIDAK boleh memutuskan pengajuannya sendiri (dijaga MESIN, bukan layar)")
    check(re.search(r'if cancel\["state"\]\s*!=\s*"diajukan"', decide) is not None,
          "K7b satu pengajuan tidak bisa diputus dua kali")
    ajukan = fungsi(cx, "request")
    check("post_journal" not in ajukan and "_post_decision_journal" not in ajukan,
          "K8 PENGAJUAN tidak menyentuh pembukuan (niat bukan peristiwa uang)")
    check("compute(org, contract)" in decide,
          "K8b hitungan DIHITUNG ULANG saat memutuskan (uang bisa bergerak sesudah pengajuan)")

    # --- jurnal: potongan menjadi pendapatan, sisanya UTANG kepada pembeli
    jr = fungsi(cx, "_post_decision_journal")
    check('"2-1400"' in cx and '"2-1460"' in cx and '"4-1200"' in cx,
          "K9 akun pembatalan terdaftar di mesin (uang muka, utang refund, potongan)")
    check("AKUN_UANG_MUKA" in jr and '"debit": hitung["received_total"]' in jr,
          "K9b kewajiban kepada pembeli DISELESAIKAN sebesar uang yang diterima (Dr 2-1400)")
    check("AKUN_POTONGAN" in jr and '"credit": hitung["cut_amount"]' in jr,
          "K9c potongan menjadi pendapatan lain-lain (Cr 4-1200)")
    check("AKUN_UTANG_REFUND" in jr and '"credit": hitung["payable_total"]' in jr,
          "K9d sisanya menjadi UTANG REFUND kepada pembeli (Cr 2-1460)")
    bayar = fungsi(cx, "pay_refund")
    check("AKUN_UTANG_REFUND" in bayar
          and re.search(r'AKUN_KAS if method == "tunai" else AKUN_BANK', bayar) is not None,
          "K9e pembayaran refund menutup utang dari kas/bank sesuai caranya")

    # --- unit tidak boleh hilang karena satu pembeli mundur
    lepas = fungsi(cx, "_release_unit")
    check("find_one_and_update" in lepas and '"status": "available"' in lepas
          and '"booked_by_deal": cancel["deal_id"]' in lepas,
          "K10 unit dilepas ATOMIK dan hanya bila unit itu memang milik deal ini")
    check("status_history" in lepas,
          "K10b pelepasan unit meninggalkan jejak di riwayat unit (bukan lenyap tanpa sebab)")
    check('"sold_by_deal": None' in lepas and '"sold_at": None' in lepas,
          "K10b2 unit yang kembali ke stok TIDAK lagi mengaku terjual (sold_by_deal & "
          "sold_at dikosongkan)")
    check('{"sold_by_deal": cancel["deal_id"]}' in lepas,
          "K10b3 unit yang tertaut HANYA lewat penjualan tetap bisa dilepas ke stok")
    void = fungsi(cx, "_void_ar")
    check("_release_unit" in decide and "_void_ar" in decide,
          "K10c keputusan melepas unit DAN membatalkan tagihan yang belum dibayar")
    check("receipts" not in void or "delete" not in void,
          "K10d kuitansi yang sudah dipegang pembeli tidak dihapus (pembatalan ≠ hapus bukti)")
    check("if dibatalkan:" in void
          and '"status": "cancelled", "outstanding": 0' in void,
          "K10e tagihan yang SUDAH LUNAS tidak ditandai 'dibatalkan' (tidak ada termin "
          "tersisa untuk dibatalkan)")
    check("db.contract_liabilities.update_one" in decide
          and '"balance": 0, "cancelled": True' in decide,
          "K10f subledger kewajiban kontrak ditutup mengikuti jurnal (tie-out terjaga)")

    # --- refund: idempoten, tidak bisa dibayar dua kali, penahanan berwenang
    check(bayar.index('client_ref') < bayar.index("post_journal"),
          "K11 penanda `client_ref` diperiksa SEBELUM jurnal (kiriman ulang bukan bayar dua kali)")
    check('"replay": True' in bayar, "K11b kiriman ulang dijawab JUJUR sebagai pemutaran ulang")
    check("if amount > sisa" in bayar and "melebihi sisa" in bayar,
          "K12 pembayaran yang MELEBIHI sisa utang refund ditolak")
    check("if not may_override" in bayar
          and re.search(r'len\(\(override_reason or ""\)\.strip\(\)\)\s*<\s*10', bayar)
          is not None,
          "K13 pengabaian penahanan butuh WEWENANG + alasan minimal 10 huruf")
    check(hold.index("sudah_lunas") < hold.index("belum_disetujui"),
          "K14 'sudah lunas' diperiksa LEBIH DAHULU (refund lunas bukan 'belum disetujui')")
    check("refund_requires_resale" in hold and "menunggu_penjualan_ulang" in hold,
          "K14b penahanan 'menunggu penjualan ulang' mengikuti ketentuan SPR di Konfigurasi")
    check('str(unit.get("status") or "") not in ("available", "")' in hold
          and 'unit.get("deal_id") != cancel.get("deal_id")' in hold,
          "K14c 'terjual kembali' berarti unit BENAR keluar dari stok (tautan deal yang BASI "
          "— termasuk deal yang justru dibatalkan — tidak boleh menghapus penahanan)")
    check("MIN_REASON = 10" in models and models.count("_reason(") >= 4,
          "K15 alasan/catatan wajib dipaksakan juga di lapis model (lapis pertama)")

    # --- router: pemisahan tugas dipaksakan izin, bukan hanya tombol layar
    izin = set(re.findall(r'require_permission\("cancellation",\s*\n?\s*"(\w+)"',
                          read(BE / "routers" / "cancellation_router.py")))
    check({"view", "create", "approve", "update"} <= izin,
          "K16 mengajukan/memutuskan/membayar memakai IZIN yang berbeda", str(sorted(izin)))
    check('can(user.get("role"), "cancellation", "override")' in router,
          "K16b wewenang mengabaikan penahanan diperiksa terpisah (`override`)")
    check("is_scoped_sales(user)" in router and '"di_luar_lingkup"' in router,
          "K16c lingkup data sales dijaga, dan 'bukan milik Anda' ≠ 'tidak ada'")
    portal_fn = fungsi(portal, "cancellations")
    check("cx.portal_rows(" in portal_fn,
          "K17 portal membaca angka dari MESIN yang sama (pembeli & staf satu sumber)")
    pratinjau = fungsi(cx, "preview")
    check('"history": [await enrich(org, r) for r in riwayat]' in pratinjau,
          "K17c riwayat pada pratinjau ikut DIPERKAYA (penahanan & sisa refund hanya benar "
          "saat dibaca; baris mentah membuat layar menulis 'Sisa 0' tanpa sebab)")
    check("account_code" not in portal_fn and "2-1460" not in portal_fn,
          "K17b tidak ada nomor akun yang bocor ke jawaban portal")

    # ------------------------------------------------------------------ layar (FE)
    ids = read(FE / "constants" / "testIds" / "p56.js")
    panel = read(FE / "components" / "contracts" / "CancellationPanel.js")
    kontrak = read(FE / "components" / "contracts" / "ContractPanel.js")
    fin_panel = read(FE / "components" / "finance" / "CancellationsPanel.js")
    fin_page = read(FE / "pages" / "FinancePage.js")
    portal_panel = read(FE / "components" / "portal" / "panels" / "CancellationPanel.js")
    portal_dash = read(FE / "components" / "portal" / "PortalDashboard.js")
    plan_tab = read(FE / "components" / "customers" / "CustomerPaymentPlanTab.js")
    layar = panel + fin_panel + portal_panel + kontrak + fin_page + portal_dash

    check("<CancellationPanel contract={contract}" in kontrak,
          "K18 panel pembatalan benar-benar DIRENDER di layar Kontrak & Legal")
    check("<CancellationsPanel />" in fin_page
          and 'key: "cancellations"' in fin_page
          and "LEGACY" in fin_page and "params.get(\"tab\")" in fin_page,
          "K19 tab 'Pembatalan & Refund' DIRENDER di Keuangan dan hidup di URL (?tab=)")
    check("Comp: CancellationPanel" in portal_dash,
          "K20 tab pembatalan DIRENDER di portal pembeli (bukan komponen mati)")
    mati = [nama for nama, tid in re.findall(r"(\w+):\s*\"([a-z0-9-]+)\"", ids)
            if f'"{tid}"' not in layar and f"P56.{nama}" not in layar]
    check(not mati, "K21 tidak ada testId Fase 56 yang MATI (setiap id dipakai layar)",
          str(mati))
    check("state_label" in strip_imports(fin_panel) or 'group="cancel_state"' in fin_panel,
          "K22 daftar Keuangan memakai label keadaan dari Kamus Data, bukan diketik layar")
    check('options("cancel_state")' in fin_panel,
          "K22p saringan keadaan memakai pilihan Kamus Data (bukan daftar yang diketik layar)")
    check("params: {" in fin_panel and "state: filter.state" in fin_panel
          and "q: filter.q" in fin_panel,
          "K22q penyaringan & pencarian dikirim ke SERVER (bukan menyaring 100 baris pertama "
          "di peramban, yang menyembunyikan baris yang justru dicari)")
    check("Kosongnya daftar ini karena saringan" in fin_panel,
          "K22r daftar kosong karena SARINGAN dijelaskan sebabnya (bukan 'belum ada')")
    check("dijumlah dari BARIS YANG TERSARING" in fin_panel,
          "K22s KPI utang refund mengaku bila angkanya hanya dari baris tersaring")
    check("r.settlement ?" in fin_panel and "belum ditetapkan" in fin_panel,
          "K22a pengajuan yang BELUM diputus tidak ditulis 'Rp 0' (utang refund belum lahir)")
    check("r.rule_label" in portal_panel and "r.money_note" in portal_panel,
          "K22b portal menampilkan DASAR ATURAN & kalimat uang dari server")
    check("waiting_note" in portal_panel,
          "K22c yang sedang ditunggu pembeli disebutkan (bukan sisa yang diam)")
    check(not re.search(r"[124]-1[0-9]{3}", strip_comments(portal_panel)),
          "K23 tidak ada nomor akun yang tampil di layar PEMBELI")
    check("portalDownload(" in portal_panel and "<a href" not in portal_panel,
          "K23b berita acara diunduh lewat SESI portal (bukan tautan mentah bertoken)")
    salah_prefix = [u for u in re.findall(r'portalApi\.\w+\(\s*"([^"]+)"', portal_panel)
                    if not u.startswith("/portal/")]
    check(not salah_prefix,
          "K23c panel portal memanggil jalur berprefix `/portal/` (jalur staf → 401 → "
          "pembeli terlempar keluar tanpa penjelasan)", str(salah_prefix))
    check("pre.blocks" in panel and "b.detail" in panel,
          "K24 layar MENYEBUTKAN sebab pembatalan belum boleh (bukan tombol mati)")
    check("client_ref" in panel,
          "K24b tombol bayar refund membawa penanda sekali-pakai (klik ganda tidak dobel)")
    check("refund_hold" in panel or "refundHold" in panel,
          "K24c penahanan refund ditampilkan beserta sebabnya")
    check("mesin pembatalan/refund berjurnal" not in plan_tab
          and "belum" in plan_tab,
          "K25 layar tidak lagi mengaku mesin pembatalan/refund 'belum ada' (janji ditepati)")


# ============================================================ D. perilaku (HTTP nyata)
def bagian_d():  # noqa: C901
    head("D. Perilaku: rantai pembatalan → jurnal → refund → unit kembali ke stok")
    sa = login("superadmin@sipro.co.id")
    mgr = login("manager@sipro.co.id")
    finlead = login("finlead@sipro.co.id")
    fin = login("finance@sipro.co.id")
    sales = login("sales@sipro.co.id")
    tanda = str(int(time.time()))[-6:]

    lead = requests.post(f"{BASE}/leads", headers=sa, json={
        "name": f"POC56 Gate Ibu Sari {tanda}", "phone": f"+62812{tanda}47",
        "source": "walk_in", "notes": "bahan uji gate 47"}, timeout=30)
    lead_id = (j(lead).get("data") or {}).get("id")
    units = j(requests.get(f"{BASE}/units", headers=sa,
                           params={"status": "available", "limit": 30},
                           timeout=30)).get("data") or []
    # Unit yang PEMBANGUNANNYA BELUM MULAI: hanya di situ potongan SPR 35% berlaku. Memakai
    # unit sembarang membuat gate merah karena aturannya benar (50% saat sedang dibangun).
    units = [u for u in units
             if str(u.get("construction_status") or "not_started")
             not in ("in_progress", "qc_hold")
             and int(u.get("construction_progress") or 0) == 0]
    if not (lead_id and units):
        check(False, "D0 bahan uji bisa dibuat (lead + unit tersedia)", d(lead))
        return
    unit = units[0]
    res = requests.post(f"{BASE}/deals/reserve", headers=sa, json={
        "lead_id": lead_id, "unit_id": unit["id"], "booking_fee": 5000000,
        "notes": "gate 47"}, timeout=30)
    deal_id = (j(res).get("data") or {}).get("id")
    requests.post(f"{BASE}/booking-fee/deals/{deal_id}/pay", headers=sa, timeout=30,
                  json={"amount": 5000000, "method": "transfer"})
    requests.post(f"{BASE}/deals/{deal_id}/book", headers=sa, json={}, timeout=30)
    cv = requests.post(f"{BASE}/deals/{deal_id}/convert", headers=sa, json={
        "scheme": "cash_bertahap", "nik": f"3299{tanda}000047",
        "address": "Jl. Gate 47 No. 1"}, timeout=30)
    contract = (j(cv).get("data") or {}).get("contract") or {}
    cust = (j(cv).get("data") or {}).get("customer") or {}
    cid = contract.get("id")
    if not check(cv.status_code == 200 and bool(cid),
                 "D0 bahan uji: lead → reservasi → booking → pembeli → kontrak", d(cv)):
        return
    requests.post(f"{BASE}/contracts/{cid}/activate", headers=fin, timeout=30)

    pv = requests.get(f"{BASE}/cancellations/preview", headers=mgr,
                      params={"contract_id": cid}, timeout=30)
    p = j(pv).get("data") or {}
    check(pv.status_code == 200 and p.get("can_request") is True,
          "D1 pembatalan boleh diajukan pada kontrak yang masih berjalan",
          f"{pv.status_code} {p.get('blocks')}")
    check(p.get("basis") == "belum_mulai" and p.get("cut_pct") == 35,
          "D2 dasar potongan = belum dibangun → 35% (ketentuan SPR dari Pusat Konfigurasi)",
          f"{p.get('basis')} {p.get('cut_pct')}")
    # Fase 75–78: booking fee adalah TITIPAN (2-1450) yang dikembalikan PENUH saat batal —
    # ia ikut utang refund tetapi tidak pernah ikut dasar potongan 35%.
    titipan = int(p.get("deposit_balance") or 0)
    check(p.get("received_total") == 0
          and (("belum ada penerimaan" in str(p.get("note")).lower()) if titipan == 0
               else ("titipan" in str(p.get("note")).lower() and p.get("cut_amount") == 0)),
          "D3 belum ada uang masuk dinyatakan SEBABNYA (bukan 'refund Rp 0' tanpa kalimat)",
          str(p.get("note"))[:120])

    ar = j(requests.get(f"{BASE}/finance/ar/{deal_id}", headers=fin,
                        timeout=30)).get("data") or {}
    inv = ar.get("invoice") or ar
    dp = int((inv.get("items") or [{}])[0].get("amount") or 0)
    bayar = requests.post(f"{BASE}/finance/ar/receipts", headers=fin, json={
        "deal_id": deal_id, "amount": dp, "method": "transfer",
        "note": "gate 47 termin pertama"}, timeout=60)
    check(bayar.status_code == 200 and dp > 0, "D4 penerimaan pembeli dicatat Keuangan", d(bayar))
    liab_awal = akun(sa, "2-1400")
    harap_cut = round(dp * 35 / 100)
    sisa = dp - harap_cut + titipan
    pv2 = j(requests.get(f"{BASE}/cancellations/preview", headers=mgr,
                         params={"contract_id": cid}, timeout=30)).get("data") or {}
    check(pv2.get("received_total") == dp and pv2.get("cut_amount") == harap_cut
          and pv2.get("payable_total") == sisa,
          "D5 potongan 35% & nominal refund dihitung dari uang NYATA (+ titipan dikembalikan penuh)",
          f"{pv2.get('received_total')}/{pv2.get('cut_amount')}/{pv2.get('payable_total')} titipan={titipan}")

    r = requests.post(f"{BASE}/cancellations", headers=sales, json={
        "contract_id": cid, "reason": "pembeli mundur karena pindah kota"}, timeout=30)
    check(r.status_code == 403, "D6 sales TIDAK boleh mengajukan pembatalan", d(r))
    r = requests.post(f"{BASE}/cancellations", headers=fin, json={
        "contract_id": cid, "reason": "pembeli mundur karena pindah kota"}, timeout=30)
    check(r.status_code == 403, "D6b kasir Keuangan TIDAK boleh mengajukan pembatalan", d(r))
    r = requests.post(f"{BASE}/cancellations", headers=mgr,
                      json={"contract_id": cid, "reason": "batal"}, timeout=30)
    check(r.status_code in (400, 422) and "10 huruf" in str(j(r).get("detail")),
          "D7 alasan sepotong (<10 huruf) DITOLAK", d(r))
    req = requests.post(f"{BASE}/cancellations", headers=mgr, json={
        "contract_id": cid,
        "reason": "pembeli mundur karena pindah tugas ke luar kota"}, timeout=30)
    cxr = j(req).get("data") or {}
    xid = cxr.get("id")
    if not check(req.status_code == 200 and bool(xid),
                 "D8 Manajer Sales mengajukan pembatalan", d(req)):
        return
    check(str(cxr.get("number") or "").startswith("BTL/"),
          "D8b pengajuan bernomor (bisa dirujuk dokumen & jurnal)", str(cxr.get("number")))
    check(akun(sa, "2-1400") == liab_awal,
          "D9 PENGAJUAN belum menyentuh pembukuan (niat bukan peristiwa uang)")
    dup = requests.post(f"{BASE}/cancellations", headers=mgr, json={
        "contract_id": cid, "reason": "pengajuan kedua yang seharusnya ditolak"}, timeout=30)
    check(dup.status_code == 400 and "menunggu keputusan" in str(j(dup).get("detail")),
          "D9b pengajuan GANDA ditolak selama yang pertama belum diputus", d(dup))
    r = requests.post(f"{BASE}/cancellations/{xid}/decision", headers=mgr, json={
        "approved": True, "note": "disetujui oleh pengaju sendiri"}, timeout=30)
    check(r.status_code == 403, "D10 pengaju (Manajer Sales) TIDAK boleh memutuskan", d(r))
    r = requests.post(f"{BASE}/cancellations/{xid}/refund", headers=fin,
                      json={"method": "transfer"}, timeout=30)
    check(r.status_code == 400 and "belum disetujui" in str(j(r).get("detail")).lower(),
          "D10b refund tidak bisa dibayar sebelum ADA keputusan", d(r))

    # Saldo dibaca ULANG tepat sebelum keputusan: penerimaan lain (atau pekerjaan
    # penjadwal) bisa menggerakkan akun ini di antara dua pemeriksaan, dan gate tidak boleh
    # merah karena hal yang bukan urusannya.
    liab_pre = akun(sa, "2-1400")
    refund_pre = akun(sa, "2-1460")
    dec = requests.post(f"{BASE}/cancellations/{xid}/decision", headers=finlead, json={
        "approved": True,
        "note": "disetujui: unit masih bisa dijual ulang, potongan sesuai SPR"}, timeout=60)
    doc = j(dec).get("data") or {}
    st = doc.get("settlement") or {}
    if not check(dec.status_code == 200 and doc.get("state") == "disetujui",
                 "D11 Manajer Keuangan MENYETUJUI pembatalan", d(dec)):
        return
    jr = (doc.get("journals") or [{}])[0]
    lines = {ln.get("account_code"): (ln.get("debit"), ln.get("credit"))
             for ln in (jr.get("lines") or [])}
    check(len(doc.get("journal_ids") or []) == 1, "D12 tepat SATU jurnal keputusan",
          str(doc.get("journal_ids")))
    check(lines.get("2-1400", (0, 0))[0] == dp
          and lines.get("4-1200", (0, 0))[1] == harap_cut
          and lines.get("2-1460", (0, 0))[1] == sisa
          and (titipan == 0 or lines.get("2-1450", (0, 0))[0] == titipan),
          "D12b jurnal: Dr uang muka (+ Dr titipan), Cr potongan, Cr UTANG REFUND", str(lines))
    check(int(jr.get("total_debit") or 0) == dp + titipan, "D12c jurnal BERIMBANG",
          str(jr.get("total_debit")))
    check(akun(sa, "2-1400") == liab_pre - dp,
          "D13 kewajiban kontrak turun tepat sebesar uang yang diterima",
          f"{akun(sa, '2-1400')} vs {liab_pre - dp} (dp={dp})")
    unit_rows = j(requests.get(f"{BASE}/units", headers=sa,
                               params={"q": unit.get("code"), "limit": 5},
                               timeout=30)).get("data") or []
    unit_after = next((u for u in unit_rows if u.get("id") == unit["id"]), {})
    check(unit_after.get("status") == "available" and st.get("unit_released") is True,
          "D14 unit KEMBALI ke stok (rumah tidak hilang karena satu pembeli mundur)",
          str(unit_after.get("status")))
    # D14b memeriksa SELURUH stok, bukan hanya unit uji: satu unit yang berstatus `available`
    # tetapi masih menyimpan tautan pembeli lama adalah rumah yang mengaku terjual kepada
    # site plan, invarian bisnis, dan gate integritas data sekaligus.
    stok = j(requests.get(f"{BASE}/units", headers=sa,
                          params={"status": "available", "limit": 500},
                          timeout=30)).get("data") or []
    basi = [u.get("code") for u in stok
            if u.get("sold_by_deal") or u.get("booked_by_deal") or u.get("reserved_by_deal")
            or u.get("deal_id") or u.get("sold_at")]
    check(not basi,
          "D14b tidak ada unit DI STOK yang masih mengaku terjual/dipesan (tautan basi)",
          ", ".join(str(x) for x in basi[:5]))
    ar2 = j(requests.get(f"{BASE}/finance/ar/{deal_id}", headers=fin,
                         timeout=30)).get("data") or {}
    inv2 = ar2.get("invoice") or ar2
    check(inv2.get("status") == "cancelled" and int(inv2.get("outstanding") or 0) == 0,
          "D15 tagihan (AR) dibatalkan — tidak ada lagi termin yang ditagihkan",
          f"{inv2.get('status')}/{inv2.get('outstanding')}")
    check(len(j(requests.get(f"{BASE}/finance/ar/{deal_id}", headers=fin,
                             timeout=30)).get("receipts") or []) >= 1,
          "D15b kuitansi yang sudah dipegang pembeli TIDAK dihapus")
    liab_sub = (j(requests.get(f"{BASE}/finance/ar/{deal_id}", headers=fin, timeout=30))
                .get("contract_liability") or {})
    check(int(liab_sub.get("balance") or 0) == 0 and liab_sub.get("cancelled") is True,
          "D15c subledger kewajiban kontrak ikut NOL (buku besar & subledger tidak berbeda)",
          str({k: liab_sub.get(k) for k in ("balance", "cancelled")}))
    bap = requests.get(f"{BASE}/cancellations/by-contract/{cid}/document", headers=mgr,
                       timeout=30)
    bdoc = j(bap).get("data") or {}
    check(bap.status_code == 200 and str(bdoc.get("doc_number") or "").count("/") == 4,
          "D16 Berita Acara Pembatalan terbit bernomor format owner",
          str(bdoc.get("doc_number")))
    pdf = requests.get(f"{BASE}/documents/{bdoc.get('id')}/pdf", headers=mgr, timeout=60)
    check(pdf.status_code == 200
          and pdf.headers.get("content-type", "").startswith("application/pdf")
          and len(pdf.content) > 1500,
          "D16b Berita Acara BISA DICETAK (PDF berisi)", f"{pdf.status_code} {len(pdf.content)}b")
    isi = str((j(requests.get(f"{BASE}/documents/{bdoc.get('id')}", headers=mgr,
                              timeout=30)).get("data") or {}).get("content") or "")
    check("35%" in isi and "Rp" in isi and "{{" not in isi,
          "D16c dokumen memuat perhitungan NYATA (bukan placeholder)",
          [ln for ln in isi.split("\n") if "Potongan" in ln][:1])

    r = requests.post(f"{BASE}/cancellations/{xid}/refund", headers=fin,
                      json={"method": "transfer"}, timeout=30)
    check(r.status_code == 400 and "penjualan ulang" in str(j(r).get("detail")),
          "D17 refund DITAHAN karena unit belum terjual kembali (ketentuan SPR)", d(r))
    r = requests.post(f"{BASE}/cancellations/{xid}/refund", headers=fin, json={
        "method": "transfer", "override": True,
        "override_reason": "pembeli mengancam ke pengadilan, direksi minta dibayar"},
        timeout=30)
    check(r.status_code == 400 and "Manajer Keuangan" in str(j(r).get("detail")),
          "D17b kasir Keuangan TIDAK boleh mengabaikan penahanan refund", d(r))
    r = requests.post(f"{BASE}/cancellations/{xid}/refund", headers=finlead, json={
        "method": "transfer", "override": True, "override_reason": "urgent"}, timeout=30)
    check(r.status_code in (400, 422) and "10 huruf" in str(j(r).get("detail")),
          "D17c alasan pengabaian sepotong DITOLAK", d(r))
    hist = ((j(requests.get(f"{BASE}/cancellations/preview", headers=finlead,
                            params={"contract_id": cid}, timeout=30)).get("data") or {})
            .get("history") or [{}])[0]
    check((hist.get("refund_hold") or {}).get("code") == "menunggu_penjualan_ulang"
          and hist.get("refund_outstanding") == sisa,
          "D17d riwayat pada layar kontrak membawa SEBAB penahanan & sisa refund yang benar",
          str({k: hist.get(k) for k in ("refund_hold", "refund_outstanding")})[:160])
    pay1 = requests.post(f"{BASE}/cancellations/{xid}/refund", headers=finlead, json={
        "method": "transfer", "amount": int(sisa / 2), "client_ref": f"g47-{tanda}-1",
        "override": True,
        "override_reason": "diputus direksi: dibayar lebih dahulu tanpa menunggu penjualan"},
        timeout=60)
    check(pay1.status_code == 200
          and (j(pay1).get("data") or {}).get("state") == "refund_sebagian",
          "D18 Manajer Keuangan membayar refund SEBAGIAN dengan alasan tertulis", d(pay1))
    ulang = requests.post(f"{BASE}/cancellations/{xid}/refund", headers=finlead, json={
        "method": "transfer", "amount": int(sisa / 2), "client_ref": f"g47-{tanda}-1",
        "override": True, "override_reason": "kiriman ulang penanda yang sama"}, timeout=30)
    check(ulang.status_code == 200 and j(ulang).get("replay") is True,
          "D19 kiriman ulang `client_ref` dijawab REPLAY (bukan pembayaran kedua)", d(ulang))
    cek = j(requests.get(f"{BASE}/cancellations/{xid}", headers=finlead,
                         timeout=30)).get("data") or {}
    check(len(cek.get("refund_payments") or []) == 1,
          "D19b tetap SATU baris pembayaran sesudah kiriman ulang",
          str(len(cek.get("refund_payments") or [])))
    lebih = requests.post(f"{BASE}/cancellations/{xid}/refund", headers=finlead, json={
        "method": "tunai", "amount": sisa, "client_ref": f"g47-{tanda}-x",
        "override": True, "override_reason": "mencoba membayar lebih dari sisa utang"},
        timeout=30)
    check(lebih.status_code == 400 and "melebihi sisa" in str(j(lebih).get("detail")),
          "D20 pembayaran MELEBIHI sisa utang refund ditolak", d(lebih))
    pay2 = requests.post(f"{BASE}/cancellations/{xid}/refund", headers=finlead, json={
        "method": "tunai", "client_ref": f"g47-{tanda}-2", "override": True,
        "override_reason": "pelunasan refund sesuai keputusan direksi"}, timeout=60)
    lunas = j(pay2).get("data") or {}
    check(pay2.status_code == 200 and lunas.get("state") == "selesai"
          and lunas.get("refund_outstanding") == 0,
          "D21 sisa refund dilunasi → keadaan selesai, sisa nol", d(pay2))
    check(akun(sa, "2-1460") == refund_pre,
          "D21b utang refund pembatalan ini kembali NOL (tidak ada utang menggantung)",
          f"{akun(sa, '2-1460')} vs {refund_pre}")
    r = requests.post(f"{BASE}/cancellations/{xid}/refund", headers=finlead, json={
        "method": "tunai", "override": True,
        "override_reason": "mencoba membayar untuk ketiga kalinya"}, timeout=30)
    check(r.status_code == 400 and "sudah dibayar penuh" in str(j(r).get("detail")),
          "D21c refund yang sudah lunas tidak bisa dibayar lagi", d(r))
    pv3 = j(requests.get(f"{BASE}/cancellations/preview", headers=mgr,
                         params={"contract_id": cid}, timeout=30)).get("data") or {}
    check(any(b["code"] == "kontrak_sudah_batal" for b in pv3.get("blocks") or []),
          "D22 kontrak yang sudah dibatalkan tidak bisa dibatalkan dua kali",
          str(pv3.get("blocks")))

    ctrs = j(requests.get(f"{BASE}/contracts", headers=sa, timeout=30)).get("data") or []
    ber_bast = None
    for c in ctrs:
        cek2 = j(requests.get(f"{BASE}/cancellations/preview", headers=finlead,
                              params={"contract_id": c["id"]}, timeout=30)).get("data") or {}
        if "sudah_bast" in [b["code"] for b in cek2.get("blocks") or []]:
            ber_bast = c
            break
    check(ber_bast is not None,
          "D23 rumah yang SUDAH diserahterimakan ditahan dengan sebab `sudah_bast`",
          "tidak ada kontrak ber-BAST di data demo")
    if ber_bast:
        r = requests.post(f"{BASE}/cancellations", headers=mgr, json={
            "contract_id": ber_bast["id"],
            "reason": "mencoba membatalkan rumah yang sudah diserahkan"}, timeout=30)
        check(r.status_code == 400 and "diserahterimakan" in str(j(r).get("detail")),
              "D23b …dan pengajuannya DITOLAK server, bukan hanya tombol yang mati", d(r))

    phone = (cust.get("phone") or "").strip()
    requests.post(f"{BASE}/portal/auth/request-otp", json={"identifier": phone}, timeout=30)
    ver = requests.post(f"{BASE}/portal/auth/verify-otp",
                        json={"identifier": phone, "code": OTP}, timeout=30)
    token = j(ver).get("token") or (j(ver).get("data") or {}).get("token")
    if check(bool(token), "D24 pembeli bisa masuk portal (OTP master uji)", d(ver)):
        ph = {"Authorization": f"Bearer {token}"}
        pc = requests.get(f"{BASE}/portal/cancellations", headers=ph, timeout=30)
        rows = j(pc).get("data") or []
        check(pc.status_code == 200 and len(rows) == 1,
              "D24b portal menampilkan pembatalan milik pembeli ini", d(pc))
        if rows:
            row = rows[0]
            check(row.get("cut_pct") == 35 and row.get("payable_total") == sisa
                  and row.get("refund_outstanding") == 0,
                  "D25 angka di portal SAMA dengan angka di pembukuan (satu sumber)",
                  str({k: row.get(k) for k in ("cut_pct", "payable_total",
                                               "refund_outstanding")}))
            check("SPR" in str(row.get("rule_label"))
                  or "Ketentuan" in str(row.get("rule_label")),
                  "D25b portal menyebut DASAR ATURAN potongan", str(row.get("rule_label"))[:90])
            check(len(row.get("payments") or []) == 2,
                  "D25c riwayat pembayaran refund terlihat pembeli",
                  str(len(row.get("payments") or [])))
            check(not re.search(r"[124]-1[0-9]{3}", str(row)),
                  "D25d tidak ada nomor akun yang bocor ke jawaban portal")

    lst = requests.get(f"{BASE}/cancellations", headers=sales, timeout=30)
    js = j(lst)
    check(lst.status_code == 200
          and all(r.get("assigned_to") == "sales@sipro.co.id" for r in js.get("data") or []),
          "D26 sales hanya melihat pengajuan yang lead-nya ia pegang", d(lst))
    if not js.get("data"):
        check(js.get("reason_code") == "di_luar_lingkup" or js.get("total") == 0,
              "D26b daftar kosong karena lingkup data DIJELASKAN sebabnya",
              str(js.get("reason")))


def main() -> int:
    print("=" * 78)
    print("GATE 47 — PEMBATALAN KONTRAK & REFUND BERJURNAL (Fase 56C)")
    print("=" * 78)
    try:
        requests.get(f"{BASE}/health", timeout=10)
    except Exception as e:  # noqa: BLE001
        print(f"Backend tidak menjawab: {e}")
        return 1
    bagian_k()
    try:
        bagian_d()
    finally:
        head("Bahan uji dibuang tanpa sisa")
        import _fixture56
        hasil = _fixture56.purge()
        sisa = _fixture56.purge(dry=True)
        bersih = all(v == 0 for v in sisa.values() if isinstance(v, int))
        check(bersih, "D27 bahan uji gate dibuang bersih (termasuk akun portal & jurnal)",
              f"dibuang={hasil} sisa={sisa}")

    print("\n" + "-" * 78)
    if FAIL:
        print(f"GATE 47 MERAH — {len(FAIL)} gagal / {PASSED + len(FAIL)} pemeriksaan")
        for f in FAIL:
            print(f"  - {f}")
        return 1
    print(f"GATE 47 HIJAU — {PASSED} pemeriksaan")
    return 0


if __name__ == "__main__":
    sys.exit(main())
