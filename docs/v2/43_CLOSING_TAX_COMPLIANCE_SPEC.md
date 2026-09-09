# 43 — SPEC PENUTUPAN BUKU, LAPORAN OWNER & KEPATUHAN PAJAK (Fase 49)

> Dasar: audit kondisi nyata repo (bukan dugaan) atas modul akuntansi/pajak yang sudah ada
> sejak Fase 12/15/25/47/48. Cakupan yang diminta: (a) tutup bulan yang **bergigi**,
> (b) tutup tahun yang **reversible**, (c) arus kas **per proyek**, (d) paket laporan bulanan
> direksi, (e) e-Faktur (pengganti/batal + ekspor berkas), (f) e-Bupot (bukti potong PPh),
> (g) rekap SPT Masa PPN yang bisa direkonstruksi.

---

## 1. Yang SUDAH ADA sebelum Fase 49 (jangan dibangun ulang)

| Modul | Kemampuan |
|---|---|
| `gl_engine.py`, `gl_reports.py` | bagan akun, jurnal (seimbang), buku besar, neraca saldo, laba-rugi/neraca/arus kas berperiode, laba per proyek, rasio |
| `gl_periods.py` | tutup/buka periode **tanpa pemeriksaan** — jurnal manual di periode tertutup ditolak, posting otomatis digeser |
| `tax_engine.py` | faktur pajak keluaran (terbit + PDF), PPN masukan (estimasi dari tagihan), catatan pajak (PPN/PPh/BPHTB) |
| `bank_match.py`, `finance_engine.py` | rekonsiliasi bank, tagihan AP + pembayaran (selalu **bruto**) |

## 2. Tujuh lubang yang ditutup Fase 49

| Kode | Lubang (bukti audit) | Penutup |
|---|---|---|
| G1 | Laba tahun berjalan tidak pernah dipindahkan ke ekuitas — neraca tahun berikutnya salah | `closing_engine.year_close/year_reopen` (jurnal penutup 31-12, idempoten, pembalik berjejak) |
| G2 | Tutup bulan hanya menandai; mutasi bank belum cocok/tagihan menunggu tetap lolos | `closing_engine.close_check/close_period` (9 pemeriksaan, **hold** + terobosan beralasan) |
| G3 | Arus kas hanya konsolidasi — owner tidak tahu proyek mana yang menghisap kas | `gl_project_cash.cash_flow_projects` (+ baris "tidak teralokasi" + **tie-out**) |
| G4 | Direksi membuka 6 layar dan MENEBAK apakah bukunya sudah ditutup | `owner_pack.owner_pack/closing_history` (status penutupan + honest-null `missing[]`) |
| G5 | Faktur salah tidak punya jalan pengganti/batal; tidak ada berkas untuk DJP | `tax_faktur_export` (pengganti kode 011, pembatalan beralasan, **ekspor XML Coretax + CSV** yang MENAHAN diri) |
| G6 | Potongan PPh hanya bisa dicatat di luar sistem → bukti potong tanpa pasangan di buku | `withholding_engine` + `POST /finance/ap/bills/{id}/pay-withholding` (NETO ke vendor, Utang Pajak, bukti potong otomatis) |
| G7 | SPT Masa PPN tidak bisa disusun dari data sistem | `tax_faktur_export.vat_return` (keluaran − masukan + `reconstruct` + status) |

---

## 3. Aturan yang DIPAKSAKAN (bukan imbauan)

### 3.1 Tutup bulan (49A)
1. `GET /api/gl/periods/close-check?period=YYYY-MM` menjalankan 9 pemeriksaan:
   jurnal seimbang, mutasi bank dicocokkan, bukti transfer pelanggan, tagihan vendor menunggu,
   uang muka subkon, rekap upah, penyusutan bulan itu, tie-out subledger, tahanan 3-way.
2. Keadaan per item memakai SSOT `closing_check_state`: `ok` / `blocking` / `warning` /
   `missing_data`. **"Belum ada data" bukan "beres"** — bulan tanpa mutasi bank tidak boleh
   mengaku sudah dicocokkan.
3. `POST /api/gl/periods/close` **DITAHAN 409** bila ada `blocking`, dan pesannya menyebut
   sebab satu per satu (nilai + jumlah dokumen + tautan halaman sumber).
4. Menerobos butuh izin `gl:close_override` **dan** alasan ≥10 huruf. Terobosan menyimpan
   `override_by`, `override_reason`, `override_items[]`, potret daftar periksa, jejak audit,
   dan **melahirkan tugas tinjauan** (WorkHub, prioritas urgent).
5. Batas tanggal pemeriksaan **inklusif hari terakhir bulan** — cacat off-by-one yang pernah
   meloloskan penutupan dijaga oleh gate 37 (M04) dan POC.

