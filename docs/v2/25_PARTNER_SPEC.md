# 25 — SPEC MITRA / PIHAK KETIGA (Partner Management)

> Keputusan owner **D5: semua bisa dikonfigurasi (toggle), lengkap.** Menutup CR-09.
> Basis kode yang sudah ada & harus dipertahankan: `backend/marketing_fee.py` (master `agents`, alur `submitted → approved → paid`, jurnal idempoten `6-1200 / 2-1500 / 2-1300`, invarian saldo).

## 1. Istilah (bahasa Indonesia yang dipakai di UI)
- **Mitra** = pihak ketiga penyumbang lead/penjualan di luar tim inhouse.
- Jenis mitra (`partner_kind`, SSOT baru): `agen_perorangan`, `kantor_broker`, `aggregator`, `referral_pembeli`, `influencer`, `korporat`.
- **Fee Mitra** = imbalan atas lead/penjualan (berbeda dari **Komisi** untuk sales internal — `commissions` tetap terpisah).

## 2. Master Mitra (`partners`)
Strategi aman: **tetap gunakan koleksi `agents`** (data & invarian GL sudah menempel padanya) dan tambahkan field baru; sediakan alias endpoint `/api/partners` yang membaca/menulis `agents`. Rename koleksi TIDAK dilakukan (menghindari kerusakan invarian yang sudah lulus gate).

| Field | Tipe | Catatan |
|---|---|---|
| `code` | string | `AGN-0001` (sudah ada, `sequences.py`) |
| `name`, `partner_kind`, `company`, `phone`, `email` | | `partner_kind` baru |
| `entity_type` | enum `individual|company` | menentukan jenis PPh (⚠️ OQ-4) |
| `nik`, `npwp`, `address`, `pic_name`, `pic_phone` | | `nik` baru (perorangan) |
| `bank_name`, `bank_account`, `bank_account_name` | | untuk pembayaran |
| `contract` | obj | `{number, start_date, end_date, file_ids[], signed_by, status}` |
| `onboarding_docs` | via `doc_submissions` | `applies_to: partner:onboarding` |
| `status` | enum `active|suspended|blacklist|expired` | suspend memblokir lead & fee baru |
| `settings` | obj | toggle per mitra (§4) |
| `stats` | obj denormalisasi | `{leads, qualified, booked, won, fee_total, fee_paid, last_lead_at}` |
| `portal` | obj | `{enabled, user_id, last_login_at}` |

**Endpoint**: `GET/POST /api/partners`, `PUT /api/partners/{id}`, `POST /api/partners/{id}/status`, `GET /api/partners/{id}/overview` (stats + fee + lead terkini), `GET /api/partners/{id}/leads`, `GET /api/partners/{id}/fees`.

## 3. Skema fee (`partner_fee_rules`) — semua opsi disediakan (D5)

| `basis` | Arti | Field | Contoh |
|---|---|---|---|
| `percent_price` | % dari harga jual unit | `value` (%) , `price_base` (`gross|nett|after_discount`) | 2% × Rp166.000.000 |
| `fixed_per_deal` | nominal tetap per transaksi | `value` (Rp) | Rp3.000.000 |
| `fixed_per_unit_type` | nominal per tipe unit | `by_unit_type{code: Rp}` | 30/60 = Rp2.500.000 |
| `tier_volume` | berjenjang per jumlah closing dalam periode | `tiers[{min,max,value,mode(percent|fixed)}]`, `period(monthly|quarterly|project)` | 1–2 unit 1.5%, 3+ 2.5% |
| `tier_value` | berjenjang per nilai penjualan | idem dengan `value_range` | |
| `per_lead_qualified` | bayar per lead lolos kualifikasi | `value`, `qualify_rule` | Rp150.000/lead survey hadir |
| `hybrid` | gabungan (mis. per lead + % closing) | `components[]` | |

**Pemicu hak fee** `trigger` (bisa bertahap): `booking_fee_verified`, `spr_signed`, `ppjb_signed`, `akad_kredit`, `ajb_signed`, `full_payment`.
**Pembayaran bertahap** `split[]`: mis. `[{trigger:'ppjb_signed', pct:50},{trigger:'ajb_signed', pct:50}]` (total wajib 100%, divalidasi).
**Pajak** `tax`: `{pph_type: pph21|pph23|none, rate, gross_up: bool}` — tarif diisi admin (⚠️ OQ-4). Jurnal mengikuti pola yang sudah ada (`marketing_fee.py`: bruto ke `6-1200`, netto ke `2-1500`, potongan ke `2-1300`).
**Cakupan & prioritas**: aturan bisa dibatasi `project_id`, `cluster_id`, `unit_type`, `valid_from/valid_to`. Pemilihan aturan = **paling spesifik & masih berlaku**; bila bentrok ⇒ tolak dengan pesan jelas (jangan diam-diam pilih satu).

## 4. Toggle konfigurasi (masuk [33](33_CONFIG_CENTER_SPEC.md))

