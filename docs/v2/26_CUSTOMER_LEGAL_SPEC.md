# 26 — SPEC CUSTOMER MANAGEMENT, LEGAL & PEMBAYARAN

> Keputusan owner yang mengikat: **D4** (AJB/BAST urusan Customer, bukan lead) · **D7** (BI/SLIK manual & terpisah) · **D9** (sub-alur KPR hanya untuk skema KPR) · koreksi owner 16 Agu 2026:
> • *"pilih rumah sudah di lead lifecycle"* • *"berkas ada ketika sudah deal"* • *"SLIK bank dilakukan terpisah di menu BI Checking"* • *"yang jadi step adalah SP3K dan akad kredit"*
> • *"tiap tipe pembayaran komponennya berbeda, KPR komponennya sangat banyak"* • *"spek tambahan / lahan lebih di-set saat reservasi/booking, di finance jadi komponen terpisah"*.
> Sumber angka: `[DOC]` = 4 dokumen owner di `docs/source_templates/`. Menutup CR-03, CR-06, CR-07, CR-08, CR-18, CR-26.

## 1. Batas domain (siapa memegang apa)

| Domain | Objek | Berakhir di |
|---|---|---|
| **Lead** (Dok 24) | `leads`, `appointments`, `deals` (reservasi + SPR) | tahap `won` = **konversi ke Customer** |
| **Customer** (dokumen ini) | `customers`, `contracts`, `payment_plans`, `kpr_applications`, `documents` legal, `receipts`, serah terima, retensi | BAST + retensi selesai |
| **BI Checking** (menu tersendiri) | `slik` di lead & customer, hasil + bukti iDeb, termasuk **SLIK versi bank** | dipakai sebagai bukti oleh kedua domain |

Satu menu di UI: **CRM › Customer & Kontrak** (menggabungkan "Deal & Unit" + "Customer & KPR" lama — CR-18).

## 2. Konversi Lead → Customer
Pemicu: `[CFG] lead.won_trigger` (default `spr_signed`).
Langkah atomik (satu transaksi logis, idempoten via `source_event="lead.convert:{lead_id}"`):
1. `customers` dibuat/ditautkan (dedup by telepon+NIK), `lead_id`, `converted_at`, salin data diri + demografi + `spouse{}`.
2. `contracts` dibuat status `draft`: `deal_id, customer_id, unit_id, scheme, price_breakdown{}, total`.
3. `payment_plans` dibuat dari **template skema** (§5) — termin & jatuh tempo terisi otomatis, bisa diedit sebelum `active` (dengan audit).
4. `unit.sales_status='booked'`, `unit.customer_id`, `unit.contract_id` (W2/W3).
5. `kpr_applications` dibuat **hanya bila** `scheme='kpr'` (D9).
6. Dokumen yang sudah verified di lead **diwarisi** (tidak diminta ulang) — `doc_submissions.entity_type` ditambah baris `customer` yang merujuk `file_id` sama.
7. Tugas administrasi lahir (jobdesk `CS-01` kelengkapan berkas, `FIN-01` verifikasi pembayaran pertama).

**BI/SLIK tidak pernah menjadi langkah wajib di sini** (D7) — hanya panel bukti + gerbang opsional `[CFG] slik.gate`.

## 3. Skema pembayaran & KOMPONEN BIAYA (koreksi owner: komponen berbeda per skema)

SSOT baru `payment_scheme`: `cash_keras`, `cash_bertahap`, `kpr` (+ `cash_tempo` bila diaktifkan `[CFG]`).

### 3.1 Master komponen biaya (`price_components` — bisa ditambah admin)
Setiap komponen punya: `code, label, group, applies_scheme[], calc(fixed|percent_of|per_m2|manual), value, taxable, finance_treatment, gl_account, editable_by_role, order, active`.

**`finance_treatment` (penting untuk akuntansi — jangan dicampur):**

| Nilai | Arti | Akun default | Contoh |
|---|---|---|---|
| `revenue` | pendapatan developer | `4-1100` Penjualan | harga unit, **spek tambahan**, kelebihan tanah, hook |
| `pass_through` | dititipkan pembeli untuk dibayarkan ke pihak ketiga | `2-1450` Titipan Pelanggan | BPHTB, notaris, biaya bank, asuransi |
| `discount` | pengurang pendapatan | kontra `4-1200` | promo all-in, diskon |
| `deposit` | uang muka/titipan sebelum diakui | `2-1450` | booking fee sebelum dialihkan |
| `tax_out` | pajak yang dipungut/disetor | `2-1300` Utang Pajak | PPN (bila berlaku), PPh penjual |

