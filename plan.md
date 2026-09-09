# Rencana Development SIPRO — Fase 58

> **Pembaruan sesi repo agavafayaja/sipro — 2026-09-06**
> Editor naskah berformat dan pengaturan tabel, jalur PDF yang melewatkan konfigurasi,
> overlap all-in/arah hadap/harga, tipe input, dan warning UI telah ditangani berbasis bukti.
> 48 tes terfokus lulus, 23 target pratinjau diuji. Rangkaian saat ini berisi 70 skrip gate.
> **Jangan menyimpulkan semua backlog selesai dari gate hijau.** Status terukur dan daftar
> yang belum ditutup ada di `memory/VERIFIKASI_SIPRO_2026-09-06.md`.
> Lanjut P1: fixture legacy sepenuhnya mandiri, audit GL/BI non-lead, matriks visual semua
> dialog/peran, indikator data uji, dan inventaris tes WA live yang membutuhkan kredensial.

> **STATUS PER PEMBARUAN TERAKHIR**
>
> | Bagian | Status |
> |---|---|
> | Pemulihan lingkungan dari repo `sjsjjdbfbd/Sipro` di container baru | **SELESAI** — `backend/.env` dibuat ulang (`JWT_SECRET`, `DEFAULT_ORG_ID`, `PORTAL_MASTER_OTP`), dependensi dipasang, seed jalan di DB bersih, login OK |
> | 58A — Cacat tempat development berhenti: unit di stok yang masih mengaku "terjual" | **SELESAI** — direproduksi, akar masalah ditutup, gate 47 diperkuat (110 pemeriksaan), `mutasi_56.py` 49 mutan / 49 TERTANGKAP |
> | 58B — Fitur: **Toleransi keterlambatan & denda keterlambatan berjurnal** | **SELESAI** — gate 49 `verify_late_fee.py` (67 pemeriksaan), `mutasi_58.py` (31 mutan) |
> | 58C — Dokumentasi & penutupan | **SELESAI** — `docs/v2/51_LATE_FEE_TOLERANCE_SPEC.md`, bagian FASE 58 di `CODEBASE_MAP.md`, `memory/PRD.md` |

---

## 0) Kenapa dev sempat berhenti (dan apa yang sebenarnya terjadi)

Gate `verify_data_integrity.py` merah dengan satu baris: **"unit terjual tanpa ikatan
lead/deal: 1"** pada unit `A-06` yang justru berstatus `available`.

Root cause-nya BUKAN gate yang salah (dugaan pertama yang paling menggoda, karena unitnya
"kan available"): `cancellation_engine._release_unit` melepas unit ke stok dan mengosongkan
`booked_by_deal`, `deal_id`, `lead_id` — tetapi **membiarkan `sold_by_deal` dan `sold_at`**.
Rumah yang sudah dikembalikan ke stok tetap mengaku terjual kepada site plan, invarian
bisnis, dan gate integritas. Lebih jauh: `seed_phase31._fix_unit_defects` → `sync_unit_binding`
membaca tautan basi itu dan **mengikat ulang** unitnya ke pembeli yang justru mundur.

Diperbaiki: pelepasan unit mengosongkan tautan penjualan, `_buyer_binding` menolak mengikat
unit berstatus `available`, dan `seed_phase56.repair_stale_sold_links()` membersihkan basis
data yang sudah pernah menjalankan pembatalan (idempoten).

Pelajaran yang dicatat: **gate yang merah lebih sering benar daripada kode yang merasa benar.**
Reproduksi dulu (`scripts/repro_stale_sold_link.py`), baru perbaiki.

---

## 1) 58A — Cacat pelepasan unit (SELESAI)

* `cancellation_engine._release_unit`: `sold_by_deal`/`sold_at` dikosongkan; unit yang tertaut
  HANYA lewat penjualan tetap bisa dilepas (dulu tidak cocok dengan filter atomiknya).
* `build_engine._buyer_binding`: unit `available` tidak punya pembeli, apa pun sisa tautannya.
* `seed_phase56.repair_stale_sold_links()`: perbaikan data lama, idempoten, jalan saat startup.
* Guardrail: gate 47 K10b2/K10b3/D14b (**D14b memeriksa SELURUH stok**, bukan hanya unit uji)
  + `mutasi_56.py` M14/M47/M48 → 49 mutan, 49 TERTANGKAP / 0 LOLOS.

---

## 2) 58B — Toleransi keterlambatan & denda berjurnal (SELESAI)

