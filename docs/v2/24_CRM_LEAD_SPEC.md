# 24 — SPEC CRM & LEAD LIFECYCLE V2

> Menggantikan `lead_lifecycle.py` versi Fase 29b pada bagian tahap & gerbang. Referensi: [21](21_AUDIT_KONDISI.md) CR-01…CR-12, [22](22_DOMAIN_DATA_WIRING.md), [27](27_DOCGEN_SPEC.md), [33](33_CONFIG_CENTER_SPEC.md).

## 1. Tujuan
1. Lead punya **rumah** (halaman profil) berisi seluruh riwayat, dokumen, dan uang.
2. Setiap tahap punya **bukti**, **aktor**, dan **umur** — sehingga bisa dinilai & dianalisis.
3. Lead dari **mitra** terlacak sejak masuk (untuk fee & CAC).
4. **Menutup cacat** reservasi/SPR (CR-01…CR-04).

## 2. Sumber lead (SSOT `lead_source` diperluas)
Nilai lama tetap (kompatibilitas): `walk_in, meta_ads, google_lead, tiktok_ads, whatsapp, website, referral, manual, import, showroom_public`.
**Nilai baru:** `partner` (pihak ketiga: aggregator/broker/agen), `event` (pameran/kanvasing), `inhouse_marketing` (marketing internal non-iklan).
Aturan: bila `source='partner'` maka `partner_id` **wajib** (validasi 400). `source_detail` menyimpan nama event/PIC.

## 3. Stage machine V2 (keputusan D4)

```
acquisition ──► nurturing ──► appointment ──► booking ──► spr ──► won ──►(konversi)──► CUSTOMER
     │              │              │            │          │
     └──────────────┴──────────────┴────────────┴──────────┴──► lost / recycle (wajib alasan SSOT)
```

| Tahap | Arti bisnis | Syarat bukti masuk tahap (gate) | Bisa manual? |
|---|---|---|---|
| `acquisition` | lead masuk, belum dihubungi | — | otomatis saat dibuat |
| `nurturing` | sudah dihubungi & dikualifikasi | `first_contact_at` terisi (WA/telepon/kunjungan) | ya |
| `appointment` | ada jadwal/hasil survei | ada `appointments` untuk lead ini | ya |
| `booking` | **unit dipegang (keep unit) + booking fee tercatat** | ada 1 reservasi aktif **dan** `booking_fee_status ∈ {recorded, verified}` | tidak — lahir dari reservasi |
| `spr` **(BARU)** | SPR diterbitkan & dokumen syarat lengkap | dokumen mandatory tahap `spr` **verified** + `spr_document_id` ada | tidak — lahir dari penerbitan SPR |
| `won` | **lead sah → dikonversi jadi Customer** | pemicu `[CFG] lead.won_trigger` (default `spr_signed`) | tidak — otomatis |
| `lost` | gagal, wajib alasan SSOT `lead_close_reason` | alasan | ya |
| `recycle` | didaur ulang (nanti dihubungi lagi) | alasan + `recycle_until` | ya |

**`[CFG] lead.won_trigger`** pilihan: `spr_signed` (default, sesuai D4) · `booking_fee_verified` · `ppjb_signed` · `ajb_signed` (perilaku lama).
**Efek `won`:** buat/tautkan `customers`, buat `contracts` (draft) + `payment_plans` sesuai skema, set `unit.sales_status='booked'`, tutup lifecycle lead (read-only kecuali data diri), lahirkan tugas administrasi (jobdesk baru, lihat §12). **AJB/BAST tidak lagi menyentuh lead** (D4).

**Migrasi semantik:** lead lama berstatus `won` (dari AJB) tetap `won`. Lead lama `booking` yang punya SPR/kontrak akan dinaikkan ke `spr`/`won` oleh migrasi beralasan (`source='migration'`), lihat [35](35_MIGRASI_DATA.md).

## 4. Timestamp, aging & SLA (CR-31)
Field: `created_at`, `first_contact_at`, `stage_entered_at`, `stage_durations{}`, `sla_due_at`, `last_activity_at`, `won_at`, `closed_at`.

