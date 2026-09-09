"""Kas & Bank (Fase 82) — master rekening/kas terpadu, sub-akun GL per rekening, transfer
internal, buku kas/bank, dan posisi kas.

Prinsip:
  * `1-1100 Kas` dan `1-1200 Bank` menjadi AKUN INDUK (header) yang TIDAK boleh diposting.
    Setiap rekening/kas punya sub-akun sendiri (`1-1201 BCA Operasional`, `1-1101 Kas Besar`).
  * Setiap aliran uang menyebut `cash_account_id`; bila kosong, jurnal jatuh ke rekening/kas
    DEFAULT jenis itu (bukan ke akun induk) — supaya saldo per rekening selalu utuh.
  * Saldo awal rekening dijurnal (Dr sub-akun / Cr 3-1950 Saldo Awal) — neraca = saldo rekening.
  * Migrasi startup: baris jurnal lama yang menunjuk akun induk dipindahkan ke rekening default.
"""
import logging

import gl_engine as gl
import sequences as seq
from core_utils import new_id, now_iso
from db import ORG_ID, db

logger = logging.getLogger("sipro.cashbank")

HEADER = {"cash": "1-1100", "bank": "1-1200"}
HEADER_CODES = set(HEADER.values())
KIND_OF_HEADER = {v: k for k, v in HEADER.items()}
OPENING_EQUITY = "3-1950"
TRANSFER_FEE_ACCOUNT = "6-1600"
TRANSFER_KINDS = {
    "transfer": "Transfer antar rekening",
    "setor_tunai": "Setor tunai (kas → bank)",
    "tarik_tunai": "Tarik tunai (bank → kas)",
    "isi_kas_kecil": "Pengisian kas kecil",
}
_DEFAULT_CACHE: dict = {}


def kind_of(acc: dict) -> str:
    return "cash" if (acc or {}).get("kind") == "cash" else "bank"


async def _next_sub_code(org: str, kind: str) -> str:
    head = HEADER[kind]
    used = set(await db.accounts.distinct("code", {"org_id": org, "parent_code": head}))
    base = int(head.split("-")[1])
    for i in range(1, 100):
        code = f"1-{base + i}"
        if code not in used:
            return code
    raise ValueError(f"Sub-akun {head} penuh (maks 99 rekening per jenis).")


async def _ensure_sub_account(org: str, acc: dict) -> str:
    """Pastikan rekening/kas punya sub-akun GL sendiri; kembalikan kodenya."""
    code = acc.get("gl_account_code")
    if code and code not in HEADER_CODES:
        existing = await db.accounts.find_one({"org_id": org, "code": code}, {"_id": 0})
        if existing:
            if existing.get("parent_code") is None and existing.get("type") == "asset":
                await db.accounts.update_one({"id": existing["id"]},
                                             {"$set": {"parent_code": HEADER[kind_of(acc)]}})
            return code
    kind = kind_of(acc)
    code = await _next_sub_code(org, kind)
    name = acc["name"] if kind == "cash" else f"{acc.get('bank_name') or 'Bank'} — {acc['name']}"
    await db.accounts.insert_one({
        "id": new_id(), "org_id": org, "code": code, "name": name[:80], "type": "asset",
        "parent_code": HEADER[kind], "is_active": True, "cash_account_id": acc["id"],
        "created_at": now_iso()})
    await db.bank_accounts.update_one({"id": acc["id"]}, {"$set": {
        "gl_account_code": code, "gl_account_name": name[:80], "updated_at": now_iso()}})
    return code


async def _post_opening(org: str, acc: dict):
    ob = int(acc.get("opening_balance") or 0)
    if ob <= 0 or acc.get("opening_posted"):
        return
    je = await gl.post_journal(
        org, f"Saldo awal {acc['name']}",
        [{"account_code": acc["gl_account_code"], "debit": ob, "credit": 0},
         {"account_code": OPENING_EQUITY, "debit": 0, "credit": ob}],
        date=acc.get("opening_date") or acc.get("created_at"), source_type="cash_opening",
        source_id=acc["id"], source_event=f"cashbank.opening:{acc['id']}",
        posted_by=acc.get("created_by") or "system")
    await db.bank_accounts.update_one({"id": acc["id"]}, {"$set": {
        "opening_posted": True, "opening_journal_id": je["id"]}})


