# 33 — SPEC PUSAT KONFIGURASI (satu menu untuk semua toggle & master)

> Permintaan owner: *"buatkan satu menu khusus konfigurasi, semua fitur konfigurasi kontrolnya di menu dedicated ini"* + **D2/D3/D5/D6** (semua bisa dikonfigurasi). Menutup CR-34, CR-21.

## 1. Struktur menu **Konfigurasi** (seksi sendiri, akses `super_admin` + peran yang diizinkan)

| Tab | Isi | Dokumen sumber |
|---|---|---|
| **Aturan Bisnis** | semua setting `[CFG]` dengan penjelasan & dampak | §3 |
| **Dokumen Syarat** | master `doc_requirements` (per tahap/skema/mitra) | [24](24_CRM_LEAD_SPEC.md) §6 |
| **Template Dokumen** | `document_templates` + klausa + pratinjau | [27](27_DOCGEN_SPEC.md) |
| **Harga & Biaya** | master `price_components`, `addon_items`, default biaya per proyek | [26](26_CUSTOMER_LEGAL_SPEC.md) §3–§4 |
| **Skema Bayar** | template termin per skema (cash/bertahap/KPR) | [26](26_CUSTOMER_LEGAL_SPEC.md) §5 |
| **Mitra & Fee** | `partner_fee_rules`, pajak, pagar wajar | [25](25_PARTNER_SPEC.md) |
| **Form Survei** | builder `survey_forms` (berversi) | [24](24_CRM_LEAD_SPEC.md) §10 |
| **Target & Anggaran** | metode target default, `budget_category`, ambang peringatan | [32](32_TARGET_BUDGET_SPEC.md) |
| **Jadwal & Kalender** | template langkah, hari kerja, hari libur (sudah ada Fase 36) | Fase 36 |
| **SLA & Otomasi** | SLA per tahap, aturan otomasi, playbook WA | [24](24_CRM_LEAD_SPEC.md) §4 |
| **Integrasi** | status kredensial (terisi/tidak) + mode live/simulasi | [30](30_MARKETING_INTEGRATION_SPEC.md) §2 |
| **SSOT / Referensi** | 85 grup enum yang sudah ada + tambah nilai (yang `strict=false`) | `reference.py` |
| **Integritas Data** | alat perbaikan & migrasi (sudah ada di `/admin/master-data`) | `migrations.py` |

## 2. Registry setting (`settings`)

```json
{"key":"reservation.max_active_per_lead","value":1,"type":"int",
 "scope":"org","scope_id":"org-sipro","group":"reservasi",
 "label":"Maksimum unit aktif per lead",
 "help":"Berapa unit yang boleh dipegang satu lead pada waktu yang sama.",
 "impact":"Menambah nilai ini memungkinkan satu calon pembeli mengunci beberapa unit.",
 "min":1,"max":5,"requires_role":"super_admin",
 "updated_by":"","updated_at":"","history":[{"at":"","by":"","from":1,"to":2,"reason":""}]}
```

**Aturan wajib:**
1. **Scope berlapis**: `org` → `project` → `cluster`. Pembacaan memakai nilai paling spesifik (`settings_store.get(key, project_id=..., cluster_id=...)`).
2. **Default ada di kode** (`settings_store.DEFAULTS`) sehingga sistem tetap jalan bila DB kosong; DB hanya menyimpan **yang diubah**.
3. **Setiap perubahan wajib `reason`** bila setting bertanda `sensitive: true` (uang, legal, RBAC) → masuk `history` + jejak audit.
4. **Tidak ada angka bisnis hard-code di kode.** Gate baru `verify_no_hardcoded_rules.py` memindai pola angka terlarang (mis. `35`, `50`, `0.02`, `7 hari`) di modul bisnis dan menuntut pemakaian `settings_store`.
5. **Endpoint**: `GET /api/settings?group=&scope=&scope_id=`, `PUT /api/settings/{key}`, `POST /api/settings/bulk`, `GET /api/settings/{key}/history`, `POST /api/settings/reset/{key}`.

## 3. Daftar setting awal (dikumpulkan dari seluruh dokumen V2)

