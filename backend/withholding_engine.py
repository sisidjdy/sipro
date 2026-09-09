"""Bukti potong PPh / e-Bupot (Fase 49F) — memotong TANPA membuktikan itu utang tersembunyi.

Tiga cacat nyata yang ditutup:

1. **Sistem sudah memotong, tetapi tidak pernah menerbitkan bukti.** Fee mitra dipotong PPh
   21/23 saat disetujui (jurnal `Cr 2-1300 Utang Pajak`) dan pembayaran tagihan vendor bisa
   memotong PPh jasa konstruksi — namun pihak yang dipotong tidak pernah menerima bukti potong
   bernomor. Tanpa bukti potong, potongan itu tidak bisa dikreditkan lawan transaksi dan
   kewajiban PER-24/PJ/2021 tidak terpenuhi.
2. **Tidak ada tie-out antara potongan NYATA dan bukti yang terbit.** Modul ini selalu
   menghitung dua sisi: potongan yang benar-benar terjadi (dari `payments_out` dan
   `marketing_fees`) versus bukti potong yang sudah diterbitkan — sisanya disebut apa adanya
   sebagai "belum berbukti potong", bukan disembunyikan.
3. **Pembetulan dengan nomor baru = lapor dobel.** PER-24/PJ/2021 menuntut nomor bukti potong
   TIDAK berubah saat dibetulkan. Di sini pembetulan menaikkan `version` dan menyimpan riwayat
   nilai lama, sedangkan nomornya tetap; pembatalan wajib beralasan dan nomornya mati.

Uang IDR integer; waktu UTC ISO-8601; seluruh query ber-scope `org_id`.
"""
import csv
import io
import logging
from xml.sax.saxutils import escape

import reference as ref
import sequences as seq
import settings_store as st
import tax_ids as tid
from core_utils import period_of  # noqa: F401 — CFG-01
from core_utils import new_id, now_iso
from db import db, ORG_ID
from tax_faktur_export import ExportHold

logger = logging.getLogger("sipro.tax.bupot")

ISSUED, CORRECTED, CANCELLED = "issued", "corrected", "cancelled"
ALIVE = (ISSUED, CORRECTED)

# Tarif bawaan diambil dari Pusat Konfigurasi — bukan angka hardcode di kode, karena tarif
# berubah lewat peraturan dan tiap perusahaan punya kualifikasi berbeda.
RATE_KEYS = {
    "pph23": "tax.pph23_rate",
    "pph4_2_konstruksi": "tax.pph4_2_konstruksi_rate",
    "pph4_2_sewa": "tax.pph4_2_sewa_rate",
    "pph21": "partner.tax_pph21_rate",
}
# Jenis mitra yang berbentuk BADAN → PPh 23; sisanya orang pribadi → PPh 21.
COMPANY_AGENT_TYPES = {"broker_kantor", "mitra_korporat"}


def _rp(n) -> str:
    return "Rp " + f"{int(n or 0):,}".replace(",", ".")


def tax_of(base, rate) -> int:
    """Potongan = dasar × tarif, dibulatkan ke rupiah penuh."""
    return int(round(int(base or 0) * float(rate or 0) / 100.0))


async def config(org_id=ORG_ID) -> dict:
    keys = ["tax.company_npwp", "tax.company_idtku", "tax.bupot_series", *RATE_KEYS.values()]
    vals = await st.get_many(keys, org_id=org_id)
    company = tid.npwp16(vals.get("tax.company_npwp"), label="NPWP perusahaan")
    orgdoc = await db.orgs.find_one({"id": org_id}, {"_id": 0, "name": 1}) or {}
    return {
        "company_npwp": company["value"], "company_npwp_state": company,
        "company_idtku": str(vals.get("tax.company_idtku") or ""),
        "company_name": orgdoc.get("name") or "PT SIPRO Land",
        "series": str(vals.get("tax.bupot_series") or "01")[:2],
        "rates": {kind: float(vals.get(key) or 0) for kind, key in RATE_KEYS.items()},
    }


async def default_rate(org_id, kind: str) -> float:
    return (await config(org_id))["rates"].get(kind, 0.0)


