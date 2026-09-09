"""Penutupan buku (Fase 49A & 49B) — daftar periksa bergigi + tutup tahun yang reversible.

Dua cacat nyata yang ditutup modul ini:

1. **Tutup bulan tanpa pemeriksaan apa pun.** `POST /gl/periods/close` dulu langsung menutup
   periode walau mutasi bank belum dicocokkan, tagihan/uang muka masih menunggu keputusan,
   penyusutan bulan itu belum diposting, dan subledger tidak tie-out dengan buku besar.
   Akibatnya "buku tertutup" tidak berarti apa-apa: angkanya masih bisa berubah lewat pintu
   lain, dan laporan yang sudah dibagikan ke owner jadi berbeda dengan pembukuan.
   Sekarang penutupan **MENAHAN** (bukan menandai) dan menyebut sebabnya satu per satu; hanya
   peran berwenang yang boleh menerobos dengan alasan tertulis, dan terobosan itu melahirkan
   tugas tinjauan.

2. **Tidak ada tutup tahun.** Laba/rugi tahun berjalan tidak pernah dipindah ke Laba Ditahan
   (`3-1900`), sehingga begitu ganti tahun akun pendapatan/beban terus menumpuk: laba-rugi
   tahun baru mewarisi angka tahun lalu dan neraca tidak pernah menunjukkan ekuitas yang
   benar. Sekarang tutup tahun membuat **jurnal penutup yang seimbang**, idempoten
   (`source_event` unik), dan bisa **DIBALIK** dengan jurnal balik berjejak — bukan dihapus.

Uang IDR integer; waktu UTC ISO-8601.
"""
import logging

import gl_engine as gl
import gl_periods as glp
import gl_reports as glr
import reference as ref
from core_utils import new_id, now_iso
from db import db, ORG_ID
import finance_engine as fe
from engine import auto_create_task

logger = logging.getLogger("sipro.closing")

OK, BLOCKING, WARNING, MISSING = "ok", "blocking", "warning", "missing_data"
RETAINED_EARNINGS = "3-1900"
PL_TYPES = ("revenue", "expense")
YEAR_CLOSING_SOURCE = "year_closing"


class ClosingHold(Exception):
    """Penutupan ditahan: daftar periksa belum bersih."""

    def __init__(self, reasons: list, items: list = None):
        self.reasons = reasons
        self.items = items or []
        super().__init__(" ".join(reasons))


def _label(item_code: str) -> str:
    return ref.label_of("closing_check_item", item_code)


def _rp(n) -> str:
    return "Rp " + f"{int(n or 0):,}".replace(",", ".")


def _in_period(value, period: str) -> bool:
    return str(value or "")[:7] == period


async def _gl_balance(org: str, code: str, end_exclusive: str = None) -> int:
    """Saldo (kredit − debit) sebuah akun sampai `end_exclusive` (kumulatif)."""
    q = {"org_id": org, "lines.account_code": code}
    if end_exclusive:
        q["date"] = {"$lt": end_exclusive}
    dr = cr = 0
    for je in await db.journal_entries.find(q, {"_id": 0, "lines": 1}).to_list(200000):
        for ln in je.get("lines", []):
            if ln.get("account_code") == code:
                dr += int(ln.get("debit", 0) or 0)
                cr += int(ln.get("credit", 0) or 0)
    return cr - dr


# =============================================================== daftar periksa
async def _check_unbalanced(org, period, start, end) -> dict:
    bad = await db.journal_entries.count_documents({
        "org_id": org, "date": {"$gte": start, "$lt": end},
        "$expr": {"$ne": ["$total_debit", "$total_credit"]}})
    if bad:
        return {"state": BLOCKING, "count": bad,
                "detail": f"{bad} jurnal periode ini tidak seimbang — perbaiki dulu sebelum ditutup."}
    return {"state": OK, "count": 0, "detail": "Semua jurnal periode ini seimbang."}


