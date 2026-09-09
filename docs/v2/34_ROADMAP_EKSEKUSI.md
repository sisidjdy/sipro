# 34 — ROADMAP EKSEKUSI (Fase 39–51)

> Urutan mengikuti **D10**: **fondasi data & IA → CRM → BI → konsolidasi proyek/konstruksi**.
> Aturan tiap fase: (a) tidak boleh menurunkan gate yang ada (**sekarang 22 gate**), (b) wajib gate baru yang **diuji-mutasi**, (c) wajib user story yang dibuktikan di browser, (d) tutup fase dengan update `plan.md` + `test_result.md` + status di dokumen V2.
> Estimasi = ukuran relatif (S/M/L/XL), bukan janji waktu.
>
> **Status pelaksanaan:** **Fase 39 = SELESAI** (+ **39b** = penutupan wiring: checklist dokumen
> benar-benar dipakai di layar Lead & Pelanggan, akun GL dropdown SSOT, riwayat migrasi bisa
> diperiksa admin; gate baru `verify_39b.py`). **Fase 40 = BERIKUTNYA** (disetujui owner).
> Catatan bawaan untuk Fase 40: pindahkan `DocChecklist` dari drawer Lead ke halaman kanonik
> `/leads/:id`. Catatan untuk Fase 41: **INV-07** (gerbang tahap oleh dokumen wajib) sengaja
> BELUM ditegakkan di Fase 39b — itu pekerjaan Fase 41/42 bersama tahap `spr`.

## PEMETAAN NOMOR FASE — RENCANA vs YANG BENAR-BENAR DIKERJAKAN (WAJIB DIBACA)

> **Kenapa bagian ini ada.** Nomor fase di dokumen ini adalah RENCANA. Urutan pengerjaan
> nyata berubah (permintaan owner mendahulukan uang masuk, pengadaan, penutupan buku, serah
> terima). Akibatnya nomor yang sama menunjuk pekerjaan yang berbeda, dan **layar yang
> menulis “dijadwalkan Fase 43” tetap mati lama setelah Fase 43 selesai** — pemakai membaca
> janji yang tidak pernah datang. Cacat itu ditemukan pemakai pada tab *Kontrak & Harga*.
>
> **Aturan sejak sekarang:** layar TIDAK BOLEH menyebut nomor fase untuk hal yang belum ada.
> Tulis NAMA pekerjaannya (lihat `TabPage`: prop `soon` berisi nama, bukan nomor).

| Rencana (dokumen ini) | Kenyataan di kode | Bukti |
|---|---|---|
| F39 Fondasi Data & Wiring | ✅ Fase 39 + 39b | `verify_masterplan.py`, `verify_39b.py` |
| F40 IA & Design System V2 | ✅ Fase 40 | `verify_ia_v2.py` |
| F41 CRM Lead V2 | ✅ sebagian: profil lead kanonik + jam tahap/SLA (Fase 41) + gerbang tahap berbukti (Fase 29b). Gate `verify_crm_v2.py` tidak pernah dibuat | `verify_41.py` |
| F42 Reservasi/SPR + Generator Dokumen | ⚠️ generator dokumen ADA (template → finalize → tanda tangan → PDF); **modul reservasi/SPR terpisah belum** | `documents_router.py` |
| **F43 Customer, Kontrak & Rencana Bayar** | ❌ **BELUM** — `contracts`, `price_breakdown` per komponen, `payment_plans` 3 skema, toleransi tunggakan, mesin pembatalan/refund berjurnal, tahap legal PPJB/AJB/sertifikat. **Yang SUDAH ada dan kini ditampilkan:** penawaran (harga unit + add-on + diskon + skema) di tab *Kontrak & Harga*, serta jadwal termin AR + penerimaan + tunggakan di tab *Rencana Bayar* | `CustomerContractTab.js`, `CustomerPaymentPlanTab.js` |
| **F44 Alur KPR + BI Checking** | ❌ **BELUM** — `kpr_applications` bertahap (berkas → bank → appraisal → SP3K → akad → pencairan) + gerbang bukti + refund 50%; menu BI Checking mandiri. **Yang ada:** pengajuan KPR + SLIK + pencairan (`financing_router`) & simulasi KPR | `financing_router.py` |
| F45 Mitra & Fee | ✅ dikerjakan sebagai **Fase 42** | `verify_partner.py` |
| **F46 Agenda & Survey V2 + Inbox WA V2** | ⚠️ dasar ADA (agenda/appointment, inbox WA + SLA + NBA); **V2 belum**: kalender besar bulan/minggu/hari, alasan reschedule ber-SSOT + follow-up WA otomatis, form survei berversi, inbox virtualized + aksi massal | `leads_router.py`, `inbox_router.py` |
| F47 Marketing, Kampanye & Biaya Iklan | ✅ dikerjakan sebagai **Fase 43** | `verify_ads.py` |
| F48 Target & Budget/RAB | ✅ dikerjakan sebagai **Fase 45** | `verify_budget_target.py` |
| F49 Analytics & BI | ✅ dikerjakan sebagai **Fase 44** | `verify_analytics.py` |
| F50 Konsolidasi Proyek & Konstruksi | ✅ dikerjakan sebagai **Fase 46** | `verify_build_hub.py` |
| F51 Kesiapan Pembayaran (opsional) | ❌ belum — butuh kredensial kanal pembayaran yang nyata | — |

