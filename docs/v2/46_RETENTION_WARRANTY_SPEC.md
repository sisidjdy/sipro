# 46 — SPEC RETENSI SUBKON ↔ KLAIM GARANSI (Fase 51A)

> Dasar: pembacaan kode yang benar-benar berjalan (`backend/subcon_finance.py`,
> `backend/routers/subcon_finance_router.py`, `backend/models_p51.py`,
> `backend/reference_p51.py`, `frontend/src/components/subcon/`). Cakupan: (a) klaim garansi
> yang masih berjalan **menahan** pencairan retensi subkon, (b) pengabaian penahanan yang
> beralasan + berjejak + terbatas peran, (c) pemisahan tugas & idempotensi pencairan,
> (d) kejujuran layar (honest-null, label dari Kamus Data, penahanan yang diabaikan tetap
> terlihat).
>
> Status: **✅ ADA** — dibuktikan gate 41 `scripts/verify_retention_warranty.py`
> (40 pemeriksaan) dan uji-mutasi `scripts/mutasi_51.py` (M01–M22).

---

## 1. Yang SUDAH ADA sebelum Fase 51A (jangan dibangun ulang)

| Modul | Kemampuan sebelum 51A |
|---|---|
| `subcon_finance.py` (`create_retention`, `retention_gate`) | retensi lahir otomatis dari termin subkon yang disetujui; gerbang memeriksa **masa pemeliharaan** dan **temuan punch list** |
| `subcon_finance.py` (`request_release`, `release`) | pengajuan → pencairan dengan jurnal Dr 2‑1200 / Cr 2‑1100 + tagihan AP siap bayar |
| `warranty_engine.py`, `handover_engine.py` (Fase 50) | klaim garansi pasca-huni: `warranty_claims` + masa garansi per bagian dari BAST |
| `offline_intake.py` | penanda `client_ref` untuk kiriman ulang yang aman (Fase 45) |
| `rbac.py` (`subcon_finance`) | SoD: lapangan/PM `create`, finance `approve`, Manajer Keuangan `manage` |

## 2. Lubang yang ditutup Fase 51A

| Kode | Lubang (bukti) | Penutup |
|---|---|---|
| R‑H1 | `retention_gate` **tidak pernah melihat `warranty_claims`** — jalur keluhan pasca-huni baru lahir di Fase 50. Akibatnya retensi bisa cair **persis ketika** rumah sedang diperbaiki karena cacat pekerjaan subkon itu; satu-satunya alat tekan pengembang hilang tepat saat dibutuhkan | penahan baru `warranty_claim_active` di `retention_gate` (`_active_warranty_claims`) |
| R‑H2 | Penahanan lama hanya berbunyi "ada kendala" — pemakai tidak tahu apa yang harus dituntaskan | `detail` menyebut **nomor + judul klaim**, `warranty_claims[]` dikirim ke layar beserta `state_label` dari Kamus Data |
| R‑H3 | Tidak ada jalan sah bila risiko mutunya memang sudah ditanggung pihak lain (adendum) → aturan dilewati di luar sistem | pintu terpisah `POST /retentions/{id}/waive` + izin `subcon_finance:override` + alasan ≥10 huruf + jejak + tugas penelaahan |
| R‑H4 | Layar harus **menebak sendiri** penahanan mana yang boleh diabaikan (dua versi aturan untuk satu keputusan) | server mengirim `waivable` per penahanan (SSOT `WAIVABLE_BLOCKS`) |
| R‑H5 | Kiriman ulang pencairan (klik ganda/sinyal buruk) bisa melahirkan **tagihan AP kedua** | `client_ref` → `offline_intake.begin/commit/rollback`, jawaban `replay: true` |
| R‑H6 | Retensi tanpa catatan masa pemeliharaan ditulis "0 hari" — kebalikan artinya (0 hari = sudah lewat) | `maintenance_detail` honest-null: "belum dicatat … bukan nol hari" |

---

## 3. Aturan yang DIPAKSAKAN (bukan imbauan)

### 3.1 Gerbang pencairan (`GET /api/subcon/retentions` → `row.gate`)
Lima kode penahan, semuanya dari SSOT `retention_block` (`reference_p51.py`):

