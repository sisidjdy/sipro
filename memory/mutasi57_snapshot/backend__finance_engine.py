"""Finance engine (Slice Finance) — worksheet-level AR/AP/Komisi/RevRec + pajak.

Prinsip (Dok 15, PSAK 72):
- Pendapatan diakui POINT-IN-TIME saat BAST (Serah Terima). Pembayaran sebelum BAST
  adalah KEWAJIBAN KONTRAK (contract liability), BUKAN pendapatan.
- AR outstanding = total - paid. AP net = claimed - retention_held.
- Angka pajak = acuan konfigurasi (default umum), WAJIB dikonfirmasi penasihat pajak.
- Ini worksheet-level (belum GL double-entry penuh / e-Faktur) — dinyatakan jujur.

Koleksi: finance_configs, payment_schemes, commission_schemes, ar_invoices, receipts,
contract_liabilities, ap_invoices, payments_out, commissions, revenue_recognitions, tax_records.
Uang IDR integer; waktu UTC ISO-8601.
"""
import logging
from datetime import datetime, timedelta

import sequences as seq
from db import db, ORG_ID
from core_utils import new_id, now_iso, now
from engine import emit, create_notification, add_activity

logger = logging.getLogger("sipro.finance")

# Default pajak (acuan konfigurasi, configurable).
DEFAULT_TAX = {"ppn_rate": 12.0, "bphtb_rate": 5.0, "pph_rate": 2.5, "npoptkp": 80_000_000}
FINANCE_NOTIFY_ROLES = ["finance", "owner", "super_admin"]
WORKSHEET_NOTE = "Angka worksheet-level (belum GL penuh / e-Faktur)."


# ----------------------------- Notifications helper -----------------------------
async def notify_finance(org_id, title, body=None, ntype="finance",
                         related_entity_type=None, related_entity_id=None, extra_emails=None):
    """Fan-out notifikasi ke role finance/owner (+ email tambahan mis. sales pemilik deal)."""
    emails = set(e for e in (extra_emails or []) if e)
    users = await db.users.find(
        {"org_id": org_id, "role": {"$in": FINANCE_NOTIFY_ROLES}, "is_active": True},
        {"_id": 0, "email": 1}).to_list(100)
    for u in users:
        emails.add(u["email"])
    for e in emails:
        await create_notification(user_email=e, title=title, body=body, type=ntype,
                                  related_entity_type=related_entity_type,
                                  related_entity_id=related_entity_id, org_id=org_id)


# ----------------------------- Config + schemes -----------------------------
async def get_finance_config(org_id=ORG_ID) -> dict:
    doc = await db.finance_configs.find_one({"org_id": org_id, "key": "finance_config"}, {"_id": 0})
    if not doc:
        doc = {"key": "finance_config", "org_id": org_id, **DEFAULT_TAX}
    return doc


async def set_finance_config(org_id, ppn_rate, bphtb_rate, pph_rate, npoptkp) -> dict:
    ts = now_iso()
    await db.finance_configs.update_one(
        {"org_id": org_id, "key": "finance_config"},
        {"$set": {"key": "finance_config", "org_id": org_id, "ppn_rate": float(ppn_rate),
                  "bphtb_rate": float(bphtb_rate), "pph_rate": float(pph_rate),
                  "npoptkp": int(npoptkp), "updated_at": ts}}, upsert=True)
    return await get_finance_config(org_id)


async def get_default_payment_scheme(org_id=ORG_ID) -> dict:
    return (await db.payment_schemes.find_one({"org_id": org_id, "is_default": True}, {"_id": 0})
            or await db.payment_schemes.find_one({"org_id": org_id}, {"_id": 0}))


async def get_default_commission_scheme(org_id=ORG_ID) -> dict:
    return (await db.commission_schemes.find_one({"org_id": org_id, "is_default": True}, {"_id": 0})
            or await db.commission_schemes.find_one({"org_id": org_id}, {"_id": 0}))


# ----------------------------- Tax compute -----------------------------
def compute_taxes(price: int, config: dict) -> dict:
    price = int(price or 0)
    ppn_rate = config.get("ppn_rate", DEFAULT_TAX["ppn_rate"])
    bphtb_rate = config.get("bphtb_rate", DEFAULT_TAX["bphtb_rate"])
    pph_rate = config.get("pph_rate", DEFAULT_TAX["pph_rate"])
    npoptkp = int(config.get("npoptkp", DEFAULT_TAX["npoptkp"]))
    bphtb_base = max(0, price - npoptkp)
    return {
        "ppn": round(price * ppn_rate / 100), "ppn_rate": ppn_rate,
        "bphtb": round(bphtb_base * bphtb_rate / 100), "bphtb_rate": bphtb_rate, "bphtb_base": bphtb_base,
        "pph": round(price * pph_rate / 100), "pph_rate": pph_rate,
    }


# ----------------------------- AR schedule -----------------------------
def _due_date(base: datetime, t: dict) -> str:
    """Tanggal jatuh tempo satu termin menurut CARA-nya (Fase 57A).

    `monthly_day` = tanggal tertentu pada bulan ke-N (hari dibatasi 1..28 di lapis model
    supaya Februari tidak membuat tagihan meleset). `event` tetap membawa tanggal PERKIRAAN
    dari `due_offset_days` — tanggal kosong akan membuat laporan umur piutang berbohong,
    jadi yang jujur adalah tanggal perkiraan yang DITANDAI perkiraan (`event_based`).
    """
    mode = t.get("due_mode") or "offset_days"
    if mode == "monthly_day":
        bulan = int(t.get("month_index") or 0)
        y, m = base.year, base.month + bulan
        y, m = y + (m - 1) // 12, (m - 1) % 12 + 1
        hari = min(int(t.get("due_day") or 1), 28)
        return base.replace(year=y, month=m, day=hari).isoformat()
    return (base + timedelta(days=int(t.get("due_offset_days", 0) or 0))).isoformat()