async def next_number(org_id, year: str = None) -> str:
    """Nomor bukti potong 10 digit: 2 digit kode seri + 8 digit urut (PER-24/PJ/2021)."""
    cfg = await config(org_id)
    y = year or now_iso()[:4]
    n = await seq.next_seq("bupot", org_id, y)
    return f"{cfg['series']}{str(n).zfill(8)}"


# =============================================================== potongan NYATA
async def _vendor_identity(org_id, vendor_name: str) -> dict:
    v = await db.vendors.find_one({"org_id": org_id, "name": vendor_name},
                                  {"_id": 0, "npwp": 1, "name": 1}) or {}
    return {"npwp": v.get("npwp"), "kind": "company"}


async def _agent_identity(org_id, agent_id: str) -> dict:
    a = await db.agents.find_one({"org_id": org_id, "id": agent_id},
                                 {"_id": 0, "npwp": 1, "agent_type": 1, "name": 1}) or {}
    kind = "company" if a.get("agent_type") in COMPANY_AGENT_TYPES else "individual"
    return {"npwp": a.get("npwp"), "kind": kind, "agent_type": a.get("agent_type")}


async def actual_deductions(org_id=ORG_ID, period: str = None) -> dict:
    """Potongan PPh yang BENAR-BENAR terjadi di pembukuan, apa pun status bukti potongnya."""
    rows = []
    for p in await db.payments_out.find({"org_id": org_id, "withheld_amount": {"$gt": 0}},
                                        {"_id": 0}).to_list(20000):
        per = period_of(p.get("created_at"))
        if period and per != period:
            continue
        rows.append({
            "basis": "ap_payment", "ref_id": p["id"], "period": per,
            "party_name": p.get("vendor"), "kind": p.get("withheld_kind"),
            "base": int(p.get("withheld_base", 0) or 0), "rate": float(p.get("withheld_rate", 0) or 0),
            "amount": int(p.get("withheld_amount", 0) or 0),
            "ref_label": f"Pembayaran tagihan {p.get('vendor') or ''}".strip(),
            "date": str(p.get("created_at") or "")[:10], "bill_id": p.get("bill_id"),
        })
    for f in await db.marketing_fees.find(
            {"org_id": org_id, "pph_amount": {"$gt": 0},
             "status": {"$in": ["approved", "paid"]}}, {"_id": 0}).to_list(20000):
        per = period_of(f.get("approved_at") or f.get("created_at"))
        if period and per != period:
            continue
        ident = await _agent_identity(org_id, f.get("agent_id"))
        rows.append({
            "basis": "partner_fee", "ref_id": f["id"], "period": per,
            "party_name": f.get("agent_name"),
            "kind": "pph23" if ident["kind"] == "company" else "pph21",
            "base": int(f.get("amount_gross", 0) or 0), "rate": float(f.get("pph_pct", 0) or 0),
            "amount": int(f.get("pph_amount", 0) or 0),
            "ref_label": f"Fee mitra {f.get('no')} — unit {f.get('unit_code') or '-'}",
            "date": str(f.get("approved_at") or f.get("created_at") or "")[:10],
            "party_kind": ident["kind"], "party_npwp": ident.get("npwp"),
            "project_id": f.get("project_id"),
        })
    rows.sort(key=lambda r: r.get("date") or "", reverse=True)
    return {"rows": rows, "total": sum(r["amount"] for r in rows), "count": len(rows)}


async def candidates(org_id=ORG_ID, period: str = None) -> dict:
    """Potongan nyata yang BELUM punya bukti potong — daftar kerja yang jujur."""
    act = await actual_deductions(org_id, period)
    issued = {(d.get("basis"), d.get("ref_id")) for d in await db.withholding_docs.find(
        {"org_id": org_id, "state": {"$in": list(ALIVE)}},
        {"_id": 0, "basis": 1, "ref_id": 1}).to_list(20000)}
    rows = [r for r in act["rows"] if (r["basis"], r["ref_id"]) not in issued]
    return {
        "rows": rows, "count": len(rows), "total": sum(r["amount"] for r in rows),
        "detail": ("Semua potongan PPh pada periode ini sudah punya bukti potong."
                   if not rows else
                   f"{len(rows)} potongan senilai {_rp(sum(r['amount'] for r in rows))} "
                   "belum diterbitkan bukti potongnya."),
    }


