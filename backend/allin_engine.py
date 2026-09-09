"""Fase 76-77 — Master KOMPONEN BIAYA + SKEMA ALL-IN + penagihan/pembukuan biaya.

Dua makna nyata di praktik properti Indonesia:
  * `developer_borne`        → "harga all-in": biaya sudah termasuk harga, developer yang membayar
                               notaris/BPN → BEBAN penjualan (lewat AP), tidak ditagih ke pembeli.
  * `customer_pass_through`  → "harga exclude": pembeli bayar terpisah; developer hanya MENAMPUNG
                               (titipan = kewajiban, bukan pendapatan) lalu MENYALURKAN ke notaris/BPN.
Perlakuan dikunci PER KOMPONEN di master; sales hanya memilih skema. Nominal biaya TIDAK PERNAH
masuk piutang unit (piutang tetap = harga − DP/booking).
"""
import logging

import finance_engine as fe
import gl_engine as gl
import sequences as seq
from core_utils import new_id, now_iso
from db import db
from engine import add_activity

logger = logging.getLogger("sipro.allin")

CALC_METHODS = ("nominal_tetap", "persen_harga", "rumus_bphtb")
TREATMENTS = ("developer_borne", "customer_pass_through")
GL_BANK = "1-1200"
GL_TITIPAN_BIAYA = "2-1470"
GL_BEBAN_PENJUALAN = "6-1700"
GL_AP = "2-1100"
MANUAL_ROLES = ("finance_manager", "super_admin", "owner")  # = pemegang izin finance:manage


async def may_manual(user: dict) -> bool:
    """Input biaya manual / koreksi & pembatalan pencairan KPR: SATU izin `finance:manage`
    (ROLE_GRANTS finance_manager; owner/super_admin implisit) dipakai backend & layar."""
    from rbac import can
    return await can(user.get("role"), "finance", "manage")

DEFAULT_COMPONENTS = [
    {"code": "BPHTB", "name": "BPHTB", "calc_method": "rumus_bphtb", "pct": 5.0, "amount": 0,
     "default_treatment": "customer_pass_through"},
    {"code": "NOTARY_FEE", "name": "Biaya notaris / akad", "calc_method": "nominal_tetap",
     "amount": 7_500_000, "default_treatment": "customer_pass_through"},
    {"code": "BANK_FEE", "name": "Biaya bank (provisi, admin, materai)", "calc_method": "persen_harga",
     "pct": 1.0, "amount": 0, "default_treatment": "customer_pass_through", "kpr_only": True},
    {"code": "INSURANCE", "name": "Asuransi jiwa & kebakaran", "calc_method": "nominal_tetap",
     "amount": 3_000_000, "default_treatment": "customer_pass_through", "kpr_only": True},
    {"code": "LEGACY", "name": "Biaya (input bebas — kontrak lama)", "calc_method": "nominal_tetap",
     "amount": 0, "default_treatment": "customer_pass_through", "is_legacy": True},
]
DEFAULT_SCHEMES = [
    {"code": "ALLIN_STD", "name": "All-in Standar", "note": "BPHTB + notaris ditanggung developer.",
     "items": [{"component_code": "BPHTB", "treatment": "developer_borne"},
               {"component_code": "NOTARY_FEE", "treatment": "developer_borne"},
               {"component_code": "BANK_FEE", "treatment": "customer_pass_through"},
               {"component_code": "INSURANCE", "treatment": "customer_pass_through"}]},
    {"code": "EXCLUDE", "name": "Exclude (semua biaya pembeli)", "note": "Developer hanya menampung & menyalurkan.",
     "items": [{"component_code": "BPHTB", "treatment": "customer_pass_through"},
               {"component_code": "NOTARY_FEE", "treatment": "customer_pass_through"},
               {"component_code": "BANK_FEE", "treatment": "customer_pass_through"},
               {"component_code": "INSURANCE", "treatment": "customer_pass_through"}]},
]


