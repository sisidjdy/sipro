# Rencana Development — SIPRO Fase 43 (Kampanye & Biaya Iklan + Atribusi/CAPI)

Problem statement (verbatim):
> "saya ingin anda lanjutkan development dari repo ini https://github.com/sjdidudu/sipro ... Now the final verification: full 26-gate suite plus the complete 22-mutation suite."

Keputusan sesi ini:
- Fokus **Fase 43** sesuai `docs/v2/30_MARKETING_INTEGRATION_SPEC.md`.
- Integrasi pihak ketiga **mode simulasi** (tanpa kredensial nyata), siap-live via env (mengisi env hanya mengubah `mode`).
- Standar mutu sama: **gate baru bergigi + uji-mutasi + E2E multi-peran**, tanpa angka karangan.
- Baseline: **26 gate PASS**; plan lama diarsipkan `memory/plan_archive_fase41_42.md`.

---

## 1) Objectives
1. Membuka 2 menu “Segera Hadir” menjadi fitur nyata:
   - **Marketing → Kampanye & Biaya Iklan** (`/campaigns`)
   - **Marketing → Atribusi & CAPI** (`/attribution`)
2. Menyediakan fondasi data & kontrak API siap-live:
   - `campaigns` + `ad_spend` (manual + CSV idempoten + dry-run)
   - metrik CPL/CAC/ROAS yang **jujur** (tanpa biaya → “data biaya belum lengkap”)
   - atribusi lead→kampanye + event `conversion_events` (CAPI) yang bisa diaudit
3. Menutup fase dengan kualitas repo: **gate baru + uji-mutasi + E2E**, dan 27 gate overall PASS.

---

## 2) Implementation Steps

### Phase 1 — Core POC (isolasi, wajib)
**Tujuan:** membuktikan alur paling rawan gagal sebelum UI dibangun.

User stories (POC):
1. Sebagai DM, saya bisa mengimpor CSV biaya iklan dengan **dry-run** dan melihat baris valid vs ditolak beserta alasannya.
2. Sebagai DM, saya bisa mengimpor file yang sama 2× dan hasilnya **tidak duplikat** (idempoten).
3. Sebagai analis, saya melihat metrik **tidak berbohong**: bila biaya belum ada untuk periode, sistem menyatakan “data biaya belum lengkap”.
4. Sebagai admin integrasi, saya melihat mode platform (simulation/live) tanpa menampilkan rahasia env.
5. Sebagai tim growth, event CAPI V2 punya `event_id` dedup dan `user_data` ter-hash sehingga siap-live.

Langkah:
- Websearch singkat best practice:
  - natural-key upsert spend harian, CSV idempotent import, hashing PII untuk CAPI (SHA-256), dan “honest metrics”.
- Buat `poc/poc_43.py` yang menjalankan:
  1) create campaign manual (atau gunakan seed sementara)
  2) CSV dry-run: validasi tanggal/mata uang/kampanye tak dikenal/duplikat internal
  3) commit import 2×: verifikasi unique natural key & update-on-change
  4) agregasi metrik + verifikasi pesan “data biaya belum lengkap”
  5) record conversion event V2: `event_id`, hash email/phone (E.164 normalize)
  6) adapter mode: simulation membaca DB; env dummy → health jujur gagal/live
- Jika POC belum hijau: perbaiki sampai stabil (tidak lanjut ke Phase 2).

### Phase 2 — V1 App Development (backend + frontend)

User stories:
1. Sebagai DM Supervisor, saya bisa membuat & mengubah **master kampanye** (platform, objective, status, periode, budget) agar spend bisa ditautkan.
2. Sebagai staf DM, saya bisa input **biaya iklan harian manual** per kampanye dan melihat sumber data (manual/csv/api).
3. Sebagai DM, saya bisa mengimpor CSV biaya iklan lewat wizard: **preview → commit → laporan**.
4. Sebagai manajer, saya bisa melihat **Kinerja Kampanye** (spend, leads, CPL, CAC, ROAS) dengan label sumber data dan warning bila biaya belum lengkap.
5. Sebagai auditor, saya bisa membuka **Atribusi & CAPI** untuk melihat funnel per (source,campaign) + daftar event CAPI dan status transport.

Backend:
- Tambah SSOT & model:
  - `backend/reference_p43.py` + registrasi ke `reference._PHASES`
  - `backend/models_p43.py`