async def _migrate_header_lines(org: str):
    """Baris jurnal lama di akun induk → sub-akun rekening/kas default (idempoten)."""
    q = {"org_id": org, "lines.account_code": {"$in": list(HEADER_CODES)}}
    moved = 0
    async for je in db.journal_entries.find(q, {"_id": 0, "id": 1, "lines": 1}):
        lines = []
        for ln in je["lines"]:
            if ln["account_code"] in HEADER_CODES:
                code = await default_code(org, KIND_OF_HEADER[ln["account_code"]])
                acct = await db.accounts.find_one({"org_id": org, "code": code}, {"_id": 0})
                ln = {**ln, "account_code": code, "account_id": acct["id"],
                      "account_name": acct["name"], "migrated_from": ln["account_code"]}
                moved += 1
            lines.append(ln)
        await db.journal_entries.update_one({"id": je["id"]}, {"$set": {"lines": lines}})
    if moved:
        logger.info("Kas & Bank: %s baris jurnal akun induk dipindah ke rekening default.", moved)
    return moved


BOOTSTRAP = {
    "cash": {"name": "Kas Besar", "bank_name": "Kas", "account_no": "KAS-01",
             "note": "Kas tunai kantor (dibuat otomatis Fase 82)."},
    # Identitas sama dengan rekening demo Fase 47 supaya seed tidak membuat rekening kembar.
    "bank": {"name": "Rekening Operasional", "bank_name": "Bank Mandiri",
             "account_no": "1440012345678", "holder": None, "demo_batch": "fase47",
             "note": "Rekening penerimaan pembeli & pembayaran operasional."},
}


async def _bootstrap_account(org: str, kind: str) -> dict:
    """Rekening/kas pertama jenis `kind` bila belum ada satu pun (self-healing)."""
    ts = now_iso()
    doc = {"id": new_id(), "org_id": org, "kind": kind, **BOOTSTRAP[kind],
           "gl_account_code": None, "opening_balance": 0, "is_active": True,
           "is_default": True, "created_by": "system", "created_at": ts, "updated_at": ts}
    doc.setdefault("holder", None)
    await db.bank_accounts.insert_one(dict(doc))
    doc.pop("_id", None)
    doc["gl_account_code"] = await _ensure_sub_account(org, doc)
    return doc


async def ensure_setup(org: str = ORG_ID) -> dict:
    await gl.ensure_coa(org)
    await db.accounts.update_many({"org_id": org, "code": {"$in": list(HEADER_CODES)}},
                                  {"$set": {"is_header": True}})
    await db.bank_accounts.update_many({"org_id": org, "kind": {"$exists": False}},
                                       {"$set": {"kind": "bank"}})
    for kind in ("cash", "bank"):
        if not await db.bank_accounts.find_one({"org_id": org, "kind": kind}, {"_id": 0, "id": 1}):
            await _bootstrap_account(org, kind)
    accounts = await db.bank_accounts.find({"org_id": org}, {"_id": 0}).to_list(200)
    for acc in accounts:
        if not acc.get("kind"):
            await db.bank_accounts.update_one({"id": acc["id"]}, {"$set": {"kind": "bank"}})
            acc["kind"] = "bank"
        acc["gl_account_code"] = await _ensure_sub_account(org, acc)
    for kind in ("cash", "bank"):
        rows = [a for a in accounts if kind_of(a) == kind]
        if rows and not any(a.get("is_default") for a in rows):
            pick = sorted(rows, key=lambda a: a.get("created_at") or "")[0]
            await db.bank_accounts.update_one({"id": pick["id"]}, {"$set": {"is_default": True}})
    _DEFAULT_CACHE.clear()
    for acc in accounts:
        await _post_opening(org, {**acc, "gl_account_code": acc["gl_account_code"]})
    moved = await _migrate_header_lines(org)
    return {"accounts": len(accounts), "migrated_lines": moved}


async def default_account(org: str, kind: str) -> dict:
    key = (org, kind)
    if key not in _DEFAULT_CACHE:
        acc = await db.bank_accounts.find_one({"org_id": org, "kind": kind, "is_default": True},
                                              {"_id": 0}) \
            or await db.bank_accounts.find_one({"org_id": org, "kind": kind, "is_active": True},
                                               {"_id": 0}, sort=[("created_at", 1)])
        if not acc:
            acc = await _bootstrap_account(org, kind)
        _DEFAULT_CACHE[key] = acc
    return _DEFAULT_CACHE[key]


