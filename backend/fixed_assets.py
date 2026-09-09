"""Aset Tetap + Penyusutan (Fase 27 — menutup gap kompetitor #7).

Mengikuti kerangka fiskal Indonesia (Pasal 11 UU PPh / PMK 72-2023): kelompok 1–4
(4/8/16/20 tahun), bangunan permanen 20 tahun, tidak permanen 10 tahun, tanah tidak
disusutkan. Metode: garis lurus & saldo menurun ganda.

Jurnal (idempoten via `source_event`):
    Perolehan   Dr 1-2100 Aset Tetap            / Cr 1-1100 Kas | 1-1200 Bank | 2-1100 Utang Usaha
    Penyusutan  Dr 6-1500 Beban Penyusutan      / Cr 1-2200 Akumulasi Penyusutan   [per aset per periode]
    Pelepasan   Dr kas (hasil) + Dr 1-2200      / Cr 1-2100 (+ Cr 4-1300 laba | Dr 6-1800 rugi)

Invarian: 1-2100 = Σ harga perolehan aset belum dilepas; saldo kredit 1-2200 =
Σ akumulasi penyusutan aset belum dilepas; nilai buku ≥ nilai residu.
"""
import logging

import gl_engine as gl
import reference_p27 as r27
import sequences as seq
from core_utils import new_id, now_iso
from db import db, ORG_ID
from engine import add_activity
from finance_engine import notify_finance
from p27_utils import (cash_account, current_period, period_end_iso, period_of, rp,
                       validate_period)

logger = logging.getLogger("sipro.assets")
ASSET_ACC = r27.ASSET_ACCOUNT                 # 1-2100
ACCUM_ACC = r27.ACCUM_DEPRECIATION_ACCOUNT    # 1-2200
EXPENSE_ACC = "6-1500"
GAIN_ACC = "4-1300"
LOSS_ACC = "6-1800"
FUNDING_ACCOUNT = {"kas": "1-1100", "bank": "1-1200", "utang_usaha": "2-1100"}


async def _get(asset_id: str, org_id: str) -> dict:
    doc = await db.fixed_assets.find_one({"id": asset_id, "org_id": org_id}, {"_id": 0})
    if not doc:
        raise ValueError("Aset tetap tidak ditemukan.")
    return doc


def default_life_months(tax_group: str) -> int:
    return int(r27.TAX_GROUP_MONTHS.get(tax_group, 0))


def monthly_amount(asset: dict) -> int:
    """Beban penyusutan satu bulan berikutnya (integer, tidak melewati batas susut)."""
    cost = int(asset.get("cost", 0))
    salvage = int(asset.get("salvage_value", 0))
    life = int(asset.get("useful_life_months", 0))
    accum = int(asset.get("accumulated_depreciation", 0))
    method = asset.get("method")
    base = max(0, cost - salvage)
    remaining = base - accum
    if life <= 0 or remaining <= 0 or method == "tidak_disusutkan":
        return 0
    if method == "saldo_menurun":
        rate = 2.0 / life
        amt = round((cost - accum) * rate)
    else:
        amt = round(base / life)
    return int(max(0, min(amt, remaining)))


def schedule(asset: dict, max_rows: int = 360) -> list:
    """Proyeksi jadwal penyusutan sisa (tanpa menulis apa pun)."""
    sim = dict(asset)
    rows = []
    period = asset.get("last_depreciated_period") or period_of(asset.get("acquired_date"))
    while len(rows) < max_rows:
        amt = monthly_amount(sim)
        if amt <= 0:
            break
        y, m = int(period[:4]), int(period[5:7])
        m += 1
        if m > 12:
            y, m = y + 1, 1
        period = f"{y:04d}-{m:02d}"
        accum = int(sim.get("accumulated_depreciation", 0)) + amt
        sim["accumulated_depreciation"] = accum
        rows.append({"period": period, "amount": amt, "accumulated": accum,
                     "book_value": int(sim["cost"]) - accum})
    return rows


