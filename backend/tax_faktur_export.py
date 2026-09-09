"""Faktur pajak keluaran v2 (Fase 49E) — pengganti, pembatalan, dan EKSPOR berkas.

Tiga cacat nyata yang ditutup:

1. **Faktur sekali terbit dianggap selamanya benar.** Tidak ada faktur PENGGANTI dan tidak ada
   PEMBATALAN, padahal salah NPWP/nilai adalah kejadian sehari-hari. Sekarang: pengganti
   memakai nomor baru dengan status faktur `1` (kode transaksi berakhiran 1) dan berjejak ke
   nomor lama; pembatalan wajib beralasan dan langsung mengeluarkan faktur itu dari rekap
   SPT Masa PPN.
2. **Tidak ada jalan keluar data.** Faktur hanya bisa dilihat/PDF satu-satu; untuk melapor,
   staf mengetik ulang ke Coretax. Sekarang ada ekspor per masa pajak: **XML** (mengikuti
   struktur template resmi Coretax: `TaxInvoiceBulk` → `TaxInvoice` → `ListOfGoodService`) dan
   **CSV** untuk ditempel ke template Excel sebelum dikonversi.
3. **Ekspor yang berbohong.** Berkas tidak boleh dibuat dengan kolom identitas kosong: NPWP
   pembeli wajib 16 digit (Coretax) dan NPWP perusahaan wajib diisi di Pusat Konfigurasi.
   Bila belum lengkap, ekspor **DITAHAN** dan menyebut faktur mana yang harus dilengkapi.

Uang IDR integer; waktu UTC ISO-8601.
"""
import csv
import io
import logging
import re
from xml.sax.saxutils import escape

import reference as ref
import settings_store as st
import tax_engine as te
import tax_ids as tid
from core_utils import new_id, now_iso
from db import db, ORG_ID

logger = logging.getLogger("sipro.tax.faktur")

DIGITS = re.compile(r"\D")
NPWP_LEN = 16
ACTIVE = "issued"


class ExportHold(Exception):
    """Ekspor ditahan: ada data wajib yang belum lengkap."""

    def __init__(self, reasons: list, rows: list = None):
        self.reasons = reasons
        self.rows = rows or []
        super().__init__(" ".join(reasons))


def npwp_digits(value) -> str:
    return tid.digits(value)


def npwp_state(value) -> tuple:
    """(ok, detail) — satu aturan identitas pajak untuk seluruh Fase 49 (`tax_ids.npwp16`).

    Semula modul ini MENOLAK NPWP 15 digit lama sambil menuliskan sendiri cara
    memperbaikinya ("tulis 0 di depan") — padahal pemetaan itu justru yang ditetapkan
    PMK 112/PMK.03/2022, dan modul bukti potong (49F) memakai aturan yang berbeda untuk
    data yang sama. Dua aturan untuk satu hal = layar dan berkas bisa saling
    bertentangan. Sekarang keduanya memanggil `tax_ids`: 15 digit dinormalkan dengan
    catatan yang terbaca, dan hanya identitas kosong/panjang aneh yang menahan ekspor.
    """
    res = tid.npwp16(value, label="NPWP pembeli")
    return res["ok"], (res["reason"] or res["note"])


def npwp_export(value) -> str:
    """Bentuk 16 digit yang ditulis ke berkas (kosong bila belum sah)."""
    return tid.npwp16(value)["value"]


def _rp(n) -> str:
    return "Rp " + f"{int(n or 0):,}".replace(",", ".")


async def _company(org_id) -> dict:
    npwp = await st.get("tax.company_npwp", org_id=org_id)
    idtku = await st.get("tax.company_idtku", org_id=org_id)
    orgdoc = await db.orgs.find_one({"id": org_id}, {"_id": 0, "name": 1}) or {}
    state = tid.npwp16(npwp, label="NPWP perusahaan")
    return {"npwp": state["value"], "npwp_state": state, "idtku": str(idtku or ""),
            "name": orgdoc.get("name") or "PT SIPRO Land"}


