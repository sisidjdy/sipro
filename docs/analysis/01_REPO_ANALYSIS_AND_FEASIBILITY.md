# SIPRO Rebuild — Dokumen 01
# ANALISIS REPO & STUDI KELAYAKAN (Feasibility)

> Status: ANALISIS (belum ada kode fitur). Bahasa: Indonesia.
> Metode: pembacaan langsung kode kedua repo (grounded, bukan asumsi).
> Sumber: `pandekomangyogaswastika-dot/SIPROnext` (sistem lama) + `udahenggaktaulagi/kn` (referensi fondasi engineering).
> Tujuan dokumen: menetapkan FAKTA kondisi lama, apa yang bisa di-*clone*, apa yang harus dibangun ulang, dan kelayakan teknis rebuild.

---

## 0. RINGKASAN EKSEKUTIF

SIPROnext adalah **Property Development Operating System** (FARM stack: React 19 + FastAPI + MongoDB) dengan **domain model yang sebenarnya cukup baik** — ide bisnisnya solid: satu sistem menyatukan CRM/marketing (lead lifecycle), penjualan (deal/unit), konstruksi (fase/QC), dan finance (billing/payment). **Masalahnya bukan di ide, tapi di EKSEKUSI**: arsitektur informasi (IA) berorientasi-modul & identik untuk semua peran, tanpa RBAC, tanpa guardrails, WhatsApp mock, task engine yang ditempel belakangan, dan pengalaman "system of record" pasif (bukan memandu pengguna).

Repo `kn` (Kain Nusantara — ERP/WMS tekstil) **bukan** domain properti, tetapi merupakan **teladan disiplin engineering** yang persis diminta owner: guardrail eksekutabel (gate yang bisa GAGAL), dokumen SSOT hidup (CODEBASE_MAP, ENTITY_REGISTRY), navigasi config-driven, **Role-Home** (Sales Home "Performa Saya", Admin "Control Tower"), guided tours + onboarding, dan protokol kerja per-fase yang ketat.

**Verdikt kelayakan:** Rebuild **SANGAT LAYAK** dan direkomendasikan sebagai *greenfield dengan panen selektif* — bukan melanjutkan repo lama, bukan pula membuang semua. Kita **panen logika domain** SIPROnext (lifecycle, invarian status unit, weighted construction progress, struktur finance) tetapi **membangun ulang fondasi, IA, RBAC, dan UX** dengan disiplin `kn` yang ditingkatkan (lihat Dokumen 04).

---

## 1. FAKTA SIPROnext (grounded dari kode)

### 1.1 Arsitektur teknis
| Aspek | Kondisi | Catatan |
|---|---|---|
| Stack | React 19 + FastAPI + Motor(MongoDB) | Sama persis dengan environment kita → banyak yang *cloneable* |
| Backend | `server.py` **1.974 baris** (auth, org, projects, units, leads, appointments, deals inline) + 11 router terpisah (tasks, finance, construction, commissions, customers, dashboard, documents, notifications, siteplan, whatsapp, dev_report) | Modularisasi **setengah jalan** — inti masih monolit |
| DB | 20 koleksi, UUID string, **tanpa referential integrity**, index seadanya | Orphan record mungkin terjadi |
| Auth | JWT + bcrypt, cookie httpOnly + Bearer, brute-force lock | Cukup, tapi **tanpa RBAC di route level** |
| Routing FE | React Router (path-based), Sidebar flat | IA modul, bukan alur |
| Tema | Glassmorphism (gradient, backdrop-blur, Plus Jakarta Sans) | Terkesan usang; bukan modern-SaaS |

