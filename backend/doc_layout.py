"""KONFIGURASI TAMPILAN DOKUMEN (Fase 60) — kop surat, footer, baris biaya, tanda tangan.

## Cacat yang ditutup berkas ini

Sampai Fase 59 setiap dokumen yang keluar dari sistem ini adalah teks polos: **tanpa kop
surat, tanpa logo, tanpa footer identitas perusahaan, tanpa kolom tanda tangan yang jelas,
tanpa materai/tempat-tanggal**, dan baris biaya selalu tercetak semua — termasuk komponen
yang bernilai Rp 0 yang justru membingungkan pembeli. Dokumen seperti itu tidak layak
diserahkan kepada pembeli, bank, maupun notaris, dan tidak bisa disesuaikan tiap pengembang
tanpa mengubah kode — padahal ini SaaS.

## Bentuk konfigurasinya

Satu dokumen `document_layouts` per (organisasi, kode). Kode `__default__` adalah **identitas
perusahaan & gaya bawaan** yang dipakai SEMUA dokumen; kode template (`SPR_KPR`, `BAST`,
`KWITANSI`, `LAPORAN`, …) hanya menyimpan **yang berbeda** dari bawaan itu. Jadi mengganti
logo satu kali mengubah semua dokumen, tetapi kolom tanda tangan SPR tetap boleh berbeda
dari BAST.

## Aturan yang dipegang

1. **Tidak ada gaya mati di kode.** Semua yang bisa dilihat pemakai (warna aksen, margin,
   kop, footer, watermark, urutan & label baris biaya, kolom tanda tangan) tinggal di sini.
2. **Angka tetap milik mesinnya.** Konfigurasi boleh MENYEMBUNYIKAN, MENGURUTKAN, dan
   MENAMAI baris — tidak boleh mengubah nilainya. Baris tambahan manual ditandai
   `manual: true` supaya auditor tahu itu diketik orang, bukan hasil hitungan sistem.
3. **`hide_if_zero` bukan pembohongan.** Yang disembunyikan hanya baris bernilai NOL; baris
   yang nilainya BELUM DIKETAHUI tetap tercetak dengan kalimat "belum ditetapkan" (aturan
   lama aplikasi ini: jangan pernah menulis Rp 0 untuk data yang tidak ada).
4. **Pratinjau memakai mesin cetak yang SAMA** dengan dokumen sungguhan. Pratinjau yang
   dirender jalur lain adalah pratinjau yang boleh berbohong.
"""
import logging

import storage
from core_utils import new_id, now_iso
from db import ORG_ID, ORG_NAME, db

logger = logging.getLogger("sipro.doc_layout")

DEFAULT_CODE = "__default__"

# Dokumen yang memakai konfigurasi ini. `kind` menentukan bentuk pratinjaunya.
TARGETS = {
    DEFAULT_CODE: ("Bawaan seluruh dokumen (identitas & gaya)", "letter"),
    "SPR": ("Surat Pemesanan Rumah (SPR)", "letter"),
    "SPR_CASH": ("Surat Pesanan Rumah — Cash Keras", "letter"),
    "SPR_CASH_STAGED": ("Surat Pesanan Rumah — Cash Bertahap", "letter"),
    "SPR_KPR": ("Surat Pesanan Rumah — KPR", "letter"),
    "PPJB": ("Perjanjian Pengikatan Jual Beli (PPJB)", "letter"),
    "AJB": ("Akta Jual Beli (AJB)", "letter"),
    "SPKT": ("Surat Pernyataan Kelebihan Tanah", "letter"),
    "ADENDUM_SPR": ("Adendum SPR — Perubahan Skema Pembayaran", "letter"),
    "BAP": ("Berita Acara Pembatalan & Refund", "letter"),
    "BAST": ("Berita Acara Serah Terima unit", "letter"),
    "KWITANSI": ("Kwitansi penerimaan pembayaran", "letter"),
    "BKM": ("Bukti Kas Masuk (BKM)", "letter"),
    "BKK": ("Bukti Kas Keluar (BKK)", "letter"),
    "PENAWARAN": ("Penawaran harga unit", "letter"),
    "FAKTUR": ("Faktur pajak", "letter"),
    "BUPOT": ("Bukti potong PPh", "letter"),
    # Fase 61 — dua dokumen yang dipegang PIHAK LUAR (subkontraktor & vendor).
    "SPK": ("Surat Perintah Kerja subkontraktor — SPK", "letter"),
    "PO": ("Purchase Order pengadaan — PO", "letter"),
    # Fase 62 — dokumen penagihan & lapangan yang ditandatangani di luar kantor.
    "SP": ("Surat Peringatan tunggakan (SP1/SP2/SP3)", "letter"),
    "BA_OPNAME": ("Berita Acara Opname pekerjaan subkontraktor", "letter"),
    "PUNCHLIST": ("Berita Acara Pemeriksaan & Punch List", "letter"),
    "LAPORAN": ("Laporan tabel (keuangan, denda, refund, mingguan)", "table"),
    # DOC-02 — invoice pembeli dulu meminjam gaya LAPORAN; kini punya tampilan & naskah sendiri.
    "INVOICE": ("Invoice / tagihan pembeli (termin & biaya transaksi)", "table"),
    "INVOICE_BF": ("Tagihan booking fee (keep unit)", "letter"),
}

