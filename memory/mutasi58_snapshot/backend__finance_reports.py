"""Finance reporting, cash-flow projection & collections (EPIC 3.5 + M5).

Worksheet-level (belum GL penuh / e-Faktur). Sumber data: ar_invoices (jadwal termin),
ap_invoices (net + retensi), revenue_recognitions, commissions.
"""
from datetime import datetime, timedelta, timezone

from db import db, ORG_ID
from core_utils import now, now_iso
import finance_engine as fe
import late_fee_engine as lf
import settings_store as cfg
from engine import create_notification, auto_create_task, add_activity, emit

DEFAULT_COLLECTION = {"denda_rate_pct_month": 2.0, "grace_days": 7}
NOTE = "Angka worksheet-level (belum GL penuh / e-Faktur). Proyeksi berbasis jatuh tempo terjadwal."

def _parse(dt_iso):
    if not dt_iso:
        return None
    try:
        d = datetime.fromisoformat(dt_iso)
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return d
    except Exception:
        return None


def _days_overdue(due) -> int:
    if not due:
        return 0
    return (now() - due).days


def _fmt_date(iso) -> str:
    d = _parse(iso)
    return d.strftime("%d %b %Y") if d else "-"


def _rp(n) -> str:
    return f"Rp {int(n or 0):,}"


# ----------------------------- Collection config -----------------------------
async def get_collection_config(org_id=ORG_ID) -> dict:
    """Kebijakan penagihan — SATU sumber: Pusat Konfigurasi (Fase 58).

    Dulu nilai ini hidup di koleksi `finance_configs` sendiri, terpisah dari Pusat
    Konfigurasi, sehingga tarif denda & masa tenggang yang dipakai penagihan BERBEDA dari
    yang tertulis di halaman konfigurasi dan di dokumen pembeli. Endpoint lama tetap ada
    (layar Keuangan memakainya), tetapi angkanya kini dibaca dari kunci resmi.
    """
    pol = await lf.policy(org_id)
    return {"key": "collection_config", "org_id": org_id,
            "denda_rate_pct_month": pol["rate_pct_month"],
            "grace_days": pol["grace_days"],
            "max_pct_of_term": pol["max_pct_of_term"],
            "min_charge": pol["min_charge"],
            "source": "Pusat Konfigurasi (payment.late.*)",
            "policy_sentence": lf.policy_sentence(pol)}


async def set_collection_config(org_id, denda_rate_pct_month, grace_days,
                                actor="system", reason=None) -> dict:
    """Simpan ke Pusat Konfigurasi (berjejak), bukan ke koleksi terpisah."""
    await cfg.set_value(lf.KEY_RATE, float(denda_rate_pct_month), actor=actor,
                        reason=reason or "Diubah dari layar Keuangan → Penagihan.",
                        org_id=org_id)
    await cfg.set_value(lf.KEY_GRACE, int(grace_days), actor=actor,
                        reason=reason or "Diubah dari layar Keuangan → Penagihan.",
                        org_id=org_id)
    return await get_collection_config(org_id)


def compute_denda(overdue_amount, days_overdue, rate_pct_month, grace_days) -> int:
    """Kompatibilitas: satu-satunya rumus denda ada di `late_fee_engine.denda_of`."""
    pol = {"rate_pct_month": float(rate_pct_month or 0), "max_pct_of_term": 0.0,
           "min_charge": 0}
    eff = max(0, int(days_overdue) - int(grace_days or 0))
    return lf.denda_of(int(overdue_amount or 0), eff, pol)


