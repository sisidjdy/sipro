"""NASKAH DOKUMEN PER JENIS (Fase 66) — satu naskah untuk satu jenis dokumen.

## Cacat yang ditutup berkas ini

Sampai Fase 65 layar **Template Dokumen** terbelah dua: satu tab berisi daftar "isi
template" (naskah) yang bebas kodenya, satu tab lagi berisi "tampilan & kop surat" per
dokumen. Akibatnya:

  1. pemakai harus mengira-ngira naskah `SPR` yang mana yang dipakai dokumen `SPR_KPR`;
  2. naskah tidak pernah terlihat di PRATINJAU — pratinjau hanya menampilkan kop, jadi
     orang menyetel tampilan tanpa tahu isinya akan tercetak seperti apa;
  3. daftar naskah tidak tahu jenis dokumennya, sehingga placeholder yang ditawarkan sama
     untuk kwitansi, laporan, maupun surat peringatan — padahal datanya berbeda.

## Bentuk yang benar

Satu **jenis dokumen** (kode di `doc_layout.TARGETS`) memiliki SATU naskah, tersimpan di
koleksi yang sudah dipakai penerbit dokumen (`document_templates`) sehingga naskah yang
disunting di layar benar-benar naskah yang tercetak. Setiap jenis punya **kategori**, dan
kategori itu menentukan placeholder yang ditawarkan + naskah bawaannya.
"""
import re

from core_utils import new_id, now_iso
from db import db

# kategori naskah -> label
CATEGORIES = {
    "surat_pesanan": "Surat pesanan & pernyataan pembeli",
    "kontrak": "Perjanjian & akta",
    "berita_acara": "Berita acara",
    "kwitansi": "Kwitansi & pembayaran",
    "penawaran": "Penawaran harga",
    "pajak": "Dokumen pajak",
    "pihak_luar": "Dokumen pihak luar (SPK/PO)",
    "penagihan": "Penagihan & peringatan",
    "lapangan": "Dokumen lapangan",
    "laporan": "Laporan tabel",
    "lainnya": "Dokumen lain",
}

# kode dokumen -> kategori naskah (kode yang tidak terdaftar dianggap "lainnya")
CATEGORY_OF = {
    "SPR": "surat_pesanan", "SPR_CASH": "surat_pesanan",
    "SPR_CASH_STAGED": "surat_pesanan", "SPR_KPR": "surat_pesanan",
    "SPKT": "surat_pesanan",
    "PPJB": "kontrak", "AJB": "kontrak",
    "BAP": "berita_acara", "BAST": "berita_acara", "BA_OPNAME": "berita_acara",
    "KWITANSI": "kwitansi", "PENAWARAN": "penawaran",
    "BKM": "kwitansi", "BKK": "kwitansi",
    "FAKTUR": "pajak", "BUPOT": "pajak",
    "SPK": "pihak_luar", "PO": "pihak_luar",
    "SP": "penagihan", "INVOICE": "penagihan", "INVOICE_BF": "penagihan", "PUNCHLIST": "lapangan", "LAPORAN": "laporan",
}

# ------------------------------------------------------------------ kosakata placeholder
# Placeholder BUKAN karangan layar: daftarnya diambil dari konteks yang benar-benar diisi
# mesin penerbit dokumen. Kalau layar menawarkan token yang tidak pernah diisi, dokumen
# resmi akan tercetak dengan `{{apa_saja}}` mentah di tangan pembeli atau bank.
COMMON_TOKENS = ("doc_number", "date", "org_name", "sales_name")

