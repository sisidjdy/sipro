# SIPRO Rebuild — Dokumen 04
# USULAN MASTER ROADMAP: FONDASI + EPIC + RENCANA GUARDRAIL

> Status: PLAN (diperbarui dgn keputusan owner). Bahasa: Indonesia.
> **UPDATE keputusan owner:** (1) **Spesifikasi lengkap seluruh sistem dibuat dulu** (Dok 10–17) sebelum kode. (2) Urutan: Spec → **POC core** (Dok 17 §2.2) → **Fase 0 Fondasi + MVP Slice A (Sales tipis) & B (Konstruksi tipis)** (Dok 17 §3) → lebarkan per pilar. (3) **Adopsi kode SIPROnext** (Dok 10) untuk minimalisir kerugian. (4) WA/Ads **simulasi-jujur dulu**.
> Aturan emas (diadopsi & ditingkatkan dari `kn`): **KODE MENANG atas DOKUMEN**, verifikasi di DB bersih, **"200/running ≠ benar"**, guardrail tumbuh bersama fitur, **dilarang klaim hijau palsu**.

---

## 0. FILOSOFI EKSEKUSI

> "Bangun fondasi & guardrail dulu → buktikan tiap fase lewat GATE + testing_agent → baru fase berikut."

Urutan makro: **Fase 0 (Fondasi)** → **Pilar 1: Sales/CRM + Work Hub** → **Pilar 2: Konstruksi/Subcon** → **Pilar 3: Finance** → **Pematangan** (portal pembeli, integrasi WA, real-time, GL, multi-tenant UI). Sales-first karena UX task-based paling kritis di sana & memvalidasi Work Hub untuk pilar lain.

---

## 1. FASE 0 — FONDASI (yang akan dibangun begitu owner ACC)

Fase 0 **tidak membangun fitur bisnis**; ia membangun **kerangka + guardrail + disiplin** agar fase fitur tidak gagal seperti sistem lama. Terbagi:

### 1.1 Dokumen SSOT (meniru `kn`, ditingkatkan)
- `memory/ENGINEERING_GUARDRAILS.md` — RC taxonomy (RC-1..RC-n) **+ RC RBAC + RC tenant-scope + RC referential-integrity** (tambahan kita), 3-Gate, DoD, escalation.
- `memory/FRONTEND_GUARDRAILS.md` — kontrak API FE, UX, testability, nav config-driven, batas ukuran file.
- `docs/UX_USABILITY_STANDARD.md` — diperkuat: Work Hub/Task/Activity punya standar sendiri.
- `CODEBASE_MAP.md` — peta file+endpoint (hidup).
- `ENTITY_REGISTRY.md` — SSOT koleksi/skema/invarian (dari Dok 03 §6).
- `MASTER_ROADMAP.md` (final), `plan.md` (fase berjalan), `SESSION_HANDOFF.md`.
- `docs/RBAC_MATRIX.md` — matriks izin peran×modul×aksi (SSOT RBAC).