# ============================================================ master
async def ensure_defaults(org: str):
    """Seed komponen & skema bawaan (idempoten per kode) + akun GL titipan/beban."""
    ts = now_iso()
    for c in DEFAULT_COMPONENTS:
        await db.cost_components.update_one(
            {"org_id": org, "code": c["code"]},
            {"$setOnInsert": {"id": new_id(), "org_id": org, "is_active": True, "pct": 0.0,
                              "gl_expense": GL_BEBAN_PENJUALAN, "gl_liability": GL_TITIPAN_BIAYA,
                              "gl_ap": GL_AP, "created_at": ts, "updated_at": ts, **c}},
            upsert=True)
    for s in DEFAULT_SCHEMES:
        await db.allin_schemes.update_one(
            {"org_id": org, "code": s["code"]},
            {"$setOnInsert": {"id": new_id(), "org_id": org, "is_active": True,
                              "project_ids": [], "unit_types": [],
                              "created_at": ts, "updated_at": ts, **s}},
            upsert=True)
    await gl.ensure_coa(org)


async def list_components(org: str, include_inactive=False) -> list:
    q = {"org_id": org}
    if not include_inactive:
        q["is_active"] = True
    return await db.cost_components.find(q, {"_id": 0}).sort("code", 1).to_list(200)


async def list_schemes(org: str, project_id: str = None, unit_type: str = None,
                       include_inactive=False) -> list:
    q = {"org_id": org}
    if not include_inactive:
        q["is_active"] = True
    rows = await db.allin_schemes.find(q, {"_id": 0}).sort("name", 1).to_list(200)
    if project_id:
        rows = [r for r in rows if not r.get("project_ids") or project_id in r["project_ids"]]
    if unit_type:
        rows = [r for r in rows if not r.get("unit_types") or unit_type in r["unit_types"]]
    return rows


# ============================================================ perhitungan
async def npoptkp_for(org: str, project_id: str) -> int:
    proj = await db.projects.find_one({"id": project_id}, {"_id": 0, "npoptkp": 1}) if project_id else None
    if proj and proj.get("npoptkp") is not None:
        return int(proj["npoptkp"])
    cfgd = await fe.get_finance_config(org)
    return int(cfgd.get("npoptkp") or 0)


def compute_amount(comp: dict, price: int, npoptkp: int, override: int = None) -> tuple:
    """(nominal, rumus-teks). Override nominal terkunci dari skema menang atas rumus."""
    if override is not None:
        return int(override), "nominal terkunci skema"
    m = comp.get("calc_method")
    if m == "persen_harga":
        pct = float(comp.get("pct") or 0)
        return int(round(price * pct / 100)), f"{pct:g}% × harga"
    if m == "rumus_bphtb":
        pct = float(comp.get("pct") or 5)
        base = max(0, int(price) - int(npoptkp))
        return int(round(base * pct / 100)), f"{pct:g}% × (harga − NPOPTKP Rp {npoptkp:,})".replace(",", ".")
    return int(comp.get("amount") or 0), "nominal tetap"


async def resolve_scheme(org: str, scheme_id: str, price: int, project_id: str = None,
                         scheme: str = None) -> dict:
    """Snapshot komponen dari skema all-in untuk harga ini → disimpan di `deal.costs`."""
    sch = await db.allin_schemes.find_one({"org_id": org, "id": scheme_id}, {"_id": 0})
    if not sch:
        raise ValueError("Skema all-in tidak ditemukan.")
    if not sch.get("is_active", True):
        raise ValueError("Skema all-in ini sudah nonaktif — pilih skema lain.")
    comps = {c["code"]: c for c in await list_components(org, include_inactive=True)}
    npoptkp = await npoptkp_for(org, project_id)
    components = []
    for it in sch.get("items") or []:
        comp = comps.get(it.get("component_code"))
        if not comp:
            continue
        if comp.get("kpr_only") and scheme and scheme != "kpr":
            continue
        amount, formula = compute_amount(comp, int(price), npoptkp, it.get("override_amount"))
        components.append({
            "code": comp["code"], "name": comp["name"], "amount": amount,
            "treatment": it.get("treatment") or comp.get("default_treatment"),
            "calc_method": comp.get("calc_method"), "formula": formula,
            "kpr_only": bool(comp.get("kpr_only")),
            "gl_expense": comp.get("gl_expense") or GL_BEBAN_PENJUALAN,
            "gl_liability": comp.get("gl_liability") or GL_TITIPAN_BIAYA,
            "gl_ap": comp.get("gl_ap") or GL_AP, "source": "scheme"})
    return {"scheme_id": sch["id"], "scheme_code": sch.get("code"), "scheme_name": sch["name"],
            "npoptkp": npoptkp, "components": components}


