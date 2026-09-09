# SIPRO Rebuild — Dokumen 17
# NFR + INTEGRATION & POC PLAN + MVP SLICE + TEST SCENARIOS

> Status: SPESIFIKASI NON-FUNGSIONAL, RENCANA POC, & DEFINISI MVP. Bahasa: Indonesia.
> Keputusan owner terpakai: **spesifikasi seluruh sistem dulu**, **MVP = Sales tipis + Konstruksi tipis**, **WA/Ads simulasi-jujur dulu + POC round-trip**.

---

## 1. NFR (Non-Functional Requirements) — standar lintas fitur (menutup Dok 09 gap #10)
| Area | Standar |
|---|---|
| **Timezone** | Simpan UTC ISO-8601; tampil **WIB (Asia/Jakarta)** di FE (formatter). |
| **Uang** | Integer **IDR** (tanpa float); format `Rp` + `tabular-nums`; pembulatan ke rupiah. |
| **Bahasa** | UI & pesan error **Bahasa Indonesia** baku. |
| **Paginasi** | default limit 50 (max 200) + `total`; list besar wajib paginasi. |
| **Upload/Storage** | Object storage (F7) untuk foto/dokumen; limit ukuran (mis. ≤10MB/foto), tipe divalidasi; simpan `key`+`url`. |
| **Konkurensi** | Booking unit **atomic** (`find_one_and_update`) — wajib POC beban paralel. |
| **Keamanan** | Secret di `.env`/vault (bukan FE/DB mentah); webhook verifikasi signature; RBAC + audit; rate-limit webhook. |
| **Observability** | Log terstruktur (level, request-id); error 5xx ter-log; `health_check` cek isi. |
| **Error handling** | Envelope `{detail}`; jangan bocorkan stack ke user; guard bisnis → 400/409. |
| **Performa** | Index sesuai Dok 11 §H; endpoint list < ~300ms pada data seed. |
| **Seeding** | Seed realistis (1 org, ~8 user tiap peran, 1–3 proyek, unit, lead, deal, dokumen) untuk demo & test; idempotent reset (`seed_reset.sh`). |
| **File size** | jsx ≤500, router .py ≤800, util ≤300, css ≤400 (validate_compliance). |

---

## 2. INTEGRATION & POC PLAN
### 2.1 Integrasi (via integration_playbook_expert_v2 — jangan implement tanpa playbook)
| Integrasi | Kredensial diminta ke owner | Status awal |
|---|---|---|
| WhatsApp Business Cloud API | WABA ID, Phone Number ID, Access Token, App Secret, Verify Token | **SIMULASI dulu** (owner belum punya) |
| Meta Lead Ads + CAPI | Meta App, Page, Lead Access, Access Token, Verify Token, Pixel/Dataset | **SIMULASI dulu** |
| Object storage | (playbook) | aktif sejak awal (foto/dokumen) |
| LLM (NBA/scoring) opsional | Emergent LLM key | tunda (heuristik dulu) |

**Mode simulasi jujur:** `channel_accounts.mode='simulation'` — UI menandai "SIMULASI"; webhook diuji via **payload sampel** (endpoint tetap nyata, dapat menerima POST uji). Saat kredensial tersedia → set `mode='live'` tanpa ubah kontrak.

### 2.2 POC CORE (wajib sebelum bangun luas — workflow "buktikan core dulu")
Satu skrip Python menguji SEKALIGUS:
1. **Event Bus + Scheduler + Guided Work Engine**: seed → emit `lead.created` → pastikan **Task lahir sekali** (idempotent) → jalankan expiry sweeper → deal reserved kadaluarsa → unit balik `available`.
2. **Atomic booking konkuren**: 2 request booking unit sama paralel → **tepat satu** sukses, satu 409.
3. **Automation rule**: emit `message.received` (keyword "harga") → NBA suggestion / task terbuat.
4. **RevRec math**: receipt → contract_liability naik; `unit.bast` → revenue+COGS diakui, contract_liability → 0.
5. **Document + PDF**: buat PPJB dari template (guard prasyarat) → finalize → sign → PDF ter-generate.
6. **WA/Ads webhook (simulasi)**: POST payload sampel → lead/conversation terbuat + task 5-menit.
> DoD POC: semua 6 lulus di DB bersih → baru lanjut membangun UI/fitur luas.

---

## 3. MVP SLICE (irisan pertama shippable — keputusan owner: KEDUANYA)
> Prinsip: tipis tapi **end-to-end** & **membuktikan arsitektur** (Work Hub + event + RBAC + omnichannel-sim + finance-hook). Bukan seluruh fitur.

