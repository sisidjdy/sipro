# 21 — AUDIT KONDISI SAAT INI (grounded, per modul)

> Semua temuan di bawah **dibuktikan dari kode**, bukan dugaan. Format: `CR-xx | severity | bukti | dampak bisnis`.
> Severity: **S1** = cacat logic/uang/legal, **S2** = fitur inti tidak memenuhi kebutuhan, **S3** = UX/IA, **S4** = kosmetik.
> Referensi lanjut: perbaikan tiap temuan ada di dokumen spec (kolom "Diperbaiki di").

## 1. Ringkasan skor per domain

| Domain | Kondisi | Catatan singkat |
|---|---|---|
| Lead capture (webhook, dead-letter) | ✅ ADA | `routers/webhooks_router.py`, `capture_failures.py` (retry/discard beralasan) |
| Atribusi iklan (source/campaign/adset/ad/creative) | ✅ ADA | `routers/omnichannel_router.py:239` funnel atribusi |
| CAPI feedback ke Meta/Google/TikTok | 🎭 SIMULASI | `capi.py:31-36` live hanya bila `META_CAPI_TOKEN`/`GOOGLE_ADS_CONV_TOKEN` ada |
| Biaya iklan (spend) → CPL/CAC/ROAS | ❌ BELUM | tidak ada koleksi `ad_spend`; `omnichannel_router.py:242` menyatakan sendiri "CPL/spend omitted" |
| Lead lifecycle sebagai gerbang bukti | ✅ ADA | `lead_lifecycle.py` (won tidak manual, `stage_history` lengkap) |
| Timestamp & aging per tahap di UI | 🟡 SEBAGIAN | data ada (`stage_changed_at`, `stage_history`) tapi UI tidak menampilkan |
| Halaman profil lead | ❌ BELUM | hanya panel samping `components/sales/LeadDetail.js` |
| Tabel lead profesional (sort/filter/eliminasi) | 🟡 SEBAGIAN | `pages/LeadsPage.js` 138 baris: chip stage + 1 search saja |
| Reservasi/SPR | 🐞 CACAT S1 | 1 lead bisa mengunci banyak unit (lihat CR-01) |
| Mitra/pihak ketiga (broker/agen) | 🟡 SEBAGIAN | master `agents` + fee + jurnal ADA (`marketing_fee.py`), tapi tidak terhubung ke lead & tanpa skema rate |
| BI/SLIK checking | ✅ ADA (manual, jujur) | `slik.py` wajib lampiran iDeb, mode `simulation` |
| Customer & KPR vs Deal & Unit | 🟡 SEBAGIAN | dua menu terpisah untuk satu alur (CR-18) |
| Generator dokumen legal (SPR/SPKT) | ❌ BELUM | `documents_router.py` generik, tidak ada template SPR/SPKT owner |
| Proyek → Cluster → Blok → Unit | ❌ BELUM | tidak ada entitas cluster/blok; "blok" = hasil `code.split("-")` |
| Konstruksi (progres/kalender/kalibrasi/mandor/diary) | 🟡 SEBAGIAN | fitur kuat tapi terpecah 6 menu (CR-24) |
| Analytics & BI | ❌ BELUM | hanya `/api/finance/reports/revenue` + funnel + rapor divisi |
| Target proyek & budget operasional | ❌ BELUM | kata "target" tidak ada sebagai konsep bisnis di backend |
| Realisasi RAB vs pendapatan (overbudget) | ❌ BELUM | `boq_items` ada, tetapi tidak dibandingkan ke realisasi & revenue |
| Pusat konfigurasi | 🟡 SEBAGIAN | `/admin/master-data` hanya SSOT + integritas; tidak ada registry setting bisnis |

## 2. TEMUAN KRITIS (S1) — cacat logic / uang / legal

### CR-01 · S1 · Satu lead bisa mengunci banyak unit (cacat yang owner laporkan)
- **Bukti:** `backend/routers/deals_router.py:78-123` (`POST /api/deals/reserve`). Ada *atomic hold* pada unit (`:94-99`) sehingga 2 orang tidak bisa merebut 1 unit — **tetapi tidak ada pemeriksaan "lead ini sudah punya reservasi aktif"**. Setiap panggilan membuat `deal` baru + mengunci unit baru.
- **Akibat:** stok unit "available" habis semu; laporan absorpsi & funnel bohong; unit mati terkunci sampai `reservation_expiry_sweeper` (`engine.py`) jalan.
- **Diperbaiki di:** [24](24_CRM_LEAD_SPEC.md) §5 (aturan + `[CFG] max_active_reservation_per_lead=1`).

