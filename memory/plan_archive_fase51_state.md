# Rencana Development SIPRO — Fase 51 (51A/51B/51C): status & sisa pekerjaan

> Rencana lengkap Fase 51 beserta latar belakangnya diarsipkan di
> `memory/plan_archive_fase51.md`. Berkas ini menyimpan **keadaan sekarang** dan apa yang
> masih harus dikerjakan, supaya sesi berikutnya tidak menebak.

---

## 0) Keadaan lingkungan (sesi lanjutan dari repo GitHub `dmskhdhd/sipro`)

Repo di-clone ke container baru; `/app` semula template kosong dan database kosong.
Pemulihan yang **wajib diulang** setiap clone (rinci di `CODEBASE_MAP.md` §FASE 51):

1. `backend/.env`: `JWT_SECRET` (acak), `DEFAULT_ORG_ID="org-sipro"` (tanda hubung),
   `DEFAULT_ORG_NAME`, `PORTAL_MASTER_OTP="000000"` — selain `MONGO_URL`/`DB_NAME` container.
2. Paket yang belum ada di image: **`reportlab==5.0.0`**, **`APScheduler==3.11.3`**
   (jangan `pip install -r requirements.txt` mentah: `emergentintegrations` vs wheel
   `litellm` bentrok).
3. `yarn install` di `frontend/`, lalu `supervisorctl restart backend frontend`; seed penuh
   Fase 16..51 jalan sendiri saat DB kosong (±12 detik).
4. `WHATSAPP_TOKEN`/`WHATSAPP_PHONE_ID` **dibiarkan kosong** (keputusan owner): pengingat
   berjalan dalam mode **simulasi**, tidak ada pesan nyata terkirim ke pelanggan.

---

## 1) SUDAH SELESAI & TERBUKTI

| Pekerjaan | Bukti |
|---|---|
| POC inti Fase 51 (retensi↔garansi, dedup pengingat, portal) | `python3 poc/poc_51.py` → **PASS (67 pemeriksaan)**, bahan uji dibuang bersih |
| Backend + UI 51A (retensi ditahan klaim garansi, pengabaian beralasan) | gate 41 `verify_retention_warranty.py` → **40 pemeriksaan HIJAU** |
| Backend + UI 51B (pengingat WA: kandidat, ambang, dedup, kejujuran status) | gate 42 `verify_wa_reminders.py` → **54 pemeriksaan HIJAU** |
| Backend + UI 51C (portal: BAST, kwitansi, pengakuan klaim) | gate 43 `verify_portal_warranty.py` → **46 pemeriksaan HIJAU** |
| **Registrasi gate 41–43** ke `scripts/run_all_gates.sh` | `bash scripts/run_all_gates.sh` → **OVERALL PASS (43 gates)** |
| **Uji-mutasi Fase 51** `scripts/mutasi_51.py` (52 mutasi: 51 kode + 1 database) | `python3 scripts/mutasi_51.py --ringkas` → **52 TERTANGKAP · 0 LOLOS** |
| Spec: `docs/v2/46_RETENTION_WARRANTY_SPEC.md`, `47_WA_REMINDER_SPEC.md`, `48_PORTAL_BUYER_SPEC.md` | ditulis + didaftarkan di `docs/v2/20_INDEX_V2.md` §7 |
| Peta kode: bagian **FASE 51** di `CODEBASE_MAP.md` | berisi pemulihan lingkungan, inventaris file, guardrail, cacat yang diperbaiki |

### Dua cacat PERANGKAT UJI yang ditemukan uji-mutasi (dan sudah diperbaiki)
1. `W8a` gate 42 hanya menguji tagihan yang **seluruhnya** lunas, sehingga penyaring
   per-TERMIN tidak pernah teruji → tanpa penyaring itu DP yang sudah dibayar penuh lahir
   sebagai kandidat **tunggakan Rp 0**. Ditambah pemeriksaan **`W2f`**.
2. `C10a` gate 43 memeriksa kata `"DocumentsPanel"` yang sudah dipenuhi **baris impor**,
   sehingga panel bisa dilepas dari daftar tab tanpa gate menyadarinya. Sekarang memeriksa
   `Comp: DocumentsPanel` (benar-benar dirender).

### Perbaikan perangkat uji lain
* `mutasi_51.py` menunggu reload backend secara **deterministik** (PID proses ANAK `uvicorn`
  berganti → `/api/health` hidup), bukan `time.sleep(6)` buta seperti `mutasi_50.py`.
