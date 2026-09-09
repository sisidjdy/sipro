"""MASTER KALENDER KERJA (Fase 36) — satu sumber hari kerja & hari libur.

Mengapa modul ini ada?
  Sebelum Fase 36 pengetahuan kalender SIPRO hanya: `calendar_mode` (hari kerja / hari
  kalender), `work_days_per_week` (5/6/7) dan `holidays` — SEMUANYA melekat pada dokumen
  TEMPLATE jadwal. Pada data nyata `holidays` selalu KOSONG dan tidak ada satu pun layar
  untuk mengisinya, sehingga:
    * tenggat pekerjaan bisa mendarat di 17 Agustus, Idul Fitri, atau Natal,
    * "Sabtu setengah hari" (praktik umum proyek) tidak bisa dinyatakan sama sekali,
    * pola hari kerja harus diulang di setiap template (mudah tidak konsisten).

  Modul ini memindahkan pengetahuan itu ke MASTER DATA per organisasi (dengan opsi
  override per proyek) dan dipakai DUA-DUANYA:
    1. tampilan Kalender Jadwal (Fase 36) — mewarnai hari libur & menandai tenggat yang
       jatuh bukan pada hari kerja,
    2. MESIN jadwal (`build_engine.generate_schedule`, `build_bulk.plan_for_template`,
       `build_bulk.plan_shift`) — hari libur benar-benar DILEWATI saat menghitung tanggal,
       bukan sekadar diwarnai di UI.

Desain yang dijaga:
  * Dokumen kalender BUKAN enum bebas: pola hari memakai nilai SSOT `calendar_day_kind`
    (full/half/off) dan jenis libur memakai SSOT `holiday_kind`.
  * "Setengah hari" (Sabtu) TETAP dihitung sebagai hari kerja oleh mesin jadwal (durasi
    template dinyatakan dalam hari kerja, bukan jam) — perbedaannya ditandai di kalender
    supaya perencana sadar kapasitasnya separuh. Ini disebut jujur di UI, tidak disembunyikan.
  * Nilai bawaan tetap aman bila belum ada dokumen: pola Senin–Jumat penuh, Sabtu setengah,
    Minggu libur (setara `work_days_per_week=6` yang dipakai template lama).
"""
import logging
from datetime import date, datetime, timedelta

from core_utils import new_id, now_iso
from db import db, ORG_ID
from reference_p36 import HOLIDAY_KINDS

logger = logging.getLogger("sipro.build.calendar")

COLLECTION = "build_work_calendars"
WEEKDAY_KEYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")   # index = date.weekday()
WEEKDAY_LABEL = {"mon": "Senin", "tue": "Selasa", "wed": "Rabu", "thu": "Kamis",
                 "fri": "Jumat", "sat": "Sabtu", "sun": "Minggu"}
DAY_MODES = ("full", "half", "off")
DEFAULT_PATTERN = {"mon": "full", "tue": "full", "wed": "full", "thu": "full",
                   "fri": "full", "sat": "half", "sun": "off"}
# Ambang bentrok — angka bawaan diambil dari kenyataan data demo (satu mandor realistis
# menuntaskan 2-3 pekerjaan berbukti sehari). Bisa diubah admin, karena tiap proyek berbeda.
DEFAULT_THRESHOLDS = {"max_items_per_person_per_day": 3, "max_critical_per_day": 2}
THRESHOLD_LIMITS = {"max_items_per_person_per_day": (1, 50), "max_critical_per_day": (1, 50)}
MAX_HOLIDAYS = 300


# ============================ util tanggal ============================
def _d(value) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()


def _iso(value) -> str:
    return _d(value).isoformat()


