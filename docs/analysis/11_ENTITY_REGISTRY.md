# SIPRO Rebuild — Dokumen 11
# ENTITY_REGISTRY (SKEMA FIELD-LEVEL) — Single Source of Truth Data

> Status: SPESIFIKASI DATA (blocker #1 ditutup). Bahasa: Indonesia.
> Konvensi global (berlaku SEMUA koleksi):
> - `id`: string UUID v4 (PK). Semua FK = string UUID.
> - `org_id`: string (multi-tenant scope) — **wajib di semua koleksi bisnis**; di-*enforce* `verify_tenant_scope.py`.
> - `created_at`/`updated_at`: string ISO-8601 UTC. Tampilan WIB di FE.
> - `created_by`/`updated_by`: email user.
> - Uang: integer **rupiah penuh** (hindari float; simpan sen bila perlu) — lihat NFR (Dok 16).
> - `_id` Mongo TIDAK pernah dikembalikan (`{"_id":0}`).
> - Enum ditulis eksplisit; nilai di luar enum = invalid (di-*gate*).
> - Legenda: 🔑=indexed, ⚑=invariant di-gate, ↗=FK.

---

## A. FONDASI & IDENTITAS

### `orgs`
| field | tipe | ket |
|---|---|---|
| id 🔑 | uuid | |
| name | str | nama developer/tenant |
| type | enum | `developer` (default) |
| npwp, address, phone, email | str? | profil |
| settings | obj | preferensi (timezone default `Asia/Jakarta`, currency `IDR`) |
| is_active | bool | |

### `users`
| field | tipe | ket |
|---|---|---|
| id 🔑, org_id 🔑↗ | uuid | |
| email 🔑 | str | unik per org |
| password_hash | str | bcrypt |
| name | str | |
| role ⚑ | enum | `super_admin`\|`owner`\|`sales_manager`\|`marketing_admin`\|`sales`\|`finance`\|`project_manager`\|`site_engineer` (lihat Dok 14) |
| phone | str? | E.164 |
| is_active | bool | |
| last_login_at | iso? | |

### `sessions` / `login_attempts`
- `sessions`: id, user_id↗, refresh_token_hash, expires_at, created_at.
- `login_attempts`: email, count, locked_until (brute-force lock — PORT dari SIPRO).

### `permission_settings` (RBAC config — Dok 14)
| field | tipe | ket |
|---|---|---|
| id, org_id | uuid | |
| role | enum | |
| resource | str | mis. `leads`,`deals`,`finance.ap` |
| actions | [str] | `view_all`\|`view_own`\|`create`\|`update`\|`delete`\|`approve` |

### `audit_logs`
| field | tipe | ket |
|---|---|---|
| id, org_id 🔑 | uuid | |
| actor | email | |
| action | str | `create`\|`update`\|`delete`\|`approve`\|`sign`… |
| entity_type, entity_id 🔑↗ | str | |
| before, after | obj? | diff ringkas |
| ip, at 🔑 | str | |

### `events` (Domain Event Bus — Dok 13)
| field | tipe | ket |
|---|---|---|
| id, org_id 🔑 | uuid | |
| type 🔑 | str | mis. `lead.created`,`deal.booked`,`payment.paid_off`,`unit.bast`,`message.received`,`lead.captured` |
| entity_type, entity_id 🔑↗ | str | |
| data | obj | payload |
| status | enum | `pending`\|`dispatched`\|`failed` (untuk konsumsi async) |
| dispatched_at, created_at 🔑 | iso | |
⚑ setiap event penting → dikonsumsi dispatcher (bukan hanya dicatat).

---

## B. WORK HUB (Task / Activity / Collaboration)

### `tasks` (Guided Work Engine — PORT shared._auto_create_task)
| field | tipe | ket |
|---|---|---|
| id, org_id 🔑 | uuid | |
| title, description | str | |
| type | enum | `contact`\|`follow_up`\|`appointment_prep`\|`ppjb`\|`kpr`\|`collection`\|`termin_verify`\|`qc`\|`custom`… |
| status ⚑ | enum | `open`\|`in_progress`\|`snoozed`\|`done`\|`canceled` |
| priority | enum | `low`\|`medium`\|`high`\|`urgent` |
| related_entity_type, related_entity_id 🔑↗ | str | lead/deal/unit/project/subcon/conversation |
| assigned_to 🔑 | email | |
| due_date 🔑 | iso? | |
| sla_due_at | iso? | untuk countdown & breach |
| source_event ⚑ | str | **idempotency key** (skip bila open+sama) |
| auto_generated | bool | |
| outcome | str? | |
| activity_history | [obj] | {action,by,at} |

### `activities` (feed + komentar + @mention + thread — F5)
| field | tipe | ket |
|---|---|---|
| id, org_id 🔑 | uuid | |
| entity_type, entity_id 🔑↗ | str | record yang ditempeli |
| kind | enum | `system_event`\|`comment`\|`stage_change`\|`note`\|`call`\|`whatsapp` |
| actor | email\|`system` | |
| body | str? | isi komentar |
| mentions | [email] | @mention |
| parent_id ↗ | uuid? | thread |
| meta | obj | data event |
| created_at 🔑 | iso | |

### `channels` / `channel_members` (kolaborasi — F5)
- `channels`: id, org_id, name, entity_type?, entity_id?↗ (terikat proyek/deal), created_by.
- `channel_members`: channel_id↗, user_email, notify_pref (`all`\|`mentions`\|`mute`).

### `notifications`
| field | tipe | ket |
|---|---|---|
| id, org_id, user_email 🔑 | | target |
| title, message, type | str | `info`\|`sla`\|`mention`\|`approval` |
| related_entity_type, related_entity_id ↗ | | |
| read_at | iso? | |

---

## C. OMNICHANNEL (Dok 07)

### `channel_accounts`
| field | tipe | ket |
|---|---|---|
| id, org_id 🔑 | | |
| kind | enum | `whatsapp`\|`meta_lead_ads`\|`google_lead`\|`tiktok_lead`\|`web_form` |
| display_name | str | |
| credentials_ref | str | pointer ke secret (`.env`/vault) — **bukan** nilai mentah |
| mode ⚑ | enum | `live`\|`simulation` (jujur; ditampilkan di UI) |
| is_active | bool | |

### `conversations`
| field | tipe | ket |
|---|---|---|
| id, org_id 🔑 | | |
| channel | enum | `whatsapp`… |
| contact_phone 🔑 | str | E.164 |
| lead_id / customer_id / deal_id ↗ | uuid? | konteks record |
| owner 🔑 | email | assignment |
| status | enum | `new`\|`active`\|`waiting`\|`closed` |
| window_expires_at ⚑ | iso? | **24-jam session window** |
| last_message_at 🔑 | iso | |
| unread_count | int | |

### `messages`
| field | tipe | ket |
|---|---|---|
| id, org_id, conversation_id 🔑↗ | | |
| direction ⚑ | enum | `in`\|`out` |
| type | enum | `text`\|`template`\|`image`\|`doc` |
| body | str? | |
| media_ref ↗ | uuid? | → attachments |
| template_id ↗ | uuid? | bila template |
| wa_message_id | str? | id provider (dedup) |
| status | enum | `queued`\|`sent`\|`delivered`\|`read`\|`failed` |
| is_internal | bool | catatan internal (tak terkirim) |
| created_at 🔑 | iso | |

### `wa_templates`
| field | tipe | ket |
|---|---|---|
| id, org_id | | |
| name, language, category | str | approved Meta |
| body, variables | str,[str] | |
| status | enum | `approved`\|`pending`\|`rejected`\|`local` (simulasi) |

### `automation_rules` (DSL — Dok 13)
| field | tipe | ket |
|---|---|---|
| id, org_id | | |
| name, is_active | | |
| trigger ⚑ | obj | {event, filter} mis. `message.received` + keyword |
| conditions | [obj] | |
| actions | [obj] | `create_lead`\|`advance_stage`\|`create_task`\|`send_template` |
| require_confirmation | bool | human-in-the-loop utk stage sensitif |
| executions | int | audit |

### `lead_capture_events`
| field | tipe | ket |
|---|---|---|
| id, org_id 🔑 | | |
| provider | enum | `meta_lead_ads`… |
| raw_payload | obj | audit |
| dedup_key 🔑 | str | phone/email/ext_lead_id |
| status | enum | `received`\|`processed`\|`duplicate`\|`error` |
| lead_id ↗ | uuid? | hasil |
| campaign_id, adset_id, creative_id, form_id | str? | atribusi |

---

## D. SALES & CRM

### `leads` (PORT + atribusi)
| field | tipe | ket |
|---|---|---|
| id, org_id 🔑 | | |
| name, phone(E.164 🔑), email | str | |
| source | enum | `meta_ads`\|`google_ads`\|`tiktok_ads`\|`referral`\|`walk_in`\|`website`\|`event`\|`manual` |
| campaign, ad_set, ad_name | str? | atribusi (sudah ada di SIPRO) |
| stage ⚑🔑 | enum | `acquisition`\|`nurturing`\|`appointment`\|`booking`\|`recycle` |
| status | enum | back-compat (`new`/`contacted`/`prospect`/`no_response`/`lost`) — map ke stage |
| score | int? | lead scoring |
| project_id ↗ | uuid? | minat |
| assigned_to 🔑 | email? | |
| assignment_history | [obj] | {to,by,at,reason,action} |
| first_contacted_at ⚑ | iso? | set sekali (acquisition→nurturing) |
| response_time_minutes ⚑ | int? | idempotent |
| follow_up_count | int | |
| nurturing_outcome, recycle_reason | str? | |

### `appointments` (PORT)
| field | tipe | ket |
|---|---|---|
| id, org_id, lead_id 🔑↗ | | |
| project_id ↗, scheduled_at 🔑, location, notes | | |
| assigned_to | email | |
| status | enum | `scheduled`\|`done`\|`no_show`\|`canceled` |
| checklist, photos | [ ] | survey (F7) |

### `customers` (CLONE — kaya)
Field lengkap SIPRO: name, nik(🔑), npwp, phone(E.164), email, birthplace/date, gender, marital_status, address/city/province/postal, occupation, company, monthly_income, spouse_*, heir_*, notes, created_from. ⚑ dedup by phone/nik.

### `deals` (PORT + state machine Dok 12)
| field | tipe | ket |
|---|---|---|
| id, org_id 🔑 | | |
| lead_id ↗?, customer_id ↗? | | |
| customer_name/email/phone | str | snapshot |
| unit_id ⚑🔑↗, project_id ↗ | uuid | |
| price | int(IDR) | |
| payment_method | enum | `cash`\|`cash_bertahap`\|`kpr` |
| status ⚑🔑 | enum | `draft`\|`reserved`\|`booked`\|`active`\|`completed`\|`canceled`\|`expired`\|`failed` |
| reserved_at, reserved_until ⚑, booked_at, completed_at | iso? | hold timer |
| financing_id ↗ | uuid? | |

### `reservations` (SPR + booking fee — baru)
| field | tipe | ket |
|---|---|---|
| id, org_id, deal_id 🔑↗ | | |
| booking_fee | int(IDR) | tanda jadi |
| ppjb_due_at ⚑ | iso | wajib PPJB ≤30 hari |
| document_id ↗ | uuid? | SPR |
| status | enum | `active`\|`converted`\|`forfeited` |

### `financing_apps` (KPR — baru)
| field | tipe | ket |
|---|---|---|
| id, org_id, deal_id 🔑↗, customer_id ↗ | | |
| bank_name | str | |
| requested_amount, approved_amount | int(IDR) | plafon |
| dp_amount, tenor_months | int | |
| slik_status | enum | `not_checked`\|`clear`\|`flagged` (pra-skrining) |
| status ⚑ | enum | `draft`\|`submitted`\|`approved`\|`rejected`\|`akad` |
| disbursements | [obj] | {milestone, amount, status, date} — pencairan bertahap ⚑ kait progress |

### `commissions` + `commission_rules` (CLONE)
- `commission_rules`: name, project_id?, role?, rate_type(`percent`\|`flat`\|`tier`), rate_value, tiers[], is_active, priority.
- `commissions`: deal_id↗, unit_id, project_id, assignee_email, assignee_role, rule_id, amount(int), status(`pending`\|`approved`\|`paid`), payout_date. ⚑ satu komisi/deal (idempotent).

---

## E. PROJECT / CONSTRUCTION

### `projects` (PORT)
id, org_id, name, location, description, total_units, target_revenue(int), status(`planning`\|`active`\|`completed`), units_sold/available/reserved (derived), revenue_realized(int).

### `units` (PORT + 3-way status eksplisit — ⚑ Dok 12)
| field | tipe | ket |
|---|---|---|
| id, org_id, project_id 🔑↗ | | |
| block, number, label, unit_type | str | |
| floor_area, land_area | num | |
| price | int(IDR) | |
| status ⚑🔑 | enum | `available`\|`holding`\|`reserved`\|`booked`\|`sold` |
| deal_status | enum? | mirror deal |
| construction_status | enum? | `not_started`\|`in_progress`\|`qc_hold`\|`completed` |
| construction_progress | int(0-100) | |
| payment_status | enum? | `none`\|`dp_paid`\|`installment`\|`overdue`\|`paid_off` |
| coordinates | obj? | siteplan |

### `boq_items` (RAB — baru)
id, org_id, project_id↗, unit_type?, cost_code, description, unit_uom, qty, unit_price(int), amount(int). ⚑ basis MRP & termin.

### `subcontractors` (baru)
id, org_id, name, npwp, phone, contact, docs[], rating?, is_active.

### `work_packages` / SPK (baru)
id, org_id, project_id↗, subcontractor_id↗, scope, contract_value(int), retention_pct, start/end, status(`draft`\|`active`\|`done`), documents[].

### `construction_units` (PORT — weighted)
id, org_id, unit_id🔑↗, project_id↗, unit_label, `phases`:[{id,name,weight,status,progress,tasks:[{id,name,weight,status}]}], overall_progress(int), overall_status⚑, qc_results:[{phase_id,task_id,result,notes,inspector,at}], logs:[]. ⚑ Σweight fase=100; overall=Σ(progress×weight/100).

### `progress_claims` (termin/opname — baru)
id, org_id, work_package_id↗, project_id↗, period, progress_pct, claimed_amount(int), retention_amount(int), status(`submitted`\|`verified`\|`paid`), qc_gate_passed⚑, photos[]. ⚑ bayar hanya jika qc_gate_passed.

### `qc_inspections` (PORT dari qc_results) + `change_orders`
- `qc_inspections`: unit_id↗, phase_id, task_id, result(`pass`\|`fail`), notes, photos[], inspector.
- `change_orders`: project_id/unit_id↗, description, boq_delta, cost_delta(int), status(`proposed`\|`approved`\|`rejected`).

### `materials` / `material_txns` / `stock_opname` (anti-kebocoran — baru)
- `materials`: id, org_id, project_id↗, name, uom, boq_ref?.
- `material_txns`: material_id↗, type(`requisition`\|`grn_receive`\|`issue`\|`return`), qty, ref (PO/task), by, at. ⚑ 3-way match PO→GRN→bill.
- `stock_opname`: project_id↗, material_id↗, period, book_qty, physical_qty, variance⚑ (target 0), by, notes, photos[].

### `permits` (dokumen izin — baru)
id, org_id, project_id↗, type(`KRK`\|`IMB/PBG`\|`SLF`\|`addendum`…), status, due_date⚑, doc_ref, reminder.

---

## F. FINANCE (PSAK 72 — detail model di Dok 15)

### `ar_schedules` / `ar_invoices` / `receipts` (PORT dari billing/payments)
- `ar_schedules`: deal_id↗, unit_id↗, customer_name, items:[{id,description,amount(int),due_date,status(`pending`\|`partial`\|`paid`\|`overdue`),paid_amount}], total, paid, outstanding, status. ⚑ outstanding=total−paid.
- `receipts`: deal_id↗, ar_item_id↗, amount(int), date, method, reference, recorded_by. ⚑ apply → update item + unit.payment_status + emit `payment.*`.

### `ap_bills` / `retentions` / `payments_out`
- `ap_bills`: work_package_id↗, progress_claim_id↗, amount(int), retention_held(int), due_date, status(`open`\|`partial`\|`paid`\|`overdue`). ⚑ net = claimed − retention.
- `retentions`: work_package_id↗, amount(int), release_due_at⚑ (masa pemeliharaan), status(`held`\|`released`).
- `payments_out`: ap_bill_id↗, amount(int), date, method, approved_by⚑.

### `contract_liabilities` / `revenue_recognitions` (PSAK 72)
- `contract_liabilities`: deal_id↗, balance(int) — akumulasi penerimaan sebelum BAST. ⚑ naik saat receipt, nol saat RevRec.
- `revenue_recognitions`: deal_id↗, unit_id↗, revenue(int), cogs(int), recognized_at⚑ (= BAST/serah terima), event `unit.bast`.

### `tax_records`
id, org_id, deal_id?↗, type(`PPN`\|`BPHTB`\|`PPh_final`), base(int), rate, amount(int), due_date, status, doc_ref. (rumus Dok 15).

---

## G. DOKUMEN & FILE (CLONE dari F1)

### `document_templates` (CLONE)
id, org_id, code(`SPR`\|`PPJB`\|`AJB`\|`BAST`\|`SPK`\|`CUSTOM`), name, description, content(`{{var.path}}`), variables[], is_active.

### `documents` (CLONE + prasyarat)
id, org_id, template_id↗, template_code, doc_number(`CODE/YEAR/NNNN`), title, deal_id↗, customer_id↗, unit_id↗, project_id↗, content(resolved), variables_snapshot, status⚑(`draft`\|`finalized`\|`signed`\|`canceled`), signatures:[{role(`buyer`\|`seller`\|`witness`),name,signature_image(base64),signed_at,ip}], finalized_at, first_signed_at. ⚑ PPJB butuh guard prasyarat (Dok 12).

### `attachments` (F7 — object storage)
id, org_id, entity_type, entity_id↗, kind(`photo`\|`doc`), url/key, mime, size, by, at.

---

## H. INDEX & INVARIAN GLOBAL (di-gate `verify_data_integrity` / `verify_referential_integrity`)
1. Semua koleksi bisnis punya `org_id` (⚑ tenant scope).
2. `units.status` konsisten dgn deal aktif (⚑ 3-way — Dok 12).
3. `deals.unit_id` unik untuk status aktif (⚑ no double-booking).
4. `construction_units`: Σweight fase = 100; overall = Σ(progress×weight/100).
5. `ar_schedules.outstanding = total − paid`; `ap_bills.net = claimed − retention`.
6. `contract_liabilities` naik saat receipt, nol saat RevRec; revenue hanya di `unit.bast`.
7. Tak ada FK yatim (lead→owner, deal→unit/project, doc→deal, dst).
8. `tasks.source_event` idempotent (tak ada 2 open task sama).
9. Index minimal: semua 🔑 di atas + `created_at` untuk sort.

> Dok ini = **kontrak data**. Perubahan skema apa pun WAJIB update dok ini + `verify_contract`/invarian sebelum kode berubah (aturan governance Dok 04 §7).