| Metrik | Rumus | Tampil di |
|---|---|---|
| Umur total | `now - created_at` | kolom tabel, header profil |
| Umur tahap | `now - stage_entered_at` | kolom tabel, header profil |
| Speed-to-lead | `first_contact_at - created_at` (menit) | KPI marketing (sudah ada `response_time_minutes`) |
| Sisa SLA | `sla_due_at - now` | badge urgensi |

**SLA default per tahap** `[CFG] lead.sla_hours` (bisa diubah): `acquisition=0.25` (15 menit speed-to-lead), `nurturing=48`, `appointment=72`, `booking=168` (7 hari, selaras klausa `[DOC]`), `spr=168`.
Pelanggaran SLA ⇒ event `lead.sla_breached` ⇒ tugas eskalasi ke supervisor (pola `engine.py` `sla_breach_check`).

## 5. Reservasi / keep unit (MENUTUP CR-01)

**Aturan:**
1. `[CFG] reservation.max_active_per_lead` **default 1** (D2). Melebihi ⇒ **409** dengan pesan: *"Lead ini sudah memegang unit {kode}. Batalkan/lepas dulu, atau minta {role} melakukan override dengan alasan."*
2. Override diizinkan hanya untuk peran di `[CFG] reservation.override_roles` (default `sales_manager, super_admin`; ⚠️ OQ-8) dan **wajib** `reason` → tercatat di `deals.override` + `activities`.
3. `[CFG] reservation.hold_days` default **7** (nilai sekarang `BOOKING_HOLD_DAYS`, `db.py`). Kadaluwarsa ⇒ unit dilepas + lead turun tahap ke `appointment` dengan alasan otomatis + tugas follow-up.
4. `[CFG] reservation.require_booking_fee_before_spr` default **true**.
5. Unit hanya bisa dipegang bila `sales_status='available'` **dan** (bila `[CFG] reservation.block_unbuildable`) unit tidak diblokir (mis. belum ada izin).
6. Pelepasan manual (`release`) wajib alasan SSOT baru `reservation_release_reason`: `customer_cancel, upgrade_unit, downgrade_unit, financing_failed, doc_incomplete, duplicate, admin_error, expired`.

**Perubahan endpoint** (`routers/deals_router.py`):

| Endpoint | Perubahan |
|---|---|
| `POST /api/deals/reserve` | + cek reservasi aktif per lead (index partial unik, [22](22_DOMAIN_DATA_WIRING.md) §4) · + `override{reason}` opsional · + set `expires_at` · + `booking_fee_status='unverified'` |
| `POST /api/deals/{id}/booking-fee` **(baru)** | catat/verifikasi booking fee (nominal, tanggal, bukti transfer `file_id`, metode) → jurnal titipan pelanggan (akun `2-1450`, sudah ada di CoA) |
| `POST /api/deals/{id}/release` **(baru)** | lepas unit dengan alasan SSOT |
| `POST /api/deals/{id}/issue-spr` **(baru)** | validasi dokumen lengkap → generate SPR ([27](27_DOCGEN_SPEC.md)) → tahap lead `spr` |
| `POST /api/deals/{id}/spr/sign` **(baru)** | tanda tangan (unggah scan / e-sign) → pemicu `won` bila `[CFG]` |
| `POST /api/deals/{id}/cancel` | + alasan SSOT + aturan booking fee (hangus/refund, [26](26_CUSTOMER_LEGAL_SPEC.md) §6) |

## 6. Master dokumen syarat (D3, CR-11)

`doc_requirements` (bisa ditambah admin lewat [33](33_CONFIG_CENTER_SPEC.md)). Field: `code, label, group, applies_to[], mandatory, allowed_mime[], max_mb, expiry_days, needs_verification, order, active, note`.
`applies_to` memakai kunci konteks: `lead_stage:booking`, `lead_stage:spr`, `payment_scheme:kpr`, `payment_scheme:cash_staged`, `customer:legal`, `partner:onboarding`, `unit:permit`.

**Seed awal (bisa diubah/ditambah; tandai sebagai default, bukan aturan mati):**