> ⚠️ **Rekomendasi akuntansi yang perlu owner setujui (OQ-9):** BPHTB / notaris / biaya bank ditagih ke pembeli tetapi **bukan pendapatan** — diperlakukan `pass_through` (titipan) supaya laba tidak digelembungkan. Bila owner menghendaki diakui sebagai pendapatan jasa, cukup ubah `finance_treatment` di master (tanpa ubah kode).

### 3.2 Matriks komponen per skema (default seed, dari `[DOC]`)

| Komponen (`code`) | cash_keras | cash_bertahap | kpr | treatment | Sumber |
|---|---|---|---|---|---|
| `unit_price` harga unit tipe | ✔ | ✔ | ✔ | revenue | `[DOC]` Rp166.000.000 (tipe 30/60) |
| `addon_spec` spek bangunan tambahan | ✔ | ✔ | ✔ | revenue | master addon (§4) |
| `excess_land` kelebihan tanah | ✔ | ✔ | ✔ | revenue | `[DOC]` SPKT |
| `hook_fee` biaya hook | ✔ | ✔ | ✔ | revenue | `[DOC]` Rp3.000.000 |
| `booking_fee` booking fee | ✔ | ✔ | ✔ | deposit | `[DOC]` Rp1.000.000 |
| `down_payment` uang muka/DP | ✔ (80%) | ✔ (80%) | ✔ (%) | — (termin) | `[DOC]` |
| `bphtb` BPHTB | ✔ | ✔ | ✔ | pass_through | `[DOC]` Rp4.000.000–4.300.000 |
| `notary_fee` biaya notaris/akad | ✔ | ✔ | ✔ | pass_through | `[DOC]` Rp13.200.000–14.400.000 |
| `bank_fee` biaya bank | ✖ | ✖ | ✔ | pass_through | `[DOC]` Rp10.500.000 (provisi, admin, blokir angsuran, materai) |
| `pph_seller` PPh | ✔ | ✔ | ✔ | tax_out | `[DOC]` (Rp0 pada contoh) |
| `insurance` asuransi jiwa/kebakaran | ✖ | ✖ | ✔ | pass_through | umum KPR |
| `promo_discount` promo all-in | ✔ | ✔ | ✔ | discount | `[DOC]` −Rp2.000.000 |
| `plafon_kredit` plafon bank | ✖ | ✖ | ✔ | info (bukan tagihan) | `[DOC]` Rp160.340.000 |
| `self_funding` selisih harga − plafon | ✖ | ✖ | ✔ | — (termin) | turunan |

**Rumus total yang ditagih ke pembeli** `[CALC]`:
```
gross      = unit_price + addon_spec + excess_land + hook_fee
nett_price = gross - promo_discount
costs      = bphtb + notary_fee + bank_fee + insurance + pph_seller
total_bill = nett_price + costs
kpr:  self_funding = nett_price - plafon_kredit  (bila negatif → 0, sisa plafon tidak boleh melebihi harga)
cash: payable_by_buyer = total_bill - booking_fee(dialihkan)
```
Setiap komponen tersimpan sebagai **baris** `contracts.price_breakdown[]` — bukan satu angka — supaya SPR, AR, dan laporan bisa merinci (permintaan owner: "di finance ini jadi komponen terpisah").

## 4. SPEK TAMBAHAN / ADD-ON (permintaan baru owner)
Master `addon_items` (lihat [28](28_PROJECT_UNIT_SPEC.md) §5 untuk relasi unit):

| Field | Contoh |
|---|---|
| `code`,`name` | `SPEC-KANOPI`, "Kanopi carport" |
| `category` (SSOT `addon_category`) | `spek_bangunan`, `kelebihan_tanah`, `posisi_unit(hook)`, `interior`, `utilitas`, `lainnya` |
| `pricing_mode` | `lump_sum` · `per_m2` · `per_unit_item` · `percent_of_price` |
| `unit_price` / `price_per_m2` | Rp2.000.000/m² `[DOC]` SPKT |
| `finance_treatment` | default `revenue` |
| `gl_account` | `4-1100` (atau akun pendapatan lain-lain bila dipisah) |
| `applies_to` | `project_id[]`, `unit_type[]`, atau semua |
| `requires_document` | mis. `kelebihan_tanah` → wajib **SPKT** ([27](27_DOCGEN_SPEC.md)) |
| `needs_approval_role` | mis. diskon spek butuh `sales_manager` |
| `active`, `order`, `note` | |

