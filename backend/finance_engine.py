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
        # Fase 58: `grace_days` & kalimat aturan IKUT ke jadwal tagihan. Sebelum ini toleransi
        # yang disusun pemakai (dan tercetak pada SPR yang ditandatangani pembeli) hilang di
        # sini, sehingga penagihan menandai termin TERLAMBAT pada H+1 — lebih cepat menuduh
        # daripada perjanjiannya sendiri.
        out.append({"id": new_id(), "label": i.get("label", "Termin"), "basis": basis,
                    "value": i.get("value", 0), "amount": int(amt),
                    "due_date": _due_date(base, i),
                    "grace_days": int(i.get("grace_days") or 0),
                    "due_rule": i.get("due_rule"),
                    "event_based": bool(i.get("event") or i.get("event_based")),
                    "status": "unpaid", "paid_amount": 0})
    # Rekonsiliasi ke harga bila skema all-percent menjumlah ~100%.
    if out and all_percent and 99 <= pct_sum <= 101:
        out[-1]["amount"] += price - sum(x["amount"] for x in out)
    return out


from pricing_engine import apply_component_discounts, dp_term_index  # noqa: E402


def ar_breakdown(deal: dict) -> dict:
    """Rincian tagihan pembeli yang DISIMPAN pada AR: harga unit, add-on, potongan, harga bersih,
    booking fee, komponen biaya all-in (kotor − potongan = bersih) dan total dibayar pembeli.
    Sumbernya snapshot deal (`pricing`, `costs`) — tidak ada perhitungan kedua."""
    pricing = deal.get("pricing") or {}
    costs = deal.get("costs") or {}
    comps = []
    for c in costs.get("components") or []:
        amt = int(c.get("amount") or 0)
        disc = int(c.get("discount") or 0)
        comps.append({"code": c.get("code"), "name": c.get("name"), "treatment": c.get("treatment"),
                      "gross": amt + disc, "discount": disc, "amount": amt,
                      "kpr_only": bool(c.get("kpr_only")),
                      "discount_lines": c.get("discount_lines") or []})
    buyer = [c for c in comps if c["treatment"] != "developer_borne"]
    cost_total = sum(c["amount"] for c in buyer)
    net = int(deal.get("price") or 0)
    addon_net = addon_net_of(deal)
    return {
        "base_price": int(pricing.get("base_price") or net),
        "addons": [{"code": a.get("code"), "name": a.get("name"), "amount": int(a.get("amount") or 0),
                    "formula": a.get("formula"), "kpr_excluded": True}
                   for a in deal.get("addons") or []
                   if (a.get("finance_treatment") or "revenue") != "info"],
        "addon_total": int(pricing.get("addon_total") or 0),
        "addon_net_total": addon_net,
        "gross_price": int(pricing.get("gross_price") or net),
        "discount_lines": [{"code": x.get("code"), "name": x.get("name"), "source": x.get("source_label"),
                            "target": x.get("target") or "price", "target_label": x.get("target_label"),
                            "amount": int(x.get("amount") or 0)}
                           for x in pricing.get("discount_lines") or [] if int(x.get("amount") or 0)],
        "price_discount": int(pricing.get("discount_amount") or deal.get("discount") or 0),
        "cost_discount": sum(c["discount"] for c in comps),
        "net_price": net, "booking_fee": int(deal.get("booking_fee") or 0),
        "allin_scheme_name": costs.get("scheme_name"), "cost_components": comps,
        "cost_total": cost_total, "developer_cost_total": sum(c["amount"] for c in comps if c["treatment"] == "developer_borne"),
        "kpr_base": net,
        "buyer_total": net + cost_total + addon_net,
        "payment_breakdown": pricing.get("payment_breakdown"),
    }


def addon_net_of(deal: dict) -> int:
    """Add-on bersih yang ditagih TERPISAH. Deal lama (sebelum pemisahan add-on) sudah memuat
    add-on di `price` → 0 supaya tidak tertagih dua kali."""
    pricing = deal.get("pricing") or {}
    if pricing.get("addon_net_total") is None:
        return 0
    return int(pricing.get("addon_net_total") or 0)


