"""Auth primitives: JWT (HS256) + bcrypt. Users use UUID string ids.

## Fase 54 — kenapa resolusi token di berkas ini pernah SALAH

Dulu `_extract_token()` berbunyi:

    token = request.cookies.get("access_token")
    if not token:                      # <- hanya kalau cookie KOSONG
        <baru> baca Authorization: Bearer

Artinya cookie yang **ADA tetapi KEDALUWARSA** mengalahkan header `Authorization` yang
membawa token **SAH**: `jwt.decode` melempar `ExpiredSignatureError`, permintaan dijawab 401,
padahal pemanggil sudah menyerahkan bekal yang benar. Akibat nyatanya:

  * frontend menyimpan token di `localStorage` dan mengirimnya sebagai Bearer, sementara
    peramban tetap melampirkan cookie lama secara otomatis — begitu keduanya tidak sinkron,
    aplikasi 401 tanpa sebab yang bisa dijelaskan ke pemakai;
  * dan ini penghalang KERAS bagi perpanjangan sesi: `POST /auth/refresh` menyerahkan token
    baru yang dipakai sebagai Bearer, tetapi cookie `access_token` yang basi masih terkirim,
    sehingga sesi yang baru diperpanjang justru 401 SELAMANYA.

Sejak Fase 54 aturannya: **kumpulkan semua kandidat bekal sesi (header dulu, lalu cookie),
coba satu per satu, dan hanya menolak bila SEMUANYA gagal.** Token yang sah adalah token yang
sah — dari pintu mana pun ia datang. Yang ditolak pun menyebut SEBABNYA lewat tajuk
`X-Session-State` (kamus SSOT `session_state`), karena hanya `expired` yang boleh dicoba
diperpanjang diam-diam; sisanya harus mengantar pemakai ke halaman masuk.
"""
import os
import bcrypt
import jwt
from datetime import datetime, timezone, timedelta
from fastapi import Request, HTTPException

from db import db

JWT_ALGORITHM = "HS256"

# Umur bekal sesi. Dijadikan konstanta (bukan angka telanjang di dalam fungsi) supaya
# endpoint refresh, gate, dan dokumentasi membaca SATU sumber yang sama.
ACCESS_TTL = timedelta(hours=24)
REFRESH_TTL = timedelta(days=7)

# Keadaan sesi — nilainya WAJIB sama dengan kamus SSOT `session_state`
# (backend/reference_p54.py). Dikirim di tajuk `X-Session-State`.
SESSION_ACTIVE = "active"
SESSION_MISSING = "missing"
SESSION_EXPIRED = "expired"
SESSION_INVALID = "invalid"
SESSION_REVOKED = "revoked"

# Kalimat untuk manusia. Sengaja TIDAK menyebut "token"/"JWT"/nama cookie: pemakai tidak
# bisa berbuat apa pun dengan istilah itu, dan repo ini melarang membocorkan istilah internal
# ke layar. Tindakan teknisnya dibawa tajuk `X-Session-State`, bukan kalimat ini.
SESSION_MESSAGE = {
    SESSION_MISSING: "Anda belum masuk. Silakan masuk untuk melanjutkan.",
    SESSION_EXPIRED: "Sesi Anda sudah berakhir. Silakan masuk kembali.",
    SESSION_INVALID: "Sesi Anda tidak dikenali. Silakan masuk kembali.",
    SESSION_REVOKED: "Akses akun Anda sedang dinonaktifkan. Hubungi admin.",
}


def session_error(state: str, status_code: int = 401,
                  detail: str = None) -> HTTPException:
    """Galat sesi yang JUJUR: kalimat untuk manusia + kode untuk mesin.

    `detail` tetap string (bukan objek) karena layar repo ini mencetak `detail` apa adanya —
    membuatnya objek langsung melahirkan "[object Object]" di muka pengguna.
    """
    return HTTPException(status_code=status_code,
                         detail=detail or SESSION_MESSAGE.get(state, SESSION_MESSAGE[SESSION_INVALID]),
                         headers={"X-Session-State": state})


def get_jwt_secret() -> str:
    return os.environ["JWT_SECRET"]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def create_access_token(user_id: str, email: str, role: str, active_org_id: str = None) -> str:
    payload = {
        "sub": user_id, "email": email, "role": role, "type": "access",
        "exp": datetime.now(timezone.utc) + ACCESS_TTL,
    }
    if active_org_id:
        payload["active_org_id"] = active_org_id
    return jwt.encode(payload, get_jwt_secret(), algorithm=JWT_ALGORITHM)


def create_refresh_token(user_id: str) -> str:
    payload = {
        "sub": user_id, "type": "refresh",
        "exp": datetime.now(timezone.utc) + REFRESH_TTL,
    }
    return jwt.encode(payload, get_jwt_secret(), algorithm=JWT_ALGORITHM)