**Kapan dipilih:** saat **reservasi/booking** (permintaan owner) — endpoint `POST /api/deals/{id}/addons` `{items:[{addon_code, qty, agreed_price?, note}]}`; perubahan setelah SPR terbit wajib `change_order` beralasan + regenerasi dokumen.
**Kelebihan tanah** khusus: `qty` = m² estimasi, `agreed_price` = harga/m² yang disepakati; sistem menandai **estimasi** sampai ada hasil ukur akhir (`final_measurement{ m2, at, by, file_id }`) lalu menghitung selisih tagihan otomatis `[DOC]`. Wajib SPKT & wajib lunas **sebelum akad kredit** `[DOC]`.
**Finance:** setiap add-on menjadi **baris tersendiri** di `contracts.price_breakdown[]`, `ar_invoices.lines[]`, dan jurnal (akun sesuai master) — tidak boleh dilebur ke `unit_price`.

## 5. Rencana bayar (`payment_plans`) per skema — aturan dari `[DOC]`

### 5.1 `cash_keras` (SPR CASH)
| Termin | Nominal | Jatuh tempo | Sumber |
|---|---|---|---|
| T1 Booking fee | `booking_fee` | saat keep unit | `[DOC]` |
| T2 DP tahap pertama | **80%** dari harga jual | sebelum pembangunan dimulai (pembangunan **mulai setelah T2 diterima**) | `[DOC]` |
| T3 Pelunasan | **20%** | setelah progres **100%**, maks **30 hari kalender** sejak pemberitahuan; perpanjangan **7 hari** | `[DOC]` |
| T4 Biaya-biaya | `costs` | sebelum akad/AJB | `[DOC]` |

### 5.2 `cash_bertahap` (SPR CASH BERTAHAP)
| Termin | Nominal | Jatuh tempo | Sumber |
|---|---|---|---|
| T1 Booking fee | `booking_fee` | saat keep unit | `[DOC]` |
| T2 DP | **80%** | sebelum pembangunan dimulai | `[DOC]` |
| T3…T8 Cicilan pelunasan | **20% ÷ 6** (6× bulanan) | **tanggal 7** tiap bulan; masa toleransi s/d **tanggal 20** → lewat = **menunggak** | `[DOC]` |
| — | — | **tunggak 2 bulan** (berurutan **atau** akumulatif) ⇒ developer berhak **membatalkan sepihak** & menjual ulang | `[DOC]` |

### 5.3 `kpr` (SPR KPR)
| Termin | Nominal | Jatuh tempo | Sumber |
|---|---|---|---|
| T1 Booking fee | `booking_fee` (Rp1.000.000) | saat keep unit | `[DOC]` |
| T2 DP / uang muka | `%` sesuai SPR (contoh 0%) | sebelum akad kredit | `[DOC]` |
| T3 Biaya-biaya (BPHTB, notaris, bank, asuransi) | `costs` | sebelum/saat akad kredit | `[DOC]` |
| T4 Selisih pendanaan (`self_funding`) | harga nett − plafon | sebelum akad kredit | `[CALC]` |
| T5 Pencairan bank | `plafon_kredit` | setelah akad kredit (dana masuk dari bank) | proses bank |
| T6 Kelebihan tanah/add-on | sesuai SPKT | **wajib lunas sebelum akad kredit** | `[DOC]` |

**Struktur termin (`payment_plans.terms[]`)**: `{no, code, label, basis(percent|amount|component), value, amount, due_rule, due_date, status(pending|due|paid|partial|overdue|waived), ar_invoice_id, paid_amount, paid_at, evidence_file_ids[]}`.
**`due_rule`** deklaratif agar bisa dihitung ulang: `on_event:reservation`, `on_event:spr_signed`, `on_event:construction_100`, `on_day_of_month:7`, `days_after_event:{event,days}`, `manual`.
**Toleransi & tunggakan** (`arrears_rule`): `{grace_day:20, late_fee: [CFG], arrears_months_to_cancel:2, notify_days_before:[3,1], escalate_to_role}` — semua `[CFG]` dengan default dari `[DOC]`.

**Link ke finance (tidak boleh terputus — W4/W5):** setiap termin `due` → `ar_invoices` (dengan `lines[]` per komponen) → pembayaran `receipts` → jurnal (`gl_engine.py`) → `revenue_recognitions` mengikuti kebijakan pengakuan yang sudah ada (`contract_liabilities`). Booking fee `deposit` dialihkan ke pendapatan/termin saat SPR sah (jurnal reklas `2-1450 →` termin).

