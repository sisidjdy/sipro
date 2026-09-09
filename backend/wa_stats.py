"""wa_stats — dashboard pengiriman WhatsApp (Fase 98B): per hari, per jenis, kegagalan per kode.

Aturan Fase 92: angka kartu = jumlah baris rinciannya — kedua fungsi memakai FILTER YANG SAMA.
"""
from datetime import datetime, timedelta, timezone

from core_utils import serialize_doc
from db import db

STATUSES = ("sent", "delivered", "read", "failed", "simulated", "queued")


def _since(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=max(1, days) - 1)).replace(
        hour=0, minute=0, second=0, microsecond=0).isoformat()


def _query(org: str, *, days: int = 14, day: str = None, kind: str = None, status: str = None,
           code: str = None) -> dict:
    q = {"org_id": org, "direction": "out"}
    if day:
        q["created_at"] = {"$gte": f"{day}T00:00:00", "$lt": f"{day}T23:59:59.999999+00:00"}
    else:
        q["created_at"] = {"$gte": _since(days)}
    if kind == "lainnya":
        q["$or"] = [{"kind": None}, {"kind": {"$exists": False}}, {"kind": "lainnya"}]
    elif kind:
        q["kind"] = kind
    if status:
        q["status"] = status
    if code:
        q["error_code"] = code
    return q


async def summary(org: str, *, days: int = 14) -> dict:
    q = _query(org, days=days)
    per_day, per_kind, failures, totals = {}, {}, {}, {s: 0 for s in STATUSES}
    proj = {"_id": 0, "created_at": 1, "kind": 1, "status": 1, "error_code": 1, "error_detail": 1, "mode": 1}
    async for m in db.messages.find(q, proj):
        st = m.get("status") or "unknown"
        d = str(m.get("created_at"))[:10]
        row = per_day.setdefault(d, {"date": d, **{s: 0 for s in STATUSES}, "total": 0})
        row[st] = row.get(st, 0) + 1
        row["total"] += 1
        k = m.get("kind") or "lainnya"
        krow = per_kind.setdefault(k, {"kind": k, **{s: 0 for s in STATUSES}, "total": 0})
        krow[st] = krow.get(st, 0) + 1
        krow["total"] += 1
        totals[st] = totals.get(st, 0) + 1
        if st == "failed":
            c = str(m.get("error_code") or "unknown")
            f = failures.setdefault(c, {"code": c, "count": 0, "detail": m.get("error_detail")})
            f["count"] += 1
    start = datetime.fromisoformat(_since(days))
    series = []
    for i in range(days):
        d = (start + timedelta(days=i)).date().isoformat()
        series.append(per_day.get(d) or {"date": d, **{s: 0 for s in STATUSES}, "total": 0})
    totals["total"] = sum(totals.get(s, 0) for s in set(list(STATUSES) + [k for k in totals if k != "total"]))
    return {"days": days, "since": _since(days), "series": series,
            "by_kind": sorted(per_kind.values(), key=lambda r: -r["total"]),
            "failures": sorted(failures.values(), key=lambda r: -r["count"]), "totals": totals}


async def messages(org: str, *, days: int = 14, day: str = None, kind: str = None, status: str = None,
                   code: str = None, skip: int = 0, limit: int = 100) -> dict:
    q = _query(org, days=days, day=day, kind=kind, status=status, code=code)
    total = await db.messages.count_documents(q)
    rows = await db.messages.find(q, {"_id": 0, "document": 0}).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    conv_ids = [r["conversation_id"] for r in rows if r.get("conversation_id")]
    convs = {c["id"]: c for c in await db.conversations.find({"id": {"$in": conv_ids}},
                                                              {"_id": 0, "id": 1, "contact_name": 1, "lead_id": 1}).to_list(500)}
    for r in rows:
        c = convs.get(r.get("conversation_id")) or {}
        r["contact_name"], r["lead_id"] = c.get("contact_name"), c.get("lead_id")
    return {"data": serialize_doc(rows), "total": total}
