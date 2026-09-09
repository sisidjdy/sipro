# plan.md — SIPRO — Lanjut Development (Slice A + Slice B + Slice Finance) — Fokus: MVP end-to-end

## ✅ STATUS (update terakhir — pemulihan repo ke-3 + **FASE 35 SELESAI & TERVERIFIKASI**)
- **Pemulihan repo (sesi ini, ke-3)**: `/app` kembali ditemukan kosong/template → repo GitHub
  `sipro` dipulihkan lagi. Langkah wajib pasca-restore ada di **§3b** (buat ulang `backend/.env`,
  `pip install APScheduler reportlab`, `yarn install`). Bukti sehat: login `Sipro#2026` normal,
  `run_all_gates.sh` hijau.
- **FASE 35 DITUTUP** (Papan Mandor tahan sinyal hilang — antrean offline): `poc_35` **43/43**,
  `verify_35` **52/52**, `run_all_gates` **16 gates PASS**, dan **dibuktikan di browser nyata**
  (offline sungguhan lewat Playwright: ajukan → antre → muat ulang saat offline → sinyal kembali →
  terkirim sendiri, tanpa dobel). Lihat §FASE 35 untuk daftar cacat yang ditemukan & diperbaiki.
- **FASE 33 DITUTUP**: verifikasi end-to-end yang dulu terputus sudah dituntaskan dua putaran
  (testing_agent iterasi 44 + 45) → **0 bug kritis, 0 bug medium, 0 error konsol**. Lihat §FASE 33.
- **FASE 34 DITUTUP** (jadwal massal per blok/cluster + geser tanggal serentak): `poc_34` 57/57,
  `verify_34` 40/40, testing_agent iterasi 46/47/48 → invarian terpenting (**bukti terikat waktu**)
  terbukti di layar. Lihat §FASE 34.
- **Fase berikutnya (dipilih owner)**: **Fase 36 = Kalender Jadwal** (kalender bulanan seluruh
  tenggat rumah untuk Manajer Proyek), lalu **Fase 37 = Kalibrasi Sekali Klik** (ubah durasi
  template langsung dari Analitik Telat). Integrasi WhatsApp/e-Sign/e-Faktur/BI-SLIK **tetap mode
  simulasi** (belum ada kredensial resmi).
- **Pemulihan repo (sesi ini)**: repo GitHub `sipro` dipulihkan lagi ke `/app` (workspace ditemukan
  kosong/template). Yang harus diulang tiap restore (sudah dilakukan): `backend/.env` dibuat ulang
  (`JWT_SECRET`, `EMERGENT_LLM_KEY`, `PORTAL_MASTER_OTP=000000`, `DEFAULT_ORG_ID=org-sipro`,
  `DEFAULT_ORG_NAME`, `COOKIE_SECURE`, `BOOKING_HOLD_DAYS`, `STORAGE_PROVIDER`, `PHOTO_*`) +
  `pip install APScheduler reportlab` (dua paket ini TIDAK ada di image dasar) + `yarn install`.
  Bukti sehat pasca-restore: `bash scripts/run_all_gates.sh` → **OVERALL PASS (14 gates)**,
  `poc_31` 63/63, `poc_32` 79/79, `poc_33` **66/66**, login `Sipro#2026` normal.
- **FASE 33 DITUTUP**: verifikasi end-to-end yang dulu terputus sudah dituntaskan dua putaran
  (testing_agent iterasi 44 + 45) → **0 bug kritis, 0 bug medium, 0 error konsol**. Lihat §FASE 33.
- **FASE 34 DITUTUP** (jadwal massal per blok/cluster + geser tanggal serentak): `poc_34` 57/57,
  `verify_34` 40/40, `run_all_gates` **15 gates PASS**, testing_agent iterasi 46/47/48 →
  invarian terpenting (**bukti terikat waktu**) terbukti di layar. Lihat §FASE 34.

## Riwayat STATUS sebelumnya (pemulihan repo + Fase 33 dimulai)
- **Pemulihan repo (15 Agu 2026)**: repo GitHub dipulihkan lagi ke `/app`. `.env` (di-gitignore) dibuat ulang: `JWT_SECRET`, `EMERGENT_LLM_KEY`, `PORTAL_MASTER_OTP`, `DEFAULT_ORG_ID/NAME`, `COOKIE_SECURE`, `PHOTO_*`. Dependensi backend dipasang ulang (`reportlab`, `APScheduler`, dll; `litellm`+`emergentintegrations` sudah ada di image).
- **Dua gate merah pasca-restore diperbaiki (bukan diakali)**:
  - `build_policies` kini punya **dokumen kebijakan nyata** hasil seed (dulu kosong → audit forensik HIGH & admin tak bisa lihat "sejak kapan/oleh siapa").
  - **Laporan mingguan pekan berjalan** dibangkitkan dari jadwal nyata saat seed (dulu direksi melihat halaman kosong sampai Senin berikutnya).
  - Hasil: `verify_32` **28/28**, `forensic_audit` **PASS**, `bash scripts/run_all_gates.sh` → **OVERALL PASS (13 gates)**.
- **Titik berhenti Fase 32 direproduksi**: Papan Mandor + instruksi kerja + dialog ajukan (kamera + panel syarat) tampil normal, **0 error console**.
- **Fase 33 (RAB/BoQ ↔ jadwal → opname & termin subkon)**: **SELESAI & TERVERIFIKASI** — lihat §FASE 33.
- **Repo & environment**: repo GitHub dipulihkan ke `/app` (workspace persisten). Backend + frontend jalan via supervisor.
  - Env yang hilang saat pemulihan sudah dibuat ulang: `JWT_SECRET`, `EMERGENT_LLM_KEY`, `PORTAL_MASTER_OTP`, `DEFAULT_ORG_ID/NAME`, `COOKIE_SECURE`, `PHOTO_WATERMARK` → bug **login 500 (`KeyError: JWT_SECRET`) FIXED**.
- **Integrations (ready, config-driven)**: `EMERGENT_LLM_KEY` tersedia → **Emergent Object Storage** aktif (managed). Mode simulasi masih dipakai untuk WhatsApp Cloud API live (tanpa kredensial Meta), e-sign, BI/SLIK, dan e-Faktur.
- **Guardrails**: `bash scripts/run_all_gates.sh` → **OVERALL PASS (12 gates)**.
- **POC Fase 31**: `python3 scripts/poc_31.py` → **63 PASS / 0 FAIL**. Gate `scripts/verify_31.py` → **30 PASS / 0 FAIL**.
- **Phase 28b/28c (Site Plan + Photo Storage + Bukti Perbaikan Berpasangan)**: **SELESAI & TERVERIFIKASI**.
- **Phase 29 (Work Hub v2 + Lead Lifecycle + UI/UX + Report/Kanban)**: **SELESAI & TERVERIFIKASI**.
- **Phase 30 (Qualification Hub / SLIK prescreen + photo optimize + capture.failed queue)**: **SELESAI & TERVERIFIKASI**.
- **Phase 31 (Construction Progress Engine v2)**: **SELESAI & TERVERIFIKASI** — lihat §Phase 31 di bawah untuk bukti per user story.
- **Phase 32 (Task-based Execution + Papan Mandor + Laporan Mingguan + Analitik Telat)**: **SELESAI & TERVERIFIKASI**
  - `bash scripts/run_all_gates.sh` → **PASS (13 gates)** (gate baru `scripts/verify_32.py` 28/28).
  - `python3 scripts/poc_32.py` → **79 PASS / 0 FAIL**; `poc_31.py` tetap 63/63 (tanpa regresi).
  - testing_agent_v3 iterasi 42 → backend 100%, frontend 11/12 user story lulus, **0 bug kritis, 0 bug medium**.