# ============================ validasi ============================
def validate_pattern(pattern: dict) -> dict:
    """Pola 7 hari; minimal satu hari kerja (kalau semua libur, jadwal tak mungkin dibuat)."""
    clean = {}
    for key in WEEKDAY_KEYS:
        val = (pattern or {}).get(key) or DEFAULT_PATTERN[key]
        if val not in DAY_MODES:
            raise ValueError(f"Pola hari {WEEKDAY_LABEL[key]} tidak dikenal ('{val}'). "
                             "Pilih hari kerja penuh, setengah hari, atau libur.")
        clean[key] = val
    if all(v == "off" for v in clean.values()):
        raise ValueError("Minimal satu hari kerja dalam seminggu — kalau semua hari libur, "
                         "tidak ada jadwal pembangunan yang bisa dihitung.")
    return clean


def validate_thresholds(thresholds: dict) -> dict:
    out = {}
    for key, (lo, hi) in THRESHOLD_LIMITS.items():
        raw = (thresholds or {}).get(key, DEFAULT_THRESHOLDS[key])
        try:
            val = int(raw)
        except (TypeError, ValueError):
            raise ValueError(f"Ambang '{key}' harus berupa angka.")
        if not lo <= val <= hi:
            raise ValueError(f"Ambang '{key}' harus antara {lo} dan {hi}.")
        out[key] = val
    return out


def validate_holiday(row) -> dict:
    """Satu hari libur: tanggal sah, nama jelas, jenis dari SSOT `holiday_kind`."""
    data = row if isinstance(row, dict) else {"date": row}
    try:
        day = _iso(data.get("date"))
    except Exception:
        raise ValueError("Tanggal hari libur harus format YYYY-MM-DD.")
    name = str(data.get("name") or "").strip()
    if len(name) < 3:
        raise ValueError(f"Nama hari libur {day} wajib diisi (minimal 3 karakter) supaya "
                         "perencana tahu kenapa tanggal itu kosong.")
    kind = data.get("kind") or "national"
    if kind not in HOLIDAY_KINDS:
        raise ValueError("Jenis hari libur tidak dikenal. Pilih dari daftar.")
    return {"date": day, "name": name[:80], "kind": kind,
            "note": (str(data.get("note")).strip()[:200] if data.get("note") else None)}


def validate_holidays(rows) -> list:
    seen, out = set(), []
    for row in rows or []:
        item = validate_holiday(row)
        if item["date"] in seen:
            continue
        seen.add(item["date"])
        out.append(item)
    if len(out) > MAX_HOLIDAYS:
        raise ValueError(f"Maksimal {MAX_HOLIDAYS} hari libur per kalender.")
    return sorted(out, key=lambda h: h["date"])


# ============================ pembacaan & resolusi ============================
def _pattern_of(doc: dict, fallback: dict) -> dict:
    out = {}
    raw = (doc or {}).get("pattern") or {}
    for key in WEEKDAY_KEYS:
        val = raw.get(key)
        out[key] = val if val in DAY_MODES else fallback[key]
    return out


def _thresholds_of(doc: dict, fallback: dict) -> dict:
    out = dict(fallback)
    for key in DEFAULT_THRESHOLDS:
        raw = ((doc or {}).get("thresholds") or {}).get(key)
        if raw:
            try:
                out[key] = int(raw)
            except (TypeError, ValueError):
                pass
    return out


def _holiday_rows(doc: dict, scope: str) -> list:
    rows = []
    for h in (doc or {}).get("holidays") or []:
        if not isinstance(h, dict) or not h.get("date"):
            continue
        rows.append({"date": str(h["date"])[:10], "name": h.get("name"),
                     "kind": h.get("kind") or "national", "note": h.get("note"),
                     "scope": scope, "inherited": scope == "org"})
    return rows


def _excluded_dates(doc: dict) -> set:
    return {str(d)[:10] for d in ((doc or {}).get("holiday_exclusions") or []) if d}


