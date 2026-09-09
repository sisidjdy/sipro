# Panduan Mendapatkan Kredensial Meta WhatsApp Cloud API

Dokumen pendamping `WA_INTEGRATION_PLAN.md`. Ikuti berurutan; total ±45–90 menit
(di luar waktu verifikasi bisnis oleh Meta).

## Prasyarat
- Akun Facebook pribadi (untuk login developer) + akses Admin ke **Meta Business Portfolio**
  (business.facebook.com) perusahaan. Kalau belum ada, buat di https://business.facebook.com.
- Satu nomor telepon yang **belum** terdaftar di aplikasi WhatsApp/WhatsApp Business biasa
  (atau bersedia dilepas dari aplikasi tersebut). Nomor ini menjadi nomor pengirim SIPRO.
- Domain HTTPS aplikasi SIPRO (untuk webhook), mis. `https://sipro.perusahaan.co.id`.

## Langkah 1 — Buat Meta App
1. Buka https://developers.facebook.com → **My Apps** → **Create App**.
2. Use case: **Other** → tipe **Business** → isi nama app (mis. "SIPRO WhatsApp"),
   pilih Business Portfolio perusahaan → **Create App**.
3. Di dashboard app, kartu **WhatsApp** → **Set up**. Menu kiri kini punya
   **WhatsApp › API Setup** dan **WhatsApp › Configuration**.

## Langkah 2 — `WHATSAPP_PHONE_ID` & `WHATSAPP_WABA_ID`
1. Menu **WhatsApp › API Setup**.
2. Bagian *Send and receive messages*:
   - **Phone number ID** → salin ke `WHATSAPP_PHONE_ID` (angka panjang, ±15 digit).
   - **WhatsApp Business Account ID** → salin ke `WHATSAPP_WABA_ID`.
3. Awalnya Meta memberi *test number* gratis (hanya bisa kirim ke ≤5 nomor terverifikasi).
   Untuk produksi: **Add phone number** → masukkan nomor perusahaan → verifikasi OTP
   (SMS/telepon) → isi nama tampilan bisnis. Setelah nomor produksi ditambahkan, **ulangi**
   langkah 2 dan salin Phone number ID milik nomor produksi (ID berbeda dengan test number).

> Token sementara (*Temporary access token*) di halaman ini hanya berlaku 24 jam —
> **jangan** dipakai untuk SIPRO; gunakan Langkah 3.

## Langkah 3 — `WHATSAPP_TOKEN` (System User permanent token)
1. Buka https://business.facebook.com/settings → **Users › System users** → **Add**.
2. Nama mis. `sipro-wa-bot`, role **Admin** → **Create system user**.
3. Klik system user tsb → **Add assets**:
   - **Apps** → pilih app "SIPRO WhatsApp" → **Full control** (Manage app).
   - **WhatsApp accounts** → pilih WABA perusahaan → **Full control**.
   → **Save changes**.
4. Klik **Generate new token**:
   - App: "SIPRO WhatsApp".
   - **Token expiration: Never**.
   - Permissions (centang): `whatsapp_business_messaging`, `whatsapp_business_management`,
     `business_management`.
   → **Generate token**. Salin sekarang (hanya ditampilkan sekali) → `WHATSAPP_TOKEN`.
5. Uji cepat (ganti nilai dalam `<>`; nomor tujuan format `62812xxxxxxx` tanpa `+`):
   ```bash
   curl -X POST "https://graph.facebook.com/v23.0/<PHONE_ID>/messages" \
     -H "Authorization: Bearer <TOKEN>" -H "Content-Type: application/json" \
     -d '{"messaging_product":"whatsapp","to":"<NOMOR_TUJUAN>","type":"template",
          "template":{"name":"hello_world","language":{"code":"en_US"}}}'
   ```
   Respons berisi `"messages":[{"id":"wamid...."}]` = token & Phone ID benar.

## Langkah 4 — `WHATSAPP_APP_SECRET`
1. Dashboard app → **App settings › Basic**.
2. Baris **App secret** → **Show** (minta password Facebook) → salin → `WHATSAPP_APP_SECRET`.
   Dipakai SIPRO untuk memverifikasi header `X-Hub-Signature-256` agar webhook palsu ditolak.
