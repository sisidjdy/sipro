"""BUKTI TRANSFER DARI PELANGGAN (Fase 47B) — diakui pelanggan, dibuktikan finance.

Cacat yang ditutup: Portal Pelanggan seluruhnya BACA-SAJA. Pembeli yang sudah transfer
tidak punya jalan resmi memberi bukti, sehingga bukti berkeliaran di WhatsApp dan status
pembayaran menjadi tafsir masing-masing pihak. Yang lebih berbahaya: tidak ada perbedaan
antara "pelanggan mengaku sudah bayar" dan "uangnya benar-benar diterima".

Aturan modul ini:

  1. **Bukti = KLAIM, bukan pelunasan.** `create_from_portal` TIDAK menyentuh AR sama sekali;
     tagihan hanya berubah setelah finance menekan verifikasi (yang memanggil jalur resmi
     `finance_engine.apply_receipt`). Uji negatif untuk ini wajib ada di gate.
  2. **Berkas kembar ditolak sopan.** Bukti dicocokkan lewat `files.sha256`, jadi foto yang
     sama tidak bisa dipakai dua kali untuk dua klaim.
  3. **Penolakan harus beralasan** — dan alasannya DIBACA PELANGGAN di portal (bukan hanya
     catatan internal), sehingga pembeli tahu apa yang harus diperbaiki.
  4. **Setiap perubahan status melahirkan notifikasi + aktivitas** pada deal, sehingga
     riwayatnya bisa diaudit.
"""
import logging

import finance_engine as fin
from core_utils import new_id, now_iso
from db import ORG_ID, db
from engine import add_activity, emit
from reference_p47 import INTAKE_LABEL

logger = logging.getLogger("sipro.payment.intake")
MIN_REJECT_REASON = 10


def _label(state: str) -> str:
    return INTAKE_LABEL.get(state, state)


async def _files(org: str, file_ids: list) -> list:
    rows = await db.files.find({"org_id": org, "id": {"$in": list(file_ids or [])}},
                              {"_id": 0, "id": 1, "filename": 1, "content_type": 1,
                               "sha256": 1, "size": 1}).to_list(20)
    return rows


async def create_from_portal(org: str, *, customer: dict, deal: dict, amount: int,
                             transfer_date: str, file_ids: list, bank_name: str = None,
                             note: str = None, actor: str = None) -> dict:
    """Catat klaim setoran dari portal. TIDAK mengubah tagihan."""
    files = await _files(org, file_ids)
    if not files:
        raise ValueError("Bukti transfer (foto/PDF) wajib dilampirkan.")
    shas = [f.get("sha256") for f in files if f.get("sha256")]
    if shas:
        dup = await db.payment_intakes.find_one(
            {"org_id": org, "file_shas": {"$in": shas}, "state": {"$ne": "rejected"}},
            {"_id": 0, "id": 1, "created_at": 1})
        if dup:
            raise ValueError("Bukti transfer ini sudah pernah dikirim pada "
                             f"{str(dup.get('created_at'))[:10]} — tidak perlu dikirim ulang. "
                             "Bila nominalnya berbeda, lampirkan bukti yang berbeda.")
    inv = await db.ar_invoices.find_one({"org_id": org, "deal_id": deal["id"]}, {"_id": 0})
    ts = now_iso()
    # Pengirim bukti adalah PELANGGAN, bukan pengguna sistem. Karena itu `created_by` diisi
    # aktor sistem "portal" dan identitas pelanggan disimpan di `submitted_by` (tertaut ke
    # `customers.id`). Dulu email pelanggan ditulis ke `created_by`, sehingga jejak audit
    # menunjuk "pengguna" yang tidak pernah ada di daftar pengguna (temuan forensik HIGH) dan
    # notifikasi in-app terkirim ke alamat yang tidak punya kotak masuk.
    doc = {
        "id": new_id(), "org_id": org, "deal_id": deal["id"],
        "customer_id": customer.get("id"), "customer_name": customer.get("name"),
        "unit_id": deal.get("unit_id"), "unit_code": (inv or {}).get("unit_code"),
        "amount": int(amount), "transfer_date": str(transfer_date)[:10],
        "bank_name": bank_name, "note": note, "source": "portal",
        "file_ids": [f["id"] for f in files], "file_shas": shas,
        "files": files, "state": "pending", "state_label": _label("pending"),
        "outstanding_at_submit": (inv or {}).get("outstanding"),
        "receipt_id": None, "bank_txn_id": None, "reject_reason": None,
        "verified_by": None, "verified_at": None,
        "submitted_by": {"customer_id": customer.get("id"), "name": customer.get("name"),
                         "contact": actor or customer.get("phone") or customer.get("email")},
        "created_by": "portal", "created_at": ts, "updated_at": ts,
    }
    await db.payment_intakes.insert_one(dict(doc))
    doc.pop("_id", None)
    await fin.notify_finance(
        org, "Bukti transfer baru dari pelanggan",
        (f"{customer.get('name')} mengirim bukti Rp {int(amount):,} untuk unit "
         f"{doc['unit_code'] or '-'} (tanggal transfer {doc['transfer_date']}). "
         "Verifikasi dulu — tagihan BELUM berkurang.").replace(",", "."),
        "finance", "payment_intake", doc["id"])
    await add_activity(entity_type="deal", entity_id=deal["id"], type="finance",
                       actor=f"portal:{customer.get('name') or 'pelanggan'}", org_id=org,
                       body=(f"Pelanggan mengirim bukti transfer Rp {int(amount):,} "
                             f"({doc['transfer_date']}) — menunggu verifikasi finance.")
                       .replace(",", "."))
    await emit("payment.proof_submitted", "deal", deal["id"],
              {"intake_id": doc["id"], "amount": int(amount)}, org_id=org)
    return doc