def addon_items(deal: dict, base_date_iso: str, due_days: int) -> list:
    """Baris tagihan add-on: per add-on, `kpr_excluded` (pencairan KPR tidak boleh melunasinya)."""
    if addon_net_of(deal) <= 0:
        return []
    try:
        base = datetime.fromisoformat(base_date_iso)
    except Exception:
        base = now()
    due = (base + timedelta(days=int(due_days or 0))).isoformat()
    lines = (deal.get("pricing") or {}).get("discount_lines") or []
    out = []
    for a in deal.get("addons") or []:
        if (a.get("finance_treatment") or "revenue") == "info":
            continue
        cut = sum(int(x.get("amount") or 0) for x in lines
                  if x.get("target") == "addon" and x.get("target_component") == a.get("code"))
        amt = max(0, int(a.get("amount") or 0) - cut)
        if amt <= 0:
            continue
        out.append({"id": new_id(), "label": f"Add-on · {a.get('name') or a.get('code')}",
                    "basis": "addon", "value": amt, "amount": amt, "due_date": due,
                    "grace_days": 0, "due_rule": None, "event_based": False,
                    "kpr_excluded": True, "addon_code": a.get("code"),
                    "status": "unpaid", "paid_amount": 0})
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
    # Fase 88C: harga deal sudah bersih dari SEMUA potongan; termin disusun dari harga
    # sebelum potongan DP/booking fee, lalu potongan itu dikurangkan dari termin uang muka.
    comp = ((deal.get("pricing") or {}).get("by_target") or {})
    comp_amt = int(comp.get("dp") or 0) + int(comp.get("booking_fee") or 0)
    items = apply_component_discounts(compute_scheme_items(scheme, price + comp_amt, base_date), comp)
    unit_total = sum(i["amount"] for i in items)
    # Add-on = baris tagihan TERPISAH (bukan termin unit, bukan dasar KPR).
    import settings_store as cfg
    addon_rows = addon_items(deal, base_date, int(await cfg.get("addon.due_days", org_id=org_id) or 30))
    items = items + addon_rows
    addon_total = sum(i["amount"] for i in addon_rows)
    total = unit_total + addon_total
    # Ganti skema TIDAK boleh menghapus uang yang sudah diterima: pembayaran lama
    # dialokasikan ulang ke termin baru (jatuh tempo terlama dulu). Sebelumnya AR dibuat
    # ulang dengan paid=0 sementara kuitansi & jurnal kasnya tetap ada — piutang membengkak
    # semu dan layar pelanggan berkata "belum bayar" pada uang yang sudah masuk.
    carried_paid = int((existing or {}).get("paid") or 0)
    if carried_paid > 0:
        _, sisa = _allocate(items, carried_paid)
        if sisa > 0:
            raise ValueError(
                f"Skema baru bernilai Rp {total:,}, lebih kecil dari pembayaran yang sudah diterima "
                f"Rp {carried_paid:,}. Kembalikan kelebihan sebagai titipan/refund dulu.")
    paid_now = sum(i.get("paid_amount", 0) for i in items)
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
        "price": price, "items": items, "total": total, "paid": paid_now, "outstanding": total - paid_now,
        "unit_total": unit_total, "addon_total": addon_total,
        "status": "paid" if total - paid_now <= 0 else ("partial" if paid_now > 0 else "unpaid"), "taxes": taxes,
        "breakdown": ar_breakdown(deal),
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
    # Booking fee yang sudah dibayar (titipan 2-1450) DIALIHKAN ke termin begitu jadwal
    # tagihan lahir — sesuai kalimat di tagihan booking fee. Dulu hanya bisa lewat tombol
    # manual "Pakai titipan", sehingga AR pelanggan tampil Rp 0 padahal uang sudah diterima.
    dep = await db.customer_deposits.find_one({"org_id": org_id, "deal_id": deal_id}, {"_id": 0, "balance": 1})
    if int((dep or {}).get("balance") or 0) > 0 and inv["outstanding"] > 0:
        try:
            res = await apply_deposit(deal_id, None, actor, org_id=org_id,
                                      note="Booking fee / titipan dialihkan ke termin (otomatis saat jadwal tagihan terbit)")
            inv = {**inv, **{k: res["invoice"][k] for k in ("items", "paid", "outstanding", "status")}}
        except ValueError:
            logger.exception("Pengalihan titipan otomatis gagal untuk deal %s", deal_id)
    return inv


