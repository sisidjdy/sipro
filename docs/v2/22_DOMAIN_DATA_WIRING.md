# 22 — DOMAIN, DATA & WIRING (kontrak data V2)

> Menggantikan bagian yang berubah dari `docs/analysis/11_ENTITY_REGISTRY.md` & `12_STATE_MACHINES_AND_INVARIANTS.md`.
> Semua koleksi memakai `id` (uuid string), `org_id`, `created_at`, `updated_at` (ISO string) — konsisten dengan kode yang ada (`core_utils.py`).

## 1. Rantai wiring yang WAJIB tidak terputus

```
AD/PARTNER/ORGANIK ──► lead ──► appointment/survey ──► reservation(deal) ──► SPR(document)
                                                             │                    │
                                                             ▼                    ▼
                                                        unit (hold)        customer (konversi)
                                                             │                    │
                                        ┌────────────────────┼────────────────────┤
                                        ▼                    ▼                    ▼
                                 build_schedule        payment_plan          kpr_application
                                 (konstruksi)          (AR + termin)         (hanya skema KPR)
                                        │                    │                    │
                                        └──────────► journal_entries (GL) ◄────────┘
                                                             │
                                                             ▼
                                              budget_items / boq_items (realisasi vs rencana)
                                                             │
                                                             ▼
                                                   metrics layer (BI, Dok 31)
```

**Aturan wiring (invarian lintas modul):**
- **W1** `deal.lead_id` wajib ada; `deal.unit_id` wajib ada; unit hanya boleh dipegang **satu** deal aktif (sudah dijaga `deals_router.py:94`).
- **W2** Konversi lead→customer **membuat/menautkan** `customers` + `contracts` (baru) dan mengisi `unit.customer_id`, `unit.contract_id`, `unit.sales_status`.
- **W3** `unit` punya **dua status paralel**: `sales_status` (available/held/booked/sold/handed_over/cancelled) dan `build_status` (not_started/in_progress/completed/handed_over) — tidak boleh saling menimpa. (Permintaan owner.)
- **W4** Setiap rupiah yang berpindah wajib melahirkan `journal_entries` dengan `source_event` unik (idempoten) — pola `gl_engine.py`.
- **W5** Setiap realisasi biaya proyek wajib punya `cost_ref` = `{budget_item_id?, boq_item_id?, unit_id?, cluster_id?, project_id}` supaya realisasi RAB & overbudget bisa dihitung tanpa menebak.
- **W6** Setiap perubahan status entitas inti (lead, deal, contract, unit, kpr, payment) wajib menulis baris riwayat `{from,to,at,actor,reason,evidence}` — pola `lead_lifecycle.record()`.
- **W7** Semua dokumen (upload maupun generate) tersimpan di `files` + baris `documents`/`doc_submissions` yang menempel ke entitas (`lead|customer|unit|contract|kpr|partner`).

## 2. Koleksi BARU (V2)

