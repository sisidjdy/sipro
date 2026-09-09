# 40 — PETA NAVIGASI V2 (lama → baru)

> Dibuat pada Fase 40c. **Tidak ada fitur yang dihapus** — tujuh pintu menu dilebur menjadi hub
> bertab, dan seluruh rute lama tetap hidup sebagai alias. Peta ini juga tersedia **di dalam
> aplikasi**: sidebar → “Peta menu baru (menu saya ke mana?)”
> (`frontend/src/config/navMigrationMap.js` + `components/layout/NavMigrationDialog.js`),
> sehingga pemakai lama tidak perlu membuka dokumentasi ini.

## 1. Angka yang bisa diverifikasi

| Ukuran | Sebelum | Sesudah |
|---|---|---|
| Item menu non-admin (rute unik yang bisa diklik) | 31 | **26** |
| Baris sidebar non-admin (termasuk duplikat) | 32 | 26 |
| Item “Segera Hadir” (terkunci, **tanpa route**) | 0 | 4 |
| Rute aplikasi | 36 | 37 (`/build` baru; tidak ada yang dihapus) |

Gate `scripts/verify_ia_v2.py` menegakkan angka & aturannya (mis. item “Segera Hadir” tidak
boleh punya `path`, dan menu yang dilebur tidak boleh muncul lagi di sidebar sementara rutenya
WAJIB tetap ada).

## 2. Peta menu

| Menu lama | Lokasi baru | Rute | Alasan |
|---|---|---|---|
| Beranda | Beranda (Control Tower) | `/` | KPI kini bisa di-drill-down |
| Work Hub | Kerja › **Tugas & Papan Divisi** | `/tasks` | nama menyebut isinya; daftar jadi tabel pro |
| Notifikasi | Kerja › Notifikasi | `/notifications` | tetap |
| Lead | CRM › **Pipeline Lead** | `/leads` | profil kanonik `/leads/:id` |
| Agenda & Survey | CRM › Agenda & Survey | `/appointments` | tetap |
| Inbox WA | CRM › **Percakapan (WA)** | `/inbox` | istilah seragam dengan playbook WA |
| **Deal & Unit** | CRM › Customer & Kontrak → tab **Deal & Unit** | `/customers?hub=deal` | satu alur: unit → deal → pembeli → dokumen → bayar |
| **Customer & KPR** | CRM › Customer & Kontrak → tab **Pembeli** | `/customers?hub=pembeli` | idem; profil kanonik `/customers/:id` |
| Automasi & Channel | Marketing › Automasi & Channel | `/automation` | domain marketing dipisah dari CRM |
| Proyek & Unit | Proyek › **Master Proyek** | `/projects` | struktur proyek→cluster→blok→unit |
| **Progres & Mutu** | Proyek › Pembangunan → tab Progres & Mutu | `/build?hub=progres` | 4 menu pembangunan jadi 1 hub |
| **Kalender Jadwal** | Proyek › Pembangunan → tab Kalender Jadwal | `/build?hub=kalender` | idem |
| **Buku Harian & Punch** | Proyek › Pembangunan → tab Buku Harian & Punch | `/build?hub=lapangan` | idem |
| **Kalibrasi Jadwal** | Proyek › Pembangunan → tab Kalibrasi Jadwal | `/build?hub=kalibrasi` | idem |
| — (baru) | Proyek › Pembangunan → tab **Papan Unit** | `/build?hub=unit` | tabel unit LINTAS proyek (mis. semua unit QC hold) |
| Material & Opname | Proyek › Material & Opname | `/materials` | tetap |
| **Site Plan & Showroom** (muncul 2×) | Proyek › **Site Plan** (satu item, terlihat utk penjualan & proyek) | `/site-plan` | hapus duplikasi baris menu |
| **Perizinan & Dokumen** | **Dokumen** → tab **Perizinan** | `/documents?hub=perizinan` | daftar global izin masuk Dokumen; izin per objek tetap di Unit 360 & Proyek |
| RAB/BoQ · Subkon & SPK · Pengadaan | Pengadaan (3 item) | `/boq` `/subcon` `/procurement` | tetap |
| Keuangan | Keuangan › AR / AP / Komisi | `/finance` | tab kini hidup di URL (`?tab=ar`) |
| Marketing Fee | **CRM › Mitra & Fee → tab “Tagihan Fee”** | `/partners?hub=tagihan` | **Fase 42 SELESAI**: keluar dari sidebar. Rute `/marketing-fee` tetap terdaftar tetapi **MENGALIHKAN** ke tab Tagihan Fee (satu pintu); halaman lama + tab “Master Agen” dihapus karena kembar dengan “Master Mitra” |
| **Kas Bon** | Keuangan › Kas Bon | `/petty-cash` | pindah dari grup terpisah “Kas & Pengeluaran” |
| **Kas & Bank** | Keuangan › Kas & Bank | `/cash-bank` | **Fase 82**: posisi kas, buku kas/bank per rekening, transfer internal, master rekening & kas (`docs/v2/52`) |
| Akuntansi (5 item) | Akuntansi | `/accounting` `/accounting/reports` `/fixed-assets` `/corporate-financing` `/tax` | tetap |
| Komplain & CS | Layanan › Komplain & CS | `/complaints` | daftar jadi tabel pro + KPI drill-down |
| Dokumen | **Dokumen & Perizinan** | `/documents` | lihat baris Perizinan di atas |
| Pusat Konfigurasi | Konfigurasi | `/config` | tetap |
| Admin (5 item) | Admin | `/admin/*` | tetap |