async def default_code(org: str, kind: str) -> str:
    acc = await default_account(org, kind)
    code = acc.get("gl_account_code")
    if not code or code in HEADER_CODES:
        code = await _ensure_sub_account(org, acc)
        _DEFAULT_CACHE.pop((org, kind), None)
    return code


async def resolve_code(org: str, cash_account_id: str = None, fallback_code: str = "1-1200",
                       strict: bool = True) -> str:
    """Kode sub-akun GL untuk sebuah aliran uang. Tanpa id → rekening default jenis fallback.
    `strict=False` (handler event tertunda): rekening yang sudah dihapus → jatuh ke default."""
    if cash_account_id:
        acc = await db.bank_accounts.find_one({"id": cash_account_id, "org_id": org}, {"_id": 0})
        if not acc:
            if strict:
                raise ValueError("Rekening/kas yang dipilih tidak ditemukan.")
            acc = None
        elif strict and not acc.get("is_active", True):
            raise ValueError(f"Rekening {acc['name']} sudah nonaktif — pilih rekening lain.")
        if acc:
            code = acc.get("gl_account_code")
            return code if code and code not in HEADER_CODES else await _ensure_sub_account(org, acc)
    if fallback_code in HEADER_CODES:
        return await default_code(org, KIND_OF_HEADER[fallback_code])
    return fallback_code


async def account_by_code(org: str, code: str) -> dict:
    return await db.bank_accounts.find_one({"org_id": org, "gl_account_code": code}, {"_id": 0})


# ----------------------------------------------------------------- saldo & buku
async def balances(org: str, date_to: str = None) -> dict:
    """{gl_code: saldo debit-normal} untuk semua sub-akun kas/bank sampai `date_to` (inklusif)."""
    codes = await db.bank_accounts.distinct("gl_account_code", {"org_id": org})
    q = {"org_id": org, "lines.account_code": {"$in": codes}}
    if date_to:
        q["date"] = {"$lt": date_to[:10] + "T99"}
    out = {c: 0 for c in codes}
    async for je in db.journal_entries.find(q, {"_id": 0, "lines": 1}):
        for ln in je["lines"]:
            if ln["account_code"] in out:
                out[ln["account_code"]] += int(ln.get("debit") or 0) - int(ln.get("credit") or 0)
    return out


async def list_accounts(org: str, active_only: bool = False) -> list:
    q = {"org_id": org}
    if active_only:
        q["is_active"] = True
    rows = await db.bank_accounts.find(q, {"_id": 0}).sort([("kind", 1), ("name", 1)]).to_list(200)
    bal = await balances(org)
    for r in rows:
        r["kind"] = kind_of(r)
        r["is_default"] = bool(r.get("is_default"))
        r["is_active"] = r.get("is_active", True)
        r["balance"] = bal.get(r.get("gl_account_code"), 0)
    return rows


async def position(org: str) -> dict:
    rows = await list_accounts(org)
    today = now_iso()[:10]
    month = today[:7]
    codes = [r["gl_account_code"] for r in rows]
    flow = {c: {"in": 0, "out": 0} for c in codes}
    q = {"org_id": org, "lines.account_code": {"$in": codes}, "date": {"$gte": month}}
    async for je in db.journal_entries.find(q, {"_id": 0, "lines": 1}):
        for ln in je["lines"]:
            f = flow.get(ln["account_code"])
            if f is not None:
                f["in"] += int(ln.get("debit") or 0)
                f["out"] += int(ln.get("credit") or 0)
    for r in rows:
        r["month_in"] = flow[r["gl_account_code"]]["in"]
        r["month_out"] = flow[r["gl_account_code"]]["out"]
    cash = [r for r in rows if r["kind"] == "cash" and r["is_active"]]
    bank = [r for r in rows if r["kind"] == "bank" and r["is_active"]]
    pending = await db.cash_transfers.count_documents({"org_id": org, "status": "pending"})
    active = cash + bank
    return {"accounts": rows, "total_cash": sum(r["balance"] for r in cash),
            "total_bank": sum(r["balance"] for r in bank),
            "total": sum(r["balance"] for r in active), "month": month,
            "inactive_balance": sum(r["balance"] for r in rows if not r["is_active"]),
            "month_in": sum(r["month_in"] for r in active),
            "month_out": sum(r["month_out"] for r in active),
            "negative": [r["name"] for r in rows if r["balance"] < 0],
            "pending_transfers": pending}


