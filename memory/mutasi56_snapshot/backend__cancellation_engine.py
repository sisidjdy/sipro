"""MESIN PEMBATALAN KONTRAK & REFUND BERJURNAL (Fase 56C).

## Kenapa berkas ini ada

Dokumen SPR yang dicetak sistem ini sudah **menjanjikan** aturan pembatalan kepada pembeli
(potongan 35% sebelum pembangunan, 50% saat pembangunan berjalan, refund menyusul penjualan
ulang unit). Sampai Fase 55, tidak ada satu pun jalan menjalankan janji itu:

  * `POST /deals/{id}/cancel` melepas unit tetapi **membiarkan uang pembeli** tercatat di
    `2-1400 Uang Muka Penjualan` — pembukuan menyimpan kewajiban kepada orang yang
    kontraknya sudah tidak ada, dan tidak ada dokumen yang bisa ditunjukkan kepadanya.
  * Penolakan KPR hanya MENGUSULKAN nominal refund di layar; tidak ada yang membukukannya.

## Aturan yang dipegang berkas ini

1. **Pengaju bukan pemutus.** Manajer Sales/Marketing MENGAJUKAN (`cancellation:create`),
   Manajer Keuangan MEMUTUSKAN (`cancellation:approve`), Keuangan MEMBAYAR
   (`cancellation:update`). Satu orang tidak boleh menjalankan ketiganya.
2. **Dasar potongan dibaca dari KEADAAN NYATA**, bukan dari yang diketik pengaju: keadaan
   pembangunan unit menentukan 35% atau 50%, dan uang yang diterima dibaca dari saldo
   kewajiban kontrak (`contract_liabilities`, cermin akun `2-1400`) — bukan dari penjumlahan
   ulang yang bisa berbeda dengan jurnal.
3. **Angka yang belum diketahui tidak pernah menjadi 0 diam-diam.** Bila belum ada uang yang
   diterima, layar & dokumen menyebut faktanya ("belum ada penerimaan"), bukan "refund
   Rp 0" tanpa penjelasan.
4. **Jurnal lahir SAAT KEPUTUSAN, bukan saat pengajuan.** Pengajuan adalah niat; keputusan
   adalah peristiwa akuntansi. Idempoten lewat `source_event`.
5. **Titipan pelanggan (kelebihan bayar, `2-1450`) dikembalikan PENUH.** Uang itu tidak
   pernah menjadi bagian harga, jadi tidak boleh ikut dipotong.
6. **Pembayaran refund idempoten** lewat `client_ref` (pelajaran antrean perangkat Fase 50B)
   dan berhenti pada nominal yang disetujui — tidak bisa dibayar dua kali.
7. **Unit kembali ke stok secara ATOMIK** dan jejaknya tercatat di riwayat unit; rumah tidak
   boleh "hilang" dari ketersediaan hanya karena satu pembeli mundur.

## Jurnal yang dihasilkan

| Peristiwa | Debit | Kredit |
|---|---|---|
| Keputusan disetujui | `2-1400` uang muka penjualan yang diterima | `4-1200` potongan (pendapatan lain-lain) + `2-1460` utang refund |
| (bila ada titipan) | `2-1450` titipan pelanggan | `2-1460` utang refund |
| Refund dibayar | `2-1460` utang refund | `1-1200` bank / `1-1100` kas |
"""
import logging

import docgen
import gl_engine as gl
import lead_lifecycle as lc
import reference as ref
import sequences as seq
import settings_store as cfg
import stage_clock as clock
from core_utils import new_id, now_iso
from db import ORG_ID, ORG_NAME, db
from engine import add_activity, emit
from finance_engine import notify_finance

logger = logging.getLogger("sipro.cancellation")

OPEN_STATES = ("diajukan",)
APPROVED_STATES = ("disetujui", "refund_sebagian")
DONE_STATES = ("selesai", "ditolak")

# Akun jurnal (SSOT tunggal supaya layar, gate, dan dokumen tidak menebak sendiri).
AKUN_UANG_MUKA = "2-1400"
AKUN_TITIPAN = "2-1450"
AKUN_UTANG_REFUND = "2-1460"
AKUN_POTONGAN = "4-1200"
AKUN_BANK = "1-1200"
AKUN_KAS = "1-1100"

TEMPLATE_CODE = "BAP"
TEMPLATE_NAME = "Berita Acara Pembatalan & Perhitungan Refund"


def _rp(v) -> str:
    """Rupiah untuk dibaca manusia. `None` = belum diketahui (BUKAN Rp 0)."""
    if v is None:
        return "belum ditetapkan"
    return f"Rp {int(v):,}".replace(",", ".")


def _blk(code: str, detail: str) -> dict:
    """Sebab berlabel Kamus Data — layar tidak boleh mengarang kalimatnya sendiri."""
    return {"code": code, "label": ref.label_of("cancel_block", code), "detail": detail}


# ============================================================ dasar perhitungan
async def _build_basis(org: str, unit: dict) -> tuple:
    """Keadaan pembangunan NYATA → kode dasar potongan.

    Dibaca dari `construction_status`/`construction_progress` unit, bukan dari yang diketik
    pengaju: selisih 35% vs 50% pada satu unit rumah bisa bernilai puluhan juta rupiah.
    """
    status = str(unit.get("construction_status") or "not_started")
    progress = int(unit.get("construction_progress") or 0)
    if status == "done":
        return "sudah_selesai", "sudah selesai dibangun"
    if status in ("in_progress", "qc_hold") or progress > 0:
        return "sedang_dibangun", "pembangunan sedang berjalan"
    return "belum_mulai", "pembangunan belum dimulai"