# =============================================================== terbit / betulkan / batal
async def _resolve_party(org_id, data: dict) -> dict:
    """Lengkapi identitas pihak dari master (vendor/mitra) bila tidak dikirim pemakai."""
    npwp = data.get("party_npwp")
    kind = data.get("party_kind") or "company"
    if not npwp and data.get("basis") == "partner_fee" and data.get("agent_id"):
        ident = await _agent_identity(org_id, data["agent_id"])
        npwp, kind = ident.get("npwp"), ident["kind"]
    if not npwp and data.get("party_name"):
        ident = await _vendor_identity(org_id, data["party_name"])
        npwp = ident.get("npwp") or npwp
    return {"party_npwp": tid.digits(npwp) or None, "party_kind": kind}


async def issue(org_id, actor: str, data: dict) -> dict:
    """Terbitkan bukti potong. IDEMPOTEN per (dasar, referensi) supaya tidak lapor dobel."""
    basis = ref.make_validator("withholding_basis", required=True)(data.get("basis") or "manual")
    kind = ref.make_validator("withholding_kind", required=True)(data.get("kind"))
    ref_id = data.get("ref_id")
    if ref_id:
        existing = await db.withholding_docs.find_one(
            {"org_id": org_id, "basis": basis, "ref_id": ref_id,
             "state": {"$in": list(ALIVE)}}, {"_id": 0})
        if existing:
            return {**existing, "idempotent": True}
    base = int(data.get("base") or 0)
    if base <= 0:
        raise ValueError("Dasar pengenaan pajak harus lebih dari 0.")
    rate = float(data.get("rate") or 0)
    if rate <= 0:
        rate = await default_rate(org_id, kind)
    if rate <= 0:
        raise ValueError(f"Tarif {ref.label_of('withholding_kind', kind)} belum diisi dan belum "
                         "ada nilai bawaan di Pusat Konfigurasi → Pajak & Kepatuhan.")
    party = await _resolve_party(org_id, {**data, "basis": basis})
    date = str(data.get("date") or now_iso())[:10]
    ts = now_iso()
    amount = tax_of(base, rate)
    doc = {
        "id": new_id(), "org_id": org_id,
        "number": await next_number(org_id, date[:4]),
        "kind": kind, "basis": basis, "state": ISSUED, "version": 1,
        "party_name": (data.get("party_name") or "").strip(),
        "party_npwp": party["party_npwp"], "party_kind": party["party_kind"],
        "base": base, "rate": rate, "amount": amount,
        "object_code": data.get("object_code") or None,
        "ref_id": ref_id, "ref_label": data.get("ref_label"),
        "project_id": data.get("project_id"), "bill_id": data.get("bill_id"),
        "date": date, "period": date[:7], "note": data.get("note"),
        "history": [], "issued_by": actor, "issued_at": ts,
        "created_at": ts, "updated_at": ts,
    }
    await db.withholding_docs.insert_one(dict(doc))
    doc.pop("_id", None)
    logger.info("Bukti potong %s terbit: %s %s atas %s (%s)", doc["number"], kind,
                _rp(amount), doc["party_name"], basis)
    return {**doc, "idempotent": False}


async def issue_for_bill_payment(org_id, actor: str, *, bill: dict, payment: dict, kind: str,
                                 base: int, rate: float, object_code: str = None,
                                 note: str = None) -> dict:
    """Bukti potong otomatis atas pembayaran tagihan yang memotong PPh (dipakai router AP)."""
    return await issue(org_id, actor, {
        "basis": "ap_payment", "kind": kind, "base": base, "rate": rate,
        "party_name": bill.get("vendor"), "object_code": object_code,
        "ref_id": payment.get("id"), "bill_id": bill.get("id"),
        "ref_label": f"Pembayaran tagihan {bill.get('vendor')} "
                     f"({_rp(payment.get('amount'))})",
        "project_id": bill.get("project_id"),
        "date": str(payment.get("created_at") or now_iso())[:10], "note": note,
    })