async def intake_or_error(org: str, intake_id: str) -> dict:
    row = await db.payment_intakes.find_one({"id": intake_id, "org_id": org}, {"_id": 0})
    if not row:
        raise ValueError("Bukti transfer tidak ditemukan.")
    return row


async def _tell_customer(org: str, row: dict, text: str) -> None:
    """Kabari PELANGGAN lewat kanal yang benar-benar dia punya (WhatsApp — mode simulasi
    bila kredensial belum dipasang).

    Kenapa bukan notifikasi in-app: kotak masuk in-app milik PENGGUNA SISTEM
    (`notifications.user_email` harus user terdaftar). Mengirimnya ke email pelanggan
    menciptakan jejak yang tidak bisa ditelusuri ke siapa pun (temuan forensik) dan tidak
    pernah terbaca. Status + alasannya tetap tampil di Portal Pelanggan.
    """
    from notifications import send_whatsapp

    cust = await db.customers.find_one({"id": row.get("customer_id"), "org_id": org},
                                      {"_id": 0, "phone": 1}) or {}
    phone = cust.get("phone") or (row.get("submitted_by") or {}).get("contact")
    if phone:
        await send_whatsapp(phone, text)


async def verify(org: str = ORG_ID, intake_id: str = None, actor: str = "system", *,
                 bank_txn_id: str = None, note: str = None,
                 allow_overpay: bool = False) -> dict:
    """Verifikasi finance — barulah tagihan berkurang (lewat jalur resmi apply_receipt)."""
    row = await intake_or_error(org, intake_id)
    if row["state"] != "pending":
        raise ValueError(f"Bukti ini sudah {_label(row['state'])} — tidak bisa diverifikasi lagi.")
    res = await fin.apply_receipt(
        row["deal_id"], int(row["amount"]), "transfer",
        note or f"Verifikasi bukti transfer pelanggan ({row['transfer_date']})",
        actor, org_id=org, allow_overpay=allow_overpay)
    ts = now_iso()
    await db.payment_intakes.update_one({"id": intake_id}, {"$set": {
        "state": "verified", "state_label": _label("verified"),
        "receipt_id": res["receipt"]["id"], "bank_txn_id": bank_txn_id,
        "verified_by": actor, "verified_at": ts, "verify_note": note, "updated_at": ts}})
    await add_activity(entity_type="deal", entity_id=row["deal_id"], type="finance",
                       actor=actor, org_id=org,
                       body=(f"Bukti transfer Rp {int(row['amount']):,} DIVERIFIKASI — "
                             f"tagihan berkurang (kuitansi {res['receipt']['id'][:8]}).")
                       .replace(",", "."))
    await _tell_customer(
        org, row,
        (f"Bukti transfer Anda Rp {int(row['amount']):,} sudah DIVERIFIKASI — tagihan unit "
         f"{row.get('unit_code') or '-'} sudah berkurang. Terima kasih.").replace(",", "."))
    return {"intake": await intake_or_error(org, intake_id), "receipt": res["receipt"],
            "invoice": res["invoice"]}