def compute_scheme_items(scheme: dict, price: int, base_date_iso: str) -> list:
    """Terjemahkan skema pembayaran -> daftar item jadwal (amount + due_date).

    SATU-SATUNYA mesin termin: dipakai penawaran, kontrak, pratinjau skema, dan penagihan.
    Dasar nilai (Fase 57A): `percent` (dari harga), `amount` (nominal tetap), `remaining`
    (sisa harga setelah termin lain) — `remaining` adalah satu-satunya cara jujur menutup
    selisih pada skema campuran tanpa mengarang angka.
    """
    try:
        base = datetime.fromisoformat(base_date_iso)
    except Exception:
        base = now()
    src = scheme.get("items", [])
    all_percent = bool(src) and all(i.get("basis", "percent") == "percent" for i in src)
    pct_sum = sum(i.get("value", 0) for i in src if i.get("basis", "percent") == "percent")
    out = []
    for i in src:
        basis = i.get("basis", "percent")
        if basis == "remaining":
            amt = max(0, int(price) - sum(x["amount"] for x in out))
        elif basis == "percent":
            amt = round(price * i.get("value", 0) / 100)
        else:
            amt = int(i.get("value", 0))
        out.append({"id": new_id(), "label": i.get("label", "Termin"), "basis": basis,
                    "value": i.get("value", 0), "amount": int(amt),
                    "due_date": _due_date(base, i),
                    "status": "unpaid", "paid_amount": 0})
    # Rekonsiliasi ke harga bila skema all-percent menjumlah ~100%.
    if out and all_percent and 99 <= pct_sum <= 101:
        out[-1]["amount"] += price - sum(x["amount"] for x in out)
    return out


async def create_ar_for_deal(deal: dict, scheme_id=None, org_id=ORG_ID, replace=False, actor="system") -> dict:
    """Buat/replace jadwal AR untuk deal dari skema pembayaran. Idempotent kecuali replace."""
    deal_id = deal["id"]
    existing = await db.ar_invoices.find_one({"org_id": org_id, "deal_id": deal_id}, {"_id": 0})
    if existing and not replace:
        return existing
    scheme = None
    if scheme_id:
        scheme = await db.payment_schemes.find_one({"id": scheme_id, "org_id": org_id}, {"_id": 0})
    if not scheme:
        scheme = await get_default_payment_scheme(org_id)
    if not scheme:
        raise ValueError("Belum ada skema pembayaran. Buat skema di Konfigurasi terlebih dahulu.")
    price = int(deal.get("price", 0))
    base_date = deal.get("booked_at") or deal.get("reserved_at") or now_iso()
    items = compute_scheme_items(scheme, price, base_date)
    total = sum(i["amount"] for i in items)
    ts = now_iso()
    unit = await db.units.find_one({"id": deal.get("unit_id")}, {"_id": 0, "code": 1}) or {}
    lead = await db.leads.find_one({"id": deal.get("lead_id")}, {"_id": 0, "name": 1}) or {}
    config = await get_finance_config(org_id)
    taxes = compute_taxes(price, config)
    inv = {
        "id": existing["id"] if existing else new_id(), "org_id": org_id, "deal_id": deal_id,
        "unit_id": deal.get("unit_id"), "lead_id": deal.get("lead_id"),
        "project_id": deal.get("project_id"), "assigned_to": deal.get("assigned_to"),
        "scheme_id": scheme.get("id"), "scheme_name": scheme.get("name"),
        "unit_code": unit.get("code"), "lead_name": lead.get("name"),
        "price": price, "items": items, "total": total, "paid": 0, "outstanding": total,
        "status": "unpaid", "taxes": taxes,
        "created_at": existing["created_at"] if existing else ts, "updated_at": ts,
    }
    if existing:
        await db.ar_invoices.update_one({"id": inv["id"]}, {"$set": inv})
    else:
        await db.ar_invoices.insert_one(dict(inv))
    # Contract liability (per deal) mulai 0.
    await db.contract_liabilities.update_one(
        {"org_id": org_id, "deal_id": deal_id},
        {"$setOnInsert": {"id": new_id(), "org_id": org_id, "deal_id": deal_id, "unit_id": deal.get("unit_id"),
                          "balance": 0, "recognized": False, "created_at": ts},
         "$set": {"updated_at": ts}}, upsert=True)
    # Tax records (refresh).
    await db.tax_records.delete_many({"org_id": org_id, "deal_id": deal_id})
    for tkey, base, rate, amount in (("ppn", price, taxes["ppn_rate"], taxes["ppn"]),
                                     ("bphtb", taxes["bphtb_base"], taxes["bphtb_rate"], taxes["bphtb"]),
                                     ("pph", price, taxes["pph_rate"], taxes["pph"])):
        await db.tax_records.insert_one({
            "id": new_id(), "org_id": org_id, "deal_id": deal_id, "type": tkey, "base": int(base),
            "rate": rate, "amount": int(amount), "status": "pending", "created_at": ts})
    await emit("ar.schedule_created", "deal", deal_id, {"total": total}, org_id=org_id)
    await notify_finance(org_id, "Jadwal AR dibuat",
                         f"Skema '{scheme.get('name')}' untuk unit {unit.get('code') or '-'} (total Rp {total:,}).",
                         "finance", "deal", deal_id, extra_emails=[deal.get("assigned_to")])
    inv.pop("_id", None)
    return inv