def manual_components(items: list, reason: str, actor: str) -> dict:
    """Input manual (hanya finance_manager/superadmin) — wajib alasan, setiap baris ter-audit."""
    if len((reason or "").strip()) < 10:
        raise ValueError("Input biaya manual wajib alasan (minimal 10 huruf).")
    out = []
    for it in items or []:
        code = (it.get("code") or "").strip().upper()
        if not code or it.get("amount") is None:
            raise ValueError("Komponen manual wajib kode & nominal.")
        tr = it.get("treatment") or "customer_pass_through"
        if tr not in TREATMENTS:
            raise ValueError(f"Perlakuan '{tr}' tidak dikenal.")
        out.append({"code": code, "name": it.get("name") or code, "amount": int(it["amount"]),
                    "treatment": tr, "calc_method": "nominal_tetap", "formula": "manual",
                    "gl_expense": GL_BEBAN_PENJUALAN, "gl_liability": GL_TITIPAN_BIAYA,
                    "gl_ap": GL_AP, "source": "manual"})
    return {"scheme_id": None, "scheme_code": "MANUAL", "scheme_name": "Manual (finance)",
            "manual_reason": reason.strip(), "manual_by": actor, "components": out}


def legacy_components(costs: dict, scheme: str = None) -> list:
    """Pemetaan `costs` bebas (kontrak lama) → komponen LEGACY agar breakdown tidak berubah."""
    labels = {"bphtb": "BPHTB", "notary_fee": "Biaya notaris / akad",
              "bank_fee": "Biaya bank (provisi, admin, blokir, materai)",
              "insurance": "Asuransi jiwa & kebakaran"}
    dev = bool(costs.get("all_in_by_developer"))
    out = []
    for k, label in labels.items():
        if costs.get(k) is None:
            continue
        out.append({"code": k.upper(), "name": label, "amount": int(costs[k]),
                    "treatment": "developer_borne" if dev else "customer_pass_through",
                    "calc_method": "nominal_tetap", "formula": "legacy", "component_code": "LEGACY",
                    "kpr_only": k in ("bank_fee", "insurance"),
                    "gl_expense": GL_BEBAN_PENJUALAN, "gl_liability": GL_TITIPAN_BIAYA,
                    "gl_ap": GL_AP, "source": "legacy"})
    return out


async def migrate_legacy_contracts(org: str) -> int:
    """Kontrak dengan `costs` bebas tanpa `components` → snapshot LEGACY (sekali, idempoten)."""
    n = 0
    cur = db.contracts.find({"org_id": org, "costs": {"$exists": True},
                             "costs.components": {"$exists": False}}, {"_id": 0, "id": 1, "costs": 1, "scheme": 1})
    async for c in cur:
        costs = c.get("costs") or {}
        comps = legacy_components(costs, c.get("scheme"))
        if not comps:
            continue
        await db.contracts.update_one({"id": c["id"]}, {"$set": {
            "costs.components": comps, "costs.scheme_code": "LEGACY",
            "costs.scheme_name": "Legacy (input bebas)", "costs.migrated_at": now_iso()}})
        n += 1
    return n


# ============================================================ penagihan & pembukuan biaya
def _applicable(contract: dict) -> list:
    return [c for c in (contract.get("costs") or {}).get("components") or []
            if not (c.get("kpr_only") and contract.get("scheme") != "kpr")]


def _pass_through(contract: dict) -> list:
    return [c for c in _applicable(contract)
            if c.get("treatment") == "customer_pass_through" and int(c.get("amount") or 0) > 0]


def _scope(contract: dict) -> dict:
    """Invoice/kuitansi biaya lahir saat BOOKING (sebelum kontrak ada) → dicari lewat deal_id juga."""
    ors = [{"deal_id": contract.get("deal_id")}] if contract.get("deal_id") else []
    if contract.get("id"):
        ors.append({"contract_id": contract["id"]})
    return {"$or": ors} if ors else {"contract_id": None, "deal_id": None}


