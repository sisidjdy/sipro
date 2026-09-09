#!/usr/bin/env bash
# Pasang SIPRO di VPS Ubuntu (sekali jalan, idempoten).
# Pakai: DOMAIN=app.domain.com ACME_EMAIL=anda@mail.com bash deploy/install_vps.sh
set -euo pipefail
cd "$(dirname "$0")"
DEPLOY_DIR="$(pwd)"

: "${DOMAIN:?Set DOMAIN=subdomain.anda.com}"
: "${ACME_EMAIL:?Set ACME_EMAIL=email untuk Let's Encrypt}"

log() { printf '\n\033[1;36m[sipro] %s\033[0m\n' "$*"; }

log "1/7 Paket dasar"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq --no-install-recommends ca-certificates curl gnupg git ufw dnsutils openssl >/dev/null

log "2/7 Docker + Compose"
if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sh
fi
systemctl enable --now docker >/dev/null 2>&1 || true
docker compose version >/dev/null

log "3/7 Firewall (22, 80, 443)"
ufw allow 22/tcp >/dev/null || true
ufw allow 80/tcp >/dev/null || true
ufw allow 443/tcp >/dev/null || true
ufw allow 443/udp >/dev/null || true
ufw --force enable >/dev/null || true

log "4/7 Cek DNS $DOMAIN"
PUBLIC_IP="$(curl -fsS https://api.ipify.org || curl -fsS https://ifconfig.me || true)"
DNS_IP="$(dig +short A "$DOMAIN" @1.1.1.1 | tail -n1 || true)"
echo "  IP VPS   : ${PUBLIC_IP:-?}"
echo "  A record : ${DNS_IP:-(belum ada)}"
if [ -n "$PUBLIC_IP" ] && [ "$DNS_IP" != "$PUBLIC_IP" ]; then
  echo "  PERINGATAN: A record belum mengarah ke VPS (atau masih di-proxy Cloudflare). HTTPS akan gagal sampai DNS benar."
fi

log "5/7 Berkas .env"
if [ ! -f .env ]; then
  cat > .env <<EOF
DOMAIN=$DOMAIN
ACME_EMAIL=$ACME_EMAIL
DB_NAME=sipro
JWT_SECRET=$(openssl rand -hex 48)
PORTAL_MASTER_OTP=$(shuf -i 100000-999999 -n 1)
SEED_DEMO_USERS=true
SUPERADMIN_EMAIL=superadmin@sipro.co.id
SUPERADMIN_PASSWORD=Sipro#2026
DEFAULT_ORG_ID=org-sipro
DEFAULT_ORG_NAME=SIPRO Developer
STORAGE_PROVIDER=mongo
EMERGENT_LLM_KEY=
WHATSAPP_TOKEN=
WHATSAPP_PHONE_ID=
META_PIXEL_ID=
EOF
  chmod 600 .env
  echo "  .env dibuat (JWT_SECRET & OTP acak). Simpan berkas ini — dibutuhkan saat pindah server."
else
  sed -i "s|^DOMAIN=.*|DOMAIN=$DOMAIN|; s|^ACME_EMAIL=.*|ACME_EMAIL=$ACME_EMAIL|" .env
  echo "  .env sudah ada → DOMAIN/ACME_EMAIL diperbarui, rahasia dipertahankan."
fi

# Swap 2 GB bila RAM < 4 GB (build frontend rawan OOM).
MEM_KB="$(grep MemTotal /proc/meminfo | awk '{print $2}')"
if [ "$MEM_KB" -lt 3900000 ] && [ ! -f /swapfile ]; then
  log "RAM < 4 GB → menambah swap 2 GB"
  fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile >/dev/null && swapon /swapfile
  grep -q '/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

log "6/7 Build & jalankan (bisa 5-10 menit pada pemasangan pertama)"
docker compose pull --ignore-buildable >/dev/null 2>&1 || true
docker compose up -d --build

echo -n "  menunggu backend sehat "
for i in $(seq 1 90); do
  if docker compose exec -T backend python3 -c "import urllib.request;urllib.request.urlopen('http://localhost:8001/api/health',timeout=3)" >/dev/null 2>&1; then
    echo " ok (${i}x)"; break
  fi
  echo -n "."; sleep 5
  if [ "$i" -eq 90 ]; then echo; echo "  backend belum sehat — lihat: docker compose logs backend"; fi
done

echo -n "  menunggu HTTPS "
for i in $(seq 1 36); do
  if curl -fsS -o /dev/null "https://$DOMAIN/api/health" 2>/dev/null; then echo " ok"; break; fi
  echo -n "."; sleep 5
  if [ "$i" -eq 36 ]; then echo; echo "  HTTPS belum aktif — cek DNS lalu: docker compose logs caddy"; fi
done

log "7/7 Cron backup harian 02:00 WIB (19:00 UTC), simpan 14 hari"
( crontab -l 2>/dev/null | grep -v 'deploy/backup.sh' ; echo "0 19 * * * bash $DEPLOY_DIR/backup.sh >> $DEPLOY_DIR/backup.log 2>&1" ) | crontab -

cat <<EOF

================================================================
 SIPRO siap: https://$DOMAIN
 Login awal : $(grep '^SUPERADMIN_EMAIL=' .env | cut -d= -f2) / $(grep '^SUPERADMIN_PASSWORD=' .env | cut -d= -f2)
 OTP portal : $(grep '^PORTAL_MASTER_OTP=' .env | cut -d= -f2)
 Webhook WA : https://$DOMAIN/api/webhooks/wa
 Update     : cd $(dirname "$DEPLOY_DIR") && bash deploy/update.sh
 Log        : cd $DEPLOY_DIR && docker compose logs -f backend
================================================================
 Segera ganti sandi semua akun demo di Admin › Pengguna.
EOF