| Key | Tipe | Default | Sumber |
|---|---|---|---|
| `reservation.max_active_per_lead` | int | **1** | D2 |
| `reservation.hold_days` | int | 7 | `BOOKING_HOLD_DAYS` |
| `reservation.override_roles` | list | `[sales_manager, super_admin]` | ⚠️ OQ-8 |
| `reservation.require_booking_fee_before_spr` | bool | true | [24](24_CRM_LEAD_SPEC.md) |
| `reservation.release_reasons_required` | bool | true | [24](24_CRM_LEAD_SPEC.md) |
| `lead.won_trigger` | enum | `spr_signed` | D4 |
| `lead.sla_hours` | obj | `{acquisition:0.25, nurturing:48, appointment:72, booking:168, spr:168}` | [24](24_CRM_LEAD_SPEC.md) |
| `lead.required_demography` | list | `[]` (wajib lengkap sebelum `spr`) | ⚠️ OQ-6 |
| `slik.gate` | enum | `before_spr` | D7 |
| `booking_fee.default_amount` | money | 1.000.000 | `[DOC]` ⚠️ OQ-3 |
| `booking_fee.refund_bi_fail_pct` | pct | 100 | `[DOC]` |
| `booking_fee.refund_kpr_rejected_pct` | pct | 50 | `[DOC]` |
| `booking_fee.forfeit_no_clarity_days` | int | 7 | `[DOC]` |
| `payment.cash.dp_pct` | pct | 80 | `[DOC]` ⚠️ OQ-2 |
| `payment.cash.payoff_days_after_completion` | int | 30 | `[DOC]` |
| `payment.cash.payoff_grace_days` | int | 7 | `[DOC]` |
| `payment.staged.installment_count` | int | 6 | `[DOC]` |
| `payment.staged.due_day` | int | 7 | `[DOC]` |
| `payment.staged.grace_day` | int | 20 | `[DOC]` |
| `payment.staged.arrears_months_to_cancel` | int | 2 | `[DOC]` |
| `cancellation.cut_before_build_pct` | pct | 35 | `[DOC]` |
| `cancellation.cut_during_build_pct` | pct | 50 | `[DOC]` |
| `cancellation.refund_requires_resale` | bool | true | `[DOC]` |
| `legal.shgb_months_after_ajb` | int | 6 | `[DOC]` |
| `retention.months` | int | ⚠️ OQ-7 | `[DOC]` |
| `kpr.use_appraisal_step` | bool | true | koreksi owner |
| `kpr.sla_days` | obj | `{berkas:7, bank:14, appraisal:7, sp3k:14, akad:7}` | [26](26_CUSTOMER_LEGAL_SPEC.md) |
| `addon.require_spkt_for_excess_land` | bool | true | `[DOC]` |
| `addon.excess_land_must_be_paid_before_akad` | bool | true | `[DOC]` |
| `partner.*` | — | lihat [25](25_PARTNER_SPEC.md) §4 | D5 |
| `budget.enforce_cost_ref` | bool | true | [32](32_TARGET_BUDGET_SPEC.md) |
| `budget.alert_pct` | pct | 90 | [32](32_TARGET_BUDGET_SPEC.md) |
| `target.default_method` | enum | `linear_remaining` | D6 |
| `docnum.scope` / `docnum.reset_policy` | enum | `per_project` / `yearly` | ⚠️ OQ-5 |
| `permit.block_build_without` | list | `[]` (peringatan saja) | [29](29_CONSTRUCTION_SPEC.md) |
| `ui.table_page_size` | int | 25 | [23](23_IA_UX_BLUEPRINT.md) |

## 4. UI Pusat Konfigurasi
- Daftar setting **berkelompok** dengan pencarian; setiap baris: label, nilai, kontrol tipe-aware (switch/number/select/multiselect/money/json), **penjelasan dampak**, siapa terakhir mengubah, tombol riwayat & reset.
- Perubahan sensitif memunculkan dialog konfirmasi + kolom alasan wajib.
- Tab **Pratinjau Dampak** untuk setting berumus (mis. ubah `payment.staged.installment_count` → tampilkan contoh termin baru sebelum simpan).
- Semua master (dokumen syarat, add-on, komponen biaya, form survei) memakai pola tabel + dialog yang sama (konsisten).

## 5. Definition of Done
1. Semua angka bisnis di Dokumen 24–32 dapat diubah dari UI tanpa deploy (uji: ubah 10 setting kunci → perilaku & dokumen ikut berubah).
2. `verify_no_hardcoded_rules.py` PASS (tidak ada aturan bisnis hard-code di modul baru).
3. Riwayat perubahan setting tersimpan lengkap dengan aktor & alasan.
4. Setting salah tidak bisa merusak sistem: validasi min/max/enum + fallback default (uji dengan nilai ekstrem).
5. `run_all_gates.sh` PASS.
