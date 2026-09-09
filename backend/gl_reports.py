"""Laporan keuangan periodik (P25 — kelengkapan akuntansi).

`gl_engine` menghitung saldo **all-time**. Modul ini melengkapinya dengan laporan
berbasis PERIODE yang dibutuhkan developer properti (paritas ERP kompetitor):

  worksheet()           Neraca Lajur: saldo awal | transaksi | penyesuaian | saldo akhir
                        + kolom Laba/Rugi & Neraca (klasik, siap audit)
  income_statement()    Laba Rugi periodik: pendapatan, HPP (laba kotor), beban operasi,
                        laba bersih + pembanding periode sebelumnya
  balance_sheet()       Neraca per tanggal (as-of) + klasifikasi lancar/tidak lancar
  cash_flow()           Arus Kas metode LANGSUNG dari mutasi kas/bank, diklasifikasi
                        operasi / investasi / pendanaan + rekonsiliasi saldo kas
  project_report()      Laba Rugi per PROYEK (segment) via pelacakan sumber jurnal
  ratios()              Analisa rasio likuiditas, solvabilitas, profitabilitas + interpretasi

Semua angka berasal dari `journal_entries` (tidak ada estimasi/mock). Uang = IDR integer.
"""
from datetime import datetime, timedelta, timezone

from db import db, ORG_ID
from gl_engine import DEBIT_NORMAL

# Klasifikasi neraca (berdasar prefix kode CoA standar SIPRO).
CURRENT_ASSET_PREFIX = ("1-11", "1-12", "1-13", "1-14", "1-15", "1-16")
CURRENT_LIAB_PREFIX = ("2-11", "2-12", "2-13", "2-14", "2-16")
CASH_PREFIX = ("1-11", "1-12")
# Klasifikasi arus kas untuk akun lawan (counterpart) dari mutasi kas.
INVESTING_PREFIX = ("1-18", "1-19", "1-2")
FINANCING_PREFIX = ("2-15", "2-17", "3-")


# ----------------------------- util periode -----------------------------
def today_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def month_start(d: str = None) -> str:
    d = (d or today_str())[:10]
    return d[:7] + "-01"


def _d(date_str: str) -> datetime:
    return datetime.strptime(str(date_str)[:10], "%Y-%m-%d")


def end_exclusive(date_to: str) -> str:
    return (_d(date_to) + timedelta(days=1)).strftime("%Y-%m-%d")


def prev_day(date_from: str) -> str:
    return (_d(date_from) - timedelta(days=1)).strftime("%Y-%m-%d")


def month_range(period: str) -> tuple:
    """'2026-08' -> ('2026-08-01', '2026-08-31')."""
    y, m = int(period[:4]), int(period[5:7])
    ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
    last = (datetime(ny, nm, 1) - timedelta(days=1)).strftime("%Y-%m-%d")
    return f"{period}-01", last


def normalize_period(date_from: str = None, date_to: str = None) -> dict:
    """Default: bulan berjalan (1 s/d hari ini). Tetap 200 untuk sweep tanpa query."""
    dt = (date_to or today_str())[:10]
    df = (date_from or month_start(dt))[:10]
    if df > dt:
        df, dt = dt, df
    days = (_d(dt) - _d(df)).days + 1
    p_to = prev_day(df)
    p_from = (_d(p_to) - timedelta(days=days - 1)).strftime("%Y-%m-%d")
    return {"date_from": df, "date_to": dt, "days": days,
            "prev_from": p_from, "prev_to": p_to, "label": f"{df} s/d {dt}"}


# ----------------------------- agregasi -----------------------------
async def accounts_map(org_id=ORG_ID) -> dict:
    rows = await db.accounts.find({"org_id": org_id}, {"_id": 0}).sort("code", 1).to_list(1000)
    return {a["code"]: a for a in rows}


def _date_query(start: str = None, end: str = None) -> dict:
    if not start and not end:
        return {}
    dq = {}
    if start:
        dq["$gte"] = start
    if end:
        dq["$lt"] = end_exclusive(end)
    return {"date": dq}


