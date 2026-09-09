# Rencana Development SIPRO — Lanjutkan Development Repo (Utang Verifikasi UI + Fase 51A/51B/51C)

## 1) Objectives
1. **Menutup utang verifikasi UI** (BUG-5/6/7 + REGRESI-1/2) dengan E2E multi-role; perbaiki apa pun yang merah.
2. **Menutup cacat baru: kebocoran data gate** (verify_partner membuat lead uji dan tidak purge), plus guardrail agar kejadian serupa terdeteksi.
3. **Fase 51A — Retensi Subkon ↔ Klaim Garansi**: retensi ditahan bila ada klaim garansi berjalan pada unit di lingkup SPK; override beralasan + SoD.
4. **Fase 51B — Notifikasi WA otomatis**: garansi hampir habis + pengingat termin jatuh tempo/tunggakan (mode simulasi bila kredensial kosong), dedup/idempoten.
5. **Fase 51C — Portal pembeli diperkuat**: ringkasan garansi, ajukan & lacak klaim, unduh BAST + kwitansi secara aman (tokenized download), kosong-jujur.
6. **Guardrails**: tambah gate baru (target 43) + `mutasi_51.py` (≥18 mutasi) + docs/spec + update peta kode & hasil uji.

---

## 2) Implementation Steps

### Phase 0 — Tutup utang verifikasi + bersihkan kebocoran gate (wajib sebelum F51)
**0.1 E2E verifikasi BUG-5/6/7 + REGRESI-1/2 (testing_agent_v3)**
- Beritahu testId login yang benar: `login-email-input`, `login-password-input`, `login-submit-button`.
- Verifikasi:
  1) **BUG-5**: lead tanpa mitra → kartu atribusi jujur “bukan dari mitra” + `lead-partner-fee-empty`.
  2) **BUG-6**: `/partners/{id}` tab “Dokumen Onboarding” → DocChecklist / empty-jujur (bukan “dijadwalkan Fase …”).
  3) **BUG-7 (RBAC)**: role `sales@` di tab Fee Mitra → kartu manusiawi “Akses fee mitra dibatasi” (tanpa `[object Object]`).
  4) **REGRESI-1**: tab lain di profil pelanggan (Ringkasan/KPR/Dokumen/Unit/Komplain/Timeline) terbuka tanpa galat.
  5) **REGRESI-2**: pastikan tidak ada teks “dijadwalkan Fase”, `[object Object]`, `undefined`, `NaN`, atau enum Inggris mentah.

**0.2 Perbaiki kebocoran data gate**
- Tambah `_fixture_partner.py` (atau re-use fixture pola fase 47/50) untuk membuat & **purge** data gate `verify_partner`.
- Ubah `scripts/verify_partner.py` agar:
  - memakai marker `demo_marker="gate42"`/prefix nama “Gate …” terpusat,
  - **selalu purge** di akhir (atau via context manager) termasuk lead `Gate 42 Lead Mitra`.
- Bersihkan DB dev: hapus lead tertinggal “Gate 42 Lead Mitra” (+628129990042).

**0.3 Guardrail anti-bocor**
- Tambah pemeriksaan ke `forensic_audit.py` (atau gate baru kecil) untuk mendeteksi dokumen uji (prefix `Gate|Uji|POC` / `demo_marker` tertentu) yang tidak dipurge.
- Pastikan log gate/mutasi ke `memory/gatelogs/`.

**User stories (Phase 0)**
1. Sebagai QA, saya bisa login otomatis via testId yang stabil tanpa timeout.
2. Sebagai sales, saya melihat alasan akses dibatasi yang manusiawi di area fee mitra.
3. Sebagai admin, saya tidak melihat “Gate/Uji/POC …” muncul di daftar lead/mitra.
4. Sebagai user, tab profil pelanggan mana pun terbuka tanpa teks placeholder fase kadaluarsa.
5. Sebagai auditor, saya yakin karena ada pemeriksaan yang menangkap kebocoran data uji.

---