async def issue_for_fee(org_id, actor: str, fee_id: str, object_code: str = None) -> dict:
    """Bukti potong atas PPh fee mitra yang SUDAH dipotong saat fee disetujui."""
    fee = await db.marketing_fees.find_one({"org_id": org_id, "id": fee_id}, {"_id": 0})
    if not fee:
        raise ValueError("Tagihan fee mitra tidak ditemukan.")
    if fee.get("status") not in ("approved", "paid"):
        raise ValueError("Fee mitra belum disetujui — belum ada potongan PPh yang bisa "
                         "dibuktikan.")
    pph = int(fee.get("pph_amount", 0) or 0)
    if pph <= 0:
        raise ValueError(f"Fee {fee.get('no')} tidak dipotong PPh — tidak ada bukti potong "
                         "yang perlu diterbitkan.")
    ident = await _agent_identity(org_id, fee.get("agent_id"))
    return await issue(org_id, actor, {
        "basis": "partner_fee",
        "kind": "pph23" if ident["kind"] == "company" else "pph21",
        "base": int(fee.get("amount_gross", 0) or 0), "rate": float(fee.get("pph_pct", 0) or 0),
        "party_name": fee.get("agent_name"), "party_npwp": ident.get("npwp"),
        "party_kind": ident["kind"], "agent_id": fee.get("agent_id"),
        "object_code": object_code, "ref_id": fee["id"],
        "ref_label": f"Fee mitra {fee.get('no')} — unit {fee.get('unit_code') or '-'}",
        "project_id": fee.get("project_id"),
        "date": str(fee.get("approved_at") or now_iso())[:10],
    })


async def correct(org_id, doc_id: str, actor: str, patch: dict) -> dict:
    """Pembetulan: NOMOR TETAP, versi naik, nilai lama disimpan di riwayat."""
    doc = await db.withholding_docs.find_one({"org_id": org_id, "id": doc_id}, {"_id": 0})
    if not doc:
        raise ValueError("Bukti potong tidak ditemukan.")
    if doc.get("state") == CANCELLED:
        raise ValueError(f"Bukti potong {doc['number']} sudah dibatalkan — terbitkan bukti baru "
                         "bila potongannya memang terjadi.")
    base = int(patch.get("base") or doc["base"])
    rate = float(patch.get("rate") or doc["rate"])
    if base <= 0 or rate <= 0:
        raise ValueError("Dasar dan tarif pembetulan harus lebih dari 0.")
    ts = now_iso()
    entry = {"version": int(doc.get("version", 1)), "base": doc["base"], "rate": doc["rate"],
             "amount": doc["amount"], "party_npwp": doc.get("party_npwp"),
             "object_code": doc.get("object_code"), "reason": patch.get("reason"),
             "actor": actor, "at": ts}
    upd = {
        "state": CORRECTED, "version": int(doc.get("version", 1)) + 1,
        "base": base, "rate": rate, "amount": tax_of(base, rate),
        "party_npwp": tid.digits(patch.get("party_npwp")) or doc.get("party_npwp"),
        "object_code": patch.get("object_code") or doc.get("object_code"),
        "corrected_by": actor, "corrected_at": ts, "correct_reason": patch.get("reason"),
        "updated_at": ts,
    }
    await db.withholding_docs.update_one({"org_id": org_id, "id": doc_id},
                                        {"$set": upd, "$push": {"history": entry}})
    return await db.withholding_docs.find_one({"org_id": org_id, "id": doc_id}, {"_id": 0})


async def cancel(org_id, doc_id: str, actor: str, reason: str) -> dict:
    doc = await db.withholding_docs.find_one({"org_id": org_id, "id": doc_id}, {"_id": 0})
    if not doc:
        raise ValueError("Bukti potong tidak ditemukan.")
    if doc.get("state") == CANCELLED:
        raise ValueError(f"Bukti potong {doc['number']} sudah dibatalkan.")
    ts = now_iso()
    await db.withholding_docs.update_one({"org_id": org_id, "id": doc_id}, {"$set": {
        "state": CANCELLED, "cancel_reason": reason, "cancelled_by": actor,
        "cancelled_at": ts, "updated_at": ts}})
    return await db.withholding_docs.find_one({"org_id": org_id, "id": doc_id}, {"_id": 0})


