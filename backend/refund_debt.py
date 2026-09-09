"""LAPORAN UTANG REFUND (akun `2-1460`) + PROYEKSI KASNYA — Fase 59.

## Utang yang dibayar berkas ini

Fase 56C membuat pembatalan berjurnal: keputusan Manajer Keuangan melahirkan **utang refund**
pada akun `2-1460`, dan pembayarannya mengurangi utang itu dari kas/bank. Yang tidak pernah
ada: **kapan** uang itu harus keluar. Kewajiban tanpa tanggal tidak bisa dipakai
merencanakan kas — dan `CancellationsPanel` hanya menjumlahkan sisa refund dari baris yang
sedang tampil, jadi angkanya berubah begitu daftarnya disaring.

## Aturan yang dipegang

1. **Jatuh tempo dihitung dari KEPUTUSAN**, bukan dari pengajuan: utangnya lahir saat
   keputusan disetujui (`decision.at`) + `cancellation.refund_due_days` hari.
2. **Yang TERTAHAN tidak dikarang tanggalnya.** Bila ketentuan SPR menahan pembayaran sampai
   unit terjual kembali, jatuh temponya `null` dengan sebab tertulis — bukan "jatuh tempo
   hari ini", dan bukan pula dibuang dari total. Ia muncul pada baris "belum bisa
   dijadwalkan" di proyeksi kas.
3. **Umur dihitung dari tanggal yang sama** (0-30/31-60/61-90/>90 hari sejak keputusan),
   sehingga laporan ini bisa dibandingkan dengan aging piutang & utang.
4. **Angka dibandingkan dengan BUKU BESAR.** Total sisa menurut dokumen pembatalan
   disandingkan dengan saldo akun `2-1460`; selisihnya ditampilkan apa adanya. Laporan yang
   tidak pernah bisa salah adalah laporan yang tidak pernah diperiksa.
"""
from datetime import datetime, timedelta, timezone

import cancellation_engine as cx
import gl_engine as gl
import reference as ref
import settings_store as cfg
from db import ORG_ID, db

KEY_DUE_DAYS = "cancellation.refund_due_days"
AKUN_UTANG_REFUND = cx.AKUN_UTANG_REFUND


def _rp(v) -> str:
    return f"Rp {int(v or 0):,}".replace(",", ".")


def _parse(iso):
    if not iso:
        return None
    try:
        d = datetime.fromisoformat(str(iso))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _fmt(iso) -> str:
    d = _parse(iso)
    return d.strftime("%d %b %Y") if d else "belum bisa dijadwalkan"


def _bucket(days: int) -> str:
    if days <= 30:
        return "0-30"
    if days <= 60:
        return "31-60"
    if days <= 90:
        return "61-90"
    return ">90"


def _periods(horizon: int) -> list:
    today = datetime.now(timezone.utc)
    out = []
    for i in range(horizon):
        mm = (today.month - 1 + i) % 12 + 1
        yy = today.year + (today.month - 1 + i) // 12
        start = datetime(yy, mm, 1, tzinfo=timezone.utc)
        nm, ny = mm % 12 + 1, yy + (1 if mm == 12 else 0)
        out.append({"label": start.strftime("%b %Y"), "start": start,
                    "end": datetime(ny, nm, 1, tzinfo=timezone.utc), "amount": 0})
    return out