def _allocate(items: list, amount: int, targets: dict = None, skip_kpr_excluded: bool = False) -> tuple:
    """Alokasi uang ke item termin. Mengubah `items` di tempat.

    `targets` = {item_id: nominal} — alokasi yang DIPILIH kasir/pembeli didahulukan (jelas
    termin mana yang dibayar); sisanya (bila ada) jatuh ke termin jatuh tempo terlama (FIFO).
    `skip_kpr_excluded` (pencairan KPR): baris add-on `kpr_excluded` TIDAK boleh dilunasi bank.
    Return (allocations, remaining). `remaining` > 0 berarti uangnya melebihi seluruh sisa tagihan.
    """
    remaining = int(amount)
    allocations = []
    for item_id, want in (targets or {}).items():
        it = next((x for x in items if x.get("id") == item_id), None)
        if not it:
            raise ValueError("Termin tujuan alokasi tidak ditemukan pada jadwal tagihan ini.")
        if skip_kpr_excluded and it.get("kpr_excluded"):
            raise ValueError(f"'{it['label']}' ditagih terpisah dan tidak boleh dilunasi pencairan KPR.")
        out = it["amount"] - it.get("paid_amount", 0)
        want = int(want or 0)
        if want <= 0:
            continue
        if want > out:
            raise ValueError(f"Alokasi Rp {want:,} untuk termin '{it['label']}' melebihi sisa termin Rp {out:,}.")
        if want > remaining:
            raise ValueError("Jumlah alokasi per termin melebihi total pembayaran.")
        it["paid_amount"] = it.get("paid_amount", 0) + want
        it["status"] = "paid" if it["paid_amount"] >= it["amount"] else "partial"
        remaining -= want
        allocations.append({"item_id": it["id"], "label": it["label"], "amount": want, "chosen": True})
    for it in sorted(items, key=lambda x: x.get("due_date") or ""):
        if remaining <= 0:
            break
        if skip_kpr_excluded and it.get("kpr_excluded"):
            continue
        out = it["amount"] - it.get("paid_amount", 0)
        if out <= 0:
            continue
        pay = min(out, remaining)
        it["paid_amount"] = it.get("paid_amount", 0) + pay
        it["status"] = "paid" if it["paid_amount"] >= it["amount"] else "partial"
        remaining -= pay
        allocations.append({"item_id": it["id"], "label": it["label"], "amount": pay})
    return allocations, remaining


