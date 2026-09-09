"""Giro / cek mundur (PDC) — Fase 86.

Giro yang diterima dari pembeli BUKAN uang sampai bank mengkliringnya. Karena AR SIPRO hanya
berkurang lewat `finance_engine.apply_receipt` (alokasi termin, titipan, kwitansi bernomor), giro
dicatat sebagai instrumen tersendiri dengan jurnal memorandum berpasangan:
    Diterima  : Dr 1-1350 Giro/Cek Belum Cair   / Cr 2-1480 Giro Diterima Belum Cair (kontra)
    Kliring   : balik pasangan itu, lalu uang benar-benar masuk → `apply_receipt(method="cheque")`
                ke rekening bank pilihan (kwitansi KWT terbit, AR berkurang, kelebihan → titipan);
                giro tanpa deal → Dr bank / Cr 2-1450 Titipan Pelanggan.
    Tolakan / batal : balik pasangan; AR tidak pernah tersentuh (memang belum dibayar).
Neraca jujur: giro di tangan terlihat sebagai aset dengan kewajiban kontra sebesar yang sama —
tidak menggelembungkan kas maupun mengurangi piutang sebelum uangnya ada.
"""
import gl_engine as gl
import sequences as seq
from core_utils import new_id, now_iso
from db import ORG_ID, db
from finance_engine import apply_receipt, notify_finance

PDC_ASSET = "1-1350"
PDC_CONTRA = "2-1480"
DEPOSIT_LIABILITY = "2-1450"
KINDS = {"cek": "Cek", "bg": "Bilyet Giro"}


def _rp(v) -> str:
    return f"Rp {int(v):,}".replace(",", ".")


async def _get(org: str, pdc_id: str) -> dict:
    doc = await db.pdc_instruments.find_one({"id": pdc_id, "org_id": org}, {"_id": 0})
    if not doc:
        raise ValueError("Giro/cek tidak ditemukan.")
    return doc


async def receive(org: str, payload: dict, actor: str) -> dict:
    kind = payload.get("kind") or "bg"
    if kind not in KINDS:
        raise ValueError("Jenis warkat harus 'cek' atau 'bg'.")
    amount = int(payload.get("amount") or 0)
    if amount <= 0:
        raise ValueError("Nominal giro harus lebih dari 0.")
    ts = now_iso()
    due = (payload.get("due_date") or "")[:10]
    if len(due) != 10:
        raise ValueError("Tanggal jatuh tempo giro wajib diisi.")
    received = (payload.get("received_date") or ts[:10])[:10]
    if received > ts[:10]:
        raise ValueError("Tanggal terima tidak boleh di masa depan.")
    deal, inv = None, None
    if payload.get("deal_id"):
        deal = await db.deals.find_one({"id": payload["deal_id"], "org_id": org}, {"_id": 0})
        if not deal:
            raise ValueError("Deal tidak ditemukan.")
        inv = await db.ar_invoices.find_one({"org_id": org, "deal_id": deal["id"]},
                                            {"_id": 0, "outstanding": 1, "unit_code": 1, "lead_name": 1, "customer_name": 1})
        if not inv:
            raise ValueError("Deal ini belum punya jadwal AR — giro tidak bisa dialokasikan.")
    if await db.pdc_instruments.find_one({"org_id": org, "bank_name": payload.get("bank_name"),
                                          "instrument_no": payload["instrument_no"], "status": {"$ne": "cancelled"}},
                                         {"_id": 0, "id": 1}):
        raise ValueError("Nomor warkat ini dari bank yang sama sudah tercatat.")
    pid = new_id()
    no = await seq.next_number("pdc", org, prefix="GIRO", width=4, year=ts[:4])
    issuer = (payload.get("issuer_name") or (inv or {}).get("lead_name") or (inv or {}).get("customer_name")
              or (deal or {}).get("lead_name") or (deal or {}).get("customer_name") or "-").strip()
    je = await gl.post_journal(
        org, f"{KINDS[kind]} {no} diterima dari {issuer} — jatuh tempo {due}",
        [{"account_code": PDC_ASSET, "debit": amount, "credit": 0, "memo": f"{KINDS[kind]} no. {payload['instrument_no']}"},
         {"account_code": PDC_CONTRA, "debit": 0, "credit": amount, "memo": "Belum cair — kontra"}],
        date=received, source_type="pdc", source_id=pid, source_event=f"pdc.receive:{pid}", posted_by=actor, auto=False)
    doc = {"id": pid, "org_id": org, "no": no, "kind": kind, "kind_label": KINDS[kind], "status": "received",
           "bank_name": payload.get("bank_name"), "instrument_no": payload["instrument_no"],
           "issuer_name": issuer, "amount": amount, "due_date": due, "received_date": received,
           "deal_id": (deal or {}).get("id"), "unit_code": (inv or deal or {}).get("unit_code"),
           "ar_outstanding_at_receipt": (inv or {}).get("outstanding"), "note": payload.get("note"),
           "journal_id": je["id"], "journal_no": je["entry_no"], "cash_account_id": None, "cash_account_name": None,
           "receipt_id": None, "receipt_no": None, "clear_journal_no": None, "cleared_date": None,
           "bounce_reason": None, "received_by": actor, "created_at": ts, "updated_at": ts, "history": [
               {"at": ts, "by": actor, "action": "received", "journal_no": je["entry_no"]}]}
    await db.pdc_instruments.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


