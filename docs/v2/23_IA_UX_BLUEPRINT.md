# 23 — IA & UX BLUEPRINT V2 (task-centric · customer-centric · unit-centric)

> Menggantikan `docs/analysis/03_IA_WORKHUB_UX_BLUEPRINT.md` pada bagian navigasi & pola tabel.
> Prinsip owner: **"TASK centric untuk memandu user, LEAD/CUSTOMER centric untuk proses bisnis, PROJECT&UNIT centric untuk pembangunan."**

## 1. Tiga sumbu navigasi (dan kapan dipakai)

| Sumbu | Pertanyaan user | Entry point | Objek utama |
|---|---|---|---|
| **TASK** | "apa yang harus saya kerjakan sekarang?" | Beranda / Work Hub | `tasks` (jobdesk, SLA, bukti) |
| **CUSTOMER** | "bagaimana orang ini bergerak dari lead sampai serah terima?" | Pipeline → **Profil Lead** → **Profil Customer** | `leads`, `contracts`, `payment_plans` |
| **UNIT** | "apa status rumah ini: terjual? dibangun? dokumen?" | Proyek → Cluster/Blok → **Unit 360** | `units`, `build_schedules`, `documents` |

Aturan: **setiap objek utama hanya punya SATU halaman rumah** (canonical page). Semua tempat lain hanya *link* ke sana. Ini menghapus penyakit "informasi sama tersebar di banyak menu".

## 2. Bahasa desain (memperbaiki CR-27 … CR-31)
1. **Tabel-first untuk data transaksional.** Kartu HANYA untuk: KPI ringkas, entitas visual (unit di siteplan), dan panel pengumuman. Deal, lead, unit, tugas, pembayaran, dokumen = **tabel**.
2. **Hierarki tipografi wajib**: `page-title 24/32 semibold` · `section 16/24 semibold` · `label 12/16 medium uppercase tracking-wide muted` · `data 14/20` · `numeric tabular-nums`. Angka uang selalu `tabular-nums` + rata kanan.
3. **Detail panjang = halaman**, bukan drawer. Drawer hanya untuk aksi cepat (≤1 layar, ≤6 field). Aturan: >6 field atau ada tab ⇒ **halaman**.
4. **Setiap tabel wajib**: pencarian, filter multi (tahap/status/sumber/PIC/tanggal), sort kolom, pilihan kolom, paginasi + total, aksi massal, ekspor CSV/XLSX, dan **kolom umur (aging)**.
5. **Aging & urgensi** ditampilkan sebagai dua angka: **umur total** (sejak lead masuk) dan **umur tahap** (sejak masuk tahap sekarang) dengan warna: `≤ SLA` netral, `> SLA` kuning, `> 2×SLA` merah.
6. **Warna status tidak boleh hanya warna** — selalu label teks (aksesibilitas + gate `verify_ui_surfaces.py`).
7. **Panel wajib punya latar** (bukan transparan) — sudah jadi gate sejak Fase 38, tetap berlaku.
8. **Setiap field wajib punya label** (gate "field bisu" Fase 38).

## 3. Peta menu LAMA → BARU

