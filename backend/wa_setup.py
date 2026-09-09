"""wa_setup — Wizard koneksi WhatsApp Cloud API dari antarmuka (Fase 100).

Semua langkah yang dulu hanya bisa lewat terminal/dashboard Meta kini punya tombol:
diagnosa token/nomor/WABA, daftarkan nomor ke Cloud API (PIN), verifikasi ulang nomor
(kode SMS/telepon), langganan webhook app→WABA, panduan webhook siap-salin, dan cek
handshake ke URL publik. Setiap hasil dicatat JUJUR (error Meta diteruskan, tidak dipalsukan).
"""
import re

import httpx

import wa_gateway as gw
from core_utils import now_iso
from db import db
from meta_api import GRAPH_BASE as GRAPH

PHONE_FIELDS = ("display_phone_number,verified_name,quality_rating,code_verification_status,status,"
                "platform_type,name_status,account_mode,messaging_limit_tier")
REQUIRED_SCOPES = ("whatsapp_business_messaging", "whatsapp_business_management")
WEBHOOK_FIELDS = ("messages", "message_template_status_update", "phone_number_quality_update", "account_update")
PIN_RE = re.compile(r"^\d{6}$")
PHONE_STATUS_HINT = {
    "CONNECTED": "Nomor terdaftar di Cloud API dan siap mengirim.",
    "PENDING": "Nomor belum terdaftar ke Cloud API. Pastikan nomor sudah TIDAK dipakai di aplikasi WhatsApp HP, "
               "lalu klik 'Daftarkan nomor' dengan PIN 6 digit.",
    "FLAGGED": "Nomor ditandai Meta (kualitas rendah). Kurangi laju kirim & perbaiki isi pesan.",
    "RESTRICTED": "Nomor dibatasi Meta — hanya bisa membalas pesan masuk sampai pembatasan dicabut.",
    "RATE_LIMITED": "Nomor dibatasi lajunya sementara. Tunggu 24 jam.",
    "DISCONNECTED": "Nomor terputus dari Cloud API — daftarkan ulang.",
    "MIGRATED": "Nomor dimigrasikan ke WABA lain — periksa Phone ID.",
    "BANNED": "Nomor diblokir Meta.",
}
REGISTER_HINT = {
    "133005": "PIN tidak cocok. Nomor ini sudah punya PIN verifikasi dua langkah — pakai PIN lama, atau matikan "
              "verifikasi dua langkah di WhatsApp Manager › Phone numbers › Two-step verification.",
    "133006": "Nomor perlu verifikasi ulang: minta kode (SMS/telepon) lalu masukkan kodenya di bawah, kemudian daftarkan lagi.",
    "133016": "Pendaftaran ditolak sementara (terlalu sering). Tunggu beberapa menit lalu coba lagi.",
    "131000": "Gangguan di sisi Meta. Coba lagi beberapa saat.",
    "100": "Parameter ditolak Meta — periksa Phone ID (harus ID nomor PRODUKSI, bukan test number).",
    "190": "Token tidak valid/kedaluwarsa. Buat System User token baru (expiry: Never).",
}


def _err(resp) -> tuple:
    try:
        e = resp.json().get("error") or {}
    except Exception:  # noqa: BLE001
        e = {}
    code = e.get("code") or resp.status_code
    detail = e.get("error_user_msg") or e.get("message") or resp.text[:200]
    return str(code), detail


class MetaSetupClient:
    """Panggilan Graph API untuk penyiapan akun (bukan kirim pesan). `transport` = mock untuk uji."""

    def __init__(self, creds: dict, transport=None):
        self.token, self.phone_id, self.waba_id = creds["token"], creds["phone_id"], creds.get("waba_id")
        self.transport = transport

    async def _call(self, method: str, path: str, **kw) -> dict:
        try:
            async with httpx.AsyncClient(timeout=25, transport=self.transport) as cli:
                resp = await cli.request(method, f"{GRAPH}/{path}",
                                         headers={"Authorization": f"Bearer {self.token}"}, **kw)
        except httpx.HTTPError as e:
            return {"ok": False, "error_code": "network", "error_detail": str(e)[:200]}
        if resp.status_code >= 300:
            code, detail = _err(resp)
            return {"ok": False, "error_code": code, "error_detail": detail}
        return {"ok": True, "data": resp.json()}

    async def token_info(self):
        return await self._call("GET", "debug_token", params={"input_token": self.token})

    async def phone(self):
        return await self._call("GET", self.phone_id, params={"fields": PHONE_FIELDS})

    async def waba(self):
        return await self._call("GET", self.waba_id, params={"fields": "name,account_review_status"})

    async def subscribed_apps(self):
        return await self._call("GET", f"{self.waba_id}/subscribed_apps")

    async def subscribe(self):
        return await self._call("POST", f"{self.waba_id}/subscribed_apps")

    async def register(self, pin: str):
        return await self._call("POST", f"{self.phone_id}/register", json={"messaging_product": "whatsapp", "pin": pin})

    async def request_code(self, method: str, language: str = "id"):
        return await self._call("POST", f"{self.phone_id}/request_code", json={"code_method": method, "language": language})

    async def verify_code(self, code: str):
        return await self._call("POST", f"{self.phone_id}/verify_code", json={"code": code})