# `docgen.build_context` — SPR (3 skema) & SPKT (Fase 53).
DOCGEN_TOKENS = (
    "doc_number", "intro", "customer_name", "customer_phone", "property_name",
    "property_address", "developer_name", "city", "unit_block", "unit_type_label",
    "building_area", "land_area", "selling_price", "dp_line", "booking_fee", "addon_rows",
    "kpr_cost_rows", "bphtb", "notary_fee", "pph_seller", "promo_discount", "discount_rows",
    "subtotal",
    "total", "total_note", "payment_terms", "ajb_clause", "shgb_months",
    "retention_months", "cut_before_build", "cut_during_build", "refund_clause",
    "refund_bi_fail", "refund_kpr_rejected", "forfeit_days", "document_date",
    "marketing_name", "spr_number_ref", "standard_land_area", "excess_land_m2",
    "excess_price_list", "excess_price_agreed", "excess_total", "excess_grand_total",
    "payoff_before_akad_clause", "template_code",
)
# `cancellation_engine` — Berita Acara Pembatalan & Refund.
BAP_TOKENS = (
    "doc_number", "developer_name", "property_name", "customer_name", "unit_block",
    "unit_type_label", "contract_number", "scheme_label", "cancel_number",
    "cancel_reason", "build_basis", "received_total", "cut_pct", "cut_amount",
    "refund_amount", "deposit_refund", "payable_total", "refund_clause", "rule_label",
    "decided_by", "decided_at", "money_note",
)
# `documents_router` — dokumen deal jalur lama (SPR/PPJB/AJB).
DEAL_TOKENS = (
    "doc_number", "date", "buyer_name", "buyer_phone", "project_name", "unit_code",
    "unit_type", "price", "booking_fee", "reserved_until", "sales_name", "org_name",
)
# `ar_router.invoice_pdf` — invoice/tagihan pembeli (DOC-02).
INVOICE_TOKENS = (
    "date", "org_name", "customer_name", "unit_code", "project_name", "total", "paid",
    "outstanding", "next_due", "status",
)
# `booking_fee_router.invoice_pdf` — tagihan booking fee.
INVOICE_BF_TOKENS = (
    "doc_number", "date", "org_name", "customer_name", "unit_code", "project_name", "booking_fee",
    "paid", "outstanding", "due_date", "status",
)

TOKENS_BY_CODE = {
    "SPR_CASH": DOCGEN_TOKENS, "SPR_CASH_STAGED": DOCGEN_TOKENS,
    "SPR_KPR": DOCGEN_TOKENS, "SPKT": DOCGEN_TOKENS,
    "BAP": BAP_TOKENS,
    "SPR": DEAL_TOKENS, "PPJB": DEAL_TOKENS, "AJB": DEAL_TOKENS,
    "INVOICE": INVOICE_TOKENS,
    "INVOICE_BF": INVOICE_BF_TOKENS,
}

# Naskah bawaan per KODE (menimpa naskah kategori) — invoice pembeli butuh kalimat yang
# menyebut siapa, unit apa, sudah bayar berapa, dan sisa berapa; bukan kalimat penagihan umum.
DEFAULTS_BY_CODE = {
    "INVOICE_BF": ("Kepada Yth. {{customer_name}}, berikut tagihan booking fee unit {{unit_code}} "
                   "{{project_name}} sebesar {{booking_fee}} (sudah dibayar {{paid}}, sisa {{outstanding}}), "
                   "jatuh tempo {{due_date}}. Booking fee dibayarkan saat keep unit dan dialihkan ke termin "
                   "setelah booking dikonfirmasi; ketentuan hangus/refund mengikuti SPR. Status: {{status}}."),
    "INVOICE": ("Kepada Yth. {{customer_name}}, berikut rincian tagihan pembayaran unit "
                "{{unit_code}} {{project_name}} per {{date}}. Total kewajiban {{total}}, sudah "
                "dibayar {{paid}}, sisa {{outstanding}}. Termin terdekat jatuh tempo {{next_due}}. "
                "Mohon melakukan pembayaran sebelum tanggal tersebut; hubungi {{org_name}} bila "
                "ada pertanyaan."),
}

