# Rencana Development SIPRO — Fase 49 (Penutupan Buku, Laporan Owner, Pajak & Kepatuhan)

Problem statement (verbatim):
> "saya ingin anda lanjutkan development dari repo ini https://github.com/kahshdhdj/sipro — development sebelumnya berhenti disini saya ingin anda lanjutkan.
> Action: search_replace ke /app/backend/settings_store.py (menambah grup \"pajak\": \"Pajak & Kepatuhan\")
> Action: create_file /app/backend/tax_faktur_export.py — 'Faktur pajak keluaran v2 (Fase 49E) — pengganti, pembatalan, dan EKSPOR berkas' (faktur pengganti, pembatalan beralasan, ekspor XML Coretax + CSV, export hold bila NPWP kurang, rekap SPT Masa PPN)."

Status saat ini (terverifikasi di container, 21 Agu):
- Repo **sudah dipulihkan penuh** ke `/app` (backend: **168** file `.py`, frontend: **480** file `.js`).
- Dependensi backend+frontend terpasang. Catatan: backend membutuhkan `reportlab` (untuk PDF) dan `APScheduler` (scheduler) — keduanya sudah tersedia.
- Backend & frontend **RUNNING**.
- `.env` tidak ikut git → `JWT_SECRET` dan `PORTAL_MASTER_OTP=000000` telah ditambahkan ke `/app/backend/.env` agar login stabil.
- **Fase 49 backend SUDAH LUNAS & tersambung** (49A–49G): engines + routers + RBAC sudah ada.
- **POC Fase 49 SUDAH LULUS**: `python3 poc/poc_49.py` → **PASS, 96 pemeriksaan hijau**, cleanup bersih (tidak ada jurnal/dokumen menggantung).
- `backend/reference.py::_PHASES` sudah memuat **49** → SSOT/label fase49 sudah termuat (bug laten sudah beres).

**Artefak Fase 49 yang SUDAH ada dan bekerja (backend):**
- Engines:
  - `backend/closing_engine.py` (49A/49B): `close_check`, `close_period` (hold+override), `year_check`, `year_close` (idempoten), `year_reopen` (reversal), `year_list`.
  - `backend/gl_project_cash.py` (49C): `cash_flow_projects` + tie-out.
  - `backend/owner_pack.py` (49D): `owner_pack`, `closing_history`.
  - `backend/tax_faktur_export.py` (49E/49G): faktur replace/cancel, export **XML Coretax + CSV**, guard hold bila NPWP kurang, `vat_return`.
  - `backend/withholding_engine.py` (49F): issue/correct/cancel, PDF, export + tie-out.
- Models/SSOT/config:
  - `backend/models_p49.py` (termasuk `BillPayWithholding`).
  - `backend/reference_p49.py` (SSOT groups 49).
  - `backend/settings_store.py` (grup **pajak** + keys: `tax.company_npwp`, `tax.company_idtku`, `tax.pph23_rate`, `tax.pph4_2_konstruksi_rate`, `tax.bupot_series`).
  - `backend/tax_ids.py`.

**Endpoint Fase 49 yang SUDAH tersambung (ringkas):**
- `gl_reports_router`:
  - `GET /api/gl/periods`
  - `GET /api/gl/periods/close-check`
  - `POST /api/gl/periods/close`
  - `POST /api/gl/periods/reopen`
  - `GET /api/gl/year` + `GET /api/gl/year/check`
  - `POST /api/gl/year/close` + `POST /api/gl/year/reopen`
  - `GET /api/gl/reports/cash-flow-projects`
  - `GET /api/gl/reports/owner-pack`
  - `GET /api/gl/reports/closing-history`
- `tax_compliance_router` (semua di prefix `/api/tax/compliance/...`):
  - Faktur: list/periods, replace/cancel
  - Export: `/faktur-export/check` + `/faktur-export/file`
  - VAT return: `/vat-return` + `/periods`
  - Withholding (e-Bupot): list/summary/candidates/config, export check+file, issue/from-fee/correct/cancel, detail+pdf
- `ap_router`:
  - `POST /api/ap/bills/{id}/pay-withholding`

**GAP NYATA yang tersisa (fokus pekerjaan sekarang):**
1. **UI Fase 49 belum ada sama sekali** (frontend belum memanggil endpoint 49) → semua fitur belum bisa dipakai user.
2. `seed_phase49.py` belum ada (seed demo idempoten).
3. Gate baru belum ada: `scripts/verify_closing.py` (gate 37) + `scripts/verify_tax_compliance.py` (gate 38); `scripts/run_all_gates.sh` masih 36 gate.
4. `scripts/mutasi_49.py` belum ada.
5. Dokumen belum diperbarui: `docs/v2/43_CLOSING_TAX_COMPLIANCE_SPEC.md`, `CODEBASE_MAP.md`, `test_result.md`, `memory/test_credentials.md`, `plan.md`.

**Keputusan user (wajib dipatuhi):**
- Urutan kerja: **UI Fase 49 penuh → seed demo fase49 → 2 gate + uji mutasi → E2E multi-peran → Fase 49 DITUTUP**.
- Letak UI: **tanpa pintu sidebar baru**.
  - `/accounting` → tab **Penutupan Buku** (49A/49B)
  - `/accounting-reports` → tab **Paket Laporan Owner** (49D) + tab **Arus Kas per Proyek** (49C)
  - `/tax` → tab **e-Faktur Ekspor** (49E), tab **Bukti Potong (e-Bupot)** (49F), tab **Rekap SPT Masa PPN** (49G)
- Pembayaran tagihan AP dengan potong PPh: **satu dialog pembayaran** dengan opsi **“Potong PPh”** (tarif otomatis dari setelan pajak).
- Seed demo `fase49` **boleh** mengisi data contoh bertanda jelas “demo” (NPWP demo `0012345678901000`, 1 faktur lengkap + 1 faktur kurang NPWP, 1 tagihan dibayar potong PPh, 1 periode gagal checklist).

---

## 1) Objectives
Fokus menutup gap nyata G1–G7 **tanpa mengulang backend yang sudah selesai**, lalu menyelesaikan “produk jadi” melalui UI + seed + gates + mutasi + E2E:

1. **Year-end closing (G1)**: fitur tutup tahun & buka kembali tersaji di UI (state, jejak, idempoten, reversal).
2. **Period close bergigi (G2)**: UI checklist tutup bulan; default **hold** bila gagal; override beralasan (≥10) untuk peran berwenang; audit & tugas tinjauan terlihat.
3. **Arus kas per proyek (G3)**: UI laporan per proyek dengan tie-out yang jelas, termasuk “Tidak teralokasi”.
4. **Paket laporan owner (G4)**: UI ringkas owner-pack + riwayat penutupan; missing data ditampilkan jujur (bukan 0).
5. **e-Faktur compliance (G5)**: UI pengganti/batal + ekspor XML/CSV per masa; ekspor **menahan diri** bila data wajib kurang dengan daftar faktur bermasalah.
6. **e-Bupot (G6)**: UI bukti potong (list/kandidat/terbit/betulkan/batal), PDF bisa dibuka, ekspor tersedia; integrasi pembayaran tagihan potong PPh ada di dialog bayar.
7. **Rekap SPT Masa PPN (G7)**: UI rekap PPN masa yang bisa direkonstruksi, dengan status & tautan ke sumber.

---

## 2) Implementation Steps

### FASE 1 — POC Core (WAJIB) ✅ SELESAI
**Output:** `poc/poc_49.py` hijau (exit 0) + cleanup bersih.

Status:
- `python3 poc/poc_49.py` → **PASS (96 pemeriksaan hijau)**.
- SSOT loader fase49 sudah aktif (`reference.py::_PHASES` memuat `49`).
- Endpoint 49A–49G sudah tersambung ke router.

> Stop point Fase 1 terpenuhi → lanjut Fase 2.

---

### FASE 2 — V1 App Development (UI end-to-end sesuai keputusan user)
**Output:** fitur tampil sebagai tab/section pada halaman existing (tanpa pintu sidebar baru), dan seluruh panel UI membaca data nyata dari endpoint 49.

#### 2.1 /accounting → Tab “Penutupan Buku” (49A/49B)
**Backend:** sudah siap.

**Frontend (yang harus dibangun):**
- Tambahkan tab baru di `frontend/src/pages/AccountingPage.js`: **Penutupan Buku**.
- Buat panel komponen (mis. `components/gl/ClosingPanel49.js`) yang mencakup:
  - Pilih periode (YYYY-MM) + load `GET /api/gl/periods`.
  - Tampilkan checklist `GET /api/gl/periods/close-check?period=...`:
    - item label dari `/api/reference` (group `closing_check_item` dan `closing_check_state`).
    - tampilkan status pill dan `blocking_reasons[]`.
  - Tombol **Tutup Periode** memanggil `POST /api/gl/periods/close`:
    - bila backend mengembalikan hold (409/400), UI harus menampilkan alasan satu per satu.
    - override: dialog input alasan ≥10 huruf + checkbox override; tombol hanya muncul bila user punya izin.
  - Tombol **Buka Periode** (bila tersedia) `POST /api/gl/periods/reopen`.
  - Bagian **Tutup Tahun**:
    - tampilkan daftar/status dari `GET /api/gl/year` & `GET /api/gl/year/check?year=...`.
    - aksi `POST /api/gl/year/close` dan `POST /api/gl/year/reopen` dengan konfirmasi.

**User stories UI yang bisa diuji (Indonesia):**
1. Sebagai finlead, saya melihat checklist tutup periode; bila ada yang gagal, tombol tutup menampilkan alasan dan tidak diam-diam berhasil.
2. Sebagai finlead/owner, saya dapat override tutup periode dengan alasan ≥10 huruf; UI menampilkan bahwa periode ditutup paksa dan alasan override tercatat.
3. Sebagai role non-berwenang, saat mencoba override, UI menampilkan pesan 403 (tanpa crash) dan tombol override tidak ditawarkan.
4. Sebagai owner, saya bisa tutup tahun dan membuka kembali; UI menampilkan state (closed/reopened) beserta ringkasan.


#### 2.2 /accounting-reports → Tab “Paket Laporan Owner” (49D)
**Backend:** sudah siap.

**Frontend:**
- Tambahkan tab baru di `frontend/src/pages/AccountingReportsPage.js`: **Paket Laporan Owner**.
- Komponen panel (mis. `components/gl/OwnerPackPanel49.js`):
  - input periode (YYYY-MM), load `GET /api/gl/reports/owner-pack?period=...`.
  - render bagian: metadata penutupan, laba-rugi, neraca, arus kas, rasio, laba per proyek, arus kas per proyek (ringkas) + `missing[]` bila ada.
  - render `GET /api/gl/reports/closing-history?limit=` sebagai list “riwayat tutup” dan penanda override.

**User stories UI:**
1. Sebagai owner, saya bisa membuka laporan owner-pack per bulan dan melihat metadata penutupan (closed_by, override_reason) bila ada.
2. Bila data tidak lengkap, UI menampilkan “missing data” sebagai catatan (bukan Rp 0).


#### 2.3 /accounting-reports → Tab “Arus Kas per Proyek” (49C)
**Backend:** sudah siap.

**Frontend:**
- Tambahkan tab baru: **Arus Kas per Proyek**.
- Komponen panel (mis. `components/gl/CashFlowProjectsPanel49.js`):
  - input rentang tanggal/periode → `GET /api/gl/reports/cash-flow-projects?date_from=...&date_to=...`.
  - tabel per proyek + baris **“Tidak teralokasi”** + total.
  - badge tie-out: `matches`/`selisih` dari `tie_out`.

**User story UI:**
1. Sebagai owner/finance, saya melihat arus kas per proyek yang bisa dijumlahkan dan tie-out ke konsolidasi.


#### 2.4 /tax → Tab “e-Faktur Ekspor” (49E)
**Backend:** sudah siap via `tax_compliance_router`.

**Frontend:**
- Tambahkan tab baru di `frontend/src/pages/TaxPage.js`: **e-Faktur Ekspor**.
- Komponen panel (mis. `components/tax/FakturExportPanel49.js`):
  - pilih masa pajak (period) dari `GET /api/tax/compliance/faktur/periods`.
  - tampilkan daftar faktur `GET /api/tax/compliance/faktur?period=...`.
  - aksi pengganti: `POST /api/tax/compliance/faktur/{id}/replace` (dialog alasan ≥10)
  - aksi pembatalan: `POST /api/tax/compliance/faktur/{id}/cancel` (dialog alasan ≥10)
  - ekspor:
    - cek `GET /api/tax/compliance/faktur-export/check?period=...&format=coretax_xml|excel_csv`
    - unduh `GET /api/tax/compliance/faktur-export/file?...` (download file) bila status “Siap”.
  - bila backend menahan ekspor (hold), UI harus menampilkan *pesan jelas* dan daftar faktur bermasalah.

**User stories UI:**
1. Sebagai finance, saya menekan “Cek Ekspor” dan bila NPWP/identitas kurang, UI menampilkan alasan serta faktur mana yang kurang.
2. Sebagai finance, setelah data lengkap, saya dapat mengunduh file **XML** dan **CSV**.


#### 2.5 /tax → Tab “Bukti Potong (e-Bupot)” (49F)
**Backend:** sudah siap via `tax_compliance_router`.

**Frontend:**
- Tambahkan tab baru: **Bukti Potong (e-Bupot)**.
- Komponen panel (mis. `components/tax/WithholdingPanel49.js`):
  - load konfigurasi `GET /api/tax/compliance/withholding/config`.
  - list bukti potong `GET /api/tax/compliance/withholding?period=...` + summary `GET /api/tax/compliance/withholding/summary?period=...`.
  - kandidat/potongan yang belum berbukti: `GET /api/tax/compliance/withholding/candidates?period=...`.
  - aksi terbit manual: `POST /api/tax/compliance/withholding/issue` (idempoten).
  - aksi pembetulan: `POST /api/tax/compliance/withholding/{doc_id}/correct` (reason ≥10).
  - aksi pembatalan: `POST /api/tax/compliance/withholding/{doc_id}/cancel` (reason ≥10).
  - PDF: tombol membuka/unduh dari `GET /api/tax/compliance/withholding/{doc_id}/pdf`.
  - ekspor:
    - check `GET /api/tax/compliance/withholding-export/check?period=...&format=...`
    - file `GET /api/tax/compliance/withholding-export/file?...`.

**User stories UI:**
1. Sebagai finance, saya melihat daftar kandidat potongan PPh yang belum punya bukti potong dan dapat menerbitkannya.
2. Sebagai finance, saya dapat membuka PDF bukti potong.
3. Sebagai sales, saya tidak bisa melihat tab/isi bukti potong (atau mendapatkan 403 yang ditangani UI).


#### 2.6 /tax → Tab “Rekap SPT Masa PPN” (49G)
**Backend:** sudah siap via `GET /api/tax/compliance/vat-return?period=...`.

**Frontend:**
- Tambahkan tab baru: **Rekap SPT Masa PPN**.
- Komponen panel (mis. `components/tax/VatReturnPanel49.js`):
  - pilih masa → panggil `GET /api/tax/compliance/vat-return?period=...`.
  - tampilkan PPN keluaran, masukan, net, status/state_label, dan `reconstruct` agar bisa diaudit.
  - tautkan ke tab faktur/ppn-input bila relevan.

**User story UI:**
1. Sebagai finance/owner, saya melihat rekap PPN masa yang menjelaskan cara hitungnya (bisa direkonstruksi).


#### 2.7 Keuangan/AP — Dialog pembayaran tagihan dengan opsi “Potong PPh”
**Keputusan user:** satu dialog pembayaran.

**Frontend:**
- Temukan komponen pembayaran tagihan AP (di area `components/finance` atau `components/vendors`/`components/procurement` sesuai implementasi) dan tambahkan:
  - checkbox **“Potong PPh”**
  - field jenis potong (default PPh23) + rate auto dari settings
  - validasi: potongan tidak boleh >= nilai pembayaran
  - submit:
    - bila tanpa potong → endpoint existing `POST /api/ap/bills/{id}/pay`
    - bila potong → panggil `POST /api/ap/bills/{id}/pay-withholding` dengan model `BillPayWithholding`
  - setelah sukses, UI menampilkan nomor bukti potong yang terbit otomatis (bila tersedia di response) dan link ke tab e-Bupot.

**User story UI:**
1. Sebagai finance, saat membayar tagihan saya bisa memilih “Potong PPh” sehingga kas keluar adalah NET dan bukti potong terbit otomatis.

---

### FASE 3 — Seed + Gates + Mutasi + Dokumen + E2E Penutupan
**Output:** seed demo `fase49` idempoten + 2 gate baru + uji mutasi + E2E multi-peran (testing_agent_v3) + suite gate menjadi **38 gates**.

#### 3.1 Seed idempoten `seed_phase49.py` (demo `fase49`)
- Buat `backend/seed_phase49.py` dan panggil dari proses seed (atau jalankan manual via script) dengan `demo_batch="fase49"`.
- Isi data demo bertanda jelas “demo”:
  - NPWP perusahaan demo: `0012345678901000` (via settings store).
  - 2 proyek + 1 transaksi tanpa proyek untuk tie-out cashflow projects.
  - 1 periode yang gagal checklist (agar UI hold/override bisa didemo).
  - 1 faktur lengkap + 1 faktur kurang NPWP (agar UI ekspor menahan diri dan menyebut faktur).
  - 1 tagihan AP yang dibayar potong PPh (agar e-Bupot otomatis ada).
- Pastikan seed:
  - idempoten (bisa dijalankan berkali-kali tanpa duplikasi)
  - aman untuk environment demo

#### 3.2 RBAC (cek konsistensi + UI gating)
- Verifikasi izin yang sudah ada:
  - `gl:close_override`, `gl:year_close`, `tax:export`, `tax:withholding_issue`, izin untuk `pay-withholding`.
- Di UI, sembunyikan tombol yang tidak berhak (namun tetap handle 403 bila terjadi).

#### 3.3 Gate baru + registrasi menjadi 38 gates
- Buat dan tambahkan ke `scripts/run_all_gates.sh`:
  - `scripts/verify_closing.py` (gate 37):
    - period close hold/override
    - year close idempoten + reopen reversal
    - owner pack/closing history minimal smoke
  - `scripts/verify_tax_compliance.py` (gate 38):
    - e-Faktur export check hold reason menyebut faktur
    - e-Bupot issue/correct/cancel + PDF smoke
    - VAT return reconstruct presence

#### 3.4 Uji mutasi `scripts/mutasi_49.py`
- Buat 16–24 mutasi untuk memastikan guard tidak bisa ditembus:
  - close tanpa alasan override (harus gagal)
  - override reason < 10 (harus gagal)
  - year close tidak idempoten (harus tertangkap)
  - reopen tanpa reversal (harus tertangkap)
  - tie-out cashflow projects mismatch (harus tertangkap)
  - export e-Faktur tanpa NPWP tapi tidak hold (harus tertangkap)
  - withholding correct mengubah nomor (harus tertangkap)

#### 3.5 Dokumen + peta kode + catatan testing
- Tambah `docs/v2/43_CLOSING_TAX_COMPLIANCE_SPEC.md` (spesifikasi ringkas Fase 49, termasuk mapping endpoint → UI).
- Update `CODEBASE_MAP.md` (permukaan UI baru + endpoint penting).
- Update `test_result.md` sesuai protokol.
- Update `memory/test_credentials.md` bila ada akun/OTP/NPWP demo.
- Update `plan.md` (dokumen ini).

#### 3.6 E2E multi-peran (testing_agent_v3)
- Jalankan E2E UI+API untuk role: owner, finlead, finance, pm, sales.
- Fokus skenario:
  - close period hold + override
  - year close/reopen
  - export e-Faktur (hold → siap → download)
  - e-Bupot (issue/correct/cancel + PDF)
  - AP pay-withholding dari dialog pembayaran

---

## 3) Next Actions (diperbarui)
1. **Bangun UI Fase 49 penuh** sesuai tab yang disepakati:
   - `/accounting` tab Penutupan Buku
   - `/accounting-reports` tab Paket Owner + Arus Kas per Proyek
   - `/tax` tab e-Faktur Ekspor + e-Bupot + Rekap SPT PPN
2. Implement **dialog pembayaran tagihan AP** dengan opsi “Potong PPh” → gunakan `/api/ap/bills/{id}/pay-withholding`.
3. Tambah `seed_phase49.py` idempoten + data demo.
4. Tambah gate 37–38 + registrasi di `scripts/run_all_gates.sh` → target **38 gates**.
5. Tambah `scripts/mutasi_49.py` dan pastikan semua mutasi tertangkap.
6. Update dokumen: spec v2/43, CODEBASE_MAP, test_result, memory/test_credentials, plan.
7. Jalankan E2E multi-peran (testing_agent_v3) untuk menutup Fase 49.

---

## 4) Success Criteria (diperbarui)
- Backend baseline tetap hijau:
  - `python3 poc/poc_49.py` → **PASS**.
- UI Fase 49 tersedia dan fungsional:
  - Tab **Penutupan Buku** menampilkan close-check, melakukan hold/override, dan menampilkan alasan secara jujur.
  - Panel **Tutup Tahun** berfungsi (close/reopen) dan state tampil benar.
  - **Arus Kas per Proyek** tampil dengan “Tidak teralokasi” + badge tie-out match/selisih.
  - **Paket Laporan Owner** tampil dan menampilkan missing data sebagai catatan.
  - **e-Faktur Ekspor**: replace/cancel via UI; ekspor menahan diri saat data wajib kurang; download **XML+CSV** berhasil.
  - **e-Bupot**: list/kandidat/terbit/betulkan/batal; **PDF** bisa dibuka; ekspor file berhasil.
  - **Rekap SPT Masa PPN** menampilkan angka + `reconstruct` yang bisa diaudit.
  - Dialog bayar tagihan AP mendukung opsi “Potong PPh” dan mem-posting NET + menerbitkan bukti potong.
- Gates:
  - `bash scripts/run_all_gates.sh` → **OVERALL PASS (38 gates)**.
- Mutasi:
  - `python3 scripts/mutasi_49.py` → semua mutasi **TERTANGKAP**.
- E2E multi-peran:
  - owner/finlead/finance/pm/sales berjalan tanpa bug kritis; 403 ditangani UI dengan baik.

---

## Fase 50 (disiapkan setelah Fase 49 ditutup)
- **PWA offline terpadu** untuk absensi (Fase 47) + progres + foto dalam satu antrean sinkron.
- **Serah terima unit**: BAST unit, masa garansi, klaim garansi pasca-huni terhubung punch list & komplain CS.
