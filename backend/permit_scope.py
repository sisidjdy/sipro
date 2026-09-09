"""IZIN MENEMPEL PADA OBJEK (Fase 46) — resolusi proyek → cluster → blok → unit.

Masalah sebelum fase ini:
  * `permits` hanya punya `project_id`. Pertanyaan sederhana pemakai — "unit A-03 ini
    izinnya apa saja, ada yang kedaluwarsa?" — tidak bisa dijawab sistem.
  * Izin berstatus `approved` tetapi tanggal berlakunya sudah lewat tetap terlihat AMAN.
    Itu bohong yang mahal (SLF kedaluwarsa = serah terima bisa batal).

Yang dikerjakan modul ini (fungsi murni + query, tanpa router/UI):
  1. `object_chain()` — naik dari unit ke blok, cluster, dan proyek secara deterministik
     sehingga izin di tingkat mana pun bisa ditemukan dari objek terkecil.
  2. `health()` — menilai kesehatan satu izin: aktif / menjelang kedaluwarsa / kedaluwarsa /
     diproses / ditolak. Dipakai UI maupun gerbang pembangunan.
  3. `coverage()` — daftar izin yang berlaku untuk satu objek + pemeriksaan daftar izin
     WAJIB (`permit.block_build_without`) → apa yang kurang dan mengapa.

Prinsip kejujuran repo: bila datanya belum ada, hasilnya `None`/`missing`, BUKAN nol.
Izin lama (hasil Fase 10) tidak punya `scope` — dianggap `scope=project` agar data lama
tetap terbaca tanpa migrasi paksa (migrasi tetap dijalankan untuk merapikan).
"""
from datetime import date, timedelta

from core_utils import today_iso_date
from db import ORG_ID, db
from reference_p46 import (PERMIT_HEALTH_LABEL, PERMIT_OK_HEALTH, PERMIT_SCOPE_LABEL,
                          PERMIT_SCOPES)

DONE_STATUS = ("approved", "rejected", "expired")


def _day(value) -> str:
    return str(value or "")[:10]


def _days_between(a: str, b: str):
    """b - a dalam hari (None bila salah satu tanggal tidak ada)."""
    if not a or not b:
        return None
    try:
        return (date.fromisoformat(b[:10]) - date.fromisoformat(a[:10])).days
    except ValueError:
        return None


async def object_chain(org: str = ORG_ID, *, unit_id: str = None, block_id: str = None,
                       cluster_id: str = None, project_id: str = None) -> dict:
    """Rantai objek (unit → blok → cluster → proyek) beserta label manusiawi."""
    chain = {"unit_id": None, "block_id": None, "cluster_id": None, "project_id": None,
             "labels": {}}
    if unit_id:
        unit = await db.units.find_one({"id": unit_id, "org_id": org}, {"_id": 0})
        if not unit:
            raise ValueError("Unit tidak ditemukan.")
        chain["unit_id"] = unit["id"]
        chain["labels"]["unit"] = unit.get("code")
        block_id = block_id or unit.get("block_id")
        cluster_id = cluster_id or unit.get("cluster_id")
        project_id = project_id or unit.get("project_id")
    if block_id:
        block = await db.blocks.find_one({"id": block_id, "org_id": org}, {"_id": 0}) or {}
        chain["block_id"] = block_id
        chain["labels"]["block"] = block.get("name") or block.get("code")
        cluster_id = cluster_id or block.get("cluster_id")
        project_id = project_id or block.get("project_id")
    if cluster_id:
        cl = await db.clusters.find_one({"id": cluster_id, "org_id": org}, {"_id": 0}) or {}
        chain["cluster_id"] = cluster_id
        chain["labels"]["cluster"] = cl.get("name") or cl.get("code")
        project_id = project_id or cl.get("project_id")
    if project_id:
        proj = await db.projects.find_one({"id": project_id, "org_id": org}, {"_id": 0}) or {}
        chain["project_id"] = project_id
        chain["labels"]["project"] = proj.get("name") or proj.get("code")
    return chain


def health(permit: dict, today: str = None) -> dict:
    """Kesehatan satu izin — memakai `expiry_at` bila ada, bukan hanya status administrasi."""
    today = _day(today or today_iso_date())
    status = permit.get("status") or "not_started"
    expiry = _day(permit.get("expiry_at"))
    remind = int(permit.get("reminder_days") or 30)
    days_left = _days_between(today, expiry) if expiry else None
    if status == "rejected":
        code = "rejected"
    elif status == "expired" or (expiry and days_left is not None and days_left < 0):
        code = "expired"
    elif status == "approved":
        code = "expiring" if (days_left is not None and days_left <= remind) else "ok"
    else:
        code = "in_process"
    return {"health": code, "health_label": PERMIT_HEALTH_LABEL[code],
            "expiry_at": permit.get("expiry_at"), "days_to_expiry": days_left,
            # JUJUR: izin tanpa tanggal berlaku TIDAK dianggap berlaku selamanya —
            # dinyatakan apa adanya agar admin melengkapi.
            "expiry_known": bool(expiry)}