async def compute(org: str, contract: dict) -> dict:
    """Hitungan pembatalan menurut ketentuan SPR + keadaan nyata (tanpa menulis apa pun)."""
    deal_id = contract.get("deal_id")
    unit = await db.units.find_one({"id": contract.get("unit_id")}, {"_id": 0}) or {}
    liab = await db.contract_liabilities.find_one(
        {"org_id": org, "deal_id": deal_id}, {"_id": 0}) or {}
    dep = await db.customer_deposits.find_one(
        {"org_id": org, "deal_id": deal_id}, {"_id": 0}) or {}
    received = max(0, int(liab.get("balance") or 0))
    deposit = max(0, int(dep.get("balance") or 0))
    basis, basis_note = await _build_basis(org, unit)
    key = ("cancellation.cut_before_build_pct" if basis == "belum_mulai"
           else "cancellation.cut_during_build_pct")
    pct = int(await cfg.get(key, org_id=org) or 0)
    cut = int(round(received * pct / 100))
    refund = received - cut
    requires_resale = bool(await cfg.get("cancellation.refund_requires_resale", org_id=org))
    return {
        "received_total": received,
        "deposit_balance": deposit,
        "basis": basis,
        "basis_label": ref.label_of("cancel_basis", basis),
        "basis_note": basis_note,
        "cut_pct": pct,
        "cut_amount": cut,
        "refund_amount": refund,
        "deposit_refund": deposit,
        "payable_total": refund + deposit,
        "rule_key": key,
        "rule_label": (f"Ketentuan SPR: potongan {pct}% karena {basis_note} "
                       f"(Pusat Konfigurasi → {key})"),
        "refund_requires_resale": requires_resale,
        # Kejujuran angka: "tidak ada refund" HARUS punya sebab yang tertulis, kalau tidak
        # pembeli membaca "Rp 0" dan menyangka sistemnya salah hitung.
        "note": ("Belum ada penerimaan yang tercatat pada kontrak ini, jadi tidak ada "
                 "potongan maupun dana yang dikembalikan." if received + deposit == 0 else
                 (f"Dari {_rp(received)} yang sudah diterima, {_rp(cut)} menjadi potongan "
                  f"({pct}%) dan {_rp(refund)} dikembalikan"
                  + (f", ditambah titipan {_rp(deposit)} yang dikembalikan PENUH "
                     "(titipan tidak pernah menjadi bagian harga)." if deposit else "."))),
    }


async def blocks(org: str, contract: dict) -> list:
    """Sebab-sebab pembatalan belum bisa DIAJUKAN — disebutkan, bukan tombol mati."""
    out = []
    if not contract:
        return [_blk("kontrak_belum_ada",
                     "Lead ini belum menjadi pembeli, jadi belum ada kontrak yang bisa "
                     "dibatalkan. Pembatalan reservasi/booking dilakukan dari daftar deal.")]
    if contract.get("state") == "cancelled":
        out.append(_blk("kontrak_sudah_batal",
                        "Kontrak ini sudah berstatus dibatalkan."))
    open_doc = await db.cancellations.find_one(
        {"org_id": org, "contract_id": contract["id"], "state": {"$in": list(OPEN_STATES)}},
        {"_id": 0, "number": 1})
    if open_doc:
        out.append(_blk("pengajuan_berjalan",
                        f"Pengajuan {open_doc.get('number')} masih menunggu keputusan "
                        "Manajer Keuangan."))
    legal = contract.get("legal") or {}
    if legal.get("ajb"):
        out.append(_blk("sudah_ajb",
                        "AJB sudah ditandatangani notaris — pembatalan sesudah AJB adalah "
                        "pembalikan jual beli yang harus lewat notaris, bukan tombol di "
                        "aplikasi ini."))
    bast = await db.unit_handovers.find_one(
        {"org_id": org, "deal_id": contract.get("deal_id"),
         "status": {"$ne": "cancelled"}}, {"_id": 0, "number": 1})
    if bast:
        out.append(_blk("sudah_bast",
                        f"Rumah sudah diserahterimakan ({bast.get('number')}). Batalkan BAST "
                        "lebih dahulu di menu Serah Terima & Garansi bila memang salah "
                        "terbit."))
    pending = await db.payment_intakes.count_documents(
        {"org_id": org, "deal_id": contract.get("deal_id"), "status": "pending"})
    if pending:
        out.append(_blk("bukti_menunggu_verifikasi",
                        f"Ada {pending} bukti transfer yang belum diverifikasi Keuangan. "
                        "Selesaikan dulu — nominal yang dikembalikan dihitung dari uang "
                        "yang SUDAH tercatat."))
    return out