## 3. Rute alias yang SENGAJA dipertahankan

`/deals` · `/construction` · `/build-calendar` · `/build-calibration` · `/field` · `/permits` · `/marketing-fee` (Fase 42)

Alasan: notifikasi & tugas yang sudah terbit menyimpan tautan ke rute tersebut, dan pemakai
menyimpan bookmark. Menghapusnya berarti “fitur hilang” dari sudut pandang pemakai walau
kodenya masih ada. Rute-rute ini tidak lagi muncul di sidebar (pintu masuknya di hub).

## 4. “Segera Hadir” (terkunci di sidebar, tanpa route)

| Item | Grup | Fase |
|---|---|---|
| ~~Mitra & Fee~~ | ~~CRM~~ | **42 — SUDAH DIBUKA** (`/partners`, hub 5 tab) |
| ~~Kampanye & Biaya Iklan~~ | ~~Marketing~~ | **43 — SUDAH DIBUKA** (`/campaigns`) |
| ~~Atribusi & CAPI~~ | ~~Marketing~~ | **43 — SUDAH DIBUKA** (`/attribution`) |
| ~~Analitik & BI~~ | ~~Analitik & BI~~ | **44 — SUDAH DIBUKA** (`/bi`, hub 6 tab: 5 dashboard persona + Kamus Metrik) |

Aturan: item “Segera Hadir” **tidak boleh punya `path`** sehingga mustahil menjadi halaman
kosong; `check_nav_map.py` CHECK 2 + `verify_ia_v2.py` menjaganya.

## 5. Drill-down KPI (US-40-4)

Tautan drill dibentuk di **backend** (`routers/work_router.py::_kpis`) supaya definisi angka
dan definisi filter daftar tidak bisa berbeda. Contoh yang sudah terbukti di layar:

| KPI | Tautan | Hasil |
|---|---|---|
| Tugas Terlambat (org) = 4 | `/tasks?tab=tasks&scope=all&bucket=overdue` | tabel berisi tepat 4 baris |
| AR Outstanding | `/finance?tab=ar&status=unpaid,partial` | tab Piutang + chip filter status |
| QC Hold | `/build?hub=unit&construction_status=qc_hold` | Papan Unit terfilter |
| Lewat SLA (komplain) | `/complaints?sla=breached` | daftar komplain lewat SLA |

## 6. Tambahan Fase 41 — tab “Umur Tahap & SLA”

