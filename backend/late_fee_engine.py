"""MESIN TOLERANSI KETERLAMBATAN & DENDA BERJURNAL (Fase 58).

## Janji yang akhirnya dijalankan

Dokumen SPR yang dicetak sistem ini berbunyi: *"cicilan wajib dibayar setiap tanggal 7;
toleransi paling lambat tanggal 20"*. Sejak Fase 57A pemakai bahkan bisa menyusun toleransi
itu sendiri per termin (`payment_schemes.items[].grace_days`). Sampai Fase 57 angka itu tidak
dipakai siapa pun:

  * jadwal tagihan (`ar_invoices.items`) tidak membawa `grace_days`, jadi tenggangnya HILANG
    begitu skema diterjemahkan menjadi termin;
  * layar menandai termin **TERLAMBAT** pada H+1 — lebih cepat menuduh daripada kontraknya;
  * denda hanya angka perkiraan worksheet (`finance_reports.compute_denda`) dengan tarif &
    tenggang yang hidup di luar Pusat Konfigurasi, dan bila diterapkan tidak berjurnal;
  * tidak ada jalan resmi untuk MERINGANKAN denda, padahal itu keputusan yang paling sering
    diambil manusia dan paling perlu jejak.

## Aturan yang dipaksakan modul ini

1. **SATU mesin.** Keadaan termin (`late_state`), tenggang efektif, dan nominal denda hanya
   dihitung di sini. Layar staf, portal pembeli, daftar penagihan, dan jurnal membaca angka
   dari fungsi yang sama — tidak ada rumus kedua.
2. **Tenggang milik TERMIN, bukan milik kode.** `item.grace_days` (dari skema yang disusun
   pemakai) menang; bila termin tidak menyebutnya, dipakai bawaan Pusat Konfigurasi
   (`payment.late.grace_days`). Angka mati di kode tidak boleh menjadi kebijakan.
3. **Denda ditagihkan BERJURNAL.** Dr `1-1300 Piutang Usaha` / Cr `4-1400 Pendapatan Denda
   Keterlambatan`, idempoten per (termin, bulan) lewat `source_event`. Denda yang tidak
   berjurnal hanyalah angka di layar — bukan uang yang bisa ditagih dan dipertanggungjawabkan.
4. **Tidak pernah dobel.** Yang ditagihkan adalah SELISIH antara denda berjalan dan denda
   yang sudah pernah ditagihkan untuk termin itu (di luar yang diringankan).
5. **Keringanan bukan penghapusan jejak.** `waive()` membalik jurnalnya, menuntut alasan
   tertulis, dan hanya boleh dilakukan Manajer Keuangan — bukan orang yang menagihkannya.
6. **Batas atas & minimum.** Denda dibatasi `payment.late.max_pct_of_term` dari tunggakan
   termin dan diabaikan bila di bawah `payment.late.min_charge`, supaya tagihan tidak
   melampaui kewajaran maupun menerbitkan denda Rp 500.
"""
import logging
from datetime import datetime, timedelta, timezone

import gl_engine as gl
import reference as ref
import settings_store as cfg
from core_utils import new_id, now_iso
from db import ORG_ID, db
from engine import add_activity, emit
from finance_engine import notify_finance

logger = logging.getLogger("sipro.late_fee")

AKUN_PIUTANG = "1-1300"
AKUN_PENDAPATAN_DENDA = "4-1400"

KEY_GRACE = "payment.late.grace_days"
KEY_RATE = "payment.late.rate_pct_month"
KEY_CAP = "payment.late.max_pct_of_term"
KEY_MIN = "payment.late.min_charge"


def _rp(v) -> str:
    return f"Rp {int(v or 0):,}".replace(",", ".")


def _blk(code: str, detail: str) -> dict:
    return {"code": code, "label": ref.label_of("late_fee_block", code), "detail": detail}


def _parse(iso):
    if not iso:
        return None
    try:
        d = datetime.fromisoformat(str(iso))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _now():
    return datetime.now(timezone.utc)


# ============================================================ kebijakan
async def policy(org: str = ORG_ID) -> dict:
    """Kebijakan denda dari Pusat Konfigurasi (bisa diubah admin tanpa deploy)."""
    return {
        "grace_days": int(await cfg.get(KEY_GRACE, org_id=org) or 0),
        "rate_pct_month": float(await cfg.get(KEY_RATE, org_id=org) or 0),
        "max_pct_of_term": float(await cfg.get(KEY_CAP, org_id=org) or 0),
        "min_charge": int(await cfg.get(KEY_MIN, org_id=org) or 0),
    }