def _allocate(items: list, amount: int) -> tuple:
    """Alokasi uang ke item termin (jatuh tempo terlama dulu). Mengubah `items` di tempat.

    Return (allocations, remaining). `remaining` > 0 berarti uangnya melebihi seluruh sisa tagihan.
    """
    remaining = int(amount)
    allocations = []
    for it in sorted(items, key=lambda x: x.get("due_date") or ""):
        if remaining <= 0:
            break
        out = it["amount"] - it.get("paid_amount", 0)
        if out <= 0:
            continue
        pay = min(out, remaining)
        it["paid_amount"] = it.get("paid_amount", 0) + pay
        it["status"] = "paid" if it["paid_amount"] >= it["amount"] else "partial"
        remaining -= pay
        allocations.append({"item_id": it["id"], "label": it["label"], "amount": pay})
    return allocations, remaining


async def _recalc_invoice(inv: dict, items: list, ts: str) -> tuple:
    """Simpan ulang total AR + status unit dari hasil alokasi. Return (paid, outstanding, status)."""
    paid = sum(i.get("paid_amount", 0) for i in items)
    total = inv["total"]
    outstanding = total - paid
    status = "paid" if outstanding <= 0 else ("partial" if paid > 0 else "unpaid")
    await db.ar_invoices.update_one({"id": inv["id"]}, {"$set": {
        "items": items, "paid": paid, "outstanding": outstanding, "status": status, "updated_at": ts}})
    pay_status = "paid_off" if status == "paid" else ("partial" if paid > 0 else "booking_fee")
    await db.units.update_one({"id": inv.get("unit_id")},
                              {"$set": {"payment_status": pay_status, "updated_at": ts}})
    return paid, outstanding, status


async def _after_paid_off(inv: dict, deal_id: str, org_id: str):
    await emit("payment.paid_off", "deal", deal_id, {}, org_id=org_id)
    deal = await db.deals.find_one({"id": deal_id}, {"_id": 0})
    if deal:
        await create_commission_for_deal(deal, org_id=org_id, trigger="paid_off")
    await notify_finance(org_id, "AR lunas",
                         f"Deal unit {inv.get('unit_code') or '-'} telah LUNAS. Menunggu BAST untuk RevRec.",
                         "finance", "deal", deal_id, extra_emails=[inv.get("assigned_to")])


async def apply_receipt(deal_id, amount, method, note, actor, org_id=ORG_ID,
                        allow_overpay=False) -> dict:
    """Terima pembayaran -> alokasi ke item termin (jatuh tempo terlama dulu) ->
    recalc outstanding -> naikkan contract_liability -> update unit.payment_status.

    Fase 26 (kebenaran uang): sisa yang tidak bisa dialokasikan TIDAK lagi hilang.
    Default kelebihan bayar DITOLAK; bila kasir sengaja menerimanya (`allow_overpay`),
    kelebihan dicatat sebagai **titipan pelanggan** (`customer_deposits`) dan dijurnal
    ke `2-1450` — jadi kas di GL selalu sama dengan kas yang benar-benar diterima.
    """
    inv = await db.ar_invoices.find_one({"org_id": org_id, "deal_id": deal_id}, {"_id": 0})
    if not inv:
        raise ValueError("Jadwal AR belum dibuat untuk deal ini.")
    amount = int(amount)
    items = inv["items"]
    outstanding_before = int(inv.get("outstanding", inv["total"] - inv.get("paid", 0)))
    allocations, excess = _allocate(items, amount)
    if excess > 0 and not allow_overpay:
        raise ValueError(
            f"Jumlah Rp {amount:,} melebihi sisa tagihan Rp {outstanding_before:,} "
            f"(kelebihan Rp {excess:,}). Centang \u201cCatat kelebihan sebagai titipan "
            f"pelanggan\u201d bila pembayaran ini memang diterima.")
    applied = amount - excess
    ts = now_iso()
    paid, outstanding, status = await _recalc_invoice(inv, items, ts)
    receipt = {
        "id": new_id(), "org_id": org_id,
        # Kwitansi WAJIB bernomor. Sebelum ini nomornya tidak pernah ada, jadi PDF kwitansi
        # yang kini bisa diunduh PEMBELI di portal (Fase 51C) memakai UUID sebagai "nomor
        # dokumen" — kwitansi tanpa nomor urut bukan bukti yang bisa diaudit.
        "receipt_no": await seq.next_number("receipt", org_id, prefix="KWT"),
        "deal_id": deal_id, "unit_id": inv.get("unit_id"),
        "unit_code": inv.get("unit_code"), "amount": amount, "applied": applied,
        "deposit_amount": excess, "funding": "cash", "method": method or "transfer",
        "note": note, "allocations": allocations, "actor": actor, "created_at": ts}
    await db.receipts.insert_one(dict(receipt))
    if applied > 0:
        await db.contract_liabilities.update_one(
            {"org_id": org_id, "deal_id": deal_id},
            {"$inc": {"balance": applied}, "$set": {"updated_at": ts}}, upsert=True)
        # `receipt_id` WAJIB ikut: jurnal GL menunjuk kuitansinya (bukan deal), supaya satu
        # deal dengan beberapa penerimaan tetap bisa direkonstruksi & dibalik satu per satu.
        await emit("payment.received", "deal", deal_id,
                   {"amount": applied, "receipt_id": receipt["id"]}, org_id=org_id)
    deposit = None
    if excess > 0:
        deposit = await _deposit_move(org_id, deal_id, inv, "in", excess,
                                      note or "Kelebihan bayar", actor, receipt_id=receipt["id"])
    await notify_finance(org_id, "Pembayaran diterima",
                         f"Rp {amount:,} ({method or 'transfer'}) untuk unit {inv.get('unit_code') or '-'}"
                         + (f" \u2014 Rp {excess:,} dicatat sebagai titipan." if excess else "."),
                         "finance", "deal", deal_id, extra_emails=[inv.get("assigned_to")])
    receipt.pop("_id", None)
    result = {"receipt": receipt, "invoice": {**inv, "items": items, "paid": paid,
              "outstanding": outstanding, "status": status}, "paid_off": status == "paid",
              "deposit": deposit}
    if status == "paid":
        await _after_paid_off(inv, deal_id, org_id)
    return result


