"""analytics_engine.py — Fase 44: komposisi dashboard + snapshot metrik (Dok 31 §1 & §2).

Dua tugas modul ini:

1. **Menyusun dashboard per persona** dari kamus metrik. Susunannya tinggal di SATU tempat
   supaya backend dan layar tidak berdebat soal "metrik mana milik dashboard mana", dan
   supaya gate bisa memeriksa tiap dashboard benar-benar punya isi.

2. **Snapshot harian** (`metric_snapshots`). Snapshot BUKAN sumber kebenaran — ia hanya
   percepatan untuk periode besar, dan SELALU bisa dihitung ulang (INV-14). Karena itu setiap
   baris menyimpan `computed_at` + `source="recompute"`, dan endpoint tetap bisa memaksa
   hitung langsung (`fresh=true`). Kalau snapshot dan hitungan langsung berbeda, yang menang
   adalah hitungan langsung — dan gate memeriksa keduanya cocok.
"""
import logging
from datetime import datetime, timedelta, timezone

import metrics
from core_utils import new_id, now_iso
from db import ORG_ID, db

logger = logging.getLogger("sipro.analytics")

# Susunan dashboard: persona -> daftar kode metrik (urutan = urutan tampil).
DASHBOARDS = {
    "eksekutif": ["SLS-01", "SLS-03", "SLS-05", "SLS-06", "SLS-04", "SLS-02",
                  "BGT-04", "BGT-05", "BGT-06", "RAB-02", "RAB-03", "PRC-01",
                  "PRJ-01", "PRJ-04", "PRJ-09", "LED-08", "MKT-03", "LED-14"],
    "penjualan": ["LED-01", "LED-02", "LED-07", "LED-04", "LED-05", "LED-06",
                  "LED-13", "LED-10", "LED-03", "LED-15", "LED-12", "LED-11",
                  "SLS-07", "SLS-08", "SLS-09", "SLS-10", "SLS-11", "LED-14",
                  "PRC-01", "PRC-02", "PRC-03", "PRC-04"],
    "marketing": ["MKT-01", "LED-09", "LED-08", "MKT-02", "MKT-03", "MKT-04", "MKT-05"],
    "proyek": ["PRJ-01", "PRJ-02", "PRJ-03", "PRJ-04", "PRJ-05", "PRJ-06", "PRJ-07",
               "PRJ-08", "PRJ-09", "BGT-01", "BGT-02", "BGT-03",
               "RAB-01", "RAB-04", "RAB-05", "RAB-06"],
    "tim": ["USR-01", "USR-02", "USR-03", "USR-04", "USR-05", "USR-06", "USR-07"],
}
# Metrik yang di-snapshot harian (periode besar) — lihat `metrics.REGISTRY[...]["snapshot"]`.
SNAPSHOT_CODES = [c for c, s in metrics.REGISTRY.items() if s.get("snapshot")]

PERIODS = {"7d": 7, "30d": 30, "90d": 90}


def resolve_range(period: str = None, date_from: str = None, date_to: str = None) -> dict:
    """Rentang efektif. `period` (7d/30d/90d/ytd/all) hanya dipakai bila tanggal tidak diisi,
    supaya pilihan pemakai selalu menang atas bawaan."""
    if date_from and date_to:
        return {"from": date_from, "to": date_to, "period": "custom"}
    today = datetime.now(timezone.utc).date()
    if period == "all":
        return {"from": "2000-01-01", "to": today.isoformat(), "period": "all"}
    if period == "ytd":
        return {"from": f"{today.year}-01-01", "to": today.isoformat(), "period": "ytd"}
    days = PERIODS.get(period or "30d", 30)
    start = today - timedelta(days=days - 1)
    return {"from": date_from or start.isoformat(), "to": date_to or today.isoformat(),
            "period": period or "30d"}


def state_of(res: dict) -> str:
    """Kosakata kelengkapan (SSOT `metric_state`) dari hasil metrik."""
    if res.get("complete"):
        return "lengkap"
    if res.get("coverage") and res.get("value") is not None:
        return "sebagian"
    return "kosong"


def decorate(code: str, res: dict) -> dict:
    """Tambahkan metadata kamus (satuan, rumus, persona, kebutuhan data) ke hasil metrik."""
    spec = metrics.REGISTRY.get(code) or {}
    return {**res, "label": res.get("label") or spec.get("label"),
            "unit": res.get("unit") or spec.get("unit"),
            "persona": spec.get("persona"), "formula": spec.get("formula"),
            "requires": spec.get("requires") or [],
            "drill": res.get("drill") or spec.get("drill"),
            "state": state_of(res)}