def _merge(org_doc: dict, proj_doc: dict, org: str, scope_project_id: str) -> dict:
    """Kalender efektif = kalender ORGANISASI diwarisi, lalu ditimpa override proyek.

    ATURAN PEWARISAN (ditulis setelah cacat nyata ditemukan pada pengujian Fase 36 ronde-2):
      * `pattern` & `thresholds` → override proyek MENGGANTI nilai organisasi, tetapi
        dokumen override selalu dibuat sebagai SALINAN kalender organisasi (lihat
        `_ensure_doc`) sehingga menekan "Simpan" tidak pernah mengubah perilaku diam-diam.
      * `holidays` → DIGABUNG (organisasi ∪ proyek). Hari libur nasional TIDAK BOLEH hilang
        hanya karena sebuah proyek punya kalender sendiri. Dulu override proyek dianggap
        pengganti utuh: SATU KALI menekan "Simpan pola & ambang" pada cakupan proyek
        menghapus 18 libur nasional secara senyap — tenggat 17 Agustus berhenti ditandai
        dan inspeksi QC bisa dijadwalkan pada Hari Kemerdekaan tanpa peringatan apa pun.
      * Bila sebuah proyek memang benar-benar bekerja pada tanggal libur warisan, tanggal itu
        harus DIKECUALIKAN secara sengaja (`holiday_exclusions`): tercatat di audit, terlihat
        di UI sebagai "dikecualikan di proyek ini", dan bisa dibatalkan. Tidak ada
        penghapusan senyap.
    """
    org_pattern = _pattern_of(org_doc, DEFAULT_PATTERN)
    org_thresholds = _thresholds_of(org_doc, DEFAULT_THRESHOLDS)
    has_override = bool(proj_doc)
    pattern = _pattern_of(proj_doc, org_pattern) if has_override else org_pattern
    thresholds = _thresholds_of(proj_doc, org_thresholds) if has_override else org_thresholds

    org_rows = _holiday_rows(org_doc, "org")
    proj_rows = _holiday_rows(proj_doc, "project")
    excluded_dates = _excluded_dates(proj_doc)
    merged = {row["date"]: row for row in org_rows}
    for row in proj_rows:                     # nama khusus proyek menang bila tanggal sama
        merged[row["date"]] = row
    excluded = [dict(merged[d], excluded=True) for d in sorted(excluded_dates) if d in merged]
    holidays = sorted((row for day, row in merged.items() if day not in excluded_dates),
                      key=lambda h: h["date"])
    off = sorted({i for i, k in enumerate(WEEKDAY_KEYS) if pattern[k] == "off"})
    return {
        "org_id": org,
        "project_id": (proj_doc or {}).get("project_id"),
        "scope_project_id": scope_project_id,
        "source": "project" if has_override else ("org" if org_doc else "default"),
        "override_exists": has_override,
        "inherits_org": bool(org_doc),
        "org_holidays": len(org_rows),
        "project_holidays": len(proj_rows),
        "exists": bool(org_doc or proj_doc),
        "pattern": pattern,
        "holidays": holidays,
        "excluded_holidays": excluded,
        "holiday_dates": {h["date"] for h in holidays},
        "holiday_names": {h["date"]: h.get("name") for h in holidays},
        "holiday_kinds": {h["date"]: h.get("kind") for h in holidays},
        "thresholds": thresholds,
        "off_weekdays": off,
        "work_days_per_week": 7 - len(off),
        "half_days": [k for k in WEEKDAY_KEYS if pattern[k] == "half"],
        "note": (proj_doc or {}).get("note") or (org_doc or {}).get("note"),
        "updated_by": (proj_doc or org_doc or {}).get("updated_by"),
        "updated_at": (proj_doc or org_doc or {}).get("updated_at"),
    }


async def get_doc(org: str = ORG_ID, project_id: str = None) -> dict:
    return await db.build_work_calendars.find_one(
        {"org_id": org, "project_id": project_id}, {"_id": 0})


async def resolve(org: str = ORG_ID, project_id: str = None) -> dict:
    """Kalender efektif: kalender organisasi DIWARISI, override proyek menimpa di atasnya."""
    org_doc = await get_doc(org, None)
    proj_doc = await get_doc(org, project_id) if project_id else None
    return _merge(org_doc, proj_doc, org, project_id)