| Key | Default | Arti |
|---|---|---|
| `partner.enabled` | true | aktifkan modul mitra |
| `partner.require_contract_active` | true | lead/fee ditolak bila kontrak mitra kedaluwarsa |
| `partner.lead_dedup_window_days` | 30 | lead sama dari 2 mitra dalam N hari → milik mitra pertama (first-touch) |
| `partner.attribution_model` | `first_touch` | `first_touch|last_touch|manual_review` |
| `partner.auto_create_fee` | true | fee otomatis dibuat saat trigger tercapai (status `submitted`) |
| `partner.fee_needs_approval` | true | wajib approve finance sebelum jadi utang |
| `partner.max_fee_pct_of_price` | 5 | pagar wajar; lebih dari ini butuh persetujuan owner |
| `partner.portal_enabled` | false | portal mitra (lihat §6) |
| `partner.tax_default_pph21_rate` | ⚠️ OQ-4 | |
| `partner.tax_default_pph23_rate` | ⚠️ OQ-4 | |

## 5. Alur lengkap (end-to-end)
```
1. Onboarding mitra: master + kontrak + dokumen (doc_requirements partner:onboarding) → status active
2. Aturan fee dibuat (partner_fee_rules) dan diberlakukan pada proyek/cluster/tipe tertentu
3. Lead masuk: source='partner' + partner_id  (manual, form khusus, atau webhook mitra ber-token)
   └─ dedup & attribution (first_touch default) → bila duplikat, catat 'attribution_conflict' untuk ditinjau
4. Lead jalan seperti biasa (Dok 24). Setiap tahap tercatat aktornya
5. Trigger tercapai (mis. spr_signed) → sistem menghitung fee dari aturan yang berlaku → marketing_fees(status=submitted)
6. Finance approve → jurnal (bruto/netto/PPh) → utang 2-1500 muncul di AP/laporan
7. Bayar → jurnal pelunasan + bukti transfer → stats mitra diperbarui
8. Analitik mitra (§7) + laporan pajak (tax_records) mengikuti
```
Semua langkah menulis riwayat (W6) sehingga **history mitra** bisa ditampilkan (permintaan owner).

## 6. Portal mitra (opsional, `partner.portal_enabled`)
Memakai pola portal pelanggan yang sudah ada (`portal_security.py`, OTP): mitra login lewat OTP nomor terdaftar, melihat **hanya**: lead yang ia kirim + status tahapnya (tanpa data pribadi pembeli yang tidak perlu), estimasi & realisasi fee, dokumen kontraknya, dan form kirim lead. Endpoint diprefiks `/api/partner-portal/*` dan dijaga token `type='partner'`.

## 7. Analitik mitra (dipakai [31](31_ANALYTICS_BI_SPEC.md))

| Metrik | Rumus |
|---|---|
| Lead per mitra | `count(leads where partner_id=X, periode)` |
| Kualitas lead mitra | `qualified/leads`, `survey_attended/leads`, `spr/leads`, `won/leads` |
| Waktu ke closing | median(`won_at - created_at`) per mitra |
| Biaya per akuisisi mitra | `Σ fee approved / count(won)` |
| Kontribusi pendapatan | `Σ contract.total dari lead mitra` |
| ROI mitra | `(pendapatan − fee) / fee` |
| Fee outstanding | `Σ (netto − terbayar)` = saldo `2-1500` (invarian yang sudah ada) |
| Ranking mitra | tabel dengan sort semua kolom di atas |

## 8. Definition of Done — ✅ SELESAI (Fase 42, 17 Agu 2026)
1. ✅ Lead mitra tidak bisa dibuat tanpa `partner_id` aktif & kontrak berlaku (bila toggle nyala).
   → `POST /api/leads` dengan `source=partner` tanpa mitra dijawab **400** dengan pesan
   "Lead bersumber mitra wajib memilih mitranya".
2. ✅ Fee otomatis muncul pada trigger, nominal **sama** dengan hitungan aturan.
   → terbukti pada data nyata: reservasi → booking → PPJB menerbitkan `MF/2026/0003`
   = 2% × Rp 850.000.000 → bruto **Rp 17.000.000**, PPh Rp 425.000, netto Rp 16.575.000
   (beban = netto + PPh, jurnal seimbang). Idempoten: pemicu sama ditolak **400**.
3. ✅ Tidak ada fee tanpa aturan yang berlaku (INV-09) — penolakan **menyebut alasannya**,
   dan aturan yang sama-sama spesifik **DITOLAK** (tidak dipilih diam-diam).
4. ✅ Saldo `2-1500` tetap = Σ (netto − terbayar) — `verify_business_invariants.py` PASS.
5. ✅ Hub `/partners` (5 tab: Master Mitra, Aturan Fee, Tagihan Fee, Sengketa Atribusi,
   Analitik Mitra) + halaman kanonik `/partners/:id`; rute lama `/marketing-fee` tetap hidup.
6. ✅ Gate `verify_partner.py` + uji-mutasi `mutasi_41_42.py` (32/32) dan
   `run_all_gates.sh` **OVERALL PASS (25 gates)**.

**Catatan implementasi yang menyimpang dari spec (disengaja):**
- Koleksi tetap **`agents`** (bukan `partners`) sesuai §2 — alias endpoint `/api/partners`.
- Tab **Analitik** dijadikan tab tersendiri di hub (`?hub=analitik`), bukan tab di dalam profil
  mitra; profil mitra memuat Profil, Kontrak & Dokumen, Aturan Fee, Lead, Tagihan Fee.
- **Portal mitra (§6) BELUM dibuat** — masih menunggu keputusan; `partner.portal_enabled`
  sudah ada sebagai toggle tetapi belum ada halaman portalnya.