### 1.2 Domain model yang SUDAH ADA (aset berharga — layak dipanen)
- **Lead lifecycle 5-tahap**: `acquisition → nurturing → appointment → booking → recycle`, transisi terkontrol + event log + backward-compat status.
- **Assignment system**: manual + auto-assign (round-robin → load-balanced di Phase D), accept/reject + `assignment_history`.
- **Lead Response Time Tracker**: `response_time_minutes` idempotent (dihitung sekali di kontak pertama) + `first_contacted_at`.
- **Projects → Units** dengan generate-units per blok + koordinat siteplan.
- **Unit lifecycle** `available → reserved → booked → sold` dengan **3-way status sync** (deal / construction / finance).
- **Deal lifecycle** `draft → reserved → booked → active → completed` (+canceled/expired/failed) dengan atomic booking (`find_one_and_update`) + reservation sweeper + booking expiry.
- **Finance**: `Deal → BillingSchedule → BillingItems[] → Payments`, payment auto-update billing + unit `payment_status`.
- **Construction**: `ConstructionUnit → Phase(weight) → Task(weight)` weighted progress + QC pass/fail (qc_hold).
- **Task Engine (Phase C)**: koleksi `tasks` persisten, auto-task idempotent via `source_event` (lead.created→contact, stage→nurturing→follow_up, dst), stats, permissions configurable.
- **Phone normalization E.164**, MongoDB indexes (Phase D), cookie security env-driven.

### 1.3 KEGAGALAN EKSEKUSI (ranked by severity) — inilah "kenapa buruk"

| # | Sev | Temuan (grounded) | Dampak |
|---|---|---|---|
| S1 | 🔴 KRITIS | **IA berorientasi-modul & IDENTIK untuk semua peran.** Sidebar flat: Dashboard / Lead Lifecycle / Property / Sales / Operations / Comms / System — sama untuk sales, finance, PM, admin. | Sales tak punya "ruang kerja"; pengguna harus tahu modul mana untuk tiap langkah → beban kognitif tinggi, bukan task-based. |
| S2 | 🔴 KRITIS | **Tanpa RBAC enforcement.** Setiap user terautentikasi bisa akses endpoint apa pun (diakui di DEVELOPMENT_REPORT §7). | Kebocoran data lintas-peran (finance ↔ sales ↔ konstruksi). Blocker produksi. |
| S3 | 🔴 KRITIS | **"System of record" pasif, bukan pemandu.** Task engine ditempel di Phase C; dashboard "task queue" dihitung client-side; tak ada next-best-action, tak ada activity feed/kolaborasi. | Tak sesuai visi owner ("Slack tapi ERP", task-based yang memandu). |
| S4 | 🟠 SEDANG | **WhatsApp MOCK**, auto-followup rules hanya trigger manual (`/simulate-followup`). | Fitur komunikasi inti tidak nyata. |
| S5 | 🟠 SEDANG | **Domain properti-legal ID tidak lengkap.** Tidak ada SPR/booking-fee formal, PPJB/AJB/BAST doc workflow, modul KPR/financing, retensi/termin subkontraktor, pajak (PPN/BPHTB/PPh). | Tidak layak untuk operasi developer nyata (lihat Dok 02). |
| S6 | 🟠 SEDANG | **Tanpa guardrails/gates, tanpa CODEBASE_MAP/ENTITY_REGISTRY.** Ada `test_result.md` + iteration reports, tapi tak ada gate yang bisa GAGAL. | Drift FE↔BE, 5xx senyap, dan "hijau palsu" tak terdeteksi — akar kualitas buruk. |
| S7 | 🟠 SEDANG | **`server.py` monolit** (~2k baris) + tanpa batas ukuran file. | Kecepatan dev melambat; sulit di-review. |
| S8 | 🟢 RENDAH | Tanpa file upload/foto, tanpa PDF legal, tanpa referential integrity, tanpa multi-tenant scope aktif (`organizations` ada tapi tak dipakai). | Backlog fitur. |
| S9 | 🟢 RENDAH | Tema glassmorphism, densitas tak konsisten, tanpa loading/empty/error state baku. | Kualitas visual & UX. |

### 1.4 Apa yang bisa DI-CLONE vs DIBANGUN ULANG