| Koleksi | Tujuan | Field inti | Spec |
|---|---|---|---|
| `clusters` | tingkat antara proyek & blok | `project_id, code, name, order, land_area, unit_count, price_policy{}, status` | [28](28_PROJECT_UNIT_SPEC.md) |
| `blocks` | blok di dalam cluster | `project_id, cluster_id, code, name, order, unit_count` | [28](28_PROJECT_UNIT_SPEC.md) |
| `unit_types` | master tipe (30/60 dst) | `code, name, building_area, land_area_std, base_price, spec{}, image_file_id` | [28](28_PROJECT_UNIT_SPEC.md) |
| `settings` | registry konfigurasi bisnis | `key, value, type, scope(org|project|cluster), scope_id, updated_by` | [33](33_CONFIG_CENTER_SPEC.md) |
| `doc_requirements` | master syarat dokumen | `code, label, group, applies_to[], mandatory, allowed_mime[], max_mb, expiry_days, order, active` | [24](24_CRM_LEAD_SPEC.md) §6 |
| `doc_submissions` | dokumen yang diserahkan | `requirement_code, entity_type, entity_id, file_id, status(pending/verified/rejected/expired), verified_by, verified_at, reject_reason, expires_at` | [24](24_CRM_LEAD_SPEC.md) §6 |
| `contracts` | kontrak jual-beli (pengganti "deal legal") | `deal_id, customer_id, unit_id, scheme(cash|cash_staged|kpr), price_breakdown{}, total, status, legal_stage, doc_ids[]` | [26](26_CUSTOMER_LEGAL_SPEC.md) |
| `payment_plans` | rencana bayar per kontrak | `contract_id, scheme, terms[{no,label,amount,due_date,due_rule,status,paid_at,ar_invoice_id}], grace_rule{}, arrears_rule{}` | [26](26_CUSTOMER_LEGAL_SPEC.md) §3 |
| `kpr_applications` | sub-alur KPR (ganti/extend `financing_apps`) | `contract_id, bank, plafon, tenor, stage, stage_history[], slik_bank{}, appraisal{}, sp3k{}, akad{}` | [26](26_CUSTOMER_LEGAL_SPEC.md) §4 |
| `partners` | mitra/pihak ketiga (extend `agents`) | lihat [25](25_PARTNER_SPEC.md) §2 | [25](25_PARTNER_SPEC.md) |
| `partner_fee_rules` | skema fee per mitra/proyek | `partner_id, project_id?, basis, value, tiers[], trigger, split[], tax{}, valid_from, valid_to` | [25](25_PARTNER_SPEC.md) §3 |
| `campaigns` | master kampanye iklan | `platform, external_id, name, project_id, objective, budget, start, end, status` | [30](30_MARKETING_INTEGRATION_SPEC.md) §4 |
| `ad_spend` | biaya iklan harian (manual/CSV/API) | `platform, campaign_id, adset_id, ad_id, date, spend, impressions, clicks, leads, source(manual|csv|api), imported_by` | [30](30_MARKETING_INTEGRATION_SPEC.md) §5 |
| `project_targets` | target proyek & bulanan | `project_id, method, horizon{start,end}, unit_target, revenue_target, periods[], recalc_policy` | [32](32_TARGET_BUDGET_SPEC.md) §2 |
| `budget_items` | master budget (RAB + operasional) | `project_id, cluster_id?, category, code, name, planned_amount, gl_account, owner_role, notes, active` | [32](32_TARGET_BUDGET_SPEC.md) §3 |
| `survey_forms` | konfigurasi form survei | `code, name, sections[{title,fields[{key,label,type,options,required}]}], active, version` | [24](24_CRM_LEAD_SPEC.md) §10 |
| `appointment_events` | riwayat reschedule/batal survei | `appointment_id, action(reschedule|cancel|no_show), reason_code, note, actor, old_at, new_at, followup_task_id` | [24](24_CRM_LEAD_SPEC.md) §10 |
| `metric_snapshots` | cache metrik BI harian | `metric_key, scope, scope_id, period, value, computed_at, inputs{}` | [31](31_ANALYTICS_BI_SPEC.md) §8 |
| `user_daily_activity` | rekap harian per user | `user_email, date, counters{}, first_action_at, last_action_at` | [31](31_ANALYTICS_BI_SPEC.md) §6 |

## 3. Koleksi yang DIUBAH (tambah field — semua backward compatible)

