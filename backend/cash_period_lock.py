"""Tutup periode Kas & Bank PER REKENING (Fase 85).

Setelah rekonsiliasi sebuah rekening dinyatakan seimbang/dijelaskan (Fase 83) — atau kas tunai
di-opname dan hitungan fisik = saldo buku — periode itu DIKUNCI: tidak ada jurnal baru yang boleh
mendarat di sub-akun rekening tersebut dengan tanggal ≤ akhir periode terkunci, sehingga saldo awal
periode berikutnya tidak berubah diam-diam.

Perilaku mengikuti `gl_periods` (P25): jurnal MANUAL ke periode terkunci ditolak; posting OTOMATIS
subledger digeser ke hari pertama sesudah kunci dan memonya diberi catatan (transaksi nyata tidak
pernah hilang). Kunci bisa dibuka kembali (`bank:approve`, alasan wajib) — jejaknya tersimpan.
"""
import calendar
from datetime import datetime, timezone

import bank_recon
import cash_bank as cb
from core_utils import new_id, now_iso
from db import ORG_ID, db

ELIGIBLE_RECON = ("seimbang", "dijelaskan")


def period_end(period: str) -> str:
    y, m = int(period[:4]), int(period[5:7])
    return f"{y:04d}-{m:02d}-{calendar.monthrange(y, m)[1]:02d}"


def next_month_start(period: str) -> str:
    y, m = int(period[:4]), int(period[5:7])
    return f"{y + 1:04d}-01-01" if m == 12 else f"{y:04d}-{m + 1:02d}-01"


async def locked_through(org: str) -> dict:
    """{gl_account_code: periode terkunci terbesar} untuk rekening yang punya kunci aktif."""
    out = {}
    async for r in db.cash_period_locks.find({"org_id": org, "status": "locked"},
                                             {"_id": 0, "gl_account_code": 1, "period": 1}):
        c = r["gl_account_code"]
        if r["period"] > out.get(c, ""):
            out[c] = r["period"]
    return out


async def resolve_date(org: str, date_str: str, codes: list, auto: bool):
    """(tanggal_final, keterangan_pergeseran|None). ValueError untuk jurnal manual ke periode terkunci."""
    locks = await locked_through(org)
    hit = [(c, locks[c]) for c in codes if c in locks and str(date_str)[:7] <= locks[c]]
    if not hit:
        return date_str, None
    code, period = max(hit, key=lambda x: x[1])
    acc = await db.bank_accounts.find_one({"org_id": org, "gl_account_code": code}, {"_id": 0, "name": 1})
    name = (acc or {}).get("name") or code
    if not auto:
        raise ValueError(f"Periode {str(date_str)[:7]} rekening/kas {name} sudah dikunci (rekonsiliasi "
                         f"seimbang s.d. {period}) — jurnal manual ditolak. Buka kunci dulu atau pakai "
                         "tanggal sesudah periode terkunci.")
    target = next_month_start(period)
    now = datetime.now(timezone.utc)
    final = now.isoformat() if target <= now.strftime("%Y-%m-%d") else f"{target}T00:00:00+00:00"
    return final, f"kunci kas {name} s.d. {period}"