### Phase 1 — POC Core Fase 51A/51B/51C (jangan lanjut sebelum PASS)
**Output:** `poc/poc_51.py` PASS + cleanup bersih.

**Core flow yang dibuktikan (minimal):**
A) **Retensi vs Klaim Garansi (51A)**
- Retensi `release` **ditahan** bila ada `warranty_claims` status aktif pada unit dalam scope SPK.
- Override hanya role berizin (`finlead/owner`) + alasan ≥10 + audit trail.
- Idempotensi keputusan `release` (client_ref / event_key) → replay tidak dobel.

B) **WA Reminders (51B)**
- Scheduler/trigger menghasilkan kandidat reminder:
  - garansi hampir habis (threshold dari settings),
  - termin jatuh tempo (H-N),
  - tunggakan (overdue).
- Dedup key per (org, kind, entity_id, due_bucket) sehingga hanya sekali per periode.
- Mode simulasi bila env WA kosong: status “simulasi” + payload tersimpan sebagai riwayat.

C) **Portal buyer (51C)**
- Portal menampilkan ringkasan garansi per bagian (sisa hari / “belum ada data” bila belum BAST).
- Portal bisa ajukan klaim (eligible saja) dan melacak status.
- Download BAST & kwitansi via endpoint bertoken (bukan link mentah), error jujur.

**Websearch (best practice)**
- Pola dedup reminder & idempotensi job scheduler (FastAPI + Mongo) + “outbox table” pattern.
- Tokenized download link untuk dokumen (TTL token, scope doc_id + user).

**User stories (POC Phase 1)**
1. Sebagai finlead, saya mencoba melepas retensi dan sistem menahan bila ada klaim garansi aktif.
2. Sebagai owner, saya bisa override tahanan dengan alasan jelas dan itu tercatat.
3. Sebagai admin, reminder WA tidak terkirim berulang walau job dipanggil berkali-kali.
4. Sebagai pembeli portal, saya bisa melihat sisa garansi yang jujur dan mengajukan klaim.
5. Sebagai QA, setelah POC selesai tidak ada data uji tersisa di layar.

---

### Phase 2 — V1 App Development Fase 51A/51B/51C (backend + UI)

**51A Backend/UI (Retensi ↔ Garansi)**
- Backend:
  - Extend mesin retensi (`subcon_retention.py`/engine terkait): sebelum `release`, cek klaim garansi aktif untuk unit di scope SPK.
  - Tambah endpoint/field “holds[]” dengan alasan rinci (honest) + `override_hold` + `override_reason`.
  - Audit log + SoD (pengaju != penyetuju).
- UI:
  - Di halaman Subkon/Retensi: tampilkan status tahanan “Klaim garansi aktif” + daftar unit/klaim terkait + CTA ke board garansi.
  - Semua aksi punya `data-testid` di `constants/testIds/subconClaims.js` (atau file baru p51).

**51B Backend/UI (WA reminders)**
- Backend:
  - Modul `wa_reminder_engine.py`: build kandidat, dedup, simpan `wa_outbox`/`wa_delivery_log`.
  - Integrasi template: pakai `wa_templates` (SSOT), jangan string hardcode.
  - Cron tick (APScheduler) + endpoint manual `POST /api/wa/reminders/run` (rbac manage) untuk uji.
- UI:
  - Halaman/Tab “Notifikasi WA Otomatis”: konfigurasi threshold (dari Config Center), tombol “Jalankan sekarang” (manage), tabel riwayat (sent/simulated/failed) + alasan.

**51C Backend/UI (Portal buyer 강화)**
- Backend:
  - Endpoint portal: `GET /api/portal/warranty`, `POST /api/portal/warranty/claims`, `GET /api/portal/documents`.
  - Token download: `POST /api/portal/documents/{id}/token` + `GET /api/documents/download?token=...`.
- UI Portal:
  - Halaman “Garansi Saya”: ringkasan per bagian + CTA ajukan klaim.
  - Halaman “Dokumen Saya”: BAST + kwitansi (downloadFile open:true) + empty-jujur.