| code | label | applies_to | mandatory |
|---|---|---|---|
| `ktp` | KTP pemesan | lead_stage:spr | ya |
| `ktp_spouse` | KTP pasangan | lead_stage:spr (bila menikah) | kondisional |
| `kk` | Kartu Keluarga | lead_stage:spr | ya |
| `npwp` | NPWP | lead_stage:spr | ya |
| `buku_nikah` | Buku nikah/akta | lead_stage:spr (bila menikah) | kondisional |
| `bukti_booking_fee` | Bukti transfer booking fee | lead_stage:booking | ya |
| `slik_ideb` | Hasil iDeb/BI checking | (terpisah, D7) | ya bila hasil meloloskan |
| `slip_gaji` | Slip gaji 3 bulan | payment_scheme:kpr | ya |
| `rek_koran` | Rekening koran 3 bulan | payment_scheme:kpr | ya |
| `sk_kerja` | SK kerja/keterangan usaha | payment_scheme:kpr | ya |
| `npwp_usaha` | NPWP/izin usaha (wirausaha) | payment_scheme:kpr | kondisional |
| `form_kpr` | Formulir aplikasi bank | payment_scheme:kpr | ya |

Status tiap dokumen: `pending → verified | rejected(alasan) | expired`. Verifikasi wajib mencatat aktor+waktu (W6). Denormalisasi `leads.doc_progress` untuk tampilan cepat.

**Endpoint**: `GET /api/doc-requirements?context=...`, `POST /api/doc-submissions`, `POST /api/doc-submissions/{id}/verify`, `POST /api/doc-submissions/{id}/reject`, `GET /api/doc-submissions?entity_type=&entity_id=`.

## 7. BI/SLIK checking (D7 — TERPISAH dari urutan)
- Tetap memakai `slik.py` (manual + wajib bukti, mode jujur `simulation`).
- **Bukan lagi syarat kaku tahap booking.** `[CFG] slik.gate` = `off | before_booking | before_spr` (**default `before_spr`**), karena praktik owner: BI checking sering **sebelum** booking, tapi yang tidak boleh adalah SPR/KPR jalan tanpa hasil.
- Panel BI/SLIK tampil di **Profil Lead** dan **Profil Customer**; hasil `rejected` ⇒ tugas SM-12 + saran tutup lead (sudah ada) + **aturan refund booking fee 100%** bila sudah bayar (`[DOC] SPR-KPR`).

## 8. Halaman Profil Lead (CR-10)
Route `/leads/:id`. Struktur tab: lihat [23](23_IA_UX_BLUEPRINT.md) §4.1.
**Endpoint agregat baru** (hemat round-trip): `GET /api/leads/{id}/profile` →
```json
{"lead":{...},"aging":{"total_hours":0,"stage_hours":0,"sla_due_at":null},
 "requirements":{...},"next_actions":[...],"documents":{"matrix":[...],"progress":{}},
 "timeline":[{"at":"","actor":"","kind":"stage|activity|message|task|doc|payment","title":"","body":"","evidence":[]}],
 "appointments":[...],"slik":{...},"reservation":{...},"partner":{...},"payments":[...]}
```
Semua item timeline **wajib** punya `actor` (owner: "harus tahu siapa yang handle").

## 9. Demografi & data kualifikasi (CR-12, ⚠️ OQ-6)
`leads.demography`: `birth_year|age_band, gender, marital_status, dependents, occupation, employer, income_band, domicile{province,city,district}, education, info_source, purpose(pakai/investasi), dp_ready_band, timeline_intent`.
Ditambah `budget_band` (SSOT baru: `<300jt, 300-500jt, 500jt-1M, >1M`) dan `interest{project_id, cluster_id, unit_type, unit_id}`.
Semua field bisa ditandai wajib/opsional lewat `[CFG] lead.required_demography[]` — supaya sales tidak diblokir saat lead baru masuk dari iklan, tetapi wajib lengkap sebelum tahap `spr`.