def kpr_outstanding(inv: dict) -> int:
    """Sisa piutang yang BOLEH dilunasi pencairan KPR = termin unit saja (tanpa baris add-on)."""
    return sum(int(i.get("amount") or 0) - int(i.get("paid_amount") or 0)
               for i in inv.get("items") or [] if not i.get("kpr_excluded"))


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
                        allow_overpay=False, cash_account_id=None, targets: dict = None) -> dict:
    """Terima pembayaran -> alokasi ke item termin (pilihan kasir dulu, lalu jatuh tempo terlama) ->
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
    is_kpr = str(method or "").lower() == "kpr"
    outstanding_before = int(inv.get("outstanding", inv["total"] - inv.get("paid", 0)))
    if is_kpr:
        outstanding_before = kpr_outstanding(inv)
    allocations, excess = _allocate(items, amount, targets, skip_kpr_excluded=is_kpr)
    if excess > 0 and not allow_overpay:
        raise ValueError(
            f"Jumlah Rp {amount:,} melebihi sisa tagihan Rp {outstanding_before:,} "
            f"(kelebihan Rp {excess:,}). Centang \u201cCatat kelebihan sebagai titipan "
            f"pelanggan\u201d bila pembayaran ini memang diterima.")
    applied = amount - excess
    ts = now_iso()
    # Fase 82: setiap penerimaan menyebut rekening/kas tempat uang mendarat (default bila kosong).
    import cash_bank as _cb
    cash_code = await _cb.resolve_code(org_id, cash_account_id,
                                       "1-1100" if method in ("cash", "tunai") else "1-1200")
    cash_acc = await _cb.account_by_code(org_id, cash_code)
    cash_account_id = (cash_acc or {}).get("id")
    paid, outstanding, status = await _recalc_invoice(inv, items, ts)
    receipt = {
        "id": new_id(), "org_id": org_id,
        # Kwitansi WAJIB bernomor. Sebelum ini nomornya tidak pernah ada, jadi PDF kwitansi
        # yang kini bisa diunduh PEMBELI di portal (Fase 51C) memakai UUID sebagai "nomor
        # dokumen" — kwitansi tanpa nomor urut bukan bukti yang bisa diaudit.
        "receipt_no": await seq.next_number("receipt", org_id, prefix="KWT",
                                            context={"unit_id": inv.get("unit_id"),
                                                     "customer_id": inv.get("customer_id")}),
        "deal_id": deal_id, "unit_id": inv.get("unit_id"),
        "unit_code": inv.get("unit_code"), "amount": amount, "applied": applied,
        "deposit_amount": excess, "funding": "cash", "method": method or "transfer",
        "cash_account_id": cash_account_id, "cash_account_name": (cash_acc or {}).get("name"),
        "cash_account_code": cash_code,
        "note": note, "allocations": allocations, "actor": actor, "created_at": ts}
    await db.receipts.insert_one(dict(receipt))
    if applied > 0:
        await db.contract_liabilities.update_one(
            {"org_id": org_id, "deal_id": deal_id},
            {"$inc": {"balance": applied}, "$set": {"updated_at": ts}}, upsert=True)
        # `receipt_id` WAJIB ikut: jurnal GL menunjuk kuitansinya (bukan deal), supaya satu
        # deal dengan beberapa penerimaan tetap bisa direkonstruksi & dibalik satu per satu.
        await emit("payment.received", "deal", deal_id,
                   {"amount": applied, "receipt_id": receipt["id"],
                    "cash_account_id": cash_account_id}, org_id=org_id)
    deposit = None
    if excess > 0:
        deposit = await _deposit_move(org_id, deal_id, inv, "in", excess,
                                      note or "Kelebihan bayar", actor, receipt_id=receipt["id"],
                                      cash_account_id=cash_account_id)
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
async def _deposit_move(org_id, deal_id, inv, kind, amount, note, actor, receipt_id=None,
                        cash_account_id=None) -> dict:
    """Catat satu mutasi titipan (in/apply/refund) + jurnal GL. Return dokumen titipan terkini."""
    amount = int(amount)
    ts = now_iso()
    entry = {"id": new_id(), "type": kind, "amount": amount, "note": note,
             "actor": actor, "receipt_id": receipt_id, "cash_account_id": cash_account_id,
             "created_at": ts}
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
               "deposit", dep["id"], {"amount": amount, "deal_id": deal_id,
                                      "cash_account_id": cash_account_id}, org_id=org_id)
    return dep


async def get_deposit(org_id, deal_id) -> dict:
    dep = await db.customer_deposits.find_one({"org_id": org_id, "deal_id": deal_id}, {"_id": 0})
    return dep or {"deal_id": deal_id, "balance": 0, "entries": []}


async def receive_deposit(deal_id, amount, note, actor, org_id=ORG_ID, cash_account_id=None) -> dict:
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
                              note or "Titipan diterima di muka", actor,
                              cash_account_id=cash_account_id)
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
        "receipt_no": await seq.next_number("receipt", org_id, prefix="KWT",
                                            context={"unit_id": inv.get("unit_id"),
                                                     "customer_id": inv.get("customer_id")}),
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


async def refund_deposit(deal_id, amount, note, actor, org_id=ORG_ID, cash_account_id=None) -> dict:
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
                                  note or "Pengembalian titipan", actor,
                                  cash_account_id=cash_account_id)
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


async def pay_commission(commission_id, payer, org_id=ORG_ID, cash_account_id=None) -> dict:
    """Bayarkan komisi yang sudah disetujui (approved -> paid). Idempotent."""
    com = await db.commissions.find_one({"id": commission_id, "org_id": org_id}, {"_id": 0})
    if not com:
        raise ValueError("Komisi tidak ditemukan.")
    if com.get("status") == "paid":
        return com
    if com.get("status") != "approved":
        raise ValueError("Komisi harus disetujui terlebih dahulu sebelum dibayar.")
    import cash_bank as _cb
    cash_code = await _cb.resolve_code(org_id, cash_account_id, "1-1200")
    cash_acc = await _cb.account_by_code(org_id, cash_code)
    cash_account_id = (cash_acc or {}).get("id")
    ts = now_iso()
    await db.commissions.update_one({"id": commission_id},
        {"$set": {"status": "paid", "paid_by": payer, "paid_at": ts, "updated_at": ts,
                  "cash_account_id": cash_account_id,
                  "cash_account_name": (cash_acc or {}).get("name")}})
    await emit("commission.paid", "commission", commission_id,
               {"amount": int(com.get("amount", 0)), "cash_account_id": cash_account_id},
               org_id=org_id)
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


# ----------------------------- Thin AP: lihat finance_ap.py -----------------------------
from finance_ap import create_ap_bill, approve_ap_bill, pay_ap_bill, ap_retention_release_sweeper  # noqa: E402,F401


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
    # FIN-03 (K-5): rumus lama `sisa/total×90` BUKAN DSO. Dinamai jujur: porsi belum tertagih.
    outstanding_pct = round(agg["total"] / total_value * 100, 1) if total_value else 0.0
    return {**agg, "outstanding_pct": outstanding_pct, "total_value": total_value}


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
        "ar_outstanding": ar["total"], "ar_buckets": ar["buckets"],
        "ar_outstanding_pct": ar["outstanding_pct"], "ar_total_value": ar["total_value"],
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
