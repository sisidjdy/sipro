"""KIRIM DOKUMEN KE PIHAK LUAR (Fase 62) — tautan berbatas waktu + pesan WhatsApp.

## Kenapa tautan, bukan "kirim WhatsApp otomatis"

Subkontraktor dan vendor tidak punya akun di sistem ini, sehingga SPK/PO selalu berpindah
lewat WhatsApp. Sampai Fase 61 caranya: unduh PDF, buka WhatsApp, cari kontaknya, kirim
berkas — empat langkah manual yang sering berhenti di langkah pertama.

Yang dibangun di sini adalah jalur yang JUJUR tanpa berpura-pura punya kredensial Meta:
sistem menerbitkan **tautan berbatas waktu** ke dokumen dan menyiapkan **pesan siap kirim**
(`wa.me`) berisi tautan itu. Yang menekan "kirim" tetap manusia dengan nomor WhatsApp
perusahaan, dan dokumen yang dibuka penerima selalu dirender ULANG dari data terkini —
jadi tidak ada berkas basi yang beredar sesudah nilainya berubah.

## Aturan yang dipegang

1. **Tautan berumur pendek & bisa dicabut.** `expires_at` (bawaan 14 hari) dan `revoked_at`.
   Tautan yang mati menjawab 404, bukan dokumen.
2. **Tautan tidak boleh berarti "boleh melihat segalanya".** Satu token = SATU dokumen.
3. **Hak menerbitkan = hak atas dokumennya**, ditegakkan router lewat `PERMISSION`.
4. **Setiap penerbitan & setiap pembukaan tercatat** (`opened_count`, `last_opened_at`)
   supaya bisa dijawab pertanyaan "sudah dibaca vendornya belum?".
"""
import logging
import secrets
from datetime import datetime, timedelta, timezone

import docgen_p61 as p61
import docgen_p62 as p62
from core_utils import new_id, now_iso
from db import db

logger = logging.getLogger("sipro.doc_share")

TTL_DAYS = 14

# Dokumen yang boleh dibagikan + izin yang wajib dimiliki penerbit tautannya.
PERMISSION = {
    "spk": ("subcon", "update"),
    "po": ("procurement", "create"),
    "warning_letter": ("late_fee", "create"),
    "claim": ("progress_claims", "update"),
}