| Permukaan | Lokasi | Rute | Catatan |
|---|---|---|---|
| Umur Tahap & SLA | Kerja › Tugas & Papan Divisi → tab **Umur Tahap & SLA** | `/tasks?tab=aging` | laporan umur tahap 7 objek (lead, deal, tugas, komplain, pembeli, tagihan AR, dokumen); setiap angka punya tautan drill ke daftar terfilter |
| Ubah ambang SLA | tautan “Ubah SLA” di tab itu | `/config?group=sla` | ambang SLA tinggal di Pusat Konfigurasi, BUKAN di komponen |

Filter **“Umur / SLA”** (`?sla=over|over2|ok|none`) kini seragam di daftar Lead, Tugas, Komplain,
Deal, Pembeli, Tagihan (AR), dan Dokumen — dieksekusi di database atas field tersimpan
`stage_due_at`, sehingga angka laporan = angka daftar. Nilai filter tak dikenal menghasilkan
daftar KOSONG (bukan diabaikan diam-diam) supaya pemakai sadar filternya tidak berlaku.

## 7. LEDGER PINTU RESMI (SSOT gate — Fase 44)

**Masalah yang ledger ini betulkan.** Sampai Fase 43, `scripts/verify_ia_v2.py` menjaga jumlah
pintu menu dengan **satu angka mati**: `MAX_NONADMIN_ITEMS = 26` (potret Fase 40c). Angka itu
membusuk begitu roadmap membuka pintu yang MEMANG direncanakan di §2/§4 dokumen ini: Fase 42
membuka **Mitra & Fee** (netral karena `Marketing Fee` keluar dari sidebar), lalu Fase 43
membuka **Kampanye & Biaya Iklan** + **Atribusi & CAPI** sehingga gate memerah (28 > 26)
padahal tidak ada yang salah — dan “memerah karena kadaluwarsa” adalah cara tercepat membuat
gate diabaikan orang.

**Perbaikan yang dipilih (bukan menaikkan angka diam-diam).** Sidebar sekarang dibandingkan
dengan **daftar pintu resmi di bawah** (bukan sekadar dihitung). Efeknya:

- menambah pintu menu **tanpa** mendaftarkannya di sini → gate GAGAL (“pintu asing”);
- menghapus/mengubah rute pintu yang terdaftar → gate GAGAL (“pintu hilang”) — mencegah fitur
  hilang diam-diam seperti kejadian Fase 40c;
- setiap pintu wajib menyebut **fase pembukaannya** (jejak keputusan) dan wajib punya `<Route>`
  di `App.js` + entri `PAGE_META`;
- **anggaran anti-sprawl tetap ada**: `DOOR_BUDGET = 30`. Melewatinya berarti IA harus dilebur
  jadi hub bertab (pola §2), bukan sekadar menaikkan angka.

`ANGGARAN` sengaja 30, bukan tak terbatas: sisa 2 kursi diperuntukkan **Analitik & BI** (Fase 44)
dan satu pintu cadangan; pekerjaan Target & Budget serta Konsolidasi Konstruksi WAJIB masuk
sebagai **tab di hub yang sudah ada** (`/bi`, `/boq`, `/build`), bukan pintu baru.

