# SIPRO Rebuild — Dokumen 08
# MASTER IMPLEMENTATION PLAN & PRODUCT VISION (detail: cara implementasi + gambaran produk)

> Status: PLAN DETAIL (pusat framework; diperbarui dgn keputusan owner). Bahasa: Indonesia.
> **UPDATE:** eksekusi mengikuti Dok 17 — Spesifikasi lengkap (Dok 10–17) → POC core → Fase 0 + **MVP Slice A (Sales tipis) & B (Konstruksi tipis)** → lebarkan. Logika di-**PORT dari SIPROnext** sesuai **Dok 10 (Adoption Map)**. Skema/kontrak mengacu Dok 11/12/16; engine Dok 13; RBAC Dok 14; finance Dok 15.
> Cara pakai: dokumen ini = **HOW & WHAT** (gambaran produk + cara implementasi). Untuk **WHY/root-cause**, tiap bagian menautkan ke Dok 01/02/05/06/07. Untuk **fondasi/guardrail**, lihat Dok 04. Untuk **IA/Work Hub/domain**, lihat Dok 03.
> Format tiap EPIC: **(a) Root-cause ref → (b) Gambaran Produk (layar/alur/state) → (c) Implementasi (data, endpoint, service, event) → (d) Guardrail → (e) DoD/KPI.**

---

## 0. PRODUCT VISION — "SATU LAYAR KERJA YANG MEMANDU" (gambaran besar)

**Kalimat produk:** *SIPRO adalah ERP properti berbasis-task yang memandu — membuka aplikasi = melihat "Hari Saya" (apa yang harus dikerjakan sekarang), bukan menu modul. Setiap pekerjaan dikerjakan di tempat datanya, dengan percakapan (WA/komentar) menempel pada record, dan setiap langkah otomatis memajukan proses bisnis.*

**Rasa produk (feel):**
- Buka app → **Role-Home** (Sales/Manager/Finance/Project/Owner) dengan **KPI strip** + **Work Hub "Hari Saya"** + **Next-Best-Action**.
- Klik task → langsung ke **record + guided action** (form terpandu) → selesai → stage maju + activity ter-log + task berikutnya lahir.
- **WA masuk** → muncul di **Inbox in-app** + jadi **lead** + task "Hubungi ≤5 menit".
- **Lead ads** → otomatis masuk <30 detik + ter-assign + task.
- Layar padat-informasi tapi lapang; angka `tabular-nums`; status pakai pill; loading/empty/error jujur; **mobile-first** untuk sales & site.

**3 lapisan framework dokumen (sinergi):**
```
WHY  (root cause / kebutuhan)  → Dok 01,02,05,06,07  (acuan saat butuh detail)
WHAT (produk & arsitektur)     → Dok 03 (IA/WorkHub/domain) + 08 (§gambaran produk)
HOW  (eksekusi & mutu)         → Dok 04 (fondasi/guardrail/roadmap) + 08 (§implementasi) + plan.md
```

---

## 1. FASE 0 — FONDASI (detail; belum fitur bisnis)

**Root-cause ref:** Dok 01 §1.3 (S2 RBAC, S6 tanpa guardrail, S7 monolit), Dok 04 §1.

**Gambaran produk (yang terlihat di akhir Fase 0):**
- Halaman **Login** (email/password) + seed 5 peran + **login-bypass test** (untuk testing_agent).
- **App shell**: Sidebar config-driven (grup + item + "Segera Hadir"), TopBar (kicker+judul+search+notif+profil), area konten.
- **Role-Home kosong-tapi-benar** (loading/empty state), **Work Hub shell** (Task Inbox kosong, Activity kosong) — belum ada data bisnis.
- Toggle peran menunjukkan **IA & menu berubah per peran** (bukti RBAC/role-home hidup).