LABELS = {
    "tabel_biaya": "Tabel biaya otomatis", "tabel_rincian": "Tabel rincian otomatis",
    "doc_number": "Nomor dokumen", "date": "Tanggal dokumen",
    "document_date": "Tanggal dokumen", "org_name": "Nama perusahaan",
    "developer_name": "Nama pengembang", "sales_name": "Nama penerbit",
    "marketing_name": "Nama pemasar", "intro": "Kalimat pembuka (dari skema)",
    "customer_name": "Nama pembeli", "buyer_name": "Nama pembeli",
    "customer_phone": "Telepon pembeli", "buyer_phone": "Telepon pembeli",
    "property_name": "Nama proyek", "project_name": "Nama proyek",
    "property_address": "Alamat proyek", "city": "Kota",
    "unit_block": "Blok/kode unit", "unit_code": "Blok/kode unit",
    "unit_type_label": "Tipe unit", "unit_type": "Tipe unit",
    "building_area": "Luas bangunan", "land_area": "Luas tanah",
    "selling_price": "Harga jual", "price": "Harga", "dp_line": "Baris uang muka",
    "booking_fee": "Booking fee", "addon_rows": "Baris spek tambahan",
    "kpr_cost_rows": "Baris biaya KPR", "bphtb": "BPHTB", "notary_fee": "Biaya notaris",
    "pph_seller": "PPh penjual", "promo_discount": "Potongan promo",
    "discount_rows": "Rincian potongan per sasaran (harga/DP/booking fee/biaya)",
    "subtotal": "Subtotal", "total": "Total kewajiban", "total_note": "Catatan total",
    "payment_terms": "Jadwal pembayaran", "ajb_clause": "Pasal AJB",
    "shgb_months": "Masa SHGB (bulan)", "retention_months": "Masa retensi (bulan)",
    "cut_before_build": "Potongan sebelum bangun",
    "cut_during_build": "Potongan saat bangun", "refund_clause": "Pasal refund",
    "refund_bi_fail": "Pasal refund BI checking", "reserved_until": "Batas booking",
    "refund_kpr_rejected": "Pasal refund KPR ditolak",
    "forfeit_days": "Hari hangus", "spr_number_ref": "Nomor SPR acuan",
    "standard_land_area": "Luas tanah standar", "excess_land_m2": "Kelebihan tanah (m2)",
    "excess_price_list": "Harga kelebihan (list)",
    "excess_price_agreed": "Harga kelebihan (sepakat)",
    "excess_total": "Total kelebihan tanah", "excess_grand_total": "Total keseluruhan",
    "payoff_before_akad_clause": "Pasal pelunasan sebelum akad",
    "template_code": "Kode template", "contract_number": "Nomor kontrak",
    "scheme_label": "Skema pembayaran", "cancel_number": "Nomor pembatalan",
    "cancel_reason": "Alasan pembatalan", "build_basis": "Dasar tahap bangun",
    "received_total": "Total diterima", "cut_pct": "Persen potongan",
    "cut_amount": "Nilai potongan", "refund_amount": "Nilai refund",
    "deposit_refund": "Refund deposit", "payable_total": "Total dibayarkan",
    "rule_label": "Aturan yang dipakai", "decided_by": "Diputuskan oleh",
    "decided_at": "Tanggal keputusan", "money_note": "Catatan angka",
}
SAMPLES = {
    "discount_rows": "  - Promo potongan uang muka (dipotong dari uang muka / DP) : Rp 5.000.000\n",
    "doc_number": "0001/SPR-KPR/CTH/VIII/2026", "date": "26 Agustus 2026",
    "document_date": "26 Agustus 2026", "org_name": "PT SIPRO Land",
    "developer_name": "PT SIPRO Land", "sales_name": "Andi Sales",
    "marketing_name": "Andi Sales", "customer_name": "Ibu Dewi Kartika",
    "buyer_name": "Ibu Dewi Kartika", "customer_phone": "0812-1111-1111",
    "buyer_phone": "0812-1111-1111", "property_name": "Cluster Asri Harmony Land",
    "project_name": "Cluster Asri Harmony Land",
    "property_address": "Jl. Melati No. 12, Bandung", "city": "Bandung",
    "unit_block": "A-01", "unit_code": "A-01", "unit_type_label": "tipe 45/90",
    "unit_type": "45/90", "building_area": "45 m2", "land_area": "90 m2",
    "selling_price": "Rp 825.000.000", "price": "825.000.000",
    "booking_fee": "Rp 5.000.000", "total": "Rp 867.125.000",
    "reserved_until": "2026-09-09",
    "intro": "Menindaklanjuti pembelian rumah atas nama:",
    "paid": "Rp 50.000.000", "outstanding": "Rp 817.125.000", "next_due": "10 September 2026",
    "status": "Sebagian dibayar",
}