async def _check_bank(org, period, start, end) -> dict:
    total = await db.bank_transactions.count_documents({"org_id": org, "date": {"$gte": start[:10], "$lt": end[:10]}})
    if not total:
        return {"state": MISSING, "count": 0,
                "detail": "Belum ada mutasi bank pada periode ini — tidak ada yang perlu dicocokkan."}
    rows = await db.bank_transactions.find(
        {"org_id": org, "date": {"$gte": start[:10], "$lt": end[:10]},
         "match_state": {"$nin": ["matched", "ignored"]}},
        {"_id": 0, "amount": 1, "description": 1, "date": 1}).to_list(2000)
    if rows:
        amount = sum(int(r.get("amount", 0) or 0) for r in rows)
        return {"state": BLOCKING, "count": len(rows), "amount": amount,
                "detail": (f"{len(rows)} mutasi bank senilai {_rp(amount)} belum dicocokkan "
                           "maupun diabaikan beralasan — uang masuk/keluar yang belum dijelaskan "
                           "tidak boleh ikut ditutup."),
                "link": "/finance?tab=bank"}
    return {"state": OK, "count": 0,
            "detail": f"{total} mutasi bank periode ini sudah dicocokkan atau diabaikan beralasan."}


async def _check_intakes(org, period, start, end) -> dict:
    rows = await db.payment_intakes.find(
        {"org_id": org, "state": "pending"}, {"_id": 0, "amount": 1, "created_at": 1,
                                              "transfer_date": 1}).to_list(2000)
    rows = [r for r in rows
            if _in_period(r.get("transfer_date") or r.get("created_at"), period)]
    if rows:
        amount = sum(int(r.get("amount", 0) or 0) for r in rows)
        return {"state": BLOCKING, "count": len(rows), "amount": amount,
                "detail": (f"{len(rows)} bukti transfer pelanggan senilai {_rp(amount)} masih "
                           "menunggu verifikasi — tagihannya belum berkurang, jadi angka piutang "
                           "periode ini belum final."),
                "link": "/finance?tab=intake"}
    return {"state": OK, "count": 0, "detail": "Tidak ada bukti transfer yang menunggu verifikasi."}


async def _check_bills(org, period, start, end) -> dict:
    rows = await db.ap_invoices.find(
        {"org_id": org, "status": "pending_approval"},
        {"_id": 0, "net": 1, "vendor": 1, "created_at": 1}).to_list(3000)
    rows = [r for r in rows if _in_period(r.get("created_at"), period)]
    if rows:
        amount = sum(int(r.get("net", 0) or 0) for r in rows)
        return {"state": BLOCKING, "count": len(rows), "amount": amount,
                "detail": (f"{len(rows)} tagihan vendor/subkon senilai {_rp(amount)} masih "
                           "menunggu persetujuan — beban/utangnya belum masuk buku."),
                "link": "/finance?tab=ap"}
    return {"state": OK, "count": 0, "detail": "Tidak ada tagihan yang menunggu persetujuan."}


async def _check_advances(org, period, start, end) -> dict:
    rows = await db.subcon_advances.find(
        {"org_id": org, "state": "draft"},
        {"_id": 0, "amount": 1, "advance_number": 1, "created_at": 1}).to_list(1000)
    rows = [r for r in rows if _in_period(r.get("created_at"), period)]
    if rows:
        amount = sum(int(r.get("amount", 0) or 0) for r in rows)
        nums = ", ".join(r.get("advance_number") or "-" for r in rows[:3])
        return {"state": BLOCKING, "count": len(rows), "amount": amount,
                "detail": (f"{len(rows)} uang muka subkon senilai {_rp(amount)} menunggu "
                           f"keputusan ({nums}) — kas yang mungkin keluar belum diputus."),
                "link": "/subcon?tab=advances"}
    return {"state": OK, "count": 0, "detail": "Tidak ada uang muka subkon yang menunggu keputusan."}


async def _check_payroll(org, period, start, end) -> dict:
    rows = await db.labor_payrolls.find(
        {"org_id": org, "state": {"$in": ["submitted", "draft", "pending"]}},
        {"_id": 0, "total": 1, "batch_number": 1, "created_at": 1}).to_list(1000)
    rows = [r for r in rows if _in_period(r.get("created_at"), period)]
    if rows:
        amount = sum(int(r.get("total", 0) or 0) for r in rows)
        return {"state": BLOCKING, "count": len(rows), "amount": amount,
                "detail": (f"{len(rows)} rekap upah harian senilai {_rp(amount)} menunggu "
                           "keputusan Manajer Keuangan — upah yang belum diputus bukan biaya final."),
                "link": "/finance?tab=labor"}
    return {"state": OK, "count": 0, "detail": "Tidak ada rekap upah yang menunggu keputusan."}