| Lama (`navigationConfig.js`) | Baru | Alasan |
|---|---|---|
| Beranda | **Beranda (Control Tower)** | tetap; tambah kartu target & BI ringkas |
| Work Hub, Notifikasi | **Kerja**: Tugas & Papan Divisi, Notifikasi | tetap |
| Lead | **CRM › Pipeline Lead** (+ halaman `/leads/:id`) | CR-10, CR-30 |
| Agenda & Survey | **CRM › Agenda & Survey** (kalender besar + tabel tunggu) | CR-19 |
| Inbox WA | **CRM › Percakapan (WA)** | CR-22 |
| Automasi & Channel | **Marketing › Automasi & Channel** | pisah domain marketing |
| — | **Marketing › Kampanye & Biaya Iklan** (baru) | D1, CR-14 |
| — | **Marketing › Atribusi & CAPI** (pindahan dari Automasi) | kejelasan |
| Deal & Unit + Customer & KPR | **CRM › Customer & Kontrak** (satu alur: SPR → dokumen → bayar → legal → serah terima) | CR-18 |
| — | **CRM › Mitra & Fee** (baru; Marketing Fee lama jadi tab "Tagihan Fee") | CR-09 |
| Site Plan & Showroom | **Site Plan** (seksi sendiri, aksi menyesuaikan peran) | CR-23 |
| Proyek & Unit | **Proyek › Master Proyek** (proyek→cluster→blok→unit) + halaman `/units/:id` | CR-05, CR-33 |
| Progres & Mutu, Kalender Jadwal, Kalibrasi, Buku Harian & Punch | **Proyek › Pembangunan** (tabs: Papan Unit · Kalender · Lapangan · Analitik & Kalibrasi) | CR-24, CR-32 |
| Material & Opname | **Proyek › Material & Opname** | tetap |
| Perizinan & Dokumen | **hilang sebagai menu** → tab di Unit 360 & Proyek; daftar global masuk **Dokumen** | CR-25 |
| RAB/BoQ, Subkon & SPK, Pengadaan | **Pengadaan** (tetap) + tab "Realisasi vs RAB" | CR-16 |
| Keuangan/Akuntansi/Pajak | tetap; tambah tab **Rencana Bayar** & **Refund/Pembatalan** | CR-07, CR-26 |
| — | **Analitik & BI** (baru): Eksekutif · Penjualan & Lead · Marketing · Proyek & Biaya · Kinerja Tim | CR-13…CR-17 |
| Admin › Master Data | **Konfigurasi** (baru, seksi sendiri): Bisnis (toggle), Dokumen Syarat, Form Survei, Biaya & Harga, Target, Mitra, SSOT, Integritas Data | CR-34, D3, D5 |
| Admin (Pengguna, RBAC, Organisasi, Audit) | tetap di **Admin** | |

**Jumlah item menu**: dari 33 → **26** (7 menu dilebur), tanpa menghapus satu pun fitur.

## 4. Halaman kanonik & isi tab

### 4.1 `/leads/:id` — Profil Lead (BARU, CR-10)
Header: nama · telepon (aksi WA/telepon) · sumber+kampanye/mitra · pemilik (PIC) · skor+band · **umur total & umur tahap** · tombol aksi utama (Next Best Action).

| Tab | Isi | Sumber data |
|---|---|---|
| Ringkasan | data diri + demografi + minat (proyek/cluster/tipe) + checklist syarat tahap + NBA | `leads`, `lead_lifecycle.requirements()` |
| Timeline | gabungan `stage_history` + `activities` + `messages` + `tasks` + upload dokumen, **selalu menampilkan aktor** | CR-10, W6 |
| Dokumen | matriks `doc_requirements` × status, unggah/verifikasi/tolak, kedaluwarsa | [24](24_CRM_LEAD_SPEC.md) §6 |
| Survey | jadwal, hasil form, foto, riwayat reschedule/batal + alasan | [24](24_CRM_LEAD_SPEC.md) §10 |
| BI/SLIK | hasil + bukti iDeb + riwayat (terpisah dari urutan, D7) | `slik.py` |
| Unit & SPR | unit yang dipegang, SPR terbit, booking fee & statusnya | [24](24_CRM_LEAD_SPEC.md) §5 |
| Percakapan | thread WA + template | `conversations`, `messages` |
| Fee Mitra | bila lead dari mitra: aturan fee yang berlaku + estimasi fee | [25](25_PARTNER_SPEC.md) |

### 4.2 `/customers/:id` — Profil Customer
Tabs: Ringkasan · Kontrak & Harga · **Rencana Bayar** (termin, jatuh tempo, tunggakan) · KPR (hanya bila skema KPR) · Dokumen & Legal (PPJB/AJB/BAST) · Unit & Konstruksi · Komplain/Retensi · Timeline.