async def list_faktur(org_id=ORG_ID, period: str = None, status: str = None) -> dict:
    q = {"org_id": org_id}
    if period:
        q["period"] = period
    if status:
        q["status"] = status
    rows = await db.faktur_pajak.find(q, {"_id": 0}).sort("created_at", -1).to_list(2000)
    for r in rows:
        ok, detail = npwp_state(r.get("buyer_npwp"))
        r["npwp_ok"] = ok
        r["npwp_note"] = detail
        r["status_label"] = ref.label_of("faktur_state", r.get("status") or ACTIVE)
    active = [r for r in rows if (r.get("status") or ACTIVE) == ACTIVE]
    return {"rows": rows, "summary": {
        "total": len(rows), "active": len(active),
        "replaced": sum(1 for r in rows if r.get("status") == "replaced"),
        "cancelled": sum(1 for r in rows if r.get("status") == "cancelled"),
        "dpp": sum(int(r.get("dpp", 0) or 0) for r in active),
        "ppn": sum(int(r.get("ppn", 0) or 0) for r in active),
        "incomplete": sum(1 for r in active if not r["npwp_ok"]),
    }}


async def replace_faktur(org_id, faktur_id: str, actor: str, reason: str,
                         buyer_npwp: str = None, buyer_name: str = None,
                         dpp: int = None) -> dict:
    """Terbitkan faktur PENGGANTI: nomor baru, faktur lama ditandai `replaced`.

    URUTAN PENTING (cacat yang ditemukan POC Fase 49): `faktur_pajak` memakai indeks UNIK
    (org_id, deal_id) — jadi menyisipkan faktur pengganti lebih dulu membuat DUA faktur untuk
    satu deal dan MongoDB menolaknya (500 duplicate key). Faktur lama karena itu ditandai
    `replaced` LEBIH DULU (indeks uniknya kini hanya berlaku untuk faktur berstatus `issued`),
    baru penggantinya disisipkan. Nomor & id pengganti dibuat sebelum penandaan supaya jejak
    dua arah (lama → pengganti, pengganti → lama) tidak pernah setengah jalan.
    """
    old = await db.faktur_pajak.find_one({"org_id": org_id, "id": faktur_id}, {"_id": 0})
    if not old:
        raise ValueError("Faktur pajak tidak ditemukan.")
    status = old.get("status") or ACTIVE
    if status == "cancelled":
        raise ValueError("Faktur yang sudah DIBATALKAN tidak bisa diganti — terbitkan faktur baru.")
    if status == "replaced":
        raise ValueError(f"Faktur ini sudah diganti oleh {old.get('replaced_by_number')}.")
    code = str(old.get("transaction_code") or "010")
    new_code = code[:2] + "1"  # status faktur 1 = pengganti (skema DJP)
    ppn_rate = float(old.get("ppn_rate") or 0)
    base = int(dpp if dpp is not None else old.get("dpp", 0) or 0)
    ts = now_iso()
    doc = {
        **{k: v for k, v in old.items() if k not in ("id", "number", "status", "created_at")},
        "id": new_id(),
        "number": await te.next_faktur_number(org_id, new_code),
        "transaction_code": new_code,
        "buyer_npwp": npwp_digits(buyer_npwp) or old.get("buyer_npwp"),
        "buyer_name": buyer_name or old.get("buyer_name"),
        "dpp": base, "ppn": round(base * ppn_rate / 100),
        "status": ACTIVE, "replaces_id": old["id"], "replaces_number": old.get("number"),
        "replace_reason": reason, "issued_by": actor, "issued_at": ts,
        "period": te.period_of(ts), "created_at": ts, "updated_at": ts,
    }
    await db.faktur_pajak.update_one({"id": old["id"], "org_id": org_id}, {"$set": {
        "status": "replaced", "replaced_by_id": doc["id"], "replaced_by_number": doc["number"],
        "replaced_reason": reason, "replaced_by": actor, "replaced_at": ts, "updated_at": ts}})
    await db.faktur_pajak.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


async def cancel_faktur(org_id, faktur_id: str, actor: str, reason: str) -> dict:
    fak = await db.faktur_pajak.find_one({"org_id": org_id, "id": faktur_id}, {"_id": 0})
    if not fak:
        raise ValueError("Faktur pajak tidak ditemukan.")
    status = fak.get("status") or ACTIVE
    if status == "cancelled":
        raise ValueError("Faktur ini sudah dibatalkan.")
    if status == "replaced":
        raise ValueError(f"Faktur ini sudah diganti oleh {fak.get('replaced_by_number')} — "
                         "batalkan faktur penggantinya bila transaksinya memang batal.")
    ts = now_iso()
    await db.faktur_pajak.update_one({"id": faktur_id, "org_id": org_id}, {"$set": {
        "status": "cancelled", "cancel_reason": reason, "cancelled_by": actor,
        "cancelled_at": ts, "updated_at": ts}})
    return await db.faktur_pajak.find_one({"id": faktur_id, "org_id": org_id}, {"_id": 0})


