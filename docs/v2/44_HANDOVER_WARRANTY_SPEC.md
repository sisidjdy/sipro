# 44 — SPEC SERAH TERIMA UNIT, MASA GARANSI & KLAIM PASCA-HUNI (Fase 50A)

> Dasar: audit kode terhadap API nyata (bukan dugaan). Cakupan: (a) berita acara serah terima
> (BAST) bernomor + PDF, (b) daftar periksa yang **menahan** penyerahan kunci, (c) terobosan
> beralasan yang berjejak, (d) masa garansi **per bagian** pekerjaan, (e) klaim garansi
> pasca-huni yang melahirkan pekerjaan nyata, (f) laporan klaim yang bisa dijumlahkan.

---

## 1. Yang SUDAH ADA sebelum Fase 50A (jangan dibangun ulang)

| Modul | Kemampuan |
|---|---|
| `reference.py` (`unit_status`) | nilai `handed_over` sudah ada sejak Fase 39 |
| `routers/ar_router.py` (`POST /ar/{deal}/bast`) | **hanya** mengakui pendapatan di buku besar |
| `inspection.py`, `punch` (Fase 36/46) | inspeksi mutu + temuan punch list per unit |
| `doc_registry.py`, `pdf_utils.py` | matriks dokumen syarat + pembuat PDF berkop |
| `complaints_router.py` | keluhan pelanggan (CS) tanpa jalur kerja pasca-huni |
| `settings_store.py` (`retention.months`) | **satu** angka masa retensi untuk semua pekerjaan |

## 2. Enam lubang yang ditutup Fase 50A

| Kode | Lubang (bukti audit) | Penutup |
|---|---|---|
| H1 | `handed_over` **tidak pernah ditulis siapa pun** — tanggal serah terima tidak bisa dibuktikan, padahal itu titik nol semua kewajiban pasca-huni | `handover_engine.issue` + koleksi `unit_handovers` (BAST bernomor `BAST/{tahun}/{urut}`) |
| H2 | Kunci bisa diserahkan walau temuan masih terbuka / pembayaran menggantung / inspeksi belum ada | `handover_engine.handover_check` (6 pemeriksaan) + **tahanan 409** dengan sebab satu per satu |
| H3 | Tidak ada jalan sah untuk kasus mendesak, sehingga aturan dilewati di luar sistem | terobosan `handover:override` + alasan ≥10 huruf + `override_items[]` + potret daftar periksa + **tugas tinjauan** |
| H4 | Garansi tanpa masa: satu angka untuk struktur dan cat | masa **per bagian** dari Pusat Konfigurasi (`warranty.*_months`), tanggal mulai = tanggal BAST |
| H5 | Keluhan pasca-huni berhenti sebagai komplain CS: tidak melahirkan pekerjaan, tidak menuntut bukti, tidak ada pemisahan tugas | `warranty_engine` (klaim → `punch_items` + tugas → bukti foto → pemeriksa lain → pengakuan pembeli) |
| H6 | Klaim yang lewat masa garansi hilang sebagai pesan galat | klaim **tetap tercatat** berstatus `ditolak` + `reject_reason` + tanggal habisnya |

---

## 3. Aturan yang DIPAKSAKAN (bukan imbauan)

### 3.1 Daftar periksa serah terima (`GET /api/handover/check?unit_id=`)
Enam pemeriksaan, keadaannya memakai SSOT `handover_check_state`
(`ok` / `blocking` / `warning` / `missing_data`):

