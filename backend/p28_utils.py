"""Utilitas Fase 28b — foto lapangan, umur listing, dan payload peta publik.

Dipakai bersama oleh `site_plan_router` (staf), `portal_router` (pembeli) dan
`public_router` (showroom tanpa login) supaya SATU logika saja yang menentukan:
  * bagaimana sebuah foto dirujuk (file di object storage vs data URL warisan),
  * berapa lama sebuah kavling sudah dipasarkan (days on market),
  * data apa yang layak keluar ke publik (tanpa identitas pembeli).
"""
from datetime import datetime, timezone

from db import db

PHOTO_LIMIT = 12


def photo_ref(value, *, label: str, date, scope: str) -> dict:
    """Bentuk rujukan foto yang bisa dirender browser.

    Nilai tersimpan bisa dua macam (jujur, tanpa migrasi paksa):
      * **file_id** — foto nyata di object storage → dirender via `/api/files/{id}`.
      * **data URL** base64 — warisan klien lama → dipakai langsung sebagai `src`.
    Bug yang diperbaiki: sebelumnya data URL dikirim sebagai `file_id` sehingga
    `<img src="/api/files/data:image/png;base64,...">` selalu 404 (gambar rusak).
    """
    v = str(value or "").strip()
    ref = {"label": (label or "Dokumentasi lapangan")[:90], "date": date, "scope": scope}
    if v.startswith("data:"):
        ref["inline"] = v
        ref["file_id"] = None
    else:
        ref["file_id"] = v
        ref["inline"] = None
    return ref


def _photo_values(doc: dict, *fields) -> list:
    """Kumpulkan nilai foto dari field tunggal lama + daftar baru, tanpa duplikat."""
    out, seen = [], set()
    for f in fields:
        val = doc.get(f)
        vals = val if isinstance(val, list) else [val]
        for v in vals:
            s = str(v or "").strip()
            if not s or s in ("None", "null") or s in seen:
                continue
            seen.add(s)
            out.append(s)
    return out


async def collect_unit_photos(org: str, project_id: str, unit_id: str = None,
                             limit: int = 8) -> list:
    """Foto progres untuk satu kavling: temuan punch pada unit + buku harian proyek.

    Cakupan setiap foto ditandai jujur (`scope`): "unit" bila melekat pada kavling
    tersebut, "proyek" bila dokumentasi lapangan umum — supaya pembeli tidak salah
    menyimpulkan bahwa foto proyek adalah foto rumahnya.
    """
    photos = []
    if unit_id:
        punch = await db.punch_items.find(
            {"org_id": org, "unit_id": unit_id},
            {"_id": 0, "title": 1, "photo": 1, "photos": 1, "fix_photos": 1,
             "created_at": 1, "updated_at": 1}).sort("created_at", -1).to_list(50)
        for p in punch:
            title = p.get("title") or "Temuan punch list"
            for v in _photo_values(p, "photo", "photos"):
                photos.append(photo_ref(v, label=title, date=p.get("created_at"), scope="unit"))
            for v in _photo_values(p, "fix_photos"):
                photos.append(photo_ref(v, label=f"Perbaikan: {title}",
                                        date=p.get("updated_at"), scope="unit"))
    diaries = await db.site_diaries.find(
        {"org_id": org, "project_id": project_id,
         "$or": [{"photo": {"$nin": [None, "", "None"]}}, {"photos": {"$ne": []}}]},
        {"_id": 0, "photo": 1, "photos": 1, "work_description": 1, "log_date": 1}
    ).sort("log_date", -1).to_list(PHOTO_LIMIT)
    for d in diaries:
        label = d.get("work_description") or "Buku harian lapangan"
        for v in _photo_values(d, "photo", "photos"):
            photos.append(photo_ref(v, label=label, date=d.get("log_date"), scope="proyek"))
    photos.sort(key=lambda x: str(x.get("date") or ""), reverse=True)
    return photos[:limit]