async def _ap_bill_for_credit_purchase(asset: dict, actor: str, org_id: str) -> dict:
    """Perolehan aset secara UTANG wajib punya catatan utang di subledger AP.

    Tanpa ini, jurnal `Cr 2-1100 Utang Usaha` dari perolehan aset membuat saldo buku besar
    lebih besar daripada total tagihan vendor yang tercatat → gate invarian
    (`2-1100 = Σ (net − paid) tagihan disetujui`) GAGAL dan utangnya tidak bisa dibayar
    lewat menu AP. Tagihan dibuat langsung berstatus `approved` (keputusan pembelian aset
    memang sudah lewat persetujuan finance) dan SENGAJA tanpa emit `ap.approved`, karena
    jurnalnya sudah diposting oleh modul aset (Dr 1-2100, bukan Dr beban/WIP).
    """
    ts = now_iso()
    bill = {
        "id": new_id(), "org_id": org_id, "vendor": asset.get("vendor"),
        "project_id": asset.get("project_id"), "claimed": int(asset["cost"]),
        "retention_pct": 0.0, "retention_held": 0, "net": int(asset["cost"]),
        "paid": 0, "outstanding": int(asset["cost"]), "status": "approved",
        "due_date": None, "retention_released": False,
        "note": f"Perolehan aset tetap {asset['code']} — {asset['name']} (dibeli secara utang)",
        "source_type": "fixed_asset", "asset_id": asset["id"],
        "approved_by": actor, "approved_at": ts, "created_by": actor,
        "created_at": ts, "updated_at": ts,
    }
    await db.ap_invoices.insert_one(dict(bill))
    bill.pop("_id", None)
    return bill


async def create_asset(payload, actor: str, org_id=ORG_ID) -> dict:
    cost = int(payload.cost)
    salvage = int(payload.salvage_value or 0)
    if salvage >= cost:
        raise ValueError(f"Nilai residu {rp(salvage)} harus lebih kecil dari harga perolehan "
                         f"{rp(cost)}.")
    method = payload.method
    life = payload.useful_life_months
    life = int(life) if life is not None else default_life_months(payload.tax_group)
    if method == "tidak_disusutkan" or payload.tax_group == "tidak_disusutkan":
        method, life = "tidak_disusutkan", 0
    elif life <= 0:
        raise ValueError("Umur manfaat (bulan) harus lebih dari 0 untuk aset yang disusutkan.")
    if method == "saldo_menurun" and payload.tax_group in ("bangunan_permanen",
                                                           "bangunan_tidak_permanen"):
        raise ValueError("Bangunan hanya boleh disusutkan dengan metode garis lurus "
                         "(Pasal 11 UU PPh).")
    if payload.funding == "utang_usaha" and not (payload.vendor or "").strip():
        raise ValueError("Nama vendor wajib diisi untuk perolehan aset secara utang "
                         "(agar utangnya tercatat di daftar tagihan vendor).")
    ts = now_iso()
    acquired = payload.acquired_date or ts
    code = await seq.next_number("fixed_asset", org_id, prefix="AST", width=4,
                                 context={"category": payload.tax_group})
    project = None
    if payload.project_id:
        project = await db.projects.find_one({"id": payload.project_id, "org_id": org_id},
                                            {"_id": 0, "name": 1})
    doc = {
        "id": new_id(), "org_id": org_id, "code": code, "name": payload.name,
        "category": payload.category, "tax_group": payload.tax_group, "method": method,
        "cost": cost, "salvage_value": salvage, "useful_life_months": life,
        "acquired_date": acquired, "funding": payload.funding, "vendor": payload.vendor,
        "project_id": payload.project_id, "project_name": (project or {}).get("name"),
        "location": payload.location, "note": payload.note, "status": "active",
        "accumulated_depreciation": 0, "book_value": cost,
        "last_depreciated_period": None, "disposed_date": None, "disposal_proceeds": 0,
        "disposal_gain_loss": 0, "journal_ids": [], "created_by": actor,
        "created_at": ts, "updated_at": ts,
    }
    await db.fixed_assets.insert_one(dict(doc))
    doc.pop("_id", None)
    je = await gl.post_journal(
        org_id, f"Perolehan aset tetap {code} — {payload.name}",
        [{"account_code": ASSET_ACC, "debit": cost, "credit": 0},
         {"account_code": FUNDING_ACCOUNT.get(payload.funding, "1-1200"),
          "debit": 0, "credit": cost}],
        date=acquired, source_type="fixed_asset", source_id=doc["id"],
        source_event=f"asset.acquire:{doc['id']}", posted_by=actor)
    await db.fixed_assets.update_one({"id": doc["id"]},
                                     {"$push": {"journal_ids": je["id"]}})
    if payload.funding == "utang_usaha":
        bill = await _ap_bill_for_credit_purchase(doc, actor, org_id)
        await db.fixed_assets.update_one({"id": doc["id"]},
                                        {"$set": {"ap_bill_id": bill["id"]}})
    await add_activity(entity_type="fixed_asset", entity_id=doc["id"], type="system",
                       body=f"Aset {code} — {payload.name} dicatat {rp(cost)}. "
                            f"Jurnal {je['entry_no']}.", actor=actor, org_id=org_id)
    return await _get(doc["id"], org_id)