**Dikerjakan DI LUAR roadmap ini (permintaan owner, semua bergate):**

| Fase nyata | Isi | Gate |
|---|---|---|
| Fase 47 | Uang masuk terbukti (rekonsiliasi bank, bukti transfer portal) + absensi & upah harian | gate 31–33 |
| Fase 48 | Pengadaan & subkon lanjutan (vendor, 3-way match, uang muka, retensi, stok) | gate 34–36 |
| Fase 49 | Penutupan buku (bulan & tahun), paket laporan owner, e-Faktur & e-Bupot | gate 37–38 |
| Fase 50 | Serah terima unit (BAST) + masa garansi + klaim pasca-huni + antrean perangkat terpadu | gate 39–40 |

---

## Ringkasan

| Fase | Nama | Ukuran | Dokumen acuan | Gate baru |
|---|---|---|---|---|
| 39 ✅ | Fondasi Data & Wiring — **SELESAI** (+39b penutupan wiring) | XL | 22, 28, 33, 35 | `verify_masterplan.py`, `verify_settings.py`, **`verify_39b.py`** |
| 40 | IA & Design System V2 | L | 23 | `verify_ia_v2.py` (+perluas `verify_ui_surfaces.py`) |
| 41 | CRM Lead V2 (profil, aging, pipeline) | XL | 24 | `verify_crm_v2.py` |
| 42 | Reservasi/SPR + Generator Dokumen | L | 24 §5–§6, 26 §4, 27 | `verify_spr_docgen.py` |
| 43 | Customer, Kontrak & Rencana Bayar | XL | 26 | `verify_contract_v2.py` |
| 44 | Alur KPR + BI Checking terpisah | M | 26 §6, 24 §7 | `verify_kpr.py` |
| 45 | Mitra & Fee | M | 25 | `verify_partner.py` |
| 46 | Agenda & Survey V2 + Inbox WA V2 | L | 24 §10, 23 §6 | `verify_appointment_inbox.py` |
| 47 | Marketing, Kampanye & Biaya Iklan | M | 30 | `verify_ads.py` |
| 48 | Target & Budget/RAB | L | 32 | `verify_budget_target.py` |
| 49 | Analytics & BI | XL | 31 | `verify_analytics.py` |
| 50 | Konsolidasi Proyek & Konstruksi | L | 29 | `verify_build_hub.py` |
| 51 | Kesiapan Pembayaran (opsional) | M | 26 §7 | `verify_payment_channel.py` |

---