async def sum_lines(org_id, *, start=None, end=None, manual=None) -> dict:
    """{code: {debit, credit}} untuk rentang tanggal.

    `manual=True`  -> hanya jurnal PENYESUAIAN (dibuat manual lewat /gl/journals)
    `manual=False` -> hanya jurnal transaksi (posting otomatis subledger + jurnal sistem)
    """
    q = {"org_id": org_id, **_date_query(start, end)}
    if manual is True:
        q["source_type"] = "manual"
    elif manual is False:
        q["source_type"] = {"$ne": "manual"}
    agg = {}
    cur = db.journal_entries.find(q, {"_id": 0, "lines": 1})
    for je in await cur.to_list(200000):
        for ln in je.get("lines", []):
            a = agg.setdefault(ln["account_code"], {"debit": 0, "credit": 0})
            a["debit"] += int(ln.get("debit", 0) or 0)
            a["credit"] += int(ln.get("credit", 0) or 0)
    return agg


def signed(acct_type: str, debit: int, credit: int) -> int:
    return (debit - credit) if acct_type in DEBIT_NORMAL else (credit - debit)


def split_dc(acct_type: str, balance: int) -> tuple:
    """Saldo bertanda -> (kolom debit, kolom kredit) sesuai sisi normal akun."""
    if acct_type in DEBIT_NORMAL:
        return (balance, 0) if balance >= 0 else (0, -balance)
    return (0, balance) if balance >= 0 else (-balance, 0)


def is_current_asset(code: str) -> bool:
    return code.startswith(CURRENT_ASSET_PREFIX)


def is_current_liab(code: str) -> bool:
    return code.startswith(CURRENT_LIAB_PREFIX)


def _row(acct, extra=None) -> dict:
    base = {"code": acct["code"], "name": acct["name"], "type": acct["type"]}
    base.update(extra or {})
    return base


# ----------------------------- Neraca Lajur -----------------------------
async def worksheet(org_id=ORG_ID, date_from=None, date_to=None) -> dict:
    p = normalize_period(date_from, date_to)
    accts = await accounts_map(org_id)
    opening = await sum_lines(org_id, end=prev_day(p["date_from"]))
    trx = await sum_lines(org_id, start=p["date_from"], end=p["date_to"], manual=False)
    adj = await sum_lines(org_id, start=p["date_from"], end=p["date_to"], manual=True)

    rows, tot = [], {k: 0 for k in (
        "open_debit", "open_credit", "trx_debit", "trx_credit", "adj_debit", "adj_credit",
        "end_debit", "end_credit", "pl_debit", "pl_credit", "bs_debit", "bs_credit")}
    for code, acct in accts.items():
        o = opening.get(code) or {"debit": 0, "credit": 0}
        t = trx.get(code) or {"debit": 0, "credit": 0}
        j = adj.get(code) or {"debit": 0, "credit": 0}
        ob = signed(acct["type"], o["debit"], o["credit"])
        eb = ob + signed(acct["type"], t["debit"], t["credit"]) + signed(acct["type"], j["debit"], j["credit"])
        if not (ob or eb or t["debit"] or t["credit"] or j["debit"] or j["credit"]):
            continue
        od, oc = split_dc(acct["type"], ob)
        ed, ec = split_dc(acct["type"], eb)
        pl = acct["type"] in ("revenue", "expense")
        r = _row(acct, {
            "open_debit": od, "open_credit": oc,
            "trx_debit": t["debit"], "trx_credit": t["credit"],
            "adj_debit": j["debit"], "adj_credit": j["credit"],
            "end_debit": ed, "end_credit": ec,
            "pl_debit": ed if pl else 0, "pl_credit": ec if pl else 0,
            "bs_debit": 0 if pl else ed, "bs_credit": 0 if pl else ec,
        })
        for k in tot:
            tot[k] += r[k]
        rows.append(r)

    net_income = tot["pl_credit"] - tot["pl_debit"]
    return {
        "period": p, "rows": rows, "totals": tot, "net_income": net_income,
        "balanced": tot["end_debit"] == tot["end_credit"],
        "pl_balanced": (tot["pl_debit"] + max(net_income, 0)) == (tot["pl_credit"] + max(-net_income, 0)),
    }


