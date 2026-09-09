"""PREFERENSI NOTIFIKASI PER PEMAKAI (Fase 65).

## Cacat yang ditutup berkas ini

Fase 64 membuat pusat notifikasi bisa HABIS, tetapi semua orang masih menerima hal yang
SAMA: seorang site engineer tetap dibanjiri kabar keuangan, dan seorang kasir tetap
menerima kabar proyek yang bukan pekerjaannya. Satu-satunya cara membungkam adalah
berhenti membaca notifikasi sama sekali — persis kebiasaan yang ingin kita hilangkan.

## Aturan yang dipegang (dan yang SENGAJA tidak boleh dilanggar pemakai)

* Tiga saluran per kategori:
  - `inapp` — masuk daftar notifikasi & lonceng;
  - `push`  — dorongan seketika (WebSocket/toast) saat kejadiannya terjadi;
  - `wa`    — ikut **ringkasan WhatsApp** yang disiapkan untuk dikirim manual
              (pola Fase 62: sistem menyiapkan pesan, manusia yang menekan kirim).
* **Notifikasi yang MENUNTUT TINDAKAN tidak bisa dibungkam dari daftar.** Kalau seseorang
  boleh mematikan "kas bon menunggu persetujuan", persetujuan akan menggantung tanpa ada
  yang tahu penyebabnya. Yang bisa dimatikan untuk kategori itu hanyalah `push` — jadi
  layarnya tidak berdenting, tetapi pekerjaannya tetap tercatat.
* Notifikasi yang dibungkam TIDAK dibuang tanpa jejak: barisnya tetap ditulis dengan
  `muted_at` + `muted_reason` (dan disembunyikan dari daftar), sehingga bila seseorang
  bertanya "kenapa saya tidak diberi tahu?", jawabannya ada di data.
"""
import logging

from core_utils import new_id, now_iso
from db import db, ORG_ID
from notif_center import CATEGORIES, category_of, needs_action

logger = logging.getLogger("sipro.notif_prefs")

CHANNELS = ("inapp", "push", "wa")
# Bawaan: masuk daftar + berdenting, tetapi TIDAK otomatis masuk ringkasan WhatsApp
# (WhatsApp dikirim manusia — jangan menyiapkan pesan yang tidak diminta siapa pun).
DEFAULT_CHANNEL = {"inapp": True, "push": True, "wa": False}
# Saluran yang tidak bisa dimatikan untuk notifikasi yang menuntut tindakan.
LOCKED_CHANNELS = ("inapp",)
LOCK_REASON = ("Notifikasi yang menuntut tindakan selalu masuk daftar — yang bisa "
               "dimatikan hanya dorongan seketika (push).")


def defaults() -> dict:
    return {k: dict(DEFAULT_CHANNEL) for k in CATEGORIES}


def _merge(stored: dict) -> dict:
    out = defaults()
    for kat, ch in (stored or {}).items():
        if kat in out and isinstance(ch, dict):
            out[kat].update({c: bool(v) for c, v in ch.items() if c in CHANNELS})
    return out


async def get_prefs(org: str, email: str) -> dict:
    doc = await db.notification_prefs.find_one(
        {"org_id": org, "user_email": email}, {"_id": 0})
    return {
        "user_email": email,
        "channels": _merge((doc or {}).get("channels")),
        "locked_channels": list(LOCKED_CHANNELS),
        "locked_reason": LOCK_REASON,
        "updated_at": (doc or {}).get("updated_at"),
        "is_default": doc is None,
    }


async def set_prefs(org: str, email: str, patch: dict) -> dict:
    """Simpan sebagian preferensi. Kategori/saluran asing DITOLAK (bukan diabaikan)."""
    salah = [f"{k}.{c}" for k, ch in (patch or {}).items()
             for c in (ch or {}) if k not in CATEGORIES or c not in CHANNELS]
    if salah:
        raise ValueError(f"Kategori/saluran notifikasi tidak dikenal: {', '.join(salah)}.")
    now = await get_prefs(org, email)
    channels = now["channels"]
    for kat, ch in (patch or {}).items():
        channels[kat].update({c: bool(v) for c, v in (ch or {}).items()})
    await db.notification_prefs.update_one(
        {"org_id": org, "user_email": email},
        {"$set": {"channels": channels, "updated_at": now_iso()},
         "$setOnInsert": {"id": new_id(), "org_id": org, "user_email": email}},
        upsert=True)
    return await get_prefs(org, email)


async def channels_for(org: str, email: str, notif: dict) -> dict:
    """Saluran yang BOLEH dipakai untuk satu notifikasi (sesudah aturan kunci diterapkan)."""
    prefs = await get_prefs(org, email)
    kat = category_of(notif)
    izin = dict(prefs["channels"].get(kat) or DEFAULT_CHANNEL)
    if needs_action(notif):
        for c in LOCKED_CHANNELS:
            izin[c] = True
    return {**izin, "category": kat}


def mute_patch(category: str) -> dict:
    """Penanda untuk notifikasi yang dibungkam preferensi — jejaknya tetap ada."""
    ts = now_iso()
    return {"muted_at": ts, "read": True, "read_at": ts, "dismissed_at": ts,
            "muted_reason": f"preferensi pemakai: kategori '{category}' dimatikan"}


# ------------------------------------------------------- ringkasan WhatsApp (manual)
async def wa_digest(org: str, email: str, limit: int = 15) -> dict:
    """Susun pesan ringkas untuk kategori yang dizinkan lewat WhatsApp.

    Tidak ada pengiriman otomatis di sini (kredensial WhatsApp perusahaan bukan milik
    sistem): yang dikembalikan adalah teks + tautan `wa.me` supaya pemakai menekan kirim
    sendiri, sama seperti pengiriman dokumen Fase 62.
    """
    prefs = await get_prefs(org, email)
    kat_wa = [k for k, ch in prefs["channels"].items() if ch.get("wa")]
    if not kat_wa:
        return {"categories": [], "count": 0, "text": "",
                "message": "Belum ada kategori yang diizinkan lewat WhatsApp."}
    rows = await db.notifications.find(
        {"org_id": org, "user_email": email, "dismissed_at": None, "resolved_at": None,
         "read": False}, {"_id": 0}).sort("created_at", -1).limit(300).to_list(300)
    pilih = [r for r in rows if category_of(r) in kat_wa and needs_action(r)][:limit]
    user = await db.users.find_one({"org_id": org, "email": email},
                                  {"_id": 0, "name": 1, "phone": 1})
    baris = [f"{i}. {r.get('title')}" + (f" — {(r.get('body') or '')[:80]}"
                                         if r.get("body") else "")
             for i, r in enumerate(pilih, 1)]
    teks = (f"*SIPRO — {len(pilih)} hal yang perlu ditindak*\n"
            f"Untuk: {(user or {}).get('name') or email}\n\n" + "\n".join(baris)
            ) if pilih else ""
    telepon = ((user or {}).get("phone") or "").replace("+", "").replace(" ", "")
    from urllib.parse import quote
    return {
        "categories": kat_wa, "count": len(pilih), "text": teks,
        "wa_link": (f"https://wa.me/{telepon}?text={quote(teks)}"
                    if telepon and teks else ""),
        "phone": (user or {}).get("phone"),
        "message": ("Tidak ada yang perlu ditindak pada kategori yang diizinkan."
                    if not pilih else
                    ("Nomor WhatsApp Anda belum tercatat — salin teksnya secara manual."
                     if not telepon else "Siap dikirim.")),
    }