## FASE 39 — Fondasi Data & Wiring ✅ SELESAI (+ 39b penutupan wiring)
**Tujuan:** menyiapkan tulang belakang data agar semua fase berikutnya tidak menambah tech-debt.
**Scope:** koleksi `clusters`, `blocks`, `unit_types`, `addon_items`, `price_components`, `doc_requirements`, `doc_submissions`, `settings` + `settings_store` + index unik + migrasi backfill ([35](35_MIGRASI_DATA.md)) + endpoint master + wiring dua arah siteplan↔unit + dua status paralel unit.
**User stories:**
- US-39-1 Admin membuat proyek → cluster → blok → unit (satuan, generator massal, impor CSV dengan dry-run).
- US-39-2 Admin membuat master add-on (spek bangunan, kelebihan tanah, hook) dengan harga & perlakuan finance.
- US-39-3 Admin membuat master dokumen syarat per tahap/skema, lalu melihatnya muncul sebagai checklist.
- US-39-4 Admin mengubah setting `reservation.max_active_per_lead` dari UI dan nilainya benar-benar dipakai.
- US-39-5 Data lama (18 unit demo) otomatis punya cluster & blok tanpa kehilangan riwayat.
**DoD:** [28](28_PROJECT_UNIT_SPEC.md) §8 + [33](33_CONFIG_CENTER_SPEC.md) §5 + INV-02, INV-06 lulus + 0 shape tanpa unit.

**Hasil (16 Agu 2026):** semua US-39-1…5 terbukti; `run_all_gates.sh` **22 gates PASS**;
`mutasi_39b.py` 20/20; testing agent iterasi 58/59/60.
**39b menutup 5 cacat nyata** yang tertinggal dari Fase 39:
(1) master 17 dokumen syarat tidak dipakai layar mana pun (`doc/matrix` & `doc/submissions`
nol kemunculan di frontend) → komponen `DocChecklist` di layar Lead & Pelanggan, konteks
diturunkan backend (`doc_registry.contexts_for`);
(2) "Akun GL" masih input teks bebas → grup SSOT dinamis `gl_account` berlabel `kode — nama`;
(3) `CONTEXT_OPTIONS` & `ORIGIN_LABEL` hardcode di frontend → grup SSOT `doc_context`,
`setting_origin`, `setting_source`;
(4) `migration_runs` tak bisa dilihat → `GET /api/admin/migrations` (+`state`) & panel di
`/admin/audit`;
(5) unggah **gagal-senyap** + **500** pada bukti kembar → input berkas per baris & penolakan
bukti kembar berbasis `files.sha256` dengan pesan jelas.
**Sisa yang SENGAJA ditunda:** INV-07 (gerbang tahap oleh dokumen wajib) → Fase 41/42 bersama
tahap `spr`; checklist untuk **mitra** & **unit** → Fase 45/50; konsolidasi
`customers.kyc_files` vs `doc_submissions` → Fase 43.

## FASE 40 — IA & Design System V2
**Tujuan:** hentikan penyakit UX (kartu untuk data, tanpa filter, drawer untuk konten panjang) sebelum menambah fitur baru.
**Scope:** komponen pola ([23](23_IA_UX_BLUEPRINT.md) §5), `@tanstack/react-table`, restrukturisasi navigasi (33 → 26 item), halaman kanonik kosong-terisi (`/leads/:id`, `/customers/:id`, `/units/:id`, `/projects/:id`), migrasi halaman lama ke `DataTable` **tanpa mengubah fitur**.
**User stories:**
- US-40-1 Semua daftar utama punya search + filter multi + sort + kolom pilihan + ekspor + aksi massal.
- US-40-2 Klik baris membuka **halaman** detail (bukan drawer) untuk objek besar.
- US-40-3 Menu baru: user menemukan fitur lama di tempat baru tanpa fitur hilang (checklist pemetaan).
- US-40-4 Setiap KPI di beranda bisa diklik → tabel terfilter.
**DoD:** `verify_ia_v2.py` memeriksa: setiap route daftar punya elemen filter/sort/search ber-`data-testid`; tidak ada halaman >500 baris; `verify_ui_surfaces.py` tetap PASS.

