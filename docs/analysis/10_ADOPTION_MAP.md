# SIPRO Rebuild — Dokumen 10
# ADOPTION MAP: APA YANG DI-CLONE / PORT / BANGUN-ULANG / BUANG (minimalisir kerugian)

> Status: SPESIFIKASI (grounded ke kode SIPROnext). Bahasa: Indonesia.
> Tujuan: memanen aset SIPROnext yang **sudah terbukti** agar rebuild tidak membuang kerja yang berharga. Setiap baris menyebut **file & baris asal** + **verdikt** + **perubahan wajib**.
> Legenda verdikt: **CLONE** (ambil ~apa adanya) · **PORT** (pindah + sesuaikan ke fondasi baru: org_id, RBAC, event bus, batas file) · **REBUILD** (tulis ulang, pola sbagai acuan) · **DISCARD** (buang/tunda).

---

## 0. RINGKASAN NILAI YANG DIPANEN (effort saved)
SIPROnext **jauh lebih matang dari kesan awal** di lapisan domain & beberapa engine. Yang bisa dipanen langsung menghemat estimasi besar:
- ✅ **Document Workflow legal (SPK/PPJB/AJB/BAST) + PDF + e-sign** — hampir lengkap (`documents_router.py`, `pdf_utils.py`). *(Ini menutup "gap legal/dokumen" yang saya soroti di Dok 09 §2C.)*
- ✅ **Commission engine** (rules flat/percent/tier + resolver specificity+priority + auto-create idempotent) — `shared.py`.
- ✅ **Weighted construction progress + QC** (fase→task berbobot, recalc, qc_hold, sync unit) — `construction_router.py`.
- ✅ **Atomic booking** (`find_one_and_update`) + **expiry sweeper** + deal/lead **state machine** — `server.py`.
- ✅ **Idempotent auto-task via `source_event`** (seed Guided Work Engine) + **event-emission pattern** (seed Event Bus) — `shared.py` + seluruh router.
- ✅ **Normalisasi phone E.164 / NIK**, cookie auth, **RBAC scoping** (SCOPED_ROLES) — `shared.py`.
- ✅ **Customer model kaya** (NIK/NPWP/spouse/heir/income) — `models.py` (ideal untuk KPR/legal).

> Estimasi: ~40–55% logika domain backend dapat di-PORT (bukan tulis dari nol), asalkan dibungkus fondasi baru (org_id, RBAC penuh, event dispatcher, batas ukuran file).

---

## 1. BACKEND — CROSS-CUTTING (`shared.py`, `deps.py`)
| Aset (asal) | Verdikt | Perubahan wajib |
|---|---|---|
| `_normalize_phone` E.164 idempotent (shared.py:13) | **CLONE** | pindah ke `core_utils` |
| `_normalize_nik` (shared.py:31) | **CLONE** | idem |
| `_set_auth_cookies` (shared.py:67) | **CLONE** | env-driven (sudah) |
| `_due_in` (shared.py:82) | **CLONE** | untuk scheduler/SLA |
| `_auto_create_task` idempotent `source_event` (shared.py:94) | **PORT** | jadi inti **Guided Work Engine**; tambah `org_id`, dipicu **event dispatcher** (bukan panggilan langsung tersebar) |
| Event insert pattern `db.events.insert_one({type,entity_type,entity_id,data})` | **PORT** | formalkan jadi **Event Bus** + dispatcher yang mengonsumsi (SIPRO hanya mencatat, tak mengonsumsi) |
| SCOPED_ROLES + `_apply_*_scope` + `_can_access_lead` (shared.py:39) | **PORT** | perluas ke **RBAC matrix penuh** (Dok 14) + `org_id` scope (Dok 13 §tenant) |
| `_find_or_create_customer_from_deal` (shared.py:133) | **PORT** | tambah org_id + dedup lebih kuat |
| Commission `_calc_commission`/`_resolve_commission_rule`/`_auto_create_commission` (shared.py:163–247) | **PORT** | tambah org_id; picu via event `deal.completed`/`payment.paid_off` (bukan langsung); recognition saat lunas/akad |