async def overrides(org: str = ORG_ID) -> list:
    """Daftar proyek yang memakai kalender sendiri — supaya divergensi TIDAK tersembunyi."""
    rows = await db.build_work_calendars.find(
        {"org_id": org, "project_id": {"$ne": None}}, {"_id": 0}).to_list(200)
    if not rows:
        return []
    ids = [r.get("project_id") for r in rows]
    names = {p["id"]: p.get("name") for p in await db.projects.find(
        {"id": {"$in": ids}}, {"_id": 0, "id": 1, "name": 1}).to_list(200)}
    return [{"project_id": r.get("project_id"),
             "project_name": names.get(r.get("project_id")) or "(proyek terhapus)",
             "extra_holidays": len(_holiday_rows(r, "project")),
             "excluded_holidays": len(_excluded_dates(r)),
             "updated_by": r.get("updated_by"), "updated_at": r.get("updated_at")}
            for r in sorted(rows, key=lambda x: str(x.get("updated_at") or ""), reverse=True)]


def public(cal: dict) -> dict:
    """Bentuk aman untuk JSON (buang set internal yang tidak bisa diserialisasi)."""
    drop = {"holiday_dates", "holiday_names", "holiday_kinds"}
    return {k: v for k, v in (cal or {}).items() if k not in drop}


# ============================ perhitungan hari ============================
def day_info(cal: dict, day) -> dict:
    """Satu hari kalender: jenis hari, nama libur, dan apakah boleh dipakai bekerja."""
    d = _d(day)
    iso = d.isoformat()
    key = WEEKDAY_KEYS[d.weekday()]
    holiday = (cal.get("holiday_names") or {}).get(iso)
    mode = (cal.get("pattern") or DEFAULT_PATTERN)[key]
    return {
        "date": iso, "weekday": d.weekday(), "weekday_key": key,
        "weekday_label": WEEKDAY_LABEL[key],
        "kind": "holiday" if holiday else mode,
        "is_workday": bool(not holiday and mode != "off"),
        "half_day": bool(mode == "half" and not holiday),
        "holiday": holiday,
        "holiday_kind": (cal.get("holiday_kinds") or {}).get(iso),
    }


def is_workday(cal: dict, day) -> bool:
    return day_info(cal, day)["is_workday"]


def next_workday(cal: dict, day, forward: bool = True) -> date:
    """Hari kerja terdekat (maju secara bawaan). Dipakai untuk SARAN tanggal pengganti."""
    step = timedelta(days=1 if forward else -1)
    cur = _d(day)
    for _ in range(90):
        if is_workday(cal, cur):
            return cur
        cur = cur + step
    return _d(day)


def month_days(cal: dict, first, last) -> list:
    out, cur, end = [], _d(first), _d(last)
    while cur <= end:
        out.append(day_info(cal, cur))
        cur += timedelta(days=1)
    return out


async def params_for(org: str, project_id: str = None, doc: dict = None) -> dict:
    """Parameter kalender untuk MESIN jadwal (dipakai build_engine & build_bulk).

    Gabungan yang disengaja:
      * `calendar_mode` tetap milik TEMPLATE (hari kerja vs hari kalender) — itu keputusan
        cara menghitung durasi, bukan keputusan kalender perusahaan.
      * pola hari kerja diambil dari MASTER bila kalender sudah ada (supaya "Sabtu libur"
        cukup diatur satu kali), kalau belum ada jatuh ke `work_days_per_week` template lama.
      * daftar hari libur = libur MASTER ∪ libur yang mungkin sudah tercatat di
        template/jadwal (tidak ada data lama yang hilang).
    """
    cal = await resolve(org, project_id)
    doc = doc or {}
    holidays = set(cal["holiday_dates"])
    for h in doc.get("holidays") or []:
        try:
            holidays.add(_iso(h.get("date") if isinstance(h, dict) else h))
        except Exception:  # noqa: BLE001 — data lama yang tidak sah cukup diabaikan
            continue
    if cal["exists"]:
        off_days = set(cal["off_weekdays"])
        wdpw = cal["work_days_per_week"]
    else:
        off_days = None
        wdpw = int(doc.get("work_days_per_week") or 6)
    return {"mode": doc.get("calendar_mode") or "working_days", "wdpw": wdpw,
            "holidays": holidays, "off_days": off_days, "calendar": cal}


