"""LAPORAN KERINGANAN DENDA (Fase 59) — siapa meringankan apa, berapa, kapan, kenapa.

## Kenapa berkas ini ada

Fase 58 membuat keringanan denda berjejak: nominal semula, alasan tertulis, pemberi
keringanan, dan jurnal baliknya semuanya tersimpan pada baris denda di `ar_invoices.items`.
Tetapi jejak itu hanya bisa dibaca **satu pembeli pada satu waktu**, dari tab Rencana Bayar
pembeli yang bersangkutan. Untuk rapat direksi, itu sama dengan tidak ada: tidak ada yang
bisa menjawab "bulan ini kita meringankan berapa, oleh siapa, dan dengan alasan apa"
tanpa membuka puluhan profil pembeli satu per satu.

## Aturan yang dipegang

1. **Tidak ada angka kedua.** Nominal keringanan dibaca dari baris denda yang sama dengan
   yang dipakai layar & jurnal (`waived_amount`), bukan dihitung ulang di sini.
2. **Alasan ikut dilaporkan.** Keringanan tanpa alasan tidak mungkin ada (mesin menolaknya),
   jadi laporan yang menyembunyikan alasan justru membuang bukti paling penting.
3. **Rekapitulasi per PEMBERI keringanan.** Pertanyaan pengawasan yang sebenarnya bukan
   "berapa totalnya" melainkan "siapa yang memutuskan sebanyak itu".
4. **Lingkup data dihormati.** Sales yang hanya boleh melihat transaksinya sendiri membaca
   laporan yang sudah dipersempit di server — bukan disaring di peramban.
"""
from datetime import datetime, timezone

from db import ORG_ID, db


def _rp(v) -> str:
    return f"Rp {int(v or 0):,}".replace(",", ".")


def _fmt(iso) -> str:
    try:
        return datetime.fromisoformat(str(iso)).strftime("%d %b %Y")
    except (TypeError, ValueError):
        return "-"


def _in_range(at: str, date_from: str | None, date_to: str | None) -> bool:
    """Penyaringan periode memakai perbandingan ISO (tanggal keringanan = `waived_at`)."""
    day = str(at or "")[:10]
    if not day:
        return False
    if date_from and day < date_from:
        return False
    if date_to and day > date_to:
        return False
    return True


async def waivers(org: str = ORG_ID, *, date_from: str | None = None,
                  date_to: str | None = None, deal_id: str | None = None,
                  own_email: str | None = None) -> dict:
    """Laporan keringanan denda. `own_email` = lingkup baris untuk peran ber-scope sales."""
    # Dicari SEMUA tagihan yang punya baris denda — bukan hanya yang punya keringanan.
    # Kalau disaring ke `items.waived`, angka pembanding "denda masih tertagih" hanya
    # menjumlahkan denda pada pembeli yang kebetulan pernah diberi keringanan: pembanding
    # yang bergerak mengikuti keringanan adalah pembanding yang tidak berarti.
    query: dict = {"org_id": org, "items.is_penalty": True}
    if deal_id:
        query["deal_id"] = deal_id
    if own_email:
        query["assigned_to"] = own_email
    invoices = await db.ar_invoices.find(query, {"_id": 0}).to_list(3000)
    rows, charged_total = [], 0
    for inv in invoices:
        for it in inv.get("items") or []:
            if not it.get("is_penalty"):
                continue
            if not it.get("waived"):
                charged_total += int(it.get("amount") or 0)
                continue
            if not _in_range(it.get("waived_at"), date_from, date_to):
                continue
            rows.append({
                "penalty_id": it.get("id"), "deal_id": inv.get("deal_id"),
                "unit_code": inv.get("unit_code"), "lead_name": inv.get("lead_name"),
                "customer_id": inv.get("customer_id"),
                "assigned_to": inv.get("assigned_to"),
                "term_label": it.get("penalty_for_label") or it.get("label"),
                "period": it.get("period"), "days_late": int(it.get("days_late") or 0),
                "amount": int(it.get("waived_amount") or 0),
                "reason": it.get("waived_reason"),
                "waived_by": it.get("waived_by"), "waived_at": it.get("waived_at"),
                "journal_id": it.get("waiver_journal_id"),
                "charged_journal_id": it.get("journal_id"),
                "charged_at": it.get("created_at"), "charged_by": it.get("created_by"),
            })
    rows.sort(key=lambda r: str(r["waived_at"] or ""), reverse=True)
    total = sum(r["amount"] for r in rows)
    by_actor: dict = {}
    for r in rows:
        a = by_actor.setdefault(r["waived_by"] or "-", {"actor": r["waived_by"] or "-",
                                                        "count": 0, "amount": 0})
        a["count"] += 1
        a["amount"] += r["amount"]
    by_month: dict = {}
    for r in rows:
        key = str(r["waived_at"] or "")[:7] or "-"
        m = by_month.setdefault(key, {"month": key, "count": 0, "amount": 0})
        m["count"] += 1
        m["amount"] += r["amount"]
    return {
        "rows": rows,
        "by_actor": sorted(by_actor.values(), key=lambda x: -x["amount"]),
        "by_month": sorted(by_month.values(), key=lambda x: x["month"]),
        "totals": {"count": len(rows), "amount": total,
                   "charged_outstanding": charged_total,
                   "deals": len({r["deal_id"] for r in rows}),
                   "actors": len(by_actor)},
        "filter": {"date_from": date_from, "date_to": date_to, "deal_id": deal_id,
                   "scoped_to": own_email},
        # Kalimat ini dibaca direksi. Ia menyebut ARTI angkanya, bukan mengulang angkanya:
        # keringanan yang besar belum tentu salah — yang salah adalah keringanan tanpa
        # alasan, dan itu tidak mungkin ada karena mesin menolaknya.
        "note": ("Setiap baris di bawah adalah keputusan Manajer Keuangan yang MEMBALIK "
                 "jurnal denda (Dr Pendapatan Denda / Cr Piutang Usaha) dan wajib beralasan "
                 "tertulis. Angka di sini sama dengan buku besar, bukan perkiraan layar."),
    }


async def dataset(org: str = ORG_ID, *, date_from: str | None = None,
                  date_to: str | None = None, deal_id: str | None = None,
                  own_email: str | None = None) -> dict:
    """Bahan cetak PDF (dipakai `pdf_utils.build_table_pdf`) — isi SAMA dengan layar."""
    rep = await waivers(org, date_from=date_from, date_to=date_to, deal_id=deal_id,
                        own_email=own_email)
    periode = (f"{date_from or 'awal'} s/d {date_to or 'hari ini'}")
    rows = [[r["unit_code"] or "-", r["lead_name"] or "-", r["term_label"] or "-",
             _rp(r["amount"]), r["waived_by"] or "-", _fmt(r["waived_at"]),
             (r["reason"] or "-")[:80]] for r in rep["rows"]]
    return {
        "title": "Laporan Keringanan Denda Keterlambatan",
        "subtitle": (f"Periode {periode} · {rep['totals']['count']} keringanan oleh "
                     f"{rep['totals']['actors']} pemberi keputusan"),
        "columns": ["Unit", "Pembeli", "Termin", "Diringankan", "Oleh", "Tanggal", "Alasan"],
        "rows": rows,
        "total_row": ["Total", "", "", _rp(rep["totals"]["amount"]), "", "", ""],
        "report": rep,
    }


def today_iso() -> str:
    return datetime.now(timezone.utc).date().isoformat()
