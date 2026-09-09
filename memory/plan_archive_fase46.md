# Rencana Development SIPRO — Fase 46 (Konsolidasi Proyek & Konstruksi — unit-centric hub)

Problem statement (verbatim):
> "saya ingin anda lanjutkan development dari repo ini https://github.com/useeeawa/sipro — sebelumnya development berhenti disini saya ingin anda lanjutkan" (berhenti setelah Fase 45 lulus uji)

Konteks terverifikasi:
- App hidup (backend+frontend), seed OK, `run_all_gates.sh` **PASS (29 gates)**.
- Tidak boleh tambah pintu sidebar baru → semua masuk **hub `/build`**.
- Gerbang **Mulai Bangun = peringatan** (default konfigurasi harus MATI/False), dan bila admin menyalakan barulah memblokir.

---

## 1) Objectives
1. Jadikan konstruksi **unit-centric**: Papan Unit (tabel) → Unit 360 (tab Pembangunan) → aksi kerja nyata berbukti.
2. Konsolidasikan UI `/build` menjadi **6 tab** tanpa kehilangan fitur lama (yang sudah ada tetap reachable, rute lama tetap hidup).
3. Implement **Papan Unit per-UNIT** (bukan per jadwal) dengan angka yang bisa direkonstruksi + tie-out ke engine yang sudah ada.
4. Implement **Readiness “Mulai Bangun”** (DP + izin) dengan mode default **PERINGATAN** + jejak audit/aktivitas.
5. Naikkan `permits` menjadi **bertingkat** (scope project/cluster/block/unit) + expiry/reminder, dan tampilkan coverage di Unit/Project.

---

## 2) Implementation Steps

### FASE 1 — POC Core (isolasi, WAJIB sebelum UI besar)
**Output:** `poc/poc_46.py` hijau (exit 0) membuktikan matematik papan unit + readiness + permit chain.

User stories (POC):
1. Sebagai PM, saya bisa menghitung **baris papan unit** (actual/planned/deviation/next_step) yang konsisten dengan data build mentah.
2. Sebagai auditor, unit tanpa jadwal menghasilkan **planned=null, deviation=null** + `missing[]` (bukan 0).
3. Sebagai owner, saya bisa melihat evaluator **Mulai Bangun** memberi status *warning* dengan alasan DP/izin.
4. Sebagai admin legal, izin bertingkat (project→cluster→block→unit) ter-resolve untuk satu unit secara deterministik.
5. Sebagai maintainer, tie-out memastikan **tidak ada dua kebenaran** antara papan unit dan `build_monitor`/`build_engine`.

Langkah:
- P1. Buat `poc/poc_46.py`:
  - Ambil 3 unit: (a) punya schedule, (b) tanpa schedule, (c) schedule on_hold.
  - Hitung row papan unit per unit: `actual_progress`, `planned_progress` (atau null), `deviation_days`, `days_late`, `next_item{name, due, assigned_to}`, `last_evidence{verified_at, photo_count}`.
  - **Tie-out**: untuk unit yang punya schedule, row harus konsisten dengan `build_monitor.timeline()` + `build_items` (Σ bobot done, gate_reasons, dsb).
  - Readiness evaluator: deteksi DP/termin pertama `paid` (atau `missing:payment_plan`) + permit coverage via scope chain.
  - Mode default: jika setting OFF → `can_start=true` tetapi `warnings[]` terisi; setting ON → `can_start=false` bila belum siap.
- P2. Websearch singkat: best-practice “construction readiness gate / permit expiry reminder” (hanya untuk edge-case: timezone, grace period).
- P3. Jika POC gagal → perbaiki engine/readiness/permit resolution dulu, **jangan lanjut Fase 2**.

---

### FASE 2 — V1 App Development (backend + frontend end-to-end)
**Output:** `/build` 6 tab, Papan Unit lengkap, Unit 360 tab Pembangunan menjadi surface kerja, permits bertingkat.