- **Audit per request owner**: `/app/memory/AUDIT_01_WORKHUB_LEAD.md`.
- **Kredensial uji**: `/app/memory/test_credentials.md` (sandi `Sipro#2026`; portal pembeli: identifier `+628121111111`, OTP master `000000`).

---

## 1) Objectives

### Objective A — Work Hub Engine “bernilai bisnis” (P0)
Membangun ulang Work Hub agar benar-benar memandu pekerjaan lintas divisi, bukan sekadar menu.
Fokus owner (disepakati):
- **Domain kerja**: 4 divisi — **Sales & Marketing**, **Teknis/Proyek**, **Digital Marketing**, **Finance**.
- Tiap divisi punya **Supervisor + Staff** (field pada user: `division` + `level`).
- RBAC modul tetap seperti sekarang, tetapi **peran baru ditambahkan** untuk mendukung pola supervisor/staff.
- Work Hub harus memetakan **jobdesk** berdasarkan fitur yang sudah ada dan menjadikan action sebagai task.
- Supervisor mengatur konfigurasi: **auto event**, **manual**, **recurring**, SLA, prioritas, aturan assignee.
- Task memiliki alur: **open → in_progress → submitted → verified/rejected → done**.

### Objective B — Lead Lifecycle sebagai “gerbang bukti” + WA terintegrasi (P0)
Menutup gap bisnis proses sales:
- Stage tidak boleh dipilih bebas; harus berdasarkan **aksi + bukti**.
- **Won otomatis** dari event deal legal/akad/BAST (tidak manual).
- WA harus terintegrasi langsung ke record lead dan memicu task/lifecycle.
- Tambahkan penilaian **kualitatif** (disposition/intent) setelah kontak pertama.

### Objective C — UI/UX stability sweep (P0)
Sambil membangun fitur P0, lakukan perbaikan UI/UX yang paling terlihat:
- Konsistensi **Card background** (pakai `bg-card`).
- Tambah **pagination** di daftar utama.
- Tambah **sticky** header/toolbar/footer aksi pada halaman panjang.
- Perbaiki **CTA mati**, dan empty/loading/error state sesuai `design_guidelines.md`.

### ✅ Objective D — Construction Progress Engine v2 (P0) — SELESAI
**FASE 31 (permintaan owner): CONSTRUCTION PROGRESS ENGINE v2 — Jadwal Berbukti, Gerbang Mutu, Reminder & Eskalasi, per TIPE UNIT.**

Target bisnis:
- Monitoring konstruksi **harus berjalan sesuai target waktu** (jadwal kalender), ada **reminder** dan **eskalasi** bila telat.
- Ada **proof/bukti** yang kuat agar benar-benar mengikuti spesifikasi & mengurangi kecurangan.
- Ada **guard/gerbang** agar tidak bisa “loncat” melewati guideline/hold point.
- Progres bisa **berbeda per tipe unit** dan bisa dikonfigurasi (template + parameter).
- **Tidak duplikasi**: wajib enhance fitur yang sudah ada (QC/Inspections, Work Hub, Object Storage).
- Data & koleksi harus **jelas**; dropdown harus dari **SSOT reference**.
- Unit harus **terikat lead/deal/customer** (terutama setelah dibeli) agar progress, portal, dan laporan tidak rapuh.

**Contoh default yang harus jadi baseline template** (tidak diparafrase):
- MINGGU 1 — PEKERJAAN PERSIAPAN + PONDASI …
- … hingga MINGGU 9 — FINAL CHECK …
- KRITIKAL PATH (minimal tunggu) …

### ✅ Objective E (BARU) — Task-based Execution + Papan Mandor + Laporan Mingguan + Analitik Telat (P0)
**FASE 32 BARU (permintaan owner):**

> === PERMINTAAN OWNER (verbatim, jangan diparafrase/disederhanakan) ===
> "Papan Mandor: Beri pelaksana satu layar 'kerja hari ini' yang enak dipakai dari HP, foto langsung dari lokasi
> Laporan Mingguan: Kirim ringkasan progres tiap rumah ke direksi setiap Senin, lengkap grafik rencana vs realisasi
> Analitik Telat: Tunjukkan pekerjaan dan pelaksana paling sering telat, supaya template bisa dikalibrasi dari data nyata
> setiap progress itu harus menjadi task dan masing masing harus upload foto sebagai bukti, ingat kembali ini action task based jadi setiap step pada konstruksi itu buat menjadi instruksi task dan harus ada validasinya"

> === JAWABAN/PILIHAN OWNER (WAJIB dipatuhi) ===
> 1) **Kapan setiap step jadi task** → **CAMPURAN**: task aktif hanya yang siap/telat, sedangkan step berikutnya tampil sebagai "instruksi menunggu" di Papan Mandor — tidak membanjiri Work Hub; urutan/predecessor WAJIB ditegakkan.
> 2) **Papan Mandor** → cukup **TAB TAMBAHAN** di halaman Progres & Mutu.
> 3) **Foto dari lokasi** → tombol kamera HP langsung + watermark unit & tanggal otomatis; ditambah rekam lokasi GPS saat pengambilan; lokasi **bisa on/off** oleh admin.
> 4) **Laporan Mingguan** → notifikasi + task baca untuk Direksi & Manajer Proyek di aplikasi + halaman laporan; **ditambah unduh PDF**.

---

## 2) Implementation Steps

### Phase 1 — Core POC / Isolation (SELESAI)
- Sudah tervalidasi.

---

### Phase 2 — V1 App Development (Slice A — Sales funnel tipis) (SELESAI)
- Backend + Frontend selesai dan teruji.

---

### Phase 3 — Add More Features (Slice B — Konstruksi tipis) (SELESAI)
- Backend + Frontend selesai dan teruji.

---

### Phase 4 — Stabilization / Guardrails Growth (SELESAI)
- Stabilitas + compliance + gates hijau.

---

### Phase 5 — Slice Finance & Real-Time Notifications (SSE) (SELESAI)
- Foundation finance + SSE + UI finance lulus testing_agent_v3.

---

### Phase 6 — EPIC 3.5 Cashflow/Collections + EPIC M5 Reports/BI (SELESAI)
- Lulus testing_agent_v3 dan gates hijau.

---

### Phase 7 — EPIC 1.5 KPR/Financing + Adoption Completion (SELESAI)
- Customer Portal + object storage + portal security sudah berjalan.

---

### Phase 8 — EPIC M1 Customer Portal (SELESAI)
- Portal OTP (master `000000`), overview/payments/progress/documents + complaints: teruji.

---

## ✅ Phase 29 — Rebuild Work Hub + Lead Lifecycle + UI/UX (P0) (SELESAI & TERVERIFIKASI)
> Ringkasan fase 29 tetap berlaku seperti di dokumen sebelumnya (29a/29b/29c/29d), dengan POC PASS, gates PASS, dan verifikasi manual UI.