## 6. Sub-alur KPR (D9 + koreksi owner) — **hanya bila `scheme='kpr'`**

```
(pilih rumah & reservasi = SUDAH di lead lifecycle, Dok 24)
        │
        ▼
berkas_lengkap  ──► diajukan_ke_bank ──► [appraisal]* ──► sp3k ──► akad_kredit ──► pencairan
(saat sudah deal)                                   │                │            │
                                                 ditolak         batal        selesai→ lanjut AJB/BAST

* appraisal opsional: [CFG] kpr.use_appraisal_step (default true, bisa dimatikan)
SLIK/BI Checking TIDAK menjadi step di sini — dilakukan di menu BI Checking (D7) dan hasilnya
dilampirkan sebagai bukti pada tahap berkas/SP3K.
```

`kpr_applications` (mengganti/memperluas `financing_apps`):

| Field | Isi |
|---|---|
| `contract_id`, `customer_id`, `unit_id` | tautan wajib |
| `bank`, `bank_branch`, `officer{name,phone}` | SSOT `financing_bank` (sudah ada) |
| `requested_plafon`, `approved_plafon`, `tenor_months`, `rate`, `installment` | angka bank |
| `stage` | `berkas_lengkap \| diajukan_ke_bank \| appraisal \| sp3k \| akad_kredit \| pencairan \| ditolak \| batal` |
| `stage_history[]` | `{from,to,at,actor,reason,evidence[]}` (W6) |
| `submission` | `{submitted_at, submitted_by, doc_submission_ids[]}` |
| `appraisal` | `{scheduled_at, done_at, value, notes, file_id}` |
| `sp3k` | `{number, date, plafon, tenor, rate, valid_until, file_id}` — **wajib file** untuk lanjut |
| `akad` | `{date, notary, place, file_id, attendees[]}` |
| `disbursement` | `{date, amount, receipt_id, journal_ref}` |
| `slik_ref` | `{lead_slik_id, bank_slik_result, checked_at, file_id}` (dari menu BI Checking) |
| `rejection` | `{at, reason_code, note, file_id, refund_decision}` |

**Gerbang bukti (tidak bisa dilewati):** `sp3k` butuh `sp3k.file_id` + `approved_plafon>0`; `akad_kredit` butuh `sp3k` valid & (bila ada) add-on/kelebihan tanah **lunas** `[DOC]`; `pencairan` butuh `akad.file_id`.
**SLA per tahap** `[CFG] kpr.sla_days` default: `berkas_lengkap=7` (selaras klausa 7 hari `[DOC]`), `diajukan_ke_bank=14`, `appraisal=7`, `sp3k=14`, `akad_kredit=7`.
**Ditolak bank** ⇒ booking fee **refund 50%** `[DOC]` (aturan di §7), tawarkan: ganti bank (buat pengajuan baru, riwayat tetap), ganti skema ke cash, atau lepas unit dengan alasan `financing_failed`.

## 7. Pembatalan, hangus & refund (engine, dari `[DOC]`)

### 7.1 Booking fee (SPR KPR `[DOC]`)
| Kondisi | Pengembalian | Otomatisasi |
|---|---|---|
| Hasil BI Checking tidak memenuhi kriteria KPR | **100%** | tombol "Ajukan refund" muncul saat `slik.status='rejected'` |
| KPR ditolak bank | **50%** | muncul saat `kpr.stage='ditolak'` |
| Tidak ada kejelasan berkas **7 hari kalender** setelah BI Checking lolos | **hangus** | penjadwal harian menandai `booking_fee_status='forfeited'` + notifikasi |
| Pembeli mengundurkan diri sepihak | **hangus** | saat `cancel` dengan alasan `customer_cancel` |

### 7.2 Pembatalan kontrak (SPR CASH & CASH BERTAHAP `[DOC]`)
| Kondisi | Potongan dari total pembayaran diterima | Catatan |
|---|---|---|
| Batal **sebelum pembangunan dimulai** | **35%** | `unit.build_status='not_started'` |
| Batal **saat pembangunan berlangsung** | **50%** | `build_status='in_progress'` |
| Pengembalian dana | **setelah unit terjual kembali** dan pembayaran pembeli baru diterima | jadi kewajiban bersyarat |