# ----------------------------- Laba Rugi -----------------------------
async def _pl_block(org_id, start, end) -> dict:
    accts = await accounts_map(org_id)
    mut = await sum_lines(org_id, start=start, end=end)
    revenue, cogs, opex = [], [], []
    for code, acct in accts.items():
        m = mut.get(code)
        if not m:
            continue
        amt = signed(acct["type"], m["debit"], m["credit"])
        if not amt:
            continue
        if acct["type"] == "revenue":
            revenue.append(_row(acct, {"amount": amt}))
        elif acct["type"] == "expense":
            (cogs if code.startswith("5-") else opex).append(_row(acct, {"amount": amt}))
    tr = sum(r["amount"] for r in revenue)
    tc = sum(r["amount"] for r in cogs)
    to = sum(r["amount"] for r in opex)
    return {"revenue": revenue, "cogs": cogs, "opex": opex,
            "total_revenue": tr, "total_cogs": tc, "total_opex": to,
            "gross_profit": tr - tc, "total_expense": tc + to, "net_income": tr - tc - to}


def _pct(now_v, prev_v):
    if not prev_v:
        return None
    return round((now_v - prev_v) / abs(prev_v) * 100, 1)


async def income_statement(org_id=ORG_ID, date_from=None, date_to=None, compare=True) -> dict:
    p = normalize_period(date_from, date_to)
    cur = await _pl_block(org_id, p["date_from"], p["date_to"])
    out = {"period": p, **cur}
    out["gross_margin_pct"] = round(cur["gross_profit"] / cur["total_revenue"] * 100, 1) if cur["total_revenue"] else 0
    out["net_margin_pct"] = round(cur["net_income"] / cur["total_revenue"] * 100, 1) if cur["total_revenue"] else 0
    if compare:
        prev = await _pl_block(org_id, p["prev_from"], p["prev_to"])
        out["previous"] = {"label": f"{p['prev_from']} s/d {p['prev_to']}", **prev}
        out["growth"] = {
            "revenue_pct": _pct(cur["total_revenue"], prev["total_revenue"]),
            "expense_pct": _pct(cur["total_expense"], prev["total_expense"]),
            "net_income_pct": _pct(cur["net_income"], prev["net_income"]),
        }
    return out


# ----------------------------- Neraca (as-of) -----------------------------
async def balance_sheet(org_id=ORG_ID, as_of=None) -> dict:
    as_of = (as_of or today_str())[:10]
    accts = await accounts_map(org_id)
    bal = await sum_lines(org_id, end=as_of)
    assets, liabilities, equity = [], [], []
    revenue_total = expense_total = 0
    for code, acct in accts.items():
        m = bal.get(code)
        if not m:
            continue
        amt = signed(acct["type"], m["debit"], m["credit"])
        if acct["type"] == "revenue":
            revenue_total += amt
            continue
        if acct["type"] == "expense":
            expense_total += amt
            continue
        if not amt:
            continue
        if acct["type"] == "asset":
            assets.append(_row(acct, {"balance": amt, "current": is_current_asset(code)}))
        elif acct["type"] == "liability":
            liabilities.append(_row(acct, {"balance": amt, "current": is_current_liab(code)}))
        else:
            equity.append(_row(acct, {"balance": amt}))
    ta = sum(r["balance"] for r in assets)
    tl = sum(r["balance"] for r in liabilities)
    teq = sum(r["balance"] for r in equity)
    ni = revenue_total - expense_total
    return {
        "as_of": as_of, "assets": assets, "liabilities": liabilities, "equity": equity,
        "total_assets": ta, "total_liabilities": tl, "total_equity": teq,
        "current_assets": sum(r["balance"] for r in assets if r["current"]),
        "noncurrent_assets": sum(r["balance"] for r in assets if not r["current"]),
        "current_liabilities": sum(r["balance"] for r in liabilities if r["current"]),
        "noncurrent_liabilities": sum(r["balance"] for r in liabilities if not r["current"]),
        "net_income": ni, "total_liab_equity": tl + teq + ni,
        "balanced": ta == (tl + teq + ni),
    }