| Bagian SIPROnext | Keputusan | Alasan |
|---|---|---|
| Logika lifecycle lead & transisi + response-time | **PANEN (port ulang)** | Matang & teruji; jadi basis stage engine baru |
| Unit 3-way status sync + atomic booking + sweeper | **PANEN** | Pola benar; pindah ke service + invarian gate |
| Weighted construction progress + QC | **PANEN** | Struktur baik; perluas ke BoQ/termin/retensi |
| Finance billing→items→payments | **PANEN sebagian** | Perbaiki ke model AR/AP + contract-liability + revenue recognition (PSAK 72) |
| Task engine + auto-task via source_event | **PANEN & PROMOSIKAN jadi fondasi** | Jadikan "Guided Work Engine" first-class (bukan tempelan) |
| shadcn/ui primitives (`components/ui/*`) | **CLONE langsung** | Standar; environment kita juga punya |
| Struktur router per-domain | **POLA diikuti, kode ditulis ulang** | Terapkan batas ukuran + kontrak kanonik |
| Auth (JWT/bcrypt) | **PERTAHANKAN + tambah RBAC** | RBAC = perbaikan #1 |
| IA/Sidebar/Routing FE | **BANGUN ULANG** | Ganti ke config-driven + Role-Home + Work Hub |
| Tema glassmorphism | **BUANG** | Ganti ke modern-SaaS (design_agent) |
| WhatsApp mock, dev-report page | **BUANG / tunda** | Ganti dgn integrasi nyata terjadwal / hapus internal tool |

---

## 2. FAKTA `kn` — POLA FONDASI YANG DIADOPSI (dan ditingkatkan)

`kn` = 680 file, sangat matang. Yang **diadopsi** sebagai fondasi SIPRO baru:

### 2.1 Guardrails eksekutabel (gate yang bisa GAGAL, exit≠0)
- `verify_contract.py` — nama koleksi kanonik vs terlarang (RC-1 collection drift).
- `verify_api_contract.py` — **3 cek**: (A) duplicate route, (B) FE call → route backend ada, (C) FE field ⊆ BE response (menangkap label kosong senyap).
- `verify_data_integrity.py` — invarian data (stok/order/number-series/intent lintas-endpoint).
- `health_check.py` — cek **ISI** endpoint kritis (bukan sekadar 200).
- `audit_endpoint_sweep.py` — sweep semua GET /api → cari 5xx.
- `ux_audit.py` — baseline UX eksekutabel (E1 loading / E2 empty / E3 chart-guard; W testid/tabular-nums).
- `check_nav_map.py` — setiap nav id → route + PAGE_META.
- `validate_compliance.py` — batas ukuran file & naming.
- `seed_reset.sh` — reset DB bersih + jalankan gate.
- `load_context.sh` — snapshot service/env/DB/file-size tiap awal sesi.

### 2.2 Dokumen SSOT hidup
- `ENGINEERING_GUARDRAILS.md` — RC taxonomy (RC-1..RC-15), 3-Gate (pre/during/post-code), Definition of Done, protokol eskalasi, "kapan nambah gate", blindspot log.
- `FRONTEND_GUARDRAILS.md` — kontrak API FE, UX, testability, nav, batas ukuran, RC-F taxonomy.
- `UX_USABILITY_STANDARD.md` — prosa yang di-*enforce* `ux_audit.py`.
- `CODEBASE_MAP.md` — peta file + endpoint + status ukuran.
- `ENTITY_REGISTRY.md` — SSOT skema/koleksi/invarian.
- `MASTER_ROADMAP.md` — EPIC + Foundations (F1..F7) + dependency graph.
- `plan.md` — presisi, ber-anchor, lessons-learned, DoD per fase.
- `SESSION_HANDOFF.md` — kontinuitas antar sesi.

### 2.3 Pola produk (persis arah owner)
- **Config-driven navigation** (`navigationConfig.js`): `PAGE_META`, `NAV_STRUCTURE`, `buildNavGroups(role)`, `ROLE_HOME_REGISTRY`, `resolveActiveNavId`, `GUIDANCE_MAP`, grup "Segera Hadir" untuk item coming-soon.
- **Role-Home**: Sales Home "Performa Saya", Admin "Control Tower", Manager "Performa Tim".
- **Guided tours + onboarding** (`tourDefinitions.js`, `GuidedTour.jsx`, `OnboardingPanel`, `GuidedActionPanel`).
- **Golden rules**: verifikasi di DB bersih; "200/running ≠ benar"; guardrail tumbuh bersama fitur; dilarang klaim hijau palsu.

