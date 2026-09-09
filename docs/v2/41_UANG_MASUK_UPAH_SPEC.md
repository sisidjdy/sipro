# 41 — UANG MASUK & UPAH HARIAN (SPEC + STATUS Fase 47)

> **Status:** **Fase 47 DIIMPLEMENTASI** (47A rekonsiliasi bank, 47B bukti transfer portal,
> 47C penawaran + simulasi KPR, 47D absensi & upah harian). Bukti: gate ke-31/32/33
> (`scripts/verify_bank_recon.py`, `scripts/verify_portal_proof.py`,
> `scripts/verify_quotation_labor.py`), uji-mutasi `scripts/mutasi_47.py` (19 mutasi),
> POC `poc/poc_47.py`. Dokumen ini melanjutkan seri V2 (lihat `20_INDEX_V2.md`).
> **Bahasa:** Indonesia. **Sumber angka:** kode `/app/backend` — tidak ada angka karangan.

Dokumen ini mengunci **aturan** yang boleh dipegang orang keuangan, sales, dan mandor.
Setiap aturan punya pasangan **uji negatif** di gate — kalau aturannya dilanggar, gate MERAH.

---

## 1. Prinsip yang mengikat seluruh fase 47

| Kode | Prinsip | Kenapa mahal bila dilanggar |
|---|---|---|
| P-1 | **Satu kebenaran angka.** Termin penawaran memakai `finance_engine.compute_scheme_items` (fungsi yang sama dengan pembuat AR). Upah memakai `labor_engine.wage_of`. Layar tidak pernah menghitung ulang. | Dua rumus = dua harga/dua upah untuk satu kesepakatan |
| P-2 | **Klaim ≠ pelunasan.** Bukti transfer pelanggan dan mutasi rekening yang belum dicocokkan TIDAK PERNAH mengurangi tagihan. | Tagihan "lunas" tanpa uang masuk |
| P-3 | **Jujur soal data yang belum ada.** Tidak ada `0` untuk hal yang belum diketahui: KPR tanpa tenor/bunga → `state="missing_data"` + `missing[]`; mutasi tanpa kolom saldo → `balance=None`; selisih rekonsiliasi yang tak terjelaskan → sebab `unexplained` yang menyebut nominalnya. | Nol yang dibaca sebagai fakta |
| P-4 | **Pemisahan tugas.** Yang mencatat tidak memutuskan: kasir mencocokkan (`bank:update`), supervisor keuangan membalik pembukuan (`bank:approve`); mandor/PM mengajukan rekap upah (`labor:create/update`), keuangan menyetujui & membayar (`labor:approve`); sales membuat penawaran, manajer memutuskan diskon (`quotations:approve`). | Satu orang bisa menciptakan & mencairkan uang |
| P-5 | **Bisa dibatalkan, tetapi beralasan & berjejak.** Pembatalan pencocokan membalik kuitansi + jurnal (bukan menghapusnya), alasan minimal 5 huruf, tercatat di `history`. | Buku besar tanpa jejak |
| P-6 | **Idempoten.** Impor mutasi rekening memakai sidik jari alami (rekening+tanggal+arah+nominal+keterangan/ref); berkas yang sama diimpor ulang = `unchanged`. Bukti transfer dikenali lewat `files.sha256`. | Uang dihitung dua kali |

---

## 2. 47A — Rekonsiliasi bank

**Data:** `bank_accounts` (tertaut `gl_account_code`), `bank_statements`, `bank_transactions`
(index UNIK `org_id+fingerprint`), `bank_matches`.

**Alur:** unggah CSV → **pratinjau (dry-run) tidak menulis apa pun** → commit → mutasi masuk
sebagai `unmatched` → kasir melihat **usulan berskor + alasan** (`GET /transactions/{id}/suggest`)
→ `POST /transactions/{id}/match` menjalankan **jalur resmi** subledger
(`apply_receipt` untuk AR, `payment_intake.verify` untuk bukti portal, `pay_ap_bill`,
`labor.pay_payroll`, atau jurnal biaya bank/jasa giro) → `POST /transactions/{id}/unmatch`
membatalkan kuitansi (status `void`, bukan dihapus) + jurnal pembalik.

