"""metrics/pricing.py — kamus metrik POTONGAN HARGA (PRC-01..04), Fase 69.

Sumber angka: `deals.pricing.discount_lines` (rincian potongan yang DISIMPAN saat
reservasi/konversi penawaran — bukan dihitung ulang) dan `coupon_redemptions`. Deal yang lahir
sebelum mesin harga tidak punya rincian; ia dilaporkan sebagai cakupan tak lengkap, bukan
diam-diam dianggap nol.
"""
from db import ORG_ID, db
from metrics.base import month_of, result
from metrics.sales import ACTIVE_DEAL_STATUS

SOURCE_LABEL = {"discount_scheme": "Skema diskon", "promo": "Promo", "coupon": "Kupon"}


async def _deals(org_id: str, date_from: str = None, date_to: str = None,
                 project_id: str = None) -> tuple:
    q = {"org_id": org_id, "status": {"$in": list(ACTIVE_DEAL_STATUS)}}
    if project_id:
        q["project_id"] = project_id
    rows = await db.deals.find(q, {"_id": 0, "id": 1, "project_id": 1, "assigned_to": 1,
                                   "pricing": 1, "discount": 1, "reserved_at": 1,
                                   "created_at": 1, "unit_code": 1}).to_list(20000)
    if date_from:
        rows = [d for d in rows if (d.get("reserved_at") or d.get("created_at") or "") >= date_from]
    if date_to:
        rows = [d for d in rows if (d.get("reserved_at") or d.get("created_at") or "")[:10] <= date_to]
    with_lines = [d for d in rows if isinstance((d.get("pricing") or {}).get("discount_lines"), list)]
    return rows, with_lines


async def _project_names(org_id: str) -> dict:
    return {p["id"]: p.get("name") or p["id"] async for p in
            db.projects.find({"org_id": org_id}, {"_id": 0, "id": 1, "name": 1})}


def _coverage(rows, with_lines):
    if len(rows) == len(with_lines):
        return None, None
    return ({"rows": len(with_lines), "total": len(rows)},
            [f"{len(rows) - len(with_lines)} deal tanpa rincian potongan (dibuat sebelum mesin harga)"])


def _bucket(key_fn, label_fn, with_lines) -> list:
    per = {}
    for d in with_lines:
        key = key_fn(d)
        row = per.setdefault(key, {"key": key, "label": label_fn(d, key), "value": 0, "deals": 0,
                                   "by_source": {s: 0 for s in SOURCE_LABEL}})
        row["deals"] += 1
        for line in d["pricing"]["discount_lines"]:
            amt = int(line.get("amount") or 0)
            row["value"] += amt
            row["by_source"][line.get("source")] = row["by_source"].get(line.get("source"), 0) + amt
    return sorted(per.values(), key=lambda r: -r["value"])


async def discount_by_project(*, org_id: str = ORG_ID, date_from: str = None, date_to: str = None,
                              project_id: str = None, **_) -> dict:
    """Σ potongan (skema + promo + kupon) per proyek, deret per bulan."""
    rows, with_lines = await _deals(org_id, date_from, date_to, project_id)
    names = await _project_names(org_id)
    breakdown = _bucket(lambda d: d.get("project_id") or "(tanpa proyek)",
                        lambda d, k: names.get(k, k), with_lines)
    series = {}
    for d in with_lines:
        b = month_of(d.get("reserved_at") or d.get("created_at"))
        series[b] = series.get(b, 0) + sum(int(x.get("amount") or 0)
                                           for x in d["pricing"]["discount_lines"])
    total = sum(r["value"] for r in breakdown)
    coverage, missing = _coverage(rows, with_lines)
    return result("PRC-01", total if rows else None, label="Potongan diberikan per proyek",
                  unit="idr", breakdown=breakdown,
                  series=[{"bucket": b, "value": v} for b, v in sorted(series.items())],
                  inputs={"deal_aktif": len(rows), "deal_berrincian": len(with_lines)},
                  coverage=coverage, missing=missing or (["belum ada deal aktif"] if not rows else None),
                  drill="/customers?hub=deal&status=reserved,booked,completed")


