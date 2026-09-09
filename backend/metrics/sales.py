"""metrics/sales.py — kamus metrik PENJUALAN & UNIT (SLS-01..11), spec Dok 31 §3.

Semua angka dihitung dari koleksi yang benar-benar ada (`units`, `deals`, `ar_invoices`,
`receipts`, `journal_entries`), bukan dari field ringkasan yang bisa basi. Metrik yang
membutuhkan data yang BELUM ada di sistem (mis. rincian komponen harga per add-on) tetap
terdaftar dan mengaku belum lengkap — itu peta pekerjaan, bukan kekurangan yang disembunyikan.
"""
from datetime import datetime, timezone

from db import ORG_ID, db
from metrics.base import date_of, day_range_query, div, median, month_of, pct, result

SOLD_UNIT_STATUS = ("booked", "sold")
ACTIVE_DEAL_STATUS = ("reserved", "booked", "completed")
SOLD_DEAL_STATUS = ("booked", "completed")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _units(org_id: str, project_id: str = None) -> list:
    q = {"org_id": org_id}
    if project_id:
        q["project_id"] = project_id
    return await db.units.find(q, {"_id": 0}).to_list(20000)


async def _deals(org_id: str, project_id: str = None, statuses=ACTIVE_DEAL_STATUS) -> list:
    q = {"org_id": org_id, "status": {"$in": list(statuses)}}
    if project_id:
        q["project_id"] = project_id
    return await db.deals.find(q, {"_id": 0}).to_list(20000)


# ------------------------------------------------------------------ SLS-01 / 02
async def units_sold(*, org_id: str = ORG_ID, date_from: str = None, date_to: str = None,
                     project_id: str = None, granularity: str = "month", **_) -> dict:
    """Unit terjual KUMULATIF: `count(units.status in {booked, sold})`.

    Deret waktunya dibentuk dari `deals.booked_at` (peristiwa yang benar-benar tercatat),
    BUKAN dari `units.status_history` — riwayat status unit sebagian dibentuk migrasi
    (`estimated: true`) sehingga tanggalnya tidak bisa dipertanggungjawabkan.
    """
    units = await _units(org_id, project_id)
    sold = [u for u in units if u.get("status") in SOLD_UNIT_STATUS]
    deals = await _deals(org_id, project_id, SOLD_DEAL_STATUS)
    keyer = month_of if granularity != "day" else date_of
    per_bucket = {}
    for d in deals:
        stamp = d.get("booked_at") or d.get("created_at")
        if not stamp:
            continue
        if date_from and stamp < date_from:
            pass  # tetap dihitung di kumulatif awal periode
        per_bucket[keyer(stamp)] = per_bucket.get(keyer(stamp), 0) + 1
    series, running = [], 0
    for bucket in sorted(per_bucket):
        running += per_bucket[bucket]
        series.append({"bucket": bucket, "value": per_bucket[bucket], "cumulative": running})
    no_stamp = [d["id"] for d in deals if not (d.get("booked_at") or d.get("created_at"))]
    return result(
        "SLS-01", len(sold), label="Unit terjual (kumulatif)", unit="count",
        breakdown=[{"key": u["code"], "label": u.get("type") or u["code"],
                    "value": u.get("price") or 0, "status": u.get("status")} for u in sold],
        series=series, inputs={"unit_total": len(units), "deal_terjual": len(deals)},
        coverage={"rows": len(deals) - len(no_stamp), "total": len(deals)} if no_stamp else None,
        missing=[f"{len(no_stamp)} deal tanpa tanggal booking (tidak masuk deret waktu)"]
        if no_stamp else None,
        drill="/customers?hub=deal&status=booked,active,completed")


async def absorption(*, org_id: str = ORG_ID, project_id: str = None, **_) -> dict:
    """Absorpsi = `unit terjual / total unit` per cluster (dan total proyek)."""
    units = await _units(org_id, project_id)
    per_cluster = {}
    for u in units:
        key = u.get("cluster_code") or "(tanpa cluster)"
        row = per_cluster.setdefault(key, {"key": key, "label": key, "total": 0, "sold": 0})
        row["total"] += 1
        row["sold"] += 1 if u.get("status") in SOLD_UNIT_STATUS else 0
    for row in per_cluster.values():
        row["value"] = pct(row["sold"], row["total"])
    sold = sum(r["sold"] for r in per_cluster.values())
    return result("SLS-02", pct(sold, len(units)), label="Absorpsi", unit="pct",
                  breakdown=sorted(per_cluster.values(), key=lambda r: -r["total"]),
                  inputs={"terjual": sold, "total_unit": len(units)},
                  missing=["belum ada unit terdaftar"] if not units else None,
                  drill="/projects")