| Aturan | Uji negatif di gate |
|---|---|
| Dry-run tidak menulis | impor `dry_run` lalu hitung koleksi = tidak berubah |
| Impor idempoten | impor berkas sama 2× → `unchanged`, jumlah mutasi sama |
| Perubahan diakui | keterangan/saldo berubah → `updated` + `history` |
| Saldo tidak wajib | mutasi tanpa kolom saldo → `balance=None` (bukan 0) |
| Mutasi belum cocok bukan pelunasan | `outstanding` AR tidak berubah sebelum match |
| Pembatalan membalik utuh | AR kembali ke nilai semula, dampak GL akun `2-1400` = 0 |
| Mengabaikan mutasi wajib beralasan | alasan <5 huruf → 400; mutasi yang sudah cocok tidak bisa diabaikan |
| Selisih dijelaskan | ringkasan menyebut `unmatched` + `unexplained` |
| RBAC | sales 403 (tidak boleh melihat kas), finance biasa 403 saat `unmatch`, `finlead` 200 |

**Layar:** `/finance` tab **Rekonsiliasi Bank**
(`frontend/src/components/finance/BankReconciliationTab.js` + dialog impor/pencocokan/alasan).

---

## 3. 47B — Bukti transfer dari portal pelanggan

**Data:** `payment_intakes` (`file_shas`, `state ∈ pending|verified|rejected`), berkas bukti
di `files` (`owner_type="payment_proof"`, `portal_customer_id`).

**Alur:** pelanggan unggah lewat **endpoint portal sendiri**
(`POST /api/portal/payments/proof/upload` — `/api/files/upload` milik staf tidak bisa dipakai
token portal, sebab fitur yang tidak bisa dicapai sama dengan tidak ada) → `POST
/api/portal/payments/proof` membuat klaim **pending** → finance
`POST /api/payment-intakes/{id}/verify|reject`.

| Aturan | Uji negatif di gate |
|---|---|
| Bukti = klaim | setelah kirim bukti, `outstanding` pelanggan **tidak berubah** |
| Bukti kembar ditolak | berkas dengan sha256 sama → 400 dengan tanggal kiriman sebelumnya |
| Berkas bukan milik akun | file_id milik pelanggan lain → 400 |
| Penolakan wajib beralasan | alasan <10 huruf → 400/422; alasannya **dibaca pelanggan** di portal |
| Verifikasi tepat sekali | verifikasi kedua → 400; kuitansi + jurnal menunjuk kuitansinya |
| Jejak audit jujur | `created_by="portal"`, identitas pelanggan di `submitted_by.customer_id`; tidak ada notifikasi in-app ke alamat bukan pengguna |
| RBAC | sales 403 melihat, pelaksana lapangan 403 memverifikasi, portal tanpa token 401 |

**Layar:** Portal → `PaymentsPanel` + `PaymentProofDialog` (riwayat + alasan penolakan);
Finance → `PaymentIntakePanel` + `IntakeReviewDialog`.

---

## 4. 47C — Penawaran (quotation) & simulasi KPR

**Data:** `quotations` (versioning: `version`, `parent_id`, `superseded_by`,
`state ∈ draft|awaiting_approval|approved|rejected|sent|converted|expired|superseded`).

**Aturan harga:** `gross = harga unit + add-on (kecuali `finance_treatment="info"`)`;
`net = gross − diskon`; **termin = `compute_scheme_items(scheme, net, hari_ini)`** sehingga
`Σ termin = net`. Pajak dari `finance_engine.compute_taxes`.

**Simulasi KPR:** anuitas `A = P × i / (1 − (1+i)^−n)` dengan `i` = bunga tahunan/12.
**Tidak ada bunga bawaan** — tenor/bunga/DP kosong → `state="missing_data"` + `missing[]`.

**Diskon berjenjang:** di atas `quotation.discount_max_pct_sales` (Pusat Konfigurasi) →
wajib `discount_reason`, penawaran `awaiting_approval`, **tidak bisa dikonversi** sebelum
diputuskan; keputusan (`POST /{id}/decision`) wajib beralasan ≥5 huruf dan butuh
`quotations:approve` (sales 403 — tidak boleh menyetujui diskonnya sendiri).

**Revisi = versi baru** (`POST /{id}/revise`): versi lama menjadi `superseded` dan tetap
terbaca. **Konversi sekali saja** (`POST /{id}/convert` → reservasi/deal nyata, unit
`reserved`). PDF (`GET /{id}/pdf`) memakai angka yang TERSIMPAN. Kirim WA = mode simulasi
bila kredensial belum ada (`sent_status` menyebutnya).

**Layar:** Lead 360 → tab **Penawaran** (`components/quotations/*`).

---