# ----------------------------- Fase 26 — Titipan pelanggan (customer deposits) -----------------------------
async def _deposit_move(org_id, deal_id, inv, kind, amount, note, actor, receipt_id=None) -> dict:
    """Catat satu mutasi titipan (in/apply/refund) + jurnal GL. Return dokumen titipan terkini."""
    amount = int(amount)
    ts = now_iso()
    entry = {"id": new_id(), "type": kind, "amount": amount, "note": note,
             "actor": actor, "receipt_id": receipt_id, "created_at": ts}
    delta = amount if kind == "in" else -amount
    inc = {"balance": delta,
           "received_total": amount if kind == "in" else 0,
           "applied_total": amount if kind == "apply" else 0,
           "refunded_total": amount if kind == "refund" else 0}
    await db.customer_deposits.update_one(
        {"org_id": org_id, "deal_id": deal_id},
        {"$inc": inc, "$push": {"entries": entry},
         "$set": {"unit_id": inv.get("unit_id"), "unit_code": inv.get("unit_code"),
                  "customer_name": inv.get("customer_name") or inv.get("lead_name"),
                  "updated_at": ts},
         "$setOnInsert": {"id": new_id(), "created_at": ts}},
        upsert=True)
    dep = await db.customer_deposits.find_one({"org_id": org_id, "deal_id": deal_id}, {"_id": 0})
    await emit(f"deposit.{'received' if kind == 'in' else ('applied' if kind == 'apply' else 'refunded')}",
               "deposit", dep["id"], {"amount": amount, "deal_id": deal_id}, org_id=org_id)
    return dep


async def get_deposit(org_id, deal_id) -> dict:
    dep = await db.customer_deposits.find_one({"org_id": org_id, "deal_id": deal_id}, {"_id": 0})
    return dep or {"deal_id": deal_id, "balance": 0, "entries": []}


async def receive_deposit(deal_id, amount, note, actor, org_id=ORG_ID) -> dict:
    """Terima titipan/uang muka bebas dari pembeli TANPA mengalokasikannya ke termin.

    Dipakai bila pembeli menyetor lebih dulu (mis. menunggu jadwal termin terbit) —
    kas tercatat sebagai kewajiban `2-1450`, bukan pendapatan, dan bisa dipakai kapan saja.
    """
    amount = int(amount or 0)
    if amount <= 0:
        raise ValueError("Nominal titipan harus lebih dari 0.")
    inv = await db.ar_invoices.find_one({"org_id": org_id, "deal_id": deal_id}, {"_id": 0})
    deal = await db.deals.find_one({"id": deal_id, "org_id": org_id}, {"_id": 0})
    if not inv and not deal:
        raise ValueError("Deal tidak ditemukan.")
    ctx = inv or {"unit_id": (deal or {}).get("unit_id"), "unit_code": (deal or {}).get("unit_code"),
                  "customer_name": (deal or {}).get("lead_name")}
    dep = await _deposit_move(org_id, deal_id, ctx, "in", amount,
                              note or "Titipan diterima di muka", actor)
    await notify_finance(org_id, "Titipan diterima",
                         f"Rp {amount:,} titipan pembeli unit {ctx.get('unit_code') or '-'} diterima.",
                         "finance", "deal", deal_id)
    return {"deposit": dep, "received": amount}


