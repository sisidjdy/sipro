"""SSOT reference registry — TAMBAHAN Fase 27 (Kas Bon, Aset Tetap, Pembiayaan, Marketing Fee).

Kenapa file terpisah? `reference.py` sudah mendekati batas compliance (≤800 baris,
gate `validate_compliance`). Grup di sini digabungkan ke `reference.GROUPS` sehingga
tetap SATU registry: satu-satunya sumber nilai enum untuk backend (validator Annotated
di `models_p27.py`) maupun frontend (`GET /api/reference` → ReferenceSelect / Kamus Data).

Referensi kelompok fiskal penyusutan: Pasal 11 UU PPh + PMK 72/2023 (Kelompok 1–4 =
4/8/16/20 tahun; bangunan permanen 20 tahun, tidak permanen 10 tahun; tanah tidak disusutkan).
"""


def _o(value: str, label: str) -> dict:
    return {"value": value, "label": label}


# Masa manfaat default (bulan) per kelompok fiskal — dipakai fixed_assets.py sebagai
# usulan otomatis saat pengguna memilih kelompok, tetap bisa ditimpa manual.
TAX_GROUP_MONTHS = {
    "kelompok_1": 48,
    "kelompok_2": 96,
    "kelompok_3": 192,
    "kelompok_4": 240,
    "bangunan_permanen": 240,
    "bangunan_tidak_permanen": 120,
    "tidak_disusutkan": 0,
}

# Kategori pengeluaran kas bon -> akun beban/aset yang dibebani saat pertanggungjawaban.
CASHBON_ACCOUNT = {
    "transport": "6-1300",
    "konsumsi_rapat": "6-1300",
    "atk_kantor": "6-1300",
    "perizinan_retribusi": "6-1300",
    "biaya_proyek": "1-1600",          # dikapitalisasi ke WIP proyek
    "upah_harian": "1-1600",
    "pemasaran_promosi": "6-1200",
    "perbaikan_pemeliharaan": "6-1300",
    "lainnya": "6-1300",
}

# Kategori aset -> akun. Fase 27 memakai satu akun induk aset tetap (1-2100) +
# akumulasi penyusutan (1-2200); pemecahan per kategori adalah pekerjaan fase lanjutan.
ASSET_ACCOUNT = "1-2100"
ACCUM_DEPRECIATION_ACCOUNT = "1-2200"

BANKS = ["BTN", "BNI", "BRI", "Mandiri", "BCA", "CIMB Niaga", "Permata", "Danamon",
         "BSI", "Muamalat", "BJB", "Panin", "Maybank", "OCBC"]
LEASINGS = ["Adira Finance", "BCA Finance", "Mandiri Tunas Finance", "BFI Finance",
            "Clipan Finance", "Maybank Finance", "Koperasi Karyawan"]