def policy_sentence(pol: dict) -> str:
    """Kalimat aturan DISUSUN MESIN dari kebijakan — bukan diketik layar."""
    return (f"Toleransi bawaan {pol['grace_days']} hari sesudah jatuh tempo; sesudah itu "
            f"denda {pol['rate_pct_month']:g}% per bulan dari tunggakan termin, dibatasi "
            f"{pol['max_pct_of_term']:g}% per termin. Toleransi yang tertulis pada termin "
            "kontrak selalu menang atas angka bawaan ini.")


def grace_of(item: dict, pol: dict) -> int:
    """Tenggang efektif satu termin: milik termin dulu, baru bawaan organisasi."""
    g = item.get("grace_days")
    return int(g) if g not in (None, "") else int(pol["grace_days"])


def denda_of(outstanding: int, days: int, pol: dict) -> int:
    """Denda berjalan satu termin (sudah dibatasi atas & bawah)."""
    if int(outstanding) <= 0 or int(days) <= 0 or pol["rate_pct_month"] <= 0:
        return 0
    kasar = round(int(outstanding) * (pol["rate_pct_month"] / 100.0) * (int(days) / 30.0))
    batas = round(int(outstanding) * (pol["max_pct_of_term"] / 100.0)) \
        if pol["max_pct_of_term"] > 0 else kasar
    nilai = min(kasar, batas)
    return 0 if nilai < int(pol["min_charge"] or 0) else nilai


# ============================================================ penilaian
def assess_item(item: dict, pol: dict, today: datetime | None = None) -> dict:
    """Keadaan satu termin terhadap jatuh tempo + tenggangnya (SSOT `late_state`)."""
    today = today or _now()
    amount = int(item.get("amount") or 0)
    paid = int(item.get("paid_amount") or 0)
    outstanding = max(0, amount - paid)
    grace = grace_of(item, pol)
    due = _parse(item.get("due_date"))
    grace_until = (due + timedelta(days=grace)) if due else None
    row = {
        "item_id": item.get("id"), "label": item.get("label"),
        "amount": amount, "paid_amount": paid, "outstanding": outstanding,
        "due_date": item.get("due_date"), "grace_days": grace,
        "grace_until": grace_until.isoformat() if grace_until else None,
        "event_based": bool(item.get("event_based") or item.get("event")),
        "days_past_due": 0, "days_late": 0, "grace_left_days": 0,
        "denda_running": 0, "is_penalty": bool(item.get("is_penalty")),
    }
    if outstanding <= 0:
        row["state"] = "lunas"
    elif not due or due > today:
        row["state"] = "menunggu"
    else:
        row["days_past_due"] = (today - due).days
        if grace_until and today <= grace_until:
            row["state"] = "dalam_tenggang"
            row["grace_left_days"] = max(0, (grace_until - today).days)
        else:
            row["state"] = "terlambat"
            row["days_late"] = max(0, row["days_past_due"] - grace)
            row["denda_running"] = denda_of(outstanding, row["days_late"], pol)
    row["state_label"] = ref.label_of("late_state", row["state"])
    return row


def _charged_map(items: list) -> dict:
    """Denda yang SUDAH ditagihkan per termin (keringanan tidak dihitung)."""
    out = {}
    for it in items:
        if not it.get("is_penalty") or it.get("waived"):
            continue
        key = it.get("penalty_for")
        out[key] = out.get(key, 0) + int(it.get("amount") or 0)
    return out


def _waived_days_map(items: list) -> dict:
    """Hari keterlambatan yang sudah DIRINGANKAN per termin.

    Tanpa ini, keringanan Manajer Keuangan bisa ditagihkan ulang oleh Keuangan pada menit
    berikutnya (denda berjalan kembali penuh) — keputusan manajerial yang bisa dibatalkan
    bawahannya bukan keputusan. Keringanan memaafkan keterlambatan SAMPAI hari itu; denda
    hanya berjalan lagi untuk hari-hari SESUDAHNYA.
    """
    out = {}
    for it in items:
        if not (it.get("is_penalty") and it.get("waived")):
            continue
        key = it.get("penalty_for")
        out[key] = max(int(out.get(key) or 0), int(it.get("days_late") or 0))
    return out