# ----------------------------- Arus Kas (metode langsung) -----------------------------
def _cash_category(code: str) -> str:
    if code.startswith(INVESTING_PREFIX):
        return "investing"
    if code.startswith(FINANCING_PREFIX):
        return "financing"
    return "operating"


async def cash_flow(org_id=ORG_ID, date_from=None, date_to=None) -> dict:
    p = normalize_period(date_from, date_to)
    accts = await accounts_map(org_id)
    cash_codes = {c for c in accts if c.startswith(CASH_PREFIX)}

    opening_mut = await sum_lines(org_id, end=prev_day(p["date_from"]))
    opening = sum(signed("asset", (opening_mut.get(c) or {}).get("debit", 0),
                         (opening_mut.get(c) or {}).get("credit", 0)) for c in cash_codes)

    q = {"org_id": org_id, "lines.account_code": {"$in": list(cash_codes)},
         **_date_query(p["date_from"], p["date_to"])}
    entries = await db.journal_entries.find(q, {"_id": 0}).sort([("date", 1)]).to_list(100000)

    buckets = {"operating": {}, "investing": {}, "financing": {}}
    net_change = 0
    for je in entries:
        for ln in je.get("lines", []):
            code = ln["account_code"]
            dr, cr = int(ln.get("debit", 0) or 0), int(ln.get("credit", 0) or 0)
            if code in cash_codes:
                net_change += dr - cr
                continue
            amt = cr - dr  # positif = sumber kas masuk
            if not amt:
                continue
            cat = _cash_category(code)
            slot = buckets[cat].setdefault(code, {
                "code": code, "name": (accts.get(code) or {}).get("name", code),
                "inflow": 0, "outflow": 0, "amount": 0})
            slot["amount"] += amt
            slot["inflow" if amt > 0 else "outflow"] += abs(amt)

    sections = {}
    for cat, rows in buckets.items():
        lst = sorted(rows.values(), key=lambda x: x["code"])
        sections[cat] = {"lines": lst, "total": sum(r["amount"] for r in lst)}
    closing = opening + net_change
    return {
        "period": p, "opening_cash": opening, "closing_cash": closing, "net_change": net_change,
        "operating": sections["operating"], "investing": sections["investing"],
        "financing": sections["financing"],
        "reconciled": (sections["operating"]["total"] + sections["investing"]["total"]
                       + sections["financing"]["total"]) == net_change,
        "cash_accounts": sorted(cash_codes),
    }


# ----------------------------- Laporan per proyek -----------------------------
async def _project_resolver(org_id):
    """Peta id-sumber -> project_id (jurnal tidak menyimpan project_id secara langsung)."""
    deals = {d["id"]: d.get("project_id") for d in
             await db.deals.find({"org_id": org_id}, {"_id": 0, "id": 1, "project_id": 1}).to_list(20000)}
    bills = {b["id"]: b.get("project_id") for b in
             await db.ap_invoices.find({"org_id": org_id}, {"_id": 0, "id": 1, "project_id": 1}).to_list(20000)}
    via_deal = {}
    for coll in ("commissions", "revenue_recognitions", "receipts", "tax_records"):
        for r in await db[coll].find({"org_id": org_id}, {"_id": 0, "id": 1, "deal_id": 1}).to_list(50000):
            via_deal[r["id"]] = r.get("deal_id")

    def resolve(source_id):
        if not source_id:
            return None
        if source_id in deals:
            return deals[source_id]
        if source_id in bills:
            return bills[source_id]
        did = via_deal.get(source_id)
        if did:
            return deals.get(did)
        return None
    return resolve