# =============================================================== daftar & tie-out
def _decorate(doc: dict) -> dict:
    state = doc.get("state") or ISSUED
    npwp = tid.npwp16(doc.get("party_npwp"), label="NPWP pihak dipotong")
    return {**doc,
            "state_label": ref.label_of("withholding_state", state),
            "kind_label": ref.label_of("withholding_kind", doc.get("kind")),
            "basis_label": ref.label_of("withholding_basis", doc.get("basis")),
            "npwp_ok": npwp["ok"], "npwp_note": npwp["reason"] or npwp["note"],
            "npwp_export": npwp["value"]}


async def list_docs(org_id=ORG_ID, period: str = None, kind: str = None,
                    state: str = None) -> dict:
    q = {"org_id": org_id}
    if period:
        q["period"] = period
    if kind:
        q["kind"] = kind
    if state:
        q["state"] = state
    rows = [_decorate(d) for d in await db.withholding_docs.find(q, {"_id": 0}).sort(
        "created_at", -1).to_list(5000)]
    alive = [r for r in rows if r.get("state") in ALIVE]
    act = await actual_deductions(org_id, period)
    issued_total = sum(r["amount"] for r in alive)
    by_kind = {}
    for r in alive:
        slot = by_kind.setdefault(r["kind"], {"kind": r["kind"],
                                              "label": ref.label_of("withholding_kind", r["kind"]),
                                              "count": 0, "base": 0, "amount": 0})
        slot["count"] += 1
        slot["base"] += int(r["base"])
        slot["amount"] += int(r["amount"])
    unproven = int(act["total"]) - issued_total
    return {
        "rows": rows,
        "summary": {
            "total": len(rows), "alive": len(alive),
            "cancelled": sum(1 for r in rows if r.get("state") == CANCELLED),
            "corrected": sum(1 for r in rows if r.get("state") == CORRECTED),
            "base": sum(int(r["base"]) for r in alive), "amount": issued_total,
            "incomplete_npwp": sum(1 for r in alive if not r["npwp_ok"]),
            "by_kind": sorted(by_kind.values(), key=lambda x: x["kind"]),
        },
        "tie_out": {
            "issued": issued_total, "actual": int(act["total"]),
            "unproven": unproven, "matches": unproven == 0,
            "detail": ("Semua potongan PPh yang terjadi sudah punya bukti potong."
                       if unproven == 0 else
                       (f"{_rp(unproven)} potongan PPh sudah dipotong tetapi BELUM diterbitkan "
                        "bukti potongnya — pihak yang dipotong tidak bisa mengkreditkannya."
                        if unproven > 0 else
                        f"Bukti potong melebihi potongan nyata sebesar {_rp(abs(unproven))} — "
                        "periksa bukti yang seharusnya dibatalkan.")),
        },
        "missing": [] if rows else ["bukti_potong"],
        "detail": ("Belum ada bukti potong pada masa ini." if not rows else
                   f"{len(alive)} bukti potong aktif senilai {_rp(issued_total)}."),
        "note": ("Nomor bukti potong TIDAK berubah saat dibetulkan (PER-24/PJ/2021); "
                 "bukti yang dibatalkan tidak boleh dipakai lagi."),
    }