### `leads`
| Field baru | Tipe | Alasan | Sumber |
|---|---|---|---|
| `partner_id` | string? | lead dari mitra (CR-09) | [25](25_PARTNER_SPEC.md) |
| `source_detail` | string? | nama event/agen/inhouse | [24](24_CRM_LEAD_SPEC.md) |
| `stage_entered_at` | iso | jam masuk tahap **saat ini** (aging tahap) | CR-31 |
| `stage_durations` | obj | `{stage: total_minutes}` akumulasi | [31](31_ANALYTICS_BI_SPEC.md) |
| `sla_due_at` | iso? | batas tindak lanjut tahap ini | [24](24_CRM_LEAD_SPEC.md) §4 |
| `demography` | obj | usia/pekerjaan/penghasilan/domisili/tanggungan (⚠️ OQ-6) | [24](24_CRM_LEAD_SPEC.md) §9 |
| `budget_band` | enum | kemampuan bayar (SSOT baru) | [31](31_ANALYTICS_BI_SPEC.md) |
| `interest` | obj | `{project_id, cluster_id, unit_type, unit_id?}` | [28](28_PROJECT_UNIT_SPEC.md) |
| `doc_progress` | obj | `{required, verified, pending, rejected}` (denormalisasi) | [24](24_CRM_LEAD_SPEC.md) §6 |
| `merged_into` / `duplicate_of` | string? | dedup & eliminasi lead | [24](24_CRM_LEAD_SPEC.md) §11 |

### `units`
`cluster_id`, `block_id`, `unit_type_id`, `no` (nomor dalam blok), `land_area`, `building_area`, `is_hook`, `hook_fee`, `excess_land_m2`, `excess_land_price_per_m2`, `price_components{}`, `sales_status`, `build_status`, `customer_id`, `contract_id`, `held_until`, `status_history[]`.

### `deals` (jadi "reservasi/SPR", bukan pemegang legal)
`spr_number`, `spr_document_id`, `spr_scheme`, `booking_fee_status`, `booking_fee_paid_at`, `booking_fee_receipt_id`, `booking_fee_refund{}`, `doc_progress{}`, `expires_at`, `override{by,reason,at}`, `contract_id`.

### `customers`
`lead_id`, `converted_at`, `spouse{}`, `id_documents[]`, `contracts[]`, `payment_status`, `kpr_status`, `handover{}`, `retention_until`.

### `agents` → dibaca sebagai `partners` (lihat [25](25_PARTNER_SPEC.md) §2 untuk strategi rename aman).

### `projects`
`address`, `developer_name`, `notary_default{}`, `cost_defaults{bphtb,notaris,bank,promo}`, `booking_fee_default`, `target_id`, `start_date`, `target_finish_date`, `cluster_count`.

## 4. Index unik & wajib (tambahkan di `backend/indexes.py`)

| Koleksi | Index | Alasan |
|---|---|---|
| `clusters` | `(org_id, project_id, code)` unik | kode cluster tidak boleh dobel |
| `blocks` | `(org_id, cluster_id, code)` unik | idem |
| `units` | `(org_id, project_id, code)` unik (sudah) + `(org_id, block_id, no)` unik | penomoran unit resmi |
| `unit_types` | `(org_id, code)` unik | |
| `settings` | `(org_id, scope, scope_id, key)` unik | satu nilai per scope |
| `doc_requirements` | `(org_id, code)` unik | |
| `doc_submissions` | `(org_id, entity_type, entity_id, requirement_code, file_id)` unik | cegah dobel unggah |
| `contracts` | `(org_id, number)` unik; `(org_id, unit_id, status)` partial unik untuk status aktif | 1 kontrak aktif/unit |
| `payment_plans` | `(org_id, contract_id)` unik | |
| `deals` | partial unik `(org_id, lead_id)` untuk `status in (reserved, spr_issued)` | **menutup CR-01 di level DB** |
| `ad_spend` | `(org_id, platform, campaign_id, adset_id, ad_id, date)` unik | impor CSV idempoten |
| `project_targets` | `(org_id, project_id, horizon.start)` unik | |
| `budget_items` | `(org_id, project_id, code)` unik | |
| `user_daily_activity` | `(org_id, user_email, date)` unik | |
| `metric_snapshots` | `(org_id, metric_key, scope, scope_id, period)` unik | |

## 5. Invarian yang bisa diuji (dipakai `scripts/verify_*.py`)