def _scope_of(permit: dict) -> tuple:
    """Scope izin; data lama (tanpa `scope`) dibaca sebagai izin tingkat proyek."""
    scope = permit.get("scope") or "project"
    if scope not in PERMIT_SCOPES:
        scope = "project"
    sid = permit.get("scope_id") or (permit.get("project_id") if scope == "project" else None)
    return scope, sid


async def permits_for(org: str, chain: dict, *, today: str = None) -> list:
    """Semua izin yang BERLAKU untuk objek pada rantai (termasuk warisan dari atas)."""
    ors = []
    for level in PERMIT_SCOPES:
        sid = chain.get(f"{level}_id")
        if sid:
            ors.append({"scope": level, "scope_id": sid})
    if chain.get("project_id"):
        # izin lama: belum punya `scope` sama sekali
        ors.append({"project_id": chain["project_id"],
                    "scope": {"$in": [None, ""]}})
        ors.append({"project_id": chain["project_id"], "scope": {"$exists": False}})
    if not ors:
        return []
    rows = await db.permits.find({"org_id": org, "$or": ors}, {"_id": 0}).to_list(500)
    out = []
    for p in rows:
        scope, sid = _scope_of(p)
        row = dict(p)
        row["scope"] = scope
        row["scope_id"] = sid
        row["scope_label"] = PERMIT_SCOPE_LABEL[scope]
        # nama yang dipakai router `/permits` agar layar tidak perlu tahu asal datanya
        row["scope_type_label"] = PERMIT_SCOPE_LABEL[scope]
        row["inherited"] = bool(chain.get("unit_id")) and scope != "unit"
        row["applies_via"] = scope
        row.update(health(p, today))
        out.append(row)
    order = {lvl: i for i, lvl in enumerate(PERMIT_SCOPES)}
    out.sort(key=lambda r: (order.get(r["scope"], 9), str(r.get("type") or "")))
    return out


def _required_row(code: str, rows: list) -> dict:
    """Apakah satu kode izin WAJIB sudah terpenuhi objek ini — dan oleh izin yang mana."""
    same = [r for r in rows if str(r.get("type") or "").upper() == code.upper()]
    good = [r for r in same if r["health"] in PERMIT_OK_HEALTH]
    best = good[0] if good else (same[0] if same else None)
    return {
        "code": code.upper(),
        "satisfied": bool(good),
        "health": (best or {}).get("health", "missing"),
        "health_label": PERMIT_HEALTH_LABEL[(best or {}).get("health", "missing")],
        "permit_id": (best or {}).get("id"),
        "permit_name": (best or {}).get("name"),
        "scope": (best or {}).get("scope"),
        "scope_label": (best or {}).get("scope_label"),
        "expiry_at": (best or {}).get("expiry_at"),
        "days_to_expiry": (best or {}).get("days_to_expiry"),
    }


async def coverage(org: str = ORG_ID, *, unit_id: str = None, block_id: str = None,
                   cluster_id: str = None, project_id: str = None,
                   required_codes=None, today: str = None) -> dict:
    """Peta izin satu objek: apa yang menempel, apa yang sakit, apa yang wajib tapi hilang."""
    chain = await object_chain(org, unit_id=unit_id, block_id=block_id,
                              cluster_id=cluster_id, project_id=project_id)
    rows = await permits_for(org, chain, today=today)
    counts = {k: 0 for k in PERMIT_HEALTH_LABEL}
    for r in rows:
        counts[r["health"]] = counts.get(r["health"], 0) + 1
    required = [_required_row(c, rows) for c in (required_codes or []) if str(c).strip()]
    warnings = []
    for r in rows:
        if r["health"] == "expired":
            warnings.append({
                "code": "permit_expired", "permit_id": r.get("id"),
                "detail": (f"Izin {r.get('type')} ({r.get('name') or '-'}) sudah kedaluwarsa "
                           f"pada {_day(r.get('expiry_at')) or 'tanggal tidak dicatat'}.")})
        elif r["health"] == "expiring":
            warnings.append({
                "code": "permit_expiring", "permit_id": r.get("id"),
                "detail": (f"Izin {r.get('type')} berakhir {_day(r.get('expiry_at'))} "
                           f"(sisa {r.get('days_to_expiry')} hari) — urus perpanjangan.")})
    return {
        "chain": chain, "permits": rows, "total": len(rows), "counts": counts,
        "required": required,
        "missing_codes": [r["code"] for r in required if not r["satisfied"]],
        "warnings": warnings,
        # JUJUR: objek tanpa satu izin pun bukan "0 masalah" — sebut bahwa datanya kosong.
        "state": ("empty" if not rows else "filled"),
        "as_of": _day(today or today_iso_date()),
    }