async def collect_repair_pairs(org: str, unit_id: str, limit: int = 6) -> list:
    """Pasangan bukti kerja per temuan: FOTO SEBELUM (temuan) → FOTO SESUDAH (perbaikan).

    Kenapa dipisah dari `collect_unit_photos`? Galeri rata hanya memperlihatkan tumpukan
    foto; pembeli tidak bisa tahu foto mana "sebelum" dan mana "sesudah" untuk temuan yang
    sama. Di sini setiap temuan menjadi SATU kartu berpasangan, dan statusnya dinyatakan
    jujur: `resolved` hanya true bila temuan sudah ditutup/diverifikasi DAN ada foto sesudah.
    Temuan yang masih ditangani tetap ditampilkan (tanpa foto sesudah) agar tidak
    memberi kesan semua sudah beres.
    """
    if not unit_id:
        return []
    rows = await db.punch_items.find(
        {"org_id": org, "unit_id": unit_id},
        {"_id": 0, "id": 1, "title": 1, "severity": 1, "status": 1, "photo": 1, "photos": 1,
         "fix_photos": 1, "fix_note": 1, "created_at": 1, "updated_at": 1, "closed_at": 1}
    ).sort("created_at", -1).to_list(50)
    pairs = []
    for p in rows:
        before_vals = _photo_values(p, "photo", "photos")
        after_vals = _photo_values(p, "fix_photos")
        if not before_vals and not after_vals:
            continue
        title = p.get("title") or "Temuan punch list"
        closed = p.get("status") in ("closed", "verified")
        pairs.append({
            "punch_id": p["id"], "title": title, "severity": p.get("severity"),
            "status": p.get("status"), "resolved": bool(closed and after_vals),
            "note": p.get("fix_note"),
            "opened_at": p.get("created_at"),
            "fixed_at": p.get("closed_at") or (p.get("updated_at") if closed else None),
            "before": [photo_ref(v, label=f"Sebelum: {title}", date=p.get("created_at"),
                                 scope="unit") for v in before_vals],
            "after": [photo_ref(v, label=f"Sesudah: {title}",
                                date=p.get("closed_at") or p.get("updated_at"),
                                scope="unit") for v in after_vals],
        })
    # Bukti yang sudah tuntas ditaruh lebih dulu (itu yang paling meyakinkan pembeli),
    # temuan yang masih berjalan tetap ikut di bawahnya.
    pairs.sort(key=lambda x: (not x["resolved"], str(x.get("fixed_at") or "")), reverse=False)
    return pairs[:limit]


def _parse(ts) -> datetime:
    if isinstance(ts, datetime):
        return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
    try:
        d = datetime.fromisoformat(str(ts))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def days_on_market(unit: dict, deal_created_at=None) -> dict:
    """Lama kavling dipasarkan.

    * Kavling tersedia/reserved → umur listing sampai HARI INI (`open=True`).
    * Kavling booked/terjual → lama waktu sampai laku (start → tanggal deal).
    Mengembalikan `{days, open}`; `days=None` bila tanggal awal tidak diketahui
    (jujur: tidak menebak angka).
    """
    start = _parse(unit.get("available_since") or unit.get("created_at"))
    if not start:
        return {"days": None, "open": True}
    closed = unit.get("status") in ("booked", "sold")
    end = _parse(deal_created_at) if closed else None
    if closed and not end:
        end = _parse(unit.get("updated_at"))
    end = end or datetime.now(timezone.utc)
    return {"days": max(0, (end - start).days), "open": not closed}


def parse_luas(u: dict):
    """Turunkan luas_bangunan/luas_tanah dari nama tipe ('Tipe 45/90') bila belum disimpan.

    Sejak Fase 28b luas bisa diisi sebagai FORM INPUT nyata di master unit; derivasi ini
    tetap dipakai sebagai fallback jujur untuk data lama agar peta & showroom tidak kosong.
    """
    lb, lt = u.get("luas_bangunan"), u.get("luas_tanah")
    if lb and lt:
        return int(lb), int(lt)
    t = (u.get("type") or "").replace("Tipe", "").strip()
    if "/" in t:
        parts = t.split("/")
        try:
            return int(parts[0]), int(parts[1])
        except ValueError:
            pass
    return int(lb or 0), int(lt or 0)


def block_of(u: dict) -> str:
    """Nama blok kavling; bila belum tersimpan, diturunkan dari prefiks kode (A-01 → A)."""
    if u.get("block"):
        return str(u["block"])
    code = str(u.get("code") or "")
    return code.split("-")[0] if "-" in code else (code[:1] or "A")


def public_unit(u: dict, *, show_price: bool) -> dict:
    """Bentuk kavling untuk konsumsi PUBLIK — tanpa identitas pembeli/deal."""
    lb, lt = parse_luas(u)
    return {
        "id": u["id"], "code": u.get("code"), "block": block_of(u),
        "type": u.get("type"), "status": u.get("status", "available"),
        "luas_bangunan": lb, "luas_tanah": lt,
        "orientation": u.get("orientation"), "corner": bool(u.get("corner")),
        "price": int(u.get("price") or 0) if show_price else None,
        "available": u.get("status", "available") == "available",
    }