# ----------------------------- Collections worklist -----------------------------
async def collections_worklist(org_id=ORG_ID) -> dict:
    """Daftar kerja penagihan — keadaan termin dihitung mesin denda (Fase 58).

    Tunggakan di sini kini MENGHORMATI toleransi kontrak: termin yang lewat tanggal tetapi
    masih di dalam masa tenggang masuk kolomnya sendiri (`in_grace_amount`) dan tidak
    dihitung sebagai tunggakan — dulu keduanya dicampur, sehingga daftar penagihan menyuruh
    orang menagih pembeli yang belum melanggar apa pun.
    """
    pol = await lf.policy(org_id)
    rate, grace = pol["rate_pct_month"], pol["grace_days"]
    invoices = await db.ar_invoices.find(
        {"org_id": org_id, "status": {"$in": ["unpaid", "partial"]}}, {"_id": 0}).to_list(2000)
    today = now()
    soon_limit = today + timedelta(days=14)
    rows = []
    for inv in invoices:
        overdue_amount = 0
        in_grace_amount = 0
        due_soon_amount = 0
        denda = 0
        max_days = 0
        earliest_overdue = None
        next_due = None
        for it in inv.get("items", []):
            if int(it.get("amount") or 0) - int(it.get("paid_amount") or 0) <= 0:
                continue
            st = lf.assess_item(it, pol, today)
            due = _parse(it.get("due_date"))
            if due and (next_due is None or due < next_due):
                next_due = due
            if st["state"] == "terlambat":
                overdue_amount += st["outstanding"]
                denda += st["denda_running"]
                max_days = max(max_days, st["days_late"])
                if due and (earliest_overdue is None or due < earliest_overdue):
                    earliest_overdue = due
            elif st["state"] == "dalam_tenggang":
                in_grace_amount += st["outstanding"]
            elif due and due <= soon_limit:
                due_soon_amount += st["outstanding"]
        days = max_days
        bucket = "overdue" if overdue_amount > 0 else ("due_soon" if due_soon_amount > 0 else "current")
        rows.append({
            "deal_id": inv["deal_id"], "unit_code": inv.get("unit_code"),
            "lead_name": inv.get("lead_name"), "assigned_to": inv.get("assigned_to"),
            "outstanding": inv.get("outstanding", 0), "overdue_amount": overdue_amount,
            "in_grace_amount": in_grace_amount,
            "due_soon_amount": due_soon_amount,
            "next_due": next_due.isoformat() if next_due else None,
            "days_overdue": max(0, days), "denda_estimate": denda, "bucket": bucket,
            "reminded_at": inv.get("last_reminded_at"), "status": inv.get("status"),
        })
    order = {"overdue": 0, "due_soon": 1, "current": 2}
    rows.sort(key=lambda r: (order.get(r["bucket"], 3), -r["days_overdue"], -r["overdue_amount"]))
    totals = {
        "overdue_total": sum(r["overdue_amount"] for r in rows),
        "in_grace_total": sum(r["in_grace_amount"] for r in rows),
        "due_soon_total": sum(r["due_soon_amount"] for r in rows),
        "denda_total": sum(r["denda_estimate"] for r in rows),
        "count_overdue": sum(1 for r in rows if r["bucket"] == "overdue"),
        "count": len(rows),
    }
    return {"rows": rows, "totals": totals,
            "config": {"denda_rate_pct_month": rate, "grace_days": grace,
                       "policy_sentence": lf.policy_sentence(pol)}, "note": NOTE}


async def send_reminder(deal_id, actor, org_id=ORG_ID) -> dict:
    inv = await db.ar_invoices.find_one({"org_id": org_id, "deal_id": deal_id}, {"_id": 0})
    if not inv:
        raise ValueError("Jadwal AR tidak ditemukan untuk deal ini.")
    ts = now_iso()
    unit = inv.get("unit_code") or "-"
    assignee = inv.get("assigned_to")
    outstanding = inv.get("outstanding", 0)
    await create_notification(
        user_email=assignee, title="Pengingat penagihan",
        body=f"Tindak lanjuti pembayaran unit {unit} ({inv.get('lead_name') or 'pembeli'}). Sisa {_rp(outstanding)}.",
        type="finance", related_entity_type="deal", related_entity_id=deal_id, org_id=org_id)
    await auto_create_task(
        source_event=f"collection_reminder:{deal_id}:{ts[:10]}",
        title=f"Tagih pembayaran unit {unit}", type="follow_up",
        related_entity_type="deal", related_entity_id=deal_id, assigned_to=assignee,
        description=f"Pengingat penagihan untuk {inv.get('lead_name') or 'pembeli'}. Sisa {_rp(outstanding)}.",
        priority="high", org_id=org_id)
    await add_activity(entity_type="deal", entity_id=deal_id, type="system",
                       body=f"Pengingat penagihan dikirim (sisa {_rp(outstanding)}).", actor=actor, org_id=org_id)
    await db.ar_invoices.update_one({"id": inv["id"]}, {"$set": {"last_reminded_at": ts}})
    await emit("collection.reminded", "deal", deal_id, {}, org_id=org_id)
    return {"deal_id": deal_id, "reminded_at": ts, "notified": assignee}


