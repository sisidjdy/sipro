# plan.md — SIPRO — Lanjut Development (Slice A + Slice B + Slice Finance) — Fokus: MVP end-to-end

## ✅ STATUS (update terakhir — Fase 31 SELESAI & TERVERIFIKASI)
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

## 3) Next Actions (immediate)
Fase 31 & 32 sudah **selesai & terverifikasi**. Kandidat berikutnya (belum dikerjakan):
1. **Jadwal massal per blok/cluster** — buat jadwal banyak unit sekaligus + geser tanggal serentak saat proyek mundur (masih ada unit belum terjadwal).
2. **Terapkan rekomendasi kalibrasi sekali klik** — dari Analitik Telat langsung mengubah durasi/waktu tunggu pada template (sekarang masih manual di editor).
3. **Integrasi RAB/BoQ ↔ item jadwal** — progres terverifikasi menarik opname/termin subkontraktor (mengurangi klaim fiktif).
4. **Ringkasan laporan mingguan via WhatsApp** (butuh kredensial Meta; saat ini WA masih simulasi).
5. **Papan mandor offline-tolerant** — antrean unggahan bila sinyal lapangan hilang.

## 3b) Catatan pemeliharaan
- Setelah pull/restore repo, WAJIB cek `/app/backend/.env` memuat `JWT_SECRET` & `EMERGENT_LLM_KEY` (file `.env` di-gitignore) — bila hilang, login akan 500.
- Selalu jalankan `bash scripts/run_all_gates.sh` + `python3 scripts/poc_31.py` sebelum menyatakan fase selesai.

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