### CR-02 · S1 · SPR hanya 1 klik, tanpa syarat dokumen & tanpa dokumen fisik
- **Bukti:** `deals_router.py:78` hanya butuh `unit_id`, `lead_id`, `booking_fee` (`models.py` `DealReserve`). Tidak ada validasi kelengkapan dokumen, tidak ada SPR yang diterbitkan.
- **Akibat:** "reservasi" tidak setara SPR nyata milik owner (`docs/source_templates/SPR_*.docx`) yang memuat harga, biaya-biaya, klausa hangus, tanda tangan.
- **Diperbaiki di:** [24](24_CRM_LEAD_SPEC.md) §6 + [27](27_DOCGEN_SPEC.md).

### CR-03 · S1 · Booking fee tidak punya siklus verifikasi/hangus/refund
- **Bukti:** `deals_router.py:103` menyimpan `booking_fee` sebagai angka pada deal; tugas konfirmasi dibuat (`:114` jobdesk `SM-05`), tetapi tidak ada status `unverified/verified/forfeited/refunded`, tidak ada aturan 7 hari, 100%/50%/hangus seperti `[DOC] SPR-KPR`.
- **Akibat:** uang masuk tidak berbukti; klausa legal tidak dijalankan sistem.
- **Diperbaiki di:** [26](26_CUSTOMER_LEGAL_SPEC.md) §6 + [27](27_DOCGEN_SPEC.md) §5.

### CR-04 · S1 · Tahap "won" memakai definisi yang bertentangan dengan keputusan owner (D4)
- **Bukti:** `lead_lifecycle.py:82-85` — `won` hanya lahir bila deal `completed/sold` atau `legal_stage in (ajb,bast)`; `MANUAL_FLOW["booking"] = ["lost"]` (`:31`).
- **Akibat:** persis keluhan owner: setelah reservasi, lead **mandek di `booking`** sampai AJB (bisa berbulan-bulan), padahal owner ingin lead **berubah jadi Customer** lebih awal dan AJB/BAST diurus di domain Customer.
- **Diperbaiki di:** [24](24_CRM_LEAD_SPEC.md) §3 (tambah tahap `spr`, `won` = konversi customer, `[CFG] won_trigger`).

### CR-05 · S1 · Tidak ada entitas Cluster & Blok → wiring siteplan/unit/customer rapuh
- **Bukti:** `seed_phase25.py:56` `"block": code.split("-")[0]` (blok = tebakan dari kode unit); `models.py:244` `UnitGenerate(prefix, type, price, count)`; tidak ada koleksi `clusters`/`blocks` (84 koleksi terdaftar, tidak ada keduanya).
- **Akibat:** tidak bisa: harga per cluster, target per cluster, siteplan per blok, penomoran unit resmi, laporan per cluster. Semua analitik proyek jadi kasar.
- **Diperbaiki di:** [28](28_PROJECT_UNIT_SPEC.md).

### CR-06 · S1 · Biaya-biaya transaksi (BPHTB, notaris, bank, hook, kelebihan tanah, promo) tidak ada di data model
- **Bukti:** `models.py` tidak punya field tersebut; `units` hanya `price`; SPR owner memuat 8 komponen biaya + promo + hook.
- **Akibat:** total yang ditagih ke pembeli tidak bisa dihitung sistem → SPR manual → AR & pajak tidak sinkron.
- **Diperbaiki di:** [26](26_CUSTOMER_LEGAL_SPEC.md) §5 + [28](28_PROJECT_UNIT_SPEC.md) §4.

### CR-07 · S1 · Skema pembayaran (cash keras / cash bertahap / KPR) tidak jadi state machine
- **Bukti:** `reference.py` punya `payment_method` & `financing_status`, `payment_schemes` ada untuk cicilan generik, tetapi tidak ada rencana bayar per kontrak dengan aturan `[DOC]`: tanggal 7 jatuh tempo, tanggal 20 batas akhir, tunggak 2 bulan = batal, pelunasan 30+7 hari setelah progres 100%.
- **Akibat:** denda/pembatalan tidak otomatis; finance mengejar manual.
- **Diperbaiki di:** [26](26_CUSTOMER_LEGAL_SPEC.md) §3–§6.