Utang yang **diakui sendiri oleh aplikasi** di tab Rencana Bayar ("yang belum dibangun:
toleransi keterlambatan"). Rinciannya ada di `docs/v2/51_LATE_FEE_TOLERANCE_SPEC.md`.

Yang dibangun:
1. **Satu mesin** `backend/late_fee_engine.py` — kebijakan dari Pusat Konfigurasi
   (`payment.late.*`), tenggang milik TERMIN menang atas bawaan, keadaan `dalam_tenggang`
   yang sebelumnya tidak ada, denda prorata berbatas atas & bawah.
2. **Denda berjurnal** (Dr `1-1300` / Cr **`4-1400` akun baru**), idempoten per (termin,
   bulan); yang ditagihkan adalah SELISIH — klik dua kali bukan denda kedua.
3. **Keringanan** hanya Manajer Keuangan (`late_fee:override`), wajib alasan ≥10 huruf,
   membalik jurnal, dan **tidak bisa dianulir** dengan menagihkan denda yang sama lagi.
4. **Tidak ada mesin kedua**: `finance_reports` (tombol "Denda" lama, daftar penagihan,
   konfigurasi penagihan) dilimpahkan ke mesin di atas; `compute_scheme_items` akhirnya
   membawa `grace_days` ke jadwal tagihan.
5. **Layar**: panel pada tab Rencana Bayar (keadaan per termin dari server, sebab denda belum
   bisa ditagihkan, tagihkan, keringanan) + kartu toleransi & denda di portal pembeli.
6. **Guardrail**: gate 49 (67 pemeriksaan) + `mutasi_58.py` (31 mutan).

---

## 3) Kriteria selesai Fase 58

- `bash scripts/run_all_gates.sh` → OVERALL PASS (**49 gates**).
- `python3 scripts/mutasi_56.py --ringkas` → 49/49 TERTANGKAP.
- `python3 scripts/mutasi_58.py --ringkas` → 31/31 TERTANGKAP.
- Tidak ada layar yang mengaku "belum dibangun" untuk sesuatu yang sudah ada.
- Pembeli membaca toleransi & dendanya sendiri dengan angka yang sama dengan pembukuan.

---

## 3b) Fase 58D — Pemulihan lingkungan & batas ukuran berkas (SELESAI, sesi lanjutan)

Development terhenti pada gate `validate_compliance.py`: `backend/rbac.py` (809) dan
`backend/reference.py` (801) melewati batas **800 baris**. Merapatkan komentar hanya menunda
masalahnya, jadi kedua berkas DIPECAH — SSOT tetap satu:

* `backend/rbac_matrix.py` (487) — `DEFAULT_PERMISSIONS`; `rbac.py` (330) menyimpan
  `require_permission`, `can`, `scope_query`, `audit_log`, `ROLE_GRANTS`.
* `backend/reference_groups.py` (527) — `GROUPS` dasar + `_o`; `reference.py` (284) memuatnya
  lalu melengkapi dengan grup per-fase (`reference_p<NN>.py`) seperti sebelumnya.
* Guardrail yang MEMBACA/MEMUTASI matriks diarahkan ke berkas barunya
  (`verify_late_fee.py` membaca `rbac.py` + `rbac_matrix.py`; `mutasi_45/52/58`).
* Pemulihan lingkungan: `backend/.env` (`JWT_SECRET`, `DEFAULT_ORG_ID`, `PORTAL_MASTER_OTP`),
  `reportlab`/`APScheduler`/`tzlocal`, `yarn install`.

Bukti: `run_all_gates.sh` **PASS (49 gates)**, `mutasi_58` 31/31, `mutasi_56` 49/49,
testing agent iterasi 94: backend 11/11, UI panel denda + dialog keringanan + kartu portal
(angka sama dengan pembukuan), 0 isu.

---

## 3c) Fase 59 — tiga utang Fase 58 dibayar (SELESAI)

| Fitur | Isi | Bukti |
|---|---|---|
| **Laporan keringanan denda** | `late_fee_report.py` (siapa/apa/berapa/kapan/alasan + rekap per pemberi keputusan), tab **Riwayat keringanan** di panel denda Rencana Bayar & tab **Keringanan Denda** di Keuangan (satu komponen), ekspor **CSV + PDF** | gate 50 K1-K5/K18-K20b/D1-D3; alur nyata: denda A-02 Rp 4.760.000 diringankan finlead@ → muncul di laporan |
| **Pembatalan karena tunggakan** | `arrears_engine.py`: bulan tunggakan **akumulatif DAN berurutan** (SPR), ambang dari Pusat Konfigurasi, panel kandidat di tab Pembatalan & Refund, `sweep()` menitipkan **TUGAS** ke Manajer Keuangan (idempoten/bulan) + job harian `scheduler_p59` | gate 50 K6-K10c/D4-D7; mesin TIDAK punya jalan membatalkan sendiri (SoD Fase 56 utuh) |
| **Laporan utang refund `2-1460`** | `refund_debt.py`: jatuh tempo = keputusan + `cancellation.refund_due_days` (30), bucket umur, proyeksi kas 6 bulan, yang **tertahan SPR tidak diberi tanggal karangan**, dan uji cocok dengan **saldo buku besar** | gate 50 K11-K15/D8-D10; proyeksi + belum-terjadwal = seluruh kewajiban |

Guardrail baru: **`scripts/verify_p59.py` (gate 50, 53 pemeriksaan)** — masuk `run_all_gates.sh`.
Kriteria selesai: `run_all_gates.sh` → **OVERALL PASS (50 gates)**; testing agent iterasi 95
17/17 backend, 3 panel + 14 tab Keuangan bersih, 0 isu.

---

## 4) Tugas berikutnya (untuk sesi lanjutan)

1. **Denda otomatis terjadwal** (opsional per organisasi): sekarang denda ditagihkan lewat
   tombol; scheduler harian bisa menerbitkannya + pengingat WhatsApp (`payment.late.auto_apply`
   belum ada — sengaja, karena menagih otomatis adalah keputusan bisnis).
2. ~~Laporan denda & keringanan~~ — **SELESAI Fase 59**.
3. ~~Pembatalan sepihak karena tunggakan~~ — **SELESAI Fase 59** (tahap usulan; pembatalan
   otomatis sengaja TIDAK dibuat).
4. ~~Laporan utang refund (`2-1460`)~~ — **SELESAI Fase 59**.
5. **Mutasi Fase 59** (`scripts/mutasi_59.py`) belum ada: gate 50 sudah menjaga ketiga fitur,
   tetapi ketangguhannya belum diuji dengan mutan seperti fase-fase sebelumnya.
6. **Pengingat WhatsApp untuk tunggakan yang mendekati batas** (H-30 sebelum kandidat) —
   sekarang pembeli baru tahu saat tugas peninjauan sudah terbit.

---

## 3d) Fase 62 — dokumen penagihan & lapangan (SELESAI, gate 53)

| Fitur | Isi | Bukti |
|---|---|---|
| **Surat Peringatan SP1/SP2/SP3** | `warning_letters.py` + `docgen_p62.sp_pdf`: angka dari mesin denda, tingkat tidak boleh melompat, SP3 hanya sesudah batas kontrak, nomor atomik, idempoten per (kontrak, tingkat, bulan) | gate 53 K1-K7/D1-D9; dialog di panel kandidat tunggakan (`warning-letter-*`) |
| **Berita Acara Opname** | `GET /api/subcon/claims/{id}/pdf` — baris termin yang SAMA dengan tagihan AP; pekerjaan yang dikeluarkan opname tercetak + alasannya; draf bertanda DRAFT | gate 53 K8-K9/D10-D11 |
| **Berita Acara Punch List** | `GET /api/field/punchlist/pdf` — lingkup = filter di layar, kolom bukti perbaikan | gate 53 K10/D12-D13 |
| **Lampiran SPK** | `spk_attachments` + halaman LAMPIRAN pada PDF SPK (`pdf_layout._attachment_flow`) | gate 53 K11-K13/D14-D20; PDF diperiksa visual (3 halaman) |
| **Kirim dokumen ke pihak luar** | `doc_share.py`: tautan 14 hari (token acak, bisa dicabut, pembukaan tercatat) + pesan `wa.me`; `GET /api/public/docs/{token}` tanpa login, dirender ULANG dari data terkini | gate 53 K15-K19/D21-D27 |

Keputusan rancangan: **tidak memakai API WhatsApp Meta**. Sistem menyiapkan tautan + pesan;
yang menekan kirim tetap manusia dengan nomor perusahaan. Ini jujur (tanpa kredensial yang
tidak dimiliki) dan tidak pernah mengedarkan berkas basi.

Kriteria selesai: `run_all_gates.sh` → **OVERALL PASS (53 gates)**; testing agent iterasi 98
10/10 alur UI bersih.

## 5) Tugas berikutnya (sesudah Fase 62)
1. `scripts/mutasi_62.py` — uji ketangguhan gate 53 dengan mutan.
2. Pengingat WhatsApp otomatis untuk tunggakan (SP1 sesudah H+N lewat toleransi).
3. Panel riwayat pengiriman dokumen (data `GET /api/docs/share` sudah ada).

---

## 3e) Fase 63 — Agenda & Survey menjadi kalender KERJA (SELESAI, gate 54)

| Fitur | Isi | Bukti |
|---|---|---|
| **Tabel agenda** | `AgendaTable.js` (DataTable+FilterBar): cari, filter rentang 7/30 hari & riwayat + golongan/jenis/status, urut & paginasi SERVER, ekspor CSV, filter hidup di URL | gate 54 K5-K7/KUI3-KUI5/D5-D8 |
| **Buat & ubah agenda** | `AgendaFormDialog.js`: golongan `sales` (lead dicari) vs `internal` (tanpa lead), peserta dari `/appointments/staff`; `PUT /api/appointments/{id}` menolak mengubah agenda `done`/`cancelled` | gate 54 K1-K2/K12/D1-D2/D11-D16 |
| **Agenda non-penjualan** | `reference_p63.py`: rapat internal, kunjungan proyek, rapat vendor/subkon, lain-lain + grup `agenda_kind` | gate 54 K3-K4/D7 |
| **Peserta & cakupan** | peserta wajib pengguna nyata; `_appt_scope()` membuat staf yang DIUNDANG melihat agendanya | gate 54 K8-K9/D9-D10/D12 |
| **RBAC** | `project_manager` & `site_engineer` boleh membuat agenda internal; agenda ber-lead tetap butuh `leads:view`; keuangan tetap hanya baca | gate 54 K10/K14/D3-D4; `verify_panel_resilience` diperbarui (80 PASS) |

Kriteria selesai: `run_all_gates.sh` → **OVERALL PASS (54 gates)**; testing agent iterasi 99
seluruh alur UI PASS (termasuk responsif 390×844, tanpa overflow).

---

## 3f) Fase 64 — pusat notifikasi yang BISA HABIS (SELESAI, gate 55)

| Keluhan pemakai | Perbaikan | Bukti |
|---|---|---|
| Kartu besar, daftar memanjang | baris padat ~52px (`NotificationRows.js`), isi dipangkas satu baris | gate 55 KUI1-KUI2; uji UI iterasi 100 |
| Overwhelming, tanpa kategori | 4 tab keadaan berjumlah + chip kategori berjumlah (kategori DITURUNKAN dari `type`+`related_entity_type`, tanpa migrasi) | gate 55 K1/KUI3-KUI4/D2-D4 |
| Notifikasi tidak hilang walau sudah ditindak | `resolve_done()` + `_resolve_task_notifs()` mencabut sendiri (tandai `resolved_at`+alasan, tidak dihapus) | gate 55 K5-K8/D10-D13 |
| Tidak membantu navigasi | `link_of()` satu peta; notifikasi tugas selalu ke papan tugas | gate 55 K3-K4/D5 |
| Yang sudah dilihat menumpuk | tab "Sudah dilihat", tombol sembunyikan per baris, "Bersihkan yang sudah dilihat" | gate 55 K9/KUI7/D14-D19 |

Kriteria selesai: `run_all_gates.sh` → **OVERALL PASS (55 gates)**; iterasi 100: 12/12 pytest
(`backend/tests/test_notif_p64.py`, snapshot→ubah→pulihkan) + UI 1440×900 & 390×844, 0 isu.

## 6) Tugas berikutnya (sesudah Fase 64)
1. Pengelompokan notifikasi kembar ("5× Persetujuan diskon penawaran").
2. Preferensi notifikasi per pemakai (kategori mana yang boleh mengirim push/WA).
3. `scripts/mutasi_62.py` & `mutasi_63.py` (uji mutan gate 53/54).

---

## 3g) Fase 65 — notifikasi kembar berkelompok & preferensi per pemakai (SELESAI, gate 56)

| Keluhan pemakai | Perbaikan | Bukti |
|---|---|---|
| "Lima permintaan diskon = lima baris yang harus dibaca satu-satu" | `group_key()` + `group_rows()`: kembar diringkas jadi SATU baris berjumlah (`5×`) yang bisa dibuka; kunci diturunkan dari data (nomor dokumen & kode dinormalkan `#`) jadi notifikasi lama ikut berkelompok tanpa migrasi | gate 56 K1-K4/D1-D7; layar: 103 notifikasi → 22 kelompok |
| "Saya harus menutup satu-satu" | `POST /notifications/group/read|dismiss` bekerja dari KUNCI kelompok (server yang menentukan anggotanya), tetap terikat pemilik & izin `notifications:update` | gate 56 K12-K13/D8-D13b |
| "Semua orang menerima hal yang sama" | `notif_prefs.py`: 3 saluran (`inapp`/`push`/`wa`) per kategori, per pemakai; kategori/saluran asing DITOLAK 400 | gate 56 K5-K8/D14-D19 |
| "Kalau dimatikan, persetujuan bisa menggantung" | notifikasi yang MENUNTUT TINDAKAN tidak bisa dibungkam dari daftar (`LOCKED_CHANNELS`), dan layar mengatakannya (`locked_reason`) | gate 56 K6/KUI9/D15/D23-D24 |
| "Kenapa saya tidak diberi tahu?" | yang dibungkam tetap ditulis dengan `muted_at` + `muted_reason` (disembunyikan, TIDAK dihapus) | gate 56 K7/K10/D20-D22 |
| Pengingat WhatsApp | `GET /notifications/wa-digest`: teks + tautan `wa.me` untuk kategori yang diizinkan — sistem menyiapkan, MANUSIA menekan kirim (pola Fase 62, tanpa kredensial yang tidak dimiliki) | gate 56 K17/KUI11/D25-D27 |

Penegakan preferensi duduk di SATU pintu (`engine.create_notification`), jadi ~30 pemanggil
lama ikut patuh tanpa diubah. Kontrak Fase 64 utuh: tanpa `group=true` bentuk daftar &
`unread_only` (lonceng TopBar) tidak berubah.

Kriteria selesai: `run_all_gates.sh` → **OVERALL PASS (56 gates)**;
`python3 -m pytest backend/tests/test_notif_p65.py` 12/12; layar diperiksa 1920×800.

---

## 3h) Fase 66 — Template Dokumen disatukan (SELESAI, gate 57)

| Keluhan pemakai | Perbaikan | Bukti |
|---|---|---|
| "Template dokumen terbelah dua: isi template dan tampilan kop surat" | satu panel per JENIS dokumen: tab Naskah / Kop & kertas / Baris & biaya / Tabel / Tanda tangan, pratinjau berdampingan | gate 57 KUI1-KUI3, KUI12 |
| "Isi template harus menyesuaikan kategori/jenis dokumen" | naskah menempel pada kode dokumen; kosakata placeholder DITURUNKAN dari konteks mesin penerbit (docgen / cancellation / documents_router), berbeda per jenis | gate 57 K1-K3, D4-D6 |
| "Naskah harusnya masuk ke dalam dokumen" | naskah disimpan di koleksi yang dipakai penerbit; `ds.intro_for()` menempelkannya ke SPK/PO/SP/BA yang dirakit sistem; pratinjau mencetak naskah + nilai contoh | gate 57 K5-K6, K18-K19, D10-D12 (isi PDF dibaca) |
| "Format tabel bisa dikonfigurasi: garis transparan, nama kolom tidak tampil" | `layout.table`: `grid=full|horizontal|none`, `show_header`, `header_fill`, `zebra`, `total_highlight`, `font_size`, `grid_color` — dipakai tabel biaya, rincian item, dan laporan | gate 57 K7-K13, D13-D19 |
| Token liar tercetak mentah di dokumen resmi | `unknown_tokens()` menolak 400 + peringatan HIDUP saat mengetik di layar | gate 57 K4, KUI8, D7 |

Naskah resmi butuh izin `settings:update` (sekelas kop surat) — sales yang boleh menerbitkan
dokumen tidak boleh mengubah kalimat yang mengikat perusahaan (gate 57 D20).

Kriteria selesai: `run_all_gates.sh` → **OVERALL PASS (57 gates)**;
`pytest backend/tests/test_doc_p66.py` 17/17; testing agent iterasi 101 tanpa cacat blokir.

## 7) Tugas berikutnya (sesudah Fase 66)
1. `scripts/mutasi_62.py`, `mutasi_63.py`, `mutasi_65.py` — uji mutan gate 53/54/56.
2. Ringkasan harian notifikasi (email/WA) per preferensi — sekarang ringkasan disusun
   saat diminta, belum ada jadwal harian.
3. Pengingat WhatsApp otomatis untuk tunggakan (SP1 sesudah H+N lewat toleransi).

---

## 3i) Fase 67 — kedalaman & konsistensi tampilan (SELESAI, gate 58) + pemulihan lingkungan

Sesi sebelumnya terputus di tengah penutupan temuan uji iterasi 102. Yang dilakukan sesi ini:

| Bagian | Status |
|---|---|
| Pemulihan lingkungan dari repo `akahdbeben/sipro` (env, dependensi, seed, login) | **SELESAI** — catatan: gate memakai `PORTAL_MASTER_OTP=000000` |
| Temuan 102 #1: kolom AKSI sticky kanan pada tabel lebar | **SELESAI** — `.col-actions`/`.col-actions-head` (~20 tabel) + `sticky: true` di `DataTable` (AR, Deals, Dokumen, Agenda, Mitra, Config, CAPI, Bank Rekonsiliasi); 4 header sticky yang tertinggal dilengkapi |
| Temuan 102 #2-#5 (pembungkus gulir ganda, empty-state pencarian notifikasi, testId SearchInput, skip-link + cincin fokus sidebar) | **SELESAI** (sebagian sudah dikerjakan sebelum sesi terputus, diverifikasi ulang) |
| Dokumentasi: bagian FASE 67 di `CODEBASE_MAP.md`, entri PRD, plan.md | **SELESAI** |
| `bash scripts/run_all_gates.sh` | **OVERALL PASS (58 gates)** |

## 8) Tugas berikutnya (sesudah Fase 67)
1. `scripts/mutasi_62.py`, `mutasi_63.py`, `mutasi_65.py` — uji mutan gate 53/54/56.
2. Ringkasan harian notifikasi (email/WA) per preferensi — belum ada jadwal harian.
3. Pengingat WhatsApp otomatis untuk tunggakan (SP1 sesudah H+N lewat toleransi).
4. Denda otomatis terjadwal (opsional per organisasi, `payment.late.auto_apply`).

---

## 3j) Fase 68 — denda terjadwal + pengingat tunggakan pra-SP (SELESAI, gate 59)

| Fitur | Isi | Bukti |
|---|---|---|
| **Denda otomatis terjadwal** | `payment.late.auto_apply` (bawaan MATI) + rem `auto_min_days`/`auto_min_amount`; `late_fee_auto.py` memakai `late_fee_engine.apply` (tanpa mesin kedua); cron harian 09:30 WIB (`scheduler_p68`); putaran ditulis ke `late_fee_auto_runs` | gate 59 K1-K6/D1-D9; panel `LateFeeAutoPanel` di tab Penagihan |
| **Pengingat tunggakan pra-SP** | jenis `arrears_warning` di mesin pengingat WA; lahir saat tunggakan lewat toleransi (mesin bulan = SP/arrears); rem nominal & aturan dari Pusat Konfigurasi (`reminder.arrears_*`); `wa_link` siap kirim manual | gate 59 K7-K10/D10-D13; tombol "Kirim manual" di RemindersPanel |
| **Bug laten** | `sched_p59.register()` tidak pernah dipanggil — kini terdaftar (+ p68) | gate 59 K5-K6 |

## 9) Tugas berikutnya (sesudah Fase 68)
1. `scripts/mutasi_62.py`, `mutasi_63.py`, `mutasi_65.py` — uji mutan gate 53/54/56.
2. Ringkasan harian notifikasi (email/WA) per preferensi — belum ada jadwal harian.

---

## 3k) Fase 71 — penomoran terkonfigurasi + kode master otomatis (SELESAI, iteration_121)

| Bagian | Status |
|---|---|
| Pemulihan lingkungan dari repo `akskdidj/sipro` (env, deps, seed, kredensial) | **SELESAI** |
| Konteks `next_number` yang terhenti (labor/petty cash/aset tetap + fee mitra, refund BF, klaim garansi) | **SELESAI** |
| `routers/numbering_router.py` (`/api/numbering`: list, tokens, preview, put, delete) | **SELESAI** |
| Kode master otomatis dari aturan bila kode kosong (proyek/cluster/blok/unit/tipe/add-on/vendor/subkon/material) | **SELESAI** — counter per induk (`parent` di registry) |
| UI /config → tab Penomoran (`NumberingPanel`, `NumberingRuleDialog`) | **SELESAI** |
| Uji: 19 pytest (dev + testing agent) + UI iteration_121 | **SELESAI** |

## 10) Tugas berikutnya (sesudah Fase 71)
1. Pratinjau/`next_seq` per konteks (pilih proyek contoh) agar sama dengan nomor yang terbit.
2. Form master di UI: kolom kode boleh dikosongkan + placeholder "otomatis dari aturan" (ProjectForm, ClusterForm, VendorForm, dll.).
3. `scripts/verify_p71.py` gate + `run_all_gates.sh`; `engine.py` 818>800 (baseline).
4. Backlog lama: mutasi gate 53/54/56, ringkasan harian notifikasi.

---

## 3l) Fase 72 — Studio Site Plan + kode master opsional + pratinjau per proyek (SELESAI, iteration_122)

| Bagian | Status |
|---|---|
| Parser SVG kaya (transform, path→poligon, teks label, deteksi kavling) `site_plan_parse.py` | **SELESAI** |
| `/api/site-plan-studio/*` (svg, background, shapes CRUD, auto-match, suggest-units, create-units 2 opsi) | **SELESAI** |
| Halaman `/site-plan/studio/:projectId` — kanvas zoom/pan, tracing poligon, mode berurutan, tab Buat unit | **SELESAI** |
| Form master: kode opsional + hint; panel Penomoran: pratinjau per proyek | **SELESAI** |

## 10) Tugas berikutnya (sesudah Fase 72)
1. Studio: edit titik poligon (drag vertex), undo/redo, snap ke grid, duplikasi kavling.
2. Impor PDF site plan (render halaman → PNG latar) & DXF/DWG.
3. Warna kanvas studio per status unit + legenda; ekspor peta PNG untuk brosur.
4. Backlog lama: engine.py 818>800, mutasi gate 53/54/56, ringkasan harian notifikasi.

---

## 3m) Fase 73 — Studio: edit titik, undo, PDF latar, warna status, ekspor PNG (SELESAI, iteration_123)

| Bagian | Status |
|---|---|
| Seret titik sudut kavling + Undo/Ctrl+Z (titik, tambah, hapus) | **SELESAI** |
| PDF → PNG latar (PyMuPDF, pilih halaman) | **SELESAI** |
| Mode warna status unit + legenda berhitung | **SELESAI** |
| Ekspor PNG 2400px untuk brosur/WA | **SELESAI** |

## 10) Tugas berikutnya (sesudah Fase 73)
1. Toolbar studio: kelompokkan kontrol latar (PDF/opasitas) ke popover; simpan colorMode di localStorage.
2. Peta publik/brosur interaktif: tautan berbagi peta status ke calon pembeli (read-only).
3. Impor DXF/DWG; snap-to-grid & duplikasi kavling.
4. Backlog lama: engine.py 818>800, mutasi gate 53/54/56.

---

## 3n) Fase 74 — Studio: mode warna persisten, palet terkonfigurasi, dua status paralel (SELESAI, iteration_124)

| Bagian | Status |
|---|---|
| 4 mode warna (pemetaan / penjualan / pembangunan / gabungan) + legenda 2 kelompok | **SELESAI** |
| Mode warna diingat (localStorage) | **SELESAI** |
| Palet per organisasi (`/site-plan-studio/palette`) + dialog Atur warna | **SELESAI** |

## 10) Tugas berikutnya (sesudah Fase 74)
1. Halaman Site Plan & Showroom (non-studio) memakai palet organisasi yang sama + mode gabungan.
2. Peta publik/brosur interaktif read-only untuk calon pembeli.
3. Snap-to-grid & duplikasi kavling; popover kontrol latar.
4. Backlog lama: engine.py 818>800, mutasi gate 53/54/56.

---

## 3o) Fase 75 — SPR biaya all-in + pencairan KPR berkuitansi (SELESAI, iteration_125)

| Bagian | Status |
|---|---|
| `deal.costs` (BPHTB/notaris/bank/asuransi + all-in) ikut ke kontrak → breakdown `developer_borne` | **SELESAI** |
| Pencairan KPR = kuitansi metode `kpr` + jurnal, piutang berkurang | **SELESAI** |
| Add-on master berharga (qty × harga) di penawaran/SPR | **SELESAI** |

## 3p) Fase 75b — Hotfix penutup (SELESAI)

| Bagian | Status |
|---|---|
| `QuotationBreakdown.js` kondisional pajak diperbaiki + `QuotationBreakdown.test.js` (3 uji render, jest alias `@/`) | **SELESAI** |
| Guard pencairan: tagihan belum terbit / outstanding 0 → **409** (`LookupError` → 409); AR dibuat **sinkron** di `customer_convert.convert` & `contracts_engine.set_scheme` | **SELESAI** |
| `GET /api/gl/journals?source_type=&source_id=` (source_id ATAU source_deal_id) | **SELESAI** |
| Hint "hitung ulang" di ReserveDialog (`reserve-recalc-hint`); `DatePickerField` shadcn di KprPanel | **SELESAI** |
| `backend/.env` dipulihkan (`JWT_SECRET`); seed uji memakai unit khusus `UJI76*/UJI78*` | **SELESAI** |

## 3q) Fase 76 — Master komponen biaya + skema all-in (SELESAI)

| Bagian | Status |
|---|---|
| `allin_engine.py`: `cost_components` (kode, nama, `nominal_tetap`/`persen_harga`/`rumus_bphtb`, perlakuan default, GL beban/titipan/AP, kpr_only, aktif) | **SELESAI** |
| `allin_schemes` (banyak; per proyek/tipe; item = komponen + perlakuan + override nominal). Seed: **All-in Standar** (BPHTB+notaris developer), **Exclude** | **SELESAI** |
| `POST /deals/reserve`: `allin_scheme_id` → snapshot `costs.components`; `costs_manual`+alasan hanya `finance_manager/super_admin/owner` (403 untuk lain), ter-audit | **SELESAI** |
| `build_breakdown` membaca snapshot komponen (komponen master nonaktif tidak mengubah kontrak) | **SELESAI** |
| Migrasi kontrak lama → komponen `LEGACY` saat startup (`migrate_legacy_contracts`, idempoten) — breakdown tidak berubah | **SELESAI** |
| UI: `AllinSchemeField` (pilih skema, komponen read-only, manual khusus finance) di SPR; Config › **Biaya All-in** (`CostComponentPanel`, `AllinSchemePanel`) | **SELESAI** |

## 3r) Fase 77 — Penagihan & pembukuan biaya + add-on Rp0 (SELESAI)

| Bagian | Status |
|---|---|
| Pass-through: `POST /contracts/{id}/cost-invoices` (seri **INB**) → `POST /cost-invoices/{id}/pay` (kuitansi **KWB**, jurnal 1-1200 / **2-1470 Titipan Biaya Customer**) → `POST /contracts/{id}/cost-disbursements` (2-1470 / 1-1200, ≤ sisa titipan) | **SELESAI** |
| Developer-borne: `POST /contracts/{id}/cost-expenses` → AP bill (approved) + jurnal **6-1700 Beban Penjualan** / 2-1100; tidak 2× | **SELESAI** |
| `GET /contracts/{id}/costs-ledger` (sisa titipan, invoice, kuitansi, penyaluran, beban) → `CostBillingPanel` di Kontrak & Legal | **SELESAI** |
| Piutang unit = harga − DP (biaya tidak pernah masuk AR; kuitansi KWB tidak tercampur di AR) | **SELESAI** |
| Add-on harga master 0 → reservasi **409**; override `sales_manager+` + alasan → add-on berharga + diskon 100% (`discount_lines.source=override`) | **SELESAI** |

## 3s) Fase 78 — Pencairan KPR terkonfigurasi (SELESAI)

| Bagian | Status |
|---|---|
| `kpr_disbursement_schemes` per bank (tahapan % / nominal, syarat `akad`/`serah_terima`/`sertifikat`, total 100%, toleransi ±% default 1) — CRUD + Config › **Pencairan KPR** | **SELESAI** |
| `POST /contracts/{id}/kpr/disbursement-scheme` → `financing_apps.tranches` dari plafon SP3K | **SELESAI** |
| Pencairan (`stage/pencairan` atau `POST …/kpr/disbursements`) **dipilih dari tahapan**; koreksi ±toleransi hanya finance; validasi: AR terbit (409), ≤ outstanding (kelebihan ditolak; titipan hanya finance + alasan), ≤ plafon, tahap tidak 2×, syarat tahap | **SELESAI** |
| Pembatalan `POST …/kpr/disbursements/{id}/cancel` (finance_manager/superadmin, alasan ≥10) = `void_receipt` (jurnal balik) + status `dibatalkan` + tahap dibuka lagi | **SELESAI** |
| UI `KprDisbursementBox` (pilih skema, tahapan, daftar pencairan, batalkan) + select tahap di dialog pencairan | **SELESAI** |
| Gate 60 `scripts/verify_p75-78.py` (23 pemeriksaan) di `run_all_gates.sh`; pytest `tests/test_p76_78_allin_kpr.py` (9) + regresi P75 (7) | **SELESAI** |

## 3t) Fase 79 — Amandemen skema all-in, PDF INB/KWB, pengingat tahap KPR (SELESAI)

| Bagian | Status |
|---|---|
| `allin_amend.py`: `allin_amendments` (pending → approved/rejected). `POST /contracts/{id}/allin-amendments` (finance, alasan ≥10; ditolak bila ada pending / kuitansi KWB non-void / kontrak batal) → `POST /allin-amendments/{id}/decide` (finance_manager/superadmin/owner; **pengaju ≠ pemutus** kecuali super_admin; tolak wajib catatan) → `contracts.costs` diganti + `costs_history`, invoice INB unpaid di-void, notifikasi pengaju + finance, aktivitas customer | **SELESAI** |
| Edit langsung komponen biaya kontrak terbit → **409** "terkunci (snapshot) — ubah hanya lewat AMANDEMEN" | **SELESAI** |
| `GET /cost-invoices/{id}/pdf` & `GET /cost-receipts/{id}/pdf` (mesin dokumen existing: kop/layout, judul "Invoice Biaya Transaksi" / "Kwitansi Penerimaan Titipan Biaya") | **SELESAI** |
| Pengingat tahap: `ready_tranches` (status open + `_condition_met`), `run_tranche_reminders` satu notifikasi per (pengajuan, tahap) ke finance, cron harian 08:15 WIB; `GET /kpr/tranche-reminders`, `POST /kpr/tranche-reminders/run`. Batal pencairan tahap **mereset penanda** (notif lama → `kpr_tranche_cancelled`) sehingga pengingat terkirim ulang | **SELESAI** |
| UI: `AllinAmendmentBox` (ajukan / pending / Setujui-Tolak hanya untuk pemutus yang bukan pengaju / riwayat; error state daftar skema), tombol PDF di baris INB & KWB, banner `kpr-tranche-ready` di `KprDisbursementBox`, `TrancheReminderPanel` di Keuangan › Penagihan (error state bila akses ditolak) | **SELESAI** |
| RBAC: `_permitted` — `view_own` dipenuhi oleh `view`/`view_all` (dulu finance/finance_manager 403 pada semua GET Fase 77–79) | **SELESAI** |
| Uji: pytest `tests/test_p79_amend_pdf_reminder.py` (4) + `tests/test_p79_ui_api.py` (10, override ID via env `P79_KPR_CID`/`P79_CASH_CID`); testing agent iteration_127 (super_admin, lulus) + iteration_128 (finance/finance_manager 8/8 lulus) | **SELESAI** |

## 3v) Fase 80 — RAB terstruktur + SPK dari RAB (SELESAI)

| Bagian | Status |
|---|---|
| `rab_engine.py` + `routers/rab_router.py` (`/rab`): `rab_templates` (kind `unit_type`/`addon`, ref_code, items qty×harga, `step_code` opsional) — **RAB tertempel pada tipe unit** & RAB add-on (HPP); `GET/PUT /rab/templates/{kind}[/{ref}]` | **SELESAI** |
| `boq_items` + `scope` (unit legacy / **fasum** wajib `facility` + opsional `phase_id` fase konstruksi / **umum** jenis biaya); `GET /boq/items?scope=`; kode biaya ganda → 409 | **SELESAI** |
| `GET /rab/projects/{pid}/summary`: RAB unit = Σ RAB tipe × jumlah unit; RAB add-on terjual (deal aktif); fasum; umum; item lama = biaya bersama; alokasi per proyek `PUT /rab/projects/{pid}/allocation` (rata / luas_tanah / harga_jual) → HPP & margin per unit; total RAB vs nilai jual → margin; kendali RAB vs SPK-dari-RAB vs termin per lingkup | **SELESAI** |
| SPK dari RAB: `POST /rab/spk-draft` (mode unit / addon / unit_addon / fasum / umum — add-on diambil dari deal aktif unit) → `POST /subcon/spk/from-rab` (nilai kontrak = Σ baris; override wajib alasan; `rab_lines`, `spk_kind`, `unit_codes`; baris ber-`step_code` otomatis masuk lingkup jadwal unit, sisanya lump-sum + peringatan; item fasum/umum tidak boleh dikontrakkan 2× → 400) | **SELESAI** |
| `opname.candidates`: acuan harga per langkah mengutamakan RAB tipe unit | **SELESAI** |
| UI `/boq` › Rincian RAB: sub-tab RAB Unit (per tipe) + RAB add-on (`RabTypePanel`, `RabTemplateDialog` dengan optgroup langkah per template jadwal), Fasum/Fasos & Umum (`RabScopePanel`), Ringkasan & HPP (`RabSummaryPanel`), Item lama; `/subcon` tombol **SPK dari RAB** (`SpkFromRabDialog`); detail SPK menampilkan dasar RAB & override | **SELESAI** |
| Uji: pytest `tests/test_p80_rab.py` (6); testing agent iteration_130 (semua alur lulus; temuan diperbaiki: optgroup langkah, peringatan langkah tidak ada di jadwal, kolom harga, guard kontrak ganda, penanda "belum ada RAB") | **SELESAI** |

## 10) Tugas berikutnya (sesudah Fase 81)
1. Amandemen komponen manual (`items`) dari UI; paginasi/limit panel pengintat tahap bila baris > 20.
2. Riwayat versi RAB: diff per baris (baris ditambah/dihapus/harga berubah) antara dua versi; ekspor Excel RAB tipe tersimpan.
3. Kendali fasum: pengingat otomatis ke PM saat termin fasum tertahan oleh progres fase; dashboard progres fase vs termin lintas proyek.
4. Backlog lama: engine.py 821>800 (pecah modul), mutasi 53/54/56, audit form `<Input>` tanpa label di 6 file (CostComponentPanel, KprDisbursementSchemePanel, PaymentSchemePanel, CostBillingPanel, KprPanel, SpkFromRabDialog).

## 3x) Fase 81b — RAB terstruktur masuk BI & Analitik (SELESAI)

| Bagian | Status |
|---|---|
| `metrics/rab.py`: RAB-01 RAB total terstruktur (idr, komposisi), RAB-02 margin HPP proyeksi (idr), RAB-03 margin HPP per tipe (pct, unit tipis <10%), RAB-04 SPK fasum melampaui progres fase (count), RAB-05 selisih SPK vs RAB (idr), RAB-06 revisi RAB (count + deret harian, ikut rentang tanggal). Semua punya drill, formula, requires; snapshot RAB-01..05 | **SELESAI** |
| Dashboard eksekutif +RAB-02/03, proyek +RAB-01/04/05/06 (`analytics_engine.DASHBOARDS`, `bi/dashboards.js`); `BGT-06` memakai RAB terstruktur | **SELESAI** |
| Uji: `tests/test_p81b_rab_metrics.py` (4), `scripts/verify_analytics.py` PASSED, layar BI dicek | **SELESAI** |

## 3w) Fase 81 — Versi RAB, salin dari tipe lain, impor Excel, kendali fasum vs progres fase (SELESAI)

| Bagian | Status |
|---|---|
| `rab_engine.save_template`: bila baris berubah → versi lama disimpan utuh ke `rab_template_versions` (version, items, total, saved_by/at, replaced_by/at, note) dan `version` naik; simpan identik tidak menaikkan versi; `note` (catatan perubahan) tersimpan | **SELESAI** |
| `rab_templates_ext.py`: `list_versions` (aktif + riwayat, selisih total antar versi), `get_version`, `restore_version` (= save_template ulang, note "Pulihkan vN"), `copy_items` (sumber ≠ tujuan, sumber wajib ber-RAB, faktor 0<f≤10, harga satuan × faktor → pratinjau), `import_workbook` (template .xlsx: header kunci + keterangan + contoh + validasi daftar kategori SSOT + sheet PETUNJUK), `parse_import` (pratinjau tervalidasi: uraian wajib, volume>0, harga ≥0, kategori tak dikenal → lainnya + peringatan, kode langkah tak ada di jadwal → peringatan) | **SELESAI** |
| Endpoint: `GET /rab/import-template.xlsx?kind=`, `GET /rab/templates/{kind}/{ref}/versions[/{vid}]`, `POST …/versions/{vid}/restore`, `POST …/copy-from`, `POST …/import` (multipart ≤5 MB .xlsx), `GET /rab/spk/{sid}/fasum-cap`; `PUT /rab/templates/{kind}/{ref}` menerima `note` | **SELESAI** |
| Kendali fasum: `fasum_phase_cap` (batas termin kumulatif = progres fase konstruksi tertaut, ditimbang nilai baris `rab_lines`; baris tanpa fase tidak dibatasi & dilaporkan `uncovered_value`), `assert_fasum_claim_within_phase` dipanggil di `POST /subcon/claims` untuk SPK lump-sum `spk_kind=fasum` → 400 dengan pesan fase & batas; `fasum_control` per SPK fasum (nilai kontrak, termin disetujui/diajukan, batas, sisa, `over`) ikut di `GET /rab/projects/{pid}/summary` | **SELESAI** |
| UI: `RabTemplateTools` (salin dari tipe/add-on lain × faktor → editor, tombol Impor Excel + unduh template, laporan kesalahan/peringatan impor), banner "Belum tersimpan" + "Batalkan, muat RAB tersimpan", input catatan perubahan, `RabVersionHistory` (v aktif/lama, tanggal, oleh, baris, total, selisih, Pulihkan), badge `vN` di tabel tipe; `RabFasumControl` di Ringkasan & HPP; hint `claim-fasum-cap` di `SubmitClaimDialog` (merah bila melebihi batas). TestIds `constants/testIds/p81.js` | **SELESAI** |
| Uji: pytest `tests/test_p81_rab_ext.py` (4) + `tests/test_p81_frontend_support.py` (5, testing agent); gate 61 `scripts/verify_p80_81.py` 32/32 (didaftarkan di `run_all_gates.sh`); testing agent iteration_131 7/7 skenario UI lulus | **SELESAI** |

## 10-lama) Tugas berikutnya (sesudah Fase 80)
1. ~~Gate 61~~ → `scripts/verify_p80_81.py` (Fase 81).
2. ~~Kendali fasum berbasis progres fase konstruksi~~ → SELESAI Fase 81.
3. ~~RAB tipe: salin dari tipe lain / impor Excel; versi RAB tipe~~ → SELESAI Fase 81.
4. Amandemen komponen manual dari UI; paginasi panel pengingat tahap; backlog lama (engine.py 821>800, mutasi 53/54/56).

## 10-lama) Tugas berikutnya (sesudah Fase 79)
1. Gate 61 `scripts/verify_p79.py` (amandemen, 409 snapshot, PDF INB/KWB, pengingat idempoten + reset) ke `run_all_gates.sh`; mutasi gate 60 (`scripts/mutasi_78.py`).
2. Panel pengingat tahap: paginasi/limit + filter bank bila baris > 20; riwayat amandemen berbentuk tabel bila > 3 baris.
3. Amandemen komponen manual (`items`) dari UI (backend sudah mendukung, UI hanya pilih skema).
4. ~~Input nominal Rp bermasker~~ → SELESAI (Fase 79b, lihat 3u). Backlog lama (engine.py 818>800, mutasi 53/54/56).

## 3y) Sesi lanjutan 2026-09-06 — pemulihan repo `hjzkzjsh/sipro`, gate merah dibersihkan, Audit Tahap 6–7 ditutup (SELESAI)

| Bagian | Status |
|---|---|
| Pemulihan lingkungan (clone, `.env` backend: `JWT_SECRET`/`SEED_DEMO_USERS`/`BACKUP_DIR`/`DEFAULT_ORG_ID`/`PORTAL_MASTER_OTP`, deps, seed, login, `memory/test_credentials.md`) | **SELESAI** |
| 3 gate merah pra-eksisting: `verify_contract_legal_docgen` (K11c kode penahan `booking_fee_belum`/`slik_belum`/`demografi_belum_lengkap` → Kamus Data; fixture melewati SLIK **berbukti** lewat API), `verify_p66` (probe tabel menyalakan bagian `biaya` yang mati bawaan), `verify_p67` (h1 SimpleMarkdown → `page-title`) | **SELESAI** |
| Audit Tahap 6 (CFG-01, FIN-01/02/03, PRJ-01/02, BI-01/02) — kode sudah ada, kini DIJAGA `tests/test_audit_tahap6_angka.py` (17) | **SELESAI** |
| Audit Tahap 7 §2 — **gate 62 `verify_card_drilldown.py`** (148 pemeriksaan: Beranda per peran, partisi lead, keuangan + ember aging, BI rumus & nama, penjaga kode) di `run_all_gates.sh` | **SELESAI** |
| Audit Tahap 7 §3 — `audit_forms_deep.py` E6 `<SelectItem>` hardcode; 16 dropdown/14 berkas → `<ReferenceItems group=…/>`; grup SSOT `wa_inbound_type` | **SELESAI** |
| Suite pytest: `conftest.py` satu sumber URL (`frontend/.env`), `test_p88` kunci `lead.score.events`, `test_iter147` skip bila demo di-seed, `test_iter148` (purge DESTRUKTIF) hanya dengan `SIPRO_ALLOW_PURGE_TEST=1`, `test_iter151`/`test_doc_p66` disesuaikan | **SELESAI** |

## 11) Tugas berikutnya (sesudah sesi 2026-09-06)
1. Pulihkan tes legacy yang bergantung data seed lama (`test_p80_rab` butuh tipe `TIPE-45-90`, `test_p69b/c`, `test_p91/92/93`, `test_p71_numbering_ext` 41→51 aturan) — jadikan fixture-nya membuat datanya sendiri lewat API.
2. Tes WA yang menuntut kredensial Meta (`test_p100_wa_setup`, `test_p94_95_wa`): skip jujur bila kredensial kosong.
3. Audit lanjutan area belum diaudit (AUDIT_SINTESIS Bagian 6): akuntansi/GL, metrik BI non-lead, portal pembeli.
4. Backlog lama: engine.py > 800 baris, mutasi gate 53/54/56.



| Bagian | Status |
|---|---|
| 88A `PhoneInput` (+62 tetap, ketik nomor lokal, output E.164) di AddLeadDialog, SimulateLeadDialog, AddCustomerDialog | **SELESAI** |
| 88B `lead_scoring.py` — bobot `lead.score.weights`, band `lead.score.bands`; naik (kontak, aktivitas, agenda, balasan WA, disposisi +) turun (diam ≥7 hari, disposisi −, ditutup); `GET/POST /leads/{id}/score|rescore`; sapuan harian `lead_rescore_tick`; `LeadScoreCard` | **SELESAI** |
| 88C aturan harga `target` (price/dp/booking_fee/cost+komponen); `compute_discounts(bases)`, `apply_component_discounts` (termin DP), `apply_cost_discounts` (komponen all-in); AR memakai fungsi yang sama; token `{{discount_rows}}` di SPR; UI dialog/tabel/breakdown; seed PROMO-DP/BF/BPHTB | **SELESAI** |
| 88D naskah SPR_CASH_STAGED tersendiri, nomor `SPR-CASHB` terpisah, `ensure_templates` tidak menimpa naskah tersunting | **SELESAI** |
| 88E `handover.settlement_policy` (wajib_lunas / minimal_persen + `settlement_min_paid_pct` / peringatan) | **SELESAI** |
| Uji: testing agent iteration_135 — 21 pytest (2 gagal → validator target=cost diperbaiki, kini 400) + 5 skenario UI lulus | **SELESAI** |

## 3u) Fase 79b — Input Rupiah bermasker (SELESAI)

| Bagian | Status |
|---|---|
| `components/ui/rupiah-input.jsx` — `RupiahInput`: tampil `Rp 1.500.000` saat mengetik (id-ID), menolak huruf/karakter lain, tanpa desimal, maks 15 digit, nol depan dibuang; `onChange` menerima event-like `{target:{value:"1500000"}}` (string digit, sama seperti `type=number`) sehingga handler & payload API tidak berubah; kelas ukuran (`h-8`, `text-xs`) diteruskan ke input, kelas grid/lebar ke pembungkus | **SELESAI** |
| 70 field nominal Rp di 55 file dikonversi (`scripts/convert_rupiah_inputs.py` = daftar file:baris); 5 field dwi-mode (%/Rp: CostComponentPanel, PaymentSchemePanel termin, PricingRuleDialog, FeeRuleFormDialog, SchemeDialogs) memakai RupiahInput hanya saat mode nominal; Aturan Bisnis (`SettingsPanel`) memasker aturan berlabel "(Rp)"; field persen/qty/hari tetap `type=number` | **SELESAI** |
| Perbaikan ikutan: kolom Debit/Kredit `AddJournalDialog` 3/3 (kredit tidak terpotong); `SheetTitle` sr-only saat "Memuat…" di `ProjectsPage` & `AppointmentDetailSheet` (hilangkan console error Radix) | **SELESAI** |
| Uji: testing agent iteration_129 — masker + 5 alur simpan (beban AP, jurnal manual, kas bon, harga unit, skema pembayaran) 100% lulus, tanpa warning controlled/uncontrolled | **SELESAI** |


## 3v) Jalur 1 — SPR ≡ skema pilihan ≡ AR (SELESAI, sesi 2026-09-08 #6)

| Bagian | Status |
|---|---|
| `engine._h_deal_booked` → `create_ar_for_deal(deal, scheme_id=deal.scheme_id)`; konversi meneruskan `scheme_id` | **SELESAI** |
| Kontrak = jenis skema deal (`deal_scheme_kind`), `payment_scheme_id` tersimpan saat `ensure_contract`; `deal.scheme_explicit` mengunci (400) / skema bawaan di-repoint + AR disusun ulang; UI Select terkunci | **SELESAI** |
| docgen: DP% & cicilan dari AR, termin unit/add-on dipisah, `{{cost_rows}}` dari snapshot all-in, "SEMENTARA" hanya komponen pembeli, block `skema_deal_beda` | **SELESAI** |
| `slik.scheme_kinds` (SPR & booking), `addon.spkt_scheme_kinds` (akad KPR / AJB tunai) | **SELESAI** |
| `tests/test_spr_single_source.py` 4/4; gate 46 HIJAU; invarian LULUS; testing agent iteration_20 lulus | **SELESAI** |
| Pre-existing: gate 48 D7 (paid>0 vs pengalihan booking fee otomatis), finance_engine.py 823 baris | **BELUM** |