### Fondasi bersama (wajib untuk kedua slice)
Fase 0 penuh: auth+RBAC (peran: minimal `sales`, `sales_manager/marketing_admin`, `project_manager`, `owner`), nav config-driven + Role-Home shell, Event Bus + Scheduler + Guided Work Engine + Activity layer, design system, guardrail scripts, seed.

### SLICE A — Sales funnel tipis (mesin konversi & guided)
**Alur:** (Ads/WA **simulasi**) capture → **lead** (auto-assign + Task "Hubungi ≤5 mnt") → **Work Hub "Hari Saya"** → **appointment** → **SPR/booking** (unit **atomic** + dokumen **SPR** PDF).
- Cakupan: 1 proyek + unit, peran `sales` + `sales_manager/marketing_admin`.
- Membuktikan: capture→lead→task, Work Hub, NBA, atomic booking, document engine, activity feed, RBAC scope (sales lihat miliknya).

### SLICE B — Konstruksi tipis (anti-kebocoran & deadline)
**Alur:** **proyek → unit** → **construction progress** (weighted + **Kurva-S** plan vs aktual) → **material opname** (requisition→GRN→issue → opname selisih).
- Cakupan: 1 proyek, peran `project_manager` + `site_engineer`.
- Membuktikan: weighted progress+QC (PORT), kurva-S, material ledger+opname (selisih), foto (F7), RBAC scope (assigned project).

### Titik temu (integrasi antar-slice)
Unit yang di-*book* di Slice A → punya `construction_unit` di Slice B; progress di B → memicu milestone (siap untuk KPR/RevRec di fase Finance berikutnya). Membuktikan **3-way sync** unit.

---

## 4. TEST SCENARIOS (Given/When/Then — untuk testing_agent; menutup Dok 09 gap #12)
### Slice A
- **A1 Capture→Task:** *Given* rule capture aktif (simulasi), *When* POST webhook lead sampel, *Then* lead terbuat + ter-assign + **Task "Hubungi ≤5 mnt"** muncul di Work Hub owner (<30 dtk).
- **A2 RBAC scope:** *Given* 2 sales, *When* sales-B GET lead milik sales-A, *Then* 403 / tak tampil.
- **A3 Guided transition:** *When* sales tandai kontak pertama, *Then* stage → nurturing + `response_time_minutes` terisi (sekali) + Task follow-up.
- **A4 Atomic booking:** *When* 2 booking unit sama nyaris bersamaan, *Then* satu sukses, satu 409; unit `booked` sekali.
- **A5 SPR PDF:** *When* buat SPR dari template → finalize → sign, *Then* status `signed` + PDF terunduh + activity ter-log.
- **A6 Empty/loading state:** *Given* belum ada lead, *Then* Work Hub tampil empty-state mendidik (bukan blank).
### Slice B
- **B1 Weighted progress:** *When* update task selesai, *Then* phase.progress & overall terhitung benar (Σ weight) + unit.construction_progress sync.
- **B2 QC hold:** *When* QC fail, *Then* task failed + phase qc_hold + unit qc_hold + event `qc.failed`.
- **B3 Kurva-S:** *Given* rencana vs aktual, *Then* deviasi negatif tampil + Task korektif.
- **B4 Material opname:** *When* input opname fisik < buku, *Then* variance>0 tersorot + audit txn tercatat.
- **B5 RBAC scope:** *When* site_engineer proyek lain akses, *Then* 403.
### Lintas
- **X1 3-way sync:** *When* unit di-book (A) lalu progres (B), *Then* status unit konsisten (deal/construction/payment).
- **X2 Gate hijau:** semua `verify_*` + ux_audit + compliance 0-FAIL di DB bersih.
> Catatan testing_agent: **skip** uji yang butuh kamera/drag-drop/voice; webhook diuji via POST payload (bukan UI eksternal).

---

## 5. URUTAN EKSEKUSI FINAL (setelah spesifikasi lengkap)
1. **Spesifikasi seluruh sistem** (Dok 10–17) — **selesai** (dok ini).
2. **design_agent** → design system.
3. **POC core** (§2.2) → lulus.
4. **Fase 0 Fondasi + MVP Slice A & B** → gate hijau → testing_agent (§4) → DoD.
5. Lebarkan per pilar (Dok 08) → Finance → Pematangan (Portal/WA-live/real-time).
