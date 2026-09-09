#!/usr/bin/env python3
"""verify_contract_legal_docgen.py — GATE 46 (Fase 53): rantai LEAD → PEMBELI → KONTRAK →
AKAD → DOKUMEN OWNER tidak boleh diam-diam terputus lagi.

## Kenapa gate ini ada (utang yang tertinggal)

Fase 53 menutup empat lubang yang dilaporkan pemilik produk dan membuktikannya dengan
`poc/poc_53.py` (66 pemeriksaan) — tetapi **tidak pernah mendapat gate**. Artinya, sejak Fase
53 selesai, seluruh rantai itu hanya dijaga oleh sebuah POC yang tidak terdaftar di
`scripts/run_all_gates.sh`: siapa pun bisa merusaknya dan rangkaian gate tetap hijau. Fase 54
membayar utang itu; **Fase 55 membuktikan gate-nya BERGIGI** lewat `scripts/mutasi_53.py`.

Gate ini SENGAJA tidak menyalin ulang seluruh `poc_53.py`. Yang dibawanya adalah dua hal yang
POC memang tidak bisa lakukan, plus inti yang paling mahal bila regresi:

  * **Penjaga di tingkat KODE (K).** POC hanya melihat perilaku HTTP; ia tidak bisa melihat
    bahwa layar mulai mengetik labelnya sendiri, bahwa satu jalur reservasi dipecah lagi
    menjadi dua, atau bahwa sebuah `testId` menjadi mati. Justru di situlah Fase 53 dulu
    bocor: gate `audit_forms_deep` menemukan field "Bank" di `KprPanel.js` masih input bebas
    padahal kamus SSOT `financing_bank` sudah ada sejak Fase 27 — dan temuan itu tidak
    pernah ditutup sampai Fase 54.
  * **Kejujuran angka (D).** "Biaya yang belum diketahui" WAJIB `null`, bukan `0`. Nol
    berarti "tidak ada biayanya" — pernyataan yang belum tentu benar dan langsung menular ke
    dokumen legal yang dicetak dan ditandatangani pembeli.

## Empat lubang Fase 53 yang dijaga di sini

1. **Tidak ada satu baris kode pun yang mengubah lead menjadi pembeli.** `db.customers` dulu
   hanya ditulis form manual + seed, sementara `build_engine._buyer_binding()` mencari pembeli
   lewat `customers.lead_id == deal.lead_id` — tautan yang tidak pernah ada untuk data nyata.
2. **Penawaran melahirkan deal berbentuk LAIN** (`status="active"` vs `"reserved"`) sehingga
   deal hasil penawaran DITOLAK saat mau di-booking.
3. **Rantai legal tanpa akad kredit**, padahal pada skema KPR justru itu peristiwa penentu.
4. **Dokumen owner belum pernah ada di sistem** (SPR 3 varian + SPKT, dengan format nomor
   `{urut}/{kode}/{proyek}/{bulan romawi}/{tahun}`).

## Yang DIPERKUAT di Fase 55 (semuanya karena uji-mutasi, bukan karena rapi)

Versi pertama gate ini HIJAU pada percobaan pertama — dan itu justru tanda bahaya, bukan
kelulusan. `mutasi_53.py` membuktikan sembilan pemeriksaan versi pertama tidak menguji apa
pun. Pelajaran yang sama dengan `mutasi_51.py` (C10a) dan `mutasi_54.py`:

  * **"apakah nama X ada di berkas" bukan bukti perilaku.** `"won" in cc`,
    `"total_is_provisional" in ce`, `"belum ditetapkan" in dg` semuanya tetap terpenuhi walau
    aturannya dimatikan, karena namanya masih tertulis di tempat lain (bahkan di baris impor).
    Sekarang pemeriksaan dibatasi **per-lingkup fungsi** (`fungsi()`) dan membaca **syarat**
    kodenya.
  * **Gerbang yang menolak bisa berarti FITURNYA MATI.** "SP3K ditolak tanpa berkas" tetap
    hijau bila pengajuan KPR-nya bahkan tidak pernah dibuat. Karena itu setiap uji NEGATIF
    kini berpasangan dengan uji POSITIF (D37/D38: dengan berkas + plafon, SP3K dan akad
    DITERIMA).
  * **Kode penahan wajib punya label manusia** (D7): `ref.label_of()` mengembalikan kodenya
    sendiri bila kode itu tidak terdaftar di Kamus Data — jadi `label == code` adalah bukti
    SSOT bercabang, dan layar akan menampilkan `deal_belum_booking` kepada pemakai.
  * **Dokumen harus dibuktikan pada keadaan "biaya belum lengkap"** (D26), bukan hanya
    sesudah semuanya diisi; di situlah aturan "jangan pernah Rp 0" benar-benar diuji.

Gate ini TIDAK meninggalkan jejak: bahan ujinya bernama berawalan `POC53` sehingga dibuang
`scripts/_fixture53.py` (termasuk berkas bukti SP3K yang diunggah), dan kebersihannya ikut
diperiksa (D40).

Jalankan: python3 scripts/verify_contract_legal_docgen.py
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
    """Buang baris impor — nama yang hanya diimpor adalah kode mati, bukan pemakaian.

    Pelajaran `mutasi_51.py` (C10a) dan `mutasi_54.py`: memeriksa `"X" in src` tanpa ini
    membuat gate tetap hijau walau pemanggilan X dicabut, karena baris impor sudah memenuhi
    pencarian.
    """
    return "\n".join(ln for ln in src.split("\n")
                     if not ln.strip().startswith("import ")
                     and not re.match(r"^\s*}\s*from\s+[\"']", ln))


def fungsi(src: str, nama: str) -> str:
    """Badan SATU fungsi tingkat-modul (`def`/`async def` tanpa indentasi).

    Inti pelajaran uji-mutasi Fase 55: memeriksa berkas UTUH membuat gate ikut membaca
    bagian lain yang kebetulan menyebut nama yang sama, sehingga aturan bisa dimatikan di
    tempatnya sementara gate tetap hijau. Fungsi bersarang (mis. `add()` di dalam
    `build_breakdown`) tetap ikut karena ia memang bagian dari lingkup itu.
    """
    m = re.search(rf"^(?:async )?def {re.escape(nama)}\(", src, re.M)
    if not m:
        return ""
    ekor = src[m.end():]
    m2 = re.search(r"^(?:async def |def |class )", ekor, re.M)
    return src[m.start(): m.end() + (m2.start() if m2 else len(ekor))]


def opsi_kamus(ref_src: str, grup: str) -> set:
    """Kode yang TERDAFTAR pada satu grup Kamus Data (`_o("kode", "label")`)."""
    m = re.search(rf'"{grup}":\s*\{{', ref_src)
    if not m:
        return set()
    seg = ref_src[m.end():].split("\n    },")[0]
    return set(re.findall(r'_o\("([a-z_0-9]+)"', seg))


def d(r) -> str:
    try:
        return f"HTTP {r.status_code} {str(r.json())[:200]}"
    except Exception:
        return f"HTTP {r.status_code} {r.text[:200]}"


def j(r):
    try:
        return r.json()
    except Exception:
        return {}


def login(email: str) -> dict:
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": PW}, timeout=30)
    if r.status_code != 200:
        raise SystemExit(f"login {email} gagal: {d(r)}")
    return {"Authorization": f"Bearer {j(r)['access_token']}"}


# ================================================================ K. penjaga tingkat KODE
def bagian_k():
    head("K. Kode: aturan Fase 53 tidak boleh bisa dibatalkan tanpa gate ini merah")
    qe = strip_comments(read(BE / "quotation_engine.py"))
    sr = strip_comments(read(BE / "sales_reserve.py"))
    cc = strip_comments(read(BE / "customer_convert.py"))
    ce = strip_comments(read(BE / "contracts_engine.py"))
    kpr_src = strip_comments(read(BE / "kpr_engine.py"))
    ref53 = read(BE / "reference_p53.py")
    dg = strip_comments(read(BE / "docgen.py"))
    router = strip_comments(read(BE / "routers" / "contracts_router.py"))

    # --- SATU jalur reservasi (cacat 2)
    reserve = fungsi(sr, "reserve")
    check(bool(reserve), "K1 `sales_reserve.reserve()` ada — satu jalur reservasi bersama")
    # Penahanan unit harus ATOMIK: tanpa filter `status: "available"` dua permintaan
    # bersamaan bisa menjual satu rumah dua kali, dan tidak ada layar yang bisa
    # memperbaikinya sesudahnya.
    check('"status": "available"' in reserve
          and "find_one_and_update" in reserve
          and "raise ValueError" in reserve,
          "K1b unit ditahan ATOMIK (hanya berhasil bila unit MASIH tersedia)")
    check('"status": "reserved"' in reserve,
          "K1c reservasi menulis status `reserved` (satu bentuk deal untuk semua jalan)")
    check('stage="booking"' in reserve,
          "K1d reservasi memajukan tahap lead ke `booking` (bukti, bukan pilihan manual)")
    q_convert = fungsi(qe, "convert")
    check("sr.reserve(" in q_convert,
          "K2 penawaran memakai jalur reservasi yang SAMA (bukan membuat deal bentuk lain)")
    check(not re.search(r'"status"\s*:\s*"active"', qe),
          "K3 penawaran tidak lagi menulis deal `status=\"active\"` (bentuk deal tidak bercabang)",
          str(re.findall(r'"status"\s*:\s*"\w+"', qe)[:3]))

    # --- konversi lead → pembeli (cacat 1)
    konversi = fungsi(cc, "convert")
    dedup = fungsi(cc, "_dedup_customer")
    check(re.search(r"existing_contract\s*=\s*await db\.contracts\.find_one", konversi)
          is not None and '"created": False' in konversi,
          "K4 konversi IDEMPOTEN di kodenya (kontrak yang sudah ada dikembalikan apa adanya)")
    check(re.search(r'lc\.record\(\s*lead,\s*"won"', konversi) is not None,
          "K5 tahap lead diakhiri `won` (akhir domain lead, bukan status karangan)")
    check(bool(dedup) and '"nik"' in dedup and '"phone"' in dedup
          and dedup.index('"nik"') < dedup.index('"phone"'),
          "K6 dedup pembeli memakai NIK LEBIH DAHULU, baru telepon (satu manusia satu baris)")
    check('"lead_id": lead.get("id")' in konversi,
          "K6b pembeli baru menyimpan `lead_id` — tautan yang dulu tidak pernah ada")

    # --- kejujuran angka (aturan repo: jangan pernah 0 untuk yang tidak diketahui)
    rincian = fungsi(ce, "build_breakdown")
    check(re.search(r"int\(amount\)\s*if\s*amount\s*is not None\s*else\s*None", rincian)
          is not None,
          "K7 nominal yang belum diketahui TETAP None saat baris disusun (bukan 0)")
    check(re.search(r'state="filled"\s*if\s*val\s*is not None\s*else\s*"empty"', rincian)
          is not None,
          "K7b komponen biaya yang belum diisi berkeadaan `empty` (bukan `filled` bernilai 0)")
    check('"total_is_provisional": bool(empty)' in rincian,
          "K8 total ditandai SEMENTARA selama masih ada biaya yang belum diisi")

    # --- rantai legal & akad kredit (cacat 3)
    gates = fungsi(ce, "legal_gates")
    check("akad_kredit" in opsi_kamus(ref53, "contract_legal_stage")
          and re.search(r'LEGAL_ORDER\s*=\s*\([^)]*"akad_kredit"', ce) is not None,
          "K9 `akad_kredit` ada di Kamus Data DAN di urutan legal (dulu tidak ada sama sekali)")
    check('ref.label_of("legal_block"' in gates,
          "K10 sebab 'kenapa belum boleh' berlabel dari Kamus Data, bukan kalimat bebas")
    legal_dipakai = set(re.findall(r'b\.append\(\("([a-z_0-9]+)"', gates))
    legal_terdaftar = opsi_kamus(ref53, "legal_block")
    check(bool(legal_dipakai) and legal_dipakai <= legal_terdaftar,
          "K10b setiap kode penahan legal yang DIPAKAI kode terdaftar di Kamus Data",
          f"tak terdaftar: {sorted(legal_dipakai - legal_terdaftar)}")
    convert_dipakai = set(re.findall(r'_blk\("([a-z_0-9]+)"', cc))
    convert_terdaftar = opsi_kamus(ref53, "convert_block")
    check('ref.label_of("convert_block"' in cc,
          "K11 sebab penolakan konversi juga berlabel dari Kamus Data (`convert_block`)")
    check(bool(convert_dipakai) and convert_dipakai <= convert_terdaftar,
          "K11b setiap kode penahan konversi terdaftar di Kamus Data (SSOT tidak bercabang)",
          f"tak terdaftar: {sorted(convert_dipakai - convert_terdaftar)}")
    docgen_dipakai = set(re.findall(r'blocks\.append\(\("([a-z_0-9]+)"', dg))
    docgen_terdaftar = opsi_kamus(ref53, "docgen_block")
    check(bool(docgen_dipakai) and docgen_dipakai <= docgen_terdaftar,
          "K11c setiap kode penahan dokumen terdaftar di Kamus Data",
          f"tak terdaftar: {sorted(docgen_dipakai - docgen_terdaftar)}")
    check(re.search(r'sp3k\.get\("file_id"\)\s*and\s*int\(app\.get\("approved_plafon"\)',
                    gates) is not None,
          "K12 gerbang akad kredit MEMBACA syarat SP3K (berkas + plafon disetujui)")
    check(re.search(r'if bd\.get\("has_excess_land"\):', gates) is not None
          and "_spkt_exists" in gates,
          "K12b akad kredit menuntut SPKT bila ada kelebihan tanah `[DOC]`")
    check("_excess_land_paid" in gates,
          "K12c kelebihan tanah wajib LUNAS sebelum akad kredit `[DOC]`")
    kpr_stage = fungsi(kpr_src, "kpr_advance")
    check('if not payload.get("file_id")' in kpr_stage
          and 'if not int(payload.get("plafon") or 0)' in kpr_stage,
          "K13 tahap SP3K menuntut BERKAS + plafon yang DISETUJUI bank")
    check(re.search(r'sp3k\.get\("file_id"\)\s*and\s*int\(app\.get\("approved_plafon"\)',
                    kpr_stage) is not None,
          "K13b akad kredit memeriksa ULANG SP3K di mesin KPR (jalur yang HTTP tak bisa capai)")

    # --- dokumen owner (cacat 4)
    nomor = fungsi(dg, "next_doc_number")
    check("ROMAN[month]" in nomor,
          "K14 nomor dokumen memakai bulan ROMAWI sesuai format dokumen asli owner")
    check("next_seq" in nomor,
          "K14b nomor urut dari mesin urutan (bukan hitungan dokumen yang bisa berulang)")
    uang = fungsi(dg, "_rp")
    check(re.search(r"if v is None:\s*\n\s*return BELUM", uang) is not None,
          "K15 biaya yang belum diisi dicetak 'belum ditetapkan' — BUKAN Rp 0")
    terap = fungsi(dg, "applicable")
    check('contract.get("scheme") != scheme' in terap and "skema_tidak_cocok" in terap,
          "K16 varian dokumen ditentukan SKEMA kontrak (dokumen tidak boleh bertentangan)")

    # --- RBAC: pemisahan tugas ada di ROUTER, bukan hanya di dokumen
    biaya_seg = router.split('@router.post("/contracts/{contract_id}/costs")')[-1][:400]
    legal_seg = router.split('@router.post("/contracts/{contract_id}/legal/{stage}")')[-1][:400]
    check('require_permission("contracts", "update")' in biaya_seg,
          "K17 mengisi komponen biaya butuh izin `contracts:update` (Keuangan)")
    check('require_permission("contracts", "manage")' in legal_seg,
          "K17b memajukan tahap legal butuh izin `contracts:manage` (bukan pengisi angka)")

    # --- frontend: layar tidak boleh mengarang & tidak boleh mengetik ulang label
    panel = strip_imports(strip_comments(read(FE / "components" / "contracts" /
                                              "ContractPanel.js")))
    kpr = strip_imports(strip_comments(read(FE / "components" / "contracts" / "KprPanel.js")))
    check("r.amount === null" in panel and "state_label" in panel,
          "K18 layar kontrak menulis keadaan 'belum diisi' untuk biaya kosong (bukan Rp 0)")
    # Regresi yang BARU ditutup di Fase 54 (temuan gate audit_forms_deep yang menganggur
    # sejak Fase 53): field Bank wajib dipilih dari Kamus Data, bukan diketik bebas.
    check("ReferenceSelect" in kpr and "financing_bank" in kpr,
          "K19 field Bank pada panel KPR memakai dropdown SSOT `financing_bank`")
    check(not re.search(r'<Input[^>]*id="kpr-bank"', kpr),
          "K19b field Bank BUKAN lagi kotak teks bebas (empat ejaan 'BTN' = empat bank)")

    # --- testId Fase 53 tidak boleh mati
    ids = dict(re.findall(r"(\w+):\s*\"([^\"]+)\"", read(FE / "constants" / "testIds" /
                                                         "p53.js")))
    semua = ""
    for p in FE.rglob("*.js"):
        if "constants/testIds" in str(p):
            continue
        semua += read(p)
    mati = [k for k, v in ids.items() if f"P53.{k}" not in semua and v not in semua]
    check(len(ids) >= 20, "K20 testId Fase 53 terdaftar", str(len(ids)))
    check(not mati, "K20b tidak ada testId Fase 53 yang MATI (tiap id dipakai layar)",
          str(mati))

    # ------------------------------------------------------------------ Fase 56
    # Tiga cacat berikut LOLOS dari gate versi Fase 55 dan baru tertangkap saat rantai ini
    # dijalankan manusia di peramban. Ketiganya sejenis: layar MENJANJIKAN atau MENGATAKAN
    # sesuatu yang tidak benar — dan tidak satu pun bisa terlihat dari uji HTTP.

    # (1) Janji "dibawa ke kontrak yang baru lahir" harus ditepati. `TabPage` membaca satu
    #     penanda saja; menulis `?hub=` pada halaman yang membaca `?tab=` membuat pemakai
    #     mendarat di tab PERTAMA (Ringkasan) tanpa ada yang berteriak.
    prof = strip_comments(read(FE / "pages" / "CustomerProfilePage.js"))
    m_par = re.search(r'<TabPage[^>]*paramKey="(\w+)"', prof)
    penanda = m_par.group(1) if m_par else "tab"
    kunci_tab = set(re.findall(r'key:\s*"([a-z0-9_]+)"', prof))
    tautan = []
    for p in FE.rglob("*.js"):
        for pen, kun in re.findall(r"/customers/\$\{[^}]+\}\?(\w+)=([a-z0-9_]+)",
                                   strip_comments(read(p))):
            tautan.append((p.name, pen, kun))
    check(bool(tautan) and bool(kunci_tab),
          "K21 ada tautan layar yang menyebut tab tujuan pada profil pembeli", str(tautan))
    salah = [t for t in tautan if t[1] != penanda or t[2] not in kunci_tab]
    check(not salah,
          f"K21b tautan profil pembeli memakai penanda `?{penanda}=` + kunci tab yang ADA "
          "(janji 'dibawa ke Kontrak & Legal' ditepati)", str(salah))

    # (2) Bahasa layar & dokumen: kode kolom bukan bahasa manusia.
    check('empty_labels = [r["label"] for r in cost_rows if r["state"] == "empty"]' in rincian,
          "K22 rincian biaya menyiapkan LABEL manusia untuk komponen yang belum diisi")
    check('", ".join(empty_labels)' in rincian,
          "K22b catatan total memakai `empty_labels` (bukan daftar kode kolom)")
    ctx_fn = fungsi(dg, "build_context")
    terap2 = fungsi(dg, "applicable")
    check("costs_incomplete_labels" in ctx_fn
          and "', '.join(bd['costs_incomplete'])" not in ctx_fn,
          "K23 catatan 'total sementara' pada DOKUMEN memakai label manusia "
          "(pembeli menandatangani kalimat itu)")
    check("costs_incomplete_labels" in terap2
          and "', '.join(bd['costs_incomplete'])" not in terap2,
          "K23b peringatan panel dokumen juga memakai label manusia")
    check("costs_incomplete_labels" in panel
          and not re.search(r"\(bd\.costs_incomplete \|\| \[\]\)\.join", panel),
          "K24 spanduk 'masih SEMENTARA' di layar memakai label manusia")

    # (3) "Tidak ada" vs "bukan milik Anda" tidak boleh diceritakan sama.
    daftar_seg = router.split('@router.get("/contracts")')[-1].split("@router.")[0]
    check("is_scoped_sales" in daftar_seg and "di_luar_lingkup" in daftar_seg
          and "tersembunyi" in daftar_seg,
          "K25 daftar kontrak MENYEBUT bila baris disembunyikan lingkup data (tidak senyap)")
    check('state.reasonCode === "di_luar_lingkup"' in panel
          and "P53.contractScoped" in panel,
          "K25b layar kontrak membedakan 'belum ada' dari 'di luar lingkup Anda'")


# ================================================================ D. bukti HTTP
def bagian_d():
    head("D. Bukti HTTP: rantai lead → pembeli → kontrak → dokumen benar-benar jalan")
    sa = login("superadmin@sipro.co.id")
    fin = login("finance@sipro.co.id")
    sales = login("sales@sipro.co.id")
    tanda = str(int(time.time()))[-6:]
    nik = f"3299{tanda}00001"

    units = j(requests.get(f"{BASE}/units", headers=sa,
                           params={"status": "available", "limit": 6}, timeout=30)).get("data") or []
    if not check(len(units) >= 3, "D0 ada minimal 3 unit tersedia untuk bahan uji",
                 f"{len(units)} unit"):
        return

    def lead_baru(judul: str, ekor: str) -> dict:
        return j(requests.post(f"{BASE}/leads", headers=sa, timeout=30, json={
            "name": f"POC53 Gate46 {judul} {tanda}", "phone": f"62{ekor}{tanda}",
            "source": "walk_in"})).get("data") or {}

    # --- deal yang SENGAJA belum di-booking: pratinjau DAN server harus MENOLAK
    lead_a = lead_baru("Belum Booking", "899")
    da = requests.post(f"{BASE}/deals/reserve", headers=sa, timeout=30,
                       json={"lead_id": lead_a.get("id"), "unit_id": units[0]["id"],
                             "booking_fee": 5000000})
    deal_a = j(da).get("data") or {}
    check(da.status_code == 200 and deal_a.get("status") == "reserved",
          "D1 reservasi melahirkan deal berstatus 'reserved' (bentuk deal tidak bercabang)",
          d(da))
    check(bool(deal_a.get("reserved_until")), "D2 masa keep unit (reserved_until) terisi")

    # Penahanan ATOMIK: unit yang sama tidak boleh bisa direservasi dua kali. Tanpa ini
    # satu rumah bisa dijanjikan kepada dua pembeli dan tidak ada layar yang bisa
    # membatalkan janji kedua.
    lead_x = lead_baru("Rebutan Unit", "897")
    dx = requests.post(f"{BASE}/deals/reserve", headers=sa, timeout=30,
                       json={"lead_id": lead_x.get("id"), "unit_id": units[0]["id"],
                             "booking_fee": 5000000})
    check(dx.status_code != 200,
          "D3 unit yang sudah direservasi TIDAK bisa direservasi lagi (penahanan atomik)",
          d(dx))
    la0 = j(requests.get(f"{BASE}/leads/{lead_a.get('id')}", headers=sa,
                         timeout=30)).get("data") or {}
    check(la0.get("stage") == "booking",
          "D4 tahap lead maju ke 'booking' dari BUKTI reservasi (bukan pilihan manual)",
          str(la0.get("stage")))

    pre = requests.get(f"{BASE}/deals/{deal_a.get('id')}/convert-preview", headers=sa,
                       timeout=30)
    pd = j(pre).get("data") or {}
    blocks = pd.get("blocks") or []
    kode = [b.get("code") if isinstance(b, dict) else str(b) for b in blocks]
    check(pd.get("can_convert") is False,
          "D5 deal yang BELUM di-booking tidak boleh dikonversi (bukti dulu, status kemudian)",
          d(pre))
    check(any("booking" in str(b) for b in kode),
          "D6 sebab penolakan memakai kode SSOT yang menyebut booking", str(kode))
    # `ref.label_of()` mengembalikan KODEnya sendiri bila kode itu tidak terdaftar di Kamus
    # Data. Jadi `label == code` bukan soal rapi: itu bukti SSOT bercabang, dan layar akan
    # menampilkan `deal_belum_booking` kepada pemakai.
    check(bool(blocks) and all(isinstance(b, dict) and b.get("label")
                               and b.get("label") != b.get("code") for b in blocks),
          "D7 sebab penolakan punya LABEL manusia dari Kamus Data (bukan kode mentah)",
          str([(b.get("code"), b.get("label")) for b in blocks][:3]))
    tolak = requests.post(f"{BASE}/deals/{deal_a.get('id')}/convert", headers=sa, timeout=30,
                          json={"scheme": "cash_keras"})
    check(tolak.status_code == 400,
          "D8 SERVER menolak konversi deal yang belum di-booking (bukan hanya pratinjau)",
          d(tolak))

    # --- jalur lengkap: booking → SLIK berbukti → konversi → kontrak (skema KPR)
    lead_b = lead_baru("KPR", "898")
    # Gerbang SPR (`slik.gate = before_spr`, bawaan Pusat Konfigurasi) menuntut pra-skrining
    # SLIK yang lolos BERBUKTI — dilalui lewat API nyata, bukan dengan mematikan konfigurasinya.
    ev = requests.post(f"{BASE}/files/upload", headers=sa, timeout=120,
                       files={"file": ("ideb-gate46.pdf", b"%PDF-1.4 iDeb SLIK simulasi gate 46\n",
                                       "application/pdf")},
                       data={"owner_type": "lead", "owner_id": lead_b.get("id"), "optimize": "false"})
    fid = (j(ev).get("data") or {}).get("id")
    sk = requests.post(f"{BASE}/leads/{lead_b.get('id')}/slik-prescreen", headers=sa, timeout=30,
                       json={"status": "clear", "note": "Kolektibilitas 1 (gate 46)",
                             "evidence_file_ids": [fid]})
    check(ev.status_code == 200 and sk.status_code == 200,
          "D8b pra-skrining SLIK lolos BERBUKTI lewat API (gerbang SPR dilalui, bukan dimatikan)",
          f"{ev.status_code}/{sk.status_code} {sk.text[:100]}")
    db_ = requests.post(f"{BASE}/deals/reserve", headers=sa, timeout=30,
                        json={"lead_id": lead_b.get("id"), "unit_id": units[1]["id"],
                              "booking_fee": 5000000})
    deal_b = j(db_).get("data") or {}
    did = deal_b.get("id")
    requests.post(f"{BASE}/booking-fee/deals/{did}/pay", headers=sa, timeout=30,
                  json={"amount": 5000000, "method": "transfer"})
    bk = requests.post(f"{BASE}/deals/{did}/book", headers=sa, json={}, timeout=30)
    check(bk.status_code == 200, "D9 booking dikonfirmasi", d(bk))

    cv = requests.post(f"{BASE}/deals/{did}/convert", headers=sa, timeout=30,
                       json={"scheme": "kpr", "nik": nik,
                             "address": "Jl. Gate 46, Sumedang"})
    check(cv.status_code == 200, "D10 lead MENJADI pembeli (customers + contracts lahir)",
          d(cv))
    out = j(cv).get("data") or {}
    cust = out.get("customer") or {}
    contract = out.get("contract") or {}
    cid = contract.get("id")
    check(cust.get("lead_id") == lead_b.get("id")
          or lead_b.get("id") in (cust.get("lead_ids") or []),
          "D11 pembeli TERTAUT ke lead (tautan yang dulu tidak pernah ada untuk data nyata)",
          f"{cust.get('lead_id')} / {cust.get('lead_ids')}")
    check(bool(contract.get("number")), "D12 kontrak punya nomor", str(contract.get("number")))
    cv2 = requests.post(f"{BASE}/deals/{did}/convert", headers=sa, json={}, timeout=30)
    check(cv2.status_code == 200 and (j(cv2).get("data") or {}).get("created") is False,
          "D13 konversi IDEMPOTEN (dua kali jalan tidak melahirkan kontrak kembar)", d(cv2))
    la = j(requests.get(f"{BASE}/leads/{lead_b.get('id')}", headers=sa,
                        timeout=30)).get("data") or {}
    check(la.get("stage") == "won", "D14 tahap lead menjadi 'won' (akhir domain lead)",
          str(la.get("stage")))
    if not cid:
        return

    # Pengajuan KPR harus lahir BERSAMA kontrak KPR (D9 Dok 26). Uji-mutasi Fase 55 (M14)
    # membuktikan versi pertama gate ini tidak memeriksanya: `kpr_advance()` memanggil
    # `ensure_kpr_app()` sendiri, jadi seluruh rantai tahap tetap jalan walau konversi tidak
    # pernah membuka pengajuan. Akibat nyata yang lolos: layar KPR pembeli KOSONG sampai ada
    # orang yang menekan tombol tahap — padahal kontraknya sudah berskema KPR.
    kv = requests.get(f"{BASE}/contracts/{cid}/kpr", headers=sa, timeout=30)
    kd = j(kv).get("data") or {}
    app = kd.get("application") or {}
    check(kd.get("applicable") is True and bool(app)
          and app.get("kpr_stage") == "berkas_lengkap"
          and kd.get("next_stage") == "diajukan_ke_bank"
          and bool(kd.get("stage_label")) and kd.get("stage_label") != kd.get("stage"),
          "D14b konversi skema KPR LANGSUNG membuka pengajuan KPR (tahap 'berkas lengkap')",
          f"{kv.status_code} applicable={kd.get('applicable')} "
          f"stage={app.get('kpr_stage')} next={kd.get('next_stage')}")

    # --- kejujuran angka
    det = requests.get(f"{BASE}/contracts/{cid}", headers=sa, timeout=30)
    bd = (j(det).get("data") or {}).get("breakdown") or {}
    rows = bd.get("rows") or []
    codes = [r.get("code") for r in rows]
    check(all(c in codes for c in ("UNIT_PRICE", "BOOKING_FEE", "BPHTB", "NOTARY_FEE")),
          "D15 setiap komponen adalah BARIS tersendiri (tidak dilebur ke harga unit)",
          str(codes))
    kosong = [r for r in rows if r.get("state") == "empty"]
    check(bool(kosong) and all(r.get("amount") is None for r in kosong),
          "D16 biaya yang belum diketahui bernilai null — BUKAN Rp 0",
          str([(r.get("code"), r.get("amount")) for r in rows if r.get("group") == "biaya"][:5]))
    check(bd.get("total_is_provisional") is True,
          "D17 total ditandai SEMENTARA selama ada biaya yang belum diisi")

    # --- gerbang bukti tahap legal & KPR (uji NEGATIF)
    r = requests.post(f"{BASE}/contracts/{cid}/legal/ppjb", headers=sa, json={}, timeout=30)
    check(r.status_code == 400, "D18 PPJB DITOLAK sebelum DP terbayar", d(r))

    # Bukti SP3K + dua tahap KPR di depannya dibereskan LEBIH DAHULU. Kalau tidak, uji
    # negatif di bawah ini akan LULUS karena alasan yang salah: versi pertama gate ini
    # mengira "SP3K ditolak tanpa berkas" padahal yang menolak adalah gerbang URUTAN
    # ("Tahap sebelumnya belum selesai: Diajukan ke bank") — gerbang berkasnya sendiri tidak
    # pernah tersentuh. Uji-mutasi Fase 55 membuka kebohongan itu.
    up = requests.post(f"{BASE}/files/upload", headers=sa, timeout=60,
                       files={"file": ("POC53-sp3k.pdf", b"%PDF-1.4 POC53 SP3K bukti uji",
                                       "application/pdf")},
                       data={"owner_type": "contract", "owner_id": cid, "doc_type": "SP3K",
                             "optimize": "false"})
    fid = (j(up).get("data") or {}).get("id")
    for tahap, badan in (("diajukan_ke_bank", {"bank": "Bank BTN"}),
                         ("appraisal", {"amount": 200000000})):
        requests.post(f"{BASE}/contracts/{cid}/kpr/stage/{tahap}", headers=sa, json=badan,
                      timeout=30)
    r = requests.post(f"{BASE}/contracts/{cid}/kpr/stage/sp3k", headers=sa,
                      json={"plafon": 150000000}, timeout=30)
    check(r.status_code == 400 and "berkas" in str(j(r).get("detail") or "").lower(),
          "D19 SP3K DITOLAK tanpa berkas bukti — dan sebab yang disebut MEMANG soal berkas",
          d(r))
    r = requests.post(f"{BASE}/contracts/{cid}/kpr/stage/akad_kredit", headers=sa,
                      json={}, timeout=30)
    check(r.status_code == 400 and "sp3k" in str(j(r).get("detail") or "").lower(),
          "D20 akad kredit DITOLAK sebelum SP3K sah — dan sebabnya menyebut SP3K", d(r))

    # --- pemisahan tugas: siapa boleh mengisi angka, siapa boleh memajukan tahap legal
    r = requests.post(f"{BASE}/contracts/{cid}/costs", headers=sales,
                      json={"bphtb": 1}, timeout=30)
    check(r.status_code == 403, "D21 sales TIDAK boleh mengisi komponen biaya kontrak", d(r))
    r = requests.post(f"{BASE}/contracts/{cid}/legal/ppjb", headers=sales, json={},
                      timeout=30)
    check(r.status_code == 403, "D22 sales TIDAK boleh memajukan tahap legal", d(r))
    r = requests.post(f"{BASE}/contracts/{cid}/legal/ppjb", headers=fin, json={}, timeout=30)
    check(r.status_code == 403,
          "D23 Keuangan yang MENGISI angka tidak boleh memajukan tahap legal (pemisahan tugas)",
          d(r))

    # --- dokumen pada keadaan "biaya belum lengkap": di sinilah aturan "jangan Rp 0" diuji
    r = requests.post(f"{BASE}/contracts/{cid}/costs", headers=fin, timeout=30,
                      json={"plafon_kredit": 160340000})
    check(r.status_code == 200, "D24 Keuangan boleh mengisi komponen biaya (plafon dulu)",
          d(r))
    doc0 = requests.post(f"{BASE}/contracts/{cid}/documents", headers=sa,
                         json={"template_code": "SPR_KPR"}, timeout=60)
    isi0 = str((j(doc0).get("data") or {}).get("content") or "")
    from bs4 import BeautifulSoup
    paragraphs0 = BeautifulSoup(isi0, "html.parser").find_all("p")
    lines0 = [p.get_text() for p in paragraphs0] if paragraphs0 else isi0.split("\n")
    baris0 = [ln for ln in lines0 if ln.strip().startswith("BPHTB")]
    check(doc0.status_code == 200 and bool(baris0)
          and all("belum ditetapkan" in ln for ln in baris0),
          "D25 dokumen yang dicetak SEBELUM biaya lengkap berbunyi 'belum ditetapkan'",
          f"{doc0.status_code} {baris0[:2]}")
    warn = (j(doc0).get("data") or {}).get("warnings") or []
    check(bool(warn) or "SEMENTARA" in isi0,
          "D26 dokumen sementara menyebut dirinya belum lengkap (peringatan/catatan total)",
          str(warn)[:120])

    # --- Fase 56: kode kolom tidak boleh sampai ke mata manusia
    KODE = re.compile(r"\b(BPHTB|NOTARY_FEE|BANK_FEE|INSURANCE|PPH_SELLER|PROMO_DISCOUNT|"
                      r"PLAFON_KREDIT|UNIT_PRICE|BOOKING_FEE)\b")
    r_bd = requests.get(f"{BASE}/contracts/{cid}", headers=sa, timeout=30)
    bd0 = (j(r_bd).get("data") or {}).get("breakdown") or {}
    label0 = bd0.get("costs_incomplete_labels")
    check(isinstance(label0, list) and len(label0) == len(bd0.get("costs_incomplete") or []),
          "D26b rincian membawa daftar LABEL sepanjang daftar kodenya", str(label0))
    # "BPHTB" memang label sah (nama pajaknya begitu); yang dilarang adalah kode ber-garis
    # bawah seperti NOTARY_FEE — nama kolom database yang tidak berarti apa pun bagi pembeli.
    kode_bocor = [s for s in (label0 or []) if "_" in s and s.upper() == s]
    check(not kode_bocor, "D26c daftar komponen belum-diisi memakai label manusia",
          str(kode_bocor))
    catatan = str(bd0.get("note") or "")
    check(bool(catatan) and not re.search(r"\b[A-Z]+_[A-Z_]+\b", catatan),
          "D26d catatan 'total masih SEMENTARA' bebas dari kode kolom", catatan[:160])
    baris_total = [ln for ln in isi0.split("\n") if "SEMENTARA" in ln]
    check(bool(baris_total) and not any(re.search(r"\b[A-Z]+_[A-Z_]+\b", ln)
                                       for ln in baris_total),
          "D26e catatan pada DOKUMEN yang ditandatangani pembeli bebas dari kode kolom",
          str(baris_total)[:200])
    check(bool(warn) and not any(re.search(r"\b[A-Z]+_[A-Z_]+\b", w) for w in warn),
          "D26f peringatan panel dokumen bebas dari kode kolom", str(warn)[:200])

    # --- Fase 56: "tidak ada" vs "bukan lingkup Anda" (layar tidak boleh berbohong)
    r_scope = requests.get(f"{BASE}/contracts", headers=sales,
                           params={"customer_id": cust.get("id")}, timeout=30)
    js = j(r_scope)
    check(r_scope.status_code == 200 and js.get("data") == [],
          "D26g sales di luar lingkup memang TIDAK menerima isi kontrak", d(r_scope))
    check(js.get("reason_code") == "di_luar_lingkup" and "lingkup" in str(js.get("reason")),
          "D26h ...tetapi diberi SEBAB ('ada, di luar lingkup Anda'), bukan senyap kosong",
          str(js.get("reason_code")))
    check(str(js.get("reason") or "").find(str(contract.get("number") or "@@")) < 0,
          "D26i sebab lingkup TIDAK membocorkan nomor kontrak milik rekan lain",
          str(js.get("reason")))

    r = requests.post(f"{BASE}/contracts/{cid}/costs", headers=fin, timeout=30, json={
        "bphtb": 4300000, "notary_fee": 13200000, "bank_fee": 10500000,
        "insurance": 2500000, "pph_seller": 0, "promo_discount": 0,
        "plafon_kredit": 160340000})
    check(r.status_code == 200, "D27 Keuangan melengkapi seluruh komponen biaya", d(r))
    bd2 = (j(r).get("data") or {}).get("breakdown") or {}
    check(bd2.get("total_is_provisional") is False,
          "D28 total tidak lagi 'sementara' setelah semua biaya diisi",
          str(bd2.get("costs_incomplete")))

    # --- dokumen owner: varian mengikuti SKEMA, dan bisa dicetak
    av = requests.get(f"{BASE}/contracts/{cid}/documents/available", headers=sa, timeout=30)
    ad = {a.get("code"): a for a in j(av).get("data") or []}
    check(j(av).get("recommended_code") == "SPR_KPR",
          "D29 varian SPR ditentukan SKEMA kontrak (bukan pilihan bebas)",
          str(j(av).get("recommended_code")))
    check(ad.get("SPR_CASH", {}).get("can_generate") is False,
          "D30 SPR Cash DITOLAK untuk kontrak KPR (dokumen tidak boleh bertentangan)",
          str(ad.get("SPR_CASH", {}).get("blocks")))
    doc = requests.post(f"{BASE}/contracts/{cid}/documents", headers=sa,
                        json={"template_code": "SPR_KPR"}, timeout=60)
    check(doc.status_code == 200, "D31 SPR KPR diterbitkan", d(doc))
    sdoc = j(doc).get("data") or {}
    num = str(sdoc.get("doc_number") or "")
    bagian = num.split("/")
    check(num.count("/") == 4 and "SPR-KPR" in num,
          "D32 nomor mengikuti format owner {urut}/{kode}/{proyek}/{romawi}/{tahun}", num)
    check(len(bagian) == 5 and re.fullmatch(r"[IVX]{1,4}", bagian[3]) is not None,
          "D33 bulan pada nomor dokumen ditulis ROMAWI (bukan angka)", num)
    isi = str(sdoc.get("content") or "")
    check("Rp 160.340.000" in isi, "D34 plafon kredit DARI KONTRAK ikut tercetak",
          str([ln for ln in isi.split("\n") if "Plafon" in ln][:1]))
    paragraphs = BeautifulSoup(isi, "html.parser").find_all("p")
    lines = [p.get_text() for p in paragraphs] if paragraphs else isi.split("\n")
    biaya = [ln for ln in lines if ln.strip().startswith(("BPHTB", "Biaya notaris"))]
    check(bool(biaya) and all("belum ditetapkan" not in ln for ln in biaya),
          "D35 biaya yang SUDAH diisi tidak lagi berbunyi 'belum ditetapkan'", str(biaya))
    pdf = requests.get(f"{BASE}/documents/{sdoc.get('id')}/pdf", headers=sa, timeout=60)
    check(pdf.status_code == 200
          and pdf.headers.get("content-type", "").startswith("application/pdf")
          and len(pdf.content) > 1500,
          "D36 dokumen BISA DICETAK (PDF berisi)",
          f"{pdf.status_code} {pdf.headers.get('content-type')} {len(pdf.content)}b")

    # --- gerbang bukti yang MENERIMA bukti (kalau tidak, "menolak" bisa berarti fitur mati)
    r = requests.post(f"{BASE}/contracts/{cid}/kpr/stage/sp3k", headers=sa, timeout=30,
                      json={"file_id": fid, "plafon": 0, "number": f"SP3K/{tanda}"})
    check(r.status_code == 400,
          "D37 SP3K DITOLAK bila plafon yang DISETUJUI bank belum diisi (berkas saja tak cukup)",
          d(r))
    r = requests.post(f"{BASE}/contracts/{cid}/kpr/stage/sp3k", headers=sa, timeout=30,
                      json={"file_id": fid, "plafon": 160340000, "number": f"SP3K/{tanda}",
                            "tenor_months": 180, "rate": 5.5})
    check(r.status_code == 200 and bool(fid),
          "D38 SP3K DITERIMA bersama berkas + plafon (gerbang bukti, bukan fitur mati)", d(r))
    r = requests.post(f"{BASE}/contracts/{cid}/kpr/stage/akad_kredit", headers=sa, timeout=30,
                      json={"notary": "Notaris Uji Gate46", "place": "Sumedang"})
    check(r.status_code == 200,
          "D39 akad kredit DITERIMA setelah SP3K sah (peristiwa penentu skema KPR tercatat)",
          d(r))

    # --- satu manusia satu baris pembeli: NIK yang sama tidak melahirkan pembeli kembar
    lead_c = lead_baru("Unit Kedua", "896")
    dc = requests.post(f"{BASE}/deals/reserve", headers=sa, timeout=30,
                       json={"lead_id": lead_c.get("id"), "unit_id": units[2]["id"],
                             "booking_fee": 5000000})
    dcid = (j(dc).get("data") or {}).get("id")
    requests.post(f"{BASE}/booking-fee/deals/{dcid}/pay", headers=sa, timeout=30,
                  json={"amount": 5000000, "method": "transfer"})
    requests.post(f"{BASE}/deals/{dcid}/book", headers=sa, json={}, timeout=30)
    cv3 = requests.post(f"{BASE}/deals/{dcid}/convert", headers=sa, timeout=30,
                        json={"scheme": "cash_keras", "nik": nik,
                              "address": "Jl. Gate 46 No. 2, Sumedang"})
    cust3 = (j(cv3).get("data") or {}).get("customer") or {}
    check(cv3.status_code == 200 and cust3.get("id") == cust.get("id"),
          "D40 pembeli lama (NIK sama) membeli unit kedua TANPA baris pembeli kembar",
          f"{cv3.status_code} {cust3.get('id')} vs {cust.get('id')}")


def main() -> int:
    print("=" * 78)
    print("GATE 46 — KONTRAK PEMBELI, TAHAP LEGAL & DOKUMEN OWNER (Fase 53)")
    print("=" * 78)
    try:
        requests.get(f"{BASE}/health", timeout=10)
    except Exception as e:
        print(f"Backend tidak menjawab: {e}")
        return 1
    bagian_k()
    try:
        bagian_d()
    finally:
        head("Bahan uji dibuang tanpa sisa")
        import _fixture53
        hasil = _fixture53.purge()
        sisa = _fixture53.purge(dry=True)
        bersih = all(v == 0 for k, v in sisa.items() if isinstance(v, int))
        check(bersih, "D41 bahan uji gate dibuang bersih (tanpa jurnal/penawaran/tugas yatim)",
              f"dibuang={hasil} sisa={sisa}")

    print("\n" + "-" * 78)
    if FAIL:
        print(f"GATE 46 MERAH — {len(FAIL)} gagal / {PASSED + len(FAIL)} pemeriksaan")
        for f in FAIL:
            print(f"  - {f}")
        return 1
    print(f"GATE 46 HIJAU — {PASSED} pemeriksaan")
    return 0


if __name__ == "__main__":
    sys.exit(main())