# Baris biaya standar SPR — kode SAMA dengan `contracts_engine.build_breakdown`.
MONEY_ROWS = [
    ("PRICE_LIST", "Harga unit (daftar)"), ("DISCOUNT", "Potongan harga"),
    ("PRICE_DEAL", "Harga kesepakatan"), ("BOOKING_FEE", "Booking fee"),
    ("DP", "Uang muka (DP)"), ("ADDON_SPEC", "Spek tambahan"),
    ("EXCESS_LAND", "Kelebihan tanah"), ("HOOK_FEE", "Biaya hook"),
    ("BPHTB", "BPHTB"), ("BANK_FEE", "Biaya bank"), ("INSURANCE", "Asuransi jiwa & kebakaran"),
    ("NOTARY", "Biaya notaris/AJB"), ("TOTAL", "Total kewajiban"),
]

SECTIONS = [
    ("identitas", "Identitas pemesan"), ("unit", "Data unit & proyek"),
    ("biaya", "Tabel rincian biaya (terkonfigurasi)"), ("termin", "Jadwal pembayaran (termin)"),
    ("ketentuan", "Naskah & pasal"), ("catatan", "Catatan tambahan"),
]
# Bagian yang MATI secara bawaan: naskah SPR owner sudah memuat rincian biaya inline, jadi
# tabel terkonfigurasi baru dicetak bila admin menyalakannya (atau memakai {{tabel_biaya}}).
SECTIONS_DEFAULT_HIDDEN = {"biaya"}


def _brand_default() -> dict:
    return {
        "company_name": ORG_NAME, "tagline": "Property Development",
        "address": "", "phone": "", "email": "", "website": "", "npwp": "",
        "logo_file_id": None, "header_image_file_id": None, "footer_image_file_id": None,
        # Dua mode yang diminta pemilik usaha: kop DIRAKIT sistem dari identitas di atas,
        # atau GAMBAR kop buatan desainer yang ditempel apa adanya.
        "header_mode": "system", "footer_mode": "system",
        "accent_color": "#0f766e", "text_color": "#0f172a",
        "footer_text": "", "show_page_numbers": True,
        "paper": "A4", "margin_top_mm": 32, "margin_bottom_mm": 24,
        "margin_left_mm": 20, "margin_right_mm": 20,
        "watermark_text": "", "watermark_file_id": None, "watermark_opacity": 8,
    }


def _table_default() -> dict:
    """Gaya TABEL dokumen (Fase 66).

    Sebelum ini semua tabel tercetak dengan kotak penuh, kepala tabel berwarna aksen, dan
    nama kolom yang selalu tampil — tidak bisa diubah tanpa menyentuh kode. Pemakai yang
    memakai kertas berkop cetakan sendiri meminta garis TRANSPARAN (tanpa kotak) dan tabel
    TANPA nama kolom; keduanya sekarang konfigurasi, bukan permintaan fitur baru.
    """
    return {
        "grid": "full",            # full | horizontal | none (transparan)
        "show_header": True,       # nama kolom tercetak?
        "header_fill": True,       # kepala tabel berwarna aksen (atau polos)
        "zebra": True,             # baris belang
        "total_highlight": True,   # baris total diberi latar
        "font_size": 8.5,
        "grid_color": "#e2e8f0",
        "width_pct": 100, "alignment": "left",
    }