async def project_report(org_id=ORG_ID, date_from=None, date_to=None) -> dict:
    p = normalize_period(date_from, date_to)
    accts = await accounts_map(org_id)
    resolve = await _project_resolver(org_id)
    projects = {pr["id"]: pr for pr in
                await db.projects.find({"org_id": org_id}, {"_id": 0}).to_list(2000)}

    def blank(pid, name, code=None):
        return {"project_id": pid, "project_name": name, "project_code": code,
                "revenue": 0, "cogs": 0, "opex": 0, "capex_wip": 0,
                "gross_profit": 0, "net_income": 0}

    rows = {pid: blank(pid, pr.get("name"), pr.get("code")) for pid, pr in projects.items()}
    rows[None] = blank(None, "Tidak teralokasi ke proyek")

    q = {"org_id": org_id, **_date_query(p["date_from"], p["date_to"])}
    for je in await db.journal_entries.find(q, {"_id": 0}).to_list(200000):
        pid = resolve(je.get("source_id"))
        if pid not in rows:
            pid = None
        tgt = rows[pid]
        for ln in je.get("lines", []):
            code = ln["account_code"]
            acct = accts.get(code) or {"type": "asset"}
            dr, cr = int(ln.get("debit", 0) or 0), int(ln.get("credit", 0) or 0)
            if acct["type"] == "revenue":
                tgt["revenue"] += cr - dr
            elif acct["type"] == "expense":
                (tgt.__setitem__("cogs", tgt["cogs"] + dr - cr) if code.startswith("5-")
                 else tgt.__setitem__("opex", tgt["opex"] + dr - cr))
            elif code.startswith(("1-16", "1-14")):
                tgt["capex_wip"] += dr - cr
    out = []
    for r in rows.values():
        r["gross_profit"] = r["revenue"] - r["cogs"]
        r["net_income"] = r["revenue"] - r["cogs"] - r["opex"]
        r["margin_pct"] = round(r["net_income"] / r["revenue"] * 100, 1) if r["revenue"] else 0
        if any((r["revenue"], r["cogs"], r["opex"], r["capex_wip"])):
            out.append(r)
    out.sort(key=lambda x: (-x["revenue"], x["project_name"] or ""))
    return {"period": p, "rows": out, "totals": {
        "revenue": sum(r["revenue"] for r in out), "cogs": sum(r["cogs"] for r in out),
        "opex": sum(r["opex"] for r in out), "capex_wip": sum(r["capex_wip"] for r in out),
        "net_income": sum(r["net_income"] for r in out)}}


# ----------------------------- Analisa rasio -----------------------------
def _ratio(name, value, unit, good, warn, hint, higher_better=True):
    if value is None:
        status = "na"
    elif (value >= good) if higher_better else (value <= good):
        status = "healthy"
    elif (value >= warn) if higher_better else (value <= warn):
        status = "watch"
    else:
        status = "risk"
    return {"name": name, "value": value, "unit": unit, "status": status,
            "benchmark": f"{'≥' if higher_better else '≤'} {good}", "hint": hint}


def _div(a, b):
    return round(a / b, 2) if b else None