### 3.2 Tutup tahun (49B)
1. `POST /api/gl/year/close` menutup pendapatan/beban tahun itu ke **Laba Ditahan (3-1900)**
   lewat satu jurnal seimbang bertanggal **31 Desember** tahun tersebut.
2. Idempoten lewat `source_event = year_close:{org}:{year}` → panggilan kedua menjawab
   `idempotent: true` **tanpa** jurnal kedua.
3. `POST /api/gl/year/reopen` **membalik** (bukan menghapus) jurnal penutup; alasan ≥10 huruf
   wajib; `reversal_entry_no` tersimpan sebagai jejak.
4. Tahun tidak boleh ditutup selama masih ada bulan bertransaksi yang terbuka
   (`GET /api/gl/year/check` menyebut bulan mana).

### 3.3 Arus kas per proyek (49C)
1. Proyek disimpulkan dari dokumen sumber jurnal (peta `DIRECT_COLLECTIONS` /
   `VIA_DEAL_COLLECTIONS` / `payments_out`).
2. Yang tidak bisa dibuktikan **tetap tampil** sebagai "Tidak teralokasi ke proyek" — tidak
   pernah dibagi rata.
3. `tie_out.matches` membuktikan Σ(proyek + tidak teralokasi) = arus kas konsolidasi; bila
   selisih, laporan menyatakan dirinya **tidak boleh dipakai**.

### 3.4 Paket laporan owner (49D)
1. Satu jawaban: neraca, laba-rugi (dengan pembanding), arus kas, laba per proyek, arus kas per
   proyek, rasio — **satu potongan waktu**.
2. Status penutupan ikut dibawa: `status`, `closed_by`, `closed_at`, `override_by/reason`, dan
   status tutup tahun.
3. `trust_note`: periode TERBUKA diberi peringatan angkanya masih bisa berubah.
4. Bagian yang memang kosong masuk `missing[]` — **bukan Rp 0**.

### 3.5 e-Faktur (49E)
1. Pengganti: nomor seri **baru** berkode status pengganti (`010` → `011`), faktur lama
   ditandai `replaced` dengan jejak dua arah (`replaced_by_number` ↔ `replaces_number`).
2. Pembatalan: alasan ≥10 huruf, tidak bisa dua kali, dan faktur batal **tidak bisa diganti**
   (harus terbit baru).
3. Ekspor `coretax_xml` / `excel_csv` per masa pajak **MENAHAN** (409) bila NPWP perusahaan
   kosong atau ada faktur wajib-NPWP yang belum lengkap — pesan menyebut **faktur mana**.
4. NPWP 15 digit lama dinormalkan menjadi 16 digit (PMK 112/2022) dan **pemakai diberi tahu**
   perubahannya (`normalized[]`), tidak diubah diam-diam.

### 3.6 e-Bupot (49F)
1. Nomor bukti potong 10 digit: 2 digit seri (`tax.bupot_series`) + 8 digit urut.
2. **Idempoten per (basis, ref_id)** — satu potongan nyata tidak boleh dilaporkan dua kali.
3. Pembetulan: **nomor TETAP** (PER-24/PJ/2021), versi naik, nilai lama tersimpan di `history`.
4. Pembatalan beralasan; bukti yang dibatalkan tidak bisa dibetulkan lagi, tetapi bukti baru
   boleh terbit dengan nomor baru.
5. `POST /finance/ap/bills/{id}/pay-withholding`:
   `Dr 2-1100 (bruto) / Cr 1-1200 (neto) / Cr 2-1300 (potongan)` — potongan **tidak boleh**
   sama dengan atau melebihi nilai pembayaran.