3. Di halaman yang sama isi **Privacy Policy URL** (wajib sebelum app dibuat *Live*).

## Langkah 5 — `WHATSAPP_VERIFY_TOKEN` & pendaftaran webhook
1. Tentukan sendiri string acak, mis. hasil `openssl rand -hex 24` → `WHATSAPP_VERIFY_TOKEN`.
2. Isi kelima nilai di SIPRO: **Pusat Konfigurasi › Integrasi WhatsApp** (setelah Fase 97),
   lalu tekan **Simpan**. SIPRO kini siap menjawab handshake.
3. Dashboard app → **WhatsApp › Configuration** → *Webhook* → **Edit**:
   - **Callback URL**: `https://<domain-sipro>/api/webhooks/wa`
   - **Verify token**: nilai `WHATSAPP_VERIFY_TOKEN` yang sama.
   → **Verify and save** (Meta mengirim `GET ?hub.mode=subscribe&hub.verify_token=...&hub.challenge=...`;
   SIPRO membalas `hub.challenge`).
4. Bagian *Webhook fields* → **Manage** → **Subscribe** pada: `messages`,
   `message_template_status_update`, `message_template_quality_update`,
   `phone_number_quality_update`, `account_update`.

## Langkah 6 — Mode Live & verifikasi bisnis (agar tidak dibatasi)
1. Dashboard app → toggle **App Mode: Development → Live** (butuh Privacy Policy URL).
2. Business Settings → **Security Center** → **Start verification** (unggah dokumen legal
   perusahaan: NIB/akta, tagihan/utilitas dengan alamat). Tanpa verifikasi bisnis nomor
   dibatasi 250 percakapan bisnis/24 jam dan nama tampilan belum resmi.
3. Business Settings → **WhatsApp accounts › Payment methods** → tambah kartu (tagihan per
   percakapan; kategori utility/authentication lebih murah dari marketing).
4. Setelah verifikasi, batas naik bertahap (1K → 10K → 100K percakapan/hari) sesuai kualitas
   nomor (**Quality rating** GREEN di WhatsApp Manager).

## Langkah 7 — Template pesan (dibutuhkan Fase 96)
1. https://business.facebook.com/wa/manage/message-templates → **Create template**.
2. Kategori **Utility** untuk pengingat tagihan/BAST/OTP-nya *Authentication*; **Marketing**
   untuk promo. Bahasa **Indonesian (id)**. Variabel ditulis `{{1}}`, `{{2}}`, …
3. Status *Pending* → biasanya disetujui <24 jam. SIPRO akan menarik status ini otomatis.

## Ringkasan yang dikirim ke tim SIPRO
```
WHATSAPP_TOKEN=EAAG...            (System user, never expire)
WHATSAPP_PHONE_ID=1234567890123    (nomor PRODUKSI)
WHATSAPP_WABA_ID=9876543210987
WHATSAPP_APP_SECRET=abcd1234...
WHATSAPP_VERIFY_TOKEN=<string acak Anda>
```
Kirim lewat jalur aman (bukan chat publik). Token bisa dicabut/diputar ulang kapan saja
dari System Users → Generate new token.

## Kesalahan umum
- **(#190) Invalid OAuth access token** → token sementara 24 jam kadaluarsa; pakai system user.
- **(#100) Unsupported post request** pada `/messages` → Phone ID salah (memakai WABA ID atau
  ID test number setelah pindah ke nomor produksi).
- **(#131030) Recipient not in allowed list** → masih memakai test number; tambahkan nomor
  tujuan di API Setup › *To* atau pindah ke nomor produksi.
- **(#131047) Re-engagement message** → sesi 24 jam tertutup, kirim harus lewat template.
- **Webhook "The callback URL or verify token couldn't be validated"** → SIPRO belum menyimpan
  VERIFY_TOKEN yang sama, atau endpoint belum bisa diakses publik via HTTPS.
- **(#132000/132001) Template name does not exist / not approved** → template belum
  disetujui atau nama/bahasa berbeda dengan yang terdaftar.