# ============================ penulisan (master data) ============================
async def ensure_indexes():
    """Satu kalender per (org, project) — dijaga DATABASE, bukan hanya kode."""
    await db.build_work_calendars.create_index(
        [("org_id", 1), ("project_id", 1)], name="uq_build_calendar_scope", unique=True)


async def _ensure_doc(org: str, project_id: str, actor: str) -> dict:
    """Pastikan dokumen kalender ada.

    Untuk cakupan PROYEK, dokumen baru dibuat sebagai SALINAN pola & ambang kalender
    organisasi (bukan nilai bawaan pabrik) supaya membuat override tidak pernah mengubah
    perilaku secara diam-diam. Daftar libur SENGAJA dibiarkan kosong karena libur
    organisasi DIWARISI (lihat `_merge`), bukan disalin — agar libur nasional yang
    ditambahkan admin kelak tetap sampai ke proyek ini.
    """
    doc = await get_doc(org, project_id)
    if doc:
        return doc
    base = _merge(await get_doc(org, None), None, org, None) if project_id else None
    fresh = {"id": new_id(), "org_id": org, "project_id": project_id,
             "pattern": dict(base["pattern"]) if base else dict(DEFAULT_PATTERN),
             "thresholds": dict(base["thresholds"]) if base else dict(DEFAULT_THRESHOLDS),
             "holidays": [], "holiday_exclusions": [], "inherits_org": bool(project_id),
             "note": None, "updated_by": actor,
             "updated_at": now_iso(), "created_at": now_iso()}
    await db.build_work_calendars.update_one(
        {"org_id": org, "project_id": project_id}, {"$setOnInsert": fresh}, upsert=True)
    return await get_doc(org, project_id)


async def save(org: str, data: dict, actor: str, project_id: str = None) -> dict:
    """Simpan pola hari kerja + ambang bentrok (+ daftar libur bila dikirim)."""
    setter = {"pattern": validate_pattern(data.get("pattern")),
              "thresholds": validate_thresholds(data.get("thresholds")),
              "updated_by": actor, "updated_at": now_iso()}
    if data.get("holidays") is not None:
        setter["holidays"] = validate_holidays(data.get("holidays"))
    if data.get("note") is not None:
        # `None` = jangan diubah (form pengaturan hari kerja tidak mengirim catatan),
        # string kosong = hapus catatan. Tanpa aturan ini, menyimpan pola hari kerja
        # akan MENGHAPUS catatan sumber daftar libur — jejak kejujuran ikut hilang.
        setter["note"] = str(data.get("note")).strip()[:300] or None
    await _ensure_doc(org, project_id, actor)
    await db.build_work_calendars.update_one(
        {"org_id": org, "project_id": project_id}, {"$set": setter})
    return await resolve(org, project_id)


async def drop_override(org: str, project_id: str, actor: str) -> dict:
    """Hapus kalender khusus proyek → proyek itu kembali mengikuti kalender organisasi."""
    if not project_id:
        raise ValueError("Kalender organisasi tidak bisa dihapus — ia adalah dasar "
                         "seluruh proyek. Ubah polanya bila perlu.")
    doc = await get_doc(org, project_id)
    if not doc:
        raise ValueError("Proyek ini sudah mengikuti kalender organisasi "
                         "(tidak ada kalender khusus untuk dihapus).")
    await db.build_work_calendars.delete_one({"org_id": org, "project_id": project_id})
    logger.info("Kalender khusus proyek %s dihapus oleh %s", project_id, actor)
    return await resolve(org, project_id)