async def _reverse_pair(org: str, doc: dict, event: str, memo: str, actor: str, date: str = None) -> dict:
    return await gl.post_journal(
        org, memo,
        [{"account_code": PDC_CONTRA, "debit": doc["amount"], "credit": 0, "memo": "Kontra dibalik"},
         {"account_code": PDC_ASSET, "debit": 0, "credit": doc["amount"], "memo": f"Giro {doc['no']} keluar dari tangan"}],
        date=date, source_type="pdc", source_id=doc["id"], source_event=f"pdc.{event}:{doc['id']}", posted_by=actor, auto=False)


async def clear(org: str, pdc_id: str, payload: dict, actor: str) -> dict:
    doc = await _get(org, pdc_id)
    if doc["status"] != "received":
        raise ValueError(f"Giro {doc['no']} sudah {doc['status']} — tidak bisa dikliring.")
    import cash_bank as cb
    acc = await db.bank_accounts.find_one({"id": payload.get("cash_account_id"), "org_id": org}, {"_id": 0})
    if not acc or cb.kind_of(acc) != "bank" or not acc.get("is_active", True):
        raise ValueError("Pilih rekening BANK aktif tempat giro dicairkan.")
    ts = now_iso()
    cleared = (payload.get("cleared_date") or ts[:10])[:10]
    if cleared > ts[:10]:
        raise ValueError("Tanggal kliring tidak boleh di masa depan.")
    if cleared < doc["received_date"]:
        raise ValueError("Tanggal kliring tidak boleh sebelum tanggal terima.")
    rev = await _reverse_pair(org, doc, "clear.reverse", f"Giro {doc['no']} kliring — memorandum dibalik", actor, cleared)
    receipt_id = receipt_no = None
    if doc.get("deal_id"):
        rc = (await apply_receipt(doc["deal_id"], doc["amount"], "cheque",
                                  f"Kliring {doc['kind_label']} {doc['no']} no. {doc['instrument_no']} ({doc['bank_name']})",
                                  actor, org_id=org, allow_overpay=True, cash_account_id=acc["id"]))["receipt"]
        receipt_id, receipt_no = rc.get("id"), rc.get("receipt_no")
        clear_no = receipt_no
    else:
        je = await gl.post_journal(
            org, f"Giro {doc['no']} cair dari {doc['issuer_name']} → {acc['name']} (titipan, tanpa deal)",
            [{"account_code": acc["gl_account_code"], "debit": doc["amount"], "credit": 0},
             {"account_code": DEPOSIT_LIABILITY, "debit": 0, "credit": doc["amount"], "memo": "Titipan pelanggan"}],
            date=cleared, source_type="pdc", source_id=pdc_id, source_event=f"pdc.clear.cash:{pdc_id}",
            posted_by=actor, auto=False)
        clear_no = je["entry_no"]
    await db.pdc_instruments.update_one({"id": pdc_id}, {"$set": {
        "status": "cleared", "cleared_date": cleared, "cash_account_id": acc["id"], "cash_account_name": acc["name"],
        "receipt_id": receipt_id, "receipt_no": receipt_no, "clear_journal_no": clear_no,
        "reverse_journal_no": rev["entry_no"], "cleared_by": actor, "updated_at": ts},
        "$push": {"history": {"at": ts, "by": actor, "action": "cleared", "journal_no": clear_no,
                              "cash_account": acc["name"]}}})
    return await _get(org, pdc_id)