# ----------------------------------------------------------------- SLS-03 / 07
async def booking_value(*, org_id: str = ORG_ID, date_from: str = None, date_to: str = None,
                        project_id: str = None, **_) -> dict:
    """Nilai penjualan (booking value) = `Σ deals.price` untuk deal aktif."""
    deals = await _deals(org_id, project_id)
    total = sum(int(d.get("price") or 0) for d in deals)
    no_price = [d["id"] for d in deals if not d.get("price")]
    per_status = {}
    for d in deals:
        row = per_status.setdefault(d.get("status"), {"key": d.get("status"),
                                                     "label": d.get("status"),
                                                     "value": 0, "count": 0})
        row["value"] += int(d.get("price") or 0)
        row["count"] += 1
    return result("SLS-03", total, label="Nilai penjualan (booking value)", unit="idr",
                  breakdown=list(per_status.values()),
                  inputs={"deal_aktif": len(deals)},
                  coverage={"rows": len(deals) - len(no_price), "total": len(deals)}
                  if no_price else None,
                  missing=[f"{len(no_price)} deal tanpa harga"] if no_price else None,
                  drill="/customers?hub=deal&status=booked,active,completed")


async def average_price(*, org_id: str = ORG_ID, project_id: str = None, **_) -> dict:
    """Rata-rata harga jual = `Σ harga deal / jumlah deal berharga`."""
    deals = [d for d in await _deals(org_id, project_id) if d.get("price")]
    total = sum(int(d["price"]) for d in deals)
    return result("SLS-07", int(round(total / len(deals))) if deals else None,
                  label="Rata-rata harga jual", unit="idr",
                  inputs={"deal_berharga": len(deals), "nilai": total},
                  missing=["belum ada deal berharga"] if not deals else None,
                  drill="/customers?hub=deal")


# ---------------------------------------------------------------------- SLS-04
async def revenue_recognized(*, org_id: str = ORG_ID, date_from: str = None,
                             date_to: str = None, **_) -> dict:
    """Pendapatan diakui = saldo akun bertipe `revenue` di buku besar (kredit - debit).

    Diambil dari `journal_entries.lines` supaya angkanya SAMA dengan laporan laba rugi —
    kalau dihitung dari `deals`, dua layar akan berbeda begitu ada jurnal koreksi.
    """
    q = {"org_id": org_id, **day_range_query("date", date_from, date_to)}
    rows = await db.journal_entries.find(q, {"_id": 0, "lines": 1, "date": 1}).to_list(20000)
    total, per_account = 0, {}
    for entry in rows:
        for line in entry.get("lines") or []:
            if line.get("account_type") != "revenue":
                continue
            amount = int(line.get("credit") or 0) - int(line.get("debit") or 0)
            total += amount
            key = f"{line.get('account_code')} — {line.get('account_name')}"
            row = per_account.setdefault(key, {"key": key, "label": key, "value": 0})
            row["value"] += amount
    return result("SLS-04", total, label="Pendapatan diakui (buku besar)", unit="idr",
                  breakdown=sorted(per_account.values(), key=lambda r: -r["value"]),
                  inputs={"jurnal_diperiksa": len(rows)},
                  missing=["belum ada jurnal pada periode ini"] if not rows else None,
                  drill="/accounting/reports")