async def _client(org_id: str, transport=None):
    cfg = await gw.get_config(org_id)
    if not cfg["live_ready"]:
        raise ValueError("Isi dan simpan WHATSAPP_TOKEN + WHATSAPP_PHONE_ID terlebih dulu.")
    return MetaSetupClient(cfg["creds"], transport), cfg


def phone_registered(ph: dict) -> bool:
    return (ph or {}).get("status") == "CONNECTED" or (ph or {}).get("platform_type") == "CLOUD_API"


async def diagnose(org_id: str, transport=None) -> dict:
    """Satu klik: token (validitas, tipe, scope), nomor (status pendaftaran), WABA, langganan webhook."""
    cli, cfg = await _client(org_id, transport)
    out = {"at": now_iso(), "ok": True, "problems": []}
    tok = await cli.token_info()
    td = (tok.get("data") or {}).get("data") or {}
    scopes = td.get("scopes") or []
    out["token"] = {"ok": tok["ok"] and bool(td.get("is_valid")), "type": td.get("type"),
                    "app_id": td.get("app_id"), "expires_at": td.get("expires_at"),
                    "permanent": tok["ok"] and td.get("expires_at") == 0, "scopes": scopes,
                    "missing_scopes": [s for s in REQUIRED_SCOPES if s not in scopes] if tok["ok"] else [],
                    "error": None if tok["ok"] else f"{tok['error_code']}: {tok['error_detail']}"}
    if not out["token"]["ok"]:
        out["problems"].append("Token tidak valid — buat System User token baru.")
    elif out["token"]["missing_scopes"]:
        out["problems"].append("Token kurang izin: " + ", ".join(out["token"]["missing_scopes"]))
    elif out["token"]["type"] != "SYSTEM_USER":
        out["problems"].append("Token bukan System User — token pengguna biasa kedaluwarsa (maks. 60 hari).")
    ph = await cli.phone()
    pd = ph.get("data") or {}
    out["phone"] = {**{k: pd.get(k) for k in PHONE_FIELDS.split(",")}, "id": cfg["creds"]["phone_id"],
                    "ok": ph["ok"], "registered": ph["ok"] and phone_registered(pd),
                    "hint": PHONE_STATUS_HINT.get((pd.get("status") or "").upper(), "") if ph["ok"]
                    else f"{ph['error_code']}: {ph['error_detail']}"}
    if not ph["ok"]:
        out["ok"] = False
        out["problems"].append(f"Phone ID tidak bisa dibaca: {ph['error_detail']}")
    elif not out["phone"]["registered"]:
        out["problems"].append(f"Nomor belum terdaftar ke Cloud API (status {pd.get('status')}).")
    out["waba"] = {"ok": False, "id": cfg["creds"].get("waba_id")}
    out["subscribed"], out["subscribed_apps"] = None, []
    if cli.waba_id:
        wb = await cli.waba()
        out["waba"] = {"ok": wb["ok"], "id": cli.waba_id, **(wb.get("data") or {}),
                       "error": None if wb["ok"] else f"{wb['error_code']}: {wb['error_detail']}"}
        subs = await cli.subscribed_apps()
        if subs["ok"]:
            apps = [((a.get("whatsapp_business_api_data") or {}).get("name") or a.get("id") or "app")
                    for a in (subs["data"].get("data") or [])]
            out["subscribed"], out["subscribed_apps"] = bool(apps), apps
            if not apps:
                out["problems"].append("Belum ada app yang berlangganan webhook WABA ini — klik 'Langganankan app'.")
        else:
            out["problems"].append(f"Langganan webhook tidak bisa dibaca: {subs['error_detail']}")
    else:
        out["problems"].append("WHATSAPP_WABA_ID kosong — template & langganan webhook tidak bisa diperiksa.")
    await db.channel_accounts.update_one({"id": cfg["channel"]["id"]}, {"$set": {"last_diagnose": out}})
    return out


async def register_phone(org_id: str, pin: str, transport=None) -> dict:
    if not PIN_RE.match(pin or ""):
        raise ValueError("PIN harus 6 digit angka.")
    cli, cfg = await _client(org_id, transport)
    res = await cli.register(pin)
    out = {"ok": res["ok"], "at": now_iso(), "error_code": res.get("error_code"), "error_detail": res.get("error_detail"),
           "hint": None if res["ok"] else REGISTER_HINT.get(str(res.get("error_code")),
                                                             "Periksa pesan Meta di atas; bila menyebut re-verification, minta kode dulu."),
           "needs_verification": str(res.get("error_code")) == "133006"}
    if res["ok"]:
        # PIN disimpan terenkripsi agar bisa dipakai lagi saat daftar ulang (mis. pindah server)
        await db.channel_accounts.update_one({"id": cfg["channel"]["id"]}, {"$set": {
            "registered_at": out["at"], "register_pin_enc": gw.encrypt(pin)}})
    return out


