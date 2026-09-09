"""Arus kas PER PROYEK + paket laporan owner (Fase 49C & 49D).

Cacat nyata yang ditutup:

* **Arus kas hanya konsolidasi.** `gl_reports.cash_flow()` menjawab "berapa kas perusahaan
  bergerak", tetapi owner butuh "proyek mana yang MENGHISAP kas dan proyek mana yang
  MENGEMBALIKAN kas". Tanpa itu, keputusan menambah termin/menahan pembelian diambil tanpa
  angka.
* **Alokasi yang berbohong.** Jurnal SIPRO tidak menyimpan `project_id`; proyek disimpulkan
  dari dokumen sumber (`source_id`). Bila petanya kurang lengkap, transaksi nyata jatuh ke
  "tidak teralokasi" tanpa ada yang tahu. Karena itu modul ini (a) memperluas peta sumber ke
  dokumen Fase 47/48 (uang muka & retensi subkon, termin, rekap upah, PO/penerimaan, kas bon),
  (b) SELALU menampilkan baris "tidak teralokasi" apa adanya, dan (c) membuktikan
  **tie-out**: Σ arus kas semua proyek + tidak teralokasi = arus kas konsolidasi.

Uang IDR integer; waktu UTC ISO-8601.
"""
import logging

import gl_reports as glr
from db import db, ORG_ID

logger = logging.getLogger("sipro.gl.project_cash")

# Koleksi yang id-nya bisa muncul sebagai `source_id` sebuah jurnal, beserta cara
# menemukan proyeknya. "direct" = dokumen menyimpan project_id sendiri.
DIRECT_COLLECTIONS = (
    "ap_invoices", "purchase_orders", "grns", "progress_claims", "subcon_advances",
    "subcon_retentions", "labor_payrolls", "cash_advances", "material_txns",
    "procurement_returns", "budget_entries",
    # Fase 49C (perbaikan setelah diuji dengan data nyata): tiga koleksi ini MENYIMPAN
    # project_id tetapi tidak pernah dibaca, sehingga pembayaran fee mitra, perolehan aset,
    # dan pembiayaan yang MEMANG milik satu proyek selalu jatuh ke "tidak teralokasi".
    "marketing_fees", "fixed_assets", "loans",
)
# Koleksi yang hanya menyimpan deal_id (proyeknya ada di deal).
VIA_DEAL_COLLECTIONS = (
    "commissions", "revenue_recognitions", "receipts", "tax_records", "ar_invoices",
    "contract_liabilities", "faktur_pajak", "payment_intakes",
)


async def project_resolver(org_id=ORG_ID):
    """Peta id dokumen sumber -> project_id, seluas yang bisa dibuktikan datanya."""
    deals = {d["id"]: d.get("project_id") for d in await db.deals.find(
        {"org_id": org_id}, {"_id": 0, "id": 1, "project_id": 1}).to_list(20000)}
    direct = {}
    for coll in DIRECT_COLLECTIONS:
        try:
            for r in await db[coll].find({"org_id": org_id},
                                         {"_id": 0, "id": 1, "project_id": 1}).to_list(50000):
                if r.get("project_id"):
                    direct[r["id"]] = r["project_id"]
        except Exception:  # noqa: BLE001 — koleksi belum ada di database baru
            logger.debug("koleksi %s dilewati", coll, exc_info=True)
    via_deal = {}
    for coll in VIA_DEAL_COLLECTIONS:
        try:
            for r in await db[coll].find({"org_id": org_id},
                                         {"_id": 0, "id": 1, "deal_id": 1}).to_list(50000):
                if r.get("deal_id"):
                    via_deal[r["id"]] = r["deal_id"]
        except Exception:  # noqa: BLE001
            logger.debug("koleksi %s dilewati", coll, exc_info=True)
    payments = {}
    # Satu baris `payments_out` bisa membayar tagihan vendor (`bill_id`) ATAU fee mitra
    # (`marketing_fee_id`). Dulu hanya `bill_id` yang dibaca, jadi setiap pembayaran fee
    # mitra hilang dari arus kas proyeknya walau fee itu jelas menempel satu unit/proyek.
    for r in await db.payments_out.find(
            {"org_id": org_id},
            {"_id": 0, "id": 1, "bill_id": 1, "marketing_fee_id": 1}).to_list(50000):
        for key in ("bill_id", "marketing_fee_id"):
            ref_id = r.get(key)
            if ref_id and ref_id in direct:
                payments[r["id"]] = direct[ref_id]
                break

    def resolve(source_id, source_deal_id=None):
        if source_deal_id and source_deal_id in deals:
            return deals[source_deal_id]
        if not source_id:
            return None
        if source_id in direct:
            return direct[source_id]
        if source_id in payments:
            return payments[source_id]
        if source_id in deals:
            return deals[source_id]
        did = via_deal.get(source_id)
        if did:
            return deals.get(did)
        return None
    return resolve