# ---------------------------------------------------------------------- SLS-05
async def cash_in(*, org_id: str = ORG_ID, date_from: str = None, date_to: str = None,
                  **_) -> dict:
    """Kas masuk = `Σ receipts.amount` pada periode (pembayaran yang benar-benar diterima)."""
    q = {"org_id": org_id, **day_range_query("created_at", date_from, date_to)}
    rows = await db.receipts.find(q, {"_id": 0}).to_list(20000)
    total = sum(int(r.get("amount") or 0) for r in rows)
    per_method = {}
    for r in rows:
        key = r.get("method") or "(tanpa metode)"
        row = per_method.setdefault(key, {"key": key, "label": key, "value": 0, "count": 0})
        row["value"] += int(r.get("amount") or 0)
        row["count"] += 1
    series = {}
    for r in rows:
        bucket = month_of(r.get("created_at"))
        series[bucket] = series.get(bucket, 0) + int(r.get("amount") or 0)
    return result("SLS-05", total, label="Kas masuk", unit="idr",
                  breakdown=list(per_method.values()),
                  series=[{"bucket": b, "value": v} for b, v in sorted(series.items())],
                  inputs={"kuitansi": len(rows)},
                  missing=["belum ada penerimaan pada periode ini"] if not rows else None,
                  drill="/finance?tab=ar")


# ---------------------------------------------------------------------- SLS-06
async def ar_overdue(*, org_id: str = ORG_ID, **_) -> dict:
    """Piutang jatuh tempo = `Σ termin yang lewat tanggal & belum lunas`, per ember umur.

    Dihitung dari `ar_invoices.items[]` (termin), bukan dari `outstanding` tingkat tagihan:
    satu tagihan bisa punya termin yang jatuh tempo dan termin yang belum — menjumlahkan
    seluruh sisanya sebagai "jatuh tempo" akan melebih-lebihkan tunggakan.
    """
    rows = await db.ar_invoices.find({"org_id": org_id}, {"_id": 0}).to_list(20000)
    now = _now()
    buckets = {"1-30 hari": 0, "31-60 hari": 0, "61-90 hari": 0, ">90 hari": 0}
    overdue_total, outstanding_total, no_due = 0, 0, 0
    for inv in rows:
        for item in inv.get("items") or []:
            sisa = int(item.get("amount") or 0) - int(item.get("paid_amount") or 0)
            if sisa <= 0:
                continue
            outstanding_total += sisa
            due = item.get("due_date")
            if not due:
                no_due += 1
                continue
            if due >= now:
                continue
            days = (datetime.fromisoformat(now) - datetime.fromisoformat(due)).days
            key = ("1-30 hari" if days <= 30 else "31-60 hari" if days <= 60
                   else "61-90 hari" if days <= 90 else ">90 hari")
            buckets[key] += sisa
            overdue_total += sisa
    return result("SLS-06", overdue_total, label="Piutang jatuh tempo", unit="idr",
                  breakdown=[{"key": k, "label": k, "value": v} for k, v in buckets.items()],
                  inputs={"tagihan": len(rows), "outstanding_total": outstanding_total},
                  coverage={"rows": len(rows), "total": len(rows)} if no_due else None,
                  missing=[f"{no_due} termin tanpa tanggal jatuh tempo"] if no_due else None,
                  drill="/finance?tab=ar&status=unpaid,partial")


# ---------------------------------------------------------------------- SLS-08
async def scheme_mix(*, org_id: str = ORG_ID, **_) -> dict:
    """Komposisi skema bayar = pangsa tiap skema pada tagihan yang terbit."""
    rows = await db.ar_invoices.find({"org_id": org_id},
                                     {"_id": 0, "scheme_name": 1, "total": 1}).to_list(20000)
    per_scheme, total = {}, 0
    for inv in rows:
        key = inv.get("scheme_name") or "(tanpa skema)"
        row = per_scheme.setdefault(key, {"key": key, "label": key, "value": 0, "count": 0})
        row["value"] += int(inv.get("total") or 0)
        row["count"] += 1
        total += int(inv.get("total") or 0)
    for row in per_scheme.values():
        row["share_pct"] = pct(row["value"], total)
    return result("SLS-08", len(per_scheme), label="Komposisi skema bayar", unit="count",
                  breakdown=sorted(per_scheme.values(), key=lambda r: -r["value"]),
                  inputs={"tagihan": len(rows), "nilai": total},
                  missing=["belum ada tagihan terbit"] if not rows else None,
                  drill="/finance?tab=ar")