async def deal_as_contract(org: str, deal: dict) -> dict:
    """Bentuk 'kontrak semu' dari deal untuk menerbitkan invoice biaya SAAT BOOKING —
    piutang biaya per komponen tercatat di Finance bersamaan dengan piutang unit."""
    sch = await db.payment_schemes.find_one({"id": deal.get("scheme_id")}, {"_id": 0, "kind": 1, "type": 1}) \
        if deal.get("scheme_id") else None
    return {"id": deal.get("contract_id"), "deal_id": deal["id"], "costs": deal.get("costs") or {},
            "scheme": ((sch or {}).get("kind") or (sch or {}).get("type") or (deal.get("pricing") or {}).get("scheme", {}).get("type")),
            "customer_id": deal.get("customer_id"), "unit_id": deal.get("unit_id"),
            "unit_code": deal.get("unit_code"), "customer_name": deal.get("lead_name"),
            "number": deal.get("contract_id") or f"deal {deal.get('unit_code')}"}


async def link_cost_docs_to_contract(org: str, contract: dict) -> int:
    """Kontrak lahir → invoice/kuitansi biaya yang terbit saat booking diikat ke kontraknya."""
    n = 0
    for coll in ("cost_invoices", "cost_receipts", "cost_disbursements", "cost_expenses"):
        res = await db[coll].update_many(
            {"org_id": org, "deal_id": contract["deal_id"], "contract_id": None},
            {"$set": {"contract_id": contract["id"], "customer_id": contract.get("customer_id"),
                      "customer_name": contract.get("customer_name")}})
        n += res.modified_count
    return n


async def ledger(org: str, contract: dict) -> dict:
    """Invoice biaya, kuitansi biaya, penyaluran, sisa titipan, beban developer — per kontrak."""
    q = _scope(contract)
    invoices = await db.cost_invoices.find({"org_id": org, **q}, {"_id": 0}).to_list(50)
    receipts = await db.cost_receipts.find({"org_id": org, **q, "status": {"$ne": "void"}},
                                           {"_id": 0}).sort("created_at", 1).to_list(200)
    disb = await db.cost_disbursements.find({"org_id": org, **q}, {"_id": 0}).sort("created_at", 1).to_list(200)
    exp = await db.cost_expenses.find({"org_id": org, **q}, {"_id": 0}).sort("created_at", 1).to_list(200)
    received = sum(int(r["amount"]) for r in receipts)
    paid_out = sum(int(d["amount"]) for d in disb)
    invoiced = sum(int(i["total"]) for i in invoices if i.get("status") != "void")
    comps = _applicable(contract)
    dev_total = sum(int(c["amount"] or 0) for c in comps if c.get("treatment") == "developer_borne")
    return {"components": comps, "pass_through_total": sum(int(c["amount"]) for c in _pass_through(contract)),
            "developer_borne_total": dev_total,
            "developer_expensed": sum(int(e["amount"]) for e in exp),
            "invoices": invoices, "receipts": receipts, "disbursements": disb, "expenses": exp,
            "invoiced": invoiced, "received": received, "paid_out": paid_out,
            "titipan_balance": received - paid_out,
            "uninvoiced": max(0, sum(int(c["amount"]) for c in _pass_through(contract)) - invoiced)}


