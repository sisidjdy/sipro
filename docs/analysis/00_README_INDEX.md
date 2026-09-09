> **⚠️ LANJUTAN V2 (16 Agu 2026):** review owner menghasilkan seri dokumen baru
> **`docs/v2/20–36`** (CRM/BI/legal/pembayaran/proyek-unit + roadmap Fase 39–51).
> **Baca `docs/v2/20_INDEX_V2.md` lebih dulu.** Bila V2 berbeda dengan dokumen 00–19 di sini, **V2 menang**.

# SIPRO REBUILD — FRAMEWORK PENGEMBANGAN (baca ini dulu)

> Satu **framework** yang saling mengunci: **WHY → WHAT → SPEC → HOW**. Bukan dokumen terpisah. Perintah owner: analisis mendalam & bersinergi; plan detail (implementasi + gambaran produk); **spesifikasi lengkap seluruh sistem**; **adopsi kode SIPROnext** untuk minimalisir kerugian.

## 0. DECISIONS LOG (keputusan owner — mengikat semua dokumen)
1. **Strategi:** Buat **Lapisan Spesifikasi lengkap untuk SELURUH sistem** dulu (Dok 10–17) → POC core → Fase 0. *(bukan just-in-time)*
2. **MVP Slice:** **KEDUANYA** — (A) Sales tipis: Ads/WA capture→lead→Work Hub→appointment→SPR/booking; (B) Konstruksi tipis: proyek→unit→progress/Kurva-S→material opname. (Dok 17 §3)
3. **WA/Ads:** **Simulasi jujur dulu + POC round-trip**; aktifkan `live` saat kredensial Meta tersedia (tanpa ubah kontrak). (Dok 07/17)
4. **Adopsi kode SIPROnext:** panen agresif (document workflow+PDF, commission engine, weighted construction+QC, atomic booking, idempotent task, normalizers) → di-PORT ke fondasi baru. (Dok 10)
5. **Design:** modern-SaaS, lebih matang dari `kn` (via design_agent).
6. **Tenancy:** internal dulu, arsitektur siap multi-tenant (`org_id` sejak awal).

## 1. EMPAT LAPISAN FRAMEWORK
```
 WHY (root cause / kebutuhan)      WHAT (produk & arsitektur)     SPEC (kontrak siap-build)         HOW (eksekusi & mutu)
 01 Repo & Feasibility            03 IA + Work Hub + Domain       10 Adoption Map                    04 Roadmap: Fondasi/Foundations
 02 Business Process + Benchmark   08 Plan+Product Vision          11 Entity Registry (field)         04 EPIC + Guardrail + DoD
 05 Pain Points (outcome)                                          12 State Machines & Invariants     08 §Implementasi (detail)
 06 Personas/JTBD + Prod Bench                                     13 Engine Spec (event/sched/rules) plan.md (fase berjalan)
 07 Omnichannel Lead Engine                                        14 RBAC Matrix                     scripts/*.py (gates)
 09 Critical Review (gap)                                          15 Finance Model & Pajak
                                                                   16 API Contract
                                                                   17 NFR + POC + MVP + Tests
        └── acuan root-cause ───────────────┴── gambaran & arsitektur ──┴── kontrak eksekusi ──────────┴── bangun & verifikasi
```
- **Butuh alasan/akar masalah?** → 01/02/05/06/07/09.
- **Butuh gambaran produk / arsitektur?** → 03 + 08.
- **Butuh kontrak siap-build (skema/API/state/engine/RBAC/finance/NFR)?** → 10–17.
- **Butuh eksekusi/urutan/mutu?** → 04 + 08 §implementasi + plan.md + scripts.