## 2. BACKEND — MODELS (`models.py`, 348 baris)
| Model | Verdikt | Catatan |
|---|---|---|
| Auth (Login/Register/Forgot/Reset) | **CLONE** | + RBAC role enum |
| Organization/Project/Unit Create | **PORT** | Unit tambah 3-way status fields eksplisit |
| Lead* (Create/Assign/Activity) | **PORT** | tambah atribusi ads (campaign/ad_set/ad_name sudah ada!), score |
| Appointment/Deal Create | **PORT** | Deal tambah `customer_id`, `financing` link |
| **Customer** (kaya: NIK/NPWP/spouse/heir/income) | **CLONE** | ideal KPR/legal — pertahankan |
| **Commission** (Rule/Update/Payout) | **CLONE** | engine sudah ada |
| **DocumentTemplate/Document/Sign** (F1) | **CLONE** | lengkap; tambah kode SPR + prasyarat PPJB |
| Billing/Payment | **PORT** | evolusi ke AR/AP/contract-liability (Dok 15) |
| Construction Phase/Progress | **PORT** | tambah BoQ/material/termin/retensi |
| WhatsApp/AutoFollowUpRule | **REBUILD** | jadi Omnichannel + Automation Rules DSL (Dok 07/13) |
| Task* (Create/Update/Complete/Permissions) | **PORT** | inti Work Hub |
| DevReportItem/Siteplan | **DISCARD**/PORT | DevReport = internal tool → DISCARD; Siteplan → PORT opsional |

## 3. BACKEND — ROUTER LOGIC
| Router (asal) | Verdikt | Perubahan wajib |
|---|---|---|
| `documents_router.py` (draft→finalized→signed, context builder, doc_number, RBAC) | **CLONE→PORT** | + org_id; + prasyarat PPJB (progress≥20% & review 7 hari) sebagai guard; + kode SPR/BAST event ke lifecycle |
| `pdf_utils.py` (reportlab markdown-lite + signature block) | **CLONE** | ganti header/branding; dukung foto (BAST) |
| `construction_router.py` (default phases, recalc, QC, sync) | **PORT** | + BoQ link, material issue, termin, kurva-S; foto ber-lokasi |
| `finance_router.py` (billing→items→payment, unit payment_status) | **PORT** | jadi AR; tambah AP/retensi/contract-liability/RevRec (Dok 15) |
| `commissions_router.py` | **PORT** | pakai engine shared |
| `customers_router.py` | **PORT** | + KYC KPR |
| `tasks_router.py` (task engine + permissions) | **PORT** | inti Work Hub + NBA |
| `notifications_router.py` (auto_followup + simulate) | **REBUILD** | jadi Automation Rules engine nyata (Dok 13) |
| `dashboard_router.py` (role-aware summary) | **PORT** | jadi Role-Home KPI |
| `siteplan_router.py` | **PORT (opsional)** | visual layout unit |
| `whatsapp_router.py` (send=SIMULASI) | **REBUILD** | jadi Omnichannel Inbox nyata + mode simulasi jujur (Dok 07) |
| `dev_report_router.py` | **DISCARD** | tool internal, bukan produk |
| `server.py` monolit (auth/org/project/unit/lead/appointment/deal + seed) | **PORT (pecah)** | pisah ke router per-domain; **atomic booking + expiry sweeper + lead/deal state machine di-PORT utuh** (logika benar) |

## 4. FRONTEND
| Aset | Verdikt | Catatan |
|---|---|---|
| `components/ui/*` (shadcn) | **CLONE** | standar; environment kita juga punya |
| Sidebar flat / module IA / react-router path | **REBUILD** | ganti ke config-driven nav + Role-Home + Work Hub (Dok 03) |
| Halaman fitur (Leads/Deals/Construction/Finance) | **REBUILD** | pakai design system baru + pola loading/empty/error + testid |
| Tema glassmorphism | **DISCARD** | ganti modern-SaaS (design_agent) |
| i18n (t('...')) | **PORT (opsional)** | pertahankan struktur ID; sederhanakan |

## 5. DOKUMEN/DISIPLIN (dari kn, ditingkatkan) — bukan dari SIPRO
Guardrail scripts + docs (Dok 04 §1.2) tetap dibangun baru (SIPRO tak punya). SIPRO menyumbang **logika**, kn menyumbang **disiplin**.

## 6. RISIKO ADOPSI (agar tidak "mewarisi bug")
- Logika SIPRO **belum ber-org_id & RBAC penuh** → saat PORT, **wajib** tambah scope/permission + gate (`verify_tenant_scope`, `verify_rbac`).
- Event hanya **dicatat**, tak dikonsumsi → **wajib** bangun dispatcher + scheduler (Dok 13); jangan asumsikan auto-followup jalan.
- Finance SIPRO **naif (billing saja)** → jangan CLONE mentah; **PORT dengan model PSAK 72** (Dok 15) agar tidak false-green.
- Tanpa referential integrity → tambah `verify_referential_integrity` saat PORT.

> Kesimpulan: **panen agresif di lapisan domain & document/commission/construction engine (hemat besar), rebuild di IA/UX/finance-akuntansi/omnichannel, bungkus semua dengan fondasi & guardrail baru.**