async def apply_late_fee(deal_id, actor, org_id=ORG_ID) -> dict:
    """Tagihkan denda keterlambatan — DILIMPAHKAN ke `late_fee_engine` (Fase 58).

    Versi lama menghitung denda dengan rumusnya sendiri, mengabaikan toleransi per termin,
    dan menambah item AR TANPA jurnal: denda muncul di tagihan pembeli tetapi tidak pernah
    ada di buku besar. Sekarang tombol "Denda" pada daftar penagihan memakai mesin yang
    sama dengan layar Rencana Bayar & portal — satu rumus, satu jurnal, idempoten.
    """
    out = await lf.apply(org_id, deal_id, actor)
    total = sum(int(c["amount"]) for c in out.get("created") or [])
    tot = (out.get("assessment") or {}).get("totals") or {}
    return {"deal_id": deal_id, "denda": total, "replay": out.get("replay", False),
            "created": out.get("created") or [],
            "denda_charged_total": tot.get("denda_charged", total)}


# ----------------------------- Cash-flow projection -----------------------------
def _period_index(dt, periods):
    if not dt:
        return None
    for i, p in enumerate(periods):
        if p["start"] <= dt < p["end"]:
            return i
    return None


def _build_periods(bucket, horizon):
    today = now()
    periods = []
    if bucket == "week":
        start = (today - timedelta(days=today.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        for i in range(horizon):
            s = start + timedelta(weeks=i)
            periods.append({"label": "Mgg " + s.strftime("%d %b"), "start": s, "end": s + timedelta(weeks=1)})
    else:
        y, m = today.year, today.month
        for i in range(horizon):
            mm = (m - 1 + i) % 12 + 1
            yy = y + (m - 1 + i) // 12
            s = datetime(yy, mm, 1, tzinfo=timezone.utc)
            nm = mm % 12 + 1
            ny = yy + (1 if mm == 12 else 0)
            periods.append({"label": s.strftime("%b %Y"), "start": s, "end": datetime(ny, nm, 1, tzinfo=timezone.utc)})
    return periods


async def cashflow_projection(org_id=ORG_ID, bucket="month", horizon=6) -> dict:
    bucket = "week" if bucket == "week" else "month"
    horizon = max(1, min(int(horizon or 6), 24))
    periods = _build_periods(bucket, horizon)
    first_start = periods[0]["start"]
    inflow = [0] * horizon
    outflow = [0] * horizon

    invoices = await db.ar_invoices.find(
        {"org_id": org_id, "status": {"$in": ["unpaid", "partial"]}}, {"_id": 0}).to_list(2000)
    for inv in invoices:
        for it in inv.get("items", []):
            rem = it["amount"] - it.get("paid_amount", 0)
            if rem <= 0:
                continue
            due = _parse(it.get("due_date"))
            if not due:
                continue
            idx = _period_index(due, periods)
            if idx is not None:
                inflow[idx] += rem
            elif due < first_start:
                inflow[0] += rem  # tunggakan -> diharapkan tertagih pada periode berjalan

    bills = await db.ap_invoices.find({"org_id": org_id}, {"_id": 0}).to_list(2000)
    for b in bills:
        if b.get("status") != "paid":
            out = b.get("outstanding", 0)
            if out > 0:
                due = _parse(b.get("due_date"))
                idx = _period_index(due, periods) if due else None
                if idx is not None:
                    outflow[idx] += out
                elif due and due < first_start:
                    outflow[0] += out
        if not b.get("retention_released") and b.get("retention_held", 0) > 0:
            rdue = _parse(b.get("release_due_at"))
            idx = _period_index(rdue, periods) if rdue else None
            if idx is not None:
                outflow[idx] += b.get("retention_held", 0)

    out_periods = []
    cumulative = 0
    for i, p in enumerate(periods):
        net = inflow[i] - outflow[i]
        cumulative += net
        out_periods.append({"label": p["label"], "inflow": inflow[i], "outflow": outflow[i],
                            "net": net, "cumulative": cumulative})
    return {
        "bucket": bucket, "periods": out_periods,
        "totals": {"inflow": sum(inflow), "outflow": sum(outflow),
                   "net": sum(inflow) - sum(outflow), "ending": cumulative},
        "note": NOTE,
    }


# ----------------------------- Revenue report -----------------------------
async def revenue_report(org_id=ORG_ID) -> dict:
    revs = await db.revenue_recognitions.find({"org_id": org_id}, {"_id": 0}).sort("recognized_at", -1).to_list(2000)
    rows = []
    for r in revs:
        unit = await db.units.find_one({"id": r.get("unit_id")}, {"_id": 0, "code": 1}) or {}
        rows.append({"unit_code": unit.get("code"), "revenue": r.get("revenue", 0),
                     "cogs": r.get("cogs", 0), "margin": r.get("margin", 0),
                     "recognized_at": r.get("recognized_at"), "recognized_by": r.get("recognized_by")})
    totals = {"revenue": sum(x["revenue"] for x in rows), "cogs": sum(x["cogs"] for x in rows),
              "margin": sum(x["margin"] for x in rows), "count": len(rows)}
    return {"rows": rows, "totals": totals, "note": NOTE}


# ----------------------------- Report dataset (for PDF export) -----------------------------
_BUCKET_LABELS = [("current", "Lancar"), ("1-30", "1-30 hari"), ("31-60", "31-60 hari"),
                  ("61-90", "61-90 hari"), (">90", "> 90 hari")]


async def report_dataset(kind, org_id=ORG_ID) -> dict:
    if kind == "ar-aging":
        ag = await fe.ar_aging(org_id)
        rows = [[lbl, _rp(ag["buckets"][k])] for k, lbl in _BUCKET_LABELS]
        return {"title": "Laporan Aging Piutang (AR)", "subtitle": f"DSO ~{ag['dso']} hari",
                "columns": ["Kategori Umur", "Nilai"], "rows": rows, "total_row": ["Total", _rp(ag["total"])]}
    if kind == "ap-aging":
        ag = await fe.ap_aging(org_id)
        rows = [[lbl, _rp(ag["buckets"][k])] for k, lbl in _BUCKET_LABELS]
        return {"title": "Laporan Aging Utang (AP)", "subtitle": f"Retensi ditahan {_rp(ag['retention_held'])}",
                "columns": ["Kategori Umur", "Nilai"], "rows": rows, "total_row": ["Total", _rp(ag["total"])]}
    if kind == "revenue":
        rep = await revenue_report(org_id)
        rows = [[r["unit_code"] or "-", _rp(r["revenue"]), _rp(r["cogs"]), _rp(r["margin"]), _fmt_date(r["recognized_at"])]
                for r in rep["rows"]]
        tt = rep["totals"]
        return {"title": "Laporan Pengakuan Pendapatan (PSAK 72)", "subtitle": f"{tt['count']} unit diserahterimakan",
                "columns": ["Unit", "Pendapatan", "COGS", "Margin", "Tgl BAST"], "rows": rows,
                "total_row": ["Total", _rp(tt["revenue"]), _rp(tt["cogs"]), _rp(tt["margin"]), ""]}
    if kind == "commissions":
        coms = await db.commissions.find({"org_id": org_id}, {"_id": 0}).sort("created_at", -1).to_list(2000)
        rows = [[c.get("unit_code") or "-", c.get("assigned_to") or "-", c.get("scheme_name") or "-",
                 _rp(c.get("amount", 0)), c.get("status", "-")] for c in coms]
        total = sum(c.get("amount", 0) for c in coms)
        return {"title": "Laporan Komisi Sales", "subtitle": f"{len(coms)} komisi",
                "columns": ["Unit", "Sales", "Skema", "Komisi", "Status"], "rows": rows,
                "total_row": ["Total", "", "", _rp(total), ""]}
    if kind == "collections":
        wl = await collections_worklist(org_id)
        rows = [[r["unit_code"] or "-", r["lead_name"] or "-", _fmt_date(r["next_due"]),
                 str(r["days_overdue"]), _rp(r["overdue_amount"]), _rp(r["denda_estimate"])]
                for r in wl["rows"]]
        tt = wl["totals"]
        return {"title": "Worklist Penagihan (Collections)", "subtitle": f"{tt['count_overdue']} akun menunggak",
                "columns": ["Unit", "Pembeli", "Jatuh Tempo", "Telat (hari)", "Tunggakan", "Denda"], "rows": rows,
                "total_row": ["Total", "", "", "", _rp(tt["overdue_total"]), _rp(tt["denda_total"])]}
    if kind == "cashflow":
        cf = await cashflow_projection(org_id, "month", 6)
        rows = [[p["label"], _rp(p["inflow"]), _rp(p["outflow"]), _rp(p["net"]), _rp(p["cumulative"])]
                for p in cf["periods"]]
        tt = cf["totals"]
        return {"title": "Proyeksi Arus Kas", "subtitle": "Horizon 6 bulan",
                "columns": ["Periode", "Kas Masuk", "Kas Keluar", "Net", "Kumulatif"], "rows": rows,
                "total_row": ["Total", _rp(tt["inflow"]), _rp(tt["outflow"]), _rp(tt["net"]), ""]}
    raise ValueError(f"Jenis laporan tidak dikenal: {kind}")