---

## ✅ PHASE 31 — SELESAI & TERVERIFIKASI (Construction Progress Engine v2)

### (Ringkas) Bukti per user story (testing_agent_v3 iter. 40–41 + verifikasi manual)
| US | Fitur | Status |
|---|---|---|
| US-1 | Papan pantau per rumah | ✅ PASS |
| US-2 | Tick pemantauan + panel hasil menetap | ✅ PASS |
| US-3 | Sheet jadwal unit (9 minggu/20 item, gerbang, bukti, kurva) | ✅ PASS |
| US-4 | Verifikasi/Kembalikan supervisor + progres berbobot | ✅ PASS |
| US-5 | Reject/rework + validasi inline | ✅ PASS |
| US-6 | Submit pelaksana + unggah foto nyata + anti duplikat | ✅ PASS |
| US-7 | Anti-loncat + RBAC | ✅ PASS |
| US-8 | Override gerbang + audit | ✅ PASS |
| US-9 | Penyebab telat SSOT | ✅ PASS |
| US-10 | Hold/resume jadwal | ✅ PASS |
| US-11 | Generate jadwal unit | ✅ PASS |
| US-12 | Template per tipe unit | ✅ PASS |
| US-13 | RBAC sales/finance | ✅ PASS |
| US-14 | Kartu beranda pembangunan | ✅ PASS |
| US-15 | Portal pembeli progres rumah nyata | ✅ PASS |
| US-16 | Regresi modul lain | ✅ PASS |

---

## Phase 32 — Task-based Execution + Papan Mandor + Laporan Mingguan + Analitik Telat (P0)

### Konteks kode yang sudah ada (agar TIDAK duplikasi mesin baru)
- Fase 31 sudah jadi: `build_templates/build_schedules/build_items/build_item_submissions`, gerbang mutu (predecessor terverifikasi, waktu tunggu curing, hold point, schedule hold), bukti foto wajib via object storage + watermark + anti foto daur ulang (hash SHA-256), SoD pengaju≠verifikator, override beralasan, reminder + eskalasi L1/L2/L3, progres unit = Σ bobot item terverifikasi, portal pembeli menampilkan progres rumah nyata.
- Work Hub v2 SUDAH punya mesin task lengkap: koleksi `tasks` dengan `jobdesk_code`, `division`, `proof_kind` (none/note/photo/document/record/wa_message), `verify_mode` (none/system/supervisor), `review`, `proof[]`, `outcome`, `link`, SLA + sweeper + notifikasi. **WAJIB DIPAKAI ULANG**.
- Jobdesk Fase 31 yang sudah ada: TK-10/TK-11/TK-12/TK-13. `build_engine._spawn_work_task()` sudah membuat TK-10 saat gerbang terbuka dan `_close_item_tasks()` menutupnya.
- `MasterDataPage` (route `/admin/master-data`, admin only) adalah tempat benar untuk toggle kebijakan bukti kerja.
- `files_router.upload_file` menerima `watermark` + `optimize`; storage MEMBUANG metadata EXIF/GPS → koordinat harus dikirim eksplisit oleh browser dan disimpan terstruktur (tidak mengandalkan EXIF).

### Cacat logika yang direvisi di Fase 32 (SEMUA SUDAH DITUTUP ✅)
- **D-H (KRITIS, anti-kecurangan bocor)**: task build (meta `build_item_id`) masih bisa diajukan/diverifikasi via Work Hub generik (`/workhub/tasks/{id}/submit` + `/verify`) hanya dengan foto tanpa checklist/min foto/anti duplikat dan tanpa mengubah `build_items`. Harus ditutup **tanpa dead-end**: Work Hub harus mengarahkan ke jalur build dengan deep link.
- **D-I**: task TK-10 belum lahir untuk item yang sudah `ready` sejak jadwal dibuat (hanya lahir saat transisi blocked→ready) sehingga pekerjaan awal tidak punya task.
- **D-J**: deskripsi task TK-10 masih ringkas; harus menjadi **instruksi task**: lingkup, checklist mutu (KRITIS), hold point, minimal foto, waktu tunggu/curing, pendahulu, verifikator.
- **D-K**: `link` task masih `/construction` generik; harus **deep link** ke item.

---

### Phase 32a — POC — ✅ SELESAI (79 PASS / 0 FAIL) (`scripts/poc_32.py`, target ≥35 asersi, pakai API nyata)
1. Instruksi task lengkap: setiap `build_items` status `ready/in_progress/rework` milik pelaksana punya task TK-10/TK-12 dengan `proof_kind=photo`, `verify_mode=supervisor`, `meta.build_item_id`, deskripsi instruksi lengkap.
2. Task lahir juga untuk item yang ready sejak generate (perbaikan D-I), idempoten.
3. Anti-bypass (perbaikan D-H): submit/verify/complete via Work Hub untuk task build **DITOLAK** dengan pesan yang mengarahkan + memuat `build_item_id`; submit via `/build/items/{id}/submit` menutup task dan menaikkan progres.
4. Urutan wajib: item yang pendahulunya belum diverifikasi **tidak punya task aktif** dan submit ditolak; setelah pendahulu diverifikasi, task berikutnya lahir.
5. Papan Mandor `GET /api/build/board/today`: kelompok `overdue`, `today`, `in_progress`, `rework`, `awaiting_verification`, `upcoming` (instruksi menunggu + alasan terkunci + perkiraan tanggal buka).
6. Kebijakan bukti kerja `GET/PUT /api/build/policy` (admin/owner): `geo_required` (on/off), `camera_only` (opsional), `min_note_chars`. Saat `geo_required=true`, submit tanpa koordinat ditolak.
7. Laporan mingguan: `POST /api/build/reports/weekly/run` idempoten (org+project+week) → notifikasi + task baca **TK-14** + seri kurva rencana vs realisasi; `GET list/detail`; `GET pdf` (header `%PDF`).
8. Penjadwal Senin: fungsi tick mingguan idempoten (dipanggil dua kali → hanya 1 laporan).
9. Analitik telat `GET /api/build/analytics/delays`: per step, per pelaksana, per tipe, `recommendations` kalibrasi template.
10. RBAC: pelaksana tidak bisa ubah policy / run report (403); sales tetap 403 semua endpoint build.

**Definition of Done (32a)**
- `scripts/poc_32.py` ≥35 asersi, 100% PASS.

---

### Phase 32b — Backend — ✅ SELESAI
- **File baru (kecil, jelas):**
  - `build_instruction.py` (penyusun instruksi task + ringkasan langkah)
  - `build_board.py` (papan mandor hari ini)
  - `build_reports.py` (laporan mingguan + PDF reportlab)
  - `build_analytics.py` (analitik telat + rekomendasi)
  - `build_policy.py` (kebijakan bukti kerja)
  - `routers/build_ops_router.py` (prefix `/api/build`: board, policy, reports, analytics)
- **Koleksi baru:**
  - `build_policies` (1 dokumen per org)
  - `build_weekly_reports` (org+project+week, idempoten)