### 4.3 `/units/:id` — Unit 360
Tabs: Ringkasan (tipe, LT/LB, hook, kelebihan tanah, harga) · Penjualan (status, customer, kontrak) · Pembangunan (jadwal, progres, QC, inspeksi, punch, foto) · Dokumen & Perizinan · Riwayat status.

### 4.4 `/projects/:id` — Proyek
Tabs: Ringkasan · **Cluster & Blok & Unit** (tree + tabel) · Target & Realisasi · RAB vs Realisasi · Perizinan Proyek · Site Plan · Tim.

## 5. Komponen pola yang HARUS dibuat (dipakai semua halaman)
Lokasi: `frontend/src/components/patterns/` (sudah ada folder `patterns`).

| Komponen | Kontrak singkat | Batas |
|---|---|---|
| `DataTable` | `columns[], rows, total, query{q,filters,sort,page}, onQueryChange, bulkActions[], columnPicker, exportCsv, emptyState, loading` | ≤300 baris (util) atau pecah |
| `FilterBar` | filter deklaratif: `select|multiselect|daterange|numberrange|text`, chip aktif, reset | ≤200 |
| `AgingCell` | `startAt, slaHours` → teks `3h 4j` + warna + tooltip | ≤80 |
| `StatusPill` | sudah ada; wajib `label` teks | ada |
| `EntityHeader` | judul + meta chips + aksi utama/sekunder | ≤150 |
| `TabPage` | layout halaman dengan tab yang sinkron ke URL (`?tab=`) | ≤150 |
| `TimelineFeed` | item `{at, actor, kind, title, body, evidence[]}` | ≤200 |
| `DocMatrix` | requirement × status + unggah/verifikasi | ≤250 |
| `KpiCard` | `label, value, delta, hint, trend[]` (sparkline recharts) | ≤120 |
| `ChartFrame` | judul + legenda kontras + empty/error state + unduh PNG/CSV | ≤200 |
| `MoneyText` | format Rp, `tabular-nums`, opsi ringkas (jt/M) | ≤60 |

**Pustaka visualisasi:** `recharts@3.6.0` **sudah terpasang** (`frontend/package.json:58`) — pakai ini, jangan tambah pustaka chart baru. Untuk tabel pro tambahkan **`@tanstack/react-table`** (headless, ringan, cocok dengan shadcn) — satu-satunya dependensi frontend baru yang direkomendasikan; `@tanstack/react-query` sudah ada.

## 6. Redesain Inbox WA untuk 1000+ lead (CR-22)
- **3 kolom**: (a) rail filter sempit (tahap, urgensi, belum dibalas, SLA lewat, PIC, kampanye/mitra), (b) daftar percakapan **virtualized** (baris padat 56px: nama, cuplikan, umur balasan, chip tahap, badge SLA), (c) thread + panel konteks lead (ringkas, tautan ke Profil Lead).
- **Urutan default**: SLA terlewat → belum dibalas terlama → skor tertinggi.
- **Aksi massal**: assign, tag, kirim template, tandai tidak relevan.
- **Metrik di header**: belum dibalas, rata-rata waktu balas hari ini, SLA breach.

## 7. Aturan pengujian UI (agar tidak jadi "cantik tapi bohong")
1. Setiap elemen interaktif punya `data-testid` dari registry `frontend/src/constants/testIds` (pola yang sudah dipakai).
2. Gate `scripts/verify_ui_surfaces.py` (sudah ada) diperluas: wajib ada filter+sort+search pada halaman daftar yang terdaftar di peta IA baru.
3. Angka pada KPI wajib bisa di-drill-down ke daftar barisnya (klik KPI → tabel terfilter). Tanpa drill-down = dianggap tidak selesai.
4. Semua state ditangani: loading skeleton, kosong (dengan aksi), error (dengan pesan sebab), tanpa data izin (403 informatif).