GROUPS_P27: dict = {
    # ---------------- Kas Bon (petty cash / uang muka karyawan) ----------------
    "cashbon_status": {
        "label": "Status Kas Bon", "strict": True, "options": [
            _o("draft", "Draf"), _o("submitted", "Diajukan"), _o("approved", "Disetujui"),
            _o("disbursed", "Dicairkan"), _o("settled", "Dipertanggungjawabkan"),
            _o("rejected", "Ditolak"), _o("cancelled", "Dibatalkan"),
        ],
    },
    "cashbon_category": {
        "label": "Kategori Pengeluaran Kas Bon", "strict": True, "options": [
            _o("transport", "Transport & BBM"), _o("konsumsi_rapat", "Konsumsi & Rapat"),
            _o("atk_kantor", "ATK & Perlengkapan Kantor"),
            _o("perizinan_retribusi", "Perizinan & Retribusi"),
            _o("biaya_proyek", "Biaya Proyek (dikapitalisasi ke WIP)"),
            _o("upah_harian", "Upah Harian Lapangan"),
            _o("pemasaran_promosi", "Pemasaran & Promosi"),
            _o("perbaikan_pemeliharaan", "Perbaikan & Pemeliharaan"),
            _o("lainnya", "Lainnya"),
        ],
    },
    "cash_source": {
        "label": "Sumber Kas", "strict": True, "options": [
            _o("kas", "Kas (tunai)"), _o("bank", "Bank (transfer)"),
        ],
    },
    # ---------------- Aset Tetap ----------------
    "asset_category": {
        "label": "Kategori Aset Tetap", "strict": True, "options": [
            _o("tanah", "Tanah"), _o("bangunan", "Bangunan & Gedung"),
            _o("kendaraan", "Kendaraan Operasional"),
            _o("mesin_peralatan", "Mesin & Peralatan Proyek"),
            _o("perabot_kantor", "Perabot & Inventaris Kantor"),
            _o("komputer_it", "Komputer & Perangkat IT"),
            _o("instalasi_infrastruktur", "Instalasi & Infrastruktur"),
            _o("lainnya", "Lainnya"),
        ],
    },
    "asset_tax_group": {
        "label": "Kelompok Fiskal Penyusutan", "strict": True, "options": [
            _o("kelompok_1", "Kelompok 1 — 4 tahun"),
            _o("kelompok_2", "Kelompok 2 — 8 tahun"),
            _o("kelompok_3", "Kelompok 3 — 16 tahun"),
            _o("kelompok_4", "Kelompok 4 — 20 tahun"),
            _o("bangunan_permanen", "Bangunan permanen — 20 tahun"),
            _o("bangunan_tidak_permanen", "Bangunan tidak permanen — 10 tahun"),
            _o("tidak_disusutkan", "Tidak disusutkan (mis. tanah)"),
        ],
    },
    "depreciation_method": {
        "label": "Metode Penyusutan", "strict": True, "options": [
            _o("garis_lurus", "Garis lurus"),
            _o("saldo_menurun", "Saldo menurun ganda"),
            _o("tidak_disusutkan", "Tidak disusutkan"),
        ],
    },
    "asset_status": {
        "label": "Status Aset Tetap", "strict": True, "options": [
            _o("active", "Aktif"), _o("fully_depreciated", "Habis disusutkan"),
            _o("disposed", "Dilepas / dijual"),
        ],
    },
    "asset_funding": {
        "label": "Sumber Dana Perolehan", "strict": True, "options": [
            _o("kas", "Kas (tunai)"), _o("bank", "Bank (transfer)"),
            _o("utang_usaha", "Utang usaha (vendor)"),
        ],
    },
    # ---------------- Pembiayaan korporat (Bank / Leasing) ----------------
    "lender": {
        "label": "Pemberi Pinjaman", "strict": False, "dynamic": True,
        "source": {"collection": "loans", "field": "lender"},
        "options": [_o(b, b) for b in BANKS] + [_o(l, l) for l in LEASINGS],
    },
    "lender_type": {
        "label": "Jenis Pemberi Pinjaman", "strict": True, "options": [
            _o("bank", "Bank"), _o("multifinance", "Multifinance"),
            _o("leasing", "Leasing"), _o("koperasi", "Koperasi"),
            _o("pemegang_saham", "Pemegang Saham"), _o("lainnya", "Lainnya"),
        ],
    },
    "loan_type": {
        "label": "Jenis Fasilitas Pembiayaan", "strict": True, "options": [
            _o("kredit_investasi", "Kredit Investasi"),
            _o("kredit_modal_kerja", "Kredit Modal Kerja"),
            _o("kredit_konstruksi", "Kredit Konstruksi"),
            _o("leasing_kendaraan", "Leasing Kendaraan"),
            _o("leasing_alat_berat", "Leasing Alat Berat"),
            _o("pinjaman_pemegang_saham", "Pinjaman Pemegang Saham"),
            _o("lainnya", "Lainnya"),
        ],
    },
    "amortization_method": {
        "label": "Metode Amortisasi", "strict": True, "options": [
            _o("anuitas", "Anuitas (angsuran total tetap)"),
            _o("pokok_tetap", "Pokok tetap (bunga efektif menurun)"),
            _o("flat", "Flat (bunga dari pokok awal)"),
        ],
    },
    "loan_status": {
        "label": "Status Fasilitas Pembiayaan", "strict": True, "options": [
            _o("draft", "Draf"), _o("active", "Aktif"), _o("paid_off", "Lunas"),
            _o("restructured", "Direstrukturisasi"), _o("cancelled", "Dibatalkan"),
        ],
    },
    "installment_status": {
        "label": "Status Angsuran", "strict": True, "options": [
            _o("unpaid", "Belum dibayar"), _o("partial", "Sebagian"), _o("paid", "Lunas"),
        ],
    },
    # ---------------- Marketing Fee (agen / broker / referral) ----------------
    "agent_type": {
        "label": "Jenis Agen / Mitra", "strict": True, "options": [
            _o("agen_properti", "Agen Properti"), _o("broker_kantor", "Kantor Broker"),
            _o("referral_pembeli", "Referral Pembeli"), _o("influencer", "Influencer / KOL"),
            _o("mitra_korporat", "Mitra Korporat"), _o("lainnya", "Lainnya"),
        ],
    },
    "agent_status": {
        "label": "Status Agen", "strict": True, "options": [
            _o("active", "Aktif"), _o("inactive", "Tidak aktif"),
            _o("blacklist", "Daftar hitam"),
        ],
    },
    "marketing_fee_status": {
        "label": "Status Marketing Fee", "strict": True, "options": [
            _o("draft", "Draf"), _o("submitted", "Diajukan"), _o("approved", "Disetujui"),
            _o("paid", "Dibayar"), _o("rejected", "Ditolak"),
        ],
    },
    "marketing_fee_trigger": {
        "label": "Pemicu Marketing Fee", "strict": True, "options": [
            _o("booking", "Booking / NUP"), _o("ppjb", "PPJB ditandatangani"),
            _o("dp_lunas", "DP lunas"), _o("akad", "Akad KPR / AJB"),
            _o("bast", "Serah terima unit (BAST)"),
        ],
    },
}
