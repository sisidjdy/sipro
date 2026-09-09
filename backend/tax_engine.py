"""Tax engine (EPIC 3.3 Perpajakan) — worksheet-level di atas tax_records + AR/AP.

Sumber data:
- **PPN Keluaran**, **PPh Final Pasal 4(2)**, **BPHTB**: koleksi `tax_records`
  (dihasilkan otomatis per-deal saat jadwal AR dibuat oleh finance_engine).
- **PPN Masukan (estimasi)**: dari tagihan AP (`ap_invoices`), metode *inklusif*
  (tagihan dianggap sudah termasuk PPN) → DPP = tagihan × 100/(100+rate).
- **Faktur Pajak Keluaran**: koleksi `faktur_pajak` (nomor seri + DPP + PPN +
  identitas pembeli) + PDF via `pdf_utils`.

JUJUR: ini worksheet/estimasi internal, BUKAN e-Faktur / e-Bupot resmi DJP.
Uang IDR integer; waktu UTC ISO-8601.
"""
import logging
from datetime import datetime

import sequences as seq
import reference as ref
from db import db, ORG_ID
from core_utils import new_id, now_iso, period_of  # noqa: F401 — CFG-01
import finance_engine as fe

logger = logging.getLogger("sipro.tax")

TAX_NOTE = "Estimasi worksheet SIPRO — bukan e-Faktur/e-Bupot resmi DJP; konfirmasi ke penasihat pajak."
# SSOT: jenis & status pajak diambil dari reference.py (bukan daftar duplikat).
TAX_TYPES = tuple(ref.values("tax_type"))
RECORD_STATUSES = tuple(ref.values("tax_status"))


# ----------------------------- PPN Masukan (input VAT) -----------------------------
async def ppn_input(org_id=ORG_ID, period=None) -> dict:
    """Estimasi PPN Masukan dari tagihan AP (metode inklusif)."""
    cfg = await fe.get_finance_config(org_id)
    rate = float(cfg.get("ppn_rate") or 0)
    bills = await db.ap_invoices.find({"org_id": org_id}, {"_id": 0}).to_list(5000)
    dpp_total = ppn_total = 0
    rows = []
    for b in bills:
        p = period_of(b.get("created_at"))
        if period and p != period:
            continue
        claimed = int(b.get("claimed", 0) or 0)
        dpp = round(claimed * 100 / (100 + rate)) if rate else claimed
        ppn = claimed - dpp
        dpp_total += dpp
        ppn_total += ppn
        rows.append({"bill_id": b.get("id"), "vendor": b.get("vendor"), "period": p,
                     "claimed": claimed, "dpp": int(dpp), "ppn": int(ppn),
                     "created_at": b.get("created_at")})
    return {"rate": rate, "dpp": int(dpp_total), "ppn": int(ppn_total),
            "count": len(rows), "rows": rows}


# ----------------------------- Summary / SPT Masa PPN -----------------------------
async def tax_summary(org_id=ORG_ID, period=None) -> dict:
    recs = await db.tax_records.find({"org_id": org_id}, {"_id": 0}).to_list(10000)
    out = {"ppn": 0, "pph": 0, "bphtb": 0}
    counts = {t: 0 for t in TAX_TYPES}
    status_agg = {t: {"pending": 0, "reported": 0, "paid": 0} for t in TAX_TYPES}
    for r in recs:
        if period and period_of(r.get("created_at")) != period:
            continue
        t = r.get("type")
        if t not in out:
            continue
        amt = int(r.get("amount", 0) or 0)
        out[t] += amt
        counts[t] += 1
        st = r.get("status", "pending")
        status_agg[t].setdefault(st, 0)
        status_agg[t][st] += amt
    inp = await ppn_input(org_id, period)
    ppn_net = out["ppn"] - inp["ppn"]
    faktur_count = await db.faktur_pajak.count_documents({"org_id": org_id})
    return {
        "period": period,
        "ppn_keluaran": out["ppn"],
        "ppn_masukan": inp["ppn"],
        "ppn_net": ppn_net,  # >0 kurang bayar; <0 lebih bayar
        "ppn_status": "kurang_bayar" if ppn_net > 0 else ("lebih_bayar" if ppn_net < 0 else "nihil"),
        "pph_final": out["pph"],
        "bphtb": out["bphtb"],
        "counts": counts,
        "status_agg": status_agg,
        "ppn_input_detail": {"dpp": inp["dpp"], "ppn": inp["ppn"],
                             "count": inp["count"], "rate": inp["rate"]},
        "faktur_count": faktur_count,
        "note": TAX_NOTE,
    }


async def list_periods(org_id=ORG_ID) -> list:
    recs = await db.tax_records.find({"org_id": org_id}, {"_id": 0, "created_at": 1}).to_list(10000)
    bills = await db.ap_invoices.find({"org_id": org_id}, {"_id": 0, "created_at": 1}).to_list(10000)
    periods = set()
    for r in recs + bills:
        p = period_of(r.get("created_at"))
        if p:
            periods.add(p)
    return sorted(periods, reverse=True)


async def enrich_records(org_id, records) -> list:
    deal_ids = list({r.get("deal_id") for r in records if r.get("deal_id")})
    ars = {a["deal_id"]: a for a in
           await db.ar_invoices.find({"org_id": org_id, "deal_id": {"$in": deal_ids}}, {"_id": 0}).to_list(5000)}
    out = []
    for r in records:
        ar = ars.get(r.get("deal_id")) or {}
        out.append({**r, "unit_code": ar.get("unit_code"), "buyer_name": ar.get("lead_name"),
                    "period": period_of(r.get("created_at"))})
    return out