- **Index** di `seed.py`.
- **Ubah (wajib):**
  - `build_engine._spawn_work_task`:
    - spawn untuk item `ready` saat generate (fix D-I)
    - instruksi kaya (fix D-J)
    - deep link (fix D-K)
  - `build_actions.submit_item`:
    - terima `geo` (lat/lng/accuracy/captured_at)
    - tegakkan policy `geo_required`
    - simpan koordinat pada submission & evidence
  - `routers/workhub_router.py` + `routers/work_router.py`:
    - guard: task dengan `meta.build_item_id` tidak boleh lewat submit/verify/complete generik (fix D-H)
    - return payload yang memandu UI untuk membuka deep link build item
  - `jobdesk_catalog.py`: tambah **TK-14** (baca laporan mingguan) + link
  - `engine.py`: APScheduler job mingguan Senin + idempotensi
  - `routers/files_router.py`: terima `lat/lng/accuracy/captured_at` opsional, simpan di dokumen `files` (terstruktur)
  - `reference_p31.py`: tambah SSOT bila perlu (`build_report_status`, `build_geo_mode`)

**Definition of Done (32b)**
- Semua endpoint Phase 32 tersedia, RBAC benar, idempoten.
- Gates tetap PASS.

---

### Phase 32c — Frontend — ✅ SELESAI
- `ConstructionPage` menjadi **7 tab**:
  1) **Papan Mandor** (default untuk `site_engineer`)
  2) Monitoring Unit
  3) Antrean Kerja
  4) Infrastruktur Kawasan
  5) QC & Inspeksi
  6) **Laporan & Analitik**
  7) Template Jadwal

- Komponen baru:
  - `ForemanBoard.js` (mobile-first)
  - `ForemanTaskCard.js` (instruksi lengkap + checklist ringkas + tombol kamera + ajukan)
  - `WeeklyReportPanel.js` (daftar laporan, grafik, tabel per rumah, unduh PDF)
  - `DelayAnalyticsPanel.js` (pekerjaan/pelaksana paling sering telat + rekomendasi kalibrasi)

- `PhotoUploader` ditingkatkan:
  - prop `capture` (buka kamera belakang HP)
  - tombol “Ambil foto” terpisah dari “Pilih berkas”
  - ambil koordinat via `navigator.geolocation` bila policy `geo_required=true`
  - pesan izin lokasi manusiawi; tidak ada data bocor

- Work Hub/Beranda:
  - task build (meta `build_item_id`) CTA = deep link "Buka & ajukan hasil" ke Papan Mandor/sheet item

- `MasterDataPage`:
  - tab baru **Kebijakan Bukti Kerja** (admin/owner): toggle GPS wajib (on/off), kamera saja, min karakter catatan.

- Deep link:
  - `/construction?tab=board&item=<id>` dan `?unit=<id>` dihormati.

- testIds:
  - tambah testIds di `constants/testIds/build.js` + `master.js` untuk tab baru/panel baru.

**Definition of Done (32c)**
- Pelaksana bisa bekerja dari HP di satu tab: lihat instruksi, ambil foto, ajukan.
- Tidak ada jalur bypass Work Hub generik untuk task build.

---

### Phase 32d — Verifikasi & Testing — ✅ SELESAI
- `scripts/poc_32.py` harus 100% PASS.
- Tambah `scripts/verify_32.py` (atau perluas verify_31) dan masukkan ke `run_all_gates.sh` → menjadi **13 gates**.
- `bash scripts/run_all_gates.sh` PASS semua; `scripts/poc_31.py` tetap 63/63.
- **testing_agent_v3 WAJIB**: papan mandor (unggah foto nyata + capture), anti-bypass task, urutan step, laporan mingguan + PDF, analitik telat, policy GPS on/off, RBAC, regresi Fase 31.

---

## ✅ FASE 33 — RAB/BoQ ↔ ITEM JADWAL → OPNAME & TERMIN SUBKON (SELESAI & TERVERIFIKASI)

### Bukti penutupan Fase 33 (jangan dihapus)
| Bukti | Hasil |
|---|---|
| `bash scripts/run_all_gates.sh` (termasuk `verify_33.py`) | ✅ **OVERALL PASS (14 gates)** pada DB bersih |
| `python3 scripts/poc_33.py` | ✅ **66 PASS / 0 FAIL** (seluruh INV-33-1..8 + tie-out AP/retensi + RBAC + regresi lump-sum) |
| `poc_31.py` / `poc_32.py` | ✅ 63/63 dan 79/79 — tanpa regresi |
| testing_agent iterasi **44** (backend + panel lingkup) | ✅ alur `site` ajukan → `pm` opname → `finance` setujui → tagihan AP; 10 “gagal” = cacat skrip tester (project_id bukan UUID, assertion RBAC terbalik), bukan bug aplikasi |
| testing_agent iterasi **45** (interaksi UI lintas peran) | ✅ **100%**, **0 error konsol** di `/login`, `/`, `/subcon`, `/boq`, `/construction` |
| US-1b dialog tambah/hapus lingkup | ✅ dialog + 70 kandidat + filter unit + input nilai + total; penambahan yang membuat Σ lingkup > nilai kontrak **DITOLAK** (INV-33-4 bekerja: kontrak SPK/2026/0003 sudah terurai penuh 66jt) |
| US-3 ajukan termin berbukti | ✅ pratinjau 5 baris, Rp 30.000.000 / retensi Rp 1.500.000 / net Rp 28.500.000, **tanpa input persen**, badge “Per item berbukti” |
| US-5 opname per baris | ✅ 5 baris + switch; mematikan 1 baris → panel alasan muncul, **simpan disabled sampai alasan diisi**, total turun ke Rp 24.000.000; **SoD**: pengaju melihat peringatan + simpan disabled |
| US-6 persetujuan uang | ✅ PM **tidak punya** tombol Setujui; `finance` menyetujui → Disetujui Rp 24.000.000, retensi Rp 1.200.000, tagihan AP terbentuk |
| US-7 anti bayar-ganda | ✅ 4 baris jadi “Sudah ditagih” + nomor termin `TRM/2026/0002`; baris yang dikeluarkan opname **kembali** “siap ditagih” (Rp 6.000.000) |
| US-8 tanpa persen manual | ✅ catatan “dihitung sistem dan tidak bisa diketik” pada SPK mode item; SPK lump-sum tetap punya input persen |
| US-9 Kendali Biaya RAB | ✅ anggaran Rp 472.000.000 / dikontrakkan Rp 66.000.000 / terbukti Rp 30.000.000 / ditagih Rp 0, 5 baris kategori, 7 baris kode biaya + kolom “Langkah terpetakan”, dialog pemetaan 20 langkah |
| US-10 transparansi lapangan | ✅ kartu item jadwal A-01 menampilkan “Borongan Rp 6.000.000 · CV Bangun Jaya (SPK/2026/0003) · siap ditagih (belum masuk termin)” |
| Regresi Fase 31/32 | ✅ Papan Mandor, Laporan & Analitik, Antrean Kerja, QC & Inspeksi normal |

### Rincian rencana Fase 33 (arsip, sudah dikerjakan)

**Masalah bisnis yang ditutup (uang bocor):** nilai termin subkon hari ini lahir dari **persen kumulatif yang DIKETIK BEBAS** (`progress_claims.progress_pct`) lalu "opname" = mengetik persen lain. Tidak ada satu pun ikatan ke **pekerjaan yang benar-benar sudah diverifikasi** (Fase 31/32: foto + checklist + verifikator ≠ pengaju). Akibatnya subkon bisa ditagihkan 60% padahal fisik terverifikasi 33%, pekerjaan yang sama bisa dibayar dua kali, bahkan dua subkon bisa dibayar untuk item yang sama. RAB/BoQ juga belum terhubung ke jadwal sehingga tidak ada kendali biaya per pekerjaan.