# =============================================================== ekspor
async def export_check(org_id=ORG_ID, period: str = None) -> dict:
    """Periksa kesiapan ekspor SEBELUM berkas dibuat (dipakai layar & endpoint ekspor)."""
    company = await _company(org_id)
    data = await list_faktur(org_id, period=period, status=ACTIVE)
    rows = data["rows"]
    blocking = []
    if not company["npwp_state"]["ok"]:
        blocking.append({"scope": "perusahaan", "number": None,
                         "reason": (company["npwp_state"]["reason"]
                                    + " Isi di Pusat Konfigurasi → Pajak & Kepatuhan — berkas "
                                    "ekspor tidak boleh dibuat tanpa identitas pemungut.")})
    notes = []
    if company["npwp_state"].get("note"):
        notes.append(company["npwp_state"]["note"])
    for r in rows:
        if not r["npwp_ok"]:
            blocking.append({"scope": "faktur", "number": r.get("number"),
                             "buyer_name": r.get("buyer_name"),
                             "reason": f"{r['npwp_note']} — lengkapi di data pelanggan."})
        elif r.get("npwp_note"):
            notes.append(f"{r.get('number')}: {r['npwp_note']}")
    return {
        "period": period, "count": len(rows), "company": company,
        "dpp": data["summary"]["dpp"], "ppn": data["summary"]["ppn"],
        "blocking": blocking, "can_export": not blocking and bool(rows),
        "normalized": notes,
        "formats": list(ref.values("tax_export_format")),
        "detail": ("Belum ada faktur aktif pada masa ini — tidak ada yang bisa diekspor."
                   if not rows else
                   ("Siap diekspor." if not blocking else
                    f"{len(blocking)} data wajib belum lengkap — ekspor ditahan.")),
        "note": ("Struktur XML mengikuti template resmi Coretax (Faktur + DetailFaktur). "
                 "Unggah lewat menu Faktur Keluaran → Impor Data, dan periksa XML Monitoring "
                 "sekali sebelum dipakai massal."),
    }


def _xml(rows: list, company: dict) -> bytes:
    parts = ['<?xml version="1.0" encoding="UTF-8"?>', "<TaxInvoiceBulk>",
             f"  <TIN>{escape(company['npwp'])}</TIN>", "  <ListOfTaxInvoice>"]
    for r in rows:
        dpp, ppn = int(r.get("dpp", 0) or 0), int(r.get("ppn", 0) or 0)
        rate = float(r.get("ppn_rate") or 0)
        name = escape(str(r.get("unit_code") or "Unit properti"))
        parts += [
            "    <TaxInvoice>",
            f"      <TaxInvoiceDate>{str(r.get('issued_at') or '')[:10]}</TaxInvoiceDate>",
            "      <TaxInvoiceOpt>Normal</TaxInvoiceOpt>",
            f"      <TrxCode>{escape(str(r.get('transaction_code') or '010')[:2])}</TrxCode>",
            f"      <RefDesc>{escape(str(r.get('number') or ''))}</RefDesc>",
            f"      <SellerIDTKU>{escape(company.get('idtku') or company['npwp'])}</SellerIDTKU>",
            f"      <BuyerTin>{escape(npwp_export(r.get('buyer_npwp')))}</BuyerTin>",
            "      <BuyerDocument>TIN</BuyerDocument>",
            f"      <BuyerName>{escape(str(r.get('buyer_name') or ''))}</BuyerName>",
            f"      <BuyerIDTKU>{escape(npwp_export(r.get('buyer_npwp')))}</BuyerIDTKU>",
            "      <ListOfGoodService>", "        <GoodService>",
            "          <Opt>B</Opt>", f"          <Name>{name}</Name>",
            f"          <Price>{dpp}</Price>", "          <Qty>1</Qty>",
            "          <TotalDiscount>0</TotalDiscount>",
            f"          <TaxBase>{dpp}</TaxBase>",
            f"          <VATRate>{rate:g}</VATRate>", f"          <VAT>{ppn}</VAT>",
            "          <STLGRate>0</STLGRate>", "          <STLG>0</STLG>",
            "        </GoodService>", "      </ListOfGoodService>", "    </TaxInvoice>"]
    parts += ["  </ListOfTaxInvoice>", "</TaxInvoiceBulk>", ""]
    return "\n".join(parts).encode("utf-8")