async def issue_cost_invoice(org: str, contract: dict, actor: str) -> dict:
    """Terbitkan INVOICE BIAYA (seri sendiri, bukan AR unit) untuk komponen pass-through."""
    comps = _pass_through(contract)
    if not comps:
        raise ValueError("Tidak ada komponen biaya yang ditagih ke pembeli (semua ditanggung developer "
                         "atau skema all-in belum dipilih).")
    exist = await db.cost_invoices.find_one({"org_id": org, **_scope(contract),
                                             "status": {"$ne": "void"}}, {"_id": 0})
    if exist:
        raise ValueError(f"Invoice biaya {exist['number']} sudah terbit untuk kontrak ini.")
    ts = now_iso()
    total = sum(int(c["amount"]) for c in comps)
    doc = {"id": new_id(), "org_id": org, "contract_id": contract.get("id"), "deal_id": contract.get("deal_id"),
           "customer_id": contract.get("customer_id"), "unit_id": contract.get("unit_id"),
           "unit_code": contract.get("unit_code"), "customer_name": contract.get("customer_name"),
           "number": await seq.next_number("cost_invoice", org, prefix="INB",
                                           context={"unit_id": contract.get("unit_id"),
                                                    "customer_id": contract.get("customer_id")}),
           "items": [{"code": c["code"], "name": c["name"], "amount": int(c["amount"]),
                      "discount": int(c.get("discount") or 0),
                      "gross": int(c["amount"]) + int(c.get("discount") or 0),
                      "discount_lines": c.get("discount_lines") or []} for c in comps],
           "total": total, "paid": 0, "outstanding": total, "status": "unpaid",
           "created_by": actor, "created_at": ts, "updated_at": ts}
    await db.cost_invoices.insert_one(dict(doc))
    doc.pop("_id", None)
    deal = await db.deals.find_one({"id": contract.get("deal_id")}, {"_id": 0, "lead_id": 1}) or {}
    await add_activity(entity_type="customer" if contract.get("customer_id") else "lead",
                       entity_id=contract.get("customer_id") or deal.get("lead_id"), type="finance",
                       actor=actor, org_id=org,
                       body=(f"Invoice biaya {doc['number']} terbit (Rp {total:,}) — piutang biaya per komponen, "
                             "terpisah dari piutang unit.").replace(",", "."))
    return doc


async def pay_cost_invoice(org: str, invoice_id: str, amount: int, method: str, note: str, actor: str) -> dict:
    """Kuitansi biaya → jurnal Kas / Titipan biaya customer (kewajiban, BUKAN pendapatan)."""
    inv = await db.cost_invoices.find_one({"org_id": org, "id": invoice_id}, {"_id": 0})
    if not inv or inv.get("status") == "void":
        raise ValueError("Invoice biaya tidak ditemukan.")
    amount = int(amount or 0)
    if amount <= 0:
        raise ValueError("Nominal pembayaran biaya wajib > 0.")
    if amount > int(inv["outstanding"]):
        raise ValueError(f"Nominal Rp {amount:,} melebihi sisa invoice biaya Rp {inv['outstanding']:,}.".replace(",", "."))
    ts = now_iso()
    rc = {"id": new_id(), "org_id": org, "contract_id": inv["contract_id"], "deal_id": inv.get("deal_id"),
          "invoice_id": inv["id"], "invoice_no": inv["number"], "unit_code": inv.get("unit_code"),
          "customer_name": inv.get("customer_name"), "kind": "cost",
          "receipt_no": await seq.next_number("cost_receipt", org, prefix="KWB",
                                              context={"unit_id": inv.get("unit_id"),
                                                       "customer_id": inv.get("customer_id")}),
          "amount": amount, "method": method or "transfer", "note": note, "status": "posted",
          "actor": actor, "created_at": ts}
    await db.cost_receipts.insert_one(dict(rc))
    rc.pop("_id", None)
    paid = int(inv["paid"]) + amount
    await db.cost_invoices.update_one({"id": inv["id"]}, {"$set": {
        "paid": paid, "outstanding": int(inv["total"]) - paid,
        "status": "paid" if paid >= int(inv["total"]) else "partial", "updated_at": ts}})
    je = await gl.post_journal(org, f"Titipan biaya pembeli diterima — {rc['receipt_no']}", [
        {"account_code": GL_BANK, "debit": amount, "credit": 0},
        {"account_code": GL_TITIPAN_BIAYA, "debit": 0, "credit": amount}],
        source_type="cost_receipt", source_id=rc["id"], source_event=f"cost_receipt:{rc['id']}",
        posted_by=actor, source_deal_id=inv.get("deal_id"))
    return {"receipt": rc, "journal_id": je.get("id")}