async def preview(org: str, contract: dict) -> dict:
    """Pratinjau lengkap untuk layar: hitungan + sebab + riwayat pengajuan kontrak ini."""
    b = await blocks(org, contract)
    hitung = await compute(org, contract) if contract else {}
    riwayat = []
    if contract:
        riwayat = await db.cancellations.find(
            {"org_id": org, "contract_id": contract["id"]},
            {"_id": 0}).sort("created_at", -1).to_list(20)
    # Riwayat WAJIB melewati `enrich`: penahanan refund, sisa utang, dan izin membayar hanya
    # benar saat DIBACA (unit bisa terjual kembali kapan saja). Mengembalikan baris mentah
    # membuat layar Kontrak & Legal kehilangan alasan penahanan dan menulis "Sisa 0" —
    # tepat kesalahan "Rp 0 tanpa sebab" yang dilarang aplikasi ini.
    return {
        "contract": ({"id": contract["id"], "number": contract.get("number"),
                      "state": contract.get("state"), "scheme": contract.get("scheme"),
                      "unit_code": contract.get("unit_code"),
                      "customer_name": contract.get("customer_name")}
                     if contract else None),
        **hitung,
        "blocks": b,
        "can_request": bool(contract) and not b,
        "history": [await enrich(org, r) for r in riwayat],
    }


# ============================================================ pengajuan
async def request(org: str, contract: dict, actor: str, reason: str) -> dict:
    """Ajukan pembatalan. Belum ada jurnal — pengajuan adalah NIAT, bukan peristiwa uang."""
    b = await blocks(org, contract)
    if b:
        raise ValueError("Belum bisa diajukan. " + " ".join(x["detail"] for x in b))
    hitung = await compute(org, contract)
    ts = now_iso()
    doc = {
        "id": new_id(), "org_id": org,
        "number": await seq.next_number("cancellation", org, prefix="BTL"),
        "contract_id": contract["id"], "contract_number": contract.get("number"),
        "deal_id": contract.get("deal_id"), "customer_id": contract.get("customer_id"),
        "customer_name": contract.get("customer_name"), "lead_id": contract.get("lead_id"),
        "unit_id": contract.get("unit_id"), "unit_code": contract.get("unit_code"),
        "project_id": contract.get("project_id"), "assigned_to": contract.get("assigned_to"),
        "scheme": contract.get("scheme"),
        "state": "diajukan", "reason": reason,
        "basis_at_request": hitung,
        "requested_by": actor, "requested_at": ts,
        "decision": None, "settlement": None,
        "refund_payments": [], "refund_paid_total": 0,
        "journal_ids": [], "document_id": None,
        "created_at": ts, "updated_at": ts,
    }
    await db.cancellations.insert_one(dict(doc))
    doc.pop("_id", None)
    await add_activity(entity_type="lead", entity_id=contract.get("lead_id"), type="system",
                       body=(f"Pembatalan {doc['number']} diajukan untuk kontrak "
                             f"{contract.get('number')}: {reason}"),
                       actor=actor, org_id=org)
    await notify_finance(org, "Pembatalan menunggu keputusan",
                         (f"{doc['number']} · unit {contract.get('unit_code')} · usul refund "
                          f"{_rp(hitung['payable_total'])} (potongan {hitung['cut_pct']}%)."),
                         "finance", "cancellation", doc["id"])
    await emit("cancellation.requested", "cancellation", doc["id"],
               {"contract_id": contract["id"]}, org_id=org)
    return doc


# ============================================================ keputusan
async def _release_unit(org: str, cancel: dict, actor: str) -> bool:
    """Unit kembali ke stok — ATOMIK, dan hanya bila unit itu memang milik deal ini."""
    ts = now_iso()
    unit = await db.units.find_one_and_update(
        {"id": cancel["unit_id"], "org_id": org,
         "$or": [{"booked_by_deal": cancel["deal_id"]},
                 {"reserved_by_deal": cancel["deal_id"]},
                 {"sold_by_deal": cancel["deal_id"]},
                 {"deal_id": cancel["deal_id"]}]},
        # `sold_by_deal`/`sold_at` WAJIB ikut dikosongkan: unit yang kembali ke stok tetapi
        # masih menyimpan tautan penjualan lama adalah rumah yang mengaku "terjual" kepada
        # setiap laporan yang membacanya (site plan, invarian bisnis, gate integritas) —
        # padahal pembelinya sudah membatalkan dan uangnya sudah dikembalikan.
        {"$set": {"status": "available", "reserved_by_deal": None, "booked_by_deal": None,
                  "sold_by_deal": None, "sold_at": None,
                  "deal_id": None, "lead_id": None, "lead_name": None, "customer_id": None,
                  "contract_id": None, "payment_status": "none", "updated_at": ts},
         "$push": {"status_history": {
             "status": "available", "at": ts, "actor": actor,
             "note": (f"Dilepas kembali ke stok karena pembatalan {cancel['number']}: "
                      f"{cancel.get('reason')}")}}})
    return unit is not None


