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

### ✅ Objective D (BARU) — Construction Progress Engine v2 (P0)
**FASE 31 BARU (permintaan owner): CONSTRUCTION PROGRESS ENGINE v2 — Jadwal Berbukti, Gerbang Mutu, Reminder & Eskalasi, per TIPE UNIT.**

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

## Phase 31 — Construction Progress Engine v2 (P0)
> Fokus baru owner. Dibagi menjadi 31a/31b/31c/31d agar bisa diuji bertahap dan gates tetap hijau.

### Input permintaan owner (SSOT requirement, jangan disederhanakan)
"fokus dulu pada construction progress contoh default
MINGGU 1 — PEKERJAAN PERSIAPAN + PONDASI
Hari 1–2
Pekerjaan Persiapan
Pembersihan lokasi
Pengukuran
Bowplank
QC Check
✅ As bangunan sesuai siteplan
✅ Elevasi lantai aman dari jalan/drainase
Hari 3–7
Pekerjaan Tanah & Pondasi
Galian pondasi
Urugan pasir
Pasangan batu belah
Hold Point
❌ Tidak boleh lanjut sloof jika pondasi belum benar-benar terkunci
Waktu tunggu
Pondasi batu kali minimal 1–2 hari
MINGGU 2 — STRUKTUR BAWAH
Hari 8–14
Pekerjaan Struktur
Sloof
Kolom praktis
Talang beton
Hari 8–10
Pembesian + bekisting
Hari 11
Pengecoran
Hari 12–14
Curing beton
Hold Point penting
❌ Bekisting jangan dibuka terlalu cepat
Minimal:
Bekisting samping: 24 jam
Beban berat: 7 hari
Kuat optimal: 28 hari
MINGGU 3 — DINDING
Hari 15–21
Pekerjaan Dinding
Pasangan bata merah
Jalur plumbing tanam
Jalur conduit listrik tanam
Karena di RAB plumbing dan ME sudah ada, idealnya jalur tanam dilakukan bersamaan sebelum plester.
Hold Point
❌ Jangan plester langsung setelah pasangan bata selesai
Tunggu:
Minimal 3–5 hari
Tujuan:
Mortar bata stabil
Mengurangi retak rambut
MINGGU 4 — RING BALOK + ATAP
Hari 22–27
Hari 22–24
Ring balk
Ring gevel
Hari 25–27
Rangka atap baja ringan
Genteng metal
Lisplank
Atap spandek
Hold Point
❌ Jangan lanjut plafon jika atap masih bocor
Lakukan:
Tes siram air
Cek kemiringan talang
MINGGU 5 — PLESTER + ACIAN
Hari 28–35
Plester dinding
Acian
Ideal jeda:
Setelah plester → tunggu 3 hari
Setelah acian → tunggu 7 hari
Hold Point
❌ Jangan cat saat dinding masih basah
Risiko:
Cat menggelembung
Lembab
Jamur
MINGGU 6 — PLAFON + KUSEN
Hari 36–41
Pekerjaan Plafond
Hollow
Gypsum
List gypsum
Pekerjaan Kusen
Kusen pintu
Daun pintu
Kusen jendela
Kaca
Dependency
Ideal setelah rumah sudah tertutup atap agar material tidak rusak terkena hujan
MINGGU 7 — KERAMIK + SANITASI
Hari 42–47
Penutup lantai
Keramik lantai utama
Keramik kamar mandi
Keramik dinding KM
Keramik backsplash dapur
Sanitasi
Closet
Kran
Sink dapur
Septictank
Jalur air bersih
QC
✅ Test aliran air
✅ Cek kemiringan floor drain
✅ Cek keramik kopong
MINGGU 8 — LISTRIK + CAT + PEKERJAAN LUAR
Hari 48–54
ME
Lampu
Saklar
Stop kontak
Cat
Interior
Exterior
Plafond
Lisplank
Luar bangunan
Carport
Dinding samping
Taman
MINGGU 9 — FINAL CHECK
Hari 55–60
Pembersihan akhir
Repair defect
Final QC
Siap akad / serah terima
KRITIKAL PATH YANG PALING SERING MENYEBABKAN CACAT
Ini yang harus dikontrol supervisor:
Pekerjaan	Minimal tunggu
Pondasi → Sloof	1–2 hari
Cor sloof → Bata	3–7 hari
Bata → Plester	3–5 hari
Plester → Acian	2–3 hari
Acian → Cat	7–14 hari
Atap → Plafon	setelah tes bocor
Keramik → Sanitair	setelah nat kering