def default_layout(code: str = DEFAULT_CODE) -> dict:
    script_first = code in {"KWITANSI", "BKM", "BKK", "PENAWARAN", "BAST", "FAKTUR", "BUPOT", "INVOICE", "INVOICE_BF", "LAPORAN"}
    section_keys = [k for k, _ in SECTIONS]
    if script_first:
        section_keys.remove("ketentuan")
        section_keys.insert(section_keys.index("termin"), "ketentuan")
    return {
        "code": code,
        "brand": _brand_default(),
        "table": _table_default(),
        "sections": [{"key": k, "label": lbl, "visible": k not in SECTIONS_DEFAULT_HIDDEN,
                      "order": section_keys.index(k) * 10}
                     for i, (k, lbl) in enumerate(SECTIONS)],
        "money_rows": [{"code": c, "label": lbl, "visible": True, "order": i * 10,
                        "hide_if_zero": c not in ("PRICE_DEAL", "TOTAL"), "manual": False,
                        "amount": None}
                       for i, (c, lbl) in enumerate(MONEY_ROWS)],
        "signatures": [
            {"title": "Pihak Pertama (Pengembang)", "name": "", "position": "Direktur",
             "show_stamp": True, "stamp_file_id": None, "sign_file_id": None,
             "auto_from_issuer": False},
            {"title": "Pihak Kedua (Pemesan)", "name": "", "position": "",
             "show_stamp": False, "stamp_file_id": None, "sign_file_id": None,
             "auto_from_issuer": False},
        ],
        "options": {
            "show_materai": True, "materai_note": "Bermeterai cukup",
            "show_place_date": True, "place": "", "show_doc_number": True,
            "show_title": True, "hide_zero_rows": True,
            "closing_note": "", "show_generated_note": True,
        },
    }


def _merge(base: dict, over: dict) -> dict:
    """Gabung layout turunan di atas bawaan — per kelompok, bukan per dokumen utuh."""
    out = {k: (dict(v) if isinstance(v, dict) else list(v) if isinstance(v, list) else v)
           for k, v in base.items()}
    for key, val in (over or {}).items():
        if key in ("brand", "options", "table") and isinstance(val, dict):
            out[key] = {**out.get(key, {}), **val}
        elif key in ("sections", "money_rows", "signatures") and isinstance(val, list) and val:
            out[key] = val
        elif key not in ("code", "org_id", "id", "_id"):
            out[key] = val
    return out


async def get_layout(org: str = ORG_ID, code: str = DEFAULT_CODE) -> dict:
    """Layout efektif: bawaan kode → dokumen `__default__` organisasi → override kode."""
    base = default_layout(code)
    org_doc = await db.document_layouts.find_one(
        {"org_id": org, "code": DEFAULT_CODE}, {"_id": 0})
    if org_doc:
        base = _merge(base, org_doc.get("layout") or {})
    if code != DEFAULT_CODE:
        own = await db.document_layouts.find_one({"org_id": org, "code": code}, {"_id": 0})
        if own:
            base = _merge(base, own.get("layout") or {})
            base["overridden"] = True
    base["code"] = code
    base["label"] = TARGETS.get(code, (code, "letter"))[0]
    base["kind"] = TARGETS.get(code, (code, "letter"))[1]
    script = await db.document_templates.find_one({"org_id": org, "code": code},
                                                   {"_id": 0, "content": 1, "is_active": 1})
    base["_script_content"] = (script or {}).get("content", "") if (script or {}).get("is_active", True) else ""
    return base