| Kode | Menahan bila | Boleh diabaikan? |
|---|---|---|
| `maintenance_active` | hari ini < `maintenance_until` | ✔ |
| `punch_open` | ada temuan `open`/`in_progress` di lingkup SPK | ✔ |
| `warranty_claim_active` | ada `warranty_claims` berstatus `diajukan`/`dikerjakan`/`selesai`/`diverifikasi` pada unit lingkup SPK | ✔ |
| `already_released` | retensi sudah cair | ✘ (dokumennya memang sudah cair) |
| `claim_not_approved` | termin sumber retensi belum `approved` | ✘ (angkanya belum sah) |

1. **Lingkup itu penting.** Klaim yang menahan hanya klaim pada unit yang benar-benar
   menjadi lingkup SPK (`spk_scope_items.unit_id`). Menahan uang subkon karena cacat
   pekerjaan orang lain sama tidak adilnya dengan membayar cacat yang belum diperbaiki.
   SPK borongan **tanpa** lingkup unit diperlakukan konservatif: seluruh klaim berjalan di
   proyek menahan, dan `warranty_scope` menuliskan kalimat sebabnya.
2. **Sebab menyebut isi, bukan jumlah.** `detail` memuat nomor + judul klaim (maksimal 3,
   sisanya "…") dan menutup dengan jalan keluar: tuntaskan klaimnya, atau abaikan penahanan
   dengan alasan tertulis.
3. `state_label` & `category_label` **wajib** dari Kamus Data (`warranty_claim_state`,
   `warranty_category`) — pembeli, staf, dan subkon tidak boleh membaca dua versi kata.
4. Setiap penahanan membawa `label` + `waivable` (SSOT). Layar tidak pernah menyusun daftar
   kode sendiri.
5. **Penahanan garansi hilang SENDIRI** begitu klaimnya `ditutup`/`ditolak` — tanpa perlu
   diabaikan. Pengabaian bukan syarat untuk keadaan yang sudah selesai.

### 3.2 Pengajuan pencairan (`POST /api/subcon/retentions/{id}/request-release`)
1. Izin `subcon_finance:create` (lapangan/PM). Manajer Keuangan **tidak** mengajukan.
2. Ditolak **400** bila gerbang tidak `ok`; badan jawaban memuat kalimat gerbang lengkap
   dengan nomor klaim penahannya.
3. Hanya retensi berstatus `held` yang bisa diajukan.

### 3.3 Pengabaian penahanan (`POST /api/subcon/retentions/{id}/waive`)
1. Izin **khusus** `subcon_finance:override` — hanya `finance_manager` (+ `owner`/`super_admin`
   lewat FULL_ACCESS). `finance` biasa dan PM mendapat **403**. Mencabut hak mengabaikan
   tidak mencabut hak mencairkan (`manage`), dan sebaliknya.
2. Alasan **≥10 huruf**, dijaga **dua lapis**: kontrak permintaan `models_p51.RetentionWaiveIn`
   dan mesin `subcon_finance.waive`. Satu lapis saja membuat mutan ekuivalen (lihat M08).
3. Hanya kode yang **memang boleh diabaikan** (`WAIVABLE_BLOCKS`) **dan memang sedang
   menahan** yang bisa diabaikan. Kode asing → 400; kode yang tidak menahan → 400 dengan
   kalimat "tidak sedang menahan retensi ini".
4. Jejak disimpan selamanya di `subcon_retentions.waivers[]` = `{code, reason, by, at}`.
5. Sesudah diabaikan, gerbang boleh `ok` **tetapi penahanannya tetap dikirim** di
   `waived_blocks[]` beserta siapa/kapan/kenapa — auditor tidak boleh kehilangan jejak.
6. Menghasilkan `audit_logs` `action="override"` **dan** tugas penelaahan
   (`workhub.spawn("FN-01", source_event="retention_waiver:{id}:{codes}")`) + aktivitas proyek.

### 3.4 Pencairan (`POST /api/subcon/retentions/{id}/release`)
1. Izin `subcon_finance:manage` (Manajer Keuangan).
2. **Pemisahan tugas**: `requested_by == actor` ditolak — pengaju tidak boleh mencairkan
   yang diajukannya sendiri.
3. Harus berstatus `release_requested` (pengajuan lapangan/PM lebih dulu).
4. Gerbang diperiksa **ulang** saat pencairan (bukan hanya saat pengajuan).
5. **Idempoten** lewat `client_ref`: kiriman ulang menjawab `replay: true` + `bill_id`/
   `journal_no` lama, **tanpa** tagihan AP kedua. Kiriman paralel dengan penanda sama → 409.
