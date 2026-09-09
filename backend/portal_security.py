"""Portal auth: buyer-facing JWT (type='portal') separate from staff access tokens.

Uses the same JWT secret/algorithm but a distinct `type` claim so staff and portal
tokens can never be used interchangeably (staff endpoints require type='access').
"""
import jwt
from datetime import datetime, timezone, timedelta
from fastapi import Request, HTTPException

from db import db, ORG_ID
from security import get_jwt_secret, JWT_ALGORITHM


def create_portal_token(portal_user: dict) -> str:
    payload = {
        "sub": portal_user["id"],
        "cid": portal_user.get("customer_id"),
        "org_id": portal_user.get("org_id", ORG_ID),
        "type": "portal",
        "exp": datetime.now(timezone.utc) + timedelta(hours=12),
    }
    return jwt.encode(payload, get_jwt_secret(), algorithm=JWT_ALGORITHM)


def _extract_token(request: Request):
    """Kompatibilitas: kandidat pertama. Otentikasi memakai `_candidates()`."""
    c = _candidates(request)
    return c[0] if c else None


def _candidates(request: Request) -> list:
    """Bekal sesi portal — **header dulu**, lalu cookie, lalu parameter `?auth=`.

    ## Fase 54 — kelas cacat yang sama seperti sesi staf

    Dulu cookie `portal_token` dibaca LEBIH DULU dan header hanya dipakai bila cookie
    KOSONG. Akibatnya cookie yang ADA tapi KEDALUWARSA mengalahkan Bearer yang masih sah:
    pembeli yang membuka portal di peramban yang pernah dipakai 12 jam lalu ditolak walau
    aplikasinya baru saja menyerahkan token baru. Aturannya kini sama dengan
    `security.candidate_tokens()`: yang SENGAJA dikirim pemanggil menang atas yang
    dilampirkan peramban otomatis, dan penolakan hanya terjadi bila SEMUA kandidat gagal.

    `?auth=` tetap ada di urutan terakhir karena tautan PDF (`<a>`/`<iframe>`) tidak bisa
    membawa tajuk — itu jalur sah, bukan celah.
    """
    out = []
    header = request.headers.get("Authorization", "")
    if header.startswith("Bearer "):
        tok = header[7:].strip()
        if tok:
            out.append(tok)
    for extra in (request.cookies.get("portal_token"), request.query_params.get("auth")):
        if extra and extra not in out:
            out.append(extra)
    return out


async def get_portal_user(request: Request) -> dict:
    tokens = _candidates(request)
    if not tokens:
        raise HTTPException(status_code=401, detail="Anda belum masuk ke portal pembeli.",
                            headers={"X-Session-State": "missing"})
    payload, state = None, "invalid"
    for token in tokens:
        try:
            claims = jwt.decode(token, get_jwt_secret(), algorithms=[JWT_ALGORITHM])
        except jwt.ExpiredSignatureError:
            state = "expired"
            continue
        except jwt.InvalidTokenError:
            continue
        if claims.get("type") != "portal":
            # Token staf tidak boleh masuk portal pembeli dan sebaliknya — dua dunia terpisah.
            continue
        payload, state = claims, "active"
        break
    if payload is None:
        pesan = ("Sesi portal Anda sudah berakhir. Silakan masuk kembali dengan kode OTP."
                 if state == "expired" else
                 "Sesi portal Anda tidak dikenali. Silakan masuk kembali dengan kode OTP.")
        raise HTTPException(status_code=401, detail=pesan,
                            headers={"X-Session-State": state})
    pu = await db.portal_users.find_one({"id": payload["sub"]}, {"_id": 0})
    if not pu or not pu.get("is_active", True):
        raise HTTPException(status_code=401,
                            detail="Akses portal Anda sedang dinonaktifkan. Hubungi kami.",
                            headers={"X-Session-State": "revoked"})
    return pu