async def apply_deposit(deal_id, amount, actor, org_id=ORG_ID, note=None) -> dict:
    """Pakai titipan pelanggan untuk melunasi termin berikutnya (tanpa kas baru masuk)."""
    inv = await db.ar_invoices.find_one({"org_id": org_id, "deal_id": deal_id}, {"_id": 0})
    if not inv:
        raise ValueError("Jadwal AR belum dibuat untuk deal ini.")
    dep = await db.customer_deposits.find_one({"org_id": org_id, "deal_id": deal_id}, {"_id": 0})
    balance = int((dep or {}).get("balance", 0))
    if balance <= 0:
        raise ValueError("Tidak ada saldo titipan untuk deal ini.")
    outstanding = int(inv.get("outstanding", 0))
    if outstanding <= 0:
        raise ValueError("Tagihan sudah lunas — titipan hanya bisa dikembalikan ke pelanggan.")
    amount = int(amount or min(balance, outstanding))
    if amount <= 0:
        raise ValueError("Nominal harus lebih dari 0.")
    if amount > balance:
        raise ValueError(f"Nominal Rp {amount:,} melebihi saldo titipan Rp {balance:,}.")
    if amount > outstanding:
        raise ValueError(f"Nominal Rp {amount:,} melebihi sisa tagihan Rp {outstanding:,}.")
    items = inv["items"]
    allocations, remaining = _allocate(items, amount)
    ts = now_iso()
    paid, outstanding_after, status = await _recalc_invoice(inv, items, ts)
    receipt = {
        "id": new_id(), "org_id": org_id,
        "receipt_no": await seq.next_number("receipt", org_id, prefix="KWT"),
        "deal_id": deal_id, "unit_id": inv.get("unit_id"),
        "unit_code": inv.get("unit_code"), "amount": 0, "applied": amount - remaining,
        "deposit_amount": 0, "funding": "deposit", "method": "deposit",
        "note": note or "Pemakaian titipan pelanggan", "allocations": allocations,
        "actor": actor, "created_at": ts}
    await db.receipts.insert_one(dict(receipt))
    await db.contract_liabilities.update_one(
        {"org_id": org_id, "deal_id": deal_id},
        {"$inc": {"balance": amount - remaining}, "$set": {"updated_at": ts}}, upsert=True)
    deposit = await _deposit_move(org_id, deal_id, inv, "apply", amount - remaining,
                                  note or "Dipakai untuk termin", actor, receipt_id=receipt["id"])
    await notify_finance(org_id, "Titipan dipakai",
                         f"Rp {amount - remaining:,} titipan dipakai untuk termin unit "
                         f"{inv.get('unit_code') or '-'}.", "finance", "deal", deal_id)
    receipt.pop("_id", None)
    if status == "paid":
        await _after_paid_off(inv, deal_id, org_id)
    return {"receipt": receipt, "deposit": deposit, "paid_off": status == "paid",
            "invoice": {**inv, "items": items, "paid": paid,
                        "outstanding": outstanding_after, "status": status}}


async def refund_deposit(deal_id, amount, note, actor, org_id=ORG_ID) -> dict:
    """Kembalikan titipan pelanggan (kas keluar, kewajiban titipan turun)."""
    inv = await db.ar_invoices.find_one({"org_id": org_id, "deal_id": deal_id}, {"_id": 0}) or {}
    dep = await db.customer_deposits.find_one({"org_id": org_id, "deal_id": deal_id}, {"_id": 0})
    balance = int((dep or {}).get("balance", 0))
    amount = int(amount or balance)
    if balance <= 0:
        raise ValueError("Tidak ada saldo titipan untuk dikembalikan.")
    if amount <= 0:
        raise ValueError("Nominal harus lebih dari 0.")
    if amount > balance:
        raise ValueError(f"Nominal Rp {amount:,} melebihi saldo titipan Rp {balance:,}.")
    deposit = await _deposit_move(org_id, deal_id, inv, "refund", amount,
                                  note or "Pengembalian titipan", actor)
    await notify_finance(org_id, "Titipan dikembalikan",
                         f"Rp {amount:,} titipan dikembalikan ke pelanggan (unit "
                         f"{inv.get('unit_code') or '-'}).", "finance", "deal", deal_id)
    return {"deposit": deposit, "refunded": amount}


async def deposits_total(org_id=ORG_ID) -> int:
    rows = await db.customer_deposits.find({"org_id": org_id}, {"_id": 0, "balance": 1}).to_list(2000)
    return sum(int(r.get("balance", 0) or 0) for r in rows)


# ----------------------------- Commission (tiered, bracket-based) -----------------------------
def compute_commission_amount(base: int, tiers: list):
    """Bracket-based: pilih tier yang mencakup 'base', terapkan rate ke seluruh base."""
    base = int(base or 0)
    rate = 0.0
    for t in sorted(tiers, key=lambda x: x.get("min_amount", 0)):
        mn = t.get("min_amount", 0)
        mx = t.get("max_amount")
        if base >= mn and (mx is None or base <= mx):
            rate = t.get("rate_pct", 0)
            break
    return round(base * rate / 100), rate


async def create_commission_for_deal(deal: dict, scheme_id=None, org_id=ORG_ID, trigger="booked") -> dict:
    """Hitung komisi bila skema (default/terpilih) trigger cocok. Idempotent per deal."""
    scheme = None
    if scheme_id:
        scheme = await db.commission_schemes.find_one({"id": scheme_id, "org_id": org_id}, {"_id": 0})
    if not scheme:
        scheme = await get_default_commission_scheme(org_id)
    if not scheme or scheme.get("trigger") != trigger:
        return None
    if await db.commissions.find_one({"org_id": org_id, "deal_id": deal["id"]}, {"_id": 0}):
        return None
    price = int(deal.get("price", 0))
    basis = scheme.get("basis", "price")
    if basis == "net":
        config = await get_finance_config(org_id)
        base = price - compute_taxes(price, config)["ppn"]
    elif basis == "dp":
        liab = await db.contract_liabilities.find_one({"org_id": org_id, "deal_id": deal["id"]}, {"_id": 0})
        base = (liab or {}).get("balance", 0)
    else:
        base = price
    amount, rate = compute_commission_amount(base, scheme.get("tiers", []))
    ts = now_iso()
    unit = await db.units.find_one({"id": deal.get("unit_id")}, {"_id": 0, "code": 1}) or {}
    doc = {
        "id": new_id(), "org_id": org_id, "deal_id": deal["id"], "unit_id": deal.get("unit_id"),
        "unit_code": unit.get("code"), "scheme_id": scheme.get("id"), "scheme_name": scheme.get("name"),
        "assigned_to": deal.get("assigned_to"), "basis": basis, "base": int(base),
        "rate_pct": rate, "amount": int(amount), "trigger": trigger, "status": "pending",
        "created_at": ts, "updated_at": ts, "approved_by": None, "approved_at": None}
    await db.commissions.insert_one(dict(doc))
    await emit("commission.created", "deal", deal["id"], {"amount": amount}, org_id=org_id)
    await notify_finance(org_id, "Komisi dihitung",
                         f"Komisi Rp {amount:,} ({rate}%) untuk {deal.get('assigned_to') or '-'}.",
                         "finance", "deal", deal["id"], extra_emails=[deal.get("assigned_to")])
    doc.pop("_id", None)
    return doc