async def _void_ar(org: str, cancel: dict) -> dict:
    """Termin yang BELUM dibayar dibatalkan; yang sudah dibayar TIDAK dihapus.

    Menghapus riwayat pembayaran akan membuat kuitansi yang sudah dipegang pembeli tidak
    punya pasangan di sistem — itu bukan pembatalan, itu penghilangan bukti.
    """
    inv = await db.ar_invoices.find_one({"org_id": org, "deal_id": cancel["deal_id"]},
                                        {"_id": 0})
    if not inv:
        return {"invoice": None, "dibatalkan": 0}
    ts = now_iso()
    items, dibatalkan = [], 0
    for it in inv.get("items") or []:
        paid = int(it.get("paid_amount") or 0)
        if paid < int(it.get("amount") or 0):
            it = {**it, "status": "cancelled", "cancelled_at": ts,
                  "cancel_note": f"Kontrak dibatalkan ({cancel['number']})"}
            dibatalkan += 1
        items.append(it)
    # Tagihan yang SUDAH LUNAS tidak dibatalkan: tidak ada termin tersisa untuk dibatalkan,
    # dan menandainya "cancelled" akan menghapus kenyataan bahwa pembeli pernah melunasi
    # rumah itu (kuitansinya masih ada di tangannya).
    ubah = {"items": items, "cancellation_id": cancel["id"], "updated_at": ts,
            "cancel_reason": cancel.get("reason")}
    if dibatalkan:
        ubah.update({"status": "cancelled", "outstanding": 0, "cancelled_at": ts})
    await db.ar_invoices.update_one({"id": inv["id"]}, {"$set": ubah})
    return {"invoice": inv["id"], "dibatalkan": dibatalkan}


async def _post_decision_journal(org: str, cancel: dict, hitung: dict, actor: str) -> list:
    """Jurnal keputusan: kewajiban ke pembeli DISELESAIKAN (potongan + utang refund)."""
    lines = []
    if hitung["received_total"] > 0:
        lines.append({"account_code": AKUN_UANG_MUKA, "debit": hitung["received_total"],
                      "credit": 0, "memo": "Uang muka penjualan diselesaikan (pembatalan)"})
    if hitung["deposit_balance"] > 0:
        lines.append({"account_code": AKUN_TITIPAN, "debit": hitung["deposit_balance"],
                      "credit": 0, "memo": "Titipan pelanggan dikembalikan penuh"})
    if hitung["cut_amount"] > 0:
        lines.append({"account_code": AKUN_POTONGAN, "debit": 0,
                      "credit": hitung["cut_amount"],
                      "memo": f"Potongan pembatalan {hitung['cut_pct']}% "
                              f"({hitung['basis_label']})"})
    if hitung["payable_total"] > 0:
        lines.append({"account_code": AKUN_UTANG_REFUND, "debit": 0,
                      "credit": hitung["payable_total"],
                      "memo": "Utang refund kepada pembeli"})
    if not lines:
        return []
    entry = await gl.post_journal(
        org, f"Pembatalan {cancel['number']} · unit {cancel.get('unit_code')}", lines,
        source_type="cancellation", source_id=cancel["id"],
        source_event=f"cancel:{cancel['id']}:approve", posted_by=actor, auto=True,
        source_deal_id=cancel.get("deal_id"))
    return [entry["id"]]


async def _generate_document(org: str, cancel: dict, hitung: dict, actor: str) -> dict:
    """Berita Acara Pembatalan — dokumen yang bisa dibaca & dicetak PEMBELI.

    Template disimpan sebagai DATA (`document_templates`) mengikuti aturan Fase 53E, jadi
    admin bisa memperbaiki kalimatnya tanpa deploy, dan dokumen menyimpan versi yang dipakai.
    """
    await ensure_template(org)
    tpl = await db.document_templates.find_one({"org_id": org, "code": TEMPLATE_CODE},
                                               {"_id": 0})
    project = await db.projects.find_one({"id": cancel.get("project_id")}, {"_id": 0}) or {}
    number = await docgen.next_doc_number(org, TEMPLATE_CODE, project)
    contract = await db.contracts.find_one({"id": cancel["contract_id"]}, {"_id": 0}) or {}
    unit = await db.units.find_one({"id": cancel.get("unit_id")}, {"_id": 0}) or {}
    ctx = {
        "doc_number": number,
        "developer_name": project.get("developer_name") or ORG_NAME,
        "property_name": project.get("name") or "belum ditetapkan",
        "customer_name": cancel.get("customer_name") or "belum ditetapkan",
        "unit_block": unit.get("code") or "belum ditetapkan",
        "unit_type_label": f"tipe {unit.get('type')}" if unit.get("type") else "belum ditetapkan",
        "contract_number": cancel.get("contract_number") or "belum ditetapkan",
        "scheme_label": contract.get("scheme_label") or ref.label_of(
            "payment_scheme", contract.get("scheme") or ""),
        "cancel_number": cancel["number"],
        "cancel_reason": cancel.get("reason") or "belum ditetapkan",
        "build_basis": hitung["basis_note"],
        "received_total": _rp(hitung["received_total"]),
        "cut_pct": f"{hitung['cut_pct']}%",
        "cut_amount": _rp(hitung["cut_amount"]),
        "refund_amount": _rp(hitung["refund_amount"]),
        "deposit_refund": _rp(hitung["deposit_refund"]),
        "payable_total": _rp(hitung["payable_total"]),
        "refund_clause": ("Pengembalian dana dilakukan setelah unit yang dibatalkan berhasil "
                          "terjual kembali kepada pihak lain."
                          if hitung["refund_requires_resale"] else
                          "Pengembalian dana dilakukan tanpa menunggu penjualan ulang unit."),
        "rule_label": hitung["rule_label"],
        "decided_by": actor,
        "decided_at": now_iso()[:10],
        "money_note": hitung["note"],
    }
    content = docgen.render(tpl["content"], ctx)
    ts = now_iso()
    doc = {
        "id": new_id(), "org_id": org, "template_id": tpl["id"],
        "template_code": TEMPLATE_CODE, "template_version": int(tpl.get("version") or 1),
        "doc_number": number, "title": TEMPLATE_NAME,
        "deal_id": cancel.get("deal_id"), "contract_id": cancel.get("contract_id"),
        "lead_id": cancel.get("lead_id"), "customer_id": cancel.get("customer_id"),
        "unit_id": cancel.get("unit_id"), "assigned_to": cancel.get("assigned_to"),
        "cancellation_id": cancel["id"],
        "content": content, "status": "draft", "signatures": [],
        "context_snapshot": ctx, "note": None, "warnings": [],
        "created_by": actor, "created_at": ts, "updated_at": ts,
    }
    await db.documents.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


