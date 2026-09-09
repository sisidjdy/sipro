# 18 — AUDIT FORENSIK DATA & LOGIKA (SSOT, Duplikasi, Cacat Form)

> Dijalankan atas permintaan: *"telusuri semua collection database, apakah ada duplikasi dan SSOT yang
> menyebabkan conflict data, cek semua endpoint API dan semua master data, apakah ada cacat logic seperti
> form yang input value custom padahal seharusnya dropdown ambil dari field data table, atau data table yang
> inputnya sama sekali kosong."*
>
> Alat: `scripts/forensic_audit.py` (idempoten, read-only, bisa dijalankan ulang kapan pun).
> Ruang lingkup: 62 koleksi MongoDB, 250 route API, 27 halaman + 22 folder komponen frontend.

---

## RINGKASAN

| | Sebelum | Sesudah |
|---|---|---|
| Temuan CRITICAL | 2 | **0** |
| Temuan HIGH | 19 | **0** |
| Temuan MED | 53 | **0** (sisanya terverifikasi *by design* + terdokumentasi) |
| Field kopi (denormalisasi) basi di DB | 2 baris | **0** |
| Nilai enum di luar daftar kanonik | 10 nilai | **0** |
| Referensi menggantung (FK yatim) | 0 | **0** (dipantau terus) |
| Validator enum di backend | **0** | 44 field tervalidasi |
| Natural key tanpa unique index | 23 | **0** |
| Titik penomoran dokumen rawan duplikat | 9 | **0** |

Gate: `validate_compliance`, `health_check`, `verify_rbac`, `verify_api_contract`, `check_nav_map`,
`audit_endpoint_sweep`, `verify_data_integrity`, `ux_audit`, `forensic_audit` — **semua PASS**.

---

## A. TEMUAN FUNDAMENTAL & PERBAIKANNYA

### A1. Tidak ada satu pun validasi enum di backend (CRITICAL — akar masalah)
**Bukti:** `models.py` sebelumnya berisi **0** `Literal` / `Enum` / `validator`. Semua field seperti
`status`, `type`, `category`, `uom`, `stage`, `severity`, `priority`, `source`, `specialty`, `authority`
menerima string apa pun. Hanya 2 field yang dijaga manual di router (`accounts.type`, `leads.stage`).

**Akibat:** klien/API mana pun bisa menyimpan `uom: "karung-besar"`, `status: "asdf"` — data tidak bisa
difilter, diagregasi, atau dipercaya.

**Perbaikan:** `backend/reference.py` = registry SSOT berisi 32 grup nilai kanonik + label Indonesia,
dipasang sebagai tipe `Annotated` di 44 field `models.py`. Nilai salah ditolak 422 dengan pesan yang
menyebutkan pilihan yang sah; sinonim/ejaan lama dinormalkan otomatis (`kubik` → `m3`, `Struktur` → `struktur`).

### A2. Vocabulary tercecer & bertentangan (HIGH — SSOT conflict nyata)
**Bukti terverifikasi:**

| Konsep | Nilai yang ditemukan | Lokasi |
|---|---|---|
| Tahap lead | 5 nilai / 3 nilai / 5 nilai / 7 nilai | `LeadsPage.js` / `RulesPanel.js` / `BroadcastPanel.js` / `leads_router.py` |
| Kategori pekerjaan | `Struktur`,`Arsitektur`,`MEP`,`Persiapan`,`Finishing`,`umum` | `boq_items` |
| Kategori pekerjaan | `MEP`,`finishing` (huruf kecil campur) | `punch_items` |
| Kategori pekerjaan | `structural`,`mep`,`handover` (Inggris) | `inspection_templates` |
| Satuan | teks bebas | `boq_items`, `materials`, PO |
| Bidang subkon | `Struktur & Beton`, `MEP (Listrik & Plumbing)` (teks bebas) | `subcontractors` |
| Cuaca | `Cerah`, `Cerah berawan` (teks bebas) | `site_diaries` |
| Channel vs sumber lead | `meta_lead_ads` vs `meta_ads`; `tiktok_lead` vs `tiktok_ads` | `channel_accounts` vs `leads` |
| Tipe unit | `Tipe 45/90` (unit) vs `Tipe 45` (minat lead) | `units` vs `leads` |

