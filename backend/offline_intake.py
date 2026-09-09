"""offline_intake — penerima kiriman ANTREAN PERANGKAT yang aman diputar ulang (Fase 50B).

Masalah nyata yang ditutup modul ini: antrean offline Fase 35 hanya aman untuk pengajuan
hasil kerja unit (`build_submit`/`build_start`) karena hanya endpoint itu yang mengenal
`client_ref`. Absensi harian, buku harian proyek, dan temuan punch list \u2014 tiga hal yang
paling sering dikerjakan di lokasi tanpa sinyal \u2014 TIDAK punya penanda itu. Akibatnya
satu-satunya cara "aman" adalah tidak mengantre: kalau sinyal hilang di tengah kiriman,
pemakai menekan ulang dan datanya masuk DUA KALI (absensi ganda = upah ganda), atau dia
tidak menekan ulang dan pekerjaan seharian HILANG tanpa jejak.

Aturan modul ini:
  1. Satu `client_ref` per (org, jenis) hanya boleh menghasilkan SATU dokumen. Kiriman kedua
     memutar ulang hasil lama (`replay=True`) \u2014 bukan menolak, karena pengirim ulang tidak
     bersalah: dia hanya tidak pernah menerima jawaban pertama.
  2. Kunci diambil SEBELUM data disentuh, sehingga dua tab/jendela yang mengirim bersamaan
     tidak sama-sama lolos pemeriksaan "sudah pernah diterima?".
  3. Kunci yang BASI (proses mati di tengah jalan) boleh diambil ulang \u2014 kalau tidak,
     antrean akan menganggap pekerjaan "sudah terkirim" padahal belum: kehilangan senyap.
  4. Bila server MENOLAK (mis. tanggal terkunci, foto wajib belum ada), kunci DILEPAS supaya
     pemakai bisa memperbaiki lalu mengirim ulang dengan penanda yang sama.
"""
import logging
from datetime import datetime, timezone

from pymongo.errors import DuplicateKeyError

from core_utils import now_iso
from db import db

logger = logging.getLogger("sipro.offline")

COLL = "offline_intake"
STALE_SECONDS = 120
# Jenis kiriman yang dikenal; labelnya hidup di SSOT `offline_queue_kind`.
KINDS = ("attendance_submit", "field_diary", "punch_create", "punch_status",
         "warranty_claim", "warranty_fix", "retention_release")


def _age_seconds(ts) -> float:
    try:
        if isinstance(ts, datetime):
            base = ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
        else:
            base = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - base).total_seconds()
    except Exception:  # noqa: BLE001 — cap waktu rusak jangan memblokir kiriman
        return STALE_SECONDS + 1


async def begin(org: str, kind: str, ref: str) -> dict:
    """Ambil kunci untuk `client_ref`.

    Jawaban:
      * `{"state": "new"}`      \u2014 silakan proses, lalu panggil `commit()`.
      * `{"state": "replay", "doc": {...}}` \u2014 sudah pernah diterima; kembalikan dokumen lama.
      * `{"state": "inflight"}` \u2014 pengirim lain sedang memproses penanda yang sama.
    """
    if not ref:
        return {"state": "new"}
    ref = str(ref).strip()
    now = datetime.now(timezone.utc)
    try:
        await db.offline_intake.insert_one({"org_id": org, "kind": kind, "client_ref": ref,
                                   "state": "processing", "at": now, "created_at": now_iso()})
        return {"state": "new"}
    except DuplicateKeyError:
        pass
    row = await db.offline_intake.find_one({"org_id": org, "kind": kind, "client_ref": ref})
    if row and row.get("state") == "done":
        doc = await stored(org, kind, ref)
        logger.info("antrean idempoten: %s/%s sudah diterima", kind, ref)
        return {"state": "replay", "doc": doc, "summary": row.get("summary")}
    if row and _age_seconds(row.get("at")) > STALE_SECONDS:
        await db.offline_intake.update_one({"_id": row["_id"]},
                                  {"$set": {"at": now, "state": "processing"}})
        return {"state": "new"}
    return {"state": "inflight"}


async def commit(org: str, kind: str, ref: str, *, collection: str, doc_id: str,
                 summary: dict = None) -> None:
    """Tandai penanda selesai + simpan ALAMAT dokumen hasilnya (bukan salinannya)."""
    if not ref:
        return
    await db.offline_intake.update_one(
        {"org_id": org, "kind": kind, "client_ref": str(ref).strip()},
        {"$set": {"state": "done", "collection": collection, "doc_id": doc_id,
                  "summary": summary or {}, "done_at": now_iso()}}, upsert=True)


async def rollback(org: str, kind: str, ref: str) -> None:
    """Lepas kunci supaya kiriman yang DITOLAK bisa diperbaiki lalu dikirim ulang."""
    if not ref:
        return
    await db.offline_intake.delete_one({"org_id": org, "kind": kind, "client_ref": str(ref).strip(),
                              "state": {"$ne": "done"}})


async def stored(org: str, kind: str, ref: str):
    """Dokumen hasil kiriman lama (None bila penanda belum pernah selesai)."""
    row = await db.offline_intake.find_one({"org_id": org, "kind": kind, "client_ref": str(ref).strip()},
                                  {"_id": 0})
    if not row or row.get("state") != "done" or not row.get("collection"):
        return None
    return await db[row["collection"]].find_one({"id": row.get("doc_id"), "org_id": org},
                                                {"_id": 0})