async def decide(org: str, cid: str, actor: str, approved: bool, note: str) -> dict:
    """Keputusan Manajer Keuangan. Di sinilah uang berpindah keadaan (jurnal lahir)."""
    cancel = await db.cancellations.find_one({"id": cid, "org_id": org}, {"_id": 0})
    if not cancel:
        raise ValueError("Pengajuan pembatalan tidak ditemukan.")
    if cancel["state"] != "diajukan":
        raise ValueError(f"Pengajuan ini sudah "
                         f"{ref.label_of('cancel_state', cancel['state'])} — tidak bisa "
                         "diputus dua kali.")
    if cancel.get("requested_by") == actor:
        # Empat mata: yang mengajukan tidak boleh memutuskan pengajuannya sendiri.
        raise ValueError("Pengaju tidak boleh memutuskan pengajuannya sendiri "
                         "(pemisahan tugas).")
    ts = now_iso()
    if not approved:
        await db.cancellations.update_one({"id": cid}, {"$set": {
            "state": "ditolak", "updated_at": ts,
            "decision": {"approved": False, "by": actor, "at": ts, "note": note}}})
        await add_activity(entity_type="lead", entity_id=cancel.get("lead_id"), type="system",
                           body=f"Pembatalan {cancel['number']} DITOLAK: {note}",
                           actor=actor, org_id=org)
        await emit("cancellation.rejected", "cancellation", cid, {}, org_id=org)
        return await db.cancellations.find_one({"id": cid}, {"_id": 0})

    contract = await db.contracts.find_one({"id": cancel["contract_id"], "org_id": org},
                                           {"_id": 0})
    if not contract:
        raise ValueError("Kontrak pengajuan ini tidak ditemukan.")
    # Uang bisa bergerak antara pengajuan dan keputusan — hitung ULANG pada saat memutuskan.
    hitung = await compute(org, contract)
    journal_ids = await _post_decision_journal(org, cancel, hitung, actor)
    ar = await _void_ar(org, cancel)
    released = await _release_unit(org, cancel, actor)
    if hitung["deposit_balance"] > 0:
        # Titipan dipindahkan ke utang refund lewat jurnal di atas; saldo titipan ditutup
        # TANPA memakai `_deposit_move` supaya tidak lahir jurnal kedua untuk uang yang sama.
        await db.customer_deposits.update_one(
            {"org_id": org, "deal_id": cancel["deal_id"]},
            {"$inc": {"balance": -hitung["deposit_balance"]},
             "$push": {"entries": {
                 "id": new_id(), "type": "cancel_transfer",
                 "amount": hitung["deposit_balance"],
                 "note": f"Dipindahkan ke utang refund pembatalan {cancel['number']}",
                 "actor": actor, "created_at": ts}},
             "$set": {"updated_at": ts}})
    if hitung["received_total"] > 0:
        # Cermin subledger dari `Dr 2-1400` pada jurnal keputusan: kewajiban kontrak SELESAI.
        # Tanpa baris ini buku besar dan subledger berbeda (tie-out MERAH) dan laporan
        # kewajiban masih menagih uang yang sudah diselesaikan pembatalan.
        await db.contract_liabilities.update_one(
            {"org_id": org, "deal_id": cancel["deal_id"]},
            {"$set": {"balance": 0, "cancelled": True, "cancellation_id": cid,
                      "cleared_by_cancellation": hitung["received_total"],
                      "updated_at": ts}})
    await db.deals.update_one({"id": cancel["deal_id"]}, {"$set": {
        "status": "cancelled", "cancelled_at": ts, "cancel_reason": cancel.get("reason"),
        "cancellation_id": cid, "updated_at": ts,
        **await clock.patch_for("deal", "cancelled", org_id=org, at=ts)}})
    await db.contracts.update_one({"id": contract["id"]}, {"$set": {
        "state": "cancelled", "cancelled_at": ts, "cancellation_id": cid,
        "cancel_reason": cancel.get("reason"), "updated_at": ts}})
    lead = await db.leads.find_one({"id": cancel.get("lead_id")}, {"_id": 0})
    if lead and lead.get("stage") not in ("lost",):
        await lc.record(lead, "lost", actor=actor,
                        reason=f"Kontrak dibatalkan ({cancel['number']}): "
                               f"{cancel.get('reason')}",
                        evidence={"cancellation_id": cid}, source="cancellation")
    doc = await _generate_document(org, cancel, hitung, actor)
    settlement = {
        **hitung,
        "ar_invoice_id": ar["invoice"], "ar_terms_cancelled": ar["dibatalkan"],
        "unit_released": released,
    }
    await db.cancellations.update_one({"id": cid}, {"$set": {
        "state": "disetujui", "updated_at": ts,
        "decision": {"approved": True, "by": actor, "at": ts, "note": note},
        "settlement": settlement, "journal_ids": journal_ids,
        "document_id": doc["id"], "document_number": doc["doc_number"]}})
    await add_activity(entity_type="lead", entity_id=cancel.get("lead_id"), type="system",
                       body=(f"Pembatalan {cancel['number']} DISETUJUI. Potongan "
                             f"{_rp(hitung['cut_amount'])} ({hitung['cut_pct']}%), utang "
                             f"refund {_rp(hitung['payable_total'])}. Unit "
                             f"{cancel.get('unit_code')} kembali ke stok."),
                       actor=actor, org_id=org)
    await notify_finance(org, "Refund pembatalan menunggu pembayaran",
                         (f"{cancel['number']} · {_rp(hitung['payable_total'])} kepada "
                          f"{cancel.get('customer_name')}."),
                         "finance", "cancellation", cid)
    await emit("cancellation.approved", "cancellation", cid,
               {"contract_id": contract["id"], "unit_id": cancel.get("unit_id"),
                "payable_total": hitung["payable_total"]}, org_id=org)
    return await db.cancellations.find_one({"id": cid}, {"_id": 0})


