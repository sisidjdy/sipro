# 35 — MIGRASI DATA V2 (idempoten, beralasan, bisa diulang)

> Prinsip: **tidak ada data yang hilang, tidak ada riwayat yang dipalsukan.** Semua migrasi menulis `source='migration'` + alasan, dan aman dijalankan berulang (pola `backend/migrations.py` yang sudah ada).
> Dijalankan lewat `run_migrations()` pada startup + perintah manual `POST /api/admin/migrations/run?name=`.

## 1. Daftar migrasi

| ID | Nama | Aksi | Idempoten karena |
|---|---|---|---|
| M39-1 | `seed_default_cluster_block` | Untuk setiap proyek tanpa cluster: buat cluster `UTAMA`; untuk setiap prefiks kode unit yang ada (`A`, `B`, `C` dari `code.split("-")`) buat `blocks` lalu isi `units.cluster_id`/`block_id`/`no` | cek `existing by (project_id, code)` |
| M39-2 | `map_unit_type_enum` | Petakan `units.type` (enum teks lama, mis. "Tipe 45/90") → `unit_types` (buat bila belum ada, ambil `building_area`/`land_area_std` dari angka pada nama; bila tidak bisa diparse → tandai `needs_review=true`, **jangan mengarang**) | cek `unit_types.code` |
| M39-3 | `backfill_unit_dual_status` | `units.status` lama → `sales_status`; `build_status` diturunkan dari `build_schedules`/progres (tanpa jadwal ⇒ `not_started`) | idempoten by field kosong |
| M39-4 | `link_siteplan_shapes` | Isi `site_plans.shapes[].unit_id` & `units.siteplan.shape_id` dari pencocokan kode; laporkan shape/unit yang tidak berpasangan | pencocokan ulang aman |
| M39-5 | `seed_price_components` | Buat master komponen biaya default (§3.2 Dok 26) bila kosong | cek `code` |
| M39-6 | `seed_addon_items` | Buat add-on default: `posisi_unit(hook)`, `kelebihan_tanah`, contoh spek bangunan | cek `code` |
| M39-7 | `seed_doc_requirements` | Buat master dokumen syarat default (§6 Dok 24) | cek `code` |
| M39-8 | `seed_settings_defaults` | Tulis **hanya** setting yang perlu terlihat di UI; sisanya tetap default kode | cek `(scope, scope_id, key)` |
| M41-1 | `backfill_lead_stage_timestamps` | `stage_entered_at` = entri `stage_history` terakhir (atau `updated_at`); `stage_durations` dihitung dari `stage_history`; lead tanpa riwayat → pakai `created_at` + tandai `estimated=true` | tulis bila kosong |
| M41-2 | `backfill_lead_source_partner` | Lead dengan sumber `referral` yang punya catatan agen → **tidak** diubah otomatis; buat laporan untuk ditinjau manual (hindari salah atribusi fee) | hanya laporan |
| M42-1 | `normalize_active_reservations` | Deteksi lead dengan >1 deal aktif: **jangan hapus**; tandai `needs_review=true` + buat tugas ke `sales_manager` untuk memilih mana yang dipertahankan; index partial unik dibuat **setelah** bersih | laporan + tugas idempoten |
| M43-1 | `promote_deals_to_contracts` | Deal dengan `legal_stage` ∈ (ppjb, ajb, bast) atau status `completed/sold` → buat `contracts` + `payment_plans` rekonstruksi dari `ar_invoices`/`receipts` yang ada; nilai yang tidak diketahui ditandai `unknown` (bukan 0) | cek `contracts.deal_id` |
| M43-2 | `lead_stage_semantics_v2` | Lead `booking` yang sudah punya SPR/kontrak → naikkan ke `spr`/`won` dengan `reason="migrasi semantik V2"`; lead `won` lama **tetap** `won` | cek stage tujuan |
| M44-1 | `financing_apps_to_kpr` | Salin `financing_apps` → `kpr_applications` (tahap dipetakan konservatif: status lama tidak jelas ⇒ `diajukan_ke_bank`, tandai `needs_review`) | cek `contract_id` |
| M45-1 | `agents_to_partners_fields` | Tambah field baru pada `agents` (`partner_kind`, `entity_type`, `contract`, `settings`, `stats`); nilai tidak diketahui = `null` | `$set` field kosong |
| M48-1 | `map_costs_to_budget_items` | Dokumen biaya lama tanpa `cost_ref` → tandai `unmapped=true` dan tampilkan di laporan "biaya belum terpetakan"; **tidak** menebak pemetaan | flag saja |
| M49-1 | `build_user_daily_activity_backfill` | Rekonstruksi 90 hari terakhir dari `activities`/`tasks`/`messages` | upsert by `(user, date)` |

## 2. Aturan wajib migrasi
1. **Dilarang menebak angka uang.** Nilai yang tidak diketahui → `null` + `needs_review`, bukan 0.
2. **Dilarang menghapus** dokumen lama. Perubahan = tambah field / tambah dokumen baru.
3. Setiap migrasi menulis ringkasan ke log & `migration_runs` (`{name, at, changed, skipped, warnings[]}`).
4. Migrasi yang menyentuh uang/legal (M43-1, M44-1) **wajib** menghasilkan laporan yang bisa diunduh untuk diperiksa manusia.
5. Index unik baru **hanya** dibuat setelah data bersih; bila konflik → log peringatan (pola `indexes.ensure_unique_indexes` yang sudah ada), **jangan** gagalkan startup.

## 3. Rencana rollback
- Tidak ada `DROP`. Rollback = matikan pemakaian field baru lewat `settings` (mis. `budget.enforce_cost_ref=false`, `lead.won_trigger=ajb_signed`) sehingga perilaku kembali seperti V1 tanpa migrasi balik.
- Snapshot sebelum fase besar: `mongodump` manual (dicatat di `plan.md`) sebelum M43-1 & M42-1.
- Bila migrasi salah: tulis migrasi koreksi baru (bukan mengedit yang lama) supaya jejaknya utuh.

## 4. Checklist verifikasi setelah migrasi
```
[] 0 unit tanpa cluster_id/block_id
[] 0 unit_types needs_review yang belum ditinjau
[] 0 shape siteplan tanpa unit_id (untuk proyek terpetakan)
[] daftar lead dengan >1 reservasi aktif = 0 (setelah tinjauan manual)
[] Σ payment_plans.terms = contracts.total untuk semua kontrak hasil M43-1 (atau ditandai unknown)
[] saldo GL tidak berubah sebelum vs sesudah migrasi (migrasi TIDAK boleh menyentuh jurnal)
[] bash scripts/run_all_gates.sh PASS
```