async def approve_commission(commission_id, approver, org_id=ORG_ID) -> dict:
    com = await db.commissions.find_one({"id": commission_id, "org_id": org_id}, {"_id": 0})
    if not com:
        raise ValueError("Komisi tidak ditemukan.")
    if com.get("status") == "approved":
        return com
    ts = now_iso()
    await db.commissions.update_one({"id": commission_id},
        {"$set": {"status": "approved", "approved_by": approver, "approved_at": ts, "updated_at": ts}})
    await emit("commission.approved", "deal", com.get("deal_id"), {}, org_id=org_id)
    await notify_finance(org_id, "Komisi disetujui",
                         f"Komisi Rp {com.get('amount', 0):,} disetujui.", "finance",
                         "deal", com.get("deal_id"), extra_emails=[com.get("assigned_to")])
    return await db.commissions.find_one({"id": commission_id, "org_id": org_id}, {"_id": 0})


async def pay_commission(commission_id, payer, org_id=ORG_ID) -> dict:
    """Bayarkan komisi yang sudah disetujui (approved -> paid). Idempotent."""
    com = await db.commissions.find_one({"id": commission_id, "org_id": org_id}, {"_id": 0})
    if not com:
        raise ValueError("Komisi tidak ditemukan.")
    if com.get("status") == "paid":
        return com
    if com.get("status") != "approved":
        raise ValueError("Komisi harus disetujui terlebih dahulu sebelum dibayar.")
    ts = now_iso()
    await db.commissions.update_one({"id": commission_id},
        {"$set": {"status": "paid", "paid_by": payer, "paid_at": ts, "updated_at": ts}})
    await emit("commission.paid", "commission", commission_id,
               {"amount": int(com.get("amount", 0))}, org_id=org_id)
    await notify_finance(org_id, "Komisi dibayar",
                         f"Komisi Rp {com.get('amount', 0):,} telah dibayarkan.", "finance",
                         "deal", com.get("deal_id"), extra_emails=[com.get("assigned_to")])
    return await db.commissions.find_one({"id": commission_id, "org_id": org_id}, {"_id": 0})


# ----------------------------- Revenue Recognition (PSAK 72, BAST) -----------------------------
async def recognize_revenue(deal: dict, org_id=ORG_ID, cogs=None, actor="system") -> dict:
    """BAST: akui pendapatan (point-in-time), nolkan contract liability, unit -> sold."""
    deal_id = deal["id"]
    existing = await db.revenue_recognitions.find_one({"org_id": org_id, "deal_id": deal_id}, {"_id": 0})
    if existing:
        return existing
    price = int(deal.get("price", 0))
    if cogs is None:
        cogs = round(price * 0.7)  # asumsi worksheet COGS 70% (dapat dikoreksi)
    liab = await db.contract_liabilities.find_one({"org_id": org_id, "deal_id": deal_id}, {"_id": 0})
    liab_bal = (liab or {}).get("balance", 0)
    ts = now_iso()
    doc = {
        "id": new_id(), "org_id": org_id, "deal_id": deal_id, "unit_id": deal.get("unit_id"),
        "project_id": deal.get("project_id"), "revenue": price, "cogs": int(cogs),
        "margin": price - int(cogs), "contract_liability_cleared": int(liab_bal),
        "recognized_at": ts, "recognized_by": actor, "created_at": ts}
    await db.revenue_recognitions.insert_one(dict(doc))
    await db.contract_liabilities.update_one({"org_id": org_id, "deal_id": deal_id},
        {"$set": {"balance": 0, "recognized": True, "updated_at": ts}})
    await db.units.update_one({"id": deal.get("unit_id")},
        {"$set": {"status": "sold", "payment_status": "paid_off", "updated_at": ts}})
    await db.deals.update_one({"id": deal_id},
        {"$set": {"status": "completed", "bast_at": ts, "updated_at": ts}})
    await emit("revenue.recognized", "deal", deal_id, {"revenue": price}, org_id=org_id)
    await add_activity(entity_type="deal", entity_id=deal_id, type="system",
                       body=f"BAST/Serah Terima — pendapatan Rp {price:,} diakui (PSAK 72).",
                       actor=actor, org_id=org_id)
    await notify_finance(org_id, "Pendapatan diakui (BAST)",
                         f"Rp {price:,} diakui saat serah terima; kewajiban kontrak dinolkan.",
                         "finance", "deal", deal_id, extra_emails=[deal.get("assigned_to")])
    doc.pop("_id", None)
    return doc