untuk contruction progress saat ini fiturnya masih minus fungsi tidak fungsionalitas sangat bodoh. tragetnya adalah memonitoring construction harus berjalan sesuai dengan target waktu ada remindernya ada ekskalasi jika telat harus ada proffnya agar benar benar mengikuti spek jadi system harus fungsional mulai dari pengamanan agar tidak terjadi kecurangan monitoring, dan penjaga agar tidak lewat dari guideline, nah progress juga bisa tergantung tipe jadi harus bisa di custom juga ditambahkan detailnya bisa dikonfiguraasi. analisis dan kembangkan, jangan bodoh jangan membuat duplikasi enchance fitur yang sudah ada, pastikan field dan data collection nya jelas tidak asal ambil data apa lagi custom value melainkan logic yang benar dropdown sesuai data yang dituju. unit juga harus mengikat pada lead ingat lead dan unit jika lead sudah dibeli maka ada relasinya jadi coba sekalian revisi cacat logika yang ada"

### Analisis kode yang sudah ada (agar TIDAK duplikasi)
- `routers/construction_router.py`: fase LEVEL PROYEK (`construction_phases`) + progres manual % diketik + `construction_logs` (foto base64 legacy) + QC ad-hoc.
- `engine.recompute_project_progress()` **CACAT KRITIS D-A**: menimpa `construction_progress` & `construction_status` semua unit dengan angka proyek → progres per unit palsu/seragam.
- `engine.build_s_curve()` Kurva-S berbasis `planned_pct` manual → tidak ada jadwal kalender → tidak bisa reminder/eskalasi berbasis tanggal.
- `routers/inspection_router.py` + `inspection_templates` + `inspections` + `punch_items`: QC per fase sudah ada dan bagus → **HARUS dipakai ulang**.
- Work Hub v2 (`workhub.py`, `routers/workhub_router.py`, `jobdesk_catalog.py`): workflow task + SLA + notifikasi + sweeper → **HARUS dipakai ulang** untuk reminder/eskalasi & verifikasi.
- Foto proof: `PhotoUploader` + `/files/upload` (kompresi, watermark, EXIF/GPS dibuang) → **HARUS dipakai** (ganti base64 legacy).
- SSOT `reference.py` + `ReferenceSelect`: semua dropdown wajib dari SSOT.
- Relasi unit↔pembeli: saat ini via `units.booked_by_deal`/`reserved_by_deal` → `deals.lead_id` → lead; **cacat D-F**: unit tidak punya `lead_id/customer_id/deal_id` eksplisit.

### Cacat logika yang harus direvisi (temuan analisis)
- **D-A**: progres unit = progres proyek (ditimpa massal) → progres per unit harus dihitung dari pekerjaan terverifikasi.
- **D-B**: progres = angka diketik manual tanpa bukti → wajib proof + verifikasi.
- **D-C**: tidak ada jadwal tanggal/dependensi/waktu tunggu → tidak ada reminder & eskalasi nyata.
- **D-D**: tidak ada template pekerjaan per tipe unit; `unit.type` bebas.
- **D-E**: QC dialog memakai foto base64 legacy → bukti lemah.
- **D-F**: unit tidak terikat lead/customer/deal secara eksplisit.
- **D-G**: jobdesk TK-02 masih level proyek.

---

### Phase 31a — POC engine (P0) — ✅ SELESAI (63 PASS / 0 FAIL)
**Output**: `scripts/poc_31.py` (dan/atau `scripts/verify_31_poc.py`) yang membuktikan core invariant.
- Template default **9 minggu / 60 hari** (rumah tapak) sesuai input owner.
- Generate **jadwal per unit** berbasis tanggal kalender:
  - konfigurasi hari kerja (default **6 hari/minggu**, Minggu libur)
  - due date per item, dan timeline minggu→hari.
- Gerbang (hard guard):
  - predecessor harus **terverifikasi**
  - waktu tunggu curing terpenuhi
  - hold point memblokir item berikutnya
- Bukti wajib:
  - minimal foto + checklist QC kritis (sesuai tahap)
  - proof memakai **file_id** object storage (bukan base64)
