# SIPRO Rebuild — Dokumen 03
# BLUEPRINT IA & UX "WORK HUB" (Slack tapi ERP) + MODEL DOMAIN

> Status: BLUEPRINT DESAIN (belum kode). Bahasa: Indonesia.
> Keputusan owner terpakai: **Slack=C (Work Hub terpadu)**, **tenancy=C (internal dulu, siap multi-tenant)**, **design=modern SaaS lebih baik dari `kn`**.
> Prinsip induk: **IA berbasis ALUR & PERAN**, sistem **memandu** (guided), bukan sekadar mencatat.

---

## 1. PRINSIP IA (INFORMATION ARCHITECTURE)

1. **Flow-based, bukan module-based.** Pengguna memasuki sistem lewat *pekerjaan* ("apa yang harus saya kerjakan"), bukan daftar modul. Modul tetap ada sebagai "rak data", tapi bukan pintu utama.
2. **Role-tailored.** Tiap peran punya Home, chrome (KPI strip), navigasi, dan izin berbeda — semuanya **config-driven** (bukan hardcode).
3. **Progressive disclosure.** Informasi lanjutan (biaya/HPP, lot, detail teknis) disembunyikan dari peran yang tak butuh; muncul on-demand.
4. **Wayfinding jelas.** Breadcrumb, penamaan Bahasa Indonesia baku, dan **Process Timeline** (rantai dokumen) di record kunci → tak ada dead-end.
5. **Kontekstual, tanpa keluar layar.** Aksi terjadi di tempat data berada (pelajaran Salesforce/HubSpot 2026).
6. **Jujur soal status data.** Setiap area data punya loading/empty/error (di-*enforce* `ux_audit.py`).

---

## 2. PERAN & ROLE-HOME (config-driven `ROLE_HOME_REGISTRY`)

| Peran | Home (landing) | Fokus | Contoh yang DISEMBUNYIKAN |
|---|---|---|---|
| **Marketing/Sales (inhouse/agent)** | **Sales Home — "Hari Saya"** | Task inbox pribadi, lead/deal saya, komisi & target, appointment, next-best-action | HPP/biaya konstruksi, AP subcon, GL |
| **Marketing Admin / Sales Manager** | **Manager Home — "Performa Tim"** | Distribusi lead, SLA & response-time tim, leaderboard, approval, funnel | biaya konstruksi detail |
| **Finance / Collection** | **Finance Home** | AR aging (pembeli), AP & retensi (subcon), penerimaan hari ini, contract-liability, pajak jatuh tempo | pipeline detail marketing |
| **Project Manager / Site Engineer** | **Project Home** | Progress proyek, termin subcon, QC/inspeksi, change order, foto lapangan | pipeline sales, komisi |
| **Owner / GM / Super Admin** | **Control Tower** | Penjualan hari/MTD, kas & AR/AP, approval pending, progress proyek, revenue diakui vs contract-liability | — (lihat semua) |

**Setiap Home = campuran 3 unsur:**
(a) **KPI strip sadar-peran** (angka miliknya, bukan global), (b) **Work Hub / Task Inbox** ("Hari Saya"), (c) **Quick actions** + **Next-Best-Action cards**.

---

## 3. THE WORK HUB — INTI "SLACK TAPI ERP" (pembeda utama)

Work Hub adalah **lapisan pemandu + kolaborasi** yang menempel pada data ERP. Empat komponen:

### 3.1 Task Inbox ("Hari Saya") — *source of truth for WORK*
- Daftar tugas pribadi: **Jatuh tempo hari ini / Terlambat / Akan datang / Menunggu saya**.
- Setiap task punya: judul, tipe, prioritas, **SLA/countdown**, **related record** (lead/deal/unit/proyek/subcon), tombol **aksi terpandu**.
- Filter: mine/overdue/type/stage. Bulk complete/snooze.
- Task lahir dari **Guided Work Engine** (auto via event) + manual.

### 3.2 Next-Best-Action (NBA) per record — *guided execution*
- Di setiap record (mis. Lead detail), panel **"Langkah Berikutnya"**: 1–3 aksi paling relevan berdasarkan stage + sinyal (mis. "Deal macet 5 hari", "PPJB jatuh tempo H-3", "KPR menunggu dokumen").
- Klik aksi → **guided flow** (form terpandu) → memutasi record + **log activity** + (bila perlu) **majukan stage** + **generate task lanjutan**. Menutup loop *rekomendasi → eksekusi* (pola Einstein NBA).