async def _check_depreciation(org, period, start, end) -> dict:
    assets = await db.fixed_assets.find(
        {"org_id": org}, {"_id": 0, "id": 1, "code": 1, "name": 1, "status": 1,
                          "acquired_at": 1, "acquisition_date": 1, "acquired_date": 1,
                          "book_value": 1, "method": 1}).to_list(2000)
    live = []
    for a in assets:
        if str(a.get("status") or "active") not in ("active", "in_use"):
            continue
        # Nama field tanggal perolehan di koleksi `fixed_assets` adalah `acquired_date`.
        # Cacat yang ditemukan POC Fase 49: pemeriksaan ini hanya mencari `acquired_at` /
        # `acquisition_date`, jadi tanggal perolehan selalu terbaca KOSONG dan setiap periode
        # lama (mis. 2024-05) dituduh "penyusutan belum diposting" untuk aset yang baru dibeli
        # 2026 — daftar periksa menahan penutupan tanpa sebab yang benar.
        acq = str(a.get("acquired_date") or a.get("acquired_at")
                  or a.get("acquisition_date") or "")[:7]
        if acq and acq > period:
            continue
        if int(a.get("book_value", 1) or 0) <= 0:
            continue
        live.append(a)
    if not live:
        return {"state": MISSING, "count": 0,
                "detail": "Belum ada aset tetap aktif yang perlu disusutkan pada periode ini."}
    posted = set(await db.asset_depreciations.distinct(
        "asset_id", {"org_id": org, "period": period}))
    missing = [a for a in live if a["id"] not in posted]
    if missing:
        names = ", ".join(f"{a.get('code')} {a.get('name')}" for a in missing[:3])
        return {"state": BLOCKING, "count": len(missing),
                "detail": (f"Penyusutan {period} belum diposting untuk {len(missing)} aset "
                           f"({names}) — beban periode ini masih kurang."),
                "link": "/assets"}
    return {"state": OK, "count": len(live),
            "detail": f"Penyusutan {period} sudah diposting untuk {len(live)} aset aktif."}


async def _check_tieout(org, period, start, end) -> dict:
    """Subledger ↔ buku besar (kumulatif sampai akhir periode).

    Aturan sama dengan gate `verify_business_invariants.py` supaya tidak ada dua kebenaran.
    """
    problems = []
    # 2-1100 Utang Usaha = Σ (net − paid) tagihan yang sudah disetujui
    ap_open = 0
    for b in await db.ap_invoices.find(
            {"org_id": org, "status": {"$in": ["approved", "partial", "paid"]}},
            {"_id": 0, "net": 1, "paid": 1}).to_list(5000):
        ap_open += int(b.get("net", 0) or 0) - int(b.get("paid", 0) or 0)
    gl_ap = await _gl_balance(org, "2-1100")
    if gl_ap != ap_open:
        problems.append(f"2-1100 Utang Usaha buku besar {_rp(gl_ap)} ≠ sisa tagihan disetujui "
                        f"{_rp(ap_open)}")
    # 2-1200 Utang Retensi = Σ retensi ditahan yang belum dilepas
    ret = 0
    for b in await db.ap_invoices.find(
            {"org_id": org, "status": {"$in": ["approved", "partial", "paid"]},
             "retention_released": {"$ne": True}}, {"_id": 0, "retention_held": 1}).to_list(5000):
        ret += int(b.get("retention_held", 0) or 0)
    gl_ret = await _gl_balance(org, "2-1200")
    if gl_ret != ret:
        problems.append(f"2-1200 Utang Retensi buku besar {_rp(gl_ret)} ≠ retensi ditahan {_rp(ret)}")
    # 2-1400 Uang Muka Penjualan = Σ kewajiban kontrak yang belum diakui
    cl = 0
    for c in await db.contract_liabilities.find(
            {"org_id": org, "recognized": {"$ne": True}}, {"_id": 0, "balance": 1}).to_list(5000):
        cl += int(c.get("balance", 0) or 0)
    gl_cl = await _gl_balance(org, "2-1400")
    if gl_cl != cl:
        problems.append(f"2-1400 Uang Muka Penjualan buku besar {_rp(gl_cl)} ≠ kewajiban kontrak "
                        f"{_rp(cl)}")
    # 1-1800 Uang Muka Subkontraktor = Σ sisa uang muka yang sudah dibayar
    adv = 0
    for a in await db.subcon_advances.find(
            {"org_id": org, "state": {"$in": ["paid", "closed"]}},
            {"_id": 0, "outstanding": 1}).to_list(2000):
        adv += int(a.get("outstanding", 0) or 0)
    gl_adv = -(await _gl_balance(org, "1-1800"))  # aset: debit − kredit
    if gl_adv != adv:
        problems.append(f"1-1800 Uang Muka Subkon buku besar {_rp(gl_adv)} ≠ sisa uang muka "
                        f"{_rp(adv)}")
    if problems:
        return {"state": BLOCKING, "count": len(problems),
                "detail": "Subledger belum tie-out: " + "; ".join(problems) + ".",
                "link": "/accounting"}
    return {"state": OK, "count": 4,
            "detail": "Utang usaha, retensi, uang muka penjualan, dan uang muka subkon tie-out "
                      "dengan buku besar."}


