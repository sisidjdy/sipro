# Rencana Penyempurnaan Integrasi WhatsApp (Meta WhatsApp Cloud API resmi)

Status: Fase 94 (inti) + Fase 95 SELESAI 5 Sep 2026 (lihat PRD). Sisa 94 (kirim dokumen, wa_outbox,
Broadcast lewat gateway), Fase 96 & 97 (dashboard, notifikasi gagal) = sesi berikutnya.
Go-live tanpa ubah kode: Pusat Konfigurasi › Integrasi WhatsApp → isi 5 kredensial → Simpan →
Tes koneksi → daftarkan webhook `https://<domain>/api/webhooks/wa` (verify token sama) → mode `live`.
Prinsip: semua dibangun & diuji dalam mode SIMULASI yang jujur; saat kredensial Meta
diberikan, owner cukup mengisi 5 nilai di Pusat Konfigurasi › Integrasi WhatsApp lalu
menekan "Tes koneksi" — tanpa perubahan kode.

## 0. Kredensial yang akan diminta saat go-live (owner menyiapkan)
| Kunci | Sumber di Meta | Dipakai untuk |
|---|---|---|
| `WHATSAPP_TOKEN` | System User permanent token (Business Settings › System Users) | semua panggilan Graph API |
| `WHATSAPP_PHONE_ID` | WhatsApp › API Setup › Phone number ID | kirim pesan/media |
| `WHATSAPP_WABA_ID` | WhatsApp Business Account ID | daftar/sinkron template |
| `WHATSAPP_APP_SECRET` | App › Settings › Basic | verifikasi tanda tangan webhook `X-Hub-Signature-256` |
| `WHATSAPP_VERIFY_TOKEN` | ditentukan sendiri (string acak) | handshake `GET /api/webhooks/wa` |
Webhook URL yang didaftarkan di Meta: `https://<domain>/api/webhooks/wa` (field: `messages`).
Disimpan terenkripsi per org di `channel_accounts` (bukan hanya `.env`); `.env` tetap
didukung sebagai fallback org default.

## Fase 94 — Gateway tunggal + kirim dokumen (fondasi)
Backend
- `wa_gateway.py`: satu pintu `send_text / send_template / send_document / send_image`
  → adapter `MetaCloudAdapter` (Graph API v21.0: `POST /{phone_id}/messages`,
  `POST /{phone_id}/media` untuk upload PDF) dan `SimulationAdapter` (perilaku sekarang).
  Mode dibaca dari `channel_accounts.wa_main.mode` (`simulation|live`) + kredensial org.
- Setiap pengiriman menulis `messages` dengan `provider_message_id` (wamid), `status`
  (`queued|sent|delivered|read|failed|simulated`), `error_code/error_detail`, `mode`.
  Tidak ada lagi fallback diam-diam: gagal = `failed` + alasan tampil di UI.
- Migrasi pemanggil ke gateway: Inbox `POST /inbox/{id}/messages`, Broadcast, Playbook
  (`send_template_message`), Reminder (`wa_reminder_engine`), `notifications.send_whatsapp`
  (OTP portal, komplain, bukti bayar, penawaran).
- Kirim dokumen: `POST /api/doc-history/send-wa {kind, id}` → render PDF (jalur yang sama
  dengan tombol PDF di Dokumen Terbit) → upload media → kirim `document` + caption dari
  template. Tercatat di percakapan lead/customer dan di riwayat dokumen (`doc_shares`).
- Antrean kirim ringan (`wa_outbox`): retry 3× backoff untuk error sementara (429/5xx),
  hormati batas laju per detik.
Frontend
- Tab Dokumen Terbit: tombol "Kirim via WhatsApp" per dokumen (nonaktif + alasan bila
  nomor tidak valid / belum +62 / channel nonaktif). Toast jujur: terkirim / simulasi / gagal.
- Inbox: badge status pesan keluar (✓ sent, ✓✓ delivered, biru read, ⚠ failed + alasan).
Uji: pytest adapter simulasi + adapter Meta dengan HTTP mock (respons 200/400/429).