# ----------------------------- Thin AP -----------------------------
async def create_ap_bill(vendor, project_id, claimed, retention_pct, due_date, note, actor, org_id=ORG_ID) -> dict:
    claimed = int(claimed)
    retention_pct = float(retention_pct or 0)
    retention_held = round(claimed * retention_pct / 100)
    net = claimed - retention_held
    ts = now_iso()
    doc = {
        "id": new_id(), "org_id": org_id, "vendor": vendor, "project_id": project_id,
        "claimed": claimed, "retention_pct": retention_pct, "retention_held": retention_held,
        "net": net, "paid": 0, "outstanding": net, "status": "pending_approval",
        "due_date": due_date, "note": note, "retention_released": False,
        "approved_by": None, "approved_at": None, "created_by": actor,
        "created_at": ts, "updated_at": ts}
    await db.ap_invoices.insert_one(dict(doc))
    await emit("ap.bill_created", "ap_bill", doc["id"], {"net": net}, org_id=org_id)
    await notify_finance(org_id, "Tagihan AP baru",
                         f"{vendor}: klaim Rp {claimed:,}, net Rp {net:,} (retensi {retention_pct}%). Menunggu approval.",
                         "finance", "ap_bill", doc["id"])
    doc.pop("_id", None)
    return doc


async def approve_ap_bill(bill_id, approver, org_id=ORG_ID) -> dict:
    bill = await db.ap_invoices.find_one({"id": bill_id, "org_id": org_id}, {"_id": 0})
    if not bill:
        raise ValueError("Tagihan AP tidak ditemukan.")
    if bill.get("status") != "pending_approval":
        raise ValueError("Tagihan sudah diproses (bukan status menunggu approval).")
    ts = now_iso()
    await db.ap_invoices.update_one({"id": bill_id},
        {"$set": {"status": "approved", "approved_by": approver, "approved_at": ts, "updated_at": ts}})
    await emit("ap.approved", "ap_bill", bill_id, {}, org_id=org_id)
    await notify_finance(org_id, "Tagihan AP disetujui",
                         f"{bill.get('vendor')}: net Rp {bill.get('net', 0):,} siap dibayar.",
                         "finance", "ap_bill", bill_id)
    return await db.ap_invoices.find_one({"id": bill_id, "org_id": org_id}, {"_id": 0})


async def pay_ap_bill(bill_id, amount, note, actor, org_id=ORG_ID, withhold: dict = None,
                      return_payment: bool = False):
    """Bayar tagihan AP. `withhold` (Fase 49F) memotong PPh dari kas yang keluar.

    Tanpa fitur ini, potongan PPh jasa konstruksi/PPh 23 hanya bisa dicatat di luar sistem,
    sehingga bukti potong yang diterbitkan tidak punya pasangan di pembukuan dan vendor
    dibayar bruto padahal kewajiban setornya ada di kita. `withhold` berisi
    `{kind, base, rate, amount, memo}` — nilai potongan dihitung pemanggil (router) supaya
    tarif & dasar yang dipakai TERBACA di layar sebelum uang keluar.
    """
    bill = await db.ap_invoices.find_one({"id": bill_id, "org_id": org_id}, {"_id": 0})
    if not bill:
        raise ValueError("Tagihan AP tidak ditemukan.")
    if bill.get("status") not in ("approved", "partial"):
        raise ValueError("Tagihan harus disetujui terlebih dahulu sebelum dibayar.")
    amount = int(amount)
    if amount <= 0:
        raise ValueError("Nominal pembayaran harus lebih dari 0.")
    withheld = int((withhold or {}).get("amount", 0) or 0)
    if withheld < 0:
        raise ValueError("Potongan PPh tidak boleh negatif.")
    if withheld >= amount:
        raise ValueError(f"Potongan PPh Rp {withheld:,} tidak boleh sama dengan atau melebihi "
                         f"nilai pembayaran Rp {amount:,}.")
    outstanding_before = int(bill.get("net", 0)) - int(bill.get("paid", 0))
    if amount > outstanding_before:
        # Fase 26: dulu tidak ada guard -> paid bisa > net dan akun 2-1100 jadi negatif.
        raise ValueError(f"Pembayaran Rp {amount:,} melebihi sisa tagihan "
                         f"Rp {outstanding_before:,} untuk {bill.get('vendor')}.")
    paid = bill.get("paid", 0) + amount
    outstanding = bill.get("net", 0) - paid
    status = "paid" if outstanding <= 0 else "partial"
    ts = now_iso()
    await db.ap_invoices.update_one({"id": bill_id}, {"$set": {
        "paid": paid, "outstanding": max(0, outstanding), "status": status, "updated_at": ts},
        "$inc": {"withheld_total": withheld}})
    payment = {
        "id": new_id(), "org_id": org_id, "bill_id": bill_id, "vendor": bill.get("vendor"),
        "amount": amount, "cash_out": amount - withheld, "withheld_amount": withheld,
        "withheld_kind": (withhold or {}).get("kind"),
        "withheld_base": int((withhold or {}).get("base", 0) or 0),
        "withheld_rate": float((withhold or {}).get("rate", 0) or 0),
        "note": note, "actor": actor, "created_at": ts,
    }
    await db.payments_out.insert_one(dict(payment))
    payment.pop("_id", None)
    await emit("ap.paid", "ap_bill", bill_id,
               {"amount": amount, "withheld": withheld,
                "withheld_memo": (withhold or {}).get("memo")}, org_id=org_id)
    body = f"Bayar Rp {amount:,} ke {bill.get('vendor')}. Sisa Rp {max(0, outstanding):,}."
    if withheld:
        body += f" Dipotong PPh Rp {withheld:,} (kas keluar Rp {amount - withheld:,})."
    await notify_finance(org_id, "Pembayaran AP", body, "finance", "ap_bill", bill_id)
    updated = await db.ap_invoices.find_one({"id": bill_id, "org_id": org_id}, {"_id": 0})
    return (updated, payment) if return_payment else updated


