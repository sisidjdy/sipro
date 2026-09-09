"""ROUTER Fase 36 — KALENDER JADWAL & MASTER KALENDER KERJA, prefix `/build/calendar`.

Kenapa router terpisah? Sama seperti Fase 34: `build_router.py` harus tetap di bawah batas
gate compliance, dan seluruh hal yang menyangkut KALENDER (tampilan bulanan + master hari
libur/pola hari kerja) berada di satu tempat yang mudah diaudit.

RBAC (resource `construction`):
  * view   — melihat kalender bulanan & pengaturan (PM, direksi, pelaksana, keuangan)
  * ubah pengaturan kalender kerja — HANYA admin/direksi/Manajer Proyek, karena pola hari
    kerja & hari libur menjadi dasar SELURUH tenggat, pengingat, dan eskalasi.
    Setiap perubahan ditulis ke `audit_logs` (siapa, kapan, apa).

Kalender ini READ-ONLY terhadap jadwal (INV-36-6): mengubah tanggal pekerjaan tetap lewat
jalur Fase 34 (`POST /build/bulk/shift`) yang mewajibkan penyebab + catatan dan menjaga
bukti pekerjaan yang sudah diverifikasi.
"""
from fastapi import APIRouter, Depends, HTTPException, Query

import build_calendar as bcal
import build_calendar_view as bcv
from core_utils import serialize_doc
from db import ORG_ID
from models_p36 import HolidayIn, WorkCalendarIn
from rbac import has_role, assert_project_access, audit_log, require_permission

router = APIRouter(prefix="/build/calendar", tags=["build-calendar"])
CONFIG_ROLES = ("owner", "super_admin", "project_manager")
SHIFT_ROLES = ("owner", "super_admin", "project_manager")
ONLY_ADMIN = ("Hanya admin/direksi/Manajer Proyek yang boleh mengubah kalender kerja — "
              "pola hari kerja & hari libur menjadi dasar seluruh tenggat, pengingat, "
              "dan eskalasi pekerjaan.")


def _org(user: dict) -> str:
    return user.get("org_id", ORG_ID)


def _can(user: dict) -> dict:
    return {"configure": has_role(user, *CONFIG_ROLES),
            "shift": has_role(user, *SHIFT_ROLES)}


def _guard_config(user: dict):
    if not has_role(user, *CONFIG_ROLES):
        raise HTTPException(status_code=403, detail=ONLY_ADMIN)


async def _scope(project_id: str, user: dict):
    if project_id:
        await assert_project_access(project_id, user)


@router.get("")
async def calendar_month(month: str = None, project_id: str = None, kinds: str = None,
                         assignee: str = None,
                         user: dict = Depends(require_permission("construction", "view"))):
    """Kalender bulanan: hari (libur/hari kerja), acara, bentrok, dan ringkasan.

    `project_id` kosong = portofolio SEMUA proyek yang boleh dilihat pengguna.
    `kinds` = daftar jenis acara dipisah koma (SSOT `calendar_event_kind`).
    """
    await _scope(project_id, user)
    want = [k.strip() for k in (kinds or "").split(",") if k.strip()] or None
    try:
        out = await bcv.month_view(_org(user), user, month, project_id, want, assignee)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"data": serialize_doc(out), "can": _can(user)}


@router.get("/settings")
async def get_settings(project_id: str = None,
                       user: dict = Depends(require_permission("construction", "view"))):
    """Kalender kerja efektif + apakah pengguna ini boleh mengubahnya.

    `data.holidays[].scope` menyebut asal setiap libur ("org" = diwarisi kalender
    organisasi, "project" = khusus proyek ini) dan `data.excluded_holidays` menyebut libur
    warisan yang sengaja dikecualikan proyek ini — supaya layar tidak pernah menyembunyikan
    dari mana sebuah tanggal libur berasal.
    """
    await _scope(project_id, user)
    cal = await bcal.resolve(_org(user), project_id)
    org_doc = await bcal.get_doc(_org(user), None)
    return {"data": bcal.public(cal), "can": _can(user),
            "defaults": {"pattern": bcal.DEFAULT_PATTERN,
                         "thresholds": bcal.DEFAULT_THRESHOLDS,
                         "day_modes": list(bcal.DAY_MODES),
                         "weekdays": [{"key": k, "label": bcal.WEEKDAY_LABEL[k]}
                                      for k in bcal.WEEKDAY_KEYS]},
            "overrides": await bcal.overrides(_org(user)),
            "org_calendar_exists": bool(org_doc)}