6. Tidak bisa dicairkan dua kali (400 "tidak bisa dicairkan dua kali").
7. Sukses menulis jurnal `2-1200` → `2-1100`, membuat `ap_invoices` `bill_kind="retention_release"`,
   mengisi `released_by/at`, `release_reason`, `release_bill_id`, `journal_no`, lalu mencatat
   audit + aktivitas proyek.

---

## 4. Peta endpoint ↔ layar

| Endpoint | Izin | Layar | testId (SSOT `constants/testIds/p51.js`) |
|---|---|---|---|
| `GET /api/subcon/retentions` | `subcon_finance:view` | `/subcon?tab=retentions` → `RetentionsPanel.js` | `retentionWarrantyHold`, `retentionWarrantyClaim`, `retentionWarrantyLink`, `retentionMaintenanceNote` |
| `POST …/request-release` | `create` | tombol "Ajukan pencairan" | (panel retensi Fase 48C) |
| `POST …/waive` | `override` | `RetentionWaiveDialog.js` | `retentionWaiveBtn`, `retentionWaiveDialog`, `retentionWaiveCode`, `retentionWaiveReason`, `retentionWaiveSubmit`, `retentionWaiveCancel`, `retentionWaiveHint` |
| `POST …/release` | `manage` | tombol "Cairkan" | (panel retensi Fase 48C) |
| — | — | blok jejak pengabaian | `retentionWaivedBlock` |

Aturan layar:
1. Kartu penahanan garansi **menyebut nomor klaim** dan menautkan ke papan garansi
   (`/construction?tab=warranty`) — bukan jalan buntu.
2. Peran tanpa `override` **tidak** melihat tombol; ia melihat kalimat penjelas
   (`retentionWaiveHint`), bukan tombol mati atau `[object Object]`.
3. Daftar penahanan yang boleh diabaikan dibaca dari `gate.blocks[].waivable`.
4. Blok violet "Penahanan yang diabaikan" menampilkan `waived_blocks[]` beserta alasan.

---

## 5. Data & index

`subcon_retentions` (tambahan Fase 51A):

| Field | Arti |
|---|---|
| `waivers[]` | `{code, reason, by, at}` — jejak pengabaian, tidak pernah dihapus |
| `gate` (turunan, tidak disimpan) | dihitung ulang tiap permintaan oleh `retention_gate` |

Tidak ada koleksi baru dan **tidak ada index baru** untuk 51A: penahanan dihitung dari
`warranty_claims` (`org_id`, `state`, `unit_id`/`project_id`) dan `spk_scope_items`
(`org_id`, `spk_id`) yang index-nya sudah ada sejak Fase 48/50.

---

## 6. Guardrail (cara membuktikan cepat)

```bash
python3 scripts/verify_retention_warranty.py     # gate 41 — 40 pemeriksaan
python3 scripts/mutasi_51.py --only=M01,M08,M14  # mutasi terpilih harus TERTANGKAP
bash scripts/run_all_gates.sh                    # 43 gate, OVERALL PASS
```

Gate 41 membuktikan R1–R13: penahanan menyebut klaimnya, pengajuan ditolak, izin & alasan
pengabaian, sasaran pengabaian yang sah, transparansi jejak, SoD, idempotensi, penahanan
yang hilang sendiri saat klaim ditutup, honest-null masa pemeliharaan, kamus SSOT, jejak
audit + tugas, dan **permukaan layar** (tidak ada testId 51A yang mati).

Uji-mutasi M01–M22 mematikan aturan-aturan di atas satu per satu; semuanya harus
**TERTANGKAP**. Mutasi yang LOLOS berarti gate-nya yang harus diperkuat, bukan diabaikan.

---

## 7. Yang SENGAJA tidak dikerjakan di 51A
1. **Retensi tidak otomatis dipotong** untuk membiayai perbaikan garansi. Memotong uang
   subkon butuh dasar kontrak (adendum/berita acara), jadi yang disediakan adalah
   penahanan + jejak keputusan — bukan potongan otomatis yang mengarang angka.
2. **Tidak ada penahanan parsial** (menahan sebagian nominal). Nilai retensi lahir dari
   termin; memecahnya tanpa dasar kontrak membuat pembukuan subkon tidak bisa ditutup.
3. Klaim berstatus `ditolak` **tidak** menahan: keputusan menolak sudah menyelesaikan
   urusannya, dan jejaknya tetap ada di papan garansi.