**Perbaikan:** kanonikalisasi otomatis saat startup (`backend/migrations.py`) + frontend mengambil daftar
yang sama dari `GET /api/reference` (tidak ada lagi array hardcode). Peta `CHANNEL_TO_SOURCE` menyatukan
atribusi channel ↔ sumber lead.

### A3. Skor lead memihak Meta, merugikan Google & TikTok (HIGH — cacat logika)
**Bukti:** `engine.SCORE_SOURCE` hanya memuat 7 sumber; `google_lead` dan `tiktok_ads` tidak terdaftar
sehingga jatuh ke nilai default 10 — sama rendah dengan `import` manual, sementara `meta_ads` mendapat 25.
Lead iklan berbayar Google/TikTok otomatis dianggap paling dingin.

**Perbaikan:** `reference.SOURCE_SCORE` jadi SSOT dan memuat semua sumber (`google_lead` 25, `tiktok_ads` 22).

### A4. Nomor dokumen rawan duplikat & bocor antar tenant (HIGH)
**Bukti:** 9 titik memakai `count_documents(...) + 1` — `journal_entries`, `faktur_pajak`, `inspections`,
`spk`, `material_requisitions`, `purchase_orders`/`grns`, `documents`, `deals.ppjb/ajb`, `progress_claims`/`change_orders`.
Tiga di antaranya menghitung `org_id=ORG_ID` (org default), bukan org milik user.

**Akibat:** dua request bersamaan menghasilkan **nomor SPK/PO/JV/Faktur yang sama**; dokumen yang dibatalkan
membuat nomor terpakai dipakai ulang; tenant kedua mendapat nomor yang menabrak tenant pertama.

**Perbaikan:** `backend/sequences.py` — koleksi `counters` dengan `find_one_and_update($inc)` (atomik di
level MongoDB), per (org, scope, tahun). Migrasi mengisi counter dari nomor tertinggi yang sudah ada.

### A5. Denormalisasi tanpa sinkronisasi (HIGH — data basi nyata ditemukan)
**Bukti:** 48 pasangan field kopi (`project_name`, `unit_code`, `lead_name`, `subcontractor_name`,
`spk_number`, `po_number`, `phase_name`, `scheme_name`, `customer_name`) disimpan ulang di koleksi anak
tanpa mekanisme sinkronisasi. Data yang **sudah salah saat audit**:

```
commissions.81b3ef2c… unit_code='A-02'  padahal unit_id -> units.code='A-01'
commissions.d4fc686e… unit_code='A-03'  padahal unit_id -> units.code='A-01'
```
(2 dari 3 baris komisi menampilkan unit yang salah di UI.)

Selain itu `PUT /subcon/subcontractors/{id}`, `PUT /customers/{id}`, `PUT /leads/{id}` bisa mengubah nama
tanpa memperbarui salinannya di dokumen anak.

**Perbaikan:** `backend/denorm.py` — `cascade_master_change()` dipanggil di setiap endpoint update master,
`resync_all()` dijalankan saat startup, dan `audit_stale()` diekspos ke UI (panel Kesehatan Data).

### A6. Master data terkunci di script seed (CRITICAL — "tabel yang tidak bisa diinput")
**Bukti:** `document_templates` dan `inspection_templates` **tidak punya endpoint tulis sama sekali** — hanya
bisa dibuat oleh `seed.py`. Padahal keduanya dipakai modul Dokumen dan QC.

Master lain yang tidak bisa dikoreksi setelah dibuat: `projects` (tanpa PUT), `units` (hanya generate),
`materials`, `construction_phases` (hanya progres), `accounts` (CoA), `payment_schemes`, `commission_schemes`.

**Perbaikan (endpoint + UI):**