async def assess(org: str, deal_id: str) -> dict:
    """Pratinjau lengkap: kebijakan, keadaan tiap termin, denda berjalan & yang tertagih."""
    pol = await policy(org)
    inv = await db.ar_invoices.find_one({"org_id": org, "deal_id": deal_id}, {"_id": 0})
    if not inv:
        return {"deal_id": deal_id, "policy": pol, "policy_sentence": policy_sentence(pol),
                "rows": [], "penalties": [], "totals": {},
                "block": _blk("tanpa_tagihan", "Transaksi ini belum punya jadwal tagihan, "
                                               "jadi belum ada termin yang bisa terlambat.")}
    items = inv.get("items") or []
    charged = _charged_map(items)
    waived_days = _waived_days_map(items)
    rows, penalties = [], []
    for it in items:
        if it.get("is_penalty"):
            penalties.append({
                "item_id": it.get("id"), "label": it.get("label"),
                "amount": int(it.get("amount") or 0),
                "paid_amount": int(it.get("paid_amount") or 0),
                "penalty_for": it.get("penalty_for"),
                "penalty_for_label": it.get("penalty_for_label"),
                "period": it.get("period"), "days_late": int(it.get("days_late") or 0),
                "waived": bool(it.get("waived")),
                "waived_reason": it.get("waived_reason"),
                "waived_amount": int(it.get("waived_amount") or 0),
                "state": ("diringankan" if it.get("waived")
                          else ("dibayar" if int(it.get("paid_amount") or 0)
                                >= int(it.get("amount") or 0) > 0 else "ditagihkan")),
                "created_at": it.get("created_at"),
            })
            continue
        row = assess_item(it, pol)
        row["denda_charged"] = int(charged.get(it.get("id")) or 0)
        row["denda_waived_days"] = int(waived_days.get(it.get("id")) or 0)
        row["denda_waived_part"] = denda_of(row["outstanding"], row["denda_waived_days"], pol)
        row["denda_billable"] = max(0, row["denda_running"] - row["denda_charged"]
                                    - row["denda_waived_part"])
        rows.append(row)
    for p in penalties:
        p["state_label"] = ref.label_of("late_fee_state", p["state"])
    totals = {
        "overdue_outstanding": sum(r["outstanding"] for r in rows if r["state"] == "terlambat"),
        "in_grace_outstanding": sum(r["outstanding"] for r in rows
                                    if r["state"] == "dalam_tenggang"),
        "denda_running": sum(r["denda_running"] for r in rows),
        "denda_charged": sum(p["amount"] for p in penalties if not p["waived"]),
        "denda_waived": sum(p["waived_amount"] for p in penalties if p["waived"]),
        "denda_billable": sum(r["denda_billable"] for r in rows),
        "count_terlambat": sum(1 for r in rows if r["state"] == "terlambat"),
        "count_dalam_tenggang": sum(1 for r in rows if r["state"] == "dalam_tenggang"),
    }
    return {"deal_id": deal_id, "unit_code": inv.get("unit_code"),
            "lead_name": inv.get("lead_name"), "invoice_status": inv.get("status"),
            "policy": pol, "policy_sentence": policy_sentence(pol),
            "rows": rows, "penalties": penalties, "totals": totals,
            "block": _block_of(inv, rows, totals)}


def _block_of(inv: dict, rows: list, totals: dict) -> dict:
    """Sebab denda BELUM bisa ditagihkan (atau `None` bila sudah boleh)."""
    if inv.get("status") == "cancelled":
        return _blk("tagihan_dibatalkan",
                    "Tagihan transaksi ini sudah dibatalkan, jadi tidak ada termin yang "
                    "bisa dikenai denda.")
    if not any(r["state"] in ("terlambat", "dalam_tenggang") for r in rows):
        return _blk("tidak_ada_tunggakan",
                    "Tidak ada termin yang lewat jatuh tempo dan masih bersisa.")
    if totals["count_terlambat"] == 0:
        return _blk("masih_tenggang",
                    "Termin yang lewat tanggal masih berada di dalam masa toleransi yang "
                    "dijanjikan kontrak — belum boleh dikenai denda.")
    if totals["denda_billable"] <= 0:
        if totals["denda_waived"] > 0 and totals["denda_charged"] <= 0:
            return _blk("sudah_ditagihkan",
                        f"Denda untuk keterlambatan sampai hari ini sudah DIRINGANKAN "
                        f"({_rp(totals['denda_waived'])}). Denda baru hanya berjalan untuk "
                        "hari-hari sesudah keringanan diberikan.")
        if totals["denda_charged"] > 0:
            return _blk("sudah_ditagihkan",
                        f"Denda yang berlaku saat ini ({_rp(totals['denda_running'])}) sudah "
                        "ditagihkan seluruhnya.")
        return _blk("denda_nol",
                    "Denda terhitung nol: masih di bawah batas minimum yang ditetapkan "
                    "Pusat Konfigurasi.")
    return None


