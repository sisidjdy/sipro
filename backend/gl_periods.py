"""Tutup periode akuntansi (P25 — kelengkapan akuntansi).

Koleksi `accounting_periods`:
    {org_id, period: "YYYY-MM", status: "closed", closed_by, closed_at, note}

Aturan (anti-manipulasi angka historis, tapi tetap jujur soal transaksi nyata):
- Jurnal **manual/penyesuaian** bertanggal di periode yang sudah ditutup → DITOLAK.
- Posting **otomatis** dari subledger (pembayaran, AP, komisi, RevRec, pajak) TIDAK
  boleh hilang hanya karena periode ditutup. Tanggalnya digeser ke periode terbuka
  paling awal dan memo diberi catatan sehingga jejak audit tetap jelas.
"""
from datetime import datetime, timezone

from db import db, ORG_ID
from core_utils import period_of  # noqa: F401 — CFG-01: satu definisi periode (WIB)


def next_period(period: str) -> str:
    y, m = int(period[:4]), int(period[5:7])
    m += 1
    if m > 12:
        y, m = y + 1, 1
    return f"{y:04d}-{m:02d}"


async def closed_periods(org_id=ORG_ID) -> set:
    rows = await db.accounting_periods.find(
        {"org_id": org_id, "status": "closed"}, {"_id": 0, "period": 1}).to_list(1200)
    return {r["period"] for r in rows}


async def is_closed(org_id, date_str) -> bool:
    return period_of(date_str) in await closed_periods(org_id)


async def resolve_post_date(org_id, date_str, auto: bool):
    """(tanggal_final, periode_asal_bila_digeser). Raise ValueError untuk jurnal manual."""
    p = period_of(date_str)
    if not p:
        return date_str, None
    closed = await closed_periods(org_id)
    if p not in closed:
        return date_str, None
    if not auto:
        raise ValueError(
            f"Periode {p} sudah ditutup — jurnal manual tidak dapat dibukukan di periode tertutup. "
            "Buka kembali periode tersebut atau gunakan tanggal di periode terbuka.")
    now = datetime.now(timezone.utc)
    current = now.strftime("%Y-%m")
    target = p
    for _ in range(240):
        target = next_period(target)
        if target not in closed:
            break
    if target <= current and current not in closed:
        return now.isoformat(), p
    return f"{target}-01T00:00:00+00:00", p


async def close_period(org_id, period: str, actor: str, note: str = None) -> dict:
    ts = now = datetime.now(timezone.utc).isoformat()
    await db.accounting_periods.update_one(
        {"org_id": org_id, "period": period},
        {"$set": {"org_id": org_id, "period": period, "status": "closed",
                  "closed_by": actor, "closed_at": ts, "note": note, "updated_at": now},
         "$setOnInsert": {"created_at": ts}}, upsert=True)
    return await db.accounting_periods.find_one({"org_id": org_id, "period": period}, {"_id": 0})


async def reopen_period(org_id, period: str, actor: str, note: str = None) -> dict:
    ts = datetime.now(timezone.utc).isoformat()
    await db.accounting_periods.update_one(
        {"org_id": org_id, "period": period},
        {"$set": {"org_id": org_id, "period": period, "status": "open",
                  "reopened_by": actor, "reopened_at": ts, "note": note, "updated_at": ts}},
        upsert=True)
    return await db.accounting_periods.find_one({"org_id": org_id, "period": period}, {"_id": 0})