User stories (V1):
1. Sebagai pelaksana lapangan, saya bisa membuka Unit 360 → Pembangunan dan **submit hasil kerja** (foto+catatan) dari langkah aktif.
2. Sebagai supervisor/PM, saya bisa **verifikasi/reject/override** langkah dan progres unit ter-update otomatis.
3. Sebagai PM, saya bisa memantau **Papan Unit**: planned vs actual, deviasi, langkah aktif, tenggat, umur telat, PIC, bukti terakhir.
4. Sebagai owner, saya menekan **Mulai Bangun** dan bila belum siap sistem memberi **peringatan jujur** + butuh konfirmasi/alasan.
5. Sebagai admin legal, saya mengelola izin di level project/cluster/block/unit dan melihat **coverage** + peringatan kadaluarsa.

#### Backend
- B1. Tambah SSOT `backend/reference_p46.py`: `permit_scope`, `readiness_state`, `build_gate_code`, label Indonesia.
- B2. Tambah `backend/models_p46.py`: request/response untuk board units, readiness, permit coverage.
- B3. Implement `backend/build_unit_board.py`:
  - fungsi `unit_rows(org, project_id, filters, pagination)` → baris per unit,
  - untuk unit tanpa schedule: planned/deviation = null + `missing=["schedule"]`.
- B4. Implement `backend/build_readiness.py`:
  - `evaluate_unit_readiness(org, unit_id)` → `{state, can_start, warnings[], missing[], evidence}`
  - gunakan setting `build.require_dp_before_start` (default **False**) + `permit.block_build_without` (default `[]`).
- B5. Endpoint baru:
  - `GET /api/build/board/units` (papan unit per unit)
  - `GET /api/build/unit/{id}/readiness`
  - `POST /api/build/unit/{id}/start` (mode peringatan: wajib `ack=true` + `reason` bila ada warnings; mode enforce: tolak bila tidak siap)
- B6. Permits bertingkat:
  - perluas model `permits` (tambah `scope, scope_id, requirement_code, expiry_at`) + migrasi backfill `scope=project, scope_id=project_id`.
  - tambah endpoint `GET /api/permits/coverage` (params: `project_id|cluster_id|block_id|unit_id`) untuk resolved requirements + status + expiry.
  - update scheduler `permit_deadline_sweeper` agar mempertimbangkan `expiry_at`/`deadline`.
- B7. Seed: `seed_phase46.py` (izin bertingkat + 1 unit siap, 1 unit warning DP, 1 unit warning izin, 1 izin near-expiry).
- B8. Update default setting: `build.require_dp_before_start = False` (peringatan default) dan pastikan `verify_settings.py` tetap hijau.

#### Frontend
- F1. Update `BuildHubPage` jadi **6 tab** sesuai dok 29:
  - Papan Unit, Kalender, Lapangan, Mutu & Inspeksi, Analitik & Kalibrasi, Template Jadwal.
  - Pastikan fitur lama tetap reachable (monitor/queue/phases/weekly/delay) via tab yang sesuai (mis. “Analitik & Kalibrasi” memuat WeeklyReport+Delay+Calibration; “Mutu & Inspeksi” memuat InspectionsPanel; “Papan Unit” memuat board per unit).
- F2. Buat `components/build/UnitBuildBoardTab.js`:
  - DataTable kolom: unit, cluster/blok, status bangun, actual%, planned%, deviasi, langkah aktif, tenggat, umur telat, PIC, bukti terakhir, readiness badge.
  - Filter: project/cluster/status/late_only/has_schedule/readiness.
  - Klik baris → `/units/:id?tab=build`.
- F3. Upgrade Unit 360 tab **Pembangunan**:
  - `components/build/UnitBuildTab.js` yang memakai endpoint build bundle + readiness.
  - Sub-komponen: Kurva-S (timeline), daftar langkah + aksi submit/verify/reject/override, shift history, punch list ringkas, inspeksi ringkas, rapor mingguan ringkas.
  - Tombol “Mulai Bangun” memanggil `/build/unit/{id}/start` dan menampilkan dialog peringatan (ack+reason).