## FASE 41 — CRM Lead V2
**Scope:** stage machine v2 (+`spr`), `stage_entered_at`/`stage_durations`/`sla_due_at`, halaman **Profil Lead** + `GET /api/leads/{id}/profile`, pipeline tabel pro + kanban toggle, demografi, matriks dokumen, eliminasi massal & merge duplikat, `partner_id` pada lead, SLA & eskalasi.
**User stories:**
- US-41-1 Sales melihat daftar lead dengan **umur total & umur tahap**, mengurutkan yang paling urgen.
- US-41-2 Sales membuka profil lead dan melihat seluruh riwayat **beserta siapa yang mengerjakan**.
- US-41-3 Sales mengunggah dokumen per tahap; supervisor memverifikasi/menolak dengan alasan.
- US-41-4 Manager mengeliminasi 20 lead spam sekaligus dengan alasan, terekam per lead.
- US-41-5 Marketing melihat lead duplikat lalu menggabungkannya tanpa kehilangan aktivitas.
- US-41-6 Lead dari mitra tercatat `partner_id` dan tampil di profil mitra.
**DoD:** [24](24_CRM_LEAD_SPEC.md) §14.

## FASE 42 — Reservasi/SPR + Generator Dokumen
**Scope:** perbaikan CR-01 (batas reservasi + index partial), siklus booking fee (catat/verifikasi/hangus/refund), pemilihan **add-on saat reservasi**, penerbitan SPR (3 varian) + SPKT, penomoran, draft→final→sign, arsip ke semua profil.
**User stories:**
- US-42-1 Sales mencoba reservasi unit kedua untuk lead yang sama → ditolak dengan pesan jelas; manajer bisa override beralasan.
- US-42-2 Sales memilih add-on "kelebihan tanah 12 m²" → SPKT wajib & total tagihan berubah.
- US-42-3 Finance memverifikasi bukti transfer booking fee → status berubah & jurnal titipan terbentuk.
- US-42-4 Sales menerbitkan SPR KPR → PDF berisi semua biaya sesuai kontrak; nomor unik.
- US-42-5 Booking fee tidak diverifikasi 7 hari → sistem menandai hangus & memberi tahu (sesuai klausa).
**DoD:** [27](27_DOCGEN_SPEC.md) §8 + INV-01.

## FASE 43 — Customer, Kontrak & Rencana Bayar
**Scope:** konversi lead→customer, `contracts` + `price_breakdown` komponen, `payment_plans` 3 skema dari `[DOC]`, AR per termin, tunggakan & toleransi, pembatalan/refund engine + jurnal, menu gabungan **Customer & Kontrak**, tahap legal PPJB/AJB/BAST/sertifikat/retensi.
**User stories:**
- US-43-1 SPR ditandatangani → lead menjadi customer, kontrak & rencana bayar otomatis terbentuk.
- US-43-2 Finance menerbitkan tagihan termin, mencatat pembayaran dengan bukti; sisa & tunggakan terlihat.
- US-43-3 Cicilan lewat tanggal 20 → ditandai menunggak; 2 bulan → muncul usulan pembatalan + hitungan potongan.
- US-43-4 BAST tidak bisa ditandatangani sebelum Finance konfirmasi lunas.
- US-43-5 Owner melihat semua add-on & biaya sebagai baris terpisah di laporan.
**DoD:** [26](26_CUSTOMER_LEGAL_SPEC.md) §10.

## FASE 44 — Alur KPR + BI Checking terpisah
**Scope:** `kpr_applications` dengan tahap `berkas_lengkap → diajukan_ke_bank → [appraisal] → sp3k → akad_kredit → pencairan`, gerbang bukti, SLA, penolakan+refund 50%, **menu BI Checking** mandiri (lead & customer, termasuk hasil SLIK bank) yang **bukan** bagian urutan.
**User stories:**
- US-44-1 Admin KPR mengajukan ke bank, mengunggah SP3K → tahap maju; tanpa file → ditolak.
- US-44-2 Add-on kelebihan tanah belum lunas → akad kredit diblokir dengan alasan.
- US-44-3 Bank menolak → booking fee refund 50% otomatis diusulkan.
- US-44-4 Staf melakukan BI Checking **sebelum** booking dari menu BI Checking, hasil menempel ke lead.
**DoD:** INV-08 + gerbang bukti terbukti lewat uji negatif.