def _csv(rows: list, company: dict) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["NomorFaktur", "TanggalFaktur", "KodeTransaksi", "NPWPPenjual", "NPWPPembeli",
                "NamaPembeli", "Referensi", "NamaBarangJasa", "DPP", "TarifPPN", "PPN"])
    for r in rows:
        w.writerow([r.get("number"), str(r.get("issued_at") or "")[:10],
                    str(r.get("transaction_code") or "010"), company["npwp"],
                    npwp_export(r.get("buyer_npwp")), r.get("buyer_name"),
                    r.get("unit_code") or "", r.get("unit_code") or "Unit properti",
                    int(r.get("dpp", 0) or 0), f"{float(r.get('ppn_rate') or 0):g}",
                    int(r.get("ppn", 0) or 0)])
    return buf.getvalue().encode("utf-8-sig")


async def export_file(org_id=ORG_ID, period: str = None, fmt: str = "coretax_xml") -> tuple:
    """(nama_berkas, media_type, isi). MENAHAN bila `export_check` belum bersih."""
    fmt = ref.make_validator("tax_export_format", required=True)(fmt)
    chk = await export_check(org_id, period)
    if chk["blocking"]:
        raise ExportHold([b["reason"] for b in chk["blocking"]], chk["blocking"])
    if not chk["count"]:
        raise ExportHold(["Belum ada faktur aktif pada masa pajak ini — tidak ada yang diekspor."])
    rows = (await list_faktur(org_id, period=period, status=ACTIVE))["rows"]
    company = chk["company"]
    if fmt == "coretax_xml":
        return (f"efaktur-{period}.xml", "application/xml", _xml(rows, company))
    return (f"efaktur-{period}.csv", "text/csv", _csv(rows, company))


# =============================================================== rekap SPT Masa PPN
async def vat_return(org_id=ORG_ID, period: str = None) -> dict:
    """Rekap SPT Masa PPN yang bisa DIREKONSTRUKSI dari faktur & PPN masukan periode itu.

    Faktur diambil TANPA saringan status: nilai PPN keluaran hanya menjumlahkan faktur yang
    masih berlaku (`issued`), tetapi jumlah faktur yang DIBATALKAN dan DIGANTI tetap harus
    terbaca. Sebelum perbaikan ini daftarnya disaring `status=issued` lebih dulu, sehingga
    "faktur dibatalkan" dan "faktur diganti" SELALU nol — pembaca tidak pernah tahu ada
    faktur yang dikeluarkan dari rekap, padahal justru itu yang membuat angkanya berubah.
    """
    fak = await list_faktur(org_id, period=period)
    keluaran = fak["summary"]["ppn"]
    dpp_keluaran = fak["summary"]["dpp"]
    inp = await te.ppn_input(org_id, period)
    masukan = int(inp["ppn"])
    net = keluaran - masukan
    recs = await db.tax_records.find({"org_id": org_id, "type": "ppn"}, {"_id": 0}).to_list(5000)
    recs = [r for r in recs if te.period_of(r.get("created_at")) == period]
    setor = sum(int(r.get("amount", 0) or 0) for r in recs if r.get("status") == "paid")
    belum = sum(int(r.get("amount", 0) or 0) for r in recs if r.get("status") != "paid")
    has_data = bool(fak["rows"] or inp["count"] or recs)
    state = ("missing_data" if not has_data else
             ("kurang_bayar" if net > 0 else ("lebih_bayar" if net < 0 else "nihil")))
    return {
        "period": period, "state": state, "state_label": ref.label_of("vat_return_state", state),
        "ppn_keluaran": keluaran, "dpp_keluaran": dpp_keluaran,
        "faktur_count": fak["summary"]["active"],
        "faktur_cancelled": fak["summary"]["cancelled"],
        "faktur_replaced": fak["summary"]["replaced"],
        "ppn_masukan": masukan, "dpp_masukan": int(inp["dpp"]),
        "masukan_count": int(inp["count"]), "ppn_rate": inp["rate"],
        "net": net, "sudah_disetor": setor, "belum_disetor": belum,
        "missing": [] if has_data else ["faktur", "ppn_masukan"],
        "detail": ("Belum ada faktur keluaran maupun tagihan masukan pada masa ini — "
                   "belum ada data, bukan nihil." if not has_data else
                   (f"PPN keluaran {_rp(keluaran)} − masukan {_rp(masukan)} = "
                    f"{_rp(abs(net))} {'kurang bayar' if net > 0 else 'lebih bayar' if net < 0 else 'nihil'}.")),
        "reconstruct": ("Keluaran = Σ PPN faktur berstatus terbit pada masa ini (faktur batal & "
                        "diganti tidak dihitung). Masukan = estimasi inklusif dari tagihan "
                        "vendor: DPP = tagihan × 100/(100+tarif)."),
        "note": te.TAX_NOTE,
    }