def _blank(pid, name, code=None) -> dict:
    return {"project_id": pid, "project_name": name, "project_code": code,
            "operating": 0, "investing": 0, "financing": 0,
            "inflow": 0, "outflow": 0, "net_change": 0, "entries": 0}


async def cash_flow_projects(org_id=ORG_ID, date_from=None, date_to=None) -> dict:
    """Arus kas per proyek + baris "tidak teralokasi" + bukti tie-out ke konsolidasi."""
    p = glr.normalize_period(date_from, date_to)
    accts = await glr.accounts_map(org_id)
    cash_codes = {c for c in accts if c.startswith(glr.CASH_PREFIX)}
    resolve = await project_resolver(org_id)
    projects = {pr["id"]: pr for pr in await db.projects.find(
        {"org_id": org_id}, {"_id": 0, "id": 1, "name": 1, "code": 1}).to_list(2000)}

    rows = {}
    q = {"org_id": org_id, "lines.account_code": {"$in": list(cash_codes)},
         **glr._date_query(p["date_from"], p["date_to"])}
    entries = await db.journal_entries.find(q, {"_id": 0}).sort([("date", 1)]).to_list(100000)
    consolidated_net = 0
    for je in entries:
        pid = resolve(je.get("source_id"), je.get("source_deal_id"))
        if pid not in projects:
            pid = None
        if pid not in rows:
            pr = projects.get(pid) or {}
            rows[pid] = _blank(pid, pr.get("name") or "Tidak teralokasi ke proyek",
                               pr.get("code"))
        tgt = rows[pid]
        tgt["entries"] += 1
        for ln in je.get("lines", []):
            code = ln["account_code"]
            dr, cr = int(ln.get("debit", 0) or 0), int(ln.get("credit", 0) or 0)
            if code in cash_codes:
                delta = dr - cr
                consolidated_net += delta
                tgt["net_change"] += delta
                tgt["inflow" if delta > 0 else "outflow"] += abs(delta)
                continue
            amt = cr - dr  # positif = sumber kas masuk
            if amt:
                tgt[glr._cash_category(code)] += amt

    out = [r for pid, r in rows.items() if pid is not None]
    out.sort(key=lambda r: (r["net_change"], r["project_name"] or ""))
    unassigned = rows.get(None)
    sum_projects = sum(r["net_change"] for r in rows.values())
    cf = await glr.cash_flow(org_id, date_from, date_to)
    tie_out = {
        "sum_projects": sum_projects,
        "consolidated_net_change": cf["net_change"],
        "diff": sum_projects - cf["net_change"],
        "matches": sum_projects == cf["net_change"] == consolidated_net,
        "detail": ("Σ arus kas per proyek + tidak teralokasi = arus kas konsolidasi."
                   if sum_projects == cf["net_change"]
                   else "Selisih ditemukan — laporkan ke admin sistem, jangan dipakai."),
    }
    return {
        "period": p, "rows": out, "unassigned": unassigned,
        "consolidated": {"opening_cash": cf["opening_cash"], "closing_cash": cf["closing_cash"],
                         "net_change": cf["net_change"], "operating": cf["operating"]["total"],
                         "investing": cf["investing"]["total"], "financing": cf["financing"]["total"]},
        "tie_out": tie_out,
        "missing": [] if entries else ["jurnal_kas"],
        "detail": ("Belum ada mutasi kas pada periode ini — belum ada data yang bisa dibagi "
                   "per proyek." if not entries else
                   f"{len(entries)} jurnal kas dibagi ke {len(out)} proyek"
                   + (" + 1 baris tidak teralokasi." if unassigned else ".")),
        "cash_accounts": sorted(cash_codes),
    }