async def add_holiday(org: str, row: dict, actor: str, project_id: str = None) -> tuple:
    """Tambah satu hari libur. Mengembalikan (kalender_efektif, tindakan)."""
    item = validate_holiday(row)
    doc = await _ensure_doc(org, project_id, actor)
    own = {str(h.get("date"))[:10] for h in doc.get("holidays") or []}
    if item["date"] in own:
        raise ValueError(f"{item['date']} sudah terdaftar sebagai hari libur. "
                         "Hapus dulu bila ingin mengganti namanya.")
    if project_id and item["date"] in _excluded_dates(doc):
        # Tanggal ini libur warisan yang tadinya DIKECUALIKAN untuk proyek ini —
        # menambahkannya kembali berarti membatalkan pengecualian itu, bukan menduplikasi.
        await db.build_work_calendars.update_one(
            {"org_id": org, "project_id": project_id},
            {"$pull": {"holiday_exclusions": item["date"]},
             "$set": {"updated_by": actor, "updated_at": now_iso()}})
        return await resolve(org, project_id), "re_included"
    if project_id:
        org_doc = await get_doc(org, None) or {}
        if item["date"] in {str(h.get("date"))[:10] for h in org_doc.get("holidays") or []}:
            raise ValueError(f"{item['date']} sudah diwarisi dari kalender organisasi — "
                             "tidak perlu ditambahkan lagi khusus untuk proyek ini.")
    if len(doc.get("holidays") or []) >= MAX_HOLIDAYS:
        raise ValueError(f"Maksimal {MAX_HOLIDAYS} hari libur per kalender.")
    await db.build_work_calendars.update_one(
        {"org_id": org, "project_id": project_id},
        {"$push": {"holidays": {"$each": [item], "$sort": {"date": 1}}},
         "$set": {"updated_by": actor, "updated_at": now_iso()}})
    return await resolve(org, project_id), "added"


async def remove_holiday(org: str, day: str, actor: str, project_id: str = None) -> tuple:
    """Hapus / kecualikan satu hari libur. Mengembalikan (kalender_efektif, tindakan).

    Pada cakupan PROYEK, hari libur WARISAN tidak dihapus dari kalender organisasi —
    ia hanya dikecualikan untuk proyek ini (tercatat & bisa dibatalkan). Ini mencegah
    "menghapus satu baris di layar proyek" ternyata menghapus libur nasional bagi
    seluruh perusahaan.
    """
    target = _iso(day)
    doc = await get_doc(org, project_id)
    own = {str(h.get("date"))[:10] for h in (doc or {}).get("holidays") or []}
    if target in own:
        await db.build_work_calendars.update_one(
            {"org_id": org, "project_id": project_id},
            {"$pull": {"holidays": {"date": target}},
             "$set": {"updated_by": actor, "updated_at": now_iso()}})
        return await resolve(org, project_id), "removed"
    if project_id:
        org_doc = await get_doc(org, None) or {}
        inherited = {str(h.get("date"))[:10] for h in org_doc.get("holidays") or []}
        if target in inherited:
            if target in _excluded_dates(doc):
                raise ValueError(f"{target} sudah dikecualikan untuk proyek ini.")
            await _ensure_doc(org, project_id, actor)
            await db.build_work_calendars.update_one(
                {"org_id": org, "project_id": project_id},
                {"$addToSet": {"holiday_exclusions": target},
                 "$set": {"updated_by": actor, "updated_at": now_iso()}})
            return await resolve(org, project_id), "excluded"
    raise ValueError(f"{target} tidak ada di daftar hari libur kalender ini.")


async def include_holiday(org: str, day: str, actor: str, project_id: str = None) -> dict:
    """Batalkan pengecualian: proyek ini kembali mengikuti hari libur warisan."""
    target = _iso(day)
    if not project_id:
        raise ValueError("Pengecualian hari libur hanya ada pada kalender khusus proyek.")
    doc = await get_doc(org, project_id)
    if target not in _excluded_dates(doc):
        raise ValueError(f"{target} tidak sedang dikecualikan pada proyek ini.")
    await db.build_work_calendars.update_one(
        {"org_id": org, "project_id": project_id},
        {"$pull": {"holiday_exclusions": target},
         "$set": {"updated_by": actor, "updated_at": now_iso()}})
    return await resolve(org, project_id)