# ============================================================ pembayaran refund
async def refund_hold(org: str, cancel: dict) -> dict:
    """Sebab refund belum bisa dibayar (atau `None` bila sudah boleh)."""
    payable = int((cancel.get("settlement") or {}).get("payable_total") or 0)
    if int(cancel.get("refund_paid_total") or 0) >= payable > 0:
        # Diperiksa LEBIH DAHULU daripada keadaan: pembatalan yang sudah `selesai` bukan
        # "belum disetujui". Salah urut membuat layar & API menjawab sebab yang keliru
        # ("belum disetujui") untuk refund yang justru sudah lunas.
        return {"code": "sudah_lunas", "label": ref.label_of("refund_hold", "sudah_lunas"),
                "detail": "Refund pembatalan ini sudah dibayar penuh."}
    if cancel["state"] not in APPROVED_STATES:
        return {"code": "belum_disetujui",
                "label": ref.label_of("refund_hold", "belum_disetujui"),
                "detail": "Pembatalan belum disetujui Manajer Keuangan."}
    if payable <= 0:
        return {"code": "refund_nol", "label": ref.label_of("refund_hold", "refund_nol"),
                "detail": (cancel.get("settlement") or {}).get("note")
                or "Tidak ada dana yang perlu dikembalikan."}
    if (cancel.get("settlement") or {}).get("refund_requires_resale"):
        unit = await db.units.find_one({"id": cancel.get("unit_id")}, {"_id": 0}) or {}
        # "Terjual kembali" HARUS berarti unit itu benar-benar keluar dari stok. Menilainya
        # hanya dari tautan deal membuat tautan BASI (deal yang justru dibatalkan, atau
        # perbaikan data lama yang menempelkannya kembali) terbaca sebagai pembeli baru —
        # dan penahanan yang dijanjikan SPR lenyap tanpa ada pembeli baru mana pun.
        terjual_ulang = (str(unit.get("status") or "") not in ("available", "")
                         and bool(unit.get("reserved_by_deal") or unit.get("booked_by_deal")
                                  or unit.get("deal_id"))
                         and unit.get("deal_id") != cancel.get("deal_id")
                         and unit.get("booked_by_deal") != cancel.get("deal_id")
                         and unit.get("reserved_by_deal") != cancel.get("deal_id"))
        if not terjual_ulang:
            return {"code": "menunggu_penjualan_ulang",
                    "label": ref.label_of("refund_hold", "menunggu_penjualan_ulang"),
                    "detail": (f"Ketentuan SPR: pengembalian dana menyusul penjualan ulang "
                               f"unit {cancel.get('unit_code')}. Unit itu sekarang berada di "
                               "stok dan belum dipesan pembeli lain. Manajer Keuangan boleh "
                               "mengabaikan penahanan ini dengan alasan tertulis.")}
    return None