| ID | Invarian | Cara uji |
|---|---|---|
| INV-01 | Tidak ada lead dengan >1 deal aktif (kecuali ada `override.reason`) | agregasi `deals` group by `lead_id` status aktif |
| INV-02 | `units.sales_status='held'` ⇒ ada deal aktif yang merujuk unit itu, dan sebaliknya | join dua arah |
| INV-03 | `contracts.status='active'` ⇒ `units.contract_id` = kontrak itu & `units.sales_status in (booked, sold)` | join |
| INV-04 | Σ `payment_plans.terms.amount` = `contracts.total` (toleransi 0) | agregasi |
| INV-05 | Setiap `receipts`/`payments_out` punya `journal_entries` dengan `source_event` sama, tidak dobel | count group by source_event = 1 |
| INV-06 | `doc_submissions.status='verified'` ⇒ `files` ada & tidak `is_deleted` | join (pola `slik.evidence_refs`) |
| INV-07 | Lead tahap ≥ `spr` ⇒ semua `doc_requirements` mandatory untuk tahap itu berstatus verified | evaluasi gerbang |
| INV-08 | `kpr_applications.stage='akad'` ⇒ ada `sp3k.file_id` & `appraisal.value` | join |
| INV-09 | `marketing_fees` yang approved ⇒ ada `partner_fee_rules` yang berlaku pada tanggal deal | join periode |
| INV-10 | Σ realisasi `budget_items` = Σ jurnal akun terkait pada periode | agregasi GL |
| INV-11 | `ad_spend` tidak punya baris ganda pada kunci natural | index + count |
| INV-12 | `project_targets.periods` menutup seluruh horizon tanpa bolong/tumpang tindih | scan periode |
| INV-13 | `unit.build_status='in_progress'` ⇒ ada `build_schedules` aktif untuk unit itu | join (sudah ada Fase 31) |
| INV-14 | Semua metrik BI dapat direkonstruksi dari data mentah (snapshot tidak boleh jadi satu-satunya sumber) | hitung ulang & bandingkan |

## 6. Peta modul backend (file yang akan disentuh V2)

| Domain V2 | File baru | File diubah |
|---|---|---|
| Proyek/unit master | `masterplan.py`, `routers/masterplan_router.py` | `models.py`, `seed.py`, `indexes.py`, `routers/projects_router.py`, `site_plan_svg.py` |
| Config center | `settings_store.py`, `routers/settings_router.py` | `reference.py`, `routers/master_router.py` |
| Dokumen syarat | `doc_registry.py`, `routers/docreq_router.py` | `routers/files_router.py` |
| Lead v2 | `lead_profile.py` | `lead_lifecycle.py`, `routers/leads_router.py`, `models.py` |
| Reservasi/SPR | `reservation.py` | `routers/deals_router.py` |
| Generator dokumen | `docgen.py`, `templates/*.py` | `pdf_utils.py`, `routers/documents_router.py`, `sequences.py` |
| Customer/legal | `contracts.py`, `payment_plan.py`, `kpr_flow.py`, `cancellation.py` | `routers/customers_router.py`, `routers/financing_router.py`, `finance_engine.py` |
| Mitra | `partners.py` | `marketing_fee.py`, `routers/marketing_fee_router.py` |
| Marketing/ads | `ads_ingest.py`, `ads_adapters/{meta,google}.py` | `capi.py`, `routers/omnichannel_router.py`, `routers/webhooks_router.py` |
| Target & budget | `targets.py`, `budget.py` | `boq_router.py`, `gl_reports.py` |
| BI | `metrics/*.py`, `routers/analytics_router.py` | `routers/reports_router.py` |
| Konstruksi konsolidasi | — | `routers/build_router.py`, `routers/construction_router.py`, `routers/field_router.py`, `routers/permits_router.py` |

> **Batas ukuran file wajib** (`scripts/validate_compliance.py`): `.py` router ≤800 baris, page/komponen `.js` ≤500, util/service `.js` ≤300, `.css` ≤400. Pecah modul lebih awal, jangan menunggu gate merah.