| Kode item (SSOT `handover_check_item`) | Menahan bila | Sumber kebenaran |
|---|---|---|
| `pembangunan_selesai` | `units.construction_status` bukan `done`/`ready_handover` | status unit (SSOT Fase 39) + progres jadwal sebagai bukti pendukung |
| `punch_terbuka` | ada temuan `open`/`in_progress` | `punch_items` |
| `inspeksi_serah_terima` | belum ada / gagal / belum difinalisasi | `inspections` kategori `handover` |
| `pelunasan_belum` | `ar_invoices.outstanding > 0` | jadwal tagihan AR |
| `dokumen_wajib_kurang` | matriks dokumen wajib belum `verified` | `doc_registry.matrix` |
| `bast_sudah_terbit` | **tidak menahan** (peringatan) — penerbitan ulang idempoten | `unit_handovers` |

1. Setiap baris WAJIB menyebut **item + keadaan + sebab** memakai label kamus data, plus
   tautan halaman sumbernya (`source`) supaya penahanan bisa ditindak, bukan diperdebatkan.
2. Sebab menyebut **isi**, bukan hanya jumlah: nama temuan ("Keramik kamar mandi pecah") dan
   nominal ("Sisa kewajiban pembeli Rp 120.000.000 dari total …").
3. **"Belum ada data" bukan "beres".** Rumah tanpa transaksi pembeli ditulis `missing_data`
   untuk pelunasan & dokumen — tidak pernah dihitung lunas.

### 3.2 Penerbitan BAST (`POST /api/handover/issue`)
1. **Ditahan 409** bila ada item `blocking`; jawaban memuat `reasons[]` + `items[]`.
2. Status rumah **tidak berubah** saat penerbitan ditahan.
3. Menerobos butuh izin `handover:override` (Manajer Keuangan/Direksi). Manajer Proyek yang
   boleh menerbitkan (`handover:create`) **tetap 403** untuk menerobos — itu pemisahan tugas.
4. Alasan terobosan ≥10 huruf, dijaga DUA lapis: kontrak permintaan (`models_p50.HandoverIssue`)
   dan mesin (`handover_engine.issue`).
5. Terobosan menyimpan `override_by`, `override_reason`, `override_items[]` (kode pemeriksaan
   yang dilewati), **potret** `checklist[]`, jejak audit, dan melahirkan **tugas tinjauan**
   (`related_entity_type="unit_handover"`, prioritas urgent).
6. **Idempoten**: rumah yang sudah punya BAST aktif tidak melahirkan dokumen kedua — dokumen
   lama diputar ulang (`replay: true`). Nomor dokumen tetap stabil.
7. Sukses menulis `units.status = handed_over` + `handover_id/number/handed_over_at`, dan
   menyalin tanggal serah terima ke `deals`.
8. `client_ref` opsional → aman diputar ulang dari antrean perangkat (lihat spec 45).

### 3.3 Pembatalan BAST (`POST /api/handover/{id}/cancel`)
1. Butuh izin `handover:cancel` (finance biasa **403**) + alasan ≥10 huruf (dua lapis).
2. **DITOLAK** selama masih ada klaim garansi berjalan (`diajukan`/`dikerjakan`/`selesai`/
   `diverifikasi`) — kalau tidak, pekerjaan perbaikan kehilangan dasarnya.
3. Dokumen **tidak dihapus**: `state = cancelled` + `cancel_reason` + `cancelled_by/at`;
   pembatalan kedua ditolak; status rumah dikembalikan (`sold`/`available`) dan
   `handover_id/number/handed_over_at` dibersihkan; lahir tugas tinjauan.

### 3.4 Masa garansi (`GET /api/handover/warranty/plan|unit|board`)
1. Masa per bagian (SSOT `warranty_category`) dibaca dari Pusat Konfigurasi — **bukan angka
   mati**: `warranty.struktur_months` (120), `atap_plafon` (12), `dinding_lantai` (12),
   `plumbing` (6), `listrik` (6), `kusen` (6), `finishing` (3).
2. `starts_at` = tanggal BAST; `expires_at` = `add_months()` kalender (31 Jan + 1 bulan =
   28/29 Feb, tidak pernah "32 Februari").