async def reject(org: str = ORG_ID, intake_id: str = None, actor: str = "system",
                 reason: str = None) -> dict:
    """Tolak bukti + alasan yang akan DIBACA PELANGGAN. AR tidak tersentuh."""
    if len((reason or "").strip()) < MIN_REJECT_REASON:
        raise ValueError(f"Alasan penolakan minimal {MIN_REJECT_REASON} huruf — pelanggan "
                         "harus tahu apa yang perlu diperbaiki.")
    row = await intake_or_error(org, intake_id)
    if row["state"] != "pending":
        raise ValueError(f"Bukti ini sudah {_label(row['state'])}.")
    ts = now_iso()
    await db.payment_intakes.update_one({"id": intake_id}, {"$set": {
        "state": "rejected", "state_label": _label("rejected"),
        "reject_reason": reason.strip(), "verified_by": actor, "verified_at": ts,
        "updated_at": ts}})
    await add_activity(entity_type="deal", entity_id=row["deal_id"], type="finance",
                       actor=actor, org_id=org,
                       body=f"Bukti transfer DITOLAK — {reason.strip()}")
    await _tell_customer(
        org, row,
        (f"Bukti transfer Anda Rp {int(row['amount']):,} BELUM bisa kami terima. Alasan: "
         f"{reason.strip()}. Silakan kirim ulang bukti yang sesuai lewat Portal.")
        .replace(",", "."))
    return await intake_or_error(org, intake_id)


async def revert_verification(org: str, intake_id: str, actor: str, reason: str) -> dict:
    """Kembalikan bukti ke 'menunggu verifikasi' setelah kuitansinya dibatalkan.

    Dipakai `bank_match.unmatch`: bila pencocokan dibatalkan, bukti pelanggan tidak boleh
    tetap berstatus "terverifikasi" — itu akan menjadi kebenaran kedua yang berbeda dari AR.
    """
    row = await intake_or_error(org, intake_id)
    ts = now_iso()
    await db.payment_intakes.update_one({"id": intake_id}, {"$set": {
        "state": "pending", "state_label": _label("pending"), "receipt_id": None,
        "bank_txn_id": None, "verified_by": None, "verified_at": None,
        "revert_reason": (reason or "").strip(), "updated_at": ts}})
    await add_activity(entity_type="deal", entity_id=row["deal_id"], type="finance",
                       actor=actor, org_id=org,
                       body=("Verifikasi bukti transfer DIBATALKAN — "
                             f"{(reason or '').strip()}"))
    return await intake_or_error(org, intake_id)


async def listing(org: str = ORG_ID, *, state: str = None, customer_id: str = None,
                  deal_id: str = None, skip: int = 0, limit: int = 50) -> dict:
    q = {"org_id": org}
    if state:
        q["state"] = state
    if customer_id:
        q["customer_id"] = customer_id
    if deal_id:
        q["deal_id"] = deal_id
    total = await db.payment_intakes.count_documents(q)
    rows = await db.payment_intakes.find(q, {"_id": 0}).sort("created_at", -1) \
        .skip(skip).limit(limit).to_list(limit)
    # Ringkasan HARUS memakai saringan barisnya. Portal pelanggan memanggil fungsi ini dengan
    # `customer_id` miliknya; ringkasan yang dihitung untuk seluruh organisasi membuat
    # pelanggan melihat JUMLAH & NOMINAL bukti transfer pelanggan LAIN — kebocoran data,
    # bukan sekadar angka yang salah.
    base = {k: v for k, v in q.items() if k != "state"}
    summary = {s: await db.payment_intakes.count_documents({**base, "state": s})
               for s in INTAKE_LABEL}
    summary["pending_amount"] = sum(
        int(r.get("amount") or 0) for r in await db.payment_intakes.find(
            {**base, "state": "pending"}, {"_id": 0, "amount": 1}).to_list(500))
    return {"data": rows, "total": total, "summary": summary}