# Naskah bawaan per kategori — hanya memakai placeholder yang SAH di semua jenis dokumen
# (COMMON), jadi naskah bawaan tidak pernah menghasilkan token mentah.
DEFAULTS = {
    "surat_pesanan": ("Yang bertanda tangan di bawah ini menyatakan memesan unit dengan "
                      "rincian sebagaimana tercantum pada dokumen nomor {{doc_number}} "
                      "tanggal {{date}}."),
    "kontrak": ("Pada hari ini, {{date}}, dibuat perjanjian oleh {{org_name}} dengan "
                "rincian sebagaimana tercantum pada dokumen nomor {{doc_number}}."),
    "berita_acara": ("Pada hari ini, {{date}}, telah dilakukan pemeriksaan bersama dengan "
                     "hasil sebagaimana tercantum pada dokumen nomor {{doc_number}}."),
    "kwitansi": ("Kwitansi nomor {{doc_number}} tanggal {{date}}, diterbitkan oleh "
                 "{{org_name}}."),
    "penawaran": ("{{org_name}} menyampaikan penawaran nomor {{doc_number}} tanggal "
                  "{{date}} dengan rincian sebagai berikut."),
    "pajak": "Dokumen pajak nomor {{doc_number}} tanggal {{date}} — {{org_name}}.",
    "pihak_luar": ("Sehubungan dengan pekerjaan yang diberikan {{org_name}}, dokumen nomor "
                   "{{doc_number}} tanggal {{date}} berlaku dengan rincian di bawah."),
    "penagihan": ("Berdasarkan catatan pembukuan {{org_name}} sampai {{date}}, terdapat "
                  "kewajiban yang belum diselesaikan dengan rincian di bawah."),
    "lapangan": ("Pemeriksaan lapangan tanggal {{date}} dengan hasil sebagaimana tercantum "
                 "pada dokumen nomor {{doc_number}}."),
    "laporan": "Laporan yang diterbitkan {{org_name}} pada {{date}}.",
    "lainnya": "",
}

TOKEN = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")


def category_of(code: str) -> str:
    return CATEGORY_OF.get(code, "lainnya")


def tokens_for(code: str) -> tuple:
    return TOKENS_BY_CODE.get(code, COMMON_TOKENS) + ("tabel_biaya", "tabel_rincian")


def placeholders_for(code: str) -> list:
    return [{"token": tok, "label": LABELS.get(tok, tok.replace("_", " ")),
             "sample": SAMPLES.get(tok, f"(contoh {tok.replace('_', ' ')})")}
            for tok in tokens_for(code)]


def known_tokens(code: str) -> set:
    return {p["token"] for p in placeholders_for(code)}


def default_script(code: str) -> str:
    return DEFAULTS_BY_CODE.get(code) or DEFAULTS.get(category_of(code), "")


def unknown_tokens(code: str, content: str) -> list:
    """Placeholder yang TIDAK akan pernah terisi — dilaporkan, bukan dibiarkan tercetak
    sebagai `{{apa_saja}}` di dokumen resmi yang dipegang pembeli/bank."""
    dikenal = known_tokens(code)
    return sorted({t for t in TOKEN.findall(content or "") if t not in dikenal})