# ============================================================ penagihan
async def apply(org: str, deal_id: str, actor: str, *, item_id: str | None = None,
                client_ref: str | None = None) -> dict:
    """Tagihkan denda yang berlaku — BERJURNAL & idempoten per (termin, bulan).

    Yang ditagihkan adalah SELISIH denda berjalan dengan denda yang sudah pernah
    ditagihkan, jadi penekanan tombol dua kali pada hari yang sama tidak menagih dua kali.
    """
    inv = await db.ar_invoices.find_one({"org_id": org, "deal_id": deal_id}, {"_id": 0})
    if not inv:
        raise ValueError("Transaksi ini belum punya jadwal tagihan.")
    hitung = await assess(org, deal_id)
    if hitung["block"]:
        raise ValueError(hitung["block"]["detail"])
    target = [r for r in hitung["rows"]
              if r["denda_billable"] > 0 and (item_id is None or r["item_id"] == item_id)]
    if not target:
        raise ValueError("Tidak ada denda yang perlu ditagihkan untuk termin itu.")
    ts = now_iso()
    period = ts[:7]
    items = list(inv.get("items") or [])
    dibuat = []
    for r in target:
        event = f"late_fee:{deal_id}:{r['item_id']}:{period}"
        jr = await gl.post_journal(
            org, (f"Denda keterlambatan {r['label']} · unit {inv.get('unit_code') or '-'} "
                  f"({r['days_late']} hari lewat toleransi)"),
            [{"account_code": AKUN_PIUTANG, "debit": r["denda_billable"], "credit": 0},
             {"account_code": AKUN_PENDAPATAN_DENDA, "debit": 0,
              "credit": r["denda_billable"]}],
            source_type="late_fee", source_id=deal_id, source_event=event,
            source_deal_id=deal_id, posted_by=actor, auto=False)
        if any(i.get("journal_id") == jr.get("id") for i in items):
            # Jurnal yang sama sudah punya item denda: kiriman ulang, bukan denda kedua.
            continue
        pid = new_id()
        items.append({
            "id": pid, "label": (f"Denda Keterlambatan · {r['label']} "
                                 f"({hitung['policy']['rate_pct_month']:g}%/bln)"),
            "basis": "fixed", "value": r["denda_billable"], "amount": r["denda_billable"],
            "due_date": ts, "status": "unpaid", "paid_amount": 0, "is_penalty": True,
            "penalty_for": r["item_id"], "penalty_for_label": r["label"],
            "period": period, "days_late": r["days_late"], "grace_days": r["grace_days"],
            "journal_id": jr.get("id"), "created_by": actor, "created_at": ts,
            "client_ref": client_ref,
        })
        dibuat.append({"id": pid, "amount": r["denda_billable"], "term": r["label"],
                       "days_late": r["days_late"], "journal_id": jr.get("id")})
    if not dibuat:
        return {"created": [], "replay": True, "assessment": await assess(org, deal_id)}
    await _recalc(org, inv, items, ts)
    total = sum(d["amount"] for d in dibuat)
    await add_activity(entity_type="deal", entity_id=deal_id, type="system", actor=actor,
                       org_id=org,
                       body=(f"Denda keterlambatan {_rp(total)} ditagihkan untuk "
                             f"{len(dibuat)} termin (berjurnal)."))
    await notify_finance(org, "Denda keterlambatan ditagihkan",
                         (f"{_rp(total)} pada unit {inv.get('unit_code') or '-'} "
                          f"({inv.get('lead_name') or 'pembeli'})."),
                         "finance", "deal", deal_id, extra_emails=[inv.get("assigned_to")])
    await emit("late_fee.charged", "deal", deal_id, {"amount": total}, org_id=org)
    return {"created": dibuat, "replay": False, "assessment": await assess(org, deal_id)}