async def run_depreciation(period: str, actor: str, org_id=ORG_ID) -> dict:
    """Jalankan penyusutan satu periode untuk semua aset aktif. IDEMPOTEN per (aset, periode)."""
    p = validate_period(period)
    assets = await db.fixed_assets.find(
        {"org_id": org_id, "status": "active"}, {"_id": 0}).to_list(5000)
    posted, skipped, rows, total = 0, 0, [], 0
    date = period_end_iso(p)
    for a in assets:
        if a.get("method") == "tidak_disusutkan" or int(a.get("useful_life_months", 0)) <= 0:
            skipped += 1
            continue
        if period_of(a.get("acquired_date")) > p:
            skipped += 1
            continue
        exists = await db.asset_depreciations.find_one(
            {"org_id": org_id, "asset_id": a["id"], "period": p}, {"_id": 0, "id": 1})
        if exists:
            skipped += 1
            continue
        amt = monthly_amount(a)
        if amt <= 0:
            skipped += 1
            continue
        je = await gl.post_journal(
            org_id, f"Penyusutan {p} — {a['code']} {a['name']}",
            [{"account_code": EXPENSE_ACC, "debit": amt, "credit": 0},
             {"account_code": ACCUM_ACC, "debit": 0, "credit": amt}],
            date=date, source_type="asset_depreciation", source_id=a["id"],
            source_event=f"asset.depr:{a['id']}:{p}", posted_by=actor)
        accum = int(a.get("accumulated_depreciation", 0)) + amt
        base = int(a["cost"]) - int(a.get("salvage_value", 0))
        status = "fully_depreciated" if accum >= base else "active"
        await db.asset_depreciations.insert_one({
            "id": new_id(), "org_id": org_id, "asset_id": a["id"], "asset_code": a["code"],
            "asset_name": a["name"], "category": a.get("category"), "period": p,
            "amount": amt, "method": a.get("method"), "accumulated_after": accum,
            "book_value_after": int(a["cost"]) - accum, "journal_id": je["id"],
            "entry_no": je["entry_no"], "created_by": actor, "created_at": now_iso()})
        await db.fixed_assets.update_one({"id": a["id"]}, {"$set": {
            "accumulated_depreciation": accum, "book_value": int(a["cost"]) - accum,
            "last_depreciated_period": p, "status": status, "updated_at": now_iso()}})
        posted += 1
        total += amt
        rows.append({"asset_id": a["id"], "code": a["code"], "name": a["name"],
                     "amount": amt, "entry_no": je["entry_no"], "status": status})
    if posted:
        await notify_finance(org_id, f"Penyusutan periode {p} diposting",
                             f"{posted} aset disusutkan, total beban {rp(total)}.",
                             "finance", "asset_depreciation", p)
    return {"period": p, "posted": posted, "skipped": skipped, "total_amount": total,
            "rows": rows, "already_posted": posted == 0 and bool(assets)}