- Progres berbobot dari item terverifikasi.
- Anti-kecurangan minimal:
  - deteksi foto daur ulang (hash SHA-256 per file_id)
  - SoD: pengaju ≠ verifikator
  - override supervisor beralasan (tercatat)
- Reminder/eskalasi berbasis tanggal (simulasi event): due soon/overdue.

**Definition of Done (31a)**
- POC menghasilkan jadwal & guard sesuai rule.
- Minimal 30 asersi lulus pada script POC.

---

### Phase 31b — Backend (P0) — ✅ SELESAI (tanpa regresi QC/Inspection/WorkHub)
**Tujuan**: menambah engine v2 TANPA merusak modul existing.

1) **SSOT & Models**
- Tambah `reference_p31.py` untuk enum baru (mis: `build_template_code`, `build_item_status`, `build_hold_reason`, `build_proof_kind`, `build_override_reason`).
- Tambah `models_p31.py` untuk request/response:
  - `BuildTemplateCreate/Update`
  - `BuildScheduleGenerate`
  - `BuildItemSubmit` (proof file_ids + checklist)
  - `BuildItemVerify/Reject/Override`

2) **Collections (jelas, minim duplikasi)**
- `build_templates` (template per `unit_type` dan per `project_id` opsional).
- `build_schedules` (schedule instance per `unit_id` + tanggal mulai + parameter kalender).
- `build_items` (item pekerjaan granular: minggu/hari, dependensi, hold, due_date, status).
- `build_item_submissions` (audit trail proof, siapa, kapan, hash foto).

3) **Router baru**
- `routers/build_router.py` prefix `/build`:
  - `GET /build/templates` (filter per unit_type)
  - `POST /build/templates` (PM/owner)
  - `PUT /build/templates/{id}`
  - `POST /build/schedules/generate` (generate schedule untuk unit)
  - `GET /build/unit/{unit_id}/schedule`
  - `POST /build/items/{item_id}/submit` (staf; proof wajib)
  - `POST /build/items/{item_id}/verify|reject|override` (supervisor; SoD)
  - `GET /build/units/board` (monitoring: deviasi hari, blocked oleh hold, overdue)

4) **Integrasi Work Hub v2 (tanpa duplikasi engine tugas)**
- Jobdesk baru:
  - **TK-10**: Item pekerjaan unit telat (eskalasi otomatis)
  - **TK-11**: Verifikasi hasil pekerjaan unit (queue supervisor)
- Scheduler tick:
  - reminder H-1 untuk item due
  - eskalasi overdue (idempotent) ke supervisor + notifikasi.

5) **Fix cacat D-A: jangan menimpa unit**
- Ubah `engine.recompute_project_progress()`:
  - hanya update `projects.construction_progress`.
  - **hapus** update massal `units.construction_progress`.
- Tambah `recompute_unit_progress(unit_id)` berbasis data `build_items` terverifikasi.

6) **Fix cacat D-F: relasi unit↔deal/lead/customer**
- Denormalisasi eksplisit:
  - `units.deal_id`, `units.lead_id`, `units.customer_id` (nullable)
- Migrations + seed update:
  - saat reserve/book/sold update field-field ini.
  - invariant check di `scripts/verify_data_integrity.py`.

**Definition of Done (31b)**
- API build engine berjalan, idempotent, RBAC benar.
- Tidak ada regresi pada modul QC/Inspection/WorkHub.
- `bash scripts/run_all_gates.sh` tetap **PASS (11)**.

---

### Phase 31c — Frontend (P0) — ✅ SELESAI (5 tab + semua dialog + portal pembeli)
**Tujuan**: ConstructionPage jadi monitoring yang benar, bukan input manual bodoh.

- `ConstructionPage` jadi bertab (tanpa duplikasi):
  1. **Monitoring Unit**: papan per unit (progress nyata, deviasi hari, blocked/hold, overdue, link ke jadwal).
  2. **Jadwal Unit**: sheet detail minggu→item + status + guard + dialog Ajukan Hasil.
  3. **Infrastruktur Proyek**: fase proyek existing (`construction_phases`) tetap ada untuk pekerjaan umum.
  4. **QC & Inspeksi**: panel `InspectionsPanel` existing.
  5. **Template Jadwal**: editor untuk PM/owner (per `unit.type`).

- Dialog **Ajukan Hasil**:
  - checklist QC kritis sesuai item
  - proof foto wajib via `PhotoUploader` (file_id, watermark konteks)
  - catatan kerja wajib (SSOT).