### 3.3 Activity Feed + Kolaborasi — *source of truth for CONVERSATION*
- Tiap record punya **timeline aktivitas** terpadu: sistem-event (stage change, payment, QC), **komentar manusia**, lampiran, **@mention**, dan **thread** (balasan).
- **@mention** → notifikasi + task ringan "Anda disebут". Mengikuti pola triase feed (news/collaboration/reminders/alerts).
- Ini menggantikan "catatan" pasif SIPRO lama dengan **percakapan kontekstual** pada data.

### 3.4 Channels per proyek/deal — *ruang tim*
- **Channel** ringan per proyek besar / deal penting / tim: aliran diskusi + tugas + dokumen terkait, mirip Slack channel namun **terikat entitas ERP**.
- Notifikasi per-channel (follow/mute), inbox @mention global.

> **Sinergi:** salah satu channel utama adalah **WhatsApp Inbox in-app** yang terhubung ke pelanggan eksternal + capture lead dari iklan. Arsitektur & trigger percakapan→lifecycle dibahas tuntas di **Dok 07 (Omnichannel Lead Engine)**; gambaran produk di **Dok 08 §EPIC 1.7**.

> Fase awal: feed/komentar/@mention/task via **polling + optimistic UI** (murah, andal). **WebSocket real-time** = peningkatan terjadwal (Dok 04).

---

## 4. PROCESS TIMELINE (rantai dokumen lintas-modul)

Di record kunci, tampilkan rantai end-to-end dengan deep-link (menghilangkan IA dead-end):
- **O2C (Sales):** `Lead → Appointment → SPR/BookingFee → PPJB → KPR → (progress) → BAST → AJB → Komisi`.
- **Konstruksi:** `BoQ/RAB → SPK Subcon → Progress/Termin → QC → Change Order → BAST → Retensi rilis`.
- **Finance:** `Deal → Jadwal AR → Penerimaan → ContractLiability → (BAST) RevRec` & `SPK → Termin AP → Retensi → Bayar`.

---

## 5. GUIDED ONBOARDING & TOURS
- **Onboarding checklist** per peran (sekali, bisa di-dismiss) — mengarahkan langkah pertama (mis. sales: "Terima lead pertama → hubungi → buat appointment").
- **Guided Tours** step-by-step (pola `tourDefinitions.js`): "Buat SPR", "Ajukan PPJB", "Input Termin Subcon", "Catat Penerimaan".
- **Empty states yang mengajar** (bukan sekadar "belum ada data", tapi "Buat X pertama Anda" + CTA).

---

## 6. MODEL DOMAIN (koleksi kanonik — calon isi `ENTITY_REGISTRY.md`)

> Semua koleksi: UUID string id, `org_id` (multi-tenant scope), `created_at/updated_at` (UTC ISO), audit di `audit_logs`. Nama kanonik final dikunci saat Fase 0.

### 6.1 Fondasi & lintas-sektor
| Koleksi | Fungsi |
|---|---|
| `orgs` | Tenant/organisasi (multi-tenant scope) |
| `users`, `sessions` | Auth + sesi (Bearer) |
| `permission_settings` | Matriks RBAC per peran/modul/aksi (config) |
| `audit_logs` | Jejak audit semua perubahan |
| `events` | **Domain Event Bus** (sumber pemicu task/notifikasi) |
| `tasks` | **Guided Work Engine** — task persisten (auto/manual) |
| `activities` | **Activity feed** (system-event + komentar + @mention + thread) |
| `channels`, `channel_members`, `messages` | Kolaborasi ala Slack (terikat entitas) |
| `notifications` | Notifikasi in-app (triase) |
| `documents`, `document_templates` | Dokumen legal berantai (SPR/PPJB/BAST/AJB) + template PDF |
| `attachments` | File/foto (object storage) |

### 6.2 Pilar Sales & Marketing
| Koleksi | Fungsi |
|---|---|
| `leads` | Lead + stage lifecycle + assignment + response-time |
| `lead_activities` | (opsional; bisa merge ke `activities`) |
| `appointments` | Survey/meeting + kalender |
| `customers` | Pembeli (identitas, kredit, tim sales) |
| `deals` | Transaksi unit (draft→reserved→booked→active→completed) |
| `reservations` | SPR + booking fee (sub-tahap booking) |
| `financing_apps` | KPR (bank, plafon, DP, tenor, BI check, status, pencairan) |
| `commissions` | Insentif marketing (per-deal, saat lunas/akad) |