## 10. Agenda & Survey V2 (CR-19…CR-21)
**UI**: kalender besar (bulan/minggu/hari/agenda) + tabel di bawah ("menunggu survei", "hari ini", "perlu reschedule") dengan kolom: lead, PIC, unit/tipe minat, waktu, status, umur menunggu, sumber.
**Reschedule/batal**: endpoint `POST /api/appointments/{id}/reschedule` & `/cancel` — wajib `reason_code` dari SSOT baru:
- `appointment_reschedule_reason`: `customer_request, customer_no_show, weather, pic_conflict, unit_not_ready, document_incomplete, transport, other`
- `appointment_cancel_reason`: `customer_cancel, lost_interest, price_mismatch, financing_failed, duplicate, wrong_number, other`
Setiap kejadian → baris `appointment_events` + **tugas follow-up WA otomatis** (jobdesk baru `SM-1x`) + masuk analitik (alasan = data berharga, permintaan owner).
**Form survei bisa dikonfigurasi**: `survey_forms` berversi; jawaban disimpan `surveys.answers{}` + `form_version`; perubahan form tidak merusak data lama.

## 11. Eliminasi, duplikat & aksi massal (CR-30)
- **Eliminasi**: `POST /api/leads/bulk/close` `{ids[], reason_code, note}` → tahap `lost`, audit per lead.
- **Duplikat**: deteksi via nomor telepon ternormalisasi (sudah ada normalizer) → `POST /api/leads/{id}/merge` `{into_lead_id}` memindahkan aktivitas/dokumen/appointment, menandai `merged_into`.
- **Aksi massal lain**: assign PIC, ganti tahap (dengan gate), tambah tag, kirim template WA, ekspor.
- **Sampah**: lead spam/uji dari webhook tetap lewat dead-letter (`capture_failures.py`), tidak masuk pipeline.

## 12. Event & jobdesk baru (lanjutan `docs/analysis/19_EVENT_AND_JOBDESK_CATALOG.md`)

| Event | Pemicu | Jobdesk/tugas |
|---|---|---|
| `lead.sla_breached` | sisa SLA < 0 | eskalasi ke supervisor |
| `reservation.expiring` | H-1 `expires_at` | ingatkan sales |
| `reservation.expired` | lewat `expires_at` | lepas unit + follow-up |
| `bookingfee.unverified_aging` | >`[CFG]` jam belum diverifikasi finance | tugas finance |
| `spr.issued` | SPR terbit | tugas kelengkapan dokumen |
| `spr.signed` | SPR ditandatangani | konversi customer + tugas administrasi |
| `appointment.rescheduled` / `.cancelled` | aksi user | follow-up WA |
| `lead.doc_rejected` | verifikasi gagal | minta ulang ke customer |
| `partner.lead_received` | lead mitra masuk | notifikasi + validasi fee |

## 13. RBAC tambahan (lanjutan `docs/analysis/14_RBAC_MATRIX.md`)

| Aksi | sales | sales_manager | marketing_admin | finance | owner/super_admin |
|---|---|---|---|---|---|
| lihat lead sendiri | ✔ | ✔ semua | ✔ semua | – | ✔ |
| reservasi | ✔ | ✔ | – | – | ✔ |
| override batas reservasi | ✖ | ✔ | ✖ | ✖ | ✔ |
| verifikasi booking fee | ✖ | ✖ | ✖ | ✔ | ✔ |
| terbitkan SPR | ✔ | ✔ | ✖ | ✖ | ✔ |
| verifikasi dokumen | ✖ | ✔ | ✔ | ✔ (keuangan) | ✔ |
| eliminasi massal | ✖ | ✔ | ✔ | ✖ | ✔ |
| ubah master dokumen/konfigurasi | ✖ | ✖ | ✖ | ✖ | ✔ |

## 14. Definition of Done (fase CRM)
1. Tidak mungkin satu lead memegang 2 unit tanpa override beralasan — dibuktikan uji negatif + INV-01.
2. SPR hanya bisa terbit bila dokumen mandatory verified — uji negatif.
3. Profil lead menampilkan aktor pada **setiap** baris timeline.
4. Tabel lead punya search + ≥4 filter + sort + kolom umur total & umur tahap + ekspor + aksi massal.
5. Reschedule/batal survei tidak bisa tanpa alasan SSOT; alasan muncul di analitik.
6. `bash scripts/run_all_gates.sh` PASS + gate baru `verify_crm_v2.py` (uji-mutasi).
