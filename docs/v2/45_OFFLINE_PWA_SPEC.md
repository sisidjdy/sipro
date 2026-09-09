# 45 — SPEC ANTREAN PERANGKAT TERPADU (PWA OFFLINE) — Fase 50B

> Janji yang dijaga dokumen ini: **pekerjaan lapangan tidak HILANG dan tidak DOBEL.**
> Dasar: audit kode Fase 35 (antrean offline Papan Mandor) terhadap kenyataan pemakaian —
> tiga pekerjaan yang paling sering dikerjakan tanpa sinyal justru belum bisa mengantre.

---

## 1. Yang SUDAH ADA sebelum Fase 50B

| Modul | Kemampuan |
|---|---|
| `frontend/src/services/offlineSync.js` (Fase 35) | antrean di perangkat (IndexedDB) untuk **`build_submit` & `build_start`** + unggah foto tertunda |
| `frontend/src/utils/offlineDb.js` | penyimpanan pekerjaan & blob foto di perangkat |
| `components/construction/OfflineQueuePanel.js` | daftar antrean + tombol coba lagi (dulu hanya di tab Papan Mandor) |
| `build_engine` (`client_ref`) | **satu-satunya** endpoint yang mengenal penanda idempotensi |
| SSOT `offline_queue_kind`, `offline_queue_status` | label antrean (layar tidak menulis label sendiri) |

## 2. Lubang yang ditutup Fase 50B

| Kode | Lubang (bukti audit) | Penutup |
|---|---|---|
| Q1 | `POST /labor/attendance` tidak punya `client_ref` → tekan ulang = **absensi ganda = upah ganda**; tidak ditekan ulang = pekerjaan seharian hilang | `client_ref` + `offline_intake` pada absensi |
| Q2 | `POST /field/diary` sama: catatan harian bisa kembar | `client_ref` pada buku harian |
| Q3 | `POST /field/punchlist` sama: temuan **dan tugasnya** kembar | `client_ref` pada temuan punch |
| Q4 | `POST /field/punchlist/{id}/status` melampirkan bukti foto **dua kali** saat dikirim ulang | `client_ref` pada perubahan status |
| Q5 | Kiriman yang ditolak server mengunci penanda selamanya (kehilangan senyap) | `offline_intake.rollback` melepas kunci |
| Q6 | Keunikan penanda hanya dijaga aplikasi → dua tab lolos bersamaan | index unik DB `uq_offline_intake_ref` |
| Q7 | Antrean hanya berisi pekerjaan unit; jalur Fase 50A (klaim garansi & bukti perbaikan) dikerjakan di lokasi tapi tidak bisa mengantre | jenis baru `warranty_claim`, `warranty_fix`, `handover_issue` |

---

## 3. Kontrak idempotensi (`backend/offline_intake.py`)

Kunci = **(`org_id`, `kind`, `client_ref`)**. Empat aturan yang dipaksakan:

1. **Satu penanda = satu dokumen.** Kiriman kedua **tidak ditolak** melainkan diputar ulang
   (`replay: true` + dokumen lama). Pengirim ulang tidak bersalah: dia hanya tidak pernah
   menerima jawaban pertama.
2. **Kunci diambil SEBELUM data disentuh** (`begin()` menyisipkan baris penanda). Dua tab yang
   mengirim bersamaan tidak bisa sama-sama lolos pemeriksaan "sudah pernah diterima?" —
   yang kedua menerima `inflight` → **409**.
3. **Kunci BASI boleh diambil ulang** (`STALE_SECONDS = 120`): kalau proses mati di tengah
   jalan, antrean tidak boleh menganggap pekerjaan "sudah terkirim" padahal belum.
4. **Server MENOLAK → kunci DILEPAS** (`rollback()`), sehingga pemakai bisa memperbaiki lalu
   mengirim ulang dengan penanda yang sama.

Jenis yang dikenal (`KINDS` di `offline_intake.py`, label di SSOT `offline_queue_kind`):
`attendance_submit`, `field_diary`, `punch_create`, `punch_status`, `warranty_claim`,
`warranty_fix`, `handover_issue`.

Baris penanda (`offline_intake`) menyimpan **alamat** dokumen hasil (`collection` + `doc_id`),
bukan salinannya — supaya pemutaran ulang selalu mengembalikan keadaan TERKINI dokumen itu,
bukan potret basi. Absensi harian tidak punya satu dokumen induk (satu baris per orang), jadi
yang disimpan adalah baris pertama hari itu + `summary` (`present`, `wage_total`).

### Endpoint yang menerima `client_ref`

| Endpoint | Jenis (`kind`) | Koleksi hasil |
|---|---|---|
| `POST /api/labor/attendance` | `attendance_submit` | `labor_attendance` |
| `POST /api/field/diary` | `field_diary` | `site_diaries` |
| `POST /api/field/punchlist` | `punch_create` | `punch_items` |
| `POST /api/field/punchlist/{id}/status` | `punch_status` | `punch_items` |
| `POST /api/handover/claims` | `warranty_claim` | `warranty_claims` |
| `POST /api/handover/claims/{id}/complete` | `warranty_fix` | `warranty_claims` |
| `POST /api/handover/issue` | `handover_issue` | `unit_handovers` |
| `POST /api/build/items/{id}/submit` (Fase 35) | `build_submit` | `build_items` |