3. Keadaan per bagian memakai SSOT `warranty_state`: `aktif` / `hampir_habis`
   (≤ `warranty.expiring_days`, bawaan 30 hari) / `habis`.
4. Rumah yang belum diserahterimakan menjawab `missing: true` + kalimat "belum ada data,
   bukan nol hari" — **tidak** menampilkan 0 bulan garansi.

### 3.5 Klaim garansi (`/api/handover/claims*`)
1. **Tidak ada klaim tanpa BAST** (masa garansi belum punya titik nol) → 400 beralasan.
2. Klaim atas bagian yang masa garansinya **habis** tetap **tercatat** dengan
   `state = ditolak`, `reject_reason = lewat_masa_garansi`, dan `reject_detail` menyebut
   tanggal habisnya + berapa hari lalu. Bagian bermasa 0 bulan → `di_luar_lingkup`.
3. Klaim sah masuk daftar kerja: `state = diajukan`, SLA dari `warranty.claim_sla_days`,
   melahirkan tugas review untuk Manajer Proyek proyek itu.
4. **Keputusan bukan milik pengaju**: `warranty:update` (PM/site). Sales/CS yang mengajukan
   (`warranty:create`) mendapat **403** di `/decide`.
5. Diterima → lahir **pekerjaan nyata** `punch_items` (`source = warranty_claim`,
   `warranty_claim_id`, severity `high`, target dari `warranty.fix_days`) + tugas urgent.
6. Ditolak manual → wajib alasan ≥10 huruf **dan** sebab dari SSOT `warranty_reject_reason`.
7. `selesai` **wajib bukti foto** (dijaga tiga lapis: `Field(min_length=1)`, validator kontrak,
   dan mesin). Catatan saja tidak cukup.
8. `verify` butuh `warranty:approve` **dan** pemeriksa ≠ `completed_by` (pemisahan tugas
   dijaga di DATA, bukan di layar). Tidak lulus → kembali `dikerjakan` + alasan ≥10 huruf +
   tugas ulang, dan `completed_by/at` dikosongkan supaya orang yang sama boleh mencoba lagi.
9. `close` menyimpan **pengakuan pembeli** (`ack_by`, `ack_note`), menutup punch itemnya
   (tidak menggantung), dan menandai komplain CS asalnya `resolved`.

### 3.6 Laporan yang tidak berbohong (`GET /api/handover/claims/report`)
1. `per_state` disusun dari SSOT `warranty_claim_state` — laporan tidak bisa kehilangan satu
   status hanya karena penulis laporan lupa menambahkannya.
2. `tie_out.matches` membuktikan **Σ klaim per status = jumlah klaim**.
3. Saringan tanpa klaim menjawab `missing: true`, `avg_days_to_close: null`, dan
   `avg_days_note` "belum ada data … (bukan 0 hari)".

---

## 4. Peta endpoint ↔ layar