## Fase 95 — Webhook Meta lengkap (pesan masuk & status)
- `GET /api/webhooks/wa`: handshake `hub.mode/hub.verify_token/hub.challenge`.
- `POST /api/webhooks/wa`: verifikasi `X-Hub-Signature-256` (HMAC-SHA256 app secret),
  parse `entry[].changes[].value`:
  - `messages[]` teks/gambar/dokumen/audio/lokasi/interaktif(tombol) → cari/buat lead by
    `wa_id` (+62), buka/perbarui sesi 24 jam (`window_expires_at`), simpan media (unduh via
    `GET /{media_id}` → Emergent Object Storage), unread++, picu `automation_rules`
    (`message.received`) & skor lead (`inbound_reply`).
  - `statuses[]` sent/delivered/read/failed → update `messages` & `broadcast_recipients`
    berdasarkan `wamid`; failed menyimpan `errors[0].code/title`.
  - `contacts[].profile.name` → isi nama lead bila masih "Lead Baru".
- Idempoten by `wamid` (indeks unik); payload mentah tak dikenal masuk `capture_failures`
  agar bisa diaudit, tidak dibuang.
- Kompatibilitas: kontrak lama `WebhookLead` (name/phone/message) tetap diterima untuk
  simulasi/integrasi internal.
- Frontend Inbox: render media masuk (thumbnail/gambar, tautan dokumen, pemutar audio),
  indikator "sesi 24 jam tersisa HH:MM", tombol simulasi pesan masuk hanya di mode simulasi.
Uji: fixture payload Meta asli (teks, gambar, status, error), signature valid/invalid.

## Fase 96 — Template Meta & kepatuhan
- `wa_templates` ditambah: `meta_name`, `language` (id), `components` (header/body/buttons,
  parameter `{{1}}..`), `meta_status` (APPROVED/PENDING/REJECTED + alasan), `category`
  resmi (MARKETING/UTILITY/AUTHENTICATION).
- Sinkron dua arah: `GET/POST /{waba_id}/message_templates` — tarik status approval,
  ajukan template baru dari Pusat Konfigurasi; pemetaan variabel SIPRO (`{{nama}}`, `{{unit}}`,
  `{{jatuh_tempo}}`, `{{jumlah}}`) → parameter berurutan Meta.
- Aturan kirim: di luar sesi 24 jam hanya template APPROVED; kategori MARKETING wajib
  cek opt-out; template PENDING/REJECTED dinonaktifkan otomatis dari pilihan.
- Kepatuhan: daftar opt-out/blacklist (balasan "STOP"/"berhenti" otomatis mendaftarkan),
  jam kirim (default 08:00–20:00 WIB, dari Pusat Konfigurasi), batas laju broadcast
  (mis. 20 pesan/detik, batch dengan jeda), pencatatan persetujuan (`consent_at/source`).
- Broadcast: antrean nyata (queued → sending → sent → delivered/read/failed), tombol
  jeda/lanjut/batal, laporan gagal per kode alasan, estimasi biaya percakapan per kategori.
Uji: template belum approved ditolak dengan alasan; opt-out menghentikan blast; jam kirim.

## Fase 97 — Konfigurasi, pemantauan & go-live checklist
- Pusat Konfigurasi › tab **Integrasi WhatsApp**: form 5 kredensial (tersimpan terenkripsi,
  ditampilkan tersamar), pilih mode `simulation|live`, tombol **Tes koneksi**
  (`GET /{phone_id}` → nama & kualitas nomor, `GET /{waba_id}/message_templates`),
  **Kirim pesan uji** ke nomor admin, status webhook (terakhir diterima, signature OK?),
  checklist go-live (kredensial ✓, webhook terverifikasi ✓, ≥1 template APPROVED ✓,
  nomor pengirim quality GREEN ✓, opt-out aktif ✓).
- Dashboard pengiriman WA (pola drill-down Fase 91–93): terkirim/terbaca/gagal per hari,
  per jenis (inbox/broadcast/pengingat/dokumen/OTP), kegagalan per kode; klik → daftar pesan.
- Notifikasi internal: gagal kirim ke sales pemilik lead; kualitas nomor turun/limit
  messaging tier → super admin.
- Dokumentasi runbook singkat di `/app/memory` (langkah setup Meta, pendaftaran webhook,
  pengajuan template).

## Urutan eksekusi & perkiraan
1. Fase 94 (fondasi + dokumen) — 1 sesi
2. Fase 95 (webhook) — 1 sesi
3. Fase 96 (template & kepatuhan) — 1 sesi
4. Fase 97 (konfigurasi, tes koneksi, dashboard) — 1 sesi
Setelah Fase 97: owner mengisi kredensial → Tes koneksi → daftarkan webhook → ubah mode ke
`live`. Semua modul (Inbox, Broadcast, Playbook, Pengingat, OTP, Dokumen) hidup serentak.