* Hasil tiap mutasi ditulis **segera** ke `memory/gatelogs/mutasi_51_hasil.tsv`
  (`--ringkas` menyusun laporan) + `memory/mutasi51_snapshot/` + `--pulihkan`, karena run
  panjang pernah dibunuh lingkungan di tengah jalan.

---

## 2) SISA PEKERJAAN (urutan kerja berikutnya)

### Phase 4 — Verifikasi E2E UI (utang dari fase sebelumnya, BELUM tertutup)
Semua tugas frontend di `test_result.md` masih `needs_retesting: true`. Yang harus diuji
multi-peran lewat `testing_agent_v3` (JANGAN uji kamera/GPS/drag-drop/suara):

1. **51A `/subcon?tab=retentions`** — kartu merah "ditahan klaim garansi" menyebut NOMOR
   klaim; tautan ke papan garansi; tombol "Abaikan penahanan…" hanya untuk `finlead`
   (`finance`/`pm` melihat kalimat penjelas, bukan `[object Object]`); alasan <10 huruf
   ditolak; sesudah diabaikan muncul blok violet "Penahanan yang diabaikan".
2. **51B `/automation?tab=reminders`** — banner mode **simulasi** apa adanya; kartu ambang +
   tautan Pusat Konfigurasi; "Jalankan sekarang" hanya peran ber-`manage` (`sales`/`pm`
   melihat kalimat, bukan tombol mati); kandidat tertahan menyebut sebabnya; riwayat
   menampilkan isi pesan; tab bertahan saat muat ulang (`?tab=`).
3. **51C `/portal`** (OTP master `000000`, pembeli demo B-01 Ibu Dewi Kartika) — tab Dokumen
   menampilkan BAST + kwitansi dan PDF-nya terbuka; tab Garansi menampilkan sisa masa per
   bagian; klaim `diverifikasi` punya tombol pengakuan; **"Belum beres" TIDAK menutup klaim**.
4. **Utang lama BUG-5/6/7 + REGRESI-1/2** — kartu atribusi lead tanpa mitra jujur; tab
   "Dokumen Onboarding" mitra bukan teks "dijadwalkan Fase …"; `sales` di area fee mitra
   melihat kalimat manusiawi; semua tab profil pelanggan terbuka; tidak ada
   `[object Object]`/`undefined`/`NaN`/enum Inggris mentah.

testId login: `login-email-input`, `login-password-input`, `login-submit-button`.
Sandi semua akun demo: `Sipro#2026`. Ganti peran lewat `profile-menu` → `logout-button`.

### Phase 5 — Sesudah UI hijau (belum dimulai, tunggu arahan owner)
* Perbaiki temuan UI (bila ada) lalu tutup Fase 51 di `test_result.md`.
* Kandidat fase berikutnya (dari backlog `docs/v2/34_ROADMAP_EKSEKUSI.md` + `⚠️ OPEN`
  `20_INDEX_V2.md` §6): jawaban OQ-1..OQ-11 milik owner, e-sign nyata (`ESIGN_*`), dan
  kredensial WhatsApp Cloud API bila pengingat mau keluar dari mode simulasi.

---

## 3) Cara membuktikan cepat (satu blok perintah)

```bash
python3 poc/poc_51.py                      # 67 pemeriksaan
python3 scripts/verify_retention_warranty.py   # gate 41 — 40
python3 scripts/verify_wa_reminders.py         # gate 42 — 54
python3 scripts/verify_portal_warranty.py      # gate 43 — 46
python3 scripts/mutasi_51.py --check           # 52 pola mutasi masih ada
python3 scripts/mutasi_51.py --ringkas         # 52 TERTANGKAP · 0 LOLOS
bash scripts/run_all_gates.sh                  # OVERALL PASS (43 gates)
```

## 4) Success Criteria Fase 51 — keadaan sekarang

| Kriteria | Status |
|---|---|
| Retensi ditahan bila ada klaim garansi aktif; pengabaian beralasan + SoD | ✅ terbukti gate 41 + M01–M22 |
| Pengingat WA dedup/idempoten; mode simulasi jujur; riwayat bisa dibaca | ✅ terbukti gate 42 + M23–M39, M52 |
| Portal: garansi/klaim/unduhan berjalan, tanpa tautan mentah, kosong-jujur | ✅ terbukti gate 43 + M40–M51 |
| `bash scripts/run_all_gates.sh` → OVERALL PASS (43 gates) | ✅ |
| `mutasi_51.py` semua mutasi TERTANGGAP & baseline hijau kembali | ✅ 52/52 |
| **Verifikasi E2E UI multi-peran (51A/51B/51C + BUG-5/6/7 + REGRESI-1/2)** | ⏳ **BELUM** — pekerjaan berikutnya |