### 2.4 Yang akan kita TINGKATKAN melebihi `kn` (ringkas; detail di Dok 04)
1. **RBAC ditegakkan sejak Fase 0** (kelemahan #1 SIPRO lama) + gate RBAC (`verify_rbac.py`).
2. **Multi-tenant-ready** — `org_id`/entity-scope disematkan di setiap koleksi & gate sejak awal (pilihan owner: internal dulu, arsitektur siap SaaS).
3. **Guided Work Engine + Domain Event Bus** sebagai fondasi first-class (kn tak punya; SIPRO menempelnya telat).
4. **Activity & Collaboration layer** (feed + komentar + @mention + thread + channel) — inti "Slack tapi ERP".
5. **Referential integrity checks** ditambahkan ke gate.
6. **Design system modern-SaaS** yang lebih baik dari iOS-glass `kn` (via design_agent).

---

## 3. STUDI KELAYAKAN (FEASIBILITY)

### 3.1 Kelayakan teknis — TINGGI
- Stack identik (FARM) → tak ada risiko platform; shadcn/ui tersedia; MongoDB async matang.
- Pola guardrail `kn` terbukti berjalan di stack yang sama → dapat direplikasi.
- Logika domain SIPRO sudah ada sebagai referensi → mengurangi risiko "salah model".

### 3.2 Kelayakan domain — SEDANG→TINGGI (butuh riset, sudah dilakukan di Dok 02)
- Properti ID punya kompleksitas legal (PPJB/AJB/BAST), pembiayaan (KPR bertahap), pajak (PPN/BPHTB/PPh), dan akuntansi (PSAK 72 point-in-time) — **bukan sepele**, tapi terpetakan (Dok 02). Ini justru pembeda nilai vs sistem lama.

### 3.3 Kelayakan UX (visi "Slack tapi ERP") — SEDANG (paling menantang, paling bernilai)
- Pola 2026 (HubSpot Sales Workspace "Suggested Tasks", Salesforce Einstein NBA) memvalidasi arah task-based/guided. Layer kolaborasi (feed/thread/mention) menambah kompleksitas real-time → dimulai polling/optimistic dulu, WebSocket menyusul.

### 3.4 Risiko utama & mitigasi
| Risiko | Mitigasi |
|---|---|
| Scope besar (3 pilar × task-based × multi-tenant) | Fase ketat; Sales/CRM dulu sebagai tulang punggung UX; guardrail cegah drift |
| "Hijau palsu" (kegagalan SIPRO lama) | Gate eksekutabel + testing_agent + DoD jujur sejak Fase 0 |
| Akuntansi/pajak salah model | Model finance dipisah (AR/AP/contract-liability/rev-rec) sesuai PSAK 72 (Dok 02) |
| Real-time kolaborasi mahal | Mulai polling + optimistic UI; WebSocket sebagai peningkatan terjadwal |
| Multi-tenant menyulitkan awal | Cukup sematkan `org_id` + scope helper + gate; UI single-tenant dulu |

### 3.5 Rekomendasi strategi rebuild
**Greenfield + panen selektif**, dieksekusi dengan disiplin `kn` yang ditingkatkan:
1. Bangun **fondasi** (guardrails + docs + skeleton + RBAC + entity-scope + event bus + design system) — *sebelum* fitur.
2. Bangun **Sales/CRM + Work Hub** sebagai pilar-1 (UX task-based paling kritis).
3. Lanjut **Konstruksi (subcon)** lalu **Finance** di atas fondasi & Work Hub yang sama.
4. Setiap fase: POC/script → implementasi → gate hijau → testing_agent → DoD → update docs.

> Kesimpulan: Ide SIPRO layak dan berharga. Kegagalan lama murni soal **fondasi & eksekusi**, bukan konsep. Dengan fondasi ala `kn` (ditingkatkan) + IA task-based + model domain properti ID yang benar, rebuild berpeluang tinggi menjadi sistem matang.