**Prinsip Fase 33:** *uang hanya boleh mengalir mengikuti bukti.* Termin = Σ nilai **item jadwal terverifikasi** yang **belum pernah ditagih**.

### Invarian (wajib ditegakkan di backend, diuji gate)
- **INV-33-1** Termin tidak boleh melebihi nilai pekerjaan yang **SUDAH diverifikasi** (`build_items.status=done` + verifikator).
- **INV-33-2** Satu item pekerjaan hanya bisa **dibayar sekali** (ledger `claim_id` pada lingkup SPK).
- **INV-33-3** Satu item pekerjaan hanya boleh masuk **satu SPK** (tidak ada dua subkon dibayar untuk pekerjaan sama).
- **INV-33-4** Σ nilai lingkup ≤ nilai kontrak SPK (termasuk Change Order); Σ termin disetujui ≤ nilai kontrak.
- **INV-33-5** `progress_pct` SPK ber-mode item **tidak bisa diketik manual**.
- **INV-33-6** Opname hanya boleh **MENGURANGI** baris (dengan alasan), tidak boleh menambah.
- **INV-33-7** **Pemisahan tugas**: pengaju termin ≠ yang meng-opname; finance/owner yang menyetujui.
- **INV-33-8** Kendali biaya RAB: nilai dikontrakkan > anggaran kategori → **peringatan over-commit** (bukan blokir; jalur resmi = Change Order).

### Fase 33a — Model & mesin
- `backend/opname.py` (baru): lingkup SPK, hitung opname (earned value dari item terverifikasi), susun baris termin, efek persetujuan, agregasi kendali biaya.
- `backend/models_p33.py`, `backend/reference_p33.py` (SSOT grup baru: basis termin, mode lingkup, alasan pengurangan opname).
- Koleksi baru `spk_scope_items` + index unik `(org_id, build_item_id)` → INV-33-3 dijaga database, bukan hanya kode.
- `backend/seed_phase33.py`: SPK demo ber-lingkup item nyata pada unit yang sudah punya jadwal (bukan data karangan).

### Fase 33b — Endpoint & guard
- `routers/spk_scope_router.py`: `GET /subcon/spk/{id}/scope`, `GET /subcon/spk/{id}/scope/candidates`, `POST /subcon/spk/{id}/scope`, `DELETE /subcon/spk/{id}/scope/{sid}`, `GET /subcon/spk/{id}/opname`.
- `routers/subcon_claims_router.py`: termin jadi **berbasis baris** (create/verify/approve), tetap kompatibel untuk SPK lump-sum lama.
- `routers/subcon_router.py`: tolak `progress_pct` manual pada SPK mode item; ringkasan lingkup ikut di list/detail.
- `routers/boq_router.py`: `step_codes` pada item RAB, `GET /boq/steps`, `GET /boq/control` (anggaran vs dikontrakkan vs terverifikasi vs ditagih).

### Fase 33c — POC (bukti mesin jalan sebelum UI)
- `scripts/poc_33.py` harus **100% PASS**: seluruh invarian di atas + tie-out angka AP/retensi + RBAC.

### Fase 33d — Frontend (semua yang ada di backend HARUS ada di UI)
- `components/subcon/SpkScopeSection.js` + `AddScopeItemsDialog.js` (pilih unit → langkah jadwal, harga acuan RAB, Σ = nilai kontrak).
- `components/subcon/ClaimOpnameSheet.js` (opname per baris + alasan pengurangan) dan `SubmitClaimDialog.js` dirombak: **tanpa kolom persen bebas**, menampilkan tabel pekerjaan terverifikasi yang bisa ditagih.
- `components/boq/CostControlPanel.js` (tab **Kendali Biaya** di halaman RAB/BoQ) + pemetaan langkah pada dialog item RAB.
- Kartu item konstruksi menampilkan **nilai borongan + status tagih** (transparan untuk PM).

### Fase 33e — Verifikasi
- `scripts/verify_33.py` masuk `run_all_gates.sh` (**14 gates**), `poc_31/32` tetap hijau (tanpa regresi), lalu **testing_agent_v3** wajib.

### User stories Fase 33 (dipakai testing agent)
1. PM mengisi lingkup SPK dari item jadwal unit nyata; nilai kontrak = Σ nilai lingkup.
2. Item yang sudah dipakai SPK lain **ditolak** saat dimasukkan ke lingkup.
3. Pengajuan termin **dihitung sistem** dari pekerjaan terverifikasi & belum ditagih (tidak ada kolom persen bebas).
4. Bila belum ada pekerjaan terverifikasi → pengajuan ditolak dengan pesan manusiawi ("belum ada yang bisa ditagih").
5. Opname: PM bisa mengurangi baris + alasan; menambah baris tidak mungkin; pengaju tidak boleh opname sendiri.
6. Finance menyetujui → tagihan AP otomatis (retensi sesuai SPK), nilai = Σ baris lolos opname, progres SPK naik sesuai nilai.
7. Item yang sudah dibayar tidak muncul lagi sebagai bisa-ditagih.
8. Σ termin disetujui tidak melebihi nilai kontrak (+CO).
9. RAB: pemetaan langkah + panel Kendali Biaya (anggaran/dikontrakkan/terverifikasi/ditagih) + peringatan over-commit.
10. RBAC: sales tidak bisa melihat; site tidak bisa menyetujui; PM tidak bisa menyetujui termin.

---

## 3) Next Actions (immediate)
Fase 31, 32, 33, 34, **dan 35 selesai & terverifikasi**. Urutan berikutnya (dipilih owner):
1. **Fase 36 — Kalender Jadwal**: kalender bulanan seluruh tenggat rumah untuk Manajer Proyek
   supaya bentrok terlihat sebelum terjadi (sekarang tenggat hanya terlihat per unit/daftar).
2. **Fase 37 — Kalibrasi Sekali Klik**: dari Analitik Telat langsung mengubah durasi / waktu
   tunggu pada template jadwal (sekarang masih diketik manual di editor).
3. **Kurva-S & laporan portofolio lintas proyek** untuk direksi (laporan mingguan masih per proyek).
4. **Ringkasan laporan mingguan via WhatsApp** (butuh kredensial Meta; WA masih simulasi).

## 3b) Catatan pemeliharaan
- **`backend/reference.py` sudah menyentuh batas compliance (≤800 baris).** Grup fase baru
  WAJIB dibuat di `reference_p<NN>.py`, lalu cukup **menambahkan nomor fase ke tuple `_PHASES`**
  di `reference.py` (pemuatan sudah dinamis sejak Fase 35 — tidak lagi satu baris import per fase).