async def book(org: str, account_id: str, date_from: str, date_to: str) -> dict:
    acc = await db.bank_accounts.find_one({"id": account_id, "org_id": org}, {"_id": 0})
    if not acc:
        raise ValueError("Rekening/kas tidak ditemukan.")
    code = acc["gl_account_code"]
    opening = 0
    async for je in db.journal_entries.find(
            {"org_id": org, "lines.account_code": code, "date": {"$lt": date_from}},
            {"_id": 0, "lines": 1}):
        for ln in je["lines"]:
            if ln["account_code"] == code:
                opening += int(ln.get("debit") or 0) - int(ln.get("credit") or 0)
    q = {"org_id": org, "lines.account_code": code,
         "date": {"$gte": date_from, "$lt": date_to[:10] + "T99"}}
    entries = await db.journal_entries.find(q, {"_id": 0}).to_list(20000)
    entries.sort(key=lambda j: (j["date"][:10], j.get("created_at") or ""))
    running, lines, tin, tout = opening, [], 0, 0
    for je in entries:
        for ln in je["lines"]:
            if ln["account_code"] != code:
                continue
            dr, cr = int(ln.get("debit") or 0), int(ln.get("credit") or 0)
            running += dr - cr
            tin += dr
            tout += cr
            counter = [x["account_name"] for x in je["lines"] if x["account_code"] != code]
            lines.append({"date": je["date"][:10], "entry_no": je["entry_no"],
                          "journal_id": je["id"], "memo": je["memo"],
                          "counter": ", ".join(dict.fromkeys(counter)),
                          "source_type": je.get("source_type"), "in": dr, "out": cr,
                          "balance": running})
    return {"account": {**acc, "kind": kind_of(acc)}, "date_from": date_from, "date_to": date_to,
            "opening": opening, "total_in": tin, "total_out": tout, "closing": running,
            "lines": lines}


def book_csv(data: dict) -> str:
    rows = ["Tanggal;No Jurnal;Keterangan;Lawan Akun;Masuk;Keluar;Saldo",
            f"{data['date_from']};;Saldo awal;;;;{data['opening']}"]
    for ln in data["lines"]:
        memo = (ln["memo"] or "").replace(";", ",")
        rows.append(f"{ln['date']};{ln['entry_no']};{memo};{ln['counter']};{ln['in']};{ln['out']};{ln['balance']}")
    rows.append(f"{data['date_to']};;Saldo akhir;;{data['total_in']};{data['total_out']};{data['closing']}")
    return "\n".join(rows)


# ----------------------------------------------------------------- master
async def create_account(org: str, payload: dict, actor: str) -> dict:
    kind = payload.get("kind") or "bank"
    if await db.bank_accounts.find_one({"org_id": org, "account_no": payload["account_no"]},
                                       {"_id": 0, "id": 1}):
        raise ValueError("Nomor rekening / kode kas ini sudah terdaftar.")
    ts = now_iso()
    doc = {"id": new_id(), "org_id": org, "kind": kind, "name": payload["name"],
           "bank_name": payload.get("bank_name") or ("Kas" if kind == "cash" else "Bank"),
           "account_no": payload["account_no"], "holder": payload.get("holder"),
           "gl_account_code": None, "opening_balance": int(payload.get("opening_balance") or 0),
           "opening_date": payload.get("opening_date"), "note": payload.get("note"),
           "imprest_limit": int(payload["imprest_limit"]) if kind == "cash" and payload.get("imprest_limit") else None,
           "is_active": True, "is_default": bool(payload.get("is_default")),
           "created_by": actor, "created_at": ts, "updated_at": ts}
    await db.bank_accounts.insert_one(dict(doc))
    doc.pop("_id", None)
    doc["gl_account_code"] = await _ensure_sub_account(org, doc)
    if doc["is_default"]:
        await set_default(org, doc["id"])
    _DEFAULT_CACHE.clear()
    await _post_opening(org, doc)
    return await db.bank_accounts.find_one({"id": doc["id"]}, {"_id": 0})