**Implementasi:**
- **Backend**: app factory + lifespan + router-registry; `core_utils` (`now_iso/new_id/serialize_doc/hash`); `dependencies` (`current_user`, `require_role`, `require_permission`, `audit`, `tenant_scope`); `permissions_config` (matriks RBAC); **event bus** (`events` + dispatcher stub); **Guided Work Engine** (generator task + `source_event` idempotent); **Activity service** (create/list activity, comment, @mention). Auth JWT/bcrypt (panen SIPRO) + RBAC guard.
- **Frontend**: `App.js` (state + view routing, bukan hanya path); `config/navigationConfig.js` (`PAGE_META`, `NAV_STRUCTURE`, `buildNavGroups(role)`, `ROLE_HOME_REGISTRY`, `GUIDANCE_MAP`, `resolveActiveNavId`); `services/apiClient.js` (axios + `REACT_APP_BACKEND_URL` + `/api`); `hooks/useAppActions.js`; `utils/formatters.js` (IDR, tanggal ID, tabular); **Work Hub shell** komponen (TaskInbox, ActivityFeed, NBAcard) + design tokens (dari design_agent).
- **Data awal**: `orgs`, `users`, `permission_settings`, `audit_logs`, `events`, `tasks`, `activities`, `notifications` (kosong/seed minimal).
- **Scripts**: `seed_reset.sh`, `load_context.sh`, `verify_contract.py`, `verify_api_contract.py`, `verify_rbac.py`, `verify_tenant_scope.py`, `verify_referential_integrity.py`, `verify_data_integrity.py`, `health_check.py`, `audit_endpoint_sweep.py`, `ux_audit.py`, `check_nav_map.py`, `validate_compliance.py`.
- **Docs**: `ENGINEERING_GUARDRAILS`, `FRONTEND_GUARDRAILS`, `UX_USABILITY_STANDARD`, `RBAC_MATRIX`, `CODEBASE_MAP`, `ENTITY_REGISTRY`, `SESSION_HANDOFF`, `test_credentials.md`.

**Guardrail:** semua gate hijau di DB bersih; batas ukuran file berlaku.
**DoD:** login + RBAC 4–5 peran; Role-Home & Work Hub shell tampil benar; semua gate 0-FAIL; testing_agent smoke (login+nav+RBAC) lulus; docs terisi.

---

## 2. PILAR 1 — SALES/CRM + WORK HUB + OMNICHANNEL (tulang punggung UX)

### EPIC 1.0 — Role-Home + Work Hub
**(a) Root-cause:** Dok 05 SL-5 (system pasif), Dok 03 §2–3, Dok 06 P1–P5.
**(b) Gambaran produk:**
- **Sales Home "Hari Saya"**: KPI strip (lead baru, follow-up due, appointment hari ini, deal aktif, komisi MTD); **Task Inbox** (Terlambat / Hari ini / Akan datang / Menunggu saya) dengan **SLA countdown**; **NBA cards** ("3 lead belum dihubungi", "PPJB H-3"); Quick actions.
- **TaskCard**: judul + tipe + prioritas + related-record chip + tombol **aksi terpandu** (buka drawer form).
- **Activity feed** global + per-record: system-event + komentar + **@mention** + thread.
**(c) Implementasi:** `tasks` (status/priority/due/sla/source_event/related), `activities` (kind, actor, body, mentions[], parent_id); endpoints `GET /api/work/tasks` (filter mine/overdue/type), `POST /api/work/tasks/{id}/complete|snooze`, `GET/POST /api/activities`, `POST /api/activities/{id}/comment`; **Guided Work Engine** menghasilkan task dari event; NBA = resolver berbasis stage+sinyal (heuristik dulu; LLM opsional kelak).
**(d) Guardrail:** ux_audit (loading/empty/error di inbox), verify_rbac (task hanya milik/rentang peran), verify_api_contract.
**(e) DoD/KPI:** tiap peran punya Home relevan; task lahir dari event & bisa diselesaikan; aktivitas/hari terukur.

### EPIC 1.1 — Lead Lifecycle (panen SIPRO)
**(a) Root-cause:** Dok 01 §1.2 (lifecycle matang), Dok 05 SL-2/SL-3.
**(b) Gambaran produk:**
- **Pipeline board** (Kanban: acquisition→nurturing→appointment→booking→recycle) drag-drop + list view + filter.
- **Lead detail**: header (nama/phone/sumber/skor) + **Process Timeline** + tab **Aktivitas/Chat** + **panel NBA** + tombol "Buat appointment/SPR".
- **Assignment**: manual + auto (load-balanced) + accept/reject; **response-time badge**.
**(c) Implementasi:** `leads` (stage, owner, source+attribution, score, response_time, first_contacted_at, assignment_history), transisi terkontrol + emit `lead.stage:*` events; endpoints CRUD + `POST /api/leads/{id}/assign|accept|advance`; import CSV.
**(d) Guardrail:** verify_data_integrity (invarian transisi & no orphan), verify_referential_integrity (lead↔owner/project).
**(e) DoD/KPI:** transisi hanya lewat aturan; response-time terhitung idempotent; 0 lead tanpa owner.