| Master | Endpoint baru | UI |
|---|---|---|
| `document_templates` | GET/POST/PUT/DELETE `/api/master/doc-templates` | Master Data → Template Dokumen |
| `inspection_templates` | GET/POST/PUT/DELETE `/api/master/qc-templates` | Master Data → Template QC |
| `projects` | PUT `/api/projects/{id}` (+cascade nama) | Detail proyek → Ubah Proyek |
| `units` | PUT/DELETE `/api/projects/{pid}/units/{uid}` | Kartu unit → Ubah / Hapus |
| `construction_phases` | PUT/DELETE `/api/construction/phases/{id}` | Detail proyek → ikon pensil di fase |
| `materials` | PUT `/api/materials/{id}` | Tabel material → Ubah |
| `accounts` (CoA) | PUT `/api/gl/accounts/{code}` | Bagan akun → ikon pensil |
| `payment_schemes` | PUT `/api/finance/config/payment-schemes/{id}` | Keuangan → Konfigurasi |
| `commission_schemes` | PUT `/api/finance/config/commission-schemes/{id}` | Keuangan → Konfigurasi |

Pengaman bisnis dipasang: harga unit `booked/sold` dikunci; tipe akun dikunci bila sudah ada jurnal;
fase dengan progres/inspeksi tidak bisa dihapus; unit dengan deal/inspeksi/punch/komplain tidak bisa dihapus;
isi termin/tier skema dikunci bila sudah dipakai transaksi; material dengan transaksi stok tidak bisa diarsipkan.

### A7. Form memakai input teks bebas untuk field enum/relasi (HIGH — sesuai dugaan pengguna)
| Form | Field | Sebelum | Sesudah |
|---|---|---|---|
| Tambah Item RAB | `uom`, `category` | teks bebas / daftar hardcode | dropdown dari `/api/reference` |
| Tambah Material | `uom` | teks bebas | dropdown |
| Tambah PO (per baris) | `uom` | teks bebas | dropdown |
| Tambah Subkontraktor | `specialty` | teks bebas | dropdown |
| Tambah Perizinan | `authority`, `type` | teks bebas / hardcode | dropdown (instansi dinamis + "Nilai baru…") |
| Generate Unit | `type` | teks bebas | dropdown tipe unit (dinamis) |
| Tambah Lead | `source`, `interest_unit_type` | hardcode 6 nilai / teks bebas | dropdown 9 sumber / tipe unit |
| Punch List | `category`, `severity` | hardcode campur | dropdown |
| Buku Harian | `weather` | teks bebas | dropdown |
| Tambah Akun CoA | `type` | hardcode | dropdown |
| Lead pipeline / Rules / Broadcast | tahap, skor, sumber | 3 daftar berbeda | satu sumber |
| Template WA | `category` | hardcode | dropdown |

Catatan: `cost_code` RAB **memang** input bebas — BoQ adalah master kode biaya; keunikannya dijaga
unique index per proyek.

### A8. Proteksi duplikat hanya di aplikasi (MED→ditutup)
**Bukti:** 23 natural key tanpa unique index (`spk_number`, `po_number`, `grn_number`, `claim_number`,
`co_number`, `req_number`, `entry_no`, `doc_number`, `inspection_number`, kode proyek/unit/material/template,
`leads.phone`, `customers.nik`, `portal_users.phone`, dst). `leads` bahkan tidak punya dedup nomor telepon
sama sekali → lead ganda dari WA/Meta/manual.

**Perbaikan:** `backend/indexes.py` (24 unique index, partial untuk field opsional) + dedup lead saat
create **dan** update dengan pesan 409 yang menyebut lead pemilik nomor + normalisasi E.164 di seluruh
koleksi bernomor telepon.

### A9. Jejak audit ditulis tapi tidak bisa dilihat (HIGH)
**Bukti:** `rbac.audit_log()` dipanggil di 9+ tempat (persetujuan PO, ubah user/hak akses, komplain) dan
resource `audit_logs` sudah ada di matriks RBAC — tetapi **tidak ada endpoint** dan tidak ada halaman.