# ----------------------------- Faktur Pajak Keluaran -----------------------------
async def next_faktur_number(org_id, transaction_code="010") -> str:
    yy = datetime.now().strftime("%y")
    n = await seq.next_seq("faktur", org_id)
    return f"{transaction_code}.000-{yy}.{str(n).zfill(8)}"


async def faktur_candidates(org_id=ORG_ID) -> list:
    """Deal yang belum punya faktur AKTIF.

    Dulu daftar ini membuang deal yang punya faktur APA PUN — termasuk faktur yang sudah
    DIBATALKAN. Akibatnya satu pembatalan mengunci deal itu selamanya: fakturnya tidak sah,
    tetapi sistem juga tidak pernah menawarkannya lagi untuk diterbitkan. Yang menghalangi
    penerbitan sekarang hanya faktur berstatus `issued` (faktur pengganti sudah menggantikan
    yang lama, jadi ia sendiri yang aktif).
    """
    issued = {f.get("deal_id") for f in await db.faktur_pajak.find(
        {"org_id": org_id, "status": {"$in": [None, "issued"]}},
        {"_id": 0, "deal_id": 1}).to_list(5000)}
    ars = await db.ar_invoices.find({"org_id": org_id}, {"_id": 0}).to_list(2000)
    return [{"deal_id": a["deal_id"], "unit_code": a.get("unit_code"),
             "buyer_name": a.get("lead_name"), "price": int(a.get("price", 0) or 0)}
            for a in ars if a.get("deal_id") not in issued]


async def issue_faktur(org_id, deal_id, actor, buyer_npwp=None, transaction_code="010") -> dict:
    """Terbitkan Faktur Pajak Keluaran untuk sebuah deal.

    Idempoten terhadap faktur yang MASIH BERLAKU saja: faktur yang sudah dibatalkan tidak
    boleh dikembalikan sebagai "sudah ada" (dulu begitu — pemakai menekan Terbitkan, sistem
    menjawab 200 dengan faktur BATAL, dan tidak ada faktur sah yang pernah lahir).
    """
    existing = await db.faktur_pajak.find_one(
        {"org_id": org_id, "deal_id": deal_id, "status": {"$in": [None, "issued"]}}, {"_id": 0})
    if existing:
        return existing
    ar = await db.ar_invoices.find_one({"org_id": org_id, "deal_id": deal_id}, {"_id": 0})
    if not ar:
        raise ValueError("Jadwal AR belum dibuat untuk deal ini.")
    price = int(ar.get("price", 0) or 0)
    cfg = await fe.get_finance_config(org_id)
    ppn_rate = float(cfg.get("ppn_rate") or 0)
    dpp = price
    ppn = round(dpp * ppn_rate / 100)
    buyer_name = ar.get("lead_name") or "-"
    npwp = buyer_npwp
    if not npwp and buyer_name and buyer_name != "-":
        cust = await db.customers.find_one({"org_id": org_id, "name": buyer_name}, {"_id": 0, "npwp": 1})
        npwp = (cust or {}).get("npwp")
    ts = now_iso()
    doc = {
        "id": new_id(), "org_id": org_id, "deal_id": deal_id, "ar_invoice_id": ar.get("id"),
        "number": await next_faktur_number(org_id, transaction_code),
        "transaction_code": transaction_code,
        "unit_code": ar.get("unit_code"), "buyer_name": buyer_name, "buyer_npwp": npwp,
        "dpp": int(dpp), "ppn": int(ppn), "ppn_rate": ppn_rate,
        "status": "issued", "issued_by": actor, "issued_at": ts, "period": period_of(ts),
        "created_at": ts, "updated_at": ts,
    }
    await db.faktur_pajak.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


def _rp(n) -> str:
    return "Rp " + f"{int(n or 0):,}".replace(",", ".")


def faktur_pdf_bytes(faktur: dict, org_name="PT SIPRO Land", *, layout=None, images=None) -> bytes:
    from pdf_utils import build_document_pdf
    content = (
        f"Kode & No. Seri Faktur : {faktur.get('number')}\n"
        f"Nama Pembeli : {faktur.get('buyer_name') or '-'}\n"
        f"NPWP Pembeli : {faktur.get('buyer_npwp') or '-'}\n"
        f"Unit : {faktur.get('unit_code') or '-'}\n"
        f"Tanggal Terbit : {str(faktur.get('issued_at') or '')[:10]}\n\n"
        f"Dasar Pengenaan Pajak (DPP) : {_rp(faktur.get('dpp'))}\n"
        f"PPN ({faktur.get('ppn_rate')}%) : {_rp(faktur.get('ppn'))}\n"
        f"Total (DPP + PPN) : {_rp(int(faktur.get('dpp', 0)) + int(faktur.get('ppn', 0)))}\n"
    )
    return build_document_pdf(
        title="Faktur Pajak (Keluaran)", doc_number=faktur.get("number") or "-",
        content=content, org_name=org_name, layout=layout, images=images,
        script_context={"date": str(faktur.get("issued_at") or "")[:10]},
        signatures=[{"role": "Pengusaha Kena Pajak", "name": org_name}],
    )