**E2E (testing_agent_v3) — V1**
- Skenario peran: owner/finlead/finance/pm/site/cs/sales/portal buyer.
- Fokus: tahanan retensi, override beralasan, dedup reminder, portal download & klaim.

**User stories (Phase 2)**
1. Sebagai finance, saya melihat retensi ditahan karena klaim garansi aktif beserta rujukan klaim.
2. Sebagai finlead, saya melepas retensi dengan override beralasan dan tercatat di audit.
3. Sebagai marketing/CS, saya melihat riwayat reminder WA yang jujur (simulasi vs terkirim).
4. Sebagai pembeli portal, saya mengunduh BAST/kwitansi tanpa link mentah dan melihat pesan error yang jelas.
5. Sebagai PM/site, klaim garansi portal masuk sebagai work item yang bisa ditangani sesuai SoD.

---

### Phase 3 — Gates + Mutasi + Docs + Close (target 43 gates)
**Gates baru**
- Gate 41: `scripts/verify_retention_warranty.py`
- Gate 42: `scripts/verify_wa_reminders.py`
- Gate 43: `scripts/verify_portal_warranty.py`
- Register di `scripts/run_all_gates.sh`.

**Mutasi**
- `scripts/mutasi_51.py` (≥18 mutasi), contoh kelas mutasi:
  - retensi release tanpa cek klaim aktif,
  - override reason <10 diterima,
  - SoD dilanggar (pengaju==penyetuju),
  - dedup reminder bocor (kirim 2x),
  - mode simulasi tidak jujur (mengaku terkirim),
  - portal download tanpa token masih boleh,
  - portal bisa klaim di luar masa garansi tanpa alasan.

**Docs/Maps**
- Tambah spec:
  - `docs/v2/46_RETENTION_WARRANTY_SPEC.md`
  - `docs/v2/47_WA_REMINDER_SPEC.md`
  - `docs/v2/48_PORTAL_BUYER_SPEC.md`
- Update: `CODEBASE_MAP.md`, `test_result.md`, `memory/test_credentials.md`, `plan.md`.

**User stories (Phase 3)**
1. Sebagai auditor, saya percaya karena gate baru membuktikan tahanan & dedup.
2. Sebagai QA, semua mutasi 51 tertangkap dan baseline kembali hijau.
3. Sebagai dev, `bash scripts/run_all_gates.sh` PASS (43 gates).
4. Sebagai admin, seed demo fase 51 idempoten dan tidak menambah data ganda.
5. Sebagai user, dokumentasi menjelaskan perilaku “ditahan” dan “simulasi” secara jujur.

---

## 3) Next Actions
1. Jalankan **testing_agent_v3** untuk menutup utang verifikasi BUG-5/6/7 + REGRESI-1/2 (pakai testId login yang benar).
2. Implement **purge verify_partner** + hapus lead bocor “Gate 42 Lead Mitra” dari DB + tambah cek anti-bocor di forensic_audit.
3. Tulis & jalankan **`poc/poc_51.py`** sampai PASS.
4. Implement V1 backend+UI untuk 51A/51B/51C, lalu E2E multi-role.
5. Tambah gate 41–43 + `mutasi_51.py`, update docs + maps, pastikan overall PASS.

---

## 4) Success Criteria
**Phase 0**
- BUG-5/6/7 + REGRESI-1/2 terverifikasi PASS; tidak ada teks placeholder fase/enum bocor.
- Tidak ada data uji gate/POC bocor ke layar (forensic audit menangkap bila ada).

**POC 51**
- `python3 poc/poc_51.py` PASS dan cleanup bersih.

**V1 51**
- Retensi: tahan bila klaim aktif; override beralasan + SoD; UI menjelaskan sebab.
- WA reminders: dedup/idempoten; mode simulasi jujur; riwayat bisa dibaca.
- Portal: garansi/claim/download berjalan, tokenized download, empty-jujur.

**Guardrails**
- `bash scripts/run_all_gates.sh` → **OVERALL PASS (43 gates)**.
- `python3 scripts/mutasi_51.py` → semua mutasi **TERTANGKAP** dan baseline kembali hijau.