**Perbaikan:** `GET /api/admin/audit-logs` (+filter objek/aksi) dan halaman **Admin → Jejak Audit**.
Semua endpoint master baru juga menulis jejak audit.

### A10. Pembayaran AP tercatat tapi tak bisa ditelusuri (MED)
**Bukti:** koleksi `payments_out` ditulis setiap pembayaran tagihan, tanpa endpoint baca.
**Perbaikan:** `GET /api/finance/ap/payments` + panel **Riwayat Pembayaran** di Keuangan → Utang (AP).

---

## B. YANG DIPERIKSA DAN TERNYATA SEHAT (agar tidak salah dituduh duplikat)

| Pasangan koleksi | Kesimpulan |
|---|---|
| `construction_logs` vs `site_diaries` | Berbeda: log perubahan progres/QC (bukti per aksi) vs buku harian lapangan harian |
| `faktur_pajak` vs `tax_records` | Berbeda: dokumen Faktur Pajak bernomor vs catatan kewajiban PPN/PPh/BPHTB |
| `revenue_recognitions` vs `contract_liabilities` | Berbeda: pendapatan diakui saat serah terima vs uang muka belum jadi pendapatan |
| `payments_out` vs `ap_invoices` | Berbeda: kas keluar per pembayaran vs header tagihan + retensi |
| `receipts` vs `ar_invoices` | Berbeda: penerimaan kas vs jadwal tagihan |
| `file_blobs` vs `files` | Berbeda: isi biner vs metadata & kepemilikan |

Koleksi turunan yang **memang** hanya ditulis engine (bukan form): `activities`, `events`, `journal_entries`,
`commissions`, `ar_invoices`, `contract_liabilities`, `conversion_events`, `lead_capture_events`,
`material_txns`, `notifications`, `counters`, `audit_logs`, `portal_otps`, `file_blobs`.
Integritas referensial seluruh koleksi: **tidak ada FK menggantung**.

---

## C. PEMANTAUAN BERKELANJUTAN

1. **UI:** Admin → *Master Data & Integritas* → tab **Kesehatan Data** menampilkan (a) nama/kode salinan basi,
   (b) nilai referensi di luar daftar kanonik, (c) referensi menggantung.
2. **API:** `GET /api/master/data-health`.
3. **CLI:** `python scripts/forensic_audit.py` (masuk daftar gate di `scripts/run_all_gates.sh`).
4. **Startup:** migrasi idempoten otomatis (kanonikalisasi enum, normalisasi telepon, backfill counter,
   resync denormalisasi) — aman dijalankan berulang.

## D. FILE BARU / BERUBAH

**Backend baru:** `reference.py` (registry SSOT), `sequences.py` (nomor atomik), `denorm.py` (cascade SSOT),
`migrations.py` (migrasi idempoten), `indexes.py` (unique index), `models_master.py`,
`routers/reference_router.py`, `routers/master_router.py`.

**Backend berubah:** `models.py` (44 field tervalidasi), `server.py` (router + migrasi), `seed.py`
(nilai kanonik + perbaikan `unit_code`), `engine.py`, `gl_engine.py`, `tax_engine.py`, `rbac.py`,
`routers/{leads,subcon,subcon_claims,procurement,materials,inspection,documents,deals,projects,gl,admin,customers,construction,finance_config,ap}_router.py`.

**Frontend baru:** `context/ReferenceContext.js`, `components/patterns/ReferenceSelect.js`,
`pages/MasterDataPage.js`, `pages/AuditLogsPage.js`, `components/master/{DocTemplatesPanel,QcTemplatesPanel,DataHealthPanel}.js`,
`components/projects/{EditProjectDialog,EditUnitDialog,EditPhaseDialog}.js`,
`components/materials/EditMaterialDialog.js`, `components/gl/EditAccountDialog.js`,
`components/finance/{RenameSchemeDialog,PaymentsHistoryPanel}.js`, `constants/testIds/master.js`.

**Frontend berubah:** 14 form/panel beralih ke registry SSOT, `App.js`, `config/navigationConfig.js`.