async def _check_threeway(org, period, start, end) -> dict:
    rows = await db.ap_invoices.find(
        {"org_id": org, "requires_senior_approval": True, "status": "pending_approval"},
        {"_id": 0, "po_number": 1, "net": 1, "created_at": 1}).to_list(1000)
    rows = [r for r in rows if _in_period(r.get("created_at"), period)]
    if rows:
        return {"state": WARNING, "count": len(rows),
                "detail": (f"{len(rows)} tagihan hasil terobosan 3-way match masih menunggu "
                           "tinjauan — tidak menahan penutupan, tetapi sebaiknya dituntaskan."),
                "link": "/procurement?tab=threeway"}
    return {"state": OK, "count": 0, "detail": "Tidak ada tahanan 3-way match yang menggantung."}


CHECKS = (
    ("jurnal_seimbang", _check_unbalanced),
    ("bank_belum_dicocokkan", _check_bank),
    ("bukti_transfer_menunggu", _check_intakes),
    ("tagihan_menunggu", _check_bills),
    ("uang_muka_menunggu", _check_advances),
    ("rekap_upah_menunggu", _check_payroll),
    ("penyusutan_belum_diposting", _check_depreciation),
    ("tieout_subledger", _check_tieout),
    ("tahanan_3way", _check_threeway),
)


async def close_check(org=ORG_ID, period: str = None) -> dict:
    """Jalankan seluruh daftar periksa penutupan untuk satu periode `YYYY-MM`."""
    start, last = glr.month_range(period)
    # Batas EKSKLUSIF untuk pemeriksaan berbasis tanggal. Cacat yang ditemukan POC Fase 49:
    # `month_range` mengembalikan tanggal TERAKHIR bulan (inklusif), lalu pemeriksaan memakai
    # `$lt end` — sehingga jurnal tidak seimbang atau mutasi bank yang bertanggal 31 LOLOS
    # dari daftar periksa dan bulan itu tetap boleh ditutup. Laporan L/R tetap memakai batas
    # inklusif (`last`) karena `_pl_block` sudah menambah satu hari sendiri.
    end = glr.end_exclusive(last)
    items = []
    for code, fn in CHECKS:
        try:
            res = await fn(org, period, start, end)
        except Exception as exc:  # noqa: BLE001 — satu pemeriksaan gagal tidak boleh menutup layar
            logger.exception("Pemeriksaan %s gagal", code)
            res = {"state": WARNING, "count": 0,
                   "detail": f"Pemeriksaan tidak bisa dijalankan: {exc}"}
        items.append({"code": code, "label": _label(code), **res})
    blocking = [i for i in items if i["state"] == BLOCKING]
    warnings = [i for i in items if i["state"] == WARNING]
    closed = period in await glp.closed_periods(org)
    meta = await db.accounting_periods.find_one({"org_id": org, "period": period}, {"_id": 0})
    pl = await glr._pl_block(org, start, last)
    return {
        "period": period, "status": "closed" if closed else "open",
        "items": items, "blocking": [i["code"] for i in blocking],
        "warnings": [i["code"] for i in warnings],
        "can_close": not blocking and not closed,
        "blocking_count": len(blocking), "warning_count": len(warnings),
        "revenue": pl["total_revenue"], "expense": pl["total_expense"],
        "net_income": pl["net_income"],
        "closed_by": (meta or {}).get("closed_by"), "closed_at": (meta or {}).get("closed_at"),
        "override_by": (meta or {}).get("override_by"),
        "override_reason": (meta or {}).get("override_reason"),
        "detail": ("Periode sudah ditutup." if closed else
                   ("Semua pemeriksaan beres — periode boleh ditutup." if not blocking else
                    f"{len(blocking)} pemeriksaan MENAHAN penutupan.")),
    }