| Endpoint | Izin | Layar (testId) |
|---|---|---|
| `GET /handover/check` | `handover:view` | `/units/{id}` tab **Serah Terima & Garansi** → `p50-handover-panel`, item `p50-handover-check-item` |
| `POST /handover/issue` | `handover:create` (+`override`) | `p50-handover-issue-btn` → dialog `p50-handover-issue-dialog` (`…-override`, `…-reason`, `…-submit`) |
| `GET /handover` | `handover:view` | daftar BAST (papan garansi & tab unit) |
| `GET /handover/{id}` · `/pdf` | `handover:view` | kartu `p50-handover-doc` + tombol `p50-handover-pdf-btn` |
| `POST /handover/{id}/cancel` | `handover:cancel` | `p50-handover-cancel-btn` → `p50-handover-cancel-dialog` |
| `GET /handover/warranty/plan` | `warranty:view` | baris rencana `p50-warranty-plan-row` |
| `GET /handover/warranty/unit` | `warranty:view` | panel `p50-warranty-panel` / `p50-warranty-missing` |
| `GET /handover/warranty/board` | `warranty:view` | `/construction` tab **Garansi** (`build-tab-warranty` → `p50-warranty-board-panel`) |
| `GET /handover/warranty/for-complaint` | `warranty:view` | tombol `p50-complaint-to-claim-btn` di lembar komplain CS |
| `POST /handover/claims` | `warranty:create` | `p50-claim-new-btn` → `p50-claim-dialog` |
| `POST /handover/claims/{id}/decide` | `warranty:update` | `p50-claim-decide-btn` / `p50-claim-reject-btn` |
| `POST /handover/claims/{id}/complete` | `warranty:update` | `p50-claim-complete-btn` (+ `p50-claim-action-photos`) |
| `POST /handover/claims/{id}/verify` | `warranty:approve` | `p50-claim-verify-btn` / `p50-claim-rework-btn` |
| `POST /handover/claims/{id}/close` | `warranty:approve` | `p50-claim-close-btn` (+ `p50-claim-action-ack`) |
| `GET /handover/claims/report` | `warranty:view` | kartu `p50-warranty-report` (+ `…-tieout`, `…-missing`) |
| `GET /portal/warranty` | pembeli (OTP) | Portal tab **Garansi** (`portal-tab-warranty`) |
| `POST /portal/warranty/claims` | pembeli (OTP) | `p50-portal-claim-btn` → `p50-portal-claim-dialog` |
| `GET /portal/warranty/claims` | pembeli (OTP) | `p50-portal-claim-row` |

> Catatan RBAC: klaim dari portal **tidak** boleh memilih `source` (model `PortalWarrantyClaim`
> memaksa `portal_pembeli`) — kalau boleh, laporan asal klaim bisa dipalsukan menjadi "temuan
> internal".

---

## 5. Data & index

| Koleksi | Isi | Index unik |
|---|---|---|
| `unit_handovers` | BAST: nomor, tanggal, penerima, meter air/listrik, jumlah kunci, potret daftar periksa, terobosan, `warranties[]` | `uq_handover_number` (`org_id`,`number`) |
| `warranty_claims` | klaim: nomor `KG/{tahun}/{urut}`, kategori, asal, keadaan, penolakan berjejak, bukti foto, pemeriksa, pengakuan pembeli | `uq_warranty_claim_number` (`org_id`,`number`) |
| `punch_items` | pekerjaan perbaikan garansi (`source = warranty_claim`) | — |
| `tasks` | tugas review terobosan / klaim / perbaikan | — |

Data demo (`seed_phase50.py`, idempoten, `demo_batch="fase50"`): satu unit **siap BAST**
(`A-06`), satu unit **sudah BAST** (`B-01`, `BAST/2025/0001`), dan 2 klaim (satu berjalan,
satu ditolak karena lewat masa garansi).

---

## 6. Guardrail (cara membuktikan cepat)

```
python3 poc/poc_50.py                          # POC core Fase 50A
python3 scripts/verify_handover_warranty.py    # GATE 39 — 43 pemeriksaan
python3 scripts/mutasi_50.py --check           # pola 37 mutasi masih ada di kode
python3 scripts/mutasi_50.py                   # uji-mutasi penuh (gate wajib MERAH saat dirusak)
bash scripts/run_all_gates.sh                  # 40 gates
```

Gate 39 menjaga sepuluh janji: (H1) daftar periksa berlabel kamus data, (H2) empat sebab nyata
menahan + status rumah tak berubah, (H3) terobosan butuh izin + alasan ≥10, (H4) terobosan
berjejak + lahir tugas, (H5) idempoten + PDF nyata, (H6) masa garansi dari Pusat Konfigurasi,
(H7) pembatalan beralasan & ditahan saat klaim berjalan, (H8) klaim kedaluwarsa tercatat,
(H9) bukti foto + pemisahan tugas + pengakuan pembeli, (H10) rekap tie-out & honest-null.