async def known_code(org: str, code: str) -> bool:
    """Kode dokumen yang boleh disetel: terdaftar di `TARGETS` ATAU punya naskah sendiri."""
    if code in TARGETS:
        return True
    return bool(await db.document_templates.find_one({"org_id": org, "code": code},
                                                     {"_id": 0, "id": 1}))


async def save_layout(org: str, code: str, layout: dict, actor: str) -> dict:
    ts = now_iso()
    cur = await db.document_layouts.find_one({"org_id": org, "code": code}, {"_id": 0})
    doc = {"layout": layout, "updated_by": actor, "updated_at": ts,
           "version": int((cur or {}).get("version") or 0) + 1}
    if cur:
        await db.document_layouts.update_one({"id": cur["id"]}, {"$set": doc})
    else:
        await db.document_layouts.insert_one(
            {"id": new_id(), "org_id": org, "code": code, "created_at": ts, **doc})
    return await get_layout(org, code)


async def reset_layout(org: str, code: str) -> dict:
    """Kembalikan ke bawaan. Yang dibuang hanya OVERRIDE-nya, bukan riwayat dokumen."""
    await db.document_layouts.delete_one({"org_id": org, "code": code})
    return await get_layout(org, code)


async def list_targets(org: str = ORG_ID) -> list:
    """Daftar SEMUA jenis dokumen yang bisa disetel — naskah maupun tampilannya.

    Fase 66: satu layar untuk satu jenis dokumen, jadi daftar ini juga membawa keadaan
    NASKAH-nya (`has_script`) dan kategorinya. Kode template buatan sendiri yang belum
    terdaftar di `TARGETS` ikut ditampilkan (`custom`) supaya naskahnya tidak jadi yatim
    seperti sebelumnya (dulu ada di tab lain yang tidak tahu-menahu soal tampilan).
    """
    import doc_script as ds
    rows = {d["code"]: d for d in await db.document_layouts.find(
        {"org_id": org}, {"_id": 0, "code": 1, "version": 1, "updated_at": 1,
                          "updated_by": 1}).to_list(1000)}
    scripts = {d["code"]: d for d in await db.document_templates.find(
        {"org_id": org}, {"_id": 0, "code": 1, "name": 1, "content": 1,
                          "is_active": 1}).to_list(1000)}
    daftar = [(c, lbl, kind, False) for c, (lbl, kind) in TARGETS.items()]
    daftar += [(c, (s.get("name") or c), "letter", True)
               for c, s in sorted(scripts.items()) if c not in TARGETS]
    out = []
    for code, label, kind, custom in daftar:
        s = scripts.get(code) or {}
        out.append({
            "code": code, "label": label, "kind": kind, "custom": custom,
            "category": ds.category_of(code),
            "category_label": ds.CATEGORIES[ds.category_of(code)],
            "has_script": bool((s.get("content") or "").strip()),
            "script_active": s.get("is_active", True),
            "customized": code in rows, "version": (rows.get(code) or {}).get("version"),
            "updated_at": (rows.get(code) or {}).get("updated_at"),
            "updated_by": (rows.get(code) or {}).get("updated_by")})
    return out


# ============================================================ pemakaian saat mencetak
def money_rows_for(layout: dict, amounts: dict) -> list:
    """Baris biaya yang BOLEH tercetak: urutan & label dari konfigurasi, nilai dari mesin.

    `amounts` = {kode: nominal|None}. `None` berarti BELUM DIKETAHUI dan tetap tercetak
    ("belum ditetapkan") — hanya nilai NOL yang boleh disembunyikan `hide_if_zero`.
    """
    hide_zero = bool((layout.get("options") or {}).get("hide_zero_rows", True))
    out = []
    for row in sorted(layout.get("money_rows") or [], key=lambda r: r.get("order") or 0):
        if not row.get("visible", True):
            continue
        if row.get("manual"):
            nilai = row.get("amount")
        else:
            if row["code"] not in amounts:
                continue
            nilai = amounts.get(row["code"])
        if nilai == 0 and hide_zero and row.get("hide_if_zero", True):
            continue
        out.append({"code": row.get("code"), "label": row.get("label"), "amount": nilai,
                    "manual": bool(row.get("manual"))})
    return out