async def close_period(org, period: str, actor: str, note: str = None,
                       override: bool = False, override_reason: str = None) -> dict:
    """Tutup periode. Menahan bila daftar periksa belum bersih (kecuali diterobos)."""
    if period in await glp.closed_periods(org):
        raise ValueError(f"Periode {period} sudah ditutup.")
    check = await close_check(org, period)
    blocking = [i for i in check["items"] if i["state"] == BLOCKING]
    if blocking and not override:
        raise ClosingHold([i["detail"] for i in blocking], blocking)
    doc = await glp.close_period(org, period, actor, note)
    ts = now_iso()
    snapshot = [{"code": i["code"], "state": i["state"], "detail": i["detail"]}
                for i in check["items"]]
    await db.accounting_periods.update_one({"org_id": org, "period": period}, {"$set": {
        "checklist": snapshot, "net_income_at_close": check["net_income"],
        "revenue_at_close": check["revenue"], "expense_at_close": check["expense"],
        "override_by": actor if (blocking and override) else None,
        "override_reason": override_reason if (blocking and override) else None,
        "override_items": [i["code"] for i in blocking] if (blocking and override) else [],
        "updated_at": ts}})
    if blocking and override:
        await auto_create_task(
            source_event=f"closing.override:{org}:{period}",
            title=f"Tinjau terobosan tutup buku — periode {period}",
            jobdesk_code="FN-11", type="review",
            related_entity_type="accounting_period", related_entity_id=period,
            assigned_to=None, priority="urgent", org_id=org,
            description=("Ditutup walau daftar periksa belum bersih: "
                         + "; ".join(i["label"] for i in blocking)
                         + f" | Alasan {actor}: {override_reason}"))
        await fe.notify_finance(
            org, "Tutup buku diterobos",
            f"Periode {period} ditutup {actor} walau {len(blocking)} pemeriksaan belum bersih: "
            + "; ".join(i["label"] for i in blocking),
            "finance", "accounting_period", period)
    return await db.accounting_periods.find_one({"org_id": org, "period": period}, {"_id": 0})


# =============================================================== tutup tahun
def _year_range(year: str) -> tuple:
    return f"{year}-01-01T00:00:00+00:00", f"{int(year) + 1}-01-01T00:00:00+00:00"


async def _year_pl(org, year: str) -> dict:
    """Saldo akun laba-rugi tahun itu, TIDAK memasukkan jurnal penutup/balik tahun."""
    start, end = _year_range(year)
    accts = {a["code"]: a for a in await db.accounts.find(
        {"org_id": org}, {"_id": 0, "code": 1, "name": 1, "type": 1}).to_list(500)}
    rows = {}
    q = {"org_id": org, "date": {"$gte": start, "$lt": end},
         "source_type": {"$ne": YEAR_CLOSING_SOURCE}}
    for je in await db.journal_entries.find(q, {"_id": 0, "lines": 1}).to_list(200000):
        for ln in je.get("lines", []):
            code = ln.get("account_code")
            acct = accts.get(code)
            if not acct or acct["type"] not in PL_TYPES:
                continue
            slot = rows.setdefault(code, {"code": code, "name": acct["name"],
                                          "type": acct["type"], "debit": 0, "credit": 0})
            slot["debit"] += int(ln.get("debit", 0) or 0)
            slot["credit"] += int(ln.get("credit", 0) or 0)
    revenue = sum(r["credit"] - r["debit"] for r in rows.values() if r["type"] == "revenue")
    expense = sum(r["debit"] - r["credit"] for r in rows.values() if r["type"] == "expense")
    return {"rows": sorted(rows.values(), key=lambda r: r["code"]),
            "revenue": revenue, "expense": expense, "net_income": revenue - expense}