async def ratios(org_id=ORG_ID, date_from=None, date_to=None) -> dict:
    p = normalize_period(date_from, date_to)
    bs = await balance_sheet(org_id, p["date_to"])
    pl = await _pl_block(org_id, p["date_from"], p["date_to"])
    accts = await accounts_map(org_id)
    bal = await sum_lines(org_id, end=p["date_to"])
    cash = sum(signed("asset", (bal.get(c) or {}).get("debit", 0), (bal.get(c) or {}).get("credit", 0))
               for c in accts if c.startswith(CASH_PREFIX))
    inventory = sum(signed("asset", (bal.get(c) or {}).get("debit", 0), (bal.get(c) or {}).get("credit", 0))
                    for c in accts if c.startswith(("1-14", "1-16")))
    ca, cl = bs["current_assets"], bs["current_liabilities"]
    equity_total = bs["total_equity"] + bs["net_income"]

    liquidity = [
        _ratio("Rasio Lancar (Current Ratio)", _div(ca, cl), "x", 1.5, 1.0,
               "Aset lancar terhadap liabilitas jangka pendek."),
        _ratio("Rasio Cepat (Quick Ratio)", _div(ca - inventory, cl), "x", 1.0, 0.7,
               "Tanpa persediaan/WIP — kemampuan bayar cepat."),
        _ratio("Rasio Kas (Cash Ratio)", _div(cash, cl), "x", 0.5, 0.2,
               "Kas & bank terhadap liabilitas jangka pendek."),
    ]
    solvency = [
        _ratio("Debt to Equity (DER)", _div(bs["total_liabilities"], equity_total), "x", 2.0, 3.0,
               "Total liabilitas dibanding ekuitas.", higher_better=False),
        _ratio("Debt to Asset", _div(bs["total_liabilities"], bs["total_assets"]), "x", 0.6, 0.8,
               "Porsi aset yang dibiayai utang.", higher_better=False),
        _ratio("Equity Multiplier", _div(bs["total_assets"], equity_total), "x", 3.0, 4.0,
               "Total aset dibanding ekuitas.", higher_better=False),
    ]
    gm = round(pl["gross_profit"] / pl["total_revenue"] * 100, 1) if pl["total_revenue"] else None
    nm = round(pl["net_income"] / pl["total_revenue"] * 100, 1) if pl["total_revenue"] else None
    roa = round(pl["net_income"] / bs["total_assets"] * 100, 1) if bs["total_assets"] else None
    roe = round(pl["net_income"] / equity_total * 100, 1) if equity_total else None
    profitability = [
        _ratio("Marjin Laba Kotor", gm, "%", 25, 15, "Laba kotor / pendapatan periode."),
        _ratio("Marjin Laba Bersih", nm, "%", 10, 5, "Laba bersih / pendapatan periode."),
        _ratio("ROA (Return on Asset)", roa, "%", 5, 2, "Laba bersih / total aset."),
        _ratio("ROE (Return on Equity)", roe, "%", 10, 5, "Laba bersih / ekuitas."),
    ]
    groups = [
        {"key": "liquidity", "label": "Likuiditas", "items": liquidity},
        {"key": "solvency", "label": "Solvabilitas", "items": solvency},
        {"key": "profitability", "label": "Profitabilitas", "items": profitability},
    ]
    flat = [i for g in groups for i in g["items"]]
    return {
        "period": p, "groups": groups,
        "inputs": {"current_assets": ca, "current_liabilities": cl, "cash": cash,
                   "inventory_wip": inventory, "total_assets": bs["total_assets"],
                   "total_liabilities": bs["total_liabilities"], "equity": equity_total,
                   "revenue": pl["total_revenue"], "net_income": pl["net_income"]},
        "counts": {"healthy": sum(1 for i in flat if i["status"] == "healthy"),
                   "watch": sum(1 for i in flat if i["status"] == "watch"),
                   "risk": sum(1 for i in flat if i["status"] == "risk"),
                   "na": sum(1 for i in flat if i["status"] == "na")},
    }


# ----------------------------- Buku besar berperiode (drill-down) -----------------------------
async def ledger(org_id, account_code, date_from=None, date_to=None) -> dict:
    acct = await db.accounts.find_one({"org_id": org_id, "code": account_code}, {"_id": 0})
    if not acct:
        return {"account": None, "lines": [], "opening": 0, "closing": 0}
    p = normalize_period(date_from, date_to) if (date_from or date_to) else None
    debit_normal = acct["type"] in DEBIT_NORMAL
    opening = 0
    if p:
        om = await sum_lines(org_id, end=prev_day(p["date_from"]))
        o = om.get(account_code) or {"debit": 0, "credit": 0}
        opening = signed(acct["type"], o["debit"], o["credit"])
    q = {"org_id": org_id, "lines.account_code": account_code}
    if p:
        q.update(_date_query(p["date_from"], p["date_to"]))
    entries = await db.journal_entries.find(q, {"_id": 0}).sort([("date", 1), ("created_at", 1)]).to_list(20000)
    running, out = opening, []
    for je in entries:
        for ln in je.get("lines", []):
            if ln["account_code"] != account_code:
                continue
            dr, cr = int(ln.get("debit", 0) or 0), int(ln.get("credit", 0) or 0)
            running += (dr - cr) if debit_normal else (cr - dr)
            out.append({"date": je["date"], "entry_no": je["entry_no"], "memo": je["memo"],
                        "journal_id": je["id"], "source_type": je.get("source_type"),
                        "debit": dr, "credit": cr, "balance": running})
    return {"account": acct, "period": p, "lines": out, "opening": opening, "closing": running,
            "total_debit": sum(x["debit"] for x in out), "total_credit": sum(x["credit"] for x in out)}