async def discount_by_sales(*, org_id: str = ORG_ID, date_from: str = None, date_to: str = None,
                            project_id: str = None, **_) -> dict:
    """Σ potongan per sales (pemilik deal) — siapa yang paling banyak memberi potongan."""
    rows, with_lines = await _deals(org_id, date_from, date_to, project_id)
    users = {u["email"]: u.get("name") or u["email"] async for u in
             db.users.find({"org_id": org_id}, {"_id": 0, "email": 1, "name": 1})}
    breakdown = _bucket(lambda d: d.get("assigned_to") or "(tanpa sales)",
                        lambda d, k: users.get(k, k), with_lines)
    coverage, missing = _coverage(rows, with_lines)
    return result("PRC-02", sum(r["value"] for r in breakdown) if rows else None,
                  label="Potongan diberikan per sales", unit="idr", breakdown=breakdown,
                  inputs={"deal_aktif": len(rows), "sales": len(breakdown)},
                  coverage=coverage, missing=missing or (["belum ada deal aktif"] if not rows else None),
                  drill="/customers?hub=deal")


async def discount_by_source(*, org_id: str = ORG_ID, date_from: str = None, date_to: str = None,
                             project_id: str = None, **_) -> dict:
    """Komposisi potongan: skema diskon vs promo vs kupon (nilai & jumlah pemakaian)."""
    rows, with_lines = await _deals(org_id, date_from, date_to, project_id)
    per = {s: {"key": s, "label": lab, "value": 0, "count": 0} for s, lab in SOURCE_LABEL.items()}
    for d in with_lines:
        for line in d["pricing"]["discount_lines"]:
            row = per.setdefault(line.get("source"), {"key": line.get("source"),
                                                      "label": line.get("source"), "value": 0, "count": 0})
            row["value"] += int(line.get("amount") or 0)
            row["count"] += 1
    coverage, missing = _coverage(rows, with_lines)
    return result("PRC-03", sum(r["value"] for r in per.values()) if rows else None,
                  label="Komposisi potongan per sumber", unit="idr",
                  breakdown=sorted(per.values(), key=lambda r: -r["value"]),
                  inputs={"deal_berrincian": len(with_lines)},
                  coverage=coverage, missing=missing or (["belum ada deal aktif"] if not rows else None),
                  drill="/config")


async def coupon_usage(*, org_id: str = ORG_ID, date_from: str = None, date_to: str = None,
                       **_) -> dict:
    """Pemakaian kupon per kode (yang masih TERPAKAI, bukan yang dilepas karena batal)."""
    q = {"org_id": org_id, "state": "used"}
    rows = await db.coupon_redemptions.find(q, {"_id": 0}).to_list(20000)
    if date_from:
        rows = [r for r in rows if (r.get("used_at") or "") >= date_from]
    if date_to:
        rows = [r for r in rows if (r.get("used_at") or "")[:10] <= date_to]
    coupons = {c["id"]: c async for c in db.coupons.find({"org_id": org_id}, {"_id": 0})}
    per = {}
    for r in rows:
        c = coupons.get(r.get("coupon_id")) or {}
        row = per.setdefault(r.get("coupon_code"), {"key": r.get("coupon_code"),
                                                    "label": c.get("name") or r.get("coupon_code"),
                                                    "value": 0, "amount": 0,
                                                    "quota_total": c.get("quota_total") or 0})
        row["value"] += 1
        row["amount"] += int(r.get("amount") or 0)
    return result("PRC-04", len(rows), label="Pemakaian kupon", unit="count",
                  breakdown=sorted(per.values(), key=lambda r: -r["value"]),
                  inputs={"kupon_terdaftar": len(coupons),
                          "nilai_potongan": sum(r["amount"] for r in per.values())},
                  missing=["belum ada pemakaian kupon pada periode ini"] if not rows else None,
                  drill="/config")


METRICS = {
    "PRC-01": {"fn": discount_by_project, "label": "Potongan diberikan per proyek", "unit": "idr",
               "persona": "eksekutif",
               "formula": "Σ deals.pricing.discount_lines.amount (deal aktif) per proyek; deret per bulan reservasi",
               "requires": ["deals.pricing"], "drill": "/customers?hub=deal"},
    "PRC-02": {"fn": discount_by_sales, "label": "Potongan diberikan per sales", "unit": "idr",
               "persona": "penjualan",
               "formula": "Σ deals.pricing.discount_lines.amount per deals.assigned_to",
               "requires": ["deals.pricing", "users"], "drill": "/customers?hub=deal"},
    "PRC-03": {"fn": discount_by_source, "label": "Komposisi potongan per sumber", "unit": "idr",
               "persona": "penjualan",
               "formula": "Σ amount per source ∈ {skema diskon, promo, kupon}",
               "requires": ["deals.pricing"], "drill": "/config"},
    "PRC-04": {"fn": coupon_usage, "label": "Pemakaian kupon", "unit": "count",
               "persona": "penjualan",
               "formula": "count(coupon_redemptions.state = used) per kode kupon",
               "requires": ["coupon_redemptions", "coupons"], "drill": "/config"},
}
