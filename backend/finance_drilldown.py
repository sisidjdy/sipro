"""Drill-down KPI dashboard keuangan (Fase 91): tiap kartu bisa dibuka menjadi daftar baris
yang menyusun angkanya, dan tiap baris punya tautan ke tabel yang sudah terfilter."""
from db import db, ORG_ID
from finance_engine import _days_overdue

AR_BASE = "/finance?tab=receivables&sub=ar"
AP_BASE = "/finance?tab=payables&sub=ap"
BUCKET_KEYS = ("current", "1-30", "31-60", "61-90", ">90")


def _bucket_of(days: int) -> str:
    if days <= 0:
        return "current"
    if days <= 30:
        return "1-30"
    if days <= 60:
        return "31-60"
    if days <= 90:
        return "61-90"
    return ">90"


def _ar_row(inv: dict, amount: int, note: str = "") -> dict:
    return {"id": inv["id"], "title": f"{inv.get('unit_code') or '-'} · {inv.get('lead_name') or '-'}",
            "subtitle": " · ".join(x for x in [inv.get("scheme_name") or "", note] if x),
            "amount": int(amount or 0), "status": inv.get("status"), "status_group": "ar_status",
            "href": f"{AR_BASE}&q={inv.get('unit_code') or ''}", "deal_id": inv.get("deal_id")}


def _ap_row(b: dict, amount: int) -> dict:
    return {"id": b["id"], "title": b.get("vendor") or "-",
            "subtitle": b.get("note") or "", "amount": int(amount or 0),
            "status": b.get("status"), "status_group": "ap_status",
            "href": f"{AP_BASE}&status={b.get('status') or ''}"}


async def _ar_by_bucket(org: str) -> dict:
    out = {k: [] for k in BUCKET_KEYS}
    for inv in await db.ar_invoices.find({"org_id": org}, {"_id": 0, "content": 0}).to_list(2000):
        per = {}
        for it in inv.get("items", []):
            sisa = int(it.get("amount", 0)) - int(it.get("paid_amount", 0) or 0)
            if sisa <= 0:
                continue
            d = _days_overdue(it.get("due_date"))
            per.setdefault(_bucket_of(d), []).append((sisa, it.get("label"), d))
        for bk, items in per.items():
            amt = sum(s for s, _, _ in items)
            labels = ", ".join(l for _, l, _ in items if l)
            worst = max(d for _, _, d in items)
            note = f"{labels}" + (f" · telat {worst} hr" if worst > 0 else "")
            out[bk].append(_ar_row(inv, amt, note))
    return out