### 1.2 Guardrail eksekutabel (scripts/ — gate yang bisa GAGAL)
Adopsi dari `kn` + **tambahan khusus SIPRO**:
| Script | Fungsi | Baru vs kn? |
|---|---|---|
| `seed_reset.sh` | reset DB bersih + jalankan gate | adopsi |
| `load_context.sh` | snapshot service/env/DB/file-size | adopsi |
| `verify_contract.py` | nama koleksi kanonik | adopsi |
| `verify_api_contract.py` | dup route / FE→route / FE field⊆BE | adopsi |
| `verify_data_integrity.py` | invarian data (unit status, AR/AP, contract-liability, progress weight) | adopsi+perluas |
| `health_check.py` | isi endpoint kritis | adopsi |
| `audit_endpoint_sweep.py` | sweep GET /api → 5xx | adopsi |
| `ux_audit.py` | baseline UX (loading/empty/error + testid + tabular-nums) | adopsi |
| `check_nav_map.py` | nav id → route + PAGE_META | adopsi |
| `validate_compliance.py` | batas ukuran file & naming | adopsi |
| **`verify_rbac.py`** | **setiap endpoint sensitif punya guard izin; peta izin FE≡BE** | **BARU (perbaikan #1 SIPRO)** |
| **`verify_tenant_scope.py`** | **setiap query koleksi ber-scope `org_id`** | **BARU (multi-tenant-ready)** |
| **`verify_referential_integrity.py`** | **FK string (lead→deal→unit→project) tak yatim** | **BARU** |

### 1.3 Kerangka kode (skeleton, tanpa fitur bisnis)
- **Backend**: app factory + lifespan + router registry; `core_utils` (`now_iso/new_id/safe_doc/hash`), `dependencies` (`current_user/require_role/require_permission/audit/tenant_scope`), `permissions_config`, **event bus** (`events` + dispatcher), **Guided Work Engine** (task generator hook), **Activity service** (feed/comment/@mention).
- **Frontend**: `App.js` (state+view routing), `config/navigationConfig.js` (PAGE_META/NAV_STRUCTURE/ROLE_HOME_REGISTRY/GUIDANCE_MAP), `services/apiClient.js`, `hooks/useAppActions.js`, `utils/formatters.js`, **Work Hub shell** (Task Inbox + Activity + NBA komponen), design tokens.
- **Auth + RBAC** end-to-end + seed peran + **login bypass test** (untuk testing_agent) + `memory/test_credentials.md`.
- **Design system** (dari design_agent) diterapkan di shell.

### 1.4 DoD Fase 0
Semua gate hijau di DB bersih; login+RBAC 4 peran jalan; Work Hub shell tampil (kosong tapi benar loading/empty); CODEBASE_MAP/ENTITY_REGISTRY/plan terisi; testing_agent smoke (login+nav+RBAC) lulus.

---

## 2. FOUNDATIONS LINTAS-SEKTOR (BUILD ONCE) — dipakai semua EPIC

| ID | Fondasi | Mengaktifkan |
|---|---|---|
| **F1** | **RBAC + Permission Matrix (config)** | semua |
| **F2** | **Multi-tenant scope (`org_id`) + helper + gate** | semua |
| **F3** | **Domain Event Bus** (`events` + dispatcher) | Work Engine, notifikasi, timeline |
| **F4** | **Guided Work Engine** (task auto/manual + SLA) | Work Hub, NBA |
| **F5** | **Activity & Collaboration** (feed, komentar, @mention, thread, channel) | semua record |
| **F6** | **Document engine** (template + PDF + e-sign/upload) untuk SPR/PPJB/BAST/AJB | Sales, Legal |
| **F7** | **Object storage** (foto/berkas) | Konstruksi, dokumen, KYC |
| **F8** | **Money/finance primitives** (currency IDR, contract-liability, AR/AP ledger) | Finance |
| **F9** | **Process Timeline / Document Relations** | navigasi lintas-modul |
| **F10** | **Notification + preference** (in-app; email/WA menyusul) | semua |

---

## 3. EPIC & FASE (usulan)

### PILAR 1 — SALES/CRM + WORK HUB (tulang punggung UX)
- **EPIC 1.0 — Role-Home + Work Hub shell** (F3,F4,F5): Sales/Manager/Finance/Project/Owner home; Task Inbox "Hari Saya"; Activity feed + komentar/@mention; NBA cards. *DoD: tiap peran punya landing relevan + task inbox jalan.*
- **EPIC 1.1 — Lead Lifecycle** (panen SIPRO): capture (manual/CSV/ads-UI), assignment (manual+load-balanced), stage engine (`acquisition→nurturing→appointment→booking→recycle`), response-time SLA, timeline, lead scoring.
- **EPIC 1.2 — Appointment & Survey** + kalender + validasi survey (foto/checklist via F7).
- **EPIC 1.3 — Reservasi (SPR) + Booking Fee** (F6): sub-tahap booking + unit atomic hold + expiry + dokumen SPR.
- **EPIC 1.4 — PPJB workflow** (F6,F9): prasyarat (progress≥20% + review 7 hari + ≤30 hari), template PDF, jadwal pembayaran mulai.
- **EPIC 1.5 — KPR/Financing** : bank, plafon, DP, tenor, BI check, status, pencairan bertahap (kait milestone).
- **EPIC 1.6 — Komisi/Insentif** : per-deal, diakui saat lunas/akad, tim sales/agen; Sales Home breakdown.

### PILAR 2 — PROJECT / CONSTRUCTION (subcon)
- **EPIC 2.0 — Projects & Units** (panen): generate-units, siteplan 4-view, 3-way status sync + invarian gate.
- **EPIC 2.1 — BoQ/RAB** per tipe/blok + cost code.
- **EPIC 2.2 — Subkontraktor & SPK** (entity + kontrak + dokumen via F7).
- **EPIC 2.3 — Progress & Termin** : weighted phase/task (panen) + progress claim/opname + change order.
- **EPIC 2.4 — QC/Inspeksi** (panen) + foto + qc_hold.
- **EPIC 2.5 — Retensi** : tahan/rilis (kait ke AP di Finance).

### PILAR 3 — FINANCE (PSAK 72 + pajak)
- **EPIC 3.0 — AR pembeli** (F8): jadwal DP/cicilan/KPR + penerimaan + aging + denda + contract-liability.
- **EPIC 3.1 — AP subcon** (F8): tagihan dari termin + retensi + pembayaran + aging.
- **EPIC 3.2 — Revenue Recognition** : trigger BAST → akui revenue+COGS; contract-liability release.
- **EPIC 3.3 — Pajak** : PPN/BPHTB/PPh worksheet + dokumen.
- **EPIC 3.4 (future) — CoA/GL** penuh + jurnal + laporan.

### PEMATANGAN
- **EPIC M1 — Customer Portal** (pembeli lihat status unit/pembayaran/progres).
- **EPIC M2 — WhatsApp Business API** (nyata) + email notifikasi.
- **EPIC M3 — Real-time** (WebSocket) untuk feed/task/notif.
- **EPIC M4 — Multi-tenant UI** (org switch, onboarding tenant).
- **EPIC M5 — BI dashboards** (sales/finance/project) + laporan PDF.

---

### 3b. EPIC TAMBAHAN DARI ANALISIS PAIN-POINT (Dok 05/06) \u2014 outcome-driven\n> Ditambahkan setelah riset pain-point lapangan; disisipkan ke pilar terkait sesuai prioritas dampak\u00d7risiko.\n- **EPIC 2.6 \u2014 Material Ledger + Stock Opname (ANTI-KEBOCORAN)**: requisition \u2192 GRN \u2192 issue-ke-task \u2192 stok site; opname terjadwal (fisik vs buku); alert permintaan > BoQ (MRP); akses/approval berjenjang; QR/label opsional. *Outcome: selisih opname \u2192 0, wastage \u2193.*\n- **EPIC 2.7 \u2014 Permit/Document Tracker + Kurva-S (JAGA DEADLINE)**: tracker izin/dokumen (KRK/IMB/PBG/addendum) dengan deadline+reminder+eskalasi; kurva-S rencana vs aktual + deteksi deviasi \u2192 task korektif. *Outcome: dokumen telat \u2193, on-time \u2191.*\n- **EPIC 2.8 \u2014 Daily Log / Site Diary + Punch List (mobile)**: catatan harian (progres/tenaga/cuaca/foto); punch/snag/defect foto ber-lokasi + assign + close-out; audit-ready. *Outcome: rework \u2193, defect closed sebelum BAST.*\n- **EPIC 3.5 \u2014 Cash-Flow Projection + Collection Worklist (ARUS KAS)**: proyeksi kas (AR masuk vs AP+termin keluar) + runway; worklist penagihan + reminder + denda. *Outcome: proyek mangkrak akibat cash \u2193, DSO \u2193.*\n- **EPIC 3.6 \u2014 Anti-Fraud Controls**: approval berjenjang + 3-way match (PO\u2192GRN\u2192tagihan) + jejak audit + segregation via RBAC. *Outcome: anomali terdeteksi, audit-ready.*\n- **EPIC M1 \u2014 Customer Portal DINAIKKAN prioritasnya** (dari \"pematangan\" \u2192 setelah P1/P2 inti): transparansi progres/pembayaran/dokumen + kanal komplain SLA. *Outcome: kepercayaan \u2191, ketepatan bayar \u2191, referral \u2191, sengketa serah-terima \u2193.*\n\n## 4. DEPENDENCY GRAPH (ringkas)
```
Fase 0 (fondasi + gates + RBAC + design)
   └─ F1..F10
        ├─ PILAR 1 (EPIC 1.0 Work Hub → 1.1 → 1.2 → 1.3 → 1.4 → 1.5 → 1.6)
        ├─ PILAR 2 (2.0 → 2.1 → 2.2 → 2.3 → 2.4 → 2.5)   [butuh F5,F7]
        └─ PILAR 3 (3.0/3.1 → 3.2 → 3.3 → 3.4)            [butuh F8; 3.2 butuh BAST dari P2 & PPJB dari P1]
Pematangan (M1..M5) setelah pilar inti hijau
```
Keterkaitan penting: **RevRec (3.2)** butuh **BAST (P2)** + **deal/PPJB (P1)**; **KPR pencairan (1.5)** butuh **progress milestone (P2)**; **komisi (1.6)** butuh **lunas/akad (P1/P3)**.

---

## 5. "LEBIH BAIK DARI `kn`" — KONKRET
1. **RBAC ditegakkan sejak Fase 0** + `verify_rbac.py` (kn & SIPRO lama lemah di sini).
2. **Multi-tenant-ready by default** (`org_id` + `verify_tenant_scope.py`).
3. **Guided Work Engine + Event Bus + Activity/Collaboration** sebagai fondasi first-class (kn tak punya; SIPRO menempel telat).
4. **Referential integrity gate** (`verify_referential_integrity.py`).
5. **Domain properti ID lengkap** (legal berantai + KPR + subcon/retensi + PSAK 72/pajak) — di luar cakupan kn.
6. **Design system modern-SaaS** lebih matang dari iOS-glass kn (via design_agent).
7. **Customer Portal + WA nyata + real-time** sebagai jalur pematangan yang direncanakan sejak awal.

---

## 6. DEFINITION OF DONE (per fase, wajib)
1. Gate A–C hijau di **DB bersih** (`seed_reset.sh` + semua verify_* + ux_audit + compliance + nav).
2. **0 5xx** pada sweep endpoint; invarian data valid.
3. **Frontend mencerminkan 100% backend** (tak ada endpoint yatim).
4. **RBAC & tenant-scope** teruji untuk fitur terkait.
5. **testing_agent_v3** lulus semua user story fase + 0 regresi.
6. Docs diperbarui (CODEBASE_MAP, ENTITY_REGISTRY, plan.md, SESSION_HANDOFF).
7. Bila ada yang belum beres → **dilaporkan jujur** (bukan diklaim hijau).

---

## 7. GOVERNANCE & KEBIASAAN SESI
- Tiap awal sesi: `bash scripts/load_context.sh` + baca Tier-0 (guardrails+map+plan fase berjalan).
- Tambah fitur ⇒ tambah koleksi ke `ENTITY_REGISTRY` + `verify_contract` + invarian + endpoint kritis + RBAC entry.
- Batas ukuran file NON-NEGOTIABLE (jsx ≤500, router .py ≤800, util .js ≤300, css ≤400).
- Integrasi pihak-3 (WA, e-sign, bank, storage, LLM) → lewat integration_playbook_expert_v2 + kredensial di `.env`.

---

## 8. KEPUTUSAN YANG DIBUTUHKAN SEBELUM MULAI FONDASI (Fase 0)
1. **ACC arah plan ini** (fondasi dulu, Sales/CRM+Work Hub sebagai pilar-1).
2. **Nama produk & tenant awal** (mis. "SIPRO" + nama developer) untuk seed.
3. **Peran final** (setuju set: Sales, Marketing Admin/Manager, Finance/Collection, Project/Site, Owner/Admin?).
4. **Design**: lanjut panggil **design_agent** untuk blueprint UI/UX modern-SaaS (owner sudah setuju arah ini)?
5. **Integrasi yang ingin nyata sejak awal** vs ditunda (WA Business API, e-sign, object storage, LLM untuk NBA/scoring).
