"""Registry penomoran: semua nomor dokumen & kode master yang bisa dikonfigurasi.

Setiap entri = satu counter/pola. `tokens` = token KONTEKS yang tersedia untuk pola itu
(di samping token umum). Pola bawaan meniru format yang sudah dipakai sistem sehingga
tidak ada nomor yang berubah sebelum admin mengubah aturannya.
"""

GLOBAL_TOKENS = [
    ("PREFIX", "Awalan aturan (bisa diganti di kolom Awalan)", "SPK"),
    ("SEQ", "Nomor urut, lebar digit dari kolom Lebar; {SEQ:6} memaksa 6 digit", "0001"),
    ("SEQ_ALPHA", "Nomor urut sebagai huruf: A, B, … Z, AA", "A"),
    ("YYYY", "Tahun 4 digit", "2026"),
    ("YY", "Tahun 2 digit", "26"),
    ("MM", "Bulan 2 digit", "06"),
    ("MM_ROMAN", "Bulan romawi", "VI"),
    ("DD", "Tanggal 2 digit", "15"),
    ("YYMMDD", "Tanggal ringkas", "260615"),
    ("ORG_INITIALS", "Inisial nama organisasi", "PSL"),
]

CONTEXT_TOKENS = {
    "PROJECT_CODE": ("Kode proyek", "GRIYA1"),
    "PROJECT_INITIALS": ("Inisial nama proyek", "GAR"),
    "CLUSTER_CODE": ("Kode cluster", "UTAMA"),
    "BLOCK_CODE": ("Kode blok", "A"),
    "UNIT_CODE": ("Kode unit", "A-01"),
    "UNIT_TYPE_CODE": ("Kode tipe unit", "T45-90"),
    "NO": ("Nomor unit dalam blok ({NO:2} = 2 digit)", "01"),
    "CUSTOMER_INITIALS": ("Inisial nama pelanggan", "DK"),
    "VENDOR_CODE": ("Kode vendor", "VND-01"),
    "SUBCON_CODE": ("Kode subkontraktor", "SUB-01"),
    "CATEGORY": ("Kategori/jenis (huruf besar)", "MATERIAL"),
    "LEVEL": ("Tingkat (mis. SP1/SP2)", "1"),
    "STAGE": ("Tahap legal", "PPJB"),
    "TEMPLATE_CODE": ("Kode template dokumen", "SPR-KPR"),
}

RESET_OPTIONS = {"never": "Tidak pernah", "yearly": "Tahunan", "monthly": "Bulanan",
                 "daily": "Harian"}
SEQ_SCOPE_OPTIONS = {"tokens": "Per kombinasi token konteks pada pola",
                     "global": "Satu urutan untuk seluruh organisasi"}

_PROJ = ["PROJECT_CODE", "PROJECT_INITIALS"]
_UNIT = _PROJ + ["CLUSTER_CODE", "BLOCK_CODE", "UNIT_CODE", "UNIT_TYPE_CODE"]
_SALES = _UNIT + ["CUSTOMER_INITIALS"]
STD = "{PREFIX}/{YYYY}/{SEQ}"


def _r(key, label, prefix, group, *, pattern=STD, width=4, reset="yearly", tokens=None,
       seq_scope="tokens", desc="", family=None, parent=None):
    """`parent` = kunci konteks INDUK yang selalu memisahkan counter (blok per cluster, cluster
    per proyek) walau tokennya tidak dipakai di pola."""
    return {"key": key, "label": label, "prefix": prefix, "group": group, "pattern": pattern,
            "width": width, "reset": reset, "tokens": tokens or [], "seq_scope": seq_scope,
            "desc": desc, "family": family, "parent": parent or []}


