"""Auth routes: login, register, me, logout, refresh."""
import time

from fastapi import APIRouter, Request, Response, HTTPException, Depends

from db import db, ORG_ID, COOKIE_SECURE, COOKIE_SAMESITE
from core_utils import new_id, now_iso, serialize_doc
from security import (
    hash_password, verify_password, create_access_token, create_refresh_token,
    get_current_user, candidate_tokens, claims_ignoring_expiry, decode_session_tokens,
    session_error, apply_org_context, ACCESS_TTL, REFRESH_TTL, SESSION_REVOKED,
)
from rbac import ALL_ROLES, effective_permissions
from models import LoginRequest, RegisterRequest

router = APIRouter(prefix="/auth", tags=["auth"])

# Umur cookie dibaca dari SATU sumber (`security.ACCESS_TTL`/`REFRESH_TTL`) supaya cookie
# tidak pernah lagi hidup lebih lama/pendek daripada token di dalamnya. Dulu angka 86400 &
# 604800 diketik langsung di sini, terpisah dari `timedelta` di `security.py` — dua tempat
# yang harus diubah bersamaan dan karena itu pasti akan berbeda suatu hari.
ACCESS_MAX_AGE = int(ACCESS_TTL.total_seconds())
REFRESH_MAX_AGE = int(REFRESH_TTL.total_seconds())


def _set_cookies(response: Response, access: str, refresh: str = None):
    response.set_cookie("access_token", access, httponly=True, secure=COOKIE_SECURE,
                        samesite=COOKIE_SAMESITE, max_age=ACCESS_MAX_AGE, path="/")
    if refresh:
        response.set_cookie("refresh_token", refresh, httponly=True, secure=COOKIE_SECURE,
                            samesite=COOKIE_SAMESITE, max_age=REFRESH_MAX_AGE, path="/")


def _public_user(u: dict) -> dict:
    u = serialize_doc(u)
    u.pop("password_hash", None)
    return u


async def session_payload(user: dict) -> dict:
    """Profil sesi LENGKAP — dipakai `/auth/login`, `/auth/register`, dan `/auth/me`.

    ## Cacat NYATA yang ditutup fungsi ini (dilaporkan pemakai: "saya masih belum punya
    ## akses, padahal superadmin")
    Dulu `/auth/login` mengembalikan `_public_user()` saja, sementara `/auth/me` menambahkan
    `permissions` (izin efektif peran). Frontend `AuthContext.login()` mengisi `user` dari
    jawaban LOGIN, jadi sepanjang sesi itu `user.permissions` = `undefined` dan
    `can(resource, action)` menjawab **false untuk apa pun** — termasuk untuk `super_admin`
    yang izinnya `{"*": ["*"]}`. Akibatnya, tepat setelah masuk:
      * `/documents` berkata \"Akun Anda belum diberi izin `documents` maupun `permits`\",
      * `/tax` menampilkan kartu AKSES DITOLAK,
      * `/bi` berkata \"Anda tidak punya akses ke Analitik & BI\",
    dan semuanya sembuh sendiri begitu halaman dimuat ulang (karena `bootstrap()` memanggil
    `/auth/me`). Layar menuduh hak akses padahal yang kurang adalah SATU FIELD di jawaban
    login. Sejak sekarang ketiga endpoint memakai SATU fungsi ini, sehingga bentuk profil
    sesi tidak bisa lagi berbeda antar pintu masuk.
    """
    u = _public_user(dict(user))
    org = await db.orgs.find_one({"id": user.get("org_id")}, {"_id": 0, "id": 1, "name": 1})
    home_id = user.get("home_org_id", user.get("org_id"))
    u["active_org"] = {"id": org.get("id"), "name": org.get("name")} if org else None
    u["home_org_id"] = home_id
    u["is_switched"] = bool(user.get("active_org_id")) and user.get("org_id") != home_id
    # Izin EFEKTIF peran ini (Fase 39b) — sumbernya tetap satu, `rbac.py`; yang dikirim ke
    # klien hanya HASILnya supaya tampilan tidak menawarkan aksi yang pasti ditolak.
    u["permissions"] = await effective_permissions(user.get("role"))
    return u