<!-- NAV_DOOR_LEDGER -->
```json
[
  {"route": "/",                     "label": "Beranda",              "group": "Beranda",      "phase": "0"},
  {"route": "/tasks",                "label": "Tugas & Papan Divisi", "group": "Kerja",        "phase": "0 (nama baru 40c)"},
  {"route": "/notifications",        "label": "Notifikasi",           "group": "Kerja",        "phase": "0"},
  {"route": "/leads",                "label": "Pipeline Lead",        "group": "CRM",          "phase": "1 (profil 41)"},
  {"route": "/appointments",         "label": "Agenda & Survey",      "group": "CRM",          "phase": "14"},
  {"route": "/customers",            "label": "Customer & Kontrak",   "group": "CRM",          "phase": "40c (lebur Deal & Unit + Customer)"},
  {"route": "/inbox",                "label": "Percakapan (WA)",      "group": "CRM",          "phase": "17"},
  {"route": "/partners",             "label": "Mitra & Fee",          "group": "CRM",          "phase": "42"},
  {"route": "/automation",           "label": "Automasi & Channel",   "group": "Marketing",    "phase": "17"},
  {"route": "/campaigns",            "label": "Kampanye & Biaya Iklan","group": "Marketing",   "phase": "43"},
  {"route": "/attribution",          "label": "Atribusi & CAPI",      "group": "Marketing",    "phase": "43"},
  {"route": "/projects",             "label": "Master Proyek",        "group": "Proyek",       "phase": "39"},
  {"route": "/build",                "label": "Pembangunan",          "group": "Proyek",       "phase": "40c (lebur 4 menu)"},
  {"route": "/materials",            "label": "Material & Opname",    "group": "Proyek",       "phase": "18"},
  {"route": "/site-plan",            "label": "Site Plan",            "group": "Proyek",       "phase": "40c (hapus duplikat)"},
  {"route": "/boq",                  "label": "RAB / BoQ",            "group": "Pengadaan",    "phase": "12"},
  {"route": "/subcon",               "label": "Subkontraktor & SPK",  "group": "Pengadaan",    "phase": "12"},
  {"route": "/procurement",          "label": "Pengadaan (PO)",       "group": "Pengadaan",    "phase": "12"},
  {"route": "/finance",              "label": "AR / AP / Komisi",     "group": "Keuangan",     "phase": "8"},
  {"route": "/petty-cash",           "label": "Kas Bon",              "group": "Keuangan",     "phase": "27"},
  {"route": "/cash-bank",            "label": "Kas & Bank",           "group": "Keuangan",     "phase": "82"},
  {"route": "/accounting",           "label": "Buku Besar & Jurnal",  "group": "Akuntansi",    "phase": "13"},
  {"route": "/accounting/reports",   "label": "Laporan Keuangan",     "group": "Akuntansi",    "phase": "25"},
  {"route": "/fixed-assets",         "label": "Aset Tetap",           "group": "Akuntansi",    "phase": "28"},
  {"route": "/corporate-financing",  "label": "Pembiayaan Korporat",  "group": "Akuntansi",    "phase": "29"},
  {"route": "/tax",                  "label": "Perpajakan",           "group": "Akuntansi",    "phase": "22"},
  {"route": "/complaints",           "label": "Komplain & CS",        "group": "Layanan",      "phase": "9"},
  {"route": "/documents",            "label": "Dokumen & Perizinan",  "group": "Dokumen",      "phase": "26 (tab Perizinan 40c)"},
  {"route": "/config",               "label": "Pusat Konfigurasi",    "group": "Konfigurasi",  "phase": "39"},
  {"route": "/bi",                   "label": "Analitik & BI",        "group": "Analitik & BI","phase": "44"},
  {"route": "/legal",                "label": "Legal & Privasi",      "group": "Konfigurasi",  "phase": "iter149 (halaman legal publik + tiket penghapusan data)"}
]
```

Pintu **Admin** (`/admin/*`, 5 item) sengaja TIDAK masuk anggaran: bukan menu kerja harian dan
hanya terlihat oleh peran admin. Item **“Segera Hadir”** juga tidak masuk ledger karena belum
punya rute (aturan §4); saat dibuka, barisnya WAJIB ditambahkan ke ledger di fase yang sama.

## 8. Catatan Fase 46 — konsolidasi tanpa pintu baru

Fase 46 menambah layar (Papan Unit per-unit, tab Pembangunan Unit 360, panel izin bertingkat)
**tanpa menambah satu pun pintu sidebar**: semuanya masuk ke hub `/build` (6 tab: Papan Unit,
Kalender, Lapangan, Mutu & Inspeksi, Analitik & Kalibrasi, Template Jadwal) dan ke tab pada
halaman objek (`/units/:id`, `/projects/:id`). Ledger §7 karena itu **tidak berubah** — dan
gate `verify_build_hub.py` memaksa hal itu: setiap `path` di `navigationConfig.js` harus sudah
terdaftar di ledger, sehingga "menu baru diam-diam" akan memerahkan gate.

Perizinan tetap bisa dicari global lewat pintu **Dokumen & Perizinan** (`/documents`, tab
Perizinan); yang dihapus hanyalah gagasan menu Perizinan tersendiri (CR-25).