- Dialog **Verifikasi/Tolak/Override**:
  - SoD: UI menolak jika verifikator sama dengan submitter
  - alasan wajib untuk reject/override (SSOT).

- Semua dropdown dari `ReferenceSelect` SSOT; tidak ada free-text untuk enum.

**Definition of Done (31c)**
- UI monitoring bisa dipakai supervisor/staf; anti-loncat bekerja.
- Portal pelanggan menampilkan progress unit **nyata** (bukan progress proyek).
- 0 error konsol; `ux_audit.py` lulus.

---

### Phase 31d — Verifikasi & Testing (WAJIB) — ✅ SELESAI
- `scripts/verify_31.py` (assertions end-to-end): schedule, hold, wait time, proof required, SoD, overdue escalation, unit progress. → **30 PASS / 0 FAIL**
- `scripts/poc_31.py` → **63 PASS / 0 FAIL**.
- Gates: `bash scripts/run_all_gates.sh` → **PASS (12 gates)**.
- **testing_agent_v3**: iterasi 40 (backend 60/62 + frontend) dan iterasi 41 (fokus user story sisa) → **0 bug kritis, 0 bug medium**.

---

## ✅ PHASE 31 — SELESAI & TERVERIFIKASI (Construction Progress Engine v2)

### Bukti per user story (testing_agent_v3 iter. 40–41 + verifikasi manual main agent)
| US | Fitur | Status |
|---|---|---|
| US-1 | Papan pantau per rumah (progres vs rencana, telat, tertahan gerbang, override, pagination, laporan penyebab telat) | ✅ PASS |
| US-2 | “Jalankan pemantauan” + panel hasil MENETAP `build-tick-result` (jadwal diperiksa, gerbang dibuka, pengingat, eskalasi) | ✅ PASS |
| US-3 | Sheet jadwal unit: 9 minggu / 20 item, metrik, kurva rencana-vs-realisasi, alasan terkunci, hold point, foto bukti termuat | ✅ PASS |
| US-4 | PM melihat & memakai tombol Verifikasi/Kembalikan pada item `submitted`; progres unit naik sesuai BOBOT | ✅ PASS |
| US-5 | Kembalikan pekerjaan: validasi inline `build-reject-hint`, tombol disabled, item → `rework`, tugas perbaikan lahir untuk pelaksana | ✅ PASS |
| US-6 | Pelaksana ajukan hasil: uraian + checklist SSOT + **unggah foto nyata** (3 foto berbeda; foto duplikat ditolak) → `submitted` → diverifikasi PM | ✅ PASS |
| US-7 | Anti-loncat: item terkunci tanpa tombol kerja + alasan jelas; pelaksana tidak melihat tombol verifikasi/override | ✅ PASS |
| US-8 | Override gerbang: alasan SSOT + penjelasan ≥15 karakter, tercatat di audit, direksi dinotifikasi | ✅ PASS |
| US-9 | Penyebab telat dari dropdown SSOT (bukan teks bebas) → masuk laporan | ✅ PASS |
| US-10 | Hentikan sementara / lanjutkan jadwal + validasi inline | ✅ PASS |
| US-11 | Buat jadwal unit (9 minggu/20 item), unit hilang dari daftar “belum dijadwalkan”, Kavling tanah ditolak sopan | ✅ PASS |
| US-12 | Template per tipe unit: edit + simpan (versi naik), peringatan total bobot, duplikat template, read-only untuk pelaksana | ✅ PASS |
| US-13 | RBAC: sales tidak melihat menu & mendapat kartu sopan `construction-access-denied`; finance view-only | ✅ PASS |
| US-14 | Kartu “Pembangunan rumah” di Beranda + CTA ke monitoring | ✅ PASS |
| US-15 | Portal pembeli: progres RUMAH nyata (A-01 33% vs rencana 66%, telat 21 hari) + 9 tahapan mingguan; pekerjaan kawasan dipisah | ✅ PASS |
| US-16 | Regresi: tab Infrastruktur Kawasan & QC/Inspeksi, halaman /field /permits /projects /tasks /notifications normal, tanpa error konsol | ✅ PASS |