async def update_account(org: str, account_id: str, payload: dict, actor: str) -> dict:
    acc = await db.bank_accounts.find_one({"id": account_id, "org_id": org}, {"_id": 0})
    if not acc:
        raise ValueError("Rekening/kas tidak ditemukan.")
    allowed = {k: payload[k] for k in ("name", "bank_name", "holder", "note", "is_active")
               if k in payload and payload[k] is not None}
    if "imprest_limit" in payload and kind_of(acc) == "cash":
        allowed["imprest_limit"] = int(payload["imprest_limit"] or 0) or None
    if payload.get("account_no") and payload["account_no"] != acc["account_no"]:
        if await db.bank_accounts.find_one({"org_id": org, "account_no": payload["account_no"],
                                            "id": {"$ne": account_id}}, {"_id": 0, "id": 1}):
            raise ValueError("Nomor rekening / kode kas ini sudah dipakai rekening lain.")
        allowed["account_no"] = payload["account_no"]
    if not acc.get("opening_posted") and "opening_balance" in payload:
        allowed["opening_balance"] = int(payload.get("opening_balance") or 0)
        allowed["opening_date"] = payload.get("opening_date") or acc.get("opening_date")
    if allowed.get("is_active") is False and acc.get("is_default"):
        raise ValueError("Rekening default tidak boleh dinonaktifkan — pindahkan default dulu.")
    allowed.update({"updated_at": now_iso(), "updated_by": actor})
    await db.bank_accounts.update_one({"id": account_id}, {"$set": allowed})
    fresh = await db.bank_accounts.find_one({"id": account_id}, {"_id": 0})
    if "name" in allowed or "bank_name" in allowed:
        nm = fresh["name"] if kind_of(fresh) == "cash" else f"{fresh.get('bank_name')} — {fresh['name']}"
        await db.accounts.update_one({"org_id": org, "code": fresh["gl_account_code"]},
                                     {"$set": {"name": nm[:80]}})
        await db.bank_accounts.update_one({"id": account_id}, {"$set": {"gl_account_name": nm[:80]}})
    _DEFAULT_CACHE.clear()
    await _post_opening(org, fresh)
    return await db.bank_accounts.find_one({"id": account_id}, {"_id": 0})


async def set_default(org: str, account_id: str) -> dict:
    acc = await db.bank_accounts.find_one({"id": account_id, "org_id": org}, {"_id": 0})
    if not acc:
        raise ValueError("Rekening/kas tidak ditemukan.")
    if not acc.get("is_active", True):
        raise ValueError("Rekening nonaktif tidak boleh menjadi default.")
    kind = kind_of(acc)
    await db.bank_accounts.update_many({"org_id": org, "kind": kind}, {"$set": {"is_default": False}})
    await db.bank_accounts.update_one({"id": account_id}, {"$set": {"is_default": True}})
    _DEFAULT_CACHE.clear()
    return await db.bank_accounts.find_one({"id": account_id}, {"_id": 0})