def candidate_tokens(request: Request, cookie_name: str = "access_token") -> list:
    """Semua bekal sesi yang dikirim pemanggil — **header lebih dulu**, lalu cookie.

    Urutannya bukan selera: `Authorization` adalah pilihan SENGAJA dari pemanggil pada
    permintaan itu, sedangkan cookie dilampirkan peramban secara otomatis dan bisa jauh
    lebih tua. Yang sengaja harus menang atas yang otomatis.
    """
    out = []
    header = request.headers.get("Authorization", "")
    if header.startswith("Bearer "):
        tok = header[7:].strip()
        if tok:
            out.append(tok)
    cookie = request.cookies.get(cookie_name)
    if cookie and cookie not in out:
        out.append(cookie)
    return out


def decode_session_tokens(tokens: list, expected_type: str = "access"):
    """Coba tiap kandidat; kembalikan `(payload, state)`.

    `payload` berisi klaim kandidat PERTAMA yang benar-benar sah. Bila tidak ada yang sah,
    `payload` = None dan `state` menjelaskan sebab TERBAIK yang diketahui:
    `expired` lebih diutamakan daripada `invalid` karena hanya `expired` yang bisa
    ditindaklanjuti (diperpanjang) — melaporkannya sebagai `invalid` akan memaksa pemakai
    mengetik sandi padahal sesinya sebenarnya masih bisa diselamatkan.
    """
    if not tokens:
        return None, SESSION_MISSING
    state = SESSION_INVALID
    for tok in tokens:
        try:
            payload = jwt.decode(tok, get_jwt_secret(), algorithms=[JWT_ALGORITHM])
        except jwt.ExpiredSignatureError:
            state = SESSION_EXPIRED
            continue
        except jwt.InvalidTokenError:
            continue
        if payload.get("type") != expected_type:
            # Salah jenis: token refresh tidak boleh dipakai sebagai token kerja (kalau
            # boleh, umur sesi efektif menjadi 7 hari dan seluruh guna access token hilang).
            continue
        return payload, SESSION_ACTIVE
    return None, state


def claims_ignoring_expiry(tokens: list, expected_type: str = "access"):
    """Klaim dari token yang TANDA TANGANNYA sah, walau waktunya sudah lewat.

    Dipakai HANYA untuk membaca konteks yang harus bertahan melewati perpanjangan —
    khususnya `active_org_id` milik `super_admin` yang sedang "bertindak sebagai" penyewa
    lain. Tanpa ini, memperpanjang sesi akan memulangkannya ke organisasi asal TANPA PESAN:
    layar masih menulis nama penyewa yang lama sementara datanya sudah milik penyewa lain.
    Tanda tangan tetap diperiksa; yang diabaikan hanya `exp`.
    """
    for tok in tokens:
        try:
            payload = jwt.decode(tok, get_jwt_secret(), algorithms=[JWT_ALGORITHM],
                                 options={"verify_exp": False})
        except jwt.InvalidTokenError:
            continue
        if payload.get("type") == expected_type:
            return payload
    return {}


def _extract_token(request: Request):
    """Kompatibilitas: kandidat pertama (header dulu). Jangan dipakai untuk otentikasi baru."""
    tokens = candidate_tokens(request)
    return tokens[0] if tokens else None


def apply_org_context(user: dict, payload: dict) -> dict:
    """EPIC M4 — multi-tenant: `super_admin` boleh "bertindak sebagai" penyewa lain lewat
    klaim `active_org_id`. `org_id` efektif disuntikkan di sini supaya SETIAP router/query
    yang ber-scope organisasi ikut berpindah secara transparan. Organisasi asal disimpan
    terpisah untuk UI pengalih + tombol pulang.
    """
    user["home_org_id"] = user.get("org_id")
    active = (payload or {}).get("active_org_id")
    if active and user.get("role") == "super_admin":
        user["org_id"] = active
        user["active_org_id"] = active
    return user


async def load_session_user(payload: dict) -> dict:
    """Ambil pengguna dari klaim yang sudah sah, lalu berlakukan gerbang akun.

    Akun yang hilang/nonaktif dilaporkan sebagai `revoked` — BUKAN `expired` — supaya layar
    tidak mencoba memperpanjang sesi yang memang sudah dimatikan (dan supaya pemakai tidak
    melihat "sesi berakhir" untuk sesuatu yang sebenarnya keputusan admin).
    """
    user = await db.users.find_one({"id": payload["sub"]}, {"_id": 0, "password_hash": 0})
    if not user:
        raise session_error(SESSION_REVOKED, detail="Akun Anda tidak ditemukan lagi. Hubungi admin.")
    if not user.get("is_active", True):
        raise session_error(SESSION_REVOKED, status_code=403)
    return apply_org_context(user, payload)


async def get_current_user(request: Request) -> dict:
    payload, state = decode_session_tokens(candidate_tokens(request))
    if payload is None:
        raise session_error(state)
    return await load_session_user(payload)