async def year_check(org=ORG_ID, year: str = None) -> dict:
    """Tahun hanya boleh ditutup bila SEMUA bulan bertransaksi tahun itu sudah ditutup."""
    start, end = _year_range(year)
    months = set()
    unbalanced = 0
    for je in await db.journal_entries.find(
            {"org_id": org, "date": {"$gte": start, "$lt": end}},
            {"_id": 0, "date": 1, "total_debit": 1, "total_credit": 1}).to_list(200000):
        m = str(je.get("date"))[:7]
        if len(m) == 7:
            months.add(m)
        if int(je.get("total_debit", 0)) != int(je.get("total_credit", 0)):
            unbalanced += 1
    closed = await glp.closed_periods(org)
    open_months = sorted(m for m in months if m not in closed)
    pl = await _year_pl(org, year)
    existing = await db.gl_year_closings.find_one({"org_id": org, "year": year}, {"_id": 0})
    items = []
    if not months:
        items.append({"code": "tahun_tanpa_jurnal", "state": MISSING,
                      "label": "Jurnal tahun ini",
                      "detail": f"Belum ada jurnal bertanggal {year} — tidak ada yang perlu ditutup."})
    if open_months:
        items.append({"code": "bulan_belum_ditutup", "state": BLOCKING,
                      "label": "Semua bulan tahun ini sudah ditutup",
                      "detail": (f"{len(open_months)} bulan belum ditutup: "
                                 + ", ".join(open_months) +
                                 " — tutup bulanannya dulu supaya angka tahunan tidak berubah "
                                 "setelah laba dipindah ke Laba Ditahan."),
                      "link": "/accounting?tab=closing"})
    if unbalanced:
        items.append({"code": "jurnal_seimbang", "state": BLOCKING,
                      "label": _label("jurnal_seimbang"),
                      "detail": f"{unbalanced} jurnal tahun ini tidak seimbang."})
    blocking = [i for i in items if i["state"] == BLOCKING]
    return {
        "year": year, "months": sorted(months), "open_months": open_months,
        "items": items, "blocking": [i["code"] for i in blocking],
        "can_close": not blocking and bool(months) and (existing or {}).get("state") != "closed",
        "state": (existing or {}).get("state", "open"),
        "closing": existing, "pl": pl,
        "detail": ("Tahun ini sudah ditutup." if (existing or {}).get("state") == "closed"
                   else ("Belum ada jurnal tahun ini." if not months
                         else ("Tahun boleh ditutup." if not blocking
                               else f"{len(blocking)} pemeriksaan MENAHAN tutup tahun."))),
    }


async def year_close(org, year: str, actor: str, note: str = None) -> dict:
    """Pindahkan laba/rugi tahun berjalan ke Laba Ditahan lewat jurnal penutup.

    Idempoten: `source_event` unik per (org, tahun) sehingga panggilan kedua tidak pernah
    membuat jurnal kedua.
    """
    existing = await db.gl_year_closings.find_one({"org_id": org, "year": year}, {"_id": 0})
    if existing and existing.get("state") == "closed":
        return {**existing, "idempotent": True}
    chk = await year_check(org, year)
    if chk["blocking"]:
        raise ClosingHold([i["detail"] for i in chk["items"] if i["state"] == BLOCKING],
                          chk["items"])
    if not chk["months"]:
        raise ValueError(f"Belum ada jurnal bertanggal {year} — tidak ada yang bisa ditutup.")
    pl = chk["pl"]
    lines = []
    for r in pl["rows"]:
        bal = (r["credit"] - r["debit"]) if r["type"] == "revenue" else (r["debit"] - r["credit"])
        if bal == 0:
            continue
        if r["type"] == "revenue":
            # menutup pendapatan: debit sebesar saldo kreditnya
            lines.append({"account_code": r["code"], "debit": bal, "credit": 0,
                          "memo": f"Tutup tahun {year}"} if bal > 0
                         else {"account_code": r["code"], "debit": 0, "credit": -bal,
                               "memo": f"Tutup tahun {year}"})
        else:
            lines.append({"account_code": r["code"], "debit": 0, "credit": bal,
                          "memo": f"Tutup tahun {year}"} if bal > 0
                         else {"account_code": r["code"], "debit": -bal, "credit": 0,
                               "memo": f"Tutup tahun {year}"})
    net = pl["net_income"]
    if net > 0:
        lines.append({"account_code": RETAINED_EARNINGS, "debit": 0, "credit": net,
                      "memo": f"Laba tahun {year} dipindah ke Laba Ditahan"})
    elif net < 0:
        lines.append({"account_code": RETAINED_EARNINGS, "debit": -net, "credit": 0,
                      "memo": f"Rugi tahun {year} dipindah ke Laba Ditahan"})
    if not lines:
        raise ValueError(f"Tidak ada saldo laba-rugi {year} yang perlu ditutup.")
    entry = await gl.post_journal(
        org, f"Jurnal penutup tahun buku {year}", lines,
        date=f"{year}-12-31T23:59:59+00:00", source_type=YEAR_CLOSING_SOURCE, source_id=year,
        source_event=f"year_close:{org}:{year}", posted_by=actor, auto=True, allow_closed=True)
    ts = now_iso()
    doc = {
        "id": (existing or {}).get("id") or new_id(), "org_id": org, "year": year,
        "state": "closed", "net_income": net, "revenue": pl["revenue"], "expense": pl["expense"],
        "entry_id": entry["id"], "entry_no": entry.get("entry_no"),
        "closed_by": actor, "closed_at": ts, "note": note,
        "reopened_by": None, "reopened_at": None, "reopen_reason": None,
        "reversal_entry_no": None, "reversal_entry_id": None,
        "months": chk["months"], "created_at": (existing or {}).get("created_at") or ts,
        "updated_at": ts,
    }
    await db.gl_year_closings.update_one({"org_id": org, "year": year}, {"$set": doc}, upsert=True)
    await fe.notify_finance(
        org, f"Tahun buku {year} ditutup",
        f"Laba/rugi {_rp(net)} dipindah ke Laba Ditahan lewat jurnal {entry.get('entry_no')}.",
        "finance", "gl_year_closing", year)
    return {**doc, "idempotent": False}