@router.post("/login")
async def login(payload: LoginRequest, response: Response):
    email = payload.email.lower()
    user = await db.users.find_one({"email": email})
    if not user or not verify_password(payload.password, user.get("password_hash", "")):
        raise HTTPException(status_code=401, detail="Email atau kata sandi salah")
    if not user.get("is_active", True):
        raise HTTPException(status_code=403, detail="Akun nonaktif, hubungi admin")
    # EPIC M4 — block login for users of a suspended tenant (super_admin exempt).
    if user.get("role") != "super_admin":
        org = await db.orgs.find_one({"id": user.get("org_id")}, {"_id": 0, "status": 1})
        if org and org.get("status") == "suspended":
            raise HTTPException(status_code=403, detail="Organisasi dinonaktifkan, hubungi super admin")
    access = create_access_token(user["id"], user["email"], user["role"])
    refresh = create_refresh_token(user["id"])
    _set_cookies(response, access, refresh)
    return {"data": await session_payload(user), "access_token": access,
            "token_type": "bearer"}


@router.post("/register")
async def register(payload: RegisterRequest, response: Response):
    email = payload.email.lower()
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=400, detail="Email sudah terdaftar")
    role = payload.role if payload.role in ALL_ROLES else "sales"
    ts = now_iso()
    user = {
        "id": new_id(), "org_id": ORG_ID, "name": payload.name, "email": email,
        "role": role, "password_hash": hash_password(payload.password), "phone": None,
        "is_active": True, "created_at": ts, "updated_at": ts,
    }
    await db.users.insert_one(user)
    access = create_access_token(user["id"], user["email"], user["role"])
    refresh = create_refresh_token(user["id"])
    _set_cookies(response, access, refresh)
    return {"data": await session_payload(user), "access_token": access,
            "token_type": "bearer"}


@router.get("/me")
async def me(user: dict = Depends(get_current_user)):
    return {"data": await session_payload(user)}


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/")
    return {"message": "Berhasil keluar"}


async def _tenant_gate(user: dict) -> None:
    """Gerbang penyewa — SAMA dengan yang dipakai `/auth/login`.

    Kalau gerbang ini tidak ada di jalur perpanjangan, perbaikan Fase 54 justru membuka
    pintu belakang: organisasi yang sudah disuspend tetap bisa memperpanjang sesinya
    berulang kali selama bekal 7 harinya belum habis, sehingga "menonaktifkan penyewa"
    hanya menjadi tulisan di layar admin.
    """
    if user.get("role") == "super_admin":
        return
    org = await db.orgs.find_one({"id": user.get("home_org_id", user.get("org_id"))},
                                {"_id": 0, "status": 1})
    if org and org.get("status") == "suspended":
        raise session_error(SESSION_REVOKED, status_code=403,
                            detail="Organisasi Anda sedang dinonaktifkan. Hubungi super admin.")


def _read_refresh_token(request: Request, body: dict) -> list:
    """Kandidat bekal perpanjangan: cookie, badan permintaan, lalu tajuk khusus.

    Peramban memakai cookie `httponly` (tidak bisa dibaca JavaScript — memang itu gunanya).
    Klien BUKAN peramban (skrip gate, aplikasi lapangan, alat uji) tidak punya cookie jar,
    jadi jalur badan/tajuk disediakan agar mereka tidak dipaksa memalsukan peramban.
    """
    out = []
    ck = request.cookies.get("refresh_token")
    if ck:
        out.append(ck)
    fromm_body = (body or {}).get("refresh_token")
    if fromm_body and fromm_body not in out:
        out.append(fromm_body)
    hdr = request.headers.get("X-Refresh-Token")
    if hdr and hdr not in out:
        out.append(hdr)
    return out