async def waive(org: str, deal_id: str, penalty_id: str, actor: str, *, reason: str,
                may_waive: bool = False) -> dict:
    """Keringanan denda — MEMBALIK jurnalnya, wajib beralasan, hanya Manajer Keuangan."""
    if not may_waive:
        raise ValueError("Hanya Manajer Keuangan yang boleh memberi keringanan denda.")
    if len((reason or "").strip()) < 10:
        raise ValueError("Alasan keringanan wajib minimal 10 huruf — keputusan ini dibaca "
                         "auditor.")
    inv = await db.ar_invoices.find_one({"org_id": org, "deal_id": deal_id}, {"_id": 0})
    if not inv:
        raise ValueError("Transaksi ini belum punya jadwal tagihan.")
    items = list(inv.get("items") or [])
    row = next((i for i in items if i.get("id") == penalty_id and i.get("is_penalty")), None)
    if not row:
        raise ValueError("Denda yang dimaksud tidak ditemukan pada jadwal tagihan.")
    if row.get("waived"):
        return {"waived": row, "replay": True}
    if int(row.get("paid_amount") or 0) > 0:
        raise ValueError("Denda ini sudah dibayar sebagian/penuh — keringanan tidak boleh "
                         "menghapus uang yang sudah diterima. Pakai pengembalian dana.")
    nilai = int(row.get("amount") or 0)
    ts = now_iso()
    jr = await gl.post_journal(
        org, (f"Keringanan denda keterlambatan · unit {inv.get('unit_code') or '-'}: "
              f"{reason.strip()}"),
        [{"account_code": AKUN_PENDAPATAN_DENDA, "debit": nilai, "credit": 0},
         {"account_code": AKUN_PIUTANG, "debit": 0, "credit": nilai}],
        source_type="late_fee_waiver", source_id=penalty_id,
        source_event=f"late_fee_waive:{penalty_id}", source_deal_id=deal_id,
        posted_by=actor, auto=False)
    row.update({"waived": True, "waived_amount": nilai, "waived_reason": reason.strip(),
                "waived_by": actor, "waived_at": ts, "waiver_journal_id": jr.get("id"),
                "amount": 0, "value": 0, "status": "cancelled"})
    await _recalc(org, inv, items, ts)
    await add_activity(entity_type="deal", entity_id=deal_id, type="system", actor=actor,
                       org_id=org,
                       body=f"Keringanan denda {_rp(nilai)} diberikan: {reason.strip()}")
    await emit("late_fee.waived", "deal", deal_id, {"amount": nilai}, org_id=org)
    return {"waived": row, "replay": False, "assessment": await assess(org, deal_id)}


async def _recalc(org: str, inv: dict, items: list, ts: str) -> None:
    """Total & sisa tagihan dihitung ulang dari item (denda ikut menjadi kewajiban)."""
    total = sum(int(i.get("amount") or 0) for i in items)
    paid = sum(int(i.get("paid_amount") or 0) for i in items)
    status = "paid" if total - paid <= 0 else ("partial" if paid > 0 else "unpaid")
    if inv.get("status") == "cancelled":
        status = "cancelled"
    await db.ar_invoices.update_one({"id": inv["id"], "org_id": org}, {"$set": {
        "items": items, "total": total, "paid": paid, "outstanding": max(0, total - paid),
        "status": status, "updated_at": ts}})


# ============================================================ tampilan pembeli
async def portal_rows(org: str, deal_id: str) -> dict:
    """Angka yang SAMA dengan pembukuan, dalam bahasa pembeli — tanpa nomor akun.

    Pembeli berhak tahu bahwa dirinya masih di dalam masa toleransi (dan sampai kapan),
    bukan hanya dituduh "belum bayar". Nomor akun GL tidak pernah dikirim ke portal.
    """
    a = await assess(org, deal_id)
    rows = [{"label": r["label"], "due_date": r["due_date"],
             "grace_days": r["grace_days"], "grace_until": r["grace_until"],
             "grace_left_days": r["grace_left_days"], "days_late": r["days_late"],
             "outstanding": r["outstanding"], "state": r["state"],
             "state_label": r["state_label"], "denda_charged": r["denda_charged"]}
            for r in a["rows"] if r["state"] in ("dalam_tenggang", "terlambat")]
    denda = [{"label": p["label"], "amount": p["amount"], "period": p["period"],
              "state": p["state"], "state_label": p["state_label"],
              "waived": p["waived"], "waived_amount": p["waived_amount"]}
             for p in a["penalties"]]
    return {"policy_sentence": a["policy_sentence"], "rows": rows, "penalties": denda,
            "totals": {k: a["totals"].get(k, 0) for k in
                       ("overdue_outstanding", "in_grace_outstanding", "denda_charged",
                        "denda_waived")}}