## FASE 45 — Mitra & Fee
**Scope:** master mitra (extend `agents`), kontrak & dokumen onboarding, `partner_fee_rules` (7 basis + trigger + split + pajak), fee otomatis, approval finance, analitik mitra, portal mitra opsional, webhook lead mitra.
**User stories:** lihat [25](25_PARTNER_SPEC.md) §5 & §8.
**DoD:** [25](25_PARTNER_SPEC.md) §8 + INV-09 + invarian saldo `2-1500` tidak rusak.

## FASE 46 — Agenda & Survey V2 + Inbox WA V2
**Scope:** kalender besar (bulan/minggu/hari/agenda) + tabel tunggu survei, reschedule/batal beralasan (SSOT) + follow-up WA otomatis + `appointment_events`, builder form survei berversi, Inbox WA 3 kolom virtualized + filter/urgensi/SLA + aksi massal.
**User stories:**
- US-46-1 PIC melihat kalender minggu ini + daftar lead menunggu survei dengan umur menunggu.
- US-46-2 Survei dibatalkan hari itu → wajib pilih alasan → tugas WA follow-up lahir → masuk analitik alasan.
- US-46-3 Admin mengubah form survei; hasil lama tetap terbaca (versi).
- US-46-4 Dengan 1000+ percakapan, user menemukan yang belum dibalas & SLA lewat dalam <3 klik.
**DoD:** filter/sort/search lengkap; uji performa daftar 1000 baris (render <1.5s).

## FASE 47 — Marketing, Kampanye & Biaya Iklan
**Scope:** `campaigns`, `ad_spend` (manual + CSV idempoten + dry-run), halaman Kampanye & Biaya, atribusi+CAPI (tambah `SubmitApplication`, `event_id`, hash user_data), adapter Meta/Google siap-live, `wa_adapter`, halaman status integrasi.
**DoD:** [30](30_MARKETING_INTEGRATION_SPEC.md) §9.

## FASE 48 — Target & Budget/RAB
**Scope:** `project_targets` (5 metode + recalc bulanan berjejak), `budget_items` master + kategori bisa ditambah, realisasi 3 lapis + peringatan 90%, `cost_ref` wajib pada dokumen biaya baru, laporan RAB vs realisasi & margin.
**DoD:** [32](32_TARGET_BUDGET_SPEC.md) §6.

## FASE 49 — Analytics & BI
**Scope:** `metrics/*` + `/api/analytics/*` + 5 dashboard + drill-down + ekspor + `user_daily_activity` + laporan harian per user + snapshot harian.
**DoD:** [31](31_ANALYTICS_BI_SPEC.md) §9 + INV-14.

## FASE 50 — Konsolidasi Proyek & Konstruksi
**Scope:** hub **Pembangunan** 6 tab, Papan Unit tabel, Unit 360 tab pembangunan, perizinan & buku harian jadi tab, gerbang "mulai bangun setelah DP 80%".
**DoD:** [29](29_CONSTRUCTION_SPEC.md) §6 (tanpa regresi gate 31–37).

## FASE 51 — Kesiapan Pembayaran (opsional, saat owner siap)
**Scope:** kanal pembayaran (VA/transfer/gateway) + rekonsiliasi otomatis ke termin + notifikasi + audit. Playbook integrasi diminta dulu ke `integration_playbook_expert_v2`; **tidak** dibangun tanpa kredensial nyata.

---

## Aturan mutu lintas fase (wajib)
1. **Tanpa mock**: bila data belum ada, tampilkan keadaan kosong yang jujur — jangan mengarang angka.
2. **Uji negatif wajib** untuk setiap aturan bisnis baru (yang dilarang harus benar-benar gagal).
3. **Angka harus bisa direkonstruksi** dari data mentah.
4. **Gate uji-mutasi**: gate baru harus gagal bila kode sengaja dirusak (dibuktikan saat menutup fase).
5. **Batas ukuran file** dipatuhi sejak awal (`validate_compliance.py`).
6. **RBAC diperiksa** untuk setiap endpoint baru (`verify_rbac.py`).
7. **Migrasi idempoten** & bisa dijalankan ulang.
8. **Bukti browser**: setiap user story dibuktikan lewat interaksi nyata, bukan hanya curl.