# ----------------------------- Aging + Summary -----------------------------
def _days_overdue(due_iso) -> int:
    if not due_iso:
        return 0
    try:
        due = datetime.fromisoformat(due_iso)
        # Ensure due is timezone-aware (assume UTC if naive)
        if due.tzinfo is None:
            from datetime import timezone
            due = due.replace(tzinfo=timezone.utc)
    except Exception:
        return 0
    return (now() - due).days


def bucketize(entries) -> dict:
    """entries: list of (due_date_iso, outstanding)."""
    buckets = {"current": 0, "1-30": 0, "31-60": 0, "61-90": 0, ">90": 0}
    total = 0
    for due, out in entries:
        out = int(out or 0)
        if out <= 0:
            continue
        total += out
        d = _days_overdue(due)
        if d <= 0:
            buckets["current"] += out
        elif d <= 30:
            buckets["1-30"] += out
        elif d <= 60:
            buckets["31-60"] += out
        elif d <= 90:
            buckets["61-90"] += out
        else:
            buckets[">90"] += out
    return {"buckets": buckets, "total": total}


async def ar_aging(org_id=ORG_ID) -> dict:
    invoices = await db.ar_invoices.find({"org_id": org_id}, {"_id": 0}).to_list(2000)
    entries, total_value = [], 0
    for inv in invoices:
        total_value += inv.get("total", 0)
        for it in inv.get("items", []):
            entries.append((it.get("due_date"), it["amount"] - it.get("paid_amount", 0)))
    agg = bucketize(entries)
    dso = round(agg["total"] / max(total_value, 1) * 90)
    return {**agg, "dso": dso, "total_value": total_value}


async def ap_aging(org_id=ORG_ID) -> dict:
    bills = await db.ap_invoices.find({"org_id": org_id}, {"_id": 0}).to_list(2000)
    entries = [(b.get("due_date"), b.get("outstanding", 0)) for b in bills if b.get("status") != "paid"]
    agg = bucketize(entries)
    retention_held = sum(b.get("retention_held", 0) for b in bills if not b.get("retention_released"))
    return {**agg, "retention_held": retention_held}


async def finance_summary(org_id=ORG_ID) -> dict:
    ar = await ar_aging(org_id)
    ap = await ap_aging(org_id)
    liabs = await db.contract_liabilities.find({"org_id": org_id}, {"_id": 0}).to_list(2000)
    revs = await db.revenue_recognitions.find({"org_id": org_id}, {"_id": 0}).to_list(2000)
    contract_liability = sum(l.get("balance", 0) for l in liabs)
    revenue_recognized = sum(r.get("revenue", 0) for r in revs)
    ar_overdue = ar["buckets"]["1-30"] + ar["buckets"]["31-60"] + ar["buckets"]["61-90"] + ar["buckets"][">90"]
    return {
        "ar_outstanding": ar["total"], "ar_buckets": ar["buckets"], "ar_dso": ar["dso"],
        "ar_overdue": ar_overdue,
        "ap_outstanding": ap["total"], "ap_buckets": ap["buckets"], "ap_retention_held": ap["retention_held"],
        "contract_liability": contract_liability, "revenue_recognized": revenue_recognized,
        "customer_deposits": await deposits_total(org_id),
        "counts": {
            "ar_invoices": await db.ar_invoices.count_documents({"org_id": org_id}),
            "ap_pending": await db.ap_invoices.count_documents({"org_id": org_id, "status": "pending_approval"}),
            "commissions_pending": await db.commissions.count_documents({"org_id": org_id, "status": "pending"}),
        },
        "worksheet_note": WORKSHEET_NOTE,
    }


# ----------------------------- Scheduler job: retention release -----------------------------
async def ap_retention_release_sweeper(org_id=ORG_ID) -> int:
    """Lepas retensi AP yang sudah lewat release_due_at (bila di-set). Fase awal: no-op aman."""
    released = 0
    cur = await db.ap_invoices.find({
        "org_id": org_id, "retention_released": False,
        "release_due_at": {"$ne": None, "$lt": now_iso()}}).to_list(1000)
    for b in cur:
        ts = now_iso()
        await db.ap_invoices.update_one({"id": b["id"]}, {"$set": {"retention_released": True, "updated_at": ts}})
        await db.payments_out.insert_one({
            "id": new_id(), "org_id": org_id, "bill_id": b["id"], "vendor": b.get("vendor"),
            "amount": b.get("retention_held", 0), "note": "Pelepasan retensi", "actor": "system", "created_at": ts})
        await notify_finance(org_id, "Retensi dilepas",
                             f"Retensi Rp {b.get('retention_held', 0):,} untuk {b.get('vendor')} dilepas.",
                             "finance", "ap_bill", b["id"])
        released += 1
    return released