### 6.3 Pilar Project / Construction
| Koleksi | Fungsi |
|---|---|
| `projects` | Proyek/cluster |
| `units` | Unit + 3-way status (deal/construction/finance) + koordinat siteplan |
| `siteplan_nodes` | Layout visual (opsional custom) |
| `boq_items` / `rab` | Bill of Quantities / RAB per tipe/blok |
| `subcontractors` | Vendor/subcon (SPK, kontrak, dokumen) |
| `work_packages` | Paket kerja/kontrak subcon per proyek |
| `construction_units` | Progress per unit: `phase(weight) → task(weight)` |
| `progress_claims` | Termin/opname progres subcon |
| `qc_inspections` | Inspeksi QC pass/fail |
| `change_orders` | Variasi/CCO |

### 6.4 Pilar Finance
| Koleksi | Fungsi |
|---|---|
| `ar_schedules` / `ar_invoices` | Jadwal & tagihan pembeli (DP/cicilan/KPR) |
| `receipts` | Penerimaan kas pembeli (apply ke jadwal) |
| `ap_bills` | Tagihan subcon/vendor (dari termin) |
| `retentions` | Retensi ditahan (Retentions Payable) + pelepasan |
| `payments_out` | Pembayaran ke subcon/vendor |
| `contract_liabilities` | Akumulasi penerimaan sebelum BAST |
| `revenue_recognitions` | RevRec di BAST (revenue + COGS) |
| `tax_records` | PPN/BPHTB/PPh (worksheet + dokumen) |
| (future) `accounts`, `journal_entries` | CoA & GL penuh (fase lanjut) |

### 6.5 Guided Work Engine — aturan task otomatis (contoh, idempotent via `source_event`)
| Event | Task ter-generate | Due | Assignee |
|---|---|---|---|
| `lead.created` | Hubungi lead | +1 jam | pemilik lead |
| `lead.stage=nurturing` | Follow-up | +2 hari | pemilik lead |
| `appointment.created` | Siapkan survey | H-1 | pemilik |
| `reservation.created` | Susun PPJB (WAJIB ≤30 hari) | +3 hari | sales+admin |
| `ppjb.signed` | Ajukan/checkup KPR | +2 hari | sales+finance |
| `construction.progress≥20%` | Buka syarat PPJB | — | admin |
| `progress_claim.submitted` | Verifikasi & bayar termin | +3 hari | finance |
| `payment.overdue` | Tindak lanjut penagihan | now | collection |
| `unit.BAST` | Proses AJB + RevRec + rilis retensi jadwal | +7 hari | admin+finance |

---

## 7. ARAH DESIGN SYSTEM (modern SaaS, lebih baik dari `kn`)

> Detail final akan dihasilkan oleh **design_agent** (owner memilih ini). Arah tingkat-tinggi (bukan mengunci warna sepihak):
- **Modern SaaS, light-first, bersih & padat-namun-lapang** (dense tapi breathable), bukan glassmorphism.
- **Sidebar terkelompok config-driven** + **TopBar** (kicker+title+search+notif+profile) + **Work Hub** sebagai landing.
- **Design tokens** rapi (spacing 4pt, radius ramping, elevasi halus, `tabular-nums` untuk angka) — lebih matang dari `kn` (iOS-glass).
- **Kontras AA**, dark-mode-ready, komponen shadcn/ui konsisten, ikon lucide.
- **Pattern library**: MetricCard, StatusPill (kelas `status-*`), DataTable (loading/empty/error), DetailDrawer, Timeline, TaskCard, ActivityItem, NBA card, Stepper (checkout/PPJB), Kanban (pipeline & task board).
- **Testability**: `data-testid` kebab-case di semua elemen interaktif & info kritis.

---

## 8. RINGKAS: KENAPA INI MENJAWAB VISI OWNER
- **Task-based & memandu** → Work Hub (Task Inbox + NBA + guided flows) menggantikan "system of record" pasif.
- **"Slack tapi ERP"** → Activity feed + komentar/@mention/thread + channel yang **terikat data ERP**.
- **IA baik** → flow-based + Role-Home + Process Timeline + progressive disclosure.
- **Kontekstual properti ID** → model domain mencakup SPR/PPJB/BAST/AJB/KPR + subcon/termin/retensi + finance PSAK 72/pajak.
- **Kualitas terjaga** → semua di atas fondasi guardrail (Dok 04), lebih ketat & lengkap dari `kn`.