- F4. Upgrade tab **Dokumen & Izin** di Unit 360:
  - panel permit bertingkat + status expiry + tombol tambah/edit (reuse AddPermitDialog/PermitDetailSheet dengan field scope).
- F5. Tambah testIds baru: `constants/testIds/buildHubV2.js` (tab 6, unit board, readiness dialog, start button, coverage panel).

---

### FASE 3 — Gate + Uji-mutasi + Penutupan
**Output:** guardrail bergigi + baseline tetap PASS.

User stories (QA/Governance):
1. Sebagai maintainer, gate gagal bila `/build` tidak punya 6 tab atau fitur lama hilang.
2. Sebagai maintainer, gate gagal bila papan unit menampilkan 0 untuk unit tanpa jadwal.
3. Sebagai maintainer, gate gagal bila `build.require_dp_before_start` default bukan **False**.
4. Sebagai maintainer, gate gagal bila mode enforce ON tidak memblokir start.
5. Sebagai auditor, gate gagal bila permit scope chain tidak menghasilkan coverage yang konsisten.

Langkah:
- G1. Tambah gate baru `scripts/verify_build_hub.py` dan daftarkan ke `run_all_gates.sh` sebagai **gate ke-30**:
  - cek `/build` 6 tab (testIds), tidak ada pintu sidebar baru,
  - cek `GET /build/board/units` tie-out sampel unit dengan data schedule/items,
  - cek honest-null untuk unit tanpa schedule (`planned=null`, `missing` ada),
  - cek default setting `build.require_dp_before_start` = False,
  - cek `POST /build/unit/{id}/start` warning-mode butuh ack+reason; enforce-mode (toggle setting) memblokir.
  - cek permit coverage bertingkat + near-expiry/expired classification.
- G2. Buat `scripts/mutasi_46.py` (8–12 mutasi) untuk merusak: null→0, tie-out, default setting, enforce toggle, scope chain, expiry reminders, ack requirement.
- G3. 1 putaran testing_agent_v3 multi-peran mencakup Fase 46 + sekalian membuktikan US15/US16 Fase 45 (kartu target di `/projects/:id`, metrik anggaran di `/bi`).
- G4. Update dokumen: `docs/v2/29` (status), `docs/v2/40_PETA_NAV_V2.md` (catatan tab hub tanpa pintu baru), `CODEBASE_MAP.md`, `plan.md`, `test_result.md`, `memory/test_credentials.md`.

---

## 3) Next Actions
1. Implement `poc/poc_46.py` sampai hijau (tie-out + honesty + readiness + permit chain).
2. Implement backend core: `reference_p46.py`, `models_p46.py`, `build_unit_board.py`, `build_readiness.py`.
3. Perluas `permits` (scope/expiry) + migrasi backfill + endpoint coverage + seed_phase46.
4. Update frontend: `/build` 6 tab + UnitBuildBoardTab + Unit 360 BuildTab + permit panel.
5. Tambah gate `verify_build_hub.py` + `mutasi_46.py`, jalankan `run_all_gates.sh`.
6. Delegate full E2E ke testing agent dan tutup fase dengan update dokumen.

---

## 4) Success Criteria
- `python3 poc/poc_46.py` → PASS.
- `/build` memiliki **6 tab** sesuai spec, tanpa pintu sidebar baru.
- Papan Unit per-UNIT menampilkan planned/actual/deviasi/umur telat/next step/PIC/bukti terakhir; unit tanpa jadwal → planned/deviasi **null** + pesan jujur.
- “Mulai Bangun” default **PERINGATAN** (setting default False), namun bila setting ON → memblokir start (uji negatif).
- Permit bertingkat bekerja + near-expiry reminder berjalan.
- `bash scripts/run_all_gates.sh` → **OVERALL PASS** dengan **30 gates**; `python3 scripts/mutasi_46.py` tertangkap.