async def report(org: str = ORG_ID, *, horizon: int = 6) -> dict:
    """Utang refund yang BELUM dibayar: jatuh tempo, umur, dan proyeksi kas keluarnya."""
    horizon = max(1, min(int(horizon or 6), 24))
    due_days = int(await cfg.get(KEY_DUE_DAYS, org_id=org) or 30)
    docs = await db.cancellations.find(
        {"org_id": org, "state": {"$in": list(cx.APPROVED_STATES)}},
        {"_id": 0}).sort("created_at", -1).to_list(1000)
    now = datetime.now(timezone.utc)
    periods = _periods(horizon)
    rows, buckets = [], {b: 0 for b in ref.values("refund_age_bucket")}
    unscheduled = 0
    for doc in docs:
        enriched = await cx.enrich(org, doc)
        sisa = int(enriched.get("refund_outstanding") or 0)
        if sisa <= 0:
            continue
        decided_at = (doc.get("decision") or {}).get("at")
        d = _parse(decided_at)
        hold = enriched.get("refund_hold")
        tertahan = bool(hold and hold.get("code") == "menunggu_penjualan_ulang")
        due = (d + timedelta(days=due_days)) if (d and not tertahan) else None
        if tertahan:
            state = "tertahan"
        elif due and due < now:
            state = "terlewat"
        elif due and (due - now).days <= 7:
            state = "segera"
        else:
            state = "terjadwal"
        age_days = (now - d).days if d else 0
        bucket = _bucket(age_days)
        buckets[bucket] = buckets.get(bucket, 0) + sisa
        if due is None:
            unscheduled += sisa
        else:
            idx = next((i for i, p in enumerate(periods)
                        if p["start"] <= due < p["end"]), None)
            if idx is None:
                # Jatuh tempo yang sudah LEWAT tetap kas keluar yang harus direncanakan:
                # ia jatuh ke periode berjalan, bukan hilang dari proyeksi.
                if due < periods[0]["start"]:
                    periods[0]["amount"] += sisa
                else:
                    unscheduled += sisa
            else:
                periods[idx]["amount"] += sisa
        s = doc.get("settlement") or {}
        rows.append({
            "id": doc.get("id"), "number": doc.get("number"),
            "customer_id": doc.get("customer_id"),
            "customer_name": doc.get("customer_name"), "unit_code": doc.get("unit_code"),
            "contract_number": doc.get("contract_number"),
            "state": doc.get("state"),
            "state_label": ref.label_of("cancel_state", doc.get("state") or ""),
            "decided_at": decided_at, "decided_by": (doc.get("decision") or {}).get("by"),
            "payable_total": int(s.get("payable_total") or 0),
            "refund_paid_total": int(doc.get("refund_paid_total") or 0),
            "refund_outstanding": sisa,
            "due_date": due.isoformat() if due else None,
            "due_state": state, "due_state_label": ref.label_of("refund_due_state", state),
            "age_days": age_days, "age_bucket": bucket,
            "age_bucket_label": ref.label_of("refund_age_bucket", bucket),
            "hold": hold,
            "cut_pct": s.get("cut_pct"), "received_total": s.get("received_total"),
        })
    rows.sort(key=lambda r: (r["due_date"] is None, str(r["due_date"] or ""),
                            -r["refund_outstanding"]))
    total = sum(r["refund_outstanding"] for r in rows)
    saldo = await gl.account_balances(org)
    gl_balance = int((saldo.get(AKUN_UTANG_REFUND) or {}).get("balance") or 0)
    return {
        "rows": rows,
        "totals": {
            "count": len(rows), "outstanding": total,
            "overdue": sum(r["refund_outstanding"] for r in rows
                           if r["due_state"] == "terlewat"),
            "due_soon": sum(r["refund_outstanding"] for r in rows
                            if r["due_state"] == "segera"),
            "held": sum(r["refund_outstanding"] for r in rows
                        if r["due_state"] == "tertahan"),
        },
        "buckets": buckets,
        "projection": {
            "bucket": "month",
            "periods": [{"label": p["label"], "outflow": p["amount"]} for p in periods],
            "unscheduled": unscheduled,
            "unscheduled_note": (
                "Nominal ini BELUM bisa dijadwalkan: ketentuan SPR menahan pembayarannya "
                "sampai unit yang dibatalkan terjual kembali. Ia tetap kewajiban nyata, jadi "
                "tidak dibuang dari total — hanya tidak punya bulan."),
        },
        "ledger": {
            "account_code": AKUN_UTANG_REFUND,
            "account_name": (saldo.get(AKUN_UTANG_REFUND) or {}).get("name")
            or "Utang Refund",
            "balance": gl_balance, "worksheet": total, "difference": gl_balance - total,
            "matched": gl_balance == total,
            "note": ("Saldo buku besar dan jumlah sisa refund pada dokumen pembatalan "
                     "seharusnya SAMA. Selisih berarti ada jurnal refund yang tidak punya "
                     "dokumen (atau sebaliknya) — itu temuan, bukan pembulatan."),
        },
        "due_days": due_days,
        "note": ("Jatuh tempo dihitung dari tanggal KEPUTUSAN pembatalan + "
                 f"{due_days} hari (Pusat Konfigurasi → {KEY_DUE_DAYS}). Utang yang tertahan "
                 "ketentuan SPR sengaja TIDAK diberi tanggal karangan."),
    }


async def dataset(org: str = ORG_ID, *, horizon: int = 6) -> dict:
    """Bahan cetak PDF — isi SAMA dengan layar (satu sumber angka)."""
    rep = await report(org, horizon=horizon)
    rows = [[r["number"] or "-", f"{r['customer_name'] or '-'} · {r['unit_code'] or '-'}",
             _fmt(r["decided_at"]), _fmt(r["due_date"]), r["due_state_label"],
             r["age_bucket_label"], _rp(r["refund_outstanding"])] for r in rep["rows"]]
    t = rep["totals"]
    return {
        "title": "Laporan Utang Refund (akun 2-1460)",
        "subtitle": (f"{t['count']} kewajiban · lewat jatuh tempo {_rp(t['overdue'])} · "
                     f"tertahan {_rp(t['held'])} · saldo buku besar "
                     f"{_rp(rep['ledger']['balance'])}"),
        "columns": ["Nomor", "Pembeli / unit", "Diputus", "Jatuh tempo", "Keadaan", "Umur",
                    "Sisa"],
        "rows": rows,
        "total_row": ["Total", "", "", "", "", "", _rp(t["outstanding"])],
        "report": rep,
    }