async def pay_refund(org: str, cid: str, actor: str, *, method: str, amount: int = None,
                     client_ref: str = None, note: str = None, override: bool = False,
                     override_reason: str = None, may_override: bool = False) -> dict:
    """Bayar refund (boleh bertahap). Idempoten lewat `client_ref`."""
    cancel = await db.cancellations.find_one({"id": cid, "org_id": org}, {"_id": 0})
    if not cancel:
        raise ValueError("Pengajuan pembatalan tidak ditemukan.")
    if client_ref:
        for p in cancel.get("refund_payments") or []:
            if p.get("client_ref") == client_ref:
                # Kiriman ulang penanda yang sama BUKAN pembayaran kedua.
                return {"cancellation": cancel, "payment": p, "replay": True}
    hold = await refund_hold(org, cancel)
    if hold and hold["code"] == "menunggu_penjualan_ulang":
        if not override:
            raise ValueError(hold["detail"])
        if not may_override:
            raise ValueError("Hanya Manajer Keuangan yang boleh mengabaikan penahanan "
                             "refund ini.")
        if len((override_reason or "").strip()) < 10:
            raise ValueError("Alasan pengabaian wajib minimal 10 huruf — keputusan ini "
                             "dibaca auditor.")
    elif hold:
        raise ValueError(hold["detail"])

    payable = int((cancel.get("settlement") or {}).get("payable_total") or 0)
    paid = int(cancel.get("refund_paid_total") or 0)
    sisa = payable - paid
    amount = int(amount or sisa)
    if amount <= 0:
        raise ValueError("Nominal refund harus lebih dari 0.")
    if amount > sisa:
        raise ValueError(f"Nominal melebihi sisa utang refund ({_rp(sisa)}). Refund tidak "
                         "boleh dibayar dua kali.")
    akun_kas = AKUN_KAS if method == "tunai" else AKUN_BANK
    ts = now_iso()
    pid = new_id()
    entry = await gl.post_journal(
        org, f"Pembayaran refund pembatalan {cancel['number']}", [
            {"account_code": AKUN_UTANG_REFUND, "debit": amount, "credit": 0,
             "memo": f"Utang refund kepada {cancel.get('customer_name')}"},
            {"account_code": akun_kas, "debit": 0, "credit": amount,
             "memo": ref.label_of("refund_method", method)},
        ], source_type="cancellation_refund", source_id=pid,
        source_event=f"cancel:{cid}:refund:{pid}", posted_by=actor, auto=True,
        source_deal_id=cancel.get("deal_id"))
    payment = {"id": pid, "amount": amount, "method": method,
               "method_label": ref.label_of("refund_method", method),
               "account_code": akun_kas, "note": note, "client_ref": client_ref,
               "override": bool(override), "override_reason": override_reason or None,
               "journal_id": entry["id"], "actor": actor, "at": ts}
    total = paid + amount
    state = "selesai" if total >= payable else "refund_sebagian"
    await db.cancellations.update_one({"id": cid}, {
        "$push": {"refund_payments": payment, "journal_ids": entry["id"]},
        "$set": {"refund_paid_total": total, "state": state, "updated_at": ts}})
    await add_activity(entity_type="lead", entity_id=cancel.get("lead_id"), type="system",
                       body=(f"Refund pembatalan {cancel['number']} dibayar {_rp(amount)} "
                             f"({ref.label_of('refund_method', method)})."
                             + (" Penahanan 'menunggu penjualan ulang' diabaikan: "
                                f"{override_reason}" if override else "")),
                       actor=actor, org_id=org)
    await emit("cancellation.refund_paid", "cancellation", cid,
               {"amount": amount, "total": total}, org_id=org)
    fresh = await db.cancellations.find_one({"id": cid}, {"_id": 0})
    return {"cancellation": fresh, "payment": payment, "replay": False}


# ============================================================ pembacaan
async def enrich(org: str, cancel: dict) -> dict:
    """Tambah keadaan yang HANYA benar saat dibaca (penahanan refund, sisa, label)."""
    hold = await refund_hold(org, cancel)
    payable = int((cancel.get("settlement") or {}).get("payable_total") or 0)
    paid = int(cancel.get("refund_paid_total") or 0)
    return {
        **cancel,
        "state_label": ref.label_of("cancel_state", cancel.get("state") or ""),
        "refund_payable": payable,
        "refund_outstanding": max(0, payable - paid),
        "refund_hold": hold,
        "can_pay_refund": hold is None,
        "journals": await db.journal_entries.find(
            {"org_id": org, "id": {"$in": cancel.get("journal_ids") or []}},
            {"_id": 0, "id": 1, "entry_no": 1, "date": 1, "memo": 1, "lines": 1,
             "total_debit": 1}).to_list(20),
    }


async def listing(org: str, *, state: str = None, contract_id: str = None,
                  customer_id: str = None, q: str = None, skip: int = 0,
                  limit: int = 50) -> dict:
    query = {"org_id": org}
    if state:
        query["state"] = state
    if contract_id:
        query["contract_id"] = contract_id
    if customer_id:
        query["customer_id"] = customer_id
    if q:
        rx = {"$regex": q.strip(), "$options": "i"}
        query["$or"] = [{"number": rx}, {"customer_name": rx}, {"unit_code": rx},
                        {"contract_number": rx}]
    total = await db.cancellations.count_documents(query)
    rows = await db.cancellations.find(query, {"_id": 0}).sort(
        "created_at", -1).skip(skip).limit(limit).to_list(limit)
    counts = {}
    for s in ref.values("cancel_state"):
        counts[s] = await db.cancellations.count_documents({**{k: v for k, v in query.items()
                                                              if k != "state"}, "state": s})
    return {"data": [await enrich(org, r) for r in rows], "total": total, "counts": counts}


async def get(org: str, cid: str) -> dict:
    cancel = await db.cancellations.find_one({"id": cid, "org_id": org}, {"_id": 0})
    if not cancel:
        raise ValueError("Pengajuan pembatalan tidak ditemukan.")
    return await enrich(org, cancel)