def section_visible(layout: dict, key: str) -> bool:
    for s in layout.get("sections") or []:
        if s.get("key") == key:
            return bool(s.get("visible", True))
    return True


def signatures_for(layout: dict, *, issuer_name: str = None,
                   issuer_position: str = None) -> list:
    """Kolom tanda tangan. `auto_from_issuer` mengambil nama penerbit dokumen."""
    out = []
    for s in layout.get("signatures") or []:
        name = s.get("name") or ""
        pos = s.get("position") or ""
        if s.get("auto_from_issuer"):
            name = issuer_name or name
            pos = issuer_position or pos
        out.append({**s, "name": name, "position": pos})
    return out


async def images(org: str, layout: dict) -> dict:
    """Ambil gambar yang dipakai layout (logo/kop/footer/watermark/cap/tanda tangan).

    Berkas yang HILANG tidak boleh menggagalkan pencetakan: dokumen tetap terbit tanpa
    gambar itu, dan kejadiannya dicatat di log supaya bisa diperbaiki.
    """
    b = layout.get("brand") or {}
    ids = {k: b.get(f"{k}_file_id") for k in
           ("logo", "header_image", "footer_image", "watermark")}
    for i, s in enumerate(layout.get("signatures") or []):
        ids[f"sig{i}_stamp"] = s.get("stamp_file_id")
        ids[f"sig{i}_sign"] = s.get("sign_file_id")
    out = {}
    for key, fid in ids.items():
        if not fid:
            continue
        rec = await db.files.find_one({"id": fid, "org_id": org, "is_deleted": False},
                                      {"_id": 0, "storage_path": 1, "provider": 1})
        if not rec:
            logger.warning("Gambar layout %s (%s) tidak ditemukan — dilewati.", key, fid)
            continue
        try:
            data, _ct = await storage.get_file_bytes(rec["storage_path"], rec.get("provider"))
            out[key] = data
        except (FileNotFoundError, OSError) as e:
            logger.warning("Gambar layout %s gagal dibaca (%s) — dilewati.", key, e)
    return out


def sample_document(layout: dict) -> dict:
    """Data CONTOH untuk pratinjau — ditandai jelas agar tidak disangka dokumen nyata."""
    amounts = {"PRICE_LIST": 850000000, "DISCOUNT": 25000000, "PRICE_DEAL": 825000000,
               "BOOKING_FEE": 5000000, "DP": 660000000, "ADDON_SPEC": 12500000,
               "EXCESS_LAND": 0, "HOOK_FEE": 0, "BPHTB": 20625000, "BANK_FEE": 7500000,
               "INSURANCE": None, "NOTARY": 9500000, "TOTAL": 867125000}
    return {
        "title": "SURAT PESANAN RUMAH (CONTOH)",
        "doc_number": "0001/SPR-KPR/CTH/VIII/2026",
        "meta": [("Nama pemesan", "Ibu Dewi Kartika"), ("No. telepon", "0812-1111-1111"),
                 ("Alamat", "Jl. Melati No. 12, Bandung"),
                 ("Unit / blok", "A-01 (tipe 45/90)"),
                 ("Proyek", "Cluster Asri Harmony Land"),
                 ("Skema pembayaran", "KPR")],
        "amounts": amounts,
        "terms": [("1. Booking fee", "Rp 5.000.000 — saat pemesanan"),
                  ("2. Uang muka (DP)", "Rp 660.000.000 — 14 hari sejak SPR"),
                  ("3. Pelunasan KPR", "Rp 160.000.000 — setelah akad kredit")],
        "clauses": [
            "Cicilan wajib dibayar setiap tanggal 7; toleransi paling lambat tanggal 20.",
            "Tunggakan 2 bulan (berturut-turut maupun akumulatif) memberi hak Pihak Pertama "
            "membatalkan pesanan secara sepihak sesuai ketentuan yang berlaku.",
            "Pembatalan sebelum pembangunan dimulai dikenakan potongan 35% dari pembayaran "
            "yang telah diterima.",
        ],
        "note": "Dokumen ini adalah PRATINJAU dengan data contoh — bukan dokumen sah.",
    }