---

## 4. Sisi perangkat (`offlineSync.js`)

1. **Satu pintu**: `submitOrQueue({ kind, endpoint, payload, photos, title })` — kirim sekarang
   bila online, antre bila tidak. Foto yang masih tersimpan di perangkat (`local:…`) **memaksa**
   pekerjaan masuk antrean, karena bukti harus terunggah lebih dulu.
2. **Penanda dibuat di perangkat** (`newRef()`), dipakai juga saat online supaya percobaan
   ulang tetap idempoten. Bila jaringan mati **tanpa jawaban server**, pekerjaan disimpan
   dengan penanda yang SAMA → kiriman berikutnya jadi pemutaran ulang, bukan data kedua.
3. **Foto tidak terunggah dua kali**: setelah unggah berhasil, id lokal langsung ditukar id
   nyata di dalam pekerjaan antrean (`uploadPhotos`), lalu blob lokalnya dibuang.
4. **Antrean tidak berbohong**: jawaban 4xx → status `rejected` + alasan ASLI server; bukti
   fotonya TIDAK dihapus. Jawaban 5xx/tanpa jawaban → tetap `pending` untuk dicoba lagi.
5. **Label dari SSOT**: panel antrean membaca `offline_queue_kind`/`offline_queue_status` lewat
   `useReference()` — tidak ada dua versi label untuk hal yang sama.

### Di layar mana antrean terlihat

| Tempat | Isi |
|---|---|
| Spanduk `OfflineBanner` (di `AppShell`, **semua halaman**) | keadaan jaringan, jumlah menunggu/ditolak, tombol "Kirim sekarang", "Lihat antrean" |
| `/field` (Buku Harian & Punch) | `OfflineQueuePanel kinds={["field_diary","punch_create","punch_status"]}` |
| Papan Mandor (`ForemanBoard`) & tab Lapangan unit (`BuildFieldTab`) | seluruh antrean (termasuk absensi) |
| `/units/{id}` tab Serah Terima & Garansi | `OfflineQueuePanel kinds={["warranty_claim","warranty_fix"]}` |

Formulir yang sudah memakai satu pintu ini: absensi (`LaborAttendancePanel`), buku harian
(`AddDiaryDialog`), temuan punch (`AddPunchDialog`), status/bukti punch (`PunchDetailSheet`),
klaim garansi & bukti perbaikan (`WarrantyClaimDialogs`).

---

## 5. Guardrail (cara membuktikan cepat)

```
python3 scripts/verify_offline_queue.py     # GATE 40 — 14 pemeriksaan
python3 scripts/mutasi_50.py --check       # pola mutasi masih ada
python3 scripts/mutasi_50.py               # termasuk MUTASI DATABASE: index unik dijatuhkan
bash scripts/run_all_gates.sh              # 40 gates
```

Gate 40 menjaga: (Q1) absensi dikirim dua kali hanya tercatat sekali + jawaban `replay` jujur,
(Q2) buku harian tidak kembar, (Q3) temuan **dan tugasnya** tidak kembar, (Q4) bukti perbaikan
tidak terlampir dua kali, (Q5) kiriman yang ditolak melepas kunci sehingga bisa diperbaiki,
(Q6) penanda tercatat + **index unik** + database benar-benar menolak penanda kembar,
(Q7) jenis antrean baru terdaftar di kamus data, (Q8) jalur Fase 50A (BAST, klaim, bukti
perbaikan) aman diputar ulang.

Mutasi `M37` sengaja **menjatuhkan index unik** `uq_offline_intake_ref` lalu membangunnya
kembali: tanpa mutasi ini, janji "keunikan dijaga database, bukan hanya aplikasi" tidak pernah
teruji — padahal itulah satu-satunya lapis yang masih berlaku saat dua tab mengirim absensi
pada saat yang sama.

---

## 6. Batas yang JUJUR (jangan dijanjikan di layar)

* Antrean hidup **per perangkat & per browser** (IndexedDB). Berganti perangkat tidak
  memindahkan antrean; pekerjaan yang belum terkirim tetap di perangkat lama.
* Belum ada Background Sync API: pengiriman berjalan saat aplikasi dibuka/online kembali
  (`OfflineContext` mendengarkan `online` + tombol "Kirim sekarang").
* Kamera/GPS tidak diuji otomatis (uji E2E agen tidak punya perangkat) — foto pada gate & POC
  diunggah sebagai PNG nyata lewat `POST /files/upload`.
* Penanda antrean bukan pengganti izin: endpoint tetap memeriksa RBAC dan aturan bisnis
  (mis. tanggal absensi yang sudah masuk rekap upah tetap terkunci).
