# Deploy SIPRO ke VPS (Ubuntu 22.04 / 24.04 / 26.04)

Arsitektur di VPS (Docker Compose, folder `deploy/`):

```
Internet ──443──> Caddy (HTTPS Let's Encrypt otomatis + auto-renew)
                    ├── /api/*  → backend  (FastAPI :8001)   ← webhook Meta: /api/webhooks/wa
                    └── /*      → frontend (nginx, build React)
                  MongoDB 7 (volume mongo_data)
```

Tidak ada nilai yang di-hardcode: domain, rahasia, dan kredensial WhatsApp semuanya dari
`deploy/.env` (dibuat otomatis) dan dari UI Pusat Konfigurasi.

## 1. Syarat

| Item | Nilai |
|---|---|
| VPS | Ubuntu LTS, ≥2 vCPU, ≥4 GB RAM (build frontend butuh RAM), CPU dengan AVX (MongoDB 7) |
| Akses | `ssh root@IP` |
| DNS | A record subdomain → IP VPS, **tanpa proxy Cloudflare** (awan abu-abu / DNS only) |
| Port | 22, 80, 443 terbuka (skrip mengatur ufw) |

Contoh: `hl5.portalsipro.com` → A → `187.77.116.100`, TTL 3600.

## 2. Pasang sekali jalan

Pastikan kode terbaru sudah di-push ke GitHub (Emergent → *Save to GitHub*). Lalu dari komputer Anda:

```bash
ssh root@187.77.116.100 'apt-get update -qq && apt-get install -y -qq git && \
  git clone https://github.com/pandeyoga/dadada.git /opt/sipro && cd /opt/sipro && \
  DOMAIN=hl5.portalsipro.com ACME_EMAIL=email-anda@gmail.com bash deploy/install_vps.sh'
```

Skrip melakukan: paket dasar → Docker → firewall → cek DNS → buat `.env` (JWT_SECRET & OTP acak)
→ build & up → tunggu backend sehat → tunggu HTTPS → cron backup harian. Di akhir tercetak URL,
login awal, dan langkah WhatsApp.

## 3. Setelah terpasang

1. Buka `https://hl5.portalsipro.com`, login `superadmin@sipro.co.id / Sipro#2026` → **ganti sandi semua akun demo**.
2. Pusat Konfigurasi → **Integrasi WhatsApp**: isi 5 kredensial Meta → Simpan → **Tes koneksi** → **Diagnosa**.
3. **Uji handshake URL publik** → harus hijau (membuktikan Caddy/DNS benar).
4. **Daftarkan nomor** (PIN 6 digit) → **Langganankan app**.
5. Dashboard Meta → WhatsApp → Configuration → Webhook: Callback URL `https://hl5.portalsipro.com/api/webhooks/wa`
   + verify token (tombol mata di panel) → *Verify and save* → subscribe field yang tertera.
6. Kirim pesan uji → balas dari HP → checklist go-live hijau → Mode **Live**.

## 4. Operasional

```bash
cd /opt/sipro && bash deploy/update.sh            # tarik kode baru + rebuild + restart
cd /opt/sipro/deploy && docker compose ps         # status
cd /opt/sipro/deploy && docker compose logs -f backend   # log
bash /opt/sipro/deploy/backup.sh                  # backup manual (otomatis 02:00 WIB, 14 hari)
bash /opt/sipro/deploy/backup.sh restore deploy/backups/sipro-YYYY-MM-DD_HHMM.archive.gz
```

SSL: Caddy memperbarui sertifikat otomatis (±30 hari sebelum habis). Tidak ada cron certbot.

## 5. Pindah domain / server

- Ganti domain: ubah `DOMAIN=` di `deploy/.env` → `bash deploy/update.sh` → perbarui Callback URL di Meta.
- Pindah server: salin `deploy/.env` (JWT_SECRET **harus sama** agar kredensial WA terenkripsi bisa dibuka)
  dan arsip backup → `install_vps.sh` → `backup.sh restore`.

## 6. Masalah umum

| Gejala | Penyebab / solusi |
|---|---|
| HTTPS tidak aktif, `logs caddy` menyebut `acme` gagal | DNS belum mengarah / masih di-proxy Cloudflare; port 80 tertutup |
| `mongo` restart terus, log `AVX` | CPU tanpa AVX → ganti image `mongo:4.4` di `docker-compose.yml` |
| Build frontend `Killed` | RAM kurang → tambah swap 2 GB: `fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile` |
| Login gagal setelah pindah server | JWT_SECRET berubah → pakai `.env` lama |
| Uji handshake merah | Path `/api` tidak sampai backend → cek `docker compose ps`, `logs caddy` |