### Perbaikan tambahan pada sesi penutupan Fase 31
1. **Titik berhenti sesi sebelumnya diselesaikan**: `BUILD.submitRequirements` belum terdaftar di `constants/testIds/build.js` → ditambahkan; panel syarat pengajuan (`build-submit-requirements`) kini menyebut satu per satu kekurangan (uraian <10 karakter, foto kurang, checklist belum lengkap, item KRITIS gagal) dan tombol “Ajukan Hasil” nonaktif sampai lengkap.
2. **Validasi inline konsisten** (komponen `Hint` dipakai bersama): `build-reject-hint`, `build-override-hint`, `build-delay-hint`, `build-hold-hint` — tidak lagi hanya toast yang mudah terlewat, dan tombol simpan disabled selama syarat belum lengkap.
3. **Hasil pemantauan menetap** `build-tick-result` (sebelumnya hanya toast sekejap).
4. **Cacat UX RBAC diperbaiki**: peran tanpa izin (mis. sales) dulu melihat halaman utuh + DUA pesan teknis berulang yang membocorkan nama izin internal (`tidak memiliki izin 'view' pada 'construction'`). Sekarang satu kartu sopan `AccessDenied` (`components/patterns/StateViews.js`) + tombol kembali ke Beranda, tab tidak dirender.
5. **Kejujuran data portal**: `build_monitor.buyer_milestones()` tidak lagi menampilkan tanggal “disetujui” pada minggu yang baru sebagian selesai (dulu pembeli bisa mengira tahapan sudah tuntas).
6. **PhotoUploader** dipoles (tombol berkas bergaya tema, tetap `<input type=file>` asli agar bisa diuji otomatis).

---

## 3) Next Actions (immediate)
Fase 31 sudah **selesai & terverifikasi**. Kandidat pekerjaan berikutnya (belum dikerjakan):
1. **Jadwal massal per blok/cluster** — buat jadwal untuk banyak unit sekaligus (11 unit masih belum terjadwal) + geser tanggal massal saat proyek delay.
2. **Papan mandor harian (mobile-first)** — satu layar “hari ini” untuk pelaksana: pekerjaan hari ini, foto langsung dari HP, tanpa masuk sheet.
3. **Kurva-S kawasan vs rumah dalam satu grafik** + ekspor laporan progres mingguan (PDF) untuk direksi/investor.
4. **Analitik penyebab telat** — pekerjaan paling rawan telat per tipe unit & per pelaksana, jadi template bisa dikalibrasi dari data nyata.
5. **Integrasi RAB/BoQ ↔ item jadwal** — progres terverifikasi menarik opname/termin pembayaran subkontraktor (mengurangi klaim fiktif).
6. **WhatsApp Cloud API nyata** (butuh kredensial Meta) untuk pengingat & eskalasi ke pelaksana/pembeli.

## 3b) Catatan pemeliharaan
- Setelah pull/restore repo, WAJIB cek `/app/backend/.env` memuat `JWT_SECRET` & `EMERGENT_LLM_KEY` (file `.env` di-gitignore) — bila hilang, login akan 500.
- Selalu jalankan `bash scripts/run_all_gates.sh` + `python3 scripts/poc_31.py` sebelum menyatakan fase selesai.

---

## 4) Success Criteria
- ✅ WorkHub berfungsi sesuai domain divisi dan menjadi penggerak kerja.
- ✅ Lead lifecycle menjadi gerbang bukti; WA terintegrasi; stage tidak loncat.
- ✅ Construction Progress Engine v2:
  - Jadwal **kalender** per unit (per tipe) + reminder & eskalasi.
  - Tidak bisa loncat tanpa bukti; ada hold point & waktu tunggu.
  - Progres unit **nyata**, bukan ditimpa dari proyek.
  - Proof memakai object storage + watermark + audit trail.
  - Unit terikat lead/deal/customer dengan jelas.
- ✅ Semua perubahan menjaga compliance (py<800, js<500, util<300, css<400) dan `bash scripts/run_all_gates.sh` tetap PASS (11 gates).

---

## ✅ FASE 29 — SELESAI & TERVERIFIKASI (Work Hub v2 + Lead Lifecycle + UI/UX)
> Bagian ini dipertahankan (ringkasan implementasi 29a/29b/29c/29d + bukti verifikasi) dan menjadi fondasi untuk Phase 31.

### Belum termasuk (jujur, kandidat fase setelah 31)
BI/SLIK checking nyata (butuh jalur legal), WhatsApp Cloud API nyata (butuh kredensial Meta), heatmap kepadatan minat, halaman publik multi-proyek.