### CR-08 · S1 · Sub-alur KPR bank tidak dimodelkan (berkas → SLIK bank → appraisal → SP3K → akad)
- **Bukti:** `financing_apps` + `routers/financing_router.py` menyimpan status ringkas (`ref.financing_status`), tanpa tahapan bank yang owner sebutkan.
- **Akibat:** tidak bisa tahu lead KPR tersangkut di tahap mana; tidak ada SLA per tahap bank.
- **Diperbaiki di:** [26](26_CUSTOMER_LEGAL_SPEC.md) §4.

### CR-09 · S1 · Lead dari pihak ketiga tidak bisa dilacak → fee mitra tidak bisa dihitung otomatis
- **Bukti:** `reference.py:77-85` `lead_source` tidak punya nilai partner/broker/agen; `models.py:84` `LeadCreate` tidak punya `partner_id`; `marketing_fees` dibuat manual per deal (`marketing_fee.py:91`).
- **Akibat:** fee mitra rawan salah/curang; CAC per kanal mitra tidak bisa dihitung.
- **Diperbaiki di:** [25](25_PARTNER_SPEC.md).

## 3. TEMUAN FITUR INTI (S2)

| Kode | Temuan | Bukti | Diperbaiki di |
|---|---|---|---|
| CR-10 | Tidak ada halaman **Profil Lead** (semua riwayat, dokumen, unit, pembayaran, komunikasi dalam satu halaman) | hanya drawer `components/sales/LeadDetail.js`; route `/leads/:id` tidak ada di `frontend/src/App.js` | [24](24_CRM_LEAD_SPEC.md) §8, [23](23_IA_UX_BLUEPRINT.md) §4 |
| CR-11 | **Dokumen per tahap lead** tidak ada masternya | `files_router.py` upload generik; `documents` = dokumen legal terformat; tidak ada `doc_requirements` | [24](24_CRM_LEAD_SPEC.md) §6 |
| CR-12 | **Demografi lead** tidak direkam | `LeadCreate` hanya nama/telepon/email/sumber/kampanye/tipe minat | [24](24_CRM_LEAD_SPEC.md) §9, ⚠️ OQ-6 |
| CR-13 | **Analitik per user & laporan harian** tidak ada | ada rapor mingguan divisi (`workhub_report.py`), tidak ada aktivitas harian per user lintas modul | [31](31_ANALYTICS_BI_SPEC.md) §6 |
| CR-14 | **Conversion/churn per tahap, velocity, CAC** tidak ada | `omnichannel_router.py:239` hanya leads→booked per sumber | [31](31_ANALYTICS_BI_SPEC.md) §4 |
| CR-15 | **Rumah terjual sejak proyek mulai** tidak ada endpoint | `/api/site-plan/{project}` punya `absorption_pct` sesaat, bukan kumulatif berseri waktu | [31](31_ANALYTICS_BI_SPEC.md) §5 |
| CR-16 | **Realisasi RAB vs pendapatan / overbudget** tidak ada | `boq_router.py` `/summary` & `/control` hanya sisi anggaran | [32](32_TARGET_BUDGET_SPEC.md) §4 |
| CR-17 | **Target proyek dinamis + budget operasional** tidak ada | tidak ada koleksi/endpoint target | [32](32_TARGET_BUDGET_SPEC.md) §2–§3 |
| CR-18 | Alur satu bisnis dipecah 2 menu: **Deal & Unit** vs **Customer & KPR** | `frontend/src/config/navigationConfig.js` (PAGE_META `/deals`, `/customers`) | [23](23_IA_UX_BLUEPRINT.md) §3, [26](26_CUSTOMER_LEGAL_SPEC.md) |
| CR-19 | **Agenda & Survey**: kalender kecil, tanpa view minggu/hari, tanpa filter/sort, tanpa daftar tunggu survey yang jelas | `pages/AppointmentsPage.js` (142 baris) | [24](24_CRM_LEAD_SPEC.md) §10 |
| CR-20 | **Reschedule/pembatalan survey** tanpa master alasan & tanpa tindak lanjut WA | `leads_router.py:289` hanya set `status` | [24](24_CRM_LEAD_SPEC.md) §10 |
| CR-21 | **Form survey tidak bisa dikonfigurasi** | `routers/survey_router.py:134` hasil survei terstruktur tetap (hard-coded) | [24](24_CRM_LEAD_SPEC.md) §10, [33](33_CONFIG_CENTER_SPEC.md) |
| CR-22 | **Inbox WA tidak skalabel** (bayangkan 1000 lead) | `pages/InboxPage.js` (225 baris), tanpa virtualisasi/filter tahap/urgensi | [23](23_IA_UX_BLUEPRINT.md) §6 |
| CR-23 | **Site Plan** menempel di seksi Penjualan padahal lintas domain | `navigationConfig.js` `/site-plan` kicker "Penjualan" | [23](23_IA_UX_BLUEPRINT.md) §3 |
| CR-24 | **Domain konstruksi terpecah 6 menu** (Progres & Mutu, Kalender, Kalibrasi, Material, Perizinan, Buku Harian) | `navigationConfig.js` PAGE_META | [29](29_CONSTRUCTION_SPEC.md) |
| CR-25 | **Perizinan & dokumen** dibuat menu sendiri padahal atribut unit/customer | `routers/permits_router.py` (permit per proyek/unit) | [29](29_CONSTRUCTION_SPEC.md) §5 |
| CR-26 | **Pembayaran/gateway** belum disiapkan wiring-nya | `finance` AR ada, tidak ada channel bayar/VA/rekonsiliasi | [26](26_CUSTOMER_LEGAL_SPEC.md) §7 |