# =============================================================== PDF & ekspor
def pdf_bytes(doc: dict, *, org_name: str, company_npwp: str = "", layout=None, images=None) -> bytes:
    from pdf_utils import build_document_pdf
    kind = ref.label_of("withholding_kind", doc.get("kind"))
    state = ref.label_of("withholding_state", doc.get("state") or ISSUED)
    content = (
        f"Jenis Pemotongan : {kind}\n"
        f"Masa Pajak : {doc.get('period') or '-'}\n"
        f"Tanggal : {doc.get('date') or '-'}\n"
        f"Status Bukti : {state} (versi {doc.get('version', 1)})\n\n"
        f"Pemotong : {org_name}\n"
        f"NPWP Pemotong : {company_npwp or '-'}\n\n"
        f"Pihak Dipotong : {doc.get('party_name') or '-'}\n"
        f"NPWP/NIK Dipotong : {tid.npwp16(doc.get('party_npwp'))['value'] or '-'}\n"
        f"Kode Objek Pajak : {doc.get('object_code') or '-'}\n\n"
        f"Dasar Pengenaan Pajak : {_rp(doc.get('base'))}\n"
        f"Tarif : {float(doc.get('rate') or 0):g}%\n"
        f"PPh Dipotong : {_rp(doc.get('amount'))}\n\n"
        f"Dasar Transaksi : {doc.get('ref_label') or '-'}\n"
    )
    if doc.get("state") == CANCELLED:
        content += f"\nDIBATALKAN : {doc.get('cancel_reason')} ({doc.get('cancelled_by')})\n"
    elif doc.get("state") == CORRECTED:
        content += f"\nPEMBETULAN : {doc.get('correct_reason')} ({doc.get('corrected_by')})\n"
    return build_document_pdf(
        title="Bukti Pemotongan PPh (e-Bupot)", doc_number=doc.get("number") or "-",
        content=content, org_name=org_name, layout=layout, images=images,
        script_context={"date": doc.get("date") or ""},
        signatures=[{"role": "Pemotong Pajak", "name": org_name}])


async def export_check(org_id=ORG_ID, period: str = None) -> dict:
    """Kesiapan ekspor SEBELUM berkas dibuat — layar memakai ini untuk menjelaskan sebab."""
    cfg = await config(org_id)
    data = await list_docs(org_id, period=period)
    alive = [r for r in data["rows"] if r.get("state") in ALIVE]
    blocking, warnings = [], []
    if not cfg["company_npwp_state"]["ok"]:
        blocking.append({"scope": "perusahaan", "number": None,
                         "reason": (cfg["company_npwp_state"]["reason"]
                                    + " Isi di Pusat Konfigurasi → Pajak & Kepatuhan.")})
    for r in alive:
        if not r["npwp_ok"]:
            blocking.append({"scope": "bukti", "number": r.get("number"),
                             "party_name": r.get("party_name"),
                             "reason": f"{r['npwp_note']} ({r.get('party_name') or '-'})."})
        if not r.get("object_code"):
            warnings.append({"number": r.get("number"), "party_name": r.get("party_name"),
                             "reason": ("Kode objek pajak belum diisi — Coretax menolak unggahan "
                                        "tanpa kode objek. Minta kodenya dari staf pajak lalu "
                                        "betulkan bukti ini.")})
    return {
        "period": period, "count": len(alive), "company": {
            "npwp": cfg["company_npwp"], "idtku": cfg["company_idtku"],
            "name": cfg["company_name"]},
        "amount": sum(r["amount"] for r in alive),
        "blocking": blocking, "warnings": warnings,
        "can_export": not blocking and bool(alive),
        "formats": list(ref.values("tax_export_format")),
        "detail": ("Belum ada bukti potong aktif pada masa ini — tidak ada yang bisa diekspor."
                   if not alive else
                   ("Siap diekspor." if not blocking else
                    f"{len(blocking)} data wajib belum lengkap — ekspor ditahan.")),
        "note": ("Berkas ini bahan unggah e-Bupot Unifikasi; periksa sekali di aplikasi DJP "
                 "sebelum dipakai massal."),
    }