LABEL = {"spk": "SPK", "po": "Purchase Order", "warning_letter": "Surat Peringatan",
         "claim": "Berita Acara Opname"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _phone_digits(phone: str) -> str:
    """Nomor untuk `wa.me`: hanya angka, awalan 0 diganti kode negara Indonesia."""
    digits = "".join(c for c in str(phone or "") if c.isdigit())
    if digits.startswith("0"):
        digits = "62" + digits[1:]
    if digits.startswith("620"):
        digits = "62" + digits[3:]
    return digits


def wa_url(phone: str, text: str) -> str:
    from urllib.parse import quote
    nomor = _phone_digits(phone)
    return f"https://wa.me/{nomor}?text={quote(text)}" if nomor \
        else f"https://wa.me/?text={quote(text)}"


async def _subject(org: str, kind: str, doc_id: str) -> dict:
    """Dokumen + penerima (nama & nomor WhatsApp) — nomornya dari master, bukan diketik."""
    if kind == "spk":
        spk = await db.spk.find_one({"id": doc_id, "org_id": org}, {"_id": 0})
        if not spk:
            return {}
        sub = await db.subcontractors.find_one(
            {"id": spk.get("subcontractor_id"), "org_id": org},
            {"_id": 0, "phone": 1, "pic_name": 1}) or {}
        return {"doc": spk, "number": spk.get("spk_number"), "project_id": spk.get("project_id"),
                "to_name": spk.get("subcontractor_name"), "to_phone": sub.get("phone"),
                "pic": sub.get("pic_name")}
    if kind == "po":
        po = await db.purchase_orders.find_one({"id": doc_id, "org_id": org}, {"_id": 0})
        if not po:
            return {}
        # Nama pada PO bisa merujuk vendor material MAUPUN subkontraktor (PO subkon), dan
        # sebagian data lama menyimpan KODE vendor. Ketiganya dicoba supaya nomor WhatsApp
        # penerima benar-benar terisi, bukan memaksa penagih mencari kontaknya sendiri.
        nama = po.get("vendor") or po.get("subcontractor_name")
        rekanan = await db.vendors.find_one(
            {"org_id": org, "$or": [{"name": nama}, {"code": nama}]},
            {"_id": 0, "phone": 1, "pic_name": 1})
        if not rekanan and po.get("spk_id"):
            spk = await db.spk.find_one({"id": po["spk_id"], "org_id": org},
                                        {"_id": 0, "subcontractor_id": 1}) or {}
            rekanan = await db.subcontractors.find_one(
                {"id": spk.get("subcontractor_id"), "org_id": org},
                {"_id": 0, "phone": 1, "pic_name": 1})
        if not rekanan:
            rekanan = await db.subcontractors.find_one(
                {"org_id": org, "$or": [{"name": nama}, {"code": nama}]},
                {"_id": 0, "phone": 1, "pic_name": 1})
        rekanan = rekanan or {}
        return {"doc": po, "number": po.get("po_number"), "project_id": po.get("project_id"),
                "to_name": nama, "to_phone": rekanan.get("phone"),
                "pic": rekanan.get("pic_name")}
    if kind == "warning_letter":
        wl = await db.warning_letters.find_one({"id": doc_id, "org_id": org}, {"_id": 0})
        if not wl:
            return {}
        return {"doc": wl, "number": wl.get("number"), "project_id": None,
                "to_name": wl.get("buyer_name"), "to_phone": wl.get("buyer_phone")}
    if kind == "claim":
        claim = await db.progress_claims.find_one({"id": doc_id, "org_id": org}, {"_id": 0})
        if not claim:
            return {}
        spk = await db.spk.find_one({"id": claim.get("spk_id"), "org_id": org},
                                    {"_id": 0}) or {}
        sub = await db.subcontractors.find_one(
            {"id": spk.get("subcontractor_id"), "org_id": org}, {"_id": 0, "phone": 1}) or {}
        return {"doc": claim, "number": claim.get("claim_number"),
                "project_id": claim.get("project_id"),
                "to_name": spk.get("subcontractor_name"), "to_phone": sub.get("phone")}
    return {}


def _message(kind: str, number: str, to_name: str, url: str, org_name: str) -> str:
    judul = LABEL.get(kind, "Dokumen")
    sapaan = f"Kepada {to_name}," if to_name else "Selamat siang,"
    inti = {
        "spk": "Berikut Surat Perintah Kerja untuk pekerjaan Bapak/Ibu. Mohon dibaca, "
               "ditandatangani, dan dikirimkan kembali sebelum pekerjaan dimulai.",
        "po": "Berikut Purchase Order dari kami. Mohon pengiriman barang sesuai jenis, "
              "jumlah, dan spesifikasi pada dokumen; tagihan wajib menyebut nomor PO ini.",
        "warning_letter": "Berikut surat mengenai kewajiban pembayaran unit Bapak/Ibu. "
                          "Mohon diperiksa dan dihubungi kembali bila perlu penjadwalan.",
        "claim": "Berikut berita acara hasil opname pekerjaan. Mohon diperiksa dan "
                 "ditandatangani sebagai dasar penagihan termin.",
    }[kind]
    return (f"{sapaan}\n\n{inti}\n\n{judul} {number}\n{url}\n\n"
            f"Tautan berlaku {TTL_DAYS} hari.\n{org_name}")


async def create(org: str, kind: str, doc_id: str, *, actor: str, base_url: str,
                 org_name: str) -> dict:
    if kind not in PERMISSION:
        raise ValueError("Jenis dokumen ini belum bisa dikirim ke pihak luar.")
    subject = await _subject(org, kind, doc_id)
    if not subject:
        raise LookupError("Dokumen tidak ditemukan.")
    ts = now_iso()
    token = secrets.token_urlsafe(24)
    doc = {
        "id": new_id(), "org_id": org, "kind": kind, "doc_id": doc_id,
        "doc_number": subject.get("number"), "project_id": subject.get("project_id"),
        "token": token, "to_name": subject.get("to_name"),
        "to_phone": subject.get("to_phone"), "issuer_name": actor,
        "expires_at": (_now() + timedelta(days=TTL_DAYS)).isoformat(),
        "revoked_at": None, "opened_count": 0, "last_opened_at": None,
        "created_by": actor, "created_at": ts,
    }
    await db.doc_shares.insert_one(dict(doc))
    doc.pop("_id", None)
    url = f"{base_url.rstrip('/')}/api/public/docs/{token}"
    pesan = _message(kind, subject.get("number") or "-", subject.get("to_name"), url,
                     org_name)
    logger.info("Tautan %s %s dibuat oleh %s", kind, subject.get("number"), actor)
    return {**doc, "url": url, "message": pesan,
            "wa_url": wa_url(subject.get("to_phone"), pesan),
            "phone_known": bool(subject.get("to_phone"))}


async def resolve(token: str) -> dict:
    share = await db.doc_shares.find_one({"token": token}, {"_id": 0})
    if not share or share.get("revoked_at"):
        return {}
    if str(share.get("expires_at") or "") < _now().isoformat():
        return {}
    return share


async def render(share: dict) -> tuple:
    """Render ULANG dokumen dari data terkini — tautan tidak menyimpan berkas basi."""
    org, kind, doc_id = share["org_id"], share["kind"], share["doc_id"]
    issuer = {"name": share.get("issuer_name"), "role": ""}
    subject = await _subject(org, kind, doc_id)
    if not subject:
        return None, None
    doc = subject["doc"]
    if kind == "spk":
        pdf = await p61.spk_pdf(org, doc, issuer)
    elif kind == "po":
        pdf = await p61.po_pdf(org, doc, issuer)
    elif kind == "warning_letter":
        pdf = await p62.sp_pdf(org, doc, issuer)
    else:
        spk = await db.spk.find_one({"id": doc.get("spk_id"), "org_id": org}, {"_id": 0}) or {}
        pdf = await p62.ba_pdf(org, doc, spk, issuer)
    nama = str(subject.get("number") or kind).replace("/", "-")
    await db.doc_shares.update_one(
        {"id": share["id"]}, {"$inc": {"opened_count": 1},
                              "$set": {"last_opened_at": now_iso()}})
    return pdf, nama


async def history(org: str, *, kind: str = None, doc_id: str = None) -> list:
    q = {"org_id": org}
    if kind:
        q["kind"] = kind
    if doc_id:
        q["doc_id"] = doc_id
    return await db.doc_shares.find(q, {"_id": 0, "token": 0}).sort(
        "created_at", -1).to_list(200)


async def ensure_indexes() -> None:
    await db.doc_shares.create_index("token", unique=True, name="doc_share_token")
    await db.doc_shares.create_index([("org_id", 1), ("kind", 1), ("doc_id", 1)])