# ----------------------------------------------------------------- transfer internal
async def create_transfer(org: str, payload: dict, actor: str) -> dict:
    kind = payload.get("kind") or "transfer"
    if kind not in TRANSFER_KINDS:
        raise ValueError("Jenis transaksi internal tidak dikenal.")
    src = await db.bank_accounts.find_one({"id": payload["from_account_id"], "org_id": org}, {"_id": 0})
    dst = await db.bank_accounts.find_one({"id": payload["to_account_id"], "org_id": org}, {"_id": 0})
    if not src or not dst:
        raise ValueError("Rekening asal/tujuan tidak ditemukan.")
    if src["id"] == dst["id"]:
        raise ValueError("Rekening asal dan tujuan tidak boleh sama.")
    if not src.get("is_active", True) or not dst.get("is_active", True):
        raise ValueError("Rekening asal/tujuan nonaktif.")
    amount = int(payload.get("amount") or 0)
    fee = int(payload.get("fee") or 0)
    if amount <= 0:
        raise ValueError("Nominal transfer harus lebih dari 0.")
    if fee < 0:
        raise ValueError("Biaya transfer tidak boleh negatif.")
    rule = {"setor_tunai": ("cash", "bank"), "tarik_tunai": ("bank", "cash"),
            "isi_kas_kecil": (None, "cash")}.get(kind)
    if rule:
        if rule[0] and kind_of(src) != rule[0]:
            raise ValueError(f"{TRANSFER_KINDS[kind]}: rekening asal harus jenis {rule[0]}.")
        if rule[1] and kind_of(dst) != rule[1]:
            raise ValueError(f"{TRANSFER_KINDS[kind]}: tujuan harus jenis {rule[1]}.")
    bal = await balances(org)
    if bal.get(src["gl_account_code"], 0) < amount + fee:
        raise ValueError(f"Saldo {src['name']} (Rp {bal.get(src['gl_account_code'], 0):,}) tidak "
                         f"cukup untuk Rp {amount + fee:,}.")
    ts = now_iso()
    doc = {"id": new_id(), "org_id": org,
           "no": await seq.next_number("cash_transfer", org, prefix="TRF", width=4, year=ts[:4]),
           "kind": kind, "kind_label": TRANSFER_KINDS[kind],
           "from_account_id": src["id"], "from_name": src["name"], "from_code": src["gl_account_code"],
           "to_account_id": dst["id"], "to_name": dst["name"], "to_code": dst["gl_account_code"],
           "amount": amount, "fee": fee, "date": (payload.get("date") or ts[:10])[:10],
           "reference": payload.get("reference"), "note": payload.get("note"),
           "status": "pending", "created_by": actor, "created_at": ts, "updated_at": ts,
           "approved_by": None, "approved_at": None, "journal_id": None, "journal_no": None}
    await db.cash_transfers.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


async def approve_transfer(org: str, transfer_id: str, actor: str) -> dict:
    tr = await db.cash_transfers.find_one({"id": transfer_id, "org_id": org}, {"_id": 0})
    if not tr:
        raise ValueError("Transaksi internal tidak ditemukan.")
    if tr["status"] != "pending":
        raise ValueError(f"Transaksi sudah {tr['status']} — tidak bisa disetujui lagi.")
    if tr["created_by"] == actor:
        raise ValueError("Pembuat transaksi tidak boleh menyetujui transaksinya sendiri (SoD).")
    lines = [{"account_code": tr["to_code"], "debit": tr["amount"], "credit": 0,
              "memo": f"Masuk ke {tr['to_name']}"},
             {"account_code": tr["from_code"], "debit": 0, "credit": tr["amount"] + tr["fee"],
              "memo": f"Keluar dari {tr['from_name']}"}]
    if tr["fee"]:
        lines.append({"account_code": TRANSFER_FEE_ACCOUNT, "debit": tr["fee"], "credit": 0,
                      "memo": "Biaya transfer/admin"})
    je = await gl.post_journal(org, f"{tr['kind_label']} {tr['no']} — {tr['from_name']} → {tr['to_name']}",
                               lines, date=tr["date"], source_type="cash_transfer", source_id=tr["id"],
                               source_event=f"cashbank.transfer:{tr['id']}", posted_by=actor, auto=False)
    ts = now_iso()
    await db.cash_transfers.update_one({"id": transfer_id}, {"$set": {
        "status": "posted", "approved_by": actor, "approved_at": ts, "updated_at": ts,
        "journal_id": je["id"], "journal_no": je["entry_no"]}})
    return await db.cash_transfers.find_one({"id": transfer_id}, {"_id": 0})


async def reject_transfer(org: str, transfer_id: str, actor: str, reason: str) -> dict:
    tr = await db.cash_transfers.find_one({"id": transfer_id, "org_id": org}, {"_id": 0})
    if not tr:
        raise ValueError("Transaksi internal tidak ditemukan.")
    if tr["status"] != "pending":
        raise ValueError(f"Transaksi sudah {tr['status']}.")
    ts = now_iso()
    await db.cash_transfers.update_one({"id": transfer_id}, {"$set": {
        "status": "rejected", "rejected_by": actor, "rejected_at": ts,
        "reject_reason": reason, "updated_at": ts}})
    return await db.cash_transfers.find_one({"id": transfer_id}, {"_id": 0})