- **Setelah pull/restore repo (PENTING — sudah TIGA kali terjadi):**
  1. `/app/backend/.env` di-gitignore → buat ulang: `JWT_SECRET` (acak), `EMERGENT_LLM_KEY`,
     `PORTAL_MASTER_OTP=000000`, `DEFAULT_ORG_ID=org-sipro`, `DEFAULT_ORG_NAME=PT SIPRO Land`,
     `COOKIE_SECURE=true`, `BOOKING_HOLD_DAYS=7`, `STORAGE_PROVIDER=emergent`, `PHOTO_*`.
     Tanpa `JWT_SECRET`, login **500 (`KeyError: JWT_SECRET`)**.
  2. `pip install APScheduler reportlab` — dua paket ini TIDAK ada di image dasar
     (tanpa itu backend gagal start: `ModuleNotFoundError: reportlab`).
     Catatan: `pip install -r backend/requirements.txt` **gagal** (konflik
     `emergentintegrations` vs `litellm` yang sudah ada di image) — cukup dua paket di atas.
  3. `cd frontend && yarn install`, lalu `sudo supervisorctl restart backend frontend`.
  4. `bash scripts/seed_reset.sh` → harus **OVERALL PASS (16 gates)**.
  5. Kredensial uji ada di `/app/memory/test_credentials.md` (sandi `Sipro#2026`).
- Sebelum menyatakan sebuah fase selesai, WAJIB hijau semua:
  `bash scripts/run_all_gates.sh` (16 gates) + `poc_31.py` (63) + `poc_32.py` (79) +
  `poc_33.py` (66) + `poc_34.py` (57) + `poc_35.py` (43).
  Catatan: `poc_35.py` memakai 3 pekerjaan siap kerja hasil seed — jalankan pada DB tersegar
  (`seed_reset.sh` lalu ulangi drop+restart bila POC lain sudah menghabiskannya).
- **Bypass uji**: tidak ada backdoor auth; pengujian memakai akun demo asli + tombol
  "Masuk cepat" di halaman login (hanya memanggil `POST /auth/login` biasa). Tombol demo ini
  boleh dimatikan sebelum go-live — beri tahu agar dihapus dari `pages/Login.js`.

---

## 4) Success Criteria
- ✅ WorkHub berfungsi sesuai domain divisi dan menjadi penggerak kerja.
- ✅ Lead lifecycle menjadi gerbang bukti; WA terintegrasi; stage tidak loncat.
- ✅ Construction Progress Engine v2 (Fase 31) stabil.
- ✅ **Fase 32**:
  - Setiap step konstruksi yang boleh dikerjakan MUNCUL sebagai task berinstruksi dengan bukti foto wajib + validasi supervisor.
  - Tidak ada jalur lain menyelesaikan task build selain endpoint build (anti-kecurangan tertutup).
  - Urutan pekerjaan tidak bisa dilangkahi.
  - Pelaksana bisa bekerja dari HP dalam satu layar (tab Papan Mandor).
  - Direksi menerima laporan tiap Senin (in-app + PDF) dengan grafik rencana vs realisasi.
  - Analitik telat menampilkan pekerjaan & pelaksana paling rawan telat + rekomendasi kalibrasi template.
  - Kebijakan GPS bisa dinyalakan/dimatikan admin.
- ✅ Semua perubahan menjaga compliance (py<800, js<500, util<300, css<400) dan `bash scripts/run_all_gates.sh` tetap PASS.

---

## ✅ FASE 29 — SELESAI & TERVERIFIKASI (Work Hub v2 + Lead Lifecycle + UI/UX)
> Bagian ini dipertahankan (ringkasan implementasi 29a/29b/29c/29d + bukti verifikasi) dan menjadi fondasi untuk Phase 31.

### Belum termasuk (jujur, kandidat fase setelah 32)
BI/SLIK checking nyata (butuh jalur legal), WhatsApp Cloud API nyata (butuh kredensial Meta), heatmap kepadatan minat, halaman publik multi-proyek.


---

## ✅ PHASE 32 — SELESAI & TERVERIFIKASI (ringkasan bukti)

| Bukti | Hasil |
|---|---|
| Setiap step boleh-dikerjakan = task berinstruksi (TK-10/TK-12) | ✅ instruksi memuat lingkup, checklist + KRITIS, hold point, waktu tunggu, urutan, verifikator + deep link |
| Anti-bypass task konstruksi (cacat D-H) | ✅ start/submit/verify/reject/complete lewat Work Hub generik DITOLAK & diarahkan ke Papan Mandor; item tidak berubah |
| Urutan tidak bisa dilangkahi | ✅ step depan tanpa task aktif + submit ditolak; tampil sebagai "instruksi menunggu" beserta alasan |
| Papan Mandor (HP) | ✅ 8 kelompok (telat/hari ini/dikerjakan/perbaikan/menunggu verifikasi/antrean verifikasi/jadwal nanti/menunggu urutan) + tombol kamera |
| Foto dari lokasi + GPS on/off admin | ✅ kamera langsung, watermark, koordinat eksplisit (EXIF tetap dibuang), kebijakan di Master Data → Kebijakan Bukti Kerja |
| Laporan mingguan Senin + PDF | ✅ idempoten per pekan, notifikasi + tugas baca TK-14 ke Direksi & PM, grafik rencana vs realisasi, PDF landscape |
| Analitik telat + rekomendasi kalibrasi | ✅ per langkah / pelaksana / tipe unit + rekomendasi konkret dengan CTA ke Template Jadwal |
| Task hantu | ✅ dirapikan otomatis pada tick pemantauan (`reconcile_item_tasks`) |
| Bug dedup tugas laporan | ✅ `source_event` memuat email penerima sehingga semua direksi & PM menerima |

---

## ✅ FASE 35 — PAPAN MANDOR TAHAN SINYAL HILANG (ANTREAN OFFLINE) — SELESAI & TERVERIFIKASI

### Masalah nyata yang diselesaikan
Mandor bekerja di lokasi yang sering kehilangan sinyal. Sebelum fase ini: menekan "Ajukan"
saat sinyal mati = **galat, foto hilang, pekerjaan harus diulang**; menyegarkan aplikasi saat
offline = **halaman kosong + terlempar ke halaman login**. Prinsip fase ini: **pekerjaan tidak
pernah hilang, dan tidak ada yang mengaku "terkirim" sebelum server benar-benar menerimanya.**

### Yang dibangun
- **Antrean di perangkat (IndexedDB)**: aksi *ajukan hasil* & *mulai dikerjakan* beserta **foto
  bukti (Blob)** disimpan di HP, terkirim otomatis saat sinyal kembali (juga dicoba ulang tiap
  30 detik) — bertahan walau aplikasi ditutup / HP mati.
- **Idempotensi berlapis (`client_ref`)**: kirim ulang **tidak** membuat pengajuan/bukti kedua.
  Server (a) memutar ulang hasil lama bila penanda sudah pernah diterima, (b) **mengunci penanda
  sebelum item disentuh** (`build_submit_claims`, indeks unik) sehingga **dua tab** tidak bisa
  mengirim berbarengan, (c) **melepas kunci bila pengajuan ditolak** supaya mandor bisa
  memperbaiki lalu mengirim ulang, (d) kunci basi (proses mati) boleh diambil ulang.
  Id foto lokal ditukar id server **sebelum** lanjut → foto tidak pernah terunggah dua kali.
- **Antrean yang jujur & bisa diperiksa**: panel antrean menampilkan status (Menunggu jaringan /
  Sedang dikirim / **Ditolak server**) + **alasan asli server**, jumlah percobaan, tombol *Kirim*
  & *Hapus*. Label diambil dari **SSOT `/api/reference`** (grup baru `offline_queue_status` &
  `offline_queue_kind`) — bukan peta hardcode. Antrean bisa dibuka **dari halaman mana pun**
  lewat spanduk jaringan (antrean milik perangkat, bukan milik satu tab).