## 4. TEMUAN UX/IA (S3)

| Kode | Temuan | Bukti |
|---|---|---|
| CR-27 | Kartu (cards) dipakai untuk data transaksional yang seharusnya tabel | `pages/DealsPage.js` (190), `pages/ConstructionPage.js` (186) |
| CR-28 | Tipografi rata (semua font sama) → hierarki informasi hilang | `App.css` + halaman terkait |
| CR-29 | Detail selalu memakai drawer samping walau isinya panjang | `components/*/*DetailSheet.js`, `UnitDetailDrawer.js` |
| CR-30 | Tidak ada pola standar tabel (sort, filter multi, kolom pilihan, ekspor, aksi massal) | tidak ada komponen `DataTable` di `components/patterns/` |
| CR-31 | Tidak ada indikator urgensi/aging pada daftar kerja penjualan | `LeadsPage.js` hanya `fromNow(created_at)` |
| CR-32 | Menu "Template Jadwal"/"Kalibrasi" berdiri sendiri padahal fitur pembantu | `navigationConfig.js` `/build-calibration` |
| CR-33 | Info unit ditaruh di menu Penjualan ("Deal & Unit") | `navigationConfig.js` `/deals` |
| CR-34 | Tidak ada satu tempat konfigurasi (tersebar di admin/master-data & kode) | `pages/MasterDataPage.js` |

## 5. Yang HARUS DIPERTAHANKAN (jangan dirusak saat refactor)
Ini fondasi yang sudah terbukti lewat 19 gate — perubahan V2 **tidak boleh** menurunkannya:
1. **Gerbang bukti lifecycle** (`lead_lifecycle.py`) — `won` tidak boleh manual, `stage_history` wajib terisi.
2. **Atomic unit hold** (`deals_router.py:94`) — cegah dua pembeli satu unit.
3. **Idempoten jurnal GL** via `source_event` (`gl_engine.py`, `marketing_fee.py`) — invarian saldo akun.
4. **SLIK wajib bukti** (`slik.py:139`) — hasil yang meloloskan wajib lampiran nyata.
5. **Dead-letter lead capture** (`capture_failures.py`) — payload iklan cacat tidak pernah dibuang.
6. **SSOT enum** (`reference.py`, 85 grup) + migrasi kanonikalisasi (`migrations.py`).
7. **Index unik natural key** (`indexes.py`) + `sequences.py` untuk penomoran dokumen.
8. **Compliance guard**: `router.py<=800`, `page/komponen.js<=500`, `util/service.js<=300`, `css<=400` (`scripts/validate_compliance.py:19-22`).
9. **19 gate** `bash scripts/run_all_gates.sh` harus tetap PASS setiap fase.
