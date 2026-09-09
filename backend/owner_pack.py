"""Paket Laporan Bulanan Owner (Fase 49D) — satu jawaban, bukan enam layar.

Sebelum ini owner harus membuka neraca, laba-rugi, arus kas, laba per proyek, dan rasio
satu-satu, lalu MENEBAK apakah semuanya memakai potongan waktu yang sama dan apakah bukunya
sudah ditutup. Paket ini menyatukannya dengan tiga kejujuran:

1. **Status periode ikut dibawa**: terbuka/tertutup, siapa yang menutup, kapan, dan bila
   penutupannya diterobos — alasannya ikut terbaca. Laporan dari periode TERBUKA diberi
   catatan bahwa angkanya masih bisa berubah.
2. **"Belum ada data" bukan Rp 0**: setiap bagian yang memang kosong masuk daftar `missing[]`.
3. **Bukti tie-out arus kas per proyek** dibawa apa adanya supaya owner bisa menjumlah sendiri.
"""
import logging

import closing_engine as ce
import gl_periods as glp
import gl_project_cash as gpc
import gl_reports as glr
from db import db, ORG_ID

logger = logging.getLogger("sipro.owner_pack")


async def owner_pack(org_id=ORG_ID, period: str = None) -> dict:
    """Rakit laporan satu periode `YYYY-MM` untuk direksi."""
    start, end = glr.month_range(period)
    as_of = glr.prev_day(end) if end else None
    closed = period in await glp.closed_periods(org_id)
    meta = await db.accounting_periods.find_one({"org_id": org_id, "period": period},
                                               {"_id": 0}) or {}
    bs = await glr.balance_sheet(org_id, as_of=as_of)
    pl = await glr.income_statement(org_id, start, end, compare=True)
    cf = await glr.cash_flow(org_id, start, end)
    proj = await glr.project_report(org_id, start, end)
    proj_cash = await gpc.cash_flow_projects(org_id, start, end)
    rat = await glr.ratios(org_id, start, end)
    year_state = await db.gl_year_closings.find_one(
        {"org_id": org_id, "year": str(period)[:4]}, {"_id": 0}) or {}

    missing = []
    if not pl.get("total_revenue") and not pl.get("total_expense"):
        missing.append("laba_rugi")
    if not cf.get("net_change") and not cf.get("opening_cash"):
        missing.append("arus_kas")
    if not proj.get("rows"):
        missing.append("laba_per_proyek")
    if proj_cash.get("missing"):
        missing.append("arus_kas_per_proyek")

    trust = ("Angka periode TERTUTUP — tidak bisa berubah lewat jurnal manual." if closed else
             "Periode masih TERBUKA — angka di laporan ini masih bisa berubah sampai ditutup.")
    return {
        "period": period, "as_of": as_of, "status": "closed" if closed else "open",
        "closed_by": meta.get("closed_by"), "closed_at": meta.get("closed_at"),
        "override_by": meta.get("override_by"), "override_reason": meta.get("override_reason"),
        "override_items": meta.get("override_items") or [],
        "checklist": meta.get("checklist") or [],
        "year_closing": {"year": str(period)[:4], "state": year_state.get("state", "open"),
                         "net_income": year_state.get("net_income"),
                         "entry_no": year_state.get("entry_no"),
                         "closed_by": year_state.get("closed_by")},
        "balance_sheet": bs, "income_statement": pl, "cash_flow": cf,
        "project_pl": proj, "project_cash_flow": proj_cash, "ratios": rat,
        "missing": missing, "trust_note": trust,
        "detail": ("Paket laporan lengkap." if not missing else
                   "Sebagian bagian belum ada datanya: " + ", ".join(missing) + "."),
    }


async def closing_history(org_id=ORG_ID, limit: int = 24) -> dict:
    """Riwayat penutupan: siapa menutup bulan apa, diterobos atau tidak, plus tutup tahun."""
    rows = await db.accounting_periods.find({"org_id": org_id}, {"_id": 0}).sort(
        "period", -1).to_list(max(1, min(int(limit or 24), 120)))
    years = await ce.year_list(org_id)
    return {"periods": rows, "years": years,
            "overridden": [r["period"] for r in rows if r.get("override_by")]}