6. Tie-out: potongan NYATA di pembukuan (pembayaran tagihan + fee mitra) vs bukti potong yang
   terbit. Selisihnya dilaporkan apa adanya ("… sudah dipotong tetapi BELUM diterbitkan bukti
   potongnya — pihak yang dipotong tidak bisa mengkreditkannya").
7. PDF bukti potong bisa dicetak untuk diberikan kepada pihak yang dipotong.

### 3.7 Rekap SPT Masa PPN (49G)
1. `net = PPN keluaran − PPN masukan`; status SSOT `vat_return_state`
   (`kurang_bayar` / `lebih_bayar` / `nihil` / `missing_data`).
2. Faktur **batal & diganti tetap terbaca jumlahnya** tetapi tidak dihitung sebagai keluaran.
3. `reconstruct` menuliskan cara menghitungnya supaya bisa diaudit ulang pembaca.
4. Masa tanpa faktur & tanpa tagihan masukan mengaku **"belum ada data"**, bukan "nihil".

---

## 4. Peta endpoint → layar

| Endpoint | Layar |
|---|---|
| `GET /api/gl/periods`, `/periods/close-check`, `POST /periods/close|reopen` | `/accounting?tab=closing` → **Penutupan Buku** |
| `GET /api/gl/year`, `/year/check`, `POST /year/close|reopen` | `/accounting?tab=closing` → panel **Tutup Tahun Buku** |
| `GET /api/gl/reports/cash-flow-projects` | `/accounting/reports?tab=cfproj` → **Arus Kas per Proyek** |
| `GET /api/gl/reports/owner-pack`, `/closing-history` | `/accounting/reports?tab=owner` → **Paket Laporan Owner** |
| `GET/POST /api/tax/compliance/faktur*`, `/faktur-export/*` | `/tax?tab=faktur-export` → **e-Faktur & Ekspor** |
| `GET/POST /api/tax/compliance/withholding*`, `/withholding-export/*` | `/tax?tab=bupot` → **Bukti Potong (e-Bupot)** |
| `GET /api/tax/compliance/vat-return` | `/tax?tab=vat` → **Rekap SPT Masa PPN** |
| `POST /api/finance/ap/bills/{id}/pay-withholding` | `/finance?tab=ap` → dialog **Bayar Tagihan** (opsi "Potong PPh") |

## 5. Izin (RBAC)

| Aksi | Izin |
|---|---|
| Melihat daftar periksa/laporan | `gl:view` |
| Menutup periode | `gl:update` |
| **Menerobos** daftar periksa | `gl:close_override` (Manajer Keuangan/Direksi) |
| Buka kembali periode | `gl:approve` |
| Tutup/buka tahun buku | `gl:year_close` (Direksi/super admin) |
| Melihat pajak | `tax:view` |
| Pengganti/batal faktur, betulkan/batalkan bukti potong | `tax:update` |
| Menerbitkan bukti potong | `tax:withholding_issue` |
| Mengeluarkan berkas ekspor | `tax:export` |

## 6. Setelan (Pusat Konfigurasi → Pajak & Kepatuhan)

| Kunci | Arti |
|---|---|
| `tax.company_npwp` | NPWP perusahaan (pemungut/pemotong). Kosong → **semua ekspor ditahan** |
| `tax.company_idtku` | IDTKU (identitas tempat kegiatan usaha) untuk berkas Coretax |
| `tax.pph23_rate` | Tarif bawaan PPh 23 (%) |
| `tax.pph4_2_konstruksi_rate` | Tarif bawaan PPh 4(2) jasa konstruksi (%) |
| `tax.bupot_series` | 2 digit seri nomor bukti potong |

## 7. Guardrail

| Berkas | Peran |
|---|---|
| `poc/poc_49.py` | POC inti Fase 49 — **96 pemeriksaan** (tutup bulan/tahun, tie-out, e-Faktur, e-Bupot, SPT PPN) + cleanup ketat |
| `scripts/verify_closing.py` | **Gate 37** — penutupan bergigi, tutup tahun reversible, tie-out arus kas proyek, laporan owner jujur |
| `scripts/verify_tax_compliance.py` | **Gate 38** — e-Faktur (hold/pengganti/batal/ekspor), e-Bupot (idempoten/nomor tetap/PDF/ekspor), rekap SPT PPN |
| `scripts/mutasi_49.py` | 24 mutasi yang mematikan aturan satu per satu untuk membuktikan gate 37/38 bergigi |
| `scripts/_fixture49.py` | bahan uji sendiri (tahun 2024 yang kosong di data demo) + `purge()`/`orphans()` |
| `backend/seed_phase49.py` | data demo idempoten: identitas pajak contoh, 1 faktur (pembeli tanpa NPWP → jalur ekspor DITAHAN bisa dicoba), 1 tagihan dibayar potong PPh (bukti potong otomatis) |

## 8. Keputusan desain yang perlu diingat

1. **Seed tidak boleh menghabiskan bahan uji.** Faktur demo memakai deal sendiri (unit yang
   dibukukan bulan lalu) supaya deal ber-AR yang belum berfaktur tetap tersedia untuk POC/gate.
   Kalau tidak, uji inti hanya bisa hijau di database kosong.
2. **Data demo tidak menetap di masa pajak berjalan**, karena masa berjalan adalah ruang kerja
   uji inti (PPN keluaran & ekspor yang ditahan dihitung di sana).
3. **Seed tidak menekan tombol milik manusia**: tidak ada bulan/tahun yang ditutup, dan
   potongan PPh fee mitra dibiarkan sebagai "kandidat" agar daftar kerja e-Bupot jujur.
4. **Layar tidak menghitung tarif pajak sendiri** — tarif selalu dari Pusat Konfigurasi
   (`withholding/config`), sehingga hanya ada satu sumber angka pajak.