**Implementasi:** `cancellations` (bagian `contracts.cancellation`): `{requested_at, requested_by, reason_code, build_state_at_cancel, paid_total, cut_pct, cut_amount, refund_amount, status(pending|approved|waiting_resale|paid|rejected), resale_deal_id, approvals[], journal_refs[]}`.
Jurnal: pembatalan mengakui potongan sebagai pendapatan lain-lain, sisa jadi **utang refund** (akun kewajiban) yang lunas hanya setelah `resale` — semua idempoten `source_event`.
Semua persentase & syarat = `[CFG]` per proyek (`cancellation.cut_before_build=35`, `cut_during_build=50`, `refund_requires_resale=true`).

## 8. Legal: PPJB → AJB → BAST → Sertifikat → Retensi
Memakai mesin legal yang sudah ada (`deals_router.py:195-268` `legal`, `ppjb`, `ajb` + `document_templates`) tetapi **dipindah ke `contracts`**:

| Tahap | Prasyarat (gerbang) | Bukti | Sumber |
|---|---|---|---|
| `ppjb` | dokumen legal lengkap; DP sesuai skema terbayar | akta/PPJB (file) | umum |
| `akad_kredit` (KPR) | SP3K + add-on lunas | akta kredit | `[DOC]` |
| `pelunasan` | semua termin `paid` + dikonfirmasi **Finance** | konfirmasi finance | `[DOC]` |
| `bast` (serah terima kunci) | **hanya setelah** seluruh kewajiban terbayar & dikonfirmasi Finance; ditandatangani kedua pihak | BAST (file) | `[DOC]` |
| `ajb` | setelah pelunasan & BAST (skema cash) / setelah akad (KPR) | AJB notaris | `[DOC]` |
| `sertifikat` (SHGB) | ± **6 bulan** sejak AJB/PPJB notaris, bila kewajiban lunas | serah terima sertifikat | `[DOC]` |
| `retensi` | mulai setelah akad/AJB; durasi `[CFG] retention.months` (⚠️ OQ-7) | tiket komplain terhubung | `[DOC]` |

Semua tahap menulis `contracts.legal_history[]` (W6) dan memicu tugas + notifikasi. Serah terima juga mengubah `unit.sales_status='handed_over'` dan `unit.build_status='handed_over'` (W3).

## 9. Endpoint (ringkas)
```
GET   /api/customers                      daftar (filter: skema, status bayar, tahap legal, proyek, PIC)
GET   /api/customers/{id}/profile         agregat profil (kontrak, termin, kpr, dokumen, unit, timeline)
POST  /api/contracts                      buat kontrak (biasanya otomatis saat konversi)
GET   /api/contracts/{id}                 detail + price_breakdown
POST  /api/contracts/{id}/addons          tambah/ubah add-on (change order bila sudah SPR)
POST  /api/contracts/{id}/activate        aktifkan kontrak + rencana bayar
GET   /api/contracts/{id}/payment-plan    termin + status + tunggakan
POST  /api/payment-plans/{id}/terms/{no}/invoice   terbitkan AR untuk termin
POST  /api/payment-plans/{id}/terms/{no}/pay       catat pembayaran (bukti wajib)
POST  /api/contracts/{id}/legal/{stage}   ppjb|ajb|bast|sertifikat (dengan bukti)
POST  /api/contracts/{id}/cancel          pembatalan + hitung potongan/refund
GET   /api/kpr                            daftar pengajuan (filter tahap, bank, SLA lewat)
POST  /api/kpr/{id}/stage/{stage}         majukan tahap (validasi bukti)
POST  /api/kpr/{id}/reject                tolak + alasan + keputusan refund
GET   /api/finance/ar/aging               (sudah ada) + kolom termin/kontrak
```

## 10. Definition of Done
1. Tiga skema bayar menghasilkan **termin & komponen berbeda** sesuai `[DOC]`, tidak ada angka hard-code di kode (semua dari master/`[CFG]`).
2. Add-on/spek tambahan muncul sebagai **baris terpisah** di kontrak, AR, dan jurnal; kelebihan tanah tidak bisa "lunas" tanpa SPKT.
3. Sub-alur KPR hanya ada pada kontrak KPR; SP3K & akad tidak bisa lanjut tanpa file bukti.
4. Tunggakan 2 bulan (cash bertahap) otomatis memunculkan usulan pembatalan + hitungan potongan 35%/50% yang benar.
5. BAST tidak bisa ditandatangani sebelum Finance mengonfirmasi pelunasan (uji negatif).
6. Invarian INV-03, INV-04, INV-05, INV-08 lulus + `run_all_gates.sh` PASS + gate baru `verify_contract_v2.py`.