@router.post("/refresh")
async def refresh(request: Request, response: Response):
    """Perpanjang sesi TANPA meminta pemakai mengetik sandi lagi.

    ## Cacat yang ditutup endpoint ini

    Baris pertama berkas ini sudah menjanjikan "refresh" sejak lama, `login()` dan
    `register()` sudah memanggil `create_refresh_token()`, dan `_set_cookies()` sudah menulis
    cookie `refresh_token` berumur 7 hari — tetapi **tidak ada satu baris pun yang
    membacanya**. Jadi sesi mati keras di jam ke-24: pemakai yang sedang mengisi rincian
    biaya kontrak atau dialog tahap legal kehilangan pekerjaannya dan dilempar ke halaman
    masuk. Itulah keluhan "sesi sering habis, harus login berulang".

    ## Yang dipaksakan di sini

    1. **Jenis token dipaksa.** Hanya token ber-`type="refresh"` diterima; token kerja yang
       dikirim ke sini ditolak. Kalau tidak, umur sesi efektif menjadi 7 hari dan seluruh
       guna access token hilang.
    2. **Gerbang akun & penyewa sama dengan login.** Akun nonaktif dan organisasi disuspend
       TIDAK bisa memperpanjang; sebabnya dilaporkan `revoked`, bukan `expired`.
    3. **Konteks penyewa dipertahankan.** `super_admin` yang sedang "bertindak sebagai"
       penyewa lain tetap di penyewa itu — klaim `active_org_id` dibaca dari token kerja yang
       ADA (walau sudah kedaluwarsa; tanda tangannya tetap diperiksa). Tanpa ini, sekali
       diperpanjang ia pulang ke org asalnya tanpa pesan apa pun.
    4. **Bentuk profil sesi tetap satu.** Jawaban memakai `session_payload()` yang sama
       dengan `/login` dan `/me` (aturan Fase 53), sehingga izin yang baru diubah admin ikut
       berlaku begitu sesi diperpanjang dan tidak ada pintu masuk yang bentuknya beda.
    5. **Jendela bergeser, tapi tetap berbatas.** Bekal 7 hari hanya diperbarui bila sisanya
       sudah kurang dari separuh — supaya orang yang MEMANG masih bekerja tidak diusir tepat
       di hari ke-7, tetapi jendelanya tidak menjadi tak terbatas hanya karena aplikasi
       ramai memanggil endpoint ini.
    """
    try:
        body = await request.json()
    except Exception:
        body = {}
    tokens = _read_refresh_token(request, body if isinstance(body, dict) else {})
    payload, state = decode_session_tokens(tokens, expected_type="refresh")
    if payload is None:
        raise session_error(state)

    user = await db.users.find_one({"id": payload["sub"]}, {"_id": 0, "password_hash": 0})
    if not user:
        raise session_error(SESSION_REVOKED,
                            detail="Akun Anda tidak ditemukan lagi. Hubungi admin.")
    if not user.get("is_active", True):
        raise session_error(SESSION_REVOKED, status_code=403)
    user["home_org_id"] = user.get("org_id")
    await _tenant_gate(user)

    # Konteks "bertindak sebagai" dibaca dari token KERJA (bukan dari token refresh, yang
    # sengaja tidak membawa klaim peran/organisasi apa pun).
    prev = claims_ignoring_expiry(candidate_tokens(request), expected_type="access")
    active = prev.get("active_org_id") if user.get("role") == "super_admin" else None

    access = create_access_token(user["id"], user["email"], user["role"], active_org_id=active)
    response.set_cookie("access_token", access, httponly=True, secure=COOKIE_SECURE,
                        samesite=COOKIE_SAMESITE, max_age=ACCESS_MAX_AGE, path="/")
    renewal = "renewed"
    sisa = payload.get("exp", 0) - int(time.time())
    if sisa < REFRESH_TTL.total_seconds() / 2:
        response.set_cookie("refresh_token", create_refresh_token(user["id"]), httponly=True,
                            secure=COOKIE_SECURE, samesite=COOKIE_SAMESITE,
                            max_age=REFRESH_MAX_AGE, path="/")
        renewal = "slid"

    user = apply_org_context(user, {"active_org_id": active})
    return {"data": await session_payload(user), "access_token": access,
            "token_type": "bearer", "renewal": renewal}