# ---------------------------------------------------------------------- SLS-09
async def addon_revenue(*, org_id: str = ORG_ID, **_) -> dict:
    """Pendapatan add-on = `Σ komponen harga bertipe pendapatan selain harga unit`.

    Permintaan pemilik: add-on harus terlihat sebagai BARIS TERPISAH. Rincian komponen harga
    per kontrak (`price_breakdown`) baru terbentuk pada fase Kontrak & Rencana Bayar; sebelum
    itu ada master add-on tetapi tidak ada kontrak yang memakainya, jadi angkanya TIDAK
    dikarang — metrik ini mengaku belum lengkap dan menyebut apa yang dibutuhkan.
    """
    deals = await db.deals.find({"org_id": org_id}, {"_id": 0, "price_breakdown": 1}).to_list(5000)
    with_breakdown = [d for d in deals if d.get("price_breakdown")]
    addons = await db.addon_items.count_documents({"org_id": org_id})
    if not with_breakdown:
        return result("SLS-09", None, label="Pendapatan add-on", unit="idr",
                      inputs={"master_addon": addons, "deal": len(deals)},
                      missing=["rincian komponen harga (price_breakdown) belum ada pada deal — "
                               "terbentuk saat fase Kontrak & Rencana Bayar"],
                      drill="/admin/master-data")
    per_code, total = {}, 0
    for d in with_breakdown:
        for comp in d.get("price_breakdown") or []:
            if comp.get("treatment") != "revenue" or comp.get("code") == "unit_price":
                continue
            key = comp.get("code") or "(tanpa kode)"
            row = per_code.setdefault(key, {"key": key, "label": comp.get("label") or key,
                                            "value": 0})
            row["value"] += int(comp.get("amount") or 0)
            total += int(comp.get("amount") or 0)
    return result("SLS-09", total, label="Pendapatan add-on", unit="idr",
                  breakdown=sorted(per_code.values(), key=lambda r: -r["value"]),
                  inputs={"deal_berrincian": len(with_breakdown), "master_addon": addons},
                  coverage={"rows": len(with_breakdown), "total": len(deals)}
                  if len(with_breakdown) != len(deals) else None,
                  missing=[f"{len(deals) - len(with_breakdown)} deal tanpa rincian komponen"]
                  if len(with_breakdown) != len(deals) else None,
                  drill="/customers?hub=deal")


# ---------------------------------------------------------------------- SLS-10
async def days_to_sell(*, org_id: str = ORG_ID, project_id: str = None, **_) -> dict:
    """Waktu jual per unit = median(`tanggal booking - tanggal unit mulai dijual`).

    Riwayat status unit yang dibentuk MIGRASI ditandai `estimated: true`; baris seperti itu
    DIBUANG dari perhitungan (tanggalnya bukan peristiwa nyata) dan dilaporkan sebagai
    cakupan yang belum penuh.
    """
    units = await _units(org_id, project_id)
    durations, estimated, no_history = [], 0, 0
    for u in units:
        if u.get("status") not in SOLD_UNIT_STATUS:
            continue
        hist = [h for h in (u.get("status_history") or []) if h.get("field") == "status"]
        real = [h for h in hist if not h.get("estimated")]
        if not real:
            estimated += 1 if hist else 0
            no_history += 0 if hist else 1
            continue
        first = min(h.get("at") for h in real)
        sold_at = max(h.get("at") for h in real if h.get("to") in SOLD_UNIT_STATUS) \
            if any(h.get("to") in SOLD_UNIT_STATUS for h in real) else None
        if not sold_at:
            continue
        durations.append((datetime.fromisoformat(sold_at)
                          - datetime.fromisoformat(first)).days)
    sold_count = len([u for u in units if u.get("status") in SOLD_UNIT_STATUS])
    missing = []
    if estimated:
        missing.append(f"{estimated} unit hanya punya riwayat status bentukan migrasi "
                       "(tanggalnya tidak bisa dipertanggungjawabkan)")
    if no_history:
        missing.append(f"{no_history} unit tanpa riwayat status")
    return result("SLS-10", median(durations), label="Waktu jual per unit (median)", unit="days",
                  inputs={"unit_terjual": sold_count, "dipakai": len(durations)},
                  coverage={"rows": len(durations), "total": sold_count} if durations else None,
                  missing=missing or None, drill="/projects")