def _xml(rows: list, company: dict) -> bytes:
    parts = ['<?xml version="1.0" encoding="UTF-8"?>', "<BuktiPotongBulk>",
             f"  <TIN>{escape(company['npwp'])}</TIN>", "  <ListOfBuktiPotong>"]
    for r in rows:
        parts += [
            "    <BuktiPotong>",
            f"      <NomorBuktiPotong>{escape(str(r.get('number') or ''))}</NomorBuktiPotong>",
            f"      <MasaPajak>{escape(str(r.get('period') or ''))}</MasaPajak>",
            f"      <TanggalPemotongan>{escape(str(r.get('date') or ''))}</TanggalPemotongan>",
            f"      <JenisPPh>{escape(str(r.get('kind') or ''))}</JenisPPh>",
            f"      <KodeObjekPajak>{escape(str(r.get('object_code') or ''))}</KodeObjekPajak>",
            f"      <NPWPPemotong>{escape(company['npwp'])}</NPWPPemotong>",
            f"      <IDTKUPemotong>{escape(company.get('idtku') or company['npwp'])}"
            "</IDTKUPemotong>",
            f"      <NPWPDipotong>{escape(str(r.get('npwp_export') or ''))}</NPWPDipotong>",
            f"      <NamaDipotong>{escape(str(r.get('party_name') or ''))}</NamaDipotong>",
            f"      <DasarPengenaanPajak>{int(r.get('base', 0) or 0)}</DasarPengenaanPajak>",
            f"      <TarifPersen>{float(r.get('rate') or 0):g}</TarifPersen>",
            f"      <PPhDipotong>{int(r.get('amount', 0) or 0)}</PPhDipotong>",
            f"      <StatusBukti>{escape(str(r.get('state') or ''))}</StatusBukti>",
            f"      <Versi>{int(r.get('version', 1) or 1)}</Versi>",
            f"      <Referensi>{escape(str(r.get('ref_label') or ''))}</Referensi>",
            "    </BuktiPotong>"]
    parts += ["  </ListOfBuktiPotong>", "</BuktiPotongBulk>", ""]
    return "\n".join(parts).encode("utf-8")


def _csv(rows: list, company: dict) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["NomorBuktiPotong", "MasaPajak", "Tanggal", "JenisPPh", "KodeObjekPajak",
                "NPWPPemotong", "NPWPDipotong", "NamaDipotong", "DPP", "Tarif", "PPh",
                "StatusBukti", "Versi", "Referensi"])
    for r in rows:
        w.writerow([r.get("number"), r.get("period"), r.get("date"), r.get("kind"),
                    r.get("object_code") or "", company["npwp"], r.get("npwp_export") or "",
                    r.get("party_name"), int(r.get("base", 0) or 0),
                    f"{float(r.get('rate') or 0):g}", int(r.get("amount", 0) or 0),
                    r.get("state"), int(r.get("version", 1) or 1), r.get("ref_label") or ""])
    return buf.getvalue().encode("utf-8-sig")


async def export_file(org_id=ORG_ID, period: str = None, fmt: str = "coretax_xml") -> tuple:
    """(nama_berkas, media_type, isi). MENAHAN bila `export_check` belum bersih."""
    fmt = ref.make_validator("tax_export_format", required=True)(fmt)
    chk = await export_check(org_id, period)
    if chk["blocking"]:
        raise ExportHold([b["reason"] for b in chk["blocking"]], chk["blocking"])
    if not chk["count"]:
        raise ExportHold(["Belum ada bukti potong aktif pada masa pajak ini — "
                          "tidak ada yang diekspor."])
    data = await list_docs(org_id, period=period)
    rows = [r for r in data["rows"] if r.get("state") in ALIVE]
    company = chk["company"]
    if fmt == "coretax_xml":
        return (f"ebupot-{period}.xml", "application/xml", _xml(rows, company))
    return (f"ebupot-{period}.csv", "text/csv", _csv(rows, company))


async def summary(org_id=ORG_ID, period: str = None) -> dict:
    """Ringkasan untuk kartu di layar Perpajakan (angka + kejujuran + kesiapan ekspor)."""
    data = await list_docs(org_id, period=period)
    cand = await candidates(org_id, period)
    chk = await export_check(org_id, period)
    return {"period": period, "summary": data["summary"], "tie_out": data["tie_out"],
            "candidates": cand["count"], "candidates_total": cand["total"],
            "can_export": chk["can_export"], "blocking": chk["blocking"],
            "warnings": chk["warnings"], "detail": data["detail"], "note": data["note"]}


async def periods(org_id=ORG_ID) -> list:
    """Masa pajak yang punya bukti potong ATAU punya potongan nyata (untuk pemilih masa)."""
    out = set(await db.withholding_docs.distinct("period", {"org_id": org_id}))
    act = await actual_deductions(org_id)
    out |= {r["period"] for r in act["rows"] if r.get("period")}
    return sorted((p for p in out if p), reverse=True)