## 5. 47D — Absensi & upah harian

**Data:** `workers` (tarif harian wajib > 0, peran dari SSOT `labor_role`),
`labor_attendance` (index UNIK `org_id+project_id+work_date+worker_id`),
`labor_payrolls` (`state ∈ draft|submitted|approved|rejected|paid`).

**Rumus upah (bisa dihitung ulang tangan):**
`total = faktor_hari × tarif_harian + jam_lembur × (tarif_harian / labor.normal_hours_per_day)
× labor.overtime_multiplier`, `faktor_hari`: hadir 1,0 · setengah 0,5 · absen/izin 0,0.
Baris absensi menyimpan `formula` sebagai kalimat yang bisa dibacakan ke tukangnya.

| Aturan | Uji negatif di gate |
|---|---|
| Tidak boleh absensi masa depan | tanggal > hari ini → 400 |
| Satu orang satu baris/hari | orang kembar dalam satu kiriman → 400; index UNIK menolak dari jalur data |
| Koreksi = memperbarui + berjejak | kiriman kedua hari sama → 1 baris + `history` |
| Rekap tie-out ke absensi | `payroll.total` = Σ `attendance.total` periode itu |
| Periode tidak boleh bertumpang | rekap bertumpang → 400 (upah tak dibayar 2×) |
| Rekap kosong tidak dibuat | periode tanpa absensi berupah → 400 |
| Periode terkunci | absensi pada rekap `submitted/approved/paid` → 400 |
| Selisih buku harian dilaporkan | `GET /labor/attendance/diary-check` → `match|mismatch|missing_diary` (tidak menimpa salah satu) |
| Pemisahan tugas | pengaju 403 saat menyetujui; bayar sebelum disetujui → 400; penolakan wajib beralasan |
| Pembayaran berjurnal & tak bisa dobel | Dr `1-1600` (pekerjaan dalam proses) / Cr `1-1200` (bank) senilai rekap; bayar kedua → 400 |

**Layar:** `/build` tab **Lapangan** → `LaborAttendancePanel` (papan absensi cepat),
`LaborWorkersPanel`, `LaborPayrollPanel` (mode lapangan: ajukan); `/finance` tab **Upah
Harian** → `LaborPayrollPanel` (mode keuangan: setujui/tolak/bayar) + `PayrollDetailSheet`.

---

## 6. SSOT & Pusat Konfigurasi yang dipakai fase ini

`backend/reference_p47.py`: `bank_txn_direction`, `bank_match_state`, `bank_match_kind`,
`import_row_state`, `payment_intake_state`, `quotation_state`, `labor_role`,
`attendance_status`, `payroll_state` (semuanya keluar lewat `GET /api/reference`).

Setting (Pusat Konfigurasi): `bank.match_tolerance_amount`, `bank.match_tolerance_days`,
`quotation.discount_max_pct_sales`, `quotation.validity_days`, `labor.overtime_multiplier`,
`labor.normal_hours_per_day`.

Akun GL: bank `1-1200`, biaya bank `6-1600`, jasa giro `4-1200`, titipan/uang muka `2-1400`,
pekerjaan dalam proses `1-1600`.

---

## 7. Yang MASIH mode simulasi (jangan dianggap cacat)

* **WhatsApp** (kirim penawaran) — `sent_status="simulated"` bila `WHATSAPP_TOKEN` kosong.
* **E-sign** & **object storage terkelola** — sama, jatuh ke mode lokal/simulasi.
* **Impor mutasi bank** = berkas CSV/manual. Tarikan API bank (open banking) **belum** ada
  dan tidak dikarang: layar hanya menjanjikan apa yang benar-benar bisa dilakukan.

## 8. ⚠️ OPEN — pertanyaan yang perlu dijawab owner

| Kode | Pertanyaan | Dampak bila dikarang |
|---|---|---|
| OQ-47-1 | Bunga & tenor KPR rekanan bank (apakah perlu master produk KPR per bank?) | simulasi angsuran mengarang bunga |
| OQ-47-2 | Batas kewenangan diskon per peran (sekarang satu ambang `discount_max_pct_sales`) | approval diskon salah sasaran |
| OQ-47-3 | Upah lembur: pengali tetap 1,5× atau mengikuti aturan jam pertama/berikutnya (PP 35/2021)? | upah lembur salah hitung |
| OQ-47-4 | Apakah upah harian dibayar tunai (kas kecil) selain transfer bank? | jurnal upah salah akun kas |