# ---------------------------------------------------------------------- SLS-11
async def cancellations(*, org_id: str = ORG_ID, date_from: str = None, date_to: str = None,
                        **_) -> dict:
    """Pembatalan & refund = jumlah + nilai deal batal (0 adalah angka JUJUR di sini:
    deal batal bisa dihitung; tidak ada yang batal artinya benar-benar nol)."""
    q = {"org_id": org_id, "status": "cancelled"}
    rows = await db.deals.find(q, {"_id": 0}).to_list(20000)
    total = sum(int(d.get("price") or 0) for d in rows)
    refunds = await db.payments_out.find({"org_id": org_id, "kind": "refund"},
                                         {"_id": 0, "amount": 1}).to_list(5000)
    return result("SLS-11", len(rows), label="Pembatalan & refund", unit="count",
                  breakdown=[{"key": d["id"], "label": d.get("unit_code") or d["id"],
                              "value": int(d.get("price") or 0)} for d in rows],
                  inputs={"nilai_batal": total,
                          "refund_dibayar": sum(int(r.get("amount") or 0) for r in refunds)},
                  drill="/customers?hub=deal&status=cancelled")


METRICS = {
    "SLS-01": {"fn": units_sold, "label": "Unit terjual (kumulatif)", "unit": "count",
               "persona": "eksekutif", "snapshot": True,
               "formula": "count(units.status ∈ {booked, sold}); deret dari deals.booked_at",
               "requires": ["units", "deals"],
               "drill": "/customers?hub=deal&status=booked,active,completed"},
    "SLS-02": {"fn": absorption, "label": "Absorpsi", "unit": "pct", "persona": "eksekutif",
               "snapshot": True, "formula": "terjual / total unit (per cluster)",
               "requires": ["units"], "drill": "/projects"},
    "SLS-03": {"fn": booking_value, "label": "Nilai penjualan (booking value)", "unit": "idr",
               "persona": "eksekutif", "snapshot": True,
               "formula": "Σ deals.price (status aktif)", "requires": ["deals"],
               "drill": "/customers?hub=deal&status=booked,active,completed"},
    "SLS-04": {"fn": revenue_recognized, "label": "Pendapatan diakui", "unit": "idr",
               "persona": "eksekutif", "snapshot": True,
               "formula": "Σ (kredit - debit) akun bertipe revenue",
               "requires": ["journal_entries"], "drill": "/accounting/reports"},
    "SLS-05": {"fn": cash_in, "label": "Kas masuk", "unit": "idr", "persona": "eksekutif",
               "snapshot": True, "formula": "Σ receipts.amount pada periode",
               "requires": ["receipts"], "drill": "/finance?tab=ar"},
    "SLS-06": {"fn": ar_overdue, "label": "Piutang jatuh tempo", "unit": "idr",
               "persona": "eksekutif", "snapshot": True,
               "formula": "Σ termin lewat tanggal & belum lunas (ember umur)",
               "requires": ["ar_invoices"], "drill": "/finance?tab=ar&status=unpaid,partial"},
    "SLS-07": {"fn": average_price, "label": "Rata-rata harga jual", "unit": "idr",
               "persona": "penjualan", "formula": "Σ harga / jumlah deal berharga",
               "requires": ["deals"], "drill": "/customers?hub=deal"},
    "SLS-08": {"fn": scheme_mix, "label": "Komposisi skema bayar", "unit": "count",
               "persona": "penjualan", "formula": "pangsa nilai tagihan per skema",
               "requires": ["ar_invoices"], "drill": "/finance?tab=ar"},
    "SLS-09": {"fn": addon_revenue, "label": "Pendapatan add-on", "unit": "idr",
               "persona": "penjualan",
               "formula": "Σ komponen harga treatment=revenue, code ≠ unit_price",
               "requires": ["deals.price_breakdown"], "drill": "/customers?hub=deal"},
    "SLS-10": {"fn": days_to_sell, "label": "Waktu jual per unit (median)", "unit": "days",
               "persona": "penjualan",
               "formula": "median(tanggal terjual - tanggal mulai dijual), riwayat nyata saja",
               "requires": ["units.status_history"], "drill": "/projects"},
    "SLS-11": {"fn": cancellations, "label": "Pembatalan & refund", "unit": "count",
               "persona": "penjualan", "formula": "count+nilai deal status cancelled",
               "requires": ["deals"], "drill": "/customers?hub=deal&status=cancelled"},
}