async def dispose_asset(asset_id: str, proceeds: int, source: str, date, note,
                        actor: str, org_id=ORG_ID) -> dict:
    """Lepas/jual aset: hapus perolehan + akumulasi, akui laba/rugi pelepasan."""
    a = await _get(asset_id, org_id)
    if a["status"] == "disposed":
        raise ValueError("Aset ini sudah dilepas sebelumnya.")
    cost = int(a["cost"])
    accum = int(a.get("accumulated_depreciation", 0))
    proceeds = int(proceeds or 0)
    book_value = cost - accum
    gain = proceeds - book_value
    lines = []
    if proceeds:
        lines.append({"account_code": cash_account(source), "debit": proceeds, "credit": 0,
                      "memo": "hasil pelepasan aset"})
    if accum:
        lines.append({"account_code": ACCUM_ACC, "debit": accum, "credit": 0,
                      "memo": "hapus akumulasi penyusutan"})
    if gain < 0:
        lines.append({"account_code": LOSS_ACC, "debit": -gain, "credit": 0,
                      "memo": "kerugian pelepasan"})
    lines.append({"account_code": ASSET_ACC, "debit": 0, "credit": cost})
    if gain > 0:
        lines.append({"account_code": GAIN_ACC, "debit": 0, "credit": gain,
                      "memo": "laba pelepasan"})
    ts = now_iso()
    je = await gl.post_journal(
        org_id, f"Pelepasan aset tetap {a['code']} — {a['name']}", lines,
        date=date or ts, source_type="fixed_asset", source_id=asset_id,
        source_event=f"asset.dispose:{asset_id}", posted_by=actor)
    await db.fixed_assets.update_one({"id": asset_id}, {"$set": {
        "status": "disposed", "disposed_date": date or ts, "disposal_proceeds": proceeds,
        "disposal_gain_loss": gain, "disposal_note": note, "disposed_by": actor,
        "book_value": 0, "updated_at": ts}, "$push": {"journal_ids": je["id"]}})
    label = "laba" if gain > 0 else ("rugi" if gain < 0 else "tanpa laba/rugi")
    await add_activity(entity_type="fixed_asset", entity_id=asset_id, type="system",
                       body=f"Aset {a['code']} dilepas. Hasil {rp(proceeds)}, nilai buku "
                            f"{rp(book_value)}, {label} {rp(abs(gain))}. Jurnal {je['entry_no']}.",
                       actor=actor, org_id=org_id)
    return await _get(asset_id, org_id)


async def summary(org_id=ORG_ID) -> dict:
    rows = await db.fixed_assets.find({"org_id": org_id}, {"_id": 0}).to_list(5000)
    live = [r for r in rows if r["status"] != "disposed"]
    cost = sum(int(r["cost"]) for r in live)
    accum = sum(int(r.get("accumulated_depreciation", 0)) for r in live)
    per_cat = {}
    for r in live:
        c = per_cat.setdefault(r["category"], {"category": r["category"], "count": 0,
                                               "cost": 0, "accumulated": 0, "book_value": 0})
        c["count"] += 1
        c["cost"] += int(r["cost"])
        c["accumulated"] += int(r.get("accumulated_depreciation", 0))
        c["book_value"] = c["cost"] - c["accumulated"]
    period = current_period()
    this_month = 0
    async for d in db.asset_depreciations.aggregate([
            {"$match": {"org_id": org_id, "period": period}},
            {"$group": {"_id": None, "s": {"$sum": "$amount"}}}]):
        this_month = int(d.get("s") or 0)
    return {
        "count": len(rows), "active_count": sum(1 for r in live if r["status"] == "active"),
        "fully_depreciated_count": sum(1 for r in live if r["status"] == "fully_depreciated"),
        "disposed_count": sum(1 for r in rows if r["status"] == "disposed"),
        "total_cost": cost, "total_accumulated": accum, "total_book_value": cost - accum,
        "depreciation_this_month": this_month, "current_period": period,
        "monthly_run_rate": sum(monthly_amount(r) for r in live if r["status"] == "active"),
        "by_category": sorted(per_cat.values(), key=lambda x: -x["cost"]),
        "disposal_gain_total": sum(int(r.get("disposal_gain_loss", 0)) for r in rows
                                   if r["status"] == "disposed"),
        "accounts": {"asset": ASSET_ACC, "accumulated": ACCUM_ACC, "expense": EXPENSE_ACC},
    }
