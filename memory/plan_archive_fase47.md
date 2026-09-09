# Rencana Development SIPRO — Fase 47 (Uang & Pekerjaan yang bisa dipertanggungjawabkan)

> **STATUS 18 Agu 2026 (sesi lanjutan dari repo `kalaoakawasa/sipro`).**
> Lingkungan dipulihkan ke container baru (lihat `CODEBASE_MAP.md` §Fase 47 "Pemulihan
> lingkungan"): backend+frontend hidup, seed & migrasi idempoten jalan saat startup.
> * **FASE 1 (POC core) — SELESAI**: `poc/poc_47.py` hijau.
> * **FASE 2 (V1 app backend+frontend) — SELESAI**: 47A rekonsiliasi bank, 47B bukti transfer
>   portal, 47C penawaran + simulasi KPR, 47D absensi & upah harian — semuanya sudah punya
>   layar (tanpa pintu sidebar baru) + seed demo `fase47`. Spec ditulis di
>   `docs/v2/41_UANG_MASUK_UPAH_SPEC.md`.
> * **FASE 3 (gates + mutasi + penutupan) — BERJALAN**: gate ke-31/32/33
>   (`verify_bank_recon.py`, `verify_portal_proof.py`, `verify_quotation_labor.py`) hijau &
>   sudah didaftarkan ke `run_all_gates.sh` (30 → **33 gates**); `scripts/mutasi_47.py`
>   (19 mutasi) dijalankan — log `test_reports/mutasi_47_run.log`; sisa: E2E testing agent
>   multi-peran, lalu **Fase 48 — Pengadaan & Subkon lanjutan** (permintaan owner).

Problem statement (verbatim):
> "saya ingin anda lanjutan development dari repo ini https://github.com/yawnabavasa/Sipro"

Status baseline (jangan turun): `run_all_gates.sh` **PASS (30 gates)**, `mutasi_46.py` **16/16**, `poc_46.py` PASS, E2E iterasi **68 & 69** tanpa bug kritis. Integrasi pihak ketiga tetap **mode simulasi**.

---

## 1) Objectives
1. **Rekonsiliasi bank** (47A): impor mutasi rekening idempoten + pencocokan manual bergigi (AR/AP/titipan/kasbon) + jurnal kliring + bisa di-unmatch.
2. **Portal bukti transfer** (47B): pelanggan upload bukti → status menunggu → finance verifikasi/tolak → baru memengaruhi AR; anti-dobel (sha256) + notifikasi.
3. **Penawaran/Quotation** (47C): simulasi harga + skema bayar + (opsional) simulasi KPR yang jujur; approval diskon; PDF; kirim WA (simulasi); konversi ke reservasi/SPR.
4. **Absensi & upah harian** (47D): master tenaga kerja + absensi harian + rekap upah periode + approval & pembayaran + tie-out ke jurnal & realisasi anggaran; selisih vs site diary diperingatkan (tidak ditimpa).

---

## 2) Implementation Steps

### FASE 1 — POC Core (WAJIB, SSOT + idempoten + tie-out)
**Output:** `poc/poc_47.py` hijau (exit 0) membuktikan 4 core flows tanpa UI.

User stories (POC):
1. Sebagai finance, saya impor CSV mutasi bank (dry-run & commit) yang **idempoten** (reimport = unchanged; perubahan = update+history; dry-run tidak menulis).
2. Sebagai finance, saya mencocokkan 1 baris mutasi ke 1 termin AR, dan **tagihan belum berubah** sebelum match dikonfirmasi.
3. Sebagai auditor, saya unmatch dan jurnal kliring **dibalik** beralasan + jejak audit.
4. Sebagai pelanggan, saya kirim bukti transfer dan AR **tidak** berkurang sebelum verifikasi finance.
5. Sebagai sales, saya membuat quotation yang perhitungan item termin **tie-out** ke `finance_engine.compute_scheme_items` (tidak ada rumus kedua) dan simulasi KPR yang kosong tampil **belum ada data** (bukan angka karangan).
6. Sebagai pelaksana, saya catat absensi harian; sistem menolak absensi dobel (index unik) dan upah periode bisa direkonstruksi baris-per-baris.

Langkah:
- P1. Tambah SSOT `backend/reference_p47.py` (bank_match_state, bank_txn_type, payment_submission_state, quotation_state, labor_role, attendance_status, overtime_policy) dan gabungkan ke `/api/reference`.
- P2. Buat POC `poc/poc_47.py` (fixture dibuat sendiri & dibuang):
  - (A) Buat bank_account + import CSV 5 baris (2 duplikat) → dry-run tidak menulis; commit menulis; reimport = unchanged.
  - (B) Buat deal+invoice sederhana dari seed (atau fixture deal) lalu match 1 bank_txn → AR tidak berubah sebelum verify; confirm match → AR berubah lewat jalur resmi; unmatch → jurnal reversal.
  - (C) Buat payment_submission (portal) → status pending; verifikasi finance → apply_receipt; tolak → alasan tampil.
  - (D) Buat quotation → hitung breakdown dari SSOT + simulasi KPR jujur.
  - (E) Buat worker + attendance 3 hari + overtime; rekap payroll; post ke GL + budget realization; tolak absensi dobel.
- P3. Websearch singkat: best-practice rekonsiliasi bank (idempotent import + matching scoring) & payroll audit trail (timezone/date).
- P4. Jika POC belum hijau → perbaiki model/engine/matching sebelum masuk Fase 2.

---

### FASE 2 — V1 App Development (backend + frontend end-to-end)
**Output:** 4 alur kerja tersedia di UI tanpa pintu sidebar baru.

#### 47A — Backend Rekonsiliasi Bank
- A1. Model/koleksi baru: `bank_accounts`, `bank_statements`, `bank_transactions`, `bank_matches` (+ index unik kunci alami txn).
- A2. Engine: `backend/bank_import.py` (parse CSV, dry-run/commit idempoten) + `backend/bank_match.py` (suggest scoring, match/unmatch, audit).
- A3. Router baru `backend/routers/bank_router.py`:
  - `GET/POST/PUT/DELETE /api/bank/accounts`
  - `POST /api/bank/statements/import` (dry_run|commit)
  - `GET /api/bank/transactions` (filter account/status/period)
  - `GET /api/bank/match/suggest` + `POST /api/bank/match` + `POST /api/bank/unmatch`
  - `GET /api/bank/reconciliation` (saldo buku vs rekening + selisih + penyebab)
- A4. GL posting: match menghasilkan jurnal kliring via `gl_engine.post_journal`; unmatch = reversal terikat source.

#### 47A — Frontend Rekonsiliasi Bank (tanpa pintu baru)
- AF1. Tambah tab **Rekonsiliasi Bank** di `FinancePage.js`.
- AF2. Komponen `components/finance/BankReconciliationTab.js`:
  - Import dialog (preview dry-run), tabel mutasi (status: cocok/belum), panel suggest + aksi match/unmatch.

#### 47B — Portal Bukti Transfer
- B1. Backend: koleksi `payment_submissions` (sha256 unik), file upload reuse `/api/files/upload`, endpoint portal:
  - `POST /api/portal/payments/proof` (buat submission pending)
  - `GET /api/portal/payments/submissions`
- B2. Finance UI: panel kerja di `/finance` (tab AR atau Rekonsiliasi) untuk verify/reject:
  - `POST /api/ar/receipts/from-submission` atau endpoint baru `POST /api/ar/submissions/{id}/verify|reject`.
- B3. In-app notifications: ke finance saat ada submission baru; ke pelanggan saat diverifikasi/ditolak.
- BF1. Portal FE: `PaymentsPanel` tambah tombol upload bukti + riwayat status + alasan penolakan.

#### 47C — Quotation & Simulasi
- C1. Backend: `backend/quotation_engine.py` (mengikat ke SSOT pricing & scheme) + koleksi `quotations` (versioning).
- C2. Router `backend/routers/quotations_router.py`:
  - `GET/POST /api/quotations`, `GET /api/quotations/{id}`
  - `POST /api/quotations/{id}/revise`
  - `POST /api/quotations/{id}/approve-discount`
  - `GET /api/quotations/{id}/pdf`, `POST /api/quotations/{id}/send` (WA simulasi), `POST /api/quotations/{id}/convert`
  - `POST /api/quotations/simulate` (tanpa simpan)
- CF1. Frontend: tab **Penawaran** di Lead Profile (`LeadProfilePage.js`) + dialog buat/simulasi + status approval.

#### 47D — Absensi & Upah
- D1. Backend: koleksi `workers`, `labor_attendance`, `labor_payrolls` + index unik (worker_id+date+project_id).
- D2. Engine: `backend/labor_engine.py` (hitung upah, rekap periode, tie-out ke absensi) + integrasi pembayaran (kasbon/AP) + posting GL + budget realization.
- D3. Router `backend/routers/labor_router.py`:
  - CRUD worker, input attendance, rekap period, submit/approve/pay payroll.
- DF1. Frontend: panel **Absensi & Upah** di `/build` tab Lapangan (`BuildFieldTab.js`): tabel cepat absensi harian + rekap + ajukan.
- DF2. Finance: lihat payroll draft/approve/pay di `/finance`.

#### Seed & RBAC
- S1. `backend/seed_phase47.py` idempoten: 1 bank account + 1 statement berisi txn belum cocok; 1 payment_submission pending; 1 quotation pending approval; 1 payroll draft.
- S2. RBAC: tambah resource baru (`bank`, `quotations`, `labor`, `portal_payments`) + update matriks; pastikan sales/finance/site/pm tepat.

Akhir Fase 2: panggil testing agent 1 putaran E2E V1.

---

### FASE 3 — Gates + Mutasi + Penutupan
**Output:** guardrail baru + E2E multi-peran + dok rapi.

User stories (QA/Governance):
1. Impor bank dry-run tidak menulis apa pun; commit idempoten.
2. Bank txn belum cocok tidak pernah dihitung sebagai pelunasan.
3. Bukti transfer portal tidak mengubah AR sebelum verifikasi.
4. Quotation pricing tie-out ke SSOT; simulasi KPR kosong = “belum ada data”.
5. Absensi dobel ditolak; payroll tie-out ke absensi; posting GL/budget dapat direkonstruksi.

Langkah:
- G1. Gate baru `scripts/verify_bank_recon.py`.
- G2. Gate baru `scripts/verify_portal_proof.py`.
- G3. Gate baru `scripts/verify_quotation_labor.py`.
- G4. `scripts/mutasi_47.py` (12–18 mutasi) menyerang: idempoten import, honest-null, match tanpa confirm, AR berubah tanpa verify, rumus quotation ganda, absensi dobel lolos, payroll tidak tie-out, RBAC longgar.
- G5. Daftarkan gate ke `run_all_gates.sh` (30 → 33). Update `plan.md`, `test_result.md`, `CODEBASE_MAP.md`, `memory/test_credentials.md`.

---

## 3) Next Actions
1. Implement `poc/poc_47.py` sampai hijau (fixture create+cleanup; tie-out & honest states).
2. Tambah `reference_p47.py` + router skeleton (bank/portal proof/quotations/labor).
3. Implement backend 47A–47D minimal end-to-end + `seed_phase47.py`.
4. Implement UI tab/panel (Finance: Rekonsiliasi Bank; Portal: upload bukti; Lead: Penawaran; Build/Lapangan: Absensi).
5. Tambah 3 gate + `mutasi_47.py`, jalankan `run_all_gates.sh`.
6. Minta testing agent E2E multi-peran untuk menutup fase.

---

## 4) Success Criteria
- `python3 poc/poc_47.py` → PASS.
- Rekonsiliasi: dry-run tidak menulis; commit idempoten; match/unmatch menghasilkan jurnal + reversal.
- Portal: `POST /api/portal/payments/proof` membuat submission pending; AR berubah hanya setelah verify finance.
- Quotation: breakdown konsisten dengan SSOT pricing/scheme; simulasi KPR kosong menulis “belum ada data”.
- Labor: absensi dobel ditolak; payroll tie-out ke absensi; biaya upah masuk GL + realisasi anggaran.
- `bash scripts/run_all_gates.sh` → **OVERALL PASS** dengan **33 gates**.
- `python3 scripts/mutasi_47.py` → semua mutasi **TERTANGKAP**.