async def dashboard(persona: str, *, org_id: str = ORG_ID, date_from: str = None,
                    date_to: str = None, project_id: str = None,
                    owner_email: str = None, components: str = "ads,partner") -> dict:
    """Satu dashboard persona: metrik + ringkasan kelengkapan + rentang yang dipakai."""
    codes = DASHBOARDS.get(persona)
    if not codes:
        raise ValueError(f"Dashboard '{persona}' tidak ada.")
    rng = resolve_range(None, date_from, date_to)
    results = await metrics.compute_many(
        codes, org_id=org_id, date_from=rng["from"], date_to=rng["to"],
        project_id=project_id, owner_email=owner_email, components=components)
    rows = [decorate(code, results[code]) for code in codes]
    tally = {"lengkap": 0, "sebagian": 0, "kosong": 0}
    for row in rows:
        tally[row["state"]] += 1
    return {
        "persona": persona, "range": rng, "metrics": rows, "tally": tally,
        "scoped_to": owner_email,
        "incomplete": [r["code"] for r in rows if r["state"] != "lengkap"],
        "computed_at": now_iso(),
    }


async def one(code: str, *, org_id: str = ORG_ID, date_from: str = None, date_to: str = None,
              **kwargs) -> dict:
    rng = resolve_range(None, date_from, date_to)
    res = await metrics.compute(code, org_id=org_id, date_from=rng["from"],
                               date_to=rng["to"], **kwargs)
    return {**decorate(code, res), "range": rng}


# ------------------------------------------------------------------ snapshot harian
async def write_snapshot(*, org_id: str = ORG_ID, date: str = None, codes: list = None,
                        actor: str = "scheduler") -> dict:
    """Hitung ulang metrik snapshot untuk SATU hari dan simpan (idempoten per kunci natural).

    Kunci natural `(org_id, code, period_key)` dijaga index unik: menjalankan job dua kali
    untuk hari yang sama memperbarui barisnya, tidak menambah baris kedua — pelajaran yang
    sama dengan biaya iklan Fase 43.
    """
    day = date or datetime.now(timezone.utc).date().isoformat()
    wanted = codes or SNAPSHOT_CODES
    results = await metrics.compute_many(wanted, org_id=org_id, date_from=f"{day[:4]}-01-01",
                                        date_to=day)
    written = 0
    for code, res in results.items():
        doc = {
            "org_id": org_id, "code": code, "period_key": f"ytd:{day}",
            "date": day, "value": res.get("value"), "unit": res.get("unit"),
            "state": state_of(res), "missing": res.get("missing") or [],
            "coverage": res.get("coverage"), "inputs": res.get("inputs") or {},
            "computed_at": now_iso(), "computed_by": actor, "source": "recompute",
        }
        await db.metric_snapshots.update_one(
            {"org_id": org_id, "code": code, "period_key": doc["period_key"]},
            {"$set": doc, "$setOnInsert": {"id": new_id()}}, upsert=True)
        written += 1
    return {"date": day, "metrics": written, "codes": sorted(wanted)}


async def rebuild_snapshots(*, org_id: str = ORG_ID, date: str = None,
                            actor: str = "scheduler") -> dict:
    """Hitung ulang snapshot. Tanpa `date` = PERBAIKI SELURUH riwayat yang tersimpan.

    Snapshot bukan kebenaran kedua: kalau satu baris lama nilainya menyimpang (rusak,
    diedit langsung di database, atau ditulis oleh versi rumus yang lebih tua), rebuild
    harus mengembalikannya ke hitungan langsung — bukan hanya menimpa baris hari ini.
    """
    today = datetime.now(timezone.utc).date().isoformat()
    if date:
        return await write_snapshot(org_id=org_id, date=date, actor=actor)
    days = await db.metric_snapshots.distinct("date", {"org_id": org_id})
    out = await write_snapshot(org_id=org_id, date=today, actor=actor)
    for day in sorted({d for d in days if d and d != today}):
        await write_snapshot(org_id=org_id, date=day, actor=actor)
    return out


async def snapshot_series(code: str, *, org_id: str = ORG_ID, limit: int = 60) -> list:
    """Deret snapshot satu metrik (untuk sparkline tren) — selalu bisa dihitung ulang."""
    rows = await db.metric_snapshots.find({"org_id": org_id, "code": code}, {"_id": 0}) \
        .sort("date", -1).limit(limit).to_list(limit)
    return list(reversed(rows))


async def snapshot_tick() -> int:
    """Job harian (dipasang di scheduler). Gagal satu metrik tidak menjatuhkan job."""
    try:
        out = await write_snapshot(actor="scheduler")
        logger.info("Snapshot metrik BI ditulis: %s metrik untuk %s", out["metrics"], out["date"])
        return out["metrics"]
    except Exception as exc:  # noqa: BLE001 — dicatat, tidak mematikan scheduler
        logger.warning("Snapshot metrik BI gagal: %s", exc)
        return 0