### EPIC 1.7 — Omnichannel & Conversational Engine (lihat Dok 07 lengkap)
**(a) Root-cause:** Dok 07 (seluruh), Dok 05 SL-1/SL-2.
**(b) Gambaran produk:**
- **Ads capture**: Settings › Integrasi (hubungkan Meta/Google/TikTok/web form, map field, uji lead) → lead masuk **<30 dtk** + auto-assign + task "Hubungi ≤5 mnt".
- **WhatsApp Inbox in-app**: daftar percakapan | thread chat (bubble in/out, status, media, **badge window 24j**) | panel konteks record (stage, NBA, tombol majukan) + catatan internal + @mention.
- **Automation Rules editor**: trigger (pesan masuk/keyword/no-response) → kondisi → aksi (buat/majukan lead, task, kirim template).
**(c) Implementasi:** koleksi `channel_accounts/conversations/messages/wa_templates/automation_rules/lead_capture_events`; endpoints webhook (`POST /api/webhooks/leads/{provider}`, `POST/GET /api/webhooks/whatsapp`), inbox (`/api/inbox/*`), rules (`/api/automation-rules`); event `lead.captured/message.received/keyword.matched` → Guided Work Engine; **integrasi via integration_playbook_expert_v2** (WA Cloud API + Meta Lead Ads/CAPI), kredensial `.env`; **mode simulasi jujur** bila kredensial belum ada (ditandai "SIMULASI").
**(d) Guardrail:** verifikasi signature webhook, idempotency, verify_tenant_scope, ux_audit inbox.
**(e) DoD/KPI:** lead ads → CRM <30 dtk + task 5-mnt; WA inbound tampil di inbox & jadi activity; ≥1 automation rule nyata (bukan simulate manual).

### EPIC 1.2 Appointment/Survey · 1.3 SPR+Booking Fee · 1.4 PPJB · 1.5 KPR/Financing · 1.6 Komisi
> Detail ringkas (pola sama; root-cause di Dok 02 §A1, Dok 05 §1).
- **1.3 SPR/Booking**: reservasi + **unit atomic hold** (find_one_and_update) + expiry; dokumen SPR (F6); *cegah double-booking (SL-3)*.
- **1.4 PPJB**: prasyarat (progress≥20% + review 7 hari + wajib ≤30 hari) sebagai **gate + Task + reminder**; template PDF; mulai jadwal AR. *Gambaran: stepper PPJB dengan checklist prasyarat.*
- **1.5 KPR**: `financing_apps` (bank, plafon, DP, tenor, BI-check checklist, status, **pencairan bertahap** terkait milestone konstruksi); *pra-skrining SLIK/DP saat nurturing (SL-4)*.
- **1.6 Komisi**: `commissions` per-deal, diakui saat lunas/akad; breakdown di Sales Home; *anti-dispute (SL-6)*.

---

## 3. PILAR 2 — PROJECT / CONSTRUCTION (subcon) — cegah kebocoran & jaga deadline

### EPIC 2.0 Projects & Units (panen) · 2.1 BoQ/RAB · 2.2 Subcon & SPK · 2.3 Progress+Termin+Kurva-S · 2.4 QC/Punch · 2.5 Retensi · 2.6 Material Ledger+Opname · 2.7 Permit/Doc Tracker · 2.8 Daily Log
**(a) Root-cause:** Dok 02 §A2, Dok 05 §2, Dok 06 §2.2.
**(b) Gambaran produk:**
- **Project Home**: **Kurva-S** (rencana vs aktual) + deviasi; kartu proyek (progress %, termin due, defect open, material alert).
- **Unit/siteplan**: grid unit + status (available/reserved/booked/sold + construction + finance) 3-way sync.
- **Material**: layar **requisition → GRN (terima) → issue ke task → stok site**; **Stock Opname** (input fisik → selisih vs buku → sorot merah); alert "permintaan > BoQ".
- **QC/Punch list**: daftar defect dengan **foto ber-lokasi** + assign + status close; **daily log** (progres/tenaga/cuaca/foto) mobile.
- **Termin subcon**: opname progres → progress claim → (gate QC) → tagih (AP) → **retensi ditahan**.
**(c) Implementasi:** koleksi `projects/units/boq_items/subcontractors/work_packages/construction_units(phase→task weight)/progress_claims/qc_inspections/change_orders/materials/material_txns/stock_opname/retentions/permits`; weighted progress (panen); event `construction.progress≥20% / progress_claim.submitted / unit.BAST`; **3-way match** (PO→GRN→bill); object storage (F7) untuk foto.
**(d) Guardrail:** verify_data_integrity (progress weight=100%, opname konsisten, no orphan unit), audit trail material.
**(e) DoD/KPI:** selisih opname→0; deviasi kurva-S terdeteksi; termin hanya setelah QC pass; retensi tercatat & terjadwal lepas.