- **Bisa dipakai saat offline, bukan cuma "tidak error"**: cuplikan papan per proyek + waktunya,
  cadangan **sesi**, **kamus pilihan** (checklist mutu), dan **daftar proyek** di perangkat;
  service worker menyimpan kerangka aplikasi (network-first) tetapi **`/api/` tidak pernah
  di-cache** supaya data operasional tidak menyamar sebagai data terkini. Manifest PWA → bisa
  dipasang di layar utama HP.
- **Penjaga Fase 31/32 tetap utuh lewat jalur antrean**: urutan tidak bisa dilangkahi, foto
  minimal & checklist KRITIS tetap diperiksa server, pemisahan tugas & RBAC tetap, jalur Work Hub
  generik tetap ditolak, dan **foto daur ulang tetap ditolak** (terbukti di layar: antrean
  menampilkan "Foto ... IDENTIK dengan bukti pekerjaan ... unggah foto asli").

### Cacat yang DITEMUKAN & DIPERBAIKI saat POC (bukan diakali)
| Cacat | Akibat sebelum diperbaiki |
|---|---|
| `PhotoUploader` memakai `sync.*`/`OFFLINE.*` tanpa import | layar merah begitu dialog "Ajukan hasil" dibuka |
| `refRef` dipakai tanpa dideklarasikan (`BuildItemDialogs`) | pengajuan gagal / penanda idempoten tidak terkirim |
| `online` dipakai tanpa diambil dari context | **Uncaught ReferenceError** → dialog tidak bisa dibuka |
| Payload kartu papan hanya mengirim JUMLAH checklist | pengajuan dari Papan Mandor berangkat tanpa jawaban checklist → **ditolak server**; saat offline penolakan baru terlihat setelah antrean terkirim |
| Muat ulang saat offline → `/auth/me` gagal | mandor **terlempar ke halaman login**, papan & antrean tak terlihat |
| Daftar proyek & kamus pilihan tanpa cadangan | halaman terjebak "Pilih proyek"; dropdown checklist kosong → tidak bisa mengajukan |
| Antrean hanya tampil di tab Papan Mandor | saat offline halaman lain gagal memuat → antrean tak bisa diperiksa/dicoba ulang |
| Balapan dua tab pada `client_ref` yang sama | bukti dobel + jejak audit kedua gagal (500) |
| `build_submit_claims` tanpa pemilik/pembersih | koleksi "mati" (temuan HIGH audit forensik) → sekarang terdokumentasi + TTL 7 hari |

### Bukti penutupan Fase 35 (jangan dihapus)
| Bukti | Hasil |
|---|---|
| `python3 scripts/poc_35.py` (API nyata) | **43 PASS / 0 FAIL** |
| `python3 scripts/verify_35.py` (gate baru) | **52 PASS / 0 FAIL** |
| `bash scripts/run_all_gates.sh` | **OVERALL PASS (16 gates)** |
| Browser NYATA (Playwright, offline sungguhan) | ajukan offline → antre (`pending`, "3 foto bukti ikut tersimpan") → **muat ulang saat offline: sesi & papan & antrean tetap ada** → ajukan pekerjaan ke-2 dari cuplikan → sinyal kembali → **terkirim sendiri** ("1 pekerjaan tersimpan berhasil dikirim ke server"), **0 error konsol** |
| Penolakan server terbukti jujur | baris antrean berubah **"Ditolak server — perlu tindakan"** + alasan asli (foto identik), bukti TIDAK dihapus, tombol *Kirim* tersedia |
| Anti-dobel terbukti | kirim ulang penanda sama → `replay=true`, jejak audit tetap **1**, foto tetap **3**, tugas verifikasi tetap **1**; dua kiriman berbarengan → tetap **1** jejak, tanpa 500 |

### Catatan teknis untuk fase berikutnya
- `backend/reference.py` sudah di batas 800 baris → pemuatan grup fase kini **dinamis**
  (`_PHASES` tuple). Fase baru: buat `reference_p<NN>.py` + tambahkan nomornya.
- Payload `build/board/today` kini memuat `checklist` lengkap. Bila menambah field baru,
  ingat bahwa payload ini juga dipakai sebagai **cuplikan offline**.
- Antrean SENGAJA hanya untuk aksi milik pelaksana (`build_submit`, `build_start`).
  Verifikasi/penolakan supervisor **tidak boleh** diantrekan offline karena harus melihat
  bukti terbaru dari server.

---


## ✅ FASE 34 — JADWAL MASSAL PER BLOK/CLUSTER + GESER TANGGAL SERENTAK (SELESAI & TERVERIFIKASI)

### Bukti penutupan Fase 34 (jangan dihapus)
| Bukti | Hasil |
|---|---|
| `bash scripts/run_all_gates.sh` (termasuk `verify_34.py`) | ✅ **OVERALL PASS (15 gates)** pada DB bersih |
| `python3 scripts/poc_34.py` | ✅ **57 PASS / 0 FAIL** (INV-34-1..9 + RBAC + regresi Fase 31/32) |
| `python3 scripts/verify_34.py` | ✅ **40 PASS / 0 FAIL** |
| `poc_31` / `poc_32` / `poc_33` | ✅ 63/63 · 79/79 · 66/66 — tanpa regresi |
| testing_agent iterasi **46** | ✅ dialog jadwal massal (14 kandidat, kavling nonaktif + alasan), gelombang bertahap + jeda hari, pratinjau (11 rumah / 208 pekerjaan, tanggal per blok berbeda), dialog geser + validasi wajib + tombol disabled, pratinjau geser (A-01: 6 dikunci) |
| testing_agent iterasi **47** | ✅ EKSEKUSI jadwal massal (**4/18 → 15/18**, banner hilang), EKSEKUSI geser **+21 hari** (279 pekerjaan bergeser, 9 terverifikasi dipertahankan), riwayat operasi massal 2 entri dengan pelaku+alasan, notifikasi "Tenggat pekerjaan Anda berubah" ke pelaksana, RBAC site (0 tombol) & owner (ada) |
| testing_agent iterasi **48** (final) | ✅ **40/42 asersi**; 2 sisa = artefak penghitungan tester (bukan bug, sudah dibuktikan ulang main agent) |
| **INV-34-1 dibuktikan DI LAYAR** | ✅ setelah geser +21 hari (dan +7 hari lagi), keenam pekerjaan terverifikasi A-01 TETAP bertanggal 2 / 8 / 11 / 13 / 16 / 24 Juli 2026, sementara jadwal unit pindah 1 Jul → 22 Jul → 29 Jul dan pekerjaan belum selesai maju |
| **INV-34-9 dibuktikan DI LAYAR** | ✅ geser −170 hari → pita konflik "3 jadwal tidak bisa digeser sejauh itu…", baris merah menyebut tanggal bukti, tombol hanya menawarkan **"Geser 12 jadwal"** (bukan 15) |
| **INV-34-8 dibuktikan DI LAYAR** | ✅ klik ganda tombol jalankan: tombol nonaktif saat proses, A-01 bergeser TEPAT 7 hari sekali (22 Jul → 29 Jul), riwayat berisi TEPAT 2 baris |
| Riwayat & jejak audit | ✅ `GET /build/bulk/runs` memuat 'Jadwal massal' & 'Geser tanggal serentak' (pelaku, waktu, angka, penyebab, catatan); `audit_logs` memuat `bulk_create` & `bulk_shift` |
| RBAC | ✅ pelaksana MELIHAT tapi tidak punya tombol (API `can.configure=false`), sales ditolak dengan kartu **"AKSES DITOLAK"** + jalan keluar, owner/PM penuh |
| Regresi Fase 31/32/33 | ✅ Papan Mandor, Laporan & Analitik, Antrean Kerja normal; `spk-scope-section` SPK/2026/0003 tetap 4 metrik + 10 baris; RAB tab Kendali Biaya tetap 472jt/66jt/30jt |
| Error konsol | ✅ 0 error aplikasi (hanya peringatan CDN/WebSocket dev) |

