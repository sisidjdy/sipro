#!/usr/bin/env python3
"""_fixture54.py — bahan uji & pembersih Fase 54 (ketahanan sesi).

## Kenapa berkas ini ada

POC dan gate Fase 54 harus membuktikan hal-hal yang TIDAK BISA dibuktikan dengan akun demo
biasa:

  * "organisasi disuspend tidak boleh memperpanjang sesi" — menyuspend `org-sipro` berarti
    mematikan seluruh data demo, jadi harus ada organisasi SEMENTARA berikut ownernya;
  * "akun dinonaktifkan tidak boleh memperpanjang sesi" — menonaktifkan `sales@sipro.co.id`
    milik seed akan merusak gate lain yang memakainya.

Aturan repo: gate & POC tidak boleh meninggalkan jejak. Berkas ini yang menepatinya.

## Cacat yang pernah ada di pembersih INI (dan pelajarannya)

Versi pertama hanya membuang `orgs` + `users` + beberapa koleksi yang ditebak. Ternyata
membuat satu organisasi baru **melahirkan bagan akun (31 baris `accounts`)** lewat
`gl_engine.ensure_coa(org_id)` — yang tidak ada dalam daftar tebakan itu. Akibatnya, sesudah
satu putaran uji-mutasi (36 mutan, masing-masing membuat penyewa sementara),
`scripts/forensic_audit.py` melaporkan **31 temuan CRITICAL** `accounts.<id> -> org_id=... tidak
ada di orgs` dan seluruh rangkaian gate menjadi MERAH karena jejak perangkat uji.

Pelajarannya: **jangan menebak koleksi.** Sekarang pembersih ini menyapu SEMUA koleksi yang
punya `org_id`, dan ditutup `sweep_orphans()` yang membuang dokumen yang menunjuk organisasi
yang sudah tidak ada — supaya database yang sudah tercemar bisa DISEMBUHKAN, bukan hanya
dicegah.

Pakai:
    python3 scripts/_fixture54.py --periksa      # laporkan apa yang akan dibuang
    python3 scripts/_fixture54.py                # bersihkan
    python3 scripts/_fixture54.py --sapu-yatim   # hanya sapu dokumen milik organisasi yatim
"""
import os
import sys

from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv("/app/backend/.env")

# Penanda bahan uji. Sengaja mencolok supaya kalau pernah bocor ke layar, manusia langsung
# tahu itu bahan uji dan bukan penyewa sungguhan.
#
# CATATAN domain: JANGAN pakai `.invalid`/`.test`/`.example`/`.localhost`. `LoginRequest`
# memakai `EmailStr`, dan email-validator menolak domain "special-use" itu — organisasinya
# terbuat (endpoint `POST /admin/orgs` hanya memeriksa ada "@") tetapi ownernya TIDAK BISA
# login, sehingga uji gerbang perpanjangan mati sebelum mulai.
ORG_NAME_PREFIX = "ZZ Uji Sesi F54"
USER_EMAIL_SUFFIX = "@ujisesif54.co.id"

# Organisasi yang HARUS selalu ada; jangan pernah ikut tersapu.
ORG_INTI = ("org-sipro", "org-nusa")


def _db():
    return MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def _koleksi_ber_org(db) -> list:
    """Semua koleksi yang memuat dokumen ber-`org_id` — dibaca dari KENYATAAN, bukan ditebak."""
    out = []
    for name in db.list_collection_names():
        if name == "orgs":
            continue
        if db[name].find_one({"org_id": {"$exists": True}}, {"_id": 1}):
            out.append(name)
    return out


def sweep_orphans(dry: bool = False) -> dict:
    """Buang dokumen yang menunjuk organisasi yang SUDAH TIDAK ADA.

    Rujukan `org_id` ke organisasi yang tidak ada selalu salah — itu tepat yang dicari
    `scripts/forensic_audit.py` sebagai temuan CRITICAL. Menyapunya di sini membuat database
    yang tercemar run lama bisa disembuhkan tanpa menghapus data yang sah.
    """
    db = _db()
    hidup = {o["id"] for o in db.orgs.find({}, {"_id": 0, "id": 1})} | set(ORG_INTI)
    hasil = {}
    for name in _koleksi_ber_org(db):
        yatim = [d["_id"] for d in db[name].find({"org_id": {"$nin": list(hidup)}}, {"_id": 1})]
        if not yatim:
            continue
        hasil[name] = len(yatim)
        if not dry:
            db[name].delete_many({"_id": {"$in": yatim}})
    return hasil


def purge(dry: bool = False) -> dict:
    db = _db()
    orgs = [o["id"] for o in db.orgs.find(
        {"name": {"$regex": f"^{ORG_NAME_PREFIX}"}}, {"_id": 0, "id": 1})
        if o["id"] not in ORG_INTI]
    users = [u["id"] for u in db.users.find(
        {"email": {"$regex": USER_EMAIL_SUFFIX.replace(".", r"\.") + "$"}},
        {"_id": 0, "id": 1})]
    hasil = {"orgs": len(orgs), "users": len(users)}
    if dry:
        # Dalam mode periksa, laporkan juga yang yatim supaya "sisa" tidak pernah tersembunyi.
        yatim = sweep_orphans(dry=True)
        if yatim:
            hasil["yatim"] = yatim
        return hasil
    if orgs:
        # SEMUA koleksi ber-org_id, bukan daftar tebakan: membuat satu organisasi bisa
        # melahirkan baris di koleksi yang tidak pernah kita sangka (mis. `accounts` lewat
        # `gl_engine.ensure_coa`).
        for name in _koleksi_ber_org(db):
            db[name].delete_many({"org_id": {"$in": orgs}})
        db.orgs.delete_many({"id": {"$in": orgs}})
    if users:
        db.users.delete_many({"id": {"$in": users}})
        db.audit_logs.delete_many({"actor_id": {"$in": users}})
    # Selalu ditutup dengan menyapu yatim: jejak dari run VERSI LAMA tetap jejak.
    yatim = sweep_orphans()
    if yatim:
        hasil["yatim"] = yatim
    return hasil


def main() -> int:
    dry = "--periksa" in sys.argv
    if "--sapu-yatim" in sys.argv:
        print(f"Dokumen organisasi yatim {'AKAN disapu' if dry else 'disapu'}: "
              f"{sweep_orphans(dry=dry)}")
        return 0
    hasil = purge(dry=dry)
    print(f"Bahan uji Fase 54 {'AKAN dibuang' if dry else 'dibuang'}: {hasil}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