def render(content: str, ctx: dict) -> str:
    from document_richtext import substitute
    return substitute(content, ctx)


def sample_script(code: str, content: str) -> str:
    """Naskah dengan nilai CONTOH — dipakai pratinjau supaya isi dokumen ikut terlihat."""
    ctx = {p["token"]: p["sample"] for p in placeholders_for(code)}
    return render(content, ctx)


def pdf_intro(layout, context=None):
    """System-composed PDFs previously used the letterhead but silently ignored their script."""
    from datetime import datetime
    from zoneinfo import ZoneInfo
    ctx = {"doc_number": "", "date": datetime.now(ZoneInfo("Asia/Jakarta")).strftime("%d-%m-%Y"),
           "org_name": (layout.get("brand") or {}).get("company_name") or "",
           "sales_name": ""}
    ctx.update(context or {})
    return render(layout.get("_script_content") or "", ctx)


async def intro_for(org: str, code: str, ctx: dict = None, *, use_default: bool = False) -> str:
    """Naskah yang DITULIS pemakai untuk jenis dokumen ini, siap ditempel ke dokumennya.

    Dipakai dokumen yang isinya dirakit sistem (SPK, PO, Surat Peringatan, berita acara
    lapangan): naskah pemakai tercetak sebagai pembuka DI ATAS rincian yang dihitung mesin —
    inilah yang membuat "naskah masuk ke dalam dokumen", bukan hidup di layar konfigurasi
    saja. Bila pemakai belum menulis apa pun, tidak ada yang ditempel (bukan naskah bawaan
    yang dipaksakan ke dokumen resmi) — kecuali `use_default=True` (invoice: naskah bawaan
    per kode memang dirancang untuk dicetak).
    """
    tpl = await db.document_templates.find_one({"org_id": org, "code": code},
                                              {"_id": 0, "content": 1, "is_active": 1})
    isi = ((tpl or {}).get("content") or "").strip()
    if (tpl or {}).get("is_active") is False:
        return ""
    if not isi:
        if not use_default:
            return ""
        isi = default_script(code)
    return render(isi, ctx or {})


async def get_script(org: str, code: str, *, label: str = None) -> dict:
    tpl = await db.document_templates.find_one({"org_id": org, "code": code}, {"_id": 0})
    kat = category_of(code)
    return {
        "code": code, "category": kat, "category_label": CATEGORIES[kat],
        "name": (tpl or {}).get("name") or label or code,
        "content": (tpl or {}).get("content") or default_script(code),
        "default_content": default_script(code),
        "customized": bool(tpl and (tpl.get("content") or "").strip()),
        "is_active": (tpl or {}).get("is_active", True),
        "updated_at": (tpl or {}).get("updated_at"),
        "placeholders": placeholders_for(code),
        "unknown_tokens": unknown_tokens(code, (tpl or {}).get("content") or ""),
    }


async def save_script(org: str, code: str, content: str, actor: str,
                      *, name: str = None) -> dict:
    from document_richtext import sanitize
    content = sanitize(content)
    salah = unknown_tokens(code, content)
    if salah:
        raise ValueError(
            "Placeholder tidak dikenal untuk jenis dokumen ini: "
            + ", ".join("{{" + t + "}}" for t in salah)
            + ". Pakai daftar placeholder yang tersedia agar tidak tercetak mentah.")
    ts = now_iso()
    cur = await db.document_templates.find_one({"org_id": org, "code": code}, {"_id": 0})
    upd = {"content": content, "category": category_of(code), "updated_at": ts,
           "updated_by": actor}
    if name:
        upd["name"] = name
    if cur:
        await db.document_templates.update_one({"id": cur["id"]}, {"$set": upd})
    else:
        await db.document_templates.insert_one(
            {"id": new_id(), "org_id": org, "code": code, "name": name or code,
             "is_active": True, "created_by": actor, "created_at": ts, **upd})
    return await get_script(org, code, label=name)