async def bounce(org: str, pdc_id: str, reason: str, actor: str) -> dict:
    doc = await _get(org, pdc_id)
    if doc["status"] != "received":
        raise ValueError(f"Giro {doc['no']} sudah {doc['status']}.")
    ts = now_iso()
    rev = await _reverse_pair(org, doc, "bounce", f"Giro {doc['no']} DITOLAK bank — {reason}", actor)
    await db.pdc_instruments.update_one({"id": pdc_id}, {"$set": {
        "status": "bounced", "bounce_reason": reason, "bounced_by": actor, "bounced_at": ts,
        "reverse_journal_no": rev["entry_no"], "updated_at": ts},
        "$push": {"history": {"at": ts, "by": actor, "action": "bounced", "journal_no": rev["entry_no"], "reason": reason}}})
    await notify_finance(org, f"Giro {doc['no']} ditolak bank",
                         f"{doc['kind_label']} {doc['instrument_no']} ({doc['bank_name']}) dari {doc['issuer_name']} "
                         f"senilai {_rp(doc['amount'])} ditolak: {reason}. Tagihan tetap terbuka — hubungi pembeli.",
                         "finance", "pdc", pdc_id)
    return await _get(org, pdc_id)


async def cancel(org: str, pdc_id: str, reason: str, actor: str) -> dict:
    doc = await _get(org, pdc_id)
    if doc["status"] != "received":
        raise ValueError(f"Giro {doc['no']} sudah {doc['status']}.")
    ts = now_iso()
    rev = await _reverse_pair(org, doc, "cancel", f"Giro {doc['no']} dibatalkan/dikembalikan — {reason}", actor)
    await db.pdc_instruments.update_one({"id": pdc_id}, {"$set": {
        "status": "cancelled", "cancel_reason": reason, "cancelled_by": actor, "cancelled_at": ts,
        "reverse_journal_no": rev["entry_no"], "updated_at": ts},
        "$push": {"history": {"at": ts, "by": actor, "action": "cancelled", "journal_no": rev["entry_no"], "reason": reason}}})
    return await _get(org, pdc_id)


async def listing(org: str, status: str = None, deal_id: str = None, limit: int = 200) -> dict:
    q = {"org_id": org}
    if status:
        q["status"] = status
    if deal_id:
        q["deal_id"] = deal_id
    rows = await db.pdc_instruments.find(q, {"_id": 0}).sort([("due_date", 1), ("created_at", -1)]).to_list(limit)
    today = now_iso()[:10]
    in_hand = [r async for r in db.pdc_instruments.find({"org_id": org, "status": "received"}, {"_id": 0, "amount": 1, "due_date": 1})]
    from datetime import date as _d, timedelta
    soon = (_d.fromisoformat(today) + timedelta(days=7)).isoformat()
    for r in rows:
        r["overdue"] = r["status"] == "received" and r["due_date"] < today
        r["due_soon"] = r["status"] == "received" and today <= r["due_date"] <= soon
    return {"rows": rows, "total": len(rows), "summary": {
        "in_hand_count": len(in_hand), "in_hand_amount": sum(int(r["amount"]) for r in in_hand),
        "due_soon_amount": sum(int(r["amount"]) for r in in_hand if today <= r["due_date"] <= soon),
        "overdue_count": sum(1 for r in in_hand if r["due_date"] < today),
        "bounced_count": await db.pdc_instruments.count_documents({"org_id": org, "status": "bounced"})},
        "kinds": [{"value": k, "label": v} for k, v in KINDS.items()]}