async def request_code(org_id: str, method: str, transport=None) -> dict:
    method = (method or "SMS").upper()
    if method not in ("SMS", "VOICE"):
        raise ValueError("Metode harus SMS atau VOICE.")
    cli, _ = await _client(org_id, transport)
    res = await cli.request_code(method)
    return {"ok": res["ok"], "method": method, "error_code": res.get("error_code"), "error_detail": res.get("error_detail")}


async def verify_code(org_id: str, code: str, transport=None) -> dict:
    if not re.match(r"^\d{4,8}$", code or ""):
        raise ValueError("Kode verifikasi harus 4–8 digit angka.")
    cli, _ = await _client(org_id, transport)
    res = await cli.verify_code(code)
    return {"ok": res["ok"], "error_code": res.get("error_code"), "error_detail": res.get("error_detail")}


async def subscribe_app(org_id: str, transport=None) -> dict:
    cli, cfg = await _client(org_id, transport)
    if not cli.waba_id:
        raise ValueError("Isi WHATSAPP_WABA_ID terlebih dulu.")
    res = await cli.subscribe()
    if res["ok"]:
        await db.channel_accounts.update_one({"id": cfg["channel"]["id"]}, {"$set": {
            "last_diagnose.subscribed": True, "subscribed_at": now_iso()}})
    return {"ok": res["ok"], "error_code": res.get("error_code"), "error_detail": res.get("error_detail")}


def _public_base(public_base: str, required: bool = True) -> str:
    base = (public_base or "").strip().rstrip("/")
    if not base and not required:
        return ""
    if not re.match(r"^https?://[A-Za-z0-9.\-:]+$", base):
        raise ValueError("URL publik tidak valid (contoh: https://sipro.perusahaan.co.id).")
    return base


async def webhook_guide(org_id: str, public_base: str) -> dict:
    cfg = await gw.get_config(org_id)
    base = _public_base(public_base, required=False)
    vt = cfg["creds"].get("verify_token") or ""
    return {"callback_url": f"{base}/api/webhooks/wa", "verify_token": vt, "verify_token_set": bool(vt),
            "app_secret_set": bool(cfg["creds"].get("app_secret")), "fields": list(WEBHOOK_FIELDS),
            "https": base.startswith("https://"),
            # URL legal yang diminta Meta di App Settings › Basic (Privacy Policy, Terms, Data Deletion).
            "legal_urls": {"privacy": f"{base}/privacy", "terms": f"{base}/terms",
                           "deletion": f"{base}/data-deletion"},
            "steps": [
                "Buka developers.facebook.com › App Anda › WhatsApp › Configuration › Webhook › Edit.",
                "Tempel Callback URL dan Verify token di bawah, klik 'Verify and save' (SIPRO membalas hub.challenge).",
                "Klik 'Manage' lalu Subscribe field: " + ", ".join(WEBHOOK_FIELDS) + ".",
                "Klik 'Langganankan app' di panel Penyiapan agar WABA ini mengirim event ke app Anda.",
                "Kirim pesan WhatsApp ke nomor bisnis dari HP lain — kolom 'Terakhir diterima' harus terisi.",
            ]}


async def handshake_check(org_id: str, public_base: str, transport=None) -> dict:
    """Panggil URL publik webhook seperti yang Meta lakukan: membuktikan domain/reverse proxy VPS benar."""
    cfg = await gw.get_config(org_id)
    base = _public_base(public_base)
    vt = cfg["creds"].get("verify_token") or ""
    if not vt:
        raise ValueError("WHATSAPP_VERIFY_TOKEN belum diisi.")
    url = f"{base}/api/webhooks/wa"
    try:
        async with httpx.AsyncClient(timeout=15, transport=transport, follow_redirects=True) as cli:
            r = await cli.get(url, params={"hub.mode": "subscribe", "hub.verify_token": vt, "hub.challenge": "sipro-ok"},
                              headers={"X-Sipro-Selfcheck": "1"})
    except httpx.HTTPError as e:
        return {"ok": False, "url": url, "detail": f"Tidak bisa dijangkau dari server: {str(e)[:160]}"}
    ok = r.status_code == 200 and r.text.strip() == "sipro-ok"
    return {"ok": ok, "url": url, "status_code": r.status_code,
            "detail": "Handshake berhasil — URL ini siap ditempel di Meta." if ok else
            f"Balasan {r.status_code}: {r.text[:120]!r} (harus 200 + challenge apa adanya). Periksa reverse proxy /api dan verify token."}