@router.put("/settings")
async def put_settings(payload: WorkCalendarIn,
                       user: dict = Depends(require_permission("construction", "update"))):
    """Simpan pola hari kerja + ambang bentrok (opsional sekaligus daftar hari libur).

    Bila `project_id` diisi, yang tersimpan adalah kalender KHUSUS proyek itu. Hari libur
    organisasi tetap DIWARISI (tidak ikut terhapus) — dulu perilakunya sebaliknya dan
    menyimpan ambang pada cakupan proyek menghapus seluruh libur nasional secara senyap.
    """
    _guard_config(user)
    await _scope(payload.project_id, user)
    data = payload.model_dump()
    if data.get("holidays") is not None:
        data["holidays"] = [h if isinstance(h, dict) else h.model_dump()
                            for h in data["holidays"]]
    try:
        cal = await bcal.save(_org(user), data, user.get("email"), payload.project_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit_log(user, "calendar_update", bcal.COLLECTION, payload.project_id or "org",
                    {"pattern": cal["pattern"], "thresholds": cal["thresholds"],
                     "holidays": len(cal["holidays"]),
                     "scope": "project" if payload.project_id else "org"})
    return {"data": bcal.public(cal), "can": _can(user),
            "message": ("Kalender khusus proyek disimpan — hari libur organisasi tetap "
                        f"berlaku ({cal['org_holidays']} tanggal diwarisi)."
                        if payload.project_id else
                        "Kalender organisasi disimpan — berlaku untuk semua proyek.")}


@router.delete("/settings")
async def drop_settings(project_id: str,
                        user: dict = Depends(require_permission("construction", "update"))):
    """Hapus kalender khusus proyek → proyek kembali mengikuti kalender organisasi."""
    _guard_config(user)
    await _scope(project_id, user)
    try:
        cal = await bcal.drop_override(_org(user), project_id, user.get("email"))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit_log(user, "calendar_override_drop", bcal.COLLECTION, project_id, {})
    return {"data": bcal.public(cal), "can": _can(user),
            "message": "Proyek ini kembali mengikuti kalender organisasi."}


@router.post("/holidays")
async def add_holiday(payload: HolidayIn, project_id: str = None,
                      user: dict = Depends(require_permission("construction", "update"))):
    """Tambah satu hari libur (langsung dipatuhi mesin jadwal untuk jadwal baru/geser)."""
    _guard_config(user)
    await _scope(project_id, user)
    try:
        cal, action = await bcal.add_holiday(_org(user), payload.model_dump(),
                                            user.get("email"), project_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit_log(user, "calendar_holiday_add", bcal.COLLECTION, payload.date,
                    {"name": payload.name, "kind": payload.kind, "action": action,
                     "project_id": project_id})
    return {"data": bcal.public(cal), "can": _can(user), "action": action,
            "message": ("Pengecualian dibatalkan — proyek ini kembali mengikuti hari libur "
                        f"{payload.date}." if action == "re_included"
                        else f"Hari libur {payload.date} ditambahkan.")}


@router.delete("/holidays/{day}")
async def remove_holiday(day: str, project_id: str = None,
                         user: dict = Depends(require_permission("construction", "update"))):
    """Hapus satu hari libur — atau kecualikan bila libur itu warisan kalender organisasi.

    Pada cakupan proyek, libur warisan TIDAK dihapus dari kalender organisasi; ia hanya
    dikecualikan untuk proyek ini, tercatat di audit, dan bisa dibatalkan kembali.
    """
    _guard_config(user)
    await _scope(project_id, user)
    try:
        cal, action = await bcal.remove_holiday(_org(user), day, user.get("email"),
                                               project_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    # Nama aksi audit dijaga STABIL (bukan hasil f-string bebas) supaya gate/laporan lama
    # tetap menemukannya: hapus = `calendar_holiday_remove`, kecualikan = `..._exclude`.
    await audit_log(user, ("calendar_holiday_exclude" if action == "excluded"
                           else "calendar_holiday_remove"),
                    bcal.COLLECTION, day, {"project_id": project_id, "action": action})
    return {"data": bcal.public(cal), "can": _can(user), "action": action,
            "message": (f"{day} dikecualikan untuk proyek ini — kalender organisasi tidak "
                        "diubah." if action == "excluded"
                        else f"Hari libur {day} dihapus.")}


@router.post("/holidays/{day}/restore")
async def restore_holiday(day: str, project_id: str,
                          user: dict = Depends(require_permission("construction", "update"))):
    """Batalkan pengecualian: proyek ini kembali mengikuti hari libur warisan."""
    _guard_config(user)
    await _scope(project_id, user)
    try:
        cal = await bcal.include_holiday(_org(user), day, user.get("email"), project_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit_log(user, "calendar_holiday_restore", bcal.COLLECTION, day,
                    {"project_id": project_id})
    return {"data": bcal.public(cal), "can": _can(user), "action": "restored",
            "message": f"Proyek ini kembali mengikuti hari libur {day}."}


@router.get("/workday")
async def workday_check(date: str = None, project_id: str = None,
                        user: dict = Depends(require_permission("construction", "view"))):
    """Apakah satu tanggal hari kerja? (dipakai dialog untuk memberi peringatan dini).

    Tanpa parameter = hari ini, supaya endpoint ini juga bisa dipakai sebagai pemeriksaan
    cepat "hari ini hari kerja atau bukan" dan aman disapu gate audit endpoint.
    """
    from core_utils import today_iso_date
    await _scope(project_id, user)
    cal = await bcal.resolve(_org(user), project_id)
    try:
        info = bcal.day_info(cal, date or today_iso_date())
    except Exception:
        raise HTTPException(status_code=400, detail="Tanggal harus format YYYY-MM-DD.")
    info["suggested_date"] = bcal.next_workday(cal, info["date"]).isoformat()
    return {"data": info}


@router.get("/months")
async def month_options(months: int = Query(default=6, ge=1, le=24), user: dict = Depends(
        require_permission("construction", "view"))):
    """Daftar bulan yang bisa dipilih (dari 1 bulan lalu ke depan) — SSOT untuk dropdown."""
    from core_utils import today_iso_date
    base = today_iso_date()[:7]
    return {"data": [bcv.shift_month(base, i) for i in range(-1, months)]}