async def preview(org: str, account_id: str, period: str, counted_balance: int = None) -> dict:
    acc = await db.bank_accounts.find_one({"id": account_id, "org_id": org}, {"_id": 0})
    if not acc:
        raise ValueError("Rekening/kas tidak ditemukan.")
    if len(period) != 7 or period[4] != "-":
        raise ValueError("Periode harus berformat YYYY-MM.")
    today = now_iso()[:10]
    end = period_end(period)
    code = acc["gl_account_code"]
    book = (await cb.balances(org, date_to=end)).get(code, 0)
    reasons, kind = [], cb.kind_of(acc)
    if period >= today[:7]:
        reasons.append("Periode belum berakhir — hanya bulan yang sudah lewat yang bisa dikunci.")
    existing = await db.cash_period_locks.find_one(
        {"org_id": org, "account_id": account_id, "status": "locked", "period": {"$gte": period}},
        {"_id": 0, "period": 1})
    if existing:
        reasons.append(f"Rekening ini sudah terkunci s.d. {existing['period']}.")
    recon = None
    if kind == "bank":
        r = await bank_recon.reconcile(org, account_id, as_of=end)
        recon = {"status": r["status"], "as_of": r["as_of"], "statement_balance": r["statement_balance"],
                 "book_balance_at_recon": r["book_balance"], "residual": r["residual"],
                 "unmatched_count": r["unmatched_count"], "unexplained_count": r["unexplained_count"]}
        if r["status"] not in ELIGIBLE_RECON:
            reasons.append({"tanpa_data": "Belum ada mutasi rekening berkolom saldo untuk periode ini.",
                            "belum_dijelaskan": "Rekonsiliasi belum seimbang: masih ada mutasi belum cocok, "
                                                "jurnal tanpa alasan, atau residu."}.get(r["status"], r["status"]))
        elif r["as_of"][:7] != period:
            reasons.append(f"Mutasi rekening terakhir yang diimpor bertanggal {r['as_of']} — belum "
                           f"mencakup {period}.")
    else:
        if counted_balance is None:
            reasons.append("Kas tunai: isi hasil opname (hitungan fisik) per akhir periode.")
        elif int(counted_balance) != book:
            reasons.append(f"Hasil opname Rp {int(counted_balance):,} ≠ saldo buku Rp {book:,} — selisih "
                           f"Rp {int(counted_balance) - book:,} harus dijurnal dulu.")
    return {"account": {"id": acc["id"], "name": acc["name"], "kind": kind, "gl_account_code": code},
            "period": period, "period_end": end, "closing_balance": book, "recon": recon,
            "counted_balance": counted_balance, "eligible": not reasons, "reasons": reasons}


async def lock(org: str, payload: dict, actor: str) -> dict:
    pv = await preview(org, payload["account_id"], payload["period"], payload.get("counted_balance"))
    if not pv["eligible"]:
        raise ValueError(" ".join(pv["reasons"]))
    ts = now_iso()
    doc = {"id": new_id(), "org_id": org, "account_id": pv["account"]["id"], "account_name": pv["account"]["name"],
           "kind": pv["account"]["kind"], "gl_account_code": pv["account"]["gl_account_code"],
           "period": pv["period"], "period_end": pv["period_end"], "status": "locked",
           "closing_balance": pv["closing_balance"],
           "statement_balance": (pv["recon"] or {}).get("statement_balance"),
           "recon_status": (pv["recon"] or {}).get("status"), "counted_balance": pv["counted_balance"],
           "note": payload.get("note"), "locked_by": actor, "locked_at": ts,
           "unlocked_by": None, "unlocked_at": None, "unlock_reason": None, "created_at": ts}
    await db.cash_period_locks.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


async def unlock(org: str, lock_id: str, actor: str, reason: str) -> dict:
    doc = await db.cash_period_locks.find_one({"id": lock_id, "org_id": org}, {"_id": 0})
    if not doc:
        raise ValueError("Kunci periode tidak ditemukan.")
    if doc["status"] != "locked":
        raise ValueError("Kunci ini sudah dibuka.")
    await db.cash_period_locks.update_one({"id": lock_id}, {"$set": {
        "status": "unlocked", "unlocked_by": actor, "unlocked_at": now_iso(), "unlock_reason": reason}})
    return await db.cash_period_locks.find_one({"id": lock_id}, {"_id": 0})


async def overview(org: str) -> dict:
    accounts = await cb.list_accounts(org, active_only=True)
    locks = await db.cash_period_locks.find({"org_id": org}, {"_id": 0}).sort([("period", -1), ("locked_at", -1)]).to_list(2000)
    active = {}
    for lk in locks:
        if lk["status"] == "locked" and lk["period"] > active.get(lk["account_id"], {}).get("period", ""):
            active[lk["account_id"]] = lk
    rows = [{"account_id": a["id"], "name": a["name"], "kind": a["kind"], "gl_account_code": a["gl_account_code"],
             "balance": a["balance"], "locked_through": active.get(a["id"], {}).get("period"),
             "closing_balance": active.get(a["id"], {}).get("closing_balance"),
             "locked_at": active.get(a["id"], {}).get("locked_at"), "lock_id": active.get(a["id"], {}).get("id")}
            for a in accounts]
    return {"accounts": rows, "history": locks[:200]}