async def drilldown(org: str, key: str, bucket: str = None) -> dict:
    """Kembalikan {title, rows, total, href_all} untuk satu kunci KPI."""
    org = org or ORG_ID
    rows, title, href_all = [], key, None
    if key == "ar_outstanding":
        # FIN-01: definisi SAMA dengan kartu (`finance_engine.ar_aging`): sisa per termin
        # (amount − paid_amount), bukan field `outstanding` invoice yang bisa basi.
        title, href_all = "Piutang (AR) belum lunas", f"{AR_BASE}&status=unpaid,partial"
        by = await _ar_by_bucket(org)
        merged = {}
        for bk in BUCKET_KEYS:
            for r in by[bk]:
                m = merged.setdefault(r["id"], {**r, "amount": 0, "subtitle": ""})
                m["amount"] += r["amount"]
                m["subtitle"] = (m["subtitle"] + " · " if m["subtitle"] else "") + r["subtitle"]
        rows = list(merged.values())
    elif key == "ar_overdue":
        title, href_all = "Termin AR yang melewati jatuh tempo", f"{AR_BASE}&status=unpaid,partial&sort=created_at"
        by = await _ar_by_bucket(org)
        merged = {}
        for bk in ("1-30", "31-60", "61-90", ">90"):
            for r in by[bk]:
                m = merged.setdefault(r["id"], {**r, "amount": 0, "subtitle": ""})
                m["amount"] += r["amount"]
                m["subtitle"] = (m["subtitle"] + " · " if m["subtitle"] else "") + r["subtitle"]
        rows = list(merged.values())
    elif key == "ar_bucket":
        bk = bucket if bucket in BUCKET_KEYS else "current"
        title, href_all = f"Aging piutang · {bk}", f"{AR_BASE}&status=unpaid,partial"
        rows = (await _ar_by_bucket(org))[bk]
    elif key == "ap_outstanding":
        title, href_all = "Utang (AP) belum dibayar", AP_BASE
        for b in await db.ap_invoices.find({"org_id": org, "status": {"$ne": "paid"}}, {"_id": 0}).to_list(2000):
            rows.append(_ap_row(b, b.get("outstanding", 0)))
    elif key == "ap_pending":
        title, href_all = "Tagihan vendor menunggu approval", f"{AP_BASE}&status=pending_approval"
        for b in await db.ap_invoices.find({"org_id": org, "status": "pending_approval"}, {"_id": 0}).to_list(2000):
            rows.append(_ap_row(b, b.get("net", b.get("outstanding", 0))))
    elif key == "ap_bucket":
        bk = bucket if bucket in BUCKET_KEYS else "current"
        title, href_all = f"Aging utang · {bk}", AP_BASE
        for b in await db.ap_invoices.find({"org_id": org, "status": {"$ne": "paid"}}, {"_id": 0}).to_list(2000):
            d = _days_overdue(b.get("due_date"))
            if _bucket_of(d) == bk and int(b.get("outstanding", 0) or 0) > 0:
                r = _ap_row(b, b.get("outstanding", 0))
                if d > 0:
                    r["subtitle"] = (r["subtitle"] + " · " if r["subtitle"] else "") + f"telat {d} hr"
                rows.append(r)
    elif key == "contract_liability":
        title, href_all = "Kewajiban kontrak (uang diterima sebelum BAST)", f"{AR_BASE}&status=unpaid,partial,paid"
        liabs = await db.contract_liabilities.find({"org_id": org, "balance": {"$gt": 0}}, {"_id": 0}).to_list(2000)
        invs = {i["deal_id"]: i for i in await db.ar_invoices.find(
            {"org_id": org, "deal_id": {"$in": [l.get("deal_id") for l in liabs]}}, {"_id": 0, "items": 0}).to_list(2000)}
        for l in liabs:
            inv = invs.get(l.get("deal_id")) or {"id": l["id"], "unit_code": None, "lead_name": None, "deal_id": l.get("deal_id")}
            rows.append(_ar_row(inv, l.get("balance", 0), "belum diakui (BAST belum terbit)"))
    elif key == "customer_deposits":
        title, href_all = "Titipan pelanggan (saldo)", "/finance?tab=receivables&sub=deposits"
        deps = await db.customer_deposits.find({"org_id": org, "balance": {"$gt": 0}}, {"_id": 0}).to_list(2000)
        invs = {i["deal_id"]: i for i in await db.ar_invoices.find(
            {"org_id": org, "deal_id": {"$in": [d.get("deal_id") for d in deps]}}, {"_id": 0, "items": 0}).to_list(2000)}
        for d in deps:
            inv = invs.get(d.get("deal_id")) or {"id": d["id"], "unit_code": None, "lead_name": None, "deal_id": d.get("deal_id")}
            r = _ar_row(inv, d.get("balance", 0), "saldo titipan")
            r["href"] = href_all
            rows.append(r)
    elif key == "revenue_recognized":
        title, href_all = "Pendapatan diakui saat BAST", f"{AR_BASE}&status=paid"
        revs = await db.revenue_recognitions.find({"org_id": org}, {"_id": 0}).to_list(2000)
        invs = {i["deal_id"]: i for i in await db.ar_invoices.find(
            {"org_id": org, "deal_id": {"$in": [r.get("deal_id") for r in revs]}}, {"_id": 0, "items": 0}).to_list(2000)}
        for rv in revs:
            inv = invs.get(rv.get("deal_id")) or {"id": rv["id"], "unit_code": None, "lead_name": None, "deal_id": rv.get("deal_id")}
            rows.append(_ar_row(inv, rv.get("revenue", 0), f"diakui {str(rv.get('recognized_at') or rv.get('created_at') or '')[:10]}"))
    else:
        raise KeyError(key)
    rows.sort(key=lambda r: -r["amount"])
    return {"key": key, "title": title, "rows": rows, "total": sum(r["amount"] for r in rows),
            "count": len(rows), "href_all": href_all}
