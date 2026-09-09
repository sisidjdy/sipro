#!/usr/bin/env python3
"""_token54.py — terbitkan token sesi BUATAN untuk menguji Fase 54 tanpa menunggu 24 jam.

## Kenapa alat ini ada

Keadaan yang paling perlu diuji pada ketahanan sesi — "token kerja sudah kedaluwarsa" —
secara alami baru terjadi 24 jam sesudah masuk. Menunggu sehari untuk satu pemeriksaan
manual tidak masuk akal, dan mengecilkan `ACCESS_TTL` demi pengujian berarti menguji
aplikasi yang berbeda dari yang dipakai orang.

Alat ini menandatangani token dengan `JWT_SECRET` yang SAMA dengan milik server, jadi token
yang dihasilkan IDENTIK dengan yang akan diterbitkan server pada detik itu. Yang dipalsukan
hanyalah WAKTU — bukan kewenangan. Ia tidak bisa dipakai memberi hak yang tidak dimiliki
akunnya, karena peran tetap dibaca dari baris pengguna di database.

## Cara pakai (uji manual di peramban)

    python3 scripts/_token54.py                          # token superadmin, kedaluwarsa 5 menit
    python3 scripts/_token54.py --email=sales@sipro.co.id
    python3 scripts/_token54.py --detik=60               # masih SAH 60 detik (uji spanduk)
    python3 scripts/_token54.py --jenis=refresh --detik=-10   # bekal refresh kedaluwarsa

Lalu di console peramban:

    localStorage.setItem('sipro_token', '<token>')

dan muat ulang salah satu halaman DALAM (mis. `/leads`).

HARAPAN: halaman TETAP TERMUAT — sesi diperpanjang diam-diam. Untuk menguji sesi yang
BENAR-BENAR mati, hapus cookie situs lebih dulu (bekal perpanjangan ada di cookie
`refresh_token` yang `httponly`).
"""
import os
import sys
from datetime import datetime, timedelta, timezone

import jwt
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv("/app/backend/.env")


def arg(nama: str, bawaan: str) -> str:
    for a in sys.argv[1:]:
        if a.startswith(f"--{nama}="):
            return a.split("=", 1)[1]
    return bawaan


def main() -> int:
    email = arg("email", "superadmin@sipro.co.id")
    jenis = arg("jenis", "access")
    detik = int(arg("detik", "-300"))
    db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    u = db.users.find_one({"email": email})
    if not u:
        print(f"Pengguna {email} tidak ada.")
        return 1
    payload = {"sub": u["id"], "type": jenis,
               "exp": datetime.now(timezone.utc) + timedelta(seconds=detik)}
    if jenis == "access":
        payload.update({"email": u["email"], "role": u["role"]})
    print(jwt.encode(payload, os.environ["JWT_SECRET"], algorithm="HS256"))
    sisa = "KEDALUWARSA" if detik < 0 else f"masih sah {detik}s"
    print(f"# {email} · jenis={jenis} · {sisa}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