### Catatan jujur (dua "temuan" yang TERBUKTI bukan bug)
1. Iterasi 46 melaporkan "site engineer melihat tombol operasi massal" → **tidak terjadi pada sesi bersih**
   (0 tombol; API mengembalikan `can.configure=false`). Penyebab: token PM masih tersimpan di
   `localStorage` saat tester berganti peran. Sejak itu instruksi uji mewajibkan membersihkan sesi.
2. Iterasi 48 melaporkan "`spk-scope-metrics` hanya 1 metrik" → `spk-scope-metrics` adalah **satu
   wadah grid** berisi 4 kartu metrik (terbukti: Nilai lingkup 66jt · Terverifikasi 30jt ·
   Sudah ditagih 0 · Siap ditagih 30jt), dan `boq-cost-control` tampil normal setelah tab diklik.

### Rincian rencana Fase 34 (arsip, sudah dikerjakan)

**Masalah bisnis yang ditutup (nyata, terlihat di data demo):**
1. **14 dari 18 rumah tidak punya jadwal** karena penjadwalan harus satu-satu. Rumah tanpa
   jadwal = tanpa tenggat, tanpa pengingat, tanpa eskalasi, dan progresnya tidak terhitung.
   Untuk proyek 50–200 unit ini mustahil dikerjakan manual.
2. **Ketika proyek mundur** (hujan, material telat, izin), tanggal seluruh rumah harus
   digeser. Sebelum fase ini satu-satunya cara adalah **MENGHAPUS lalu membuat ulang jadwal**
   — yang **membakar bukti kerja** (foto + checklist + verifikasi Fase 31/32) dan memutus
   jejak audit. Praktiknya: orang memilih membiarkan tanggal salah → laporan telat jadi palsu.

**Prinsip Fase 34:** *jadwal boleh bergerak, bukti tidak boleh hilang.*

### Invarian (ditegakkan backend, diuji `poc_34.py`, dijaga `verify_34.py`)
- **INV-34-1** Pekerjaan yang SUDAH selesai & terverifikasi tidak boleh berubah tanggal.
- **INV-34-2** Geser massal WAJIB beralasan (SSOT `build_delay_cause`) + catatan ≥10 huruf.
- **INV-34-3** Jadwal massal tidak menimpa jadwal berjalan (dilewati + alasan manusiawi).
- **INV-34-4** Unit tipe non-bangunan (Kavling) tidak bisa dijadwalkan.
- **INV-34-5** Hanya Manajer Proyek/direksi; pelaksana boleh MELIHAT, sales tidak.
- **INV-34-6** Pratinjau = hasil (satu fungsi hitung dipakai keduanya); pratinjau tidak menulis.
- **INV-34-7** Setelah geser: gerbang & progres dihitung ulang → tidak ada "telat" palsu.
- **INV-34-8** Batas 100 unit/operasi + `client_ref` idempoten (klik ganda tidak dobel).
- **INV-34-9** Geser ke belakang tidak boleh menaruh pekerjaan belum selesai SEBELUM
  pekerjaan yang sudah diverifikasi.

### 34a — Mesin & model (SELESAI)
`backend/build_bulk.py` (blok, kandidat, `plan_create`/`run_create`, `plan_shift`/`run_shift`,
riwayat operasi), `models_p34.py`, `reference_p34.py` (SSOT `build_bulk_wave`,
`build_shift_scope`), koleksi baru `build_bulk_runs` + index unik `(org_id, kind, client_ref)`.

### 34b — Endpoint (SELESAI)
`routers/build_bulk_router.py`: `GET /build/bulk/blocks`, `GET /build/bulk/candidates`,
`POST /build/bulk/schedules/preview`, `POST /build/bulk/schedules`,
`GET /build/bulk/shift/targets`, `POST /build/bulk/shift/preview`, `POST /build/bulk/shift`,
`GET /build/bulk/runs`.

### 34c — POC (SELESAI) — `scripts/poc_34.py` → **57 PASS / 0 FAIL**

### 34d — Frontend (SELESAI)
`BulkScheduleDialog.js` (saring blok/tipe, pilih massal, pola gelombang serentak/bertahap +
jeda hari, pratinjau tabel, hasil per unit), `BulkShiftDialog.js` (cakupan proyek/blok/pilihan,
geser ±hari, penyebab + catatan wajib, pratinjau dampak digeser-vs-dikunci, konflik bukti),
`BulkRunsPanel.js` (riwayat operasi massal), `ShiftHistoryPanel.js` (riwayat geser per unit),
tombol **Jadwal massal** / **Geser jadwal** + CTA pada banner "rumah belum terjadwal".

### 34e — Verifikasi
`scripts/verify_34.py` → **40 PASS / 0 FAIL**, masuk `run_all_gates.sh` (**15 gates**).
testing_agent_v3 iterasi **46 → 47 → 48**: LULUS (lihat tabel bukti di atas §FASE 34).

### User stories Fase 34 (dipakai testing agent)
1. PM melihat berapa rumah belum terjadwal per blok, lalu menjadwalkan sekaligus dari satu dialog.
2. PM memilih pola mulai bertahap (jeda hari per blok/unit) karena tukang tak bisa masuk serentak.
3. Pratinjau menunjukkan tanggal mulai, target selesai, dan jumlah pekerjaan per rumah SEBELUM dijalankan.
4. Unit yang sudah punya jadwal otomatis dilewati dengan alasan (jadwal & bukti tidak ditimpa).
5. Unit kavling/tanah ditolak dengan alasan yang bisa dimengerti.
6. Klik ganda tombol jalankan tidak membuat jadwal dobel.
7. PM menggeser tenggat seluruh proyek/blok saat hujan berkepanjangan — dengan penyebab + catatan wajib.
8. Pratinjau geser menunjukkan tanggal lama → baru, berapa pekerjaan bergeser, dan berapa
   pekerjaan terverifikasi yang tanggalnya dipertahankan.
9. Geser yang melangkahi bukti (mundur terlalu jauh) ditolak dengan alasan jelas.
10. Setelah digeser, pekerjaan tidak lagi tercatat "telat" palsu; pelaksana menerima notifikasi.
11. Riwayat penggeseran terlihat di sheet jadwal unit dan di panel riwayat operasi massal
    (siapa, kapan, berapa hari, alasan).
12. RBAC: pelaksana boleh melihat, tidak boleh menjalankan; sales tidak boleh melihat.