## 2. DAFTAR DOKUMEN
| # | Dokumen | Lapisan | Peran |
|---|---|---|---|
| 01 | REPO_ANALYSIS_AND_FEASIBILITY | WHY | fakta SIPRO + pola kn + kelayakan |
| 02 | BUSINESS_PROCESS_AND_BENCHMARK | WHY | proses ID end-to-end + benchmark |
| 05 | PAIN_POINTS_AND_BUSINESS_NEEDS | WHY | outcome-driven Pain→KPI |
| 06 | USER_PERSONAS_AND_PRODUCT_BENCHMARK | WHY | 6 persona/JTBD + benchmark produk |
| 07 | OMNICHANNEL_LEAD_ENGINE | WHY/WHAT | WA in-chat + Ads capture + triggers |
| 09 | CRITICAL_REVIEW_AND_READINESS_GAPS | WHY | review jujur + daftar gap (dipenuhi 10–17) |
| 03 | IA_WORKHUB_UX_BLUEPRINT | WHAT | IA + Work Hub + domain model |
| 08 | MASTER_PLAN_AND_PRODUCT_VISION | WHAT/HOW | plan detail + gambaran produk |
| 04 | MASTER_ROADMAP | HOW | Fondasi + Foundations + EPIC + DoD |
| **10** | **ADOPTION_MAP** | SPEC | clone/port/rebuild/discard (grounded kode) |
| **11** | **ENTITY_REGISTRY** | SPEC | skema field-level (SSOT data) |
| **12** | **STATE_MACHINES_AND_INVARIANTS** | SPEC | transisi + guard + invarian |
| **13** | **ENGINE_SPEC** | SPEC | event bus/scheduler/work-engine/rules/NBA |
| **14** | **RBAC_MATRIX** | SPEC | role×resource×action + scoping |
| **15** | **FINANCE_MODEL_AND_TAX** | SPEC | PSAK 72 + AR/AP/retensi/RevRec + pajak |
| **16** | **API_CONTRACT** | SPEC | konvensi + katalog endpoint |
| **17** | **NFR_INTEGRATION_POC_MVP** | SPEC | NFR + POC core + MVP slice + test scenarios |

## 3. EMPAT OUTCOME BISNIS (north-star)
1. Konversi ↑ · 2. Cegah kebocoran · 3. Jaga deadline · 4. Amankan arus kas & kepercayaan.

## 4. TRACEABILITY (kebutuhan → kode → gate) — versi diperluas ke SPEC
| Outcome | Pain (05/07) | Kapabilitas (03/07) | EPIC (04/08) | Entity (11) | State/Rule (12/13) | RBAC (14) | Guardrail |
|---|---|---|---|---|---|---|---|
| Konversi ↑ | respons lambat | Ads/WA capture + task 5-mnt | 1.7 | leads, tasks, conversations, lead_capture_events | GWE rule lead.created; automation msg.received | sales own | verify_rbac, signature |
| Konversi ↑ | double booking | atomic hold | 1.3/2.0 | units, deals | Deal SM + atomic | sales/manager | verify_data_integrity |
| Konversi ↑ | sistem pasif | Work Hub + NBA | 1.0 | tasks, activities, events | GWE + NBA rules | per role | ux_audit |
| Cegah kebocoran | material dicuri | ledger+opname+3way | 2.6 | materials, material_txns, stock_opname | 3-way match | finance/site | data_integrity, audit |
| Jaga deadline | jadwal telat | Kurva-S + progress | 2.3 | construction_units, progress_claims | progress SM + QC gate | PM/site | data_integrity |
| Arus kas | RevRec (PSAK72) | contract-liab + RevRec@BAST | 3.2 | contract_liabilities, revenue_recognitions | RevRec @ unit.bast | finance | data_integrity |
| Trust | pembeli tak percaya | Customer Portal | M1 | documents, ar_schedules, construction_units | \u2014 | portal scope | verify_rbac |

(Matriks kapabilitas\u2192pain lengkap tetap di Dok 05/08.)

## 5. FONDASI LINTAS-SEKTOR (build once) — F1..F10 (Dok 04 §2)
RBAC · Multi-tenant scope · Event Bus · Guided Work Engine · Activity/Collaboration · Document engine · Object storage · Finance primitives · Process Timeline · Notification.

## 6. VERDIKT & STATUS
Rebuild **layak & bernilai**; kegagalan lama = fondasi & eksekusi. Aset SIPRO **dipanen agresif** (Dok 10) di atas fondasi ala `kn` yang ditingkatkan (RBAC + multi-tenant + event/engine + omnichannel + design modern-SaaS).

- [x] 01–09 Analisis + blueprint + roadmap + review kritis
- [x] **10–17 Lapisan Spesifikasi lengkap (seluruh sistem)** ← keputusan owner
- [x] design_agent → design system → `/app/design_guidelines.md` (modern-SaaS: teal+amber, Space Grotesk/Inter/Roboto Mono, pattern library + data-testid)
- [x] **POC core 7/7 LULUS** (`/app/poc/poc_core.py`) — event bus+GWE idempotent, expiry sweeper, atomic booking konkuren, automation rule, RevRec PSAK 72, Document+PDF, WA/Ads webhook-sim+dedup
- [ ] Fase 0 Fondasi + MVP Slice A & B (Dok 17 §3) → gate hijau → testing_agent