async def year_reopen(org, year: str, actor: str, reason: str) -> dict:
    """Buka kembali tahun buku: jurnal penutup DIBALIK (bukan dihapus) dan berjejak."""
    doc = await db.gl_year_closings.find_one({"org_id": org, "year": year}, {"_id": 0})
    if not doc or doc.get("state") != "closed":
        raise ValueError(f"Tahun buku {year} tidak dalam status tertutup.")
    entry = await db.journal_entries.find_one({"org_id": org, "id": doc["entry_id"]}, {"_id": 0})
    if not entry:
        raise ValueError("Jurnal penutup tahun tidak ditemukan — laporkan ke admin sistem.")
    mirror = [{"account_code": ln["account_code"], "debit": int(ln.get("credit", 0) or 0),
               "credit": int(ln.get("debit", 0) or 0),
               "memo": f"Balik jurnal penutup {doc.get('entry_no')}"} for ln in entry["lines"]]
    rev = await gl.post_journal(
        org, f"Balik jurnal penutup tahun {year} — {reason}", mirror,
        date=f"{year}-12-31T23:59:59+00:00", source_type=YEAR_CLOSING_SOURCE, source_id=year,
        source_event=f"year_reopen:{org}:{year}", posted_by=actor, auto=True, allow_closed=True)
    ts = now_iso()
    await db.gl_year_closings.update_one({"org_id": org, "year": year}, {"$set": {
        "state": "reopened", "reopened_by": actor, "reopened_at": ts, "reopen_reason": reason,
        "reversal_entry_id": rev["id"], "reversal_entry_no": rev.get("entry_no"),
        "updated_at": ts}})
    await fe.notify_finance(
        org, f"Tahun buku {year} dibuka kembali",
        f"{actor}: {reason}. Jurnal penutup dibalik lewat {rev.get('entry_no')}.",
        "finance", "gl_year_closing", year)
    return await db.gl_year_closings.find_one({"org_id": org, "year": year}, {"_id": 0})


async def year_list(org=ORG_ID) -> list:
    """Daftar tahun buku yang punya jurnal + status penutupannya."""
    years = set()
    for je in await db.journal_entries.find({"org_id": org}, {"_id": 0, "date": 1}).to_list(200000):
        y = str(je.get("date"))[:4]
        if len(y) == 4:
            years.add(y)
    docs = {d["year"]: d for d in await db.gl_year_closings.find(
        {"org_id": org}, {"_id": 0}).to_list(200)}
    out = []
    for y in sorted(years | set(docs), reverse=True):
        d = docs.get(y) or {}
        pl = await _year_pl(org, y)
        out.append({"year": y, "state": d.get("state", "open"),
                    "net_income": d.get("net_income", pl["net_income"]),
                    "revenue": pl["revenue"], "expense": pl["expense"],
                    "current_net_income": pl["net_income"],
                    "entry_no": d.get("entry_no"), "closed_by": d.get("closed_by"),
                    "closed_at": d.get("closed_at"), "note": d.get("note"),
                    "reopened_by": d.get("reopened_by"), "reopened_at": d.get("reopened_at"),
                    "reopen_reason": d.get("reopen_reason"),
                    "reversal_entry_no": d.get("reversal_entry_no")})
    return out