async def portal_rows(org: str, deal_ids: list) -> dict:
    """Pembatalan MILIK PEMBELI, dalam bahasa pembeli (dipakai `/api/portal/cancellations`).

    Tinggal di mesin, bukan di router portal: angkanya WAJIB berasal dari satu sumber yang
    sama dengan yang dibaca staf, supaya pembeli dan staf tidak pernah membaca dua versi
    hitungan yang berbeda. Tidak ada nomor akun & istilah internal yang lewat ke sini.
    """
    rows = []
    if deal_ids:
        rows = await db.cancellations.find(
            {"org_id": org, "deal_id": {"$in": deal_ids}},
            {"_id": 0}).sort("created_at", -1).to_list(20)
    out = []
    for r in rows:
        s = r.get("settlement") or r.get("basis_at_request") or {}
        paid = int(r.get("refund_paid_total") or 0)
        payable = int(s.get("payable_total") or 0)
        out.append({
            "number": r.get("number"), "state": r.get("state"),
            "state_label": ref.label_of("cancel_state", r.get("state") or ""),
            "unit_code": r.get("unit_code"), "reason": r.get("reason"),
            "requested_at": r.get("requested_at"),
            "decided_at": (r.get("decision") or {}).get("at"),
            "received_total": s.get("received_total"), "cut_pct": s.get("cut_pct"),
            "cut_amount": s.get("cut_amount"), "refund_amount": s.get("refund_amount"),
            "deposit_refund": s.get("deposit_refund"), "payable_total": payable,
            "refund_paid_total": paid, "refund_outstanding": max(0, payable - paid),
            "rule_label": s.get("rule_label"), "money_note": s.get("note"),
            "document_number": r.get("document_number"),
            "document_id": r.get("document_id"),
            "payments": [{"amount": p.get("amount"), "at": p.get("at"),
                          "method_label": p.get("method_label")}
                         for p in (r.get("refund_payments") or [])],
            "waiting_note": (
                "Sesuai ketentuan Surat Pesanan Rumah, pengembalian dana dilakukan setelah "
                "unit yang dibatalkan terjual kembali."
                if s.get("refund_requires_resale") and payable > paid
                and r.get("state") in ("disetujui", "refund_sebagian") else None),
        })
    return {"data": out,
            "reason": (None if out else
                       "Tidak ada pembatalan pada pesanan Anda — ini kabar baik.")}



# ============================================================ template dokumen (DATA)
_BAP = """BERITA ACARA PEMBATALAN PESANAN & PERHITUNGAN PENGEMBALIAN DANA
Nomor: {{doc_number}}

Pada hari ini, {{decided_at}}, yang bertanda tangan di bawah ini:

I.  {{developer_name}}, selanjutnya disebut PIHAK PERTAMA (Pengembang) — proyek
    {{property_name}}.
II. {{customer_name}}, selanjutnya disebut PIHAK KEDUA (Pemesan) atas unit
    {{unit_block}} ({{unit_type_label}}), kontrak {{contract_number}} dengan skema
    pembayaran {{scheme_label}}.

Kedua belah pihak sepakat menyatakan hal-hal berikut:

1. PEMBATALAN
   Pesanan atas unit {{unit_block}} DIBATALKAN dengan nomor pembatalan {{cancel_number}}.
   Alasan yang dicatat: {{cancel_reason}}
   Keadaan pembangunan pada saat pembatalan: {{build_basis}}.

2. PERHITUNGAN
   Total pembayaran yang telah diterima PIHAK PERTAMA : {{received_total}}
   Potongan pembatalan ({{cut_pct}})                  : {{cut_amount}}
   Pengembalian dari pembayaran                        : {{refund_amount}}
   Pengembalian titipan/kelebihan bayar                : {{deposit_refund}}
   TOTAL YANG DIKEMBALIKAN                             : {{payable_total}}

   Dasar perhitungan: {{rule_label}}
   Catatan: {{money_note}}

3. PENGEMBALIAN DANA
   {{refund_clause}}
   Pengembalian dilakukan melalui transfer ke rekening atas nama PIHAK KEDUA, dan menjadi
   selesai setelah seluruh nominal pada angka 2 dibayarkan.

4. AKIBAT PEMBATALAN
   a. Unit {{unit_block}} kembali menjadi persediaan PIHAK PERTAMA dan dapat dipesan pihak
      lain.
   b. Tagihan (termin) yang belum dibayar dinyatakan batal dan tidak lagi ditagihkan.
   c. Dokumen pesanan (SPR) beserta lampirannya tidak lagi berlaku sebagai dasar transaksi.

5. PENUTUP
   Berita acara ini dibuat dua rangkap bermeterai cukup, masing-masing pihak memegang satu
   rangkap dengan kekuatan hukum yang sama.

PIHAK PERTAMA                                   PIHAK KEDUA


{{developer_name}}                              {{customer_name}}
Diputuskan oleh: {{decided_by}}
"""


async def ensure_template(org: str = ORG_ID) -> dict:
    """Pasang/segarkan template Berita Acara Pembatalan. Idempoten; `version` naik bila isi berubah."""
    ts = now_iso()
    cur = await db.document_templates.find_one({"org_id": org, "code": TEMPLATE_CODE},
                                               {"_id": 0})
    if not cur:
        await db.document_templates.insert_one({
            "id": new_id(), "org_id": org, "code": TEMPLATE_CODE, "name": TEMPLATE_NAME,
            "scheme": None, "doc_code": TEMPLATE_CODE, "content": _BAP, "version": 1,
            "is_active": True, "generator": True, "source_file": None,
            "created_by": "system", "created_at": ts, "updated_at": ts})
        return {"created": TEMPLATE_CODE}
    if (cur.get("content") or "") != _BAP:
        await db.document_templates.update_one({"id": cur["id"]}, {"$set": {
            "name": TEMPLATE_NAME, "doc_code": TEMPLATE_CODE, "content": _BAP,
            "version": int(cur.get("version") or 1) + 1, "is_active": True,
            "generator": True, "updated_at": ts}})
        return {"updated": TEMPLATE_CODE}
    return {"unchanged": TEMPLATE_CODE}