---

## 4. PILAR 3 — FINANCE (PSAK 72 + pajak) — arus kas, tertib bayar, anti-fraud

### EPIC 3.0 AR · 3.1 AP+Retensi · 3.2 Revenue Recognition · 3.3 Pajak · 3.5 Cash-Flow+Collection · 3.6 Anti-Fraud
**(a) Root-cause:** Dok 02 §A3 (PSAK 72), Dok 05 §3.
**(b) Gambaran produk:**
- **Finance Home**: **AR aging** (buckets), **cash-flow projection** (AR masuk vs AP+termin keluar → runway), contract-liability vs revenue diakui, pajak jatuh tempo.
- **Collection worklist**: daftar tagihan overdue + reminder + denda + catat penerimaan.
- **AP subcon**: tagihan dari termin + retensi + jadwal bayar + aging.
- **RevRec**: saat **BAST** → tombol/otomasi akui revenue+COGS; contract-liability release.
**(c) Implementasi:** koleksi `ar_schedules/ar_invoices/receipts/ap_bills/retentions/payments_out/contract_liabilities/revenue_recognitions/tax_records`; penerimaan auto-apply ke jadwal & update unit payment_status (panen); event `payment.overdue/unit.BAST`; approval berjenjang + 3-way match (anti-fraud); (future) `accounts/journal_entries` GL.
**(d) Guardrail:** verify_data_integrity (DP/termin=contract-liability; revenue hanya di BAST; AP=termin−retensi), RBAC segregation.
**(e) DoD/KPI:** DSO/overdue turun; pengakuan pendapatan sesuai PSAK 72; cash-flow projection akurat; anomali terdeteksi.

---

## 5. PEMATANGAN

- **M1 Customer Portal (prioritas dinaikkan)**: pembeli lihat progres (kurva-S/%/foto), jadwal & status pembayaran, status dokumen (PPJB/AJB/sertifikat), **kanal komplain + SLA**. *Root-cause: Dok 05 §4, Dok 06 P6 — kepercayaan & ketepatan bayar.*
- **M2 WhatsApp/Email nyata penuh** (bila belum di 1.7) + broadcast + CAPI feedback loop.
- **M3 Real-time (WebSocket)** untuk inbox/feed/task/notif (awalnya polling+optimistic).
- **M4 Multi-tenant UI** (switch org, onboarding tenant).
- **M5 BI dashboards & laporan PDF** (sales/finance/project) + analitik ROI iklan.

---

## 6. URUTAN EKSEKUSI & GERBANG ANTAR-FASE

```
Fase 0 Fondasi  ──✔ gate──▶  P1: 1.0 WorkHub → 1.1 Lead → 1.7 Omnichannel → 1.2→1.6
                                   │ (P1 memvalidasi Work Hub utk semua pilar)
                                   ├──▶ P2: 2.0→2.1→2.2→2.3(+Kurva-S)→2.4→2.5→2.6→2.7→2.8
                                   └──▶ P3: 3.0/3.1→3.2(RevRec@BAST)→3.3→3.5→3.6
                                        Pematangan: M1(Portal)→M2→M3→M4→M5
```
Gerbang: **tiap EPIC selesai = DoD terpenuhi + gate hijau + testing_agent lulus**, baru lanjut. Tak ada klaim hijau palsu (RC-10).

---

## 7. TRACEABILITY (ringkas; matriks penuh di 00_README_INDEX)
Setiap EPIC di atas tertaut ke: **Outcome bisnis (Dok 05 §0)** ↔ **Pain (Dok 05/07)** ↔ **Capability (Dok 03/07)** ↔ **Entity (Dok 03 §6 + 07 §E)** ↔ **Guardrail (Dok 04 §1.2)**. Inilah yang membuat dokumen **saling mengunci** menjadi satu framework, bukan berdiri sendiri.

## 8. CATATAN IMPLEMENTASI LINTAS-EPIC
- **Config-driven** (nav, permission, automation rules, home) — hindari hardcode.
- **Idempotent** (source_event) untuk semua auto-generation.
- **Mobile-first** untuk P1 (sales) & P2 (site).
- **Integrasi** selalu via integration_playbook_expert_v2 + kredensial `.env`; **mode simulasi ditandai jujur** bila belum ada kredensial.
- **Panen kode SIPRO** (lifecycle, atomic booking, weighted progress) di-port ke service + ditambah gate.
