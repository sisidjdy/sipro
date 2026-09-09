"""KEBIJAKAN BUKTI KERJA (Fase 32) — satu tempat aturan bukti, bisa diatur admin.

Permintaan owner: foto diambil langsung dari lokasi, **lokasi (GPS) bisa dinyalakan /
dimatikan oleh admin**. Karena itu aturannya TIDAK di-hardcode di UI maupun router,
melainkan satu dokumen kebijakan per organisasi yang dibaca semua jalur submit.

Catatan privasi yang jujur: pipeline foto SIPRO membuang metadata EXIF/GPS pada berkas
(agar berkas yang dibagikan tidak membocorkan lokasi rumah pembeli). Jadi koordinat
TIDAK diambil dari EXIF, melainkan dikirim eksplisit oleh aplikasi saat pengambilan foto
dan disimpan sebagai field terstruktur pada bukti pekerjaan — terlihat jelas, bisa
diaudit, dan bisa dimatikan.
"""
from core_utils import now_iso
from db import db, ORG_ID

COLLECTION = "build_policies"

DEFAULTS = {
    "geo_required": False,      # wajib rekam koordinat saat mengajukan hasil kerja
    "camera_only": False,       # hanya boleh kamera (bukan pilih dari galeri)
    "min_note_chars": 10,       # panjang minimal uraian pekerjaan
    "min_accuracy_m": 200,      # akurasi GPS maksimal yang masih diterima (meter)
}
FIELDS = tuple(DEFAULTS.keys())


async def get_policy(org: str = ORG_ID) -> dict:
    doc = await db.build_policies.find_one({"org_id": org}, {"_id": 0}) or {}
    out = dict(DEFAULTS)
    for k in FIELDS:
        if doc.get(k) is not None:
            out[k] = doc[k]
    out["updated_by"] = doc.get("updated_by")
    out["updated_at"] = doc.get("updated_at")
    return out


async def set_policy(org: str, data: dict, actor: str) -> dict:
    payload = {k: data[k] for k in FIELDS if k in data and data[k] is not None}
    payload.update({"org_id": org, "updated_by": actor, "updated_at": now_iso()})
    await db.build_policies.update_one({"org_id": org}, {"$set": payload}, upsert=True)
    return await get_policy(org)


def check_note(policy: dict, note: str):
    need = int(policy.get("min_note_chars") or 0)
    if len((note or "").strip()) < need:
        raise ValueError(f"Uraian pekerjaan minimal {need} karakter — tulis apa yang "
                         "benar-benar dikerjakan agar bisa diperiksa supervisor.")


def check_geo(policy: dict, geo) -> dict:
    """Terjemahkan kebijakan GPS menjadi keputusan + pesan manusiawi."""
    doc = geo_doc(geo)
    if not policy.get("geo_required"):
        return doc
    if not doc:
        raise ValueError(
            "Kebijakan perusahaan: pengajuan hasil kerja wajib merekam LOKASI. "
            "Izinkan akses lokasi pada peramban/HP lalu ajukan ulang, atau minta admin "
            "mematikan kewajiban lokasi di Master Data → Kebijakan Bukti Kerja.")
    limit = int(policy.get("min_accuracy_m") or 0)
    acc = doc.get("accuracy")
    if limit and acc and float(acc) > limit:
        raise ValueError(f"Akurasi lokasi {int(float(acc))} m terlalu kasar (maksimal "
                         f"{limit} m). Keluar ke area terbuka lalu coba lagi.")
    return doc


def geo_doc(geo) -> dict:
    """Normalkan koordinat menjadi dokumen kecil yang jelas (atau None bila tidak ada)."""
    if not geo:
        return None
    data = geo if isinstance(geo, dict) else geo.model_dump()
    if data.get("lat") is None or data.get("lng") is None:
        return None
    return {
        "lat": round(float(data["lat"]), 6), "lng": round(float(data["lng"]), 6),
        "accuracy": (round(float(data["accuracy"]), 1)
                     if data.get("accuracy") is not None else None),
        "captured_at": data.get("captured_at") or now_iso(),
        "maps_url": (f"https://maps.google.com/?q={round(float(data['lat']), 6)},"
                     f"{round(float(data['lng']), 6)}"),
    }