- Logika inti:
  - `backend/ads_engine.py`: parse/validate CSV, dry-run report, idempotent upsert natural key
  - `backend/ads_adapters/meta.py` & `backend/ads_adapters/google.py`: kontrak `list_campaigns`, `daily_insights` (simulation = data DB)
- API:
  - `backend/routers/ads_router.py` sesuai spec (§5)
  - registrasi router di `backend/server.py`
- CAPI V2:
  - update `backend/capi.py` (event_id + hash user_data + `SubmitApplication` hook di alur nyata SPR signed)
- RBAC + index:
  - tambah resource `ads` di `backend/rbac.py`
  - unique index `ad_spend` natural key + index `campaigns` + `ads_imports`
- Seed:
  - `backend/seed_phase43.py`: seed `campaigns` yang **match** `lead.campaign` demo + sedikit `ad_spend` manual
  - panggil dari `seed.py`/startup seperti fase lain.

Frontend:
- Nav + routes:
  - aktifkan 2 menu (hapus `comingSoon`) di `navigationConfig.js`, tambah `PAGE_META`, tambah `<Route>` di `App.js`.
- Test IDs:
  - `frontend/src/constants/testIds/ads.js` + re-export.
- Pages:
  - `pages/CampaignsPage.js` (hub bertab: Kampanye, Biaya, Kinerja, Riwayat Impor)
  - `pages/AttributionPage.js` (hub bertab: Funnel, Event CAPI, Status Integrasi)
- Components:
  - `components/ads/*` (DataTable/FilterBar/TabPage/KpiCard, mode badge, label sumber data)
- Config Center:
  - bagian/tab “Integrasi” membaca `/api/ads/health`.

E2E (testing agent):
- 1 putaran multi-peran: dm_supervisor, dm_staff, marketing_admin, finance, owner.

### Phase 3 — Gates + Uji-mutasi + Hardening

User stories:
1. Sebagai maintainer, saya punya **gate verify_ads** yang gagal bila idempotensi import dirusak.
2. Sebagai maintainer, gate gagal bila UI menampilkan kosakata enum hardcode (bukan SSOT).
3. Sebagai maintainer, gate gagal bila nav live tanpa route / comingSoon punya route.
4. Sebagai maintainer, gate gagal bila RBAC endpoint `ads` bocor (403/Non-403 salah).
5. Sebagai maintainer, saya bisa menjalankan `mutasi_43.py` dan melihat semua mutasi memerah lalu pulih hijau.

Langkah:
- Buat `scripts/verify_ads.py` + registrasi di `scripts/run_all_gates.sh`.
- Buat `scripts/mutasi_43.py` (mutasi minimal yang “bergigi” untuk idempotensi, dry-run, honesty metrics, RBAC, nav).
- Jalankan:
  - `bash scripts/run_all_gates.sh` (target: **27 gate PASS**)
  - `python3 scripts/mutasi_43.py` (target: semua mutasi tertangkap + pulih hijau)
- Update `plan.md` (status fase + cara verifikasi).

---

## 3) Next Actions
1. Implement `poc/poc_43.py` + stub minimal `ads_engine.py` untuk memenuhi 5 uji POC.
2. Tambah SSOT `reference_p43.py` + registrasi `_PHASES`.
3. Tambah unique index `ad_spend` natural key dan koleksi import report.
4. Setelah POC hijau: buat `routers/ads_router.py` + seed_phase43 + registrasi di server.
5. Aktifkan menu + bangun UI hubs `/campaigns` dan `/attribution` + testIds.
6. Buat `verify_ads.py` + `mutasi_43.py`, lalu jalankan gate suite + E2E.

---

## 4) Success Criteria
- Fitur:
  - `/campaigns` & `/attribution` aktif di sidebar (bukan comingSoon), masing-masing berfungsi end-to-end.
  - CSV import mendukung dry-run + commit + laporan; import 2× **tanpa duplikasi**.
  - CPL/CAC/ROAS **jujur**: bila biaya belum lengkap, UI menampilkan peringatan (bukan 0).
  - `/api/ads/health` menunjukkan mode per platform (simulation/live) tanpa membocorkan rahasia.
  - `conversion_events` memuat CAPI V2: `event_id` + hash user_data, dan `SubmitApplication` terbit dari titik bisnis nyata.
- Kualitas:
  - `bash scripts/run_all_gates.sh` → **OVERALL PASS (27 gates)**.
  - `python3 scripts/mutasi_43.py` → semua mutasi tertangkap, lalu baseline pulih hijau.
  - E2E multi-peran tidak menemukan tombol mati/403 tak terduga.