REGISTRY = [
    # ---------------------------------------------------------------- penjualan & legal
    _r("quotation", "Penawaran harga", "PNW", "penjualan", tokens=_SALES),
    _r("booking_fee_invoice", "Invoice booking fee", "INV-BF", "penjualan", tokens=_SALES),
    _r("booking_fee_refund", "Refund booking fee", "RF-BF", "penjualan", tokens=_SALES),
    _r("receipt", "Kwitansi penerimaan", "KWT", "penjualan", tokens=_SALES),
    _r("cost_invoice", "Invoice biaya (BPHTB/notaris pass-through)", "INB", "penjualan", tokens=_SALES),
    _r("cost_receipt", "Kwitansi biaya (titipan pembeli)", "KWB", "penjualan", tokens=_SALES),
    _r("contract", "Kontrak / PPJB (internal)", "KTR", "penjualan", tokens=_SALES),
    _r("legal", "Dokumen tahap legal (SPR/PPJB/AJB…)", "", "penjualan",
       pattern="{STAGE}/{YYYY}/{SEQ}", tokens=_SALES + ["STAGE"], family=True,
       desc="Awalan diambil dari nama tahap (token {STAGE})."),
    _r("docnum", "Surat pesanan & pernyataan — bawaan semua jenis", "", "penjualan",
       pattern="{SEQ}/{TEMPLATE_CODE}/{PROJECT_CODE}/{MM_ROMAN}/{YYYY}",
       tokens=_SALES + ["TEMPLATE_CODE"], family=True,
       desc="Dipakai bila aturan per jenis di bawah tidak diubah. Counter tiap jenis tetap TERPISAH."),
    _r("docnum:SPR-CASH", "SPR — Cash Keras", "SPR-CASH", "penjualan",
       pattern="{SEQ}/{TEMPLATE_CODE}/{PROJECT_CODE}/{MM_ROMAN}/{YYYY}",
       tokens=_SALES + ["TEMPLATE_CODE"], desc="Pola khusus SPR cash keras (menimpa bawaan)."),
    _r("docnum:SPR-CASHB", "SPR — Cash Bertahap", "SPR-CASHB", "penjualan",
       pattern="{SEQ}/{TEMPLATE_CODE}/{PROJECT_CODE}/{MM_ROMAN}/{YYYY}",
       tokens=_SALES + ["TEMPLATE_CODE"], desc="Pola khusus SPR cash bertahap (menimpa bawaan)."),
    _r("docnum:SPR-KPR", "SPR — KPR", "SPR-KPR", "penjualan",
       pattern="{SEQ}/{TEMPLATE_CODE}/{PROJECT_CODE}/{MM_ROMAN}/{YYYY}",
       tokens=_SALES + ["TEMPLATE_CODE"], desc="Pola khusus SPR KPR (menimpa bawaan)."),
    _r("docnum:SPKT", "Surat Pernyataan Kelebihan Tanah (SPKT)", "SPKT", "penjualan",
       pattern="{SEQ}/{TEMPLATE_CODE}/{PROJECT_CODE}/{MM_ROMAN}/{YYYY}",
       tokens=_SALES + ["TEMPLATE_CODE"], desc="Pola khusus SPKT (menimpa bawaan)."),
    _r("document", "Dokumen dari template kustom", "DOC", "penjualan",
       pattern="{TEMPLATE_CODE}/{YYYY}/{SEQ}", tokens=_SALES + ["TEMPLATE_CODE"], family=True),
    _r("cancellation", "Pembatalan kontrak", "BTL", "penjualan", tokens=_SALES),
    _r("handover", "Berita acara serah terima", "BAST", "penjualan", tokens=_SALES),
    _r("warranty_claim", "Klaim garansi", "KG", "penjualan", tokens=_SALES),
    _r("warning_letter", "Surat peringatan", "SP", "penjualan",
       pattern="{PREFIX}{LEVEL}/{YYYY}/{SEQ}", tokens=_SALES + ["LEVEL"]),
    # ---------------------------------------------------------------- mitra & marketing
    _r("marketing_fee", "Tagihan fee mitra", "MF", "mitra", tokens=_PROJ),
    _r("partner_fee_rule", "Aturan fee mitra", "PFR", "mitra"),
    _r("campaign", "Kampanye iklan", "CMP", "mitra"),
    # ---------------------------------------------------------------- konstruksi & pengadaan
    _r("spk", "SPK subkontraktor", "SPK", "konstruksi", tokens=_PROJ + ["SUBCON_CODE"]),
    _r("claim", "Termin / opname", "TRM", "konstruksi", tokens=_PROJ + ["SUBCON_CODE"]),
    _r("change_order", "Change order", "CO", "konstruksi", tokens=_PROJ + ["SUBCON_CODE"]),
    _r("subcon_advance", "Uang muka subkon", "UMK", "konstruksi", tokens=_PROJ + ["SUBCON_CODE"]),
    _r("subcon_retention", "Retensi subkon", "RET", "konstruksi", tokens=_PROJ + ["SUBCON_CODE"]),
    _r("inspection", "Inspeksi QC", "QC", "konstruksi", tokens=_UNIT),
    _r("requisition", "Permintaan material (PR)", "PR", "konstruksi", tokens=_PROJ),
    _r("po", "Purchase order", "PO", "konstruksi", tokens=_PROJ + ["VENDOR_CODE"]),
    _r("grn", "Penerimaan barang (GRN)", "GRN", "konstruksi", tokens=_PROJ + ["VENDOR_CODE"]),
    _r("grn_return", "Retur barang", "RTN", "konstruksi", tokens=_PROJ + ["VENDOR_CODE"]),
    _r("material_transfer", "Transfer material", "TRF", "konstruksi", tokens=_PROJ),
    _r("labor_payroll", "Upah tenaga kerja", "UPH", "konstruksi", tokens=_PROJ),
    # ---------------------------------------------------------------- keuangan
    _r("journal", "Jurnal umum", "JV", "keuangan", width=5),
    _r("cash_advance", "Kas bon / uang muka", "KB", "keuangan", tokens=_PROJ),
    _r("petty_expense", "Pengeluaran kas kecil", "KK", "keuangan", tokens=_PROJ),
    _r("pdc", "Giro / cek mundur diterima", "GIRO", "keuangan"),
    _r("cash_voucher_in", "Bukti kas masuk (BKM)", "BKM", "keuangan"),
    _r("cash_voucher_out", "Bukti kas keluar (BKK)", "BKK", "keuangan"),
    _r("loan", "Pembiayaan / pinjaman", "PBY", "keuangan"),
    _r("fixed_asset", "Aset tetap", "AST", "keuangan", tokens=["CATEGORY"]),
    # ---------------------------------------------------------------- kode master
    _r("master:project", "Kode proyek", "PRJ", "master", pattern="{PREFIX}-{SEQ:2}",
       width=2, reset="never", tokens=["PROJECT_INITIALS"],
       desc="Dipakai bila kolom kode dikosongkan saat membuat proyek."),
    _r("master:cluster", "Kode cluster", "C", "master", pattern="{PREFIX}{SEQ:2}", width=2,
       reset="never", tokens=_PROJ, parent=["project_id"], desc="Urut per proyek."),
    _r("master:block", "Kode blok", "", "master", pattern="{SEQ_ALPHA}", width=1,
       reset="never", tokens=_PROJ + ["CLUSTER_CODE"], parent=["project_id", "cluster_code"],
       desc="Bawaan huruf A, B, C… per cluster."),
    _r("master:unit", "Kode unit", "", "master", pattern="{BLOCK_CODE}-{NO:2}", width=2,
       reset="never", tokens=_PROJ + ["CLUSTER_CODE", "BLOCK_CODE", "UNIT_TYPE_CODE", "NO"],
       parent=["project_id", "cluster_code", "block_code"], desc="Kode unit selalu dibentuk dari pola ini (nomor unit = token {NO}); "
            "{SEQ} bila ingin urut otomatis."),
    _r("master:unit_type", "Kode tipe unit", "T", "master", pattern="{PREFIX}{SEQ:2}",
       width=2, reset="never"),
    _r("master:addon", "Kode add-on", "ADD", "master", pattern="{PREFIX}-{SEQ:3}", width=3,
       reset="never", tokens=["CATEGORY"]),
    _r("master:vendor", "Kode vendor", "VND", "master", pattern="{PREFIX}-{SEQ:3}", width=3,
       reset="never", tokens=["CATEGORY"]),
    _r("master:subcontractor", "Kode subkontraktor", "SUB", "master",
       pattern="{PREFIX}-{SEQ:3}", width=3, reset="never", tokens=["CATEGORY"]),
    _r("master:material", "Kode material", "MAT", "master", pattern="{PREFIX}-{SEQ:3}",
       width=3, reset="never", tokens=_PROJ + ["CATEGORY"], parent=["project_id"],
       desc="Urut per proyek."),
    _r("agent", "Kode mitra / agen", "AGN", "master", tokens=["CATEGORY"],
       desc="Selalu otomatis (AGN/TAHUN/URUT)."),
]

REGISTRY_BY_KEY = {r["key"]: r for r in REGISTRY}
GROUP_LABELS = {"penjualan": "Penjualan & Legal", "mitra": "Mitra & Marketing",
                "konstruksi": "Konstruksi & Pengadaan", "keuangan": "Keuangan",
                "master": "Kode Master Data"}

# scope legacy → key registry (nama counter lama tetap dipakai agar urutan tidak terputus)
LEGACY_SCOPE_MAP = {"legal:": "legal", "docnum:": "docnum", "document:": "document"}


def registry_for(scope: str) -> dict | None:
    if scope in REGISTRY_BY_KEY:
        return REGISTRY_BY_KEY[scope]
    # `docnum:SPR-KPR:PROJ:...` → aturan per jenis bila ada; kalau tidak, aturan keluarga.
    parts = scope.split(":")
    if len(parts) >= 2 and ":".join(parts[:2]) in REGISTRY_BY_KEY:
        return REGISTRY_BY_KEY[":".join(parts[:2])]
    for pref, key in LEGACY_SCOPE_MAP.items():
        if scope.startswith(pref):
            return REGISTRY_BY_KEY[key]
    return None