async def disburse_titipan(org: str, contract: dict, component_code: str, amount: int,
                           payee: str, note: str, actor: str) -> dict:
    """Salurkan titipan ke notaris/BPN → Titipan / Kas. Tidak boleh melebihi sisa titipan."""
    led = await ledger(org, contract)
    amount = int(amount or 0)
    if amount <= 0:
        raise ValueError("Nominal penyaluran wajib > 0.")
    if amount > led["titipan_balance"]:
        raise ValueError(f"Penyaluran Rp {amount:,} melebihi sisa titipan Rp {led['titipan_balance']:,}.".replace(",", "."))
    if not (payee or "").strip():
        raise ValueError("Penerima (notaris/BPN) wajib diisi.")
    ts = now_iso()
    doc = {"id": new_id(), "org_id": org, "contract_id": contract.get("id"), "deal_id": contract.get("deal_id"),
           "component_code": component_code, "amount": amount, "payee": payee.strip(), "note": note,
           "actor": actor, "created_at": ts}
    await db.cost_disbursements.insert_one(dict(doc))
    doc.pop("_id", None)
    je = await gl.post_journal(org, f"Penyaluran titipan biaya ({component_code}) ke {payee.strip()}", [
        {"account_code": GL_TITIPAN_BIAYA, "debit": amount, "credit": 0},
        {"account_code": GL_BANK, "debit": 0, "credit": amount}],
        source_type="cost_disbursement", source_id=doc["id"], source_event=f"cost_disb:{doc['id']}",
        posted_by=actor, source_deal_id=contract.get("deal_id"))
    return {"disbursement": doc, "journal_id": je.get("id"), "titipan_balance": led["titipan_balance"] - amount}


async def record_developer_expense(org: str, contract: dict, component_code: str, amount: int,
                                   vendor: str, note: str, actor: str) -> dict:
    """Komponen developer_borne: developer bayar notaris/BPN lewat AP → Beban penjualan / Utang usaha."""
    comps = {c["code"]: c for c in (contract.get("costs") or {}).get("components") or []}
    comp = comps.get(component_code)
    if not comp or comp.get("treatment") != "developer_borne":
        raise ValueError("Komponen ini bukan tanggungan developer (developer_borne).")
    amount = int(amount or comp.get("amount") or 0)
    if amount <= 0:
        raise ValueError("Nominal beban wajib > 0.")
    if await db.cost_expenses.find_one({"org_id": org, "contract_id": contract["id"], "component_code": component_code}):
        raise ValueError(f"Beban {component_code} untuk kontrak ini sudah dicatat.")
    deal = await db.deals.find_one({"id": contract.get("deal_id")}, {"_id": 0, "project_id": 1}) or {}
    bill = await fe.create_ap_bill(vendor or "Notaris/BPN", deal.get("project_id"), amount, 0, None,
                                   f"Biaya {comp['name']} all-in kontrak {contract.get('number')}", actor, org_id=org)
    ts = now_iso()
    await db.ap_invoices.update_one({"id": bill["id"]}, {"$set": {
        "status": "approved", "approved_by": actor, "approved_at": ts, "kind": "sales_cost",
        "contract_id": contract["id"], "component_code": component_code, "gl_expense": comp.get("gl_expense")}})
    je = await gl.post_journal(org, f"Beban penjualan {comp['name']} (all-in) — {contract.get('number')}", [
        {"account_code": comp.get("gl_expense") or GL_BEBAN_PENJUALAN, "debit": amount, "credit": 0},
        {"account_code": comp.get("gl_ap") or GL_AP, "debit": 0, "credit": amount}],
        source_type="ap_bill", source_id=bill["id"], source_event=f"ap.sales_cost:{bill['id']}",
        posted_by=actor, source_deal_id=contract.get("deal_id"))
    doc = {"id": new_id(), "org_id": org, "contract_id": contract["id"], "deal_id": contract.get("deal_id"),
           "component_code": component_code, "amount": amount, "vendor": vendor or "Notaris/BPN",
           "ap_bill_id": bill["id"], "journal_id": je.get("id"), "note": note, "actor": actor, "created_at": ts}
    await db.cost_expenses.insert_one(dict(doc))
    doc.pop("_id", None)
    return {"expense": doc, "ap_bill": bill}
