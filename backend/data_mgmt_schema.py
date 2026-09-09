"""Skema master data untuk migrasi Excel (template, impor, ekspor).

Satu sumber definisi: sheet Excel ↔ koleksi Mongo ↔ kolom + aturan. Urutan ENTITIES =
urutan dependensi (proyek sebelum cluster, cluster sebelum blok, dst.) sehingga satu berkas
bisa diimpor sekali jalan.
"""
import reference as ref

DEFAULT_IMPORT_PASSWORD = "Sipro#2026"


def _f(key, label, type="str", required=False, enum=None, default=None, desc="", example="",
       ref_to=None, width=None):
    return {"key": key, "label": label, "type": type, "required": required, "enum": enum,
            "default": default, "desc": desc, "example": example, "ref": ref_to,
            "width": width}


ENTITIES = [
    {
        "key": "users", "sheet": "Pengguna", "collection": "users", "icon": "users",
        "desc": "Akun staf. Sandi kosong = sandi awal bawaan (wajib diganti pengguna).",
        "key_fields": ["email"],
        "fields": [
            _f("name", "Nama", required=True, example="Budi Santoso"),
            _f("email", "Email", "email", required=True, example="budi@perusahaan.co.id",
               desc="Kunci unik (login)."),
            _f("role", "Peran", "enum", required=True, enum="user_role", example="sales"),
            _f("phone", "No. HP", "phone", example="08123456789"),
            _f("password", "Sandi awal", desc="Kosong = " + DEFAULT_IMPORT_PASSWORD,
               example=""),
            _f("is_active", "Aktif", "bool", default=True, example="TRUE"),
        ],
    },
    {
        "key": "projects", "sheet": "Proyek", "collection": "projects", "icon": "building",
        "desc": "Proyek/perumahan. Kode dipakai sheet lain sebagai rujukan.",
        "key_fields": ["code"],
        "fields": [
            _f("code", "Kode proyek", required=True, example="GRIYA1",
               desc="Kunci unik, huruf besar tanpa spasi."),
            _f("name", "Nama proyek", required=True, example="Griya Asri Residence"),
            _f("location", "Lokasi", example="Bogor, Jawa Barat"),
            _f("status", "Status", "enum", enum="project_status", default="active",
               example="active"),
            _f("members", "Anggota tim (email)", "list",
               desc="Email PM/site engineer dipisah ; (harus ada di sheet Pengguna)",
               example="pm@perusahaan.co.id; site@perusahaan.co.id"),
        ],
    },
    {
        "key": "clusters", "sheet": "Cluster", "collection": "clusters", "icon": "layers",
        "desc": "Cluster/tahap dalam proyek. Setiap proyek minimal satu cluster.",
        "key_fields": ["project_code", "code"],
        "fields": [
            _f("project_code", "Kode proyek", required=True, ref_to="projects", example="GRIYA1"),
            _f("code", "Kode cluster", required=True, example="UTAMA"),
            _f("name", "Nama cluster", required=True, example="Cluster Utama"),
            _f("order", "Urutan", "int", default=0, example="1"),
            _f("status", "Status", "enum", enum="cluster_status", default="selling",
               example="selling"),
            _f("price_multiplier", "Pengali harga", "float", default=1.0, example="1.0",
               desc="1.0 = harga tipe; 1.05 = premium 5%"),
            _f("land_area", "Luas lahan (m2)", "int", example="12000"),
            _f("unit_target", "Target unit", "int", example="120"),
            _f("description", "Keterangan", example=""),
        ],
    },
    {
        "key": "blocks", "sheet": "Blok", "collection": "blocks", "icon": "grid",
        "desc": "Blok dalam cluster. Kode unit = KODE_BLOK-NOMOR (mis. A-01).",
        "key_fields": ["project_code", "cluster_code", "code"],
        "fields": [
            _f("project_code", "Kode proyek", required=True, ref_to="projects", example="GRIYA1"),
            _f("cluster_code", "Kode cluster", required=True, ref_to="clusters", example="UTAMA"),
            _f("code", "Kode blok", required=True, example="A"),
            _f("name", "Nama blok", example="Blok A"),
            _f("order", "Urutan", "int", default=0, example="1"),
            _f("orientation", "Orientasi", example="Utara"),
            _f("notes", "Catatan", example=""),
        ],
    },
    {
        "key": "unit_types", "sheet": "Tipe Unit", "collection": "unit_types", "icon": "home",
        "desc": "Katalog tipe rumah/kavling: luas standar & harga dasar.",
        "key_fields": ["code"],
        "fields": [
            _f("code", "Kode tipe", required=True, example="T45-90",
               desc="Kunci unik, dirujuk sheet Unit."),
            _f("name", "Nama tipe", required=True, example="Tipe 45/90"),
            _f("building_area", "Luas bangunan (m2)", "int", example="45",
               desc="Kosong untuk kavling"),
            _f("land_area_std", "Luas tanah standar (m2)", "int", example="90"),
            _f("base_price", "Harga dasar (Rp)", "int", required=True, example="650000000"),
            _f("bedrooms", "Kamar tidur", "int", example="2"),
            _f("bathrooms", "Kamar mandi", "int", example="1"),
            _f("floors", "Jumlah lantai", "int", default=1, example="1"),
            _f("active", "Aktif", "bool", default=True, example="TRUE"),
        ],
    },
    {
        "key": "units", "sheet": "Unit", "collection": "units", "icon": "map",
        "desc": "Daftar unit/kavling. Harga kosong = harga tipe × pengali cluster.",
        "key_fields": ["project_code", "cluster_code", "block_code", "no"],
        "fields": [
            _f("project_code", "Kode proyek", required=True, ref_to="projects", example="GRIYA1"),
            _f("cluster_code", "Kode cluster", required=True, ref_to="clusters", example="UTAMA"),
            _f("block_code", "Kode blok", required=True, ref_to="blocks", example="A"),
            _f("no", "Nomor unit", required=True, example="01",
               desc="Nomor dalam blok; kode unit jadi A-01"),
            _f("unit_type_code", "Kode tipe unit", ref_to="unit_types", example="T45-90"),
            _f("land_area", "Luas tanah (m2)", "int", example="90"),
            _f("building_area", "Luas bangunan (m2)", "int", example="45"),
            _f("price", "Harga (Rp)", "int", example="650000000"),
            _f("is_hook", "Posisi hook/sudut", "bool", default=False, example="FALSE"),
            _f("excess_land_m2", "Kelebihan tanah (m2)", "int", default=0, example="0"),
            _f("status", "Status awal", "enum", enum="unit_import_status", default="available",
               example="available",
               desc="available/blocked/sold/handed_over. Unit terjual lama diberi tanda saja."),
            _f("notes", "Catatan", example=""),
        ],
    },
    {
        "key": "addon_items", "sheet": "Add-on", "collection": "addon_items", "icon": "plus",
        "desc": "Spek tambahan/biaya opsional yang bisa dipilih saat penawaran.",
        "key_fields": ["code"],
        "fields": [
            _f("code", "Kode", required=True, example="ADD-CANOPY"),
            _f("name", "Nama", required=True, example="Kanopi carport"),
            _f("category", "Kategori", "enum", required=True, enum="addon_category",
               example="spek_bangunan"),
            _f("pricing_mode", "Cara hitung", "enum", required=True, enum="addon_pricing_mode",
               example="lump_sum"),
            _f("unit_price", "Harga satuan (Rp)", "int", required=True, example="7500000"),
            _f("uom", "Satuan", "enum", enum="uom", default="unit", example="unit"),
            _f("finance_treatment", "Perlakuan keuangan", "enum", enum="finance_treatment",
               default="revenue", example="revenue"),
            _f("gl_account", "Akun GL", default="4-1100", example="4-1100"),
            _f("negotiable", "Bisa nego", "bool", default=False, example="FALSE"),
            _f("active", "Aktif", "bool", default=True, example="TRUE"),
            _f("note", "Catatan", example=""),
        ],
    },
    {
        "key": "customers", "sheet": "Pelanggan", "collection": "customers", "icon": "contact",
        "desc": "Pembeli yang sudah ada. Kunci: NIK, bila kosong No. HP.",
        "key_fields": ["nik", "phone"],
        "fields": [
            _f("name", "Nama lengkap", required=True, example="Dewi Kartika"),
            _f("phone", "No. HP", "phone", example="08121111111"),
            _f("email", "Email", "email", example="dewi@email.com"),
            _f("nik", "NIK", example="3201234567890001"),
            _f("npwp", "NPWP", example="09.123.456.7-011.000"),
            _f("address", "Alamat", example="Jl. Melati No. 12, Bogor"),
            _f("occupation", "Pekerjaan", example="Wiraswasta"),
            _f("monthly_income", "Penghasilan/bulan (Rp)", "int", example="25000000"),
            _f("spouse_name", "Nama pasangan", example=""),
            _f("spouse_nik", "NIK pasangan", example=""),
            _f("heir_name", "Nama ahli waris", example=""),
            _f("heir_relation", "Hubungan ahli waris", example="Anak"),
            _f("notes", "Catatan", example=""),
        ],
    },
    {
        "key": "vendors", "sheet": "Vendor", "collection": "vendors", "icon": "truck",
        "desc": "Pemasok material/alat/jasa untuk PO & tagihan.",
        "key_fields": ["code"],
        "fields": [
            _f("code", "Kode vendor", required=True, example="VND-01"),
            _f("name", "Nama vendor", required=True, example="CV Sumber Beton"),
            _f("category", "Kategori", "enum", enum="vendor_category", default="material",
               example="material"),
            _f("npwp", "NPWP", example=""),
            _f("phone", "Telepon", "phone", example="08123456701"),
            _f("email", "Email", "email", example=""),
            _f("address", "Alamat", example=""),
            _f("pic_name", "Nama PIC", example="Hendra"),
            _f("payment_terms_days", "Termin bayar (hari)", "int", default=30, example="30"),
            _f("bank_name", "Bank", example="BCA"),
            _f("bank_account_no", "No. rekening", example="5220114455"),
            _f("bank_account_holder", "Atas nama", example="CV Sumber Beton"),
            _f("is_active", "Aktif", "bool", default=True, example="TRUE"),
            _f("note", "Catatan", example=""),
        ],
    },
    {
        "key": "subcontractors", "sheet": "Subkontraktor", "collection": "subcontractors",
        "icon": "hammer", "desc": "Subkon pelaksana pekerjaan (SPK, opname, retensi).",
        "key_fields": ["code"],
        "fields": [
            _f("code", "Kode", required=True, example="SUB-01"),
            _f("name", "Nama", required=True, example="CV Bangun Jaya"),
            _f("specialty", "Spesialisasi", "enum", enum="subcon_specialty", example="struktur"),
            _f("phone", "Telepon", "phone", example="08130000001"),
            _f("email", "Email", "email", example=""),
            _f("npwp", "NPWP", example=""),
            _f("address", "Alamat", example=""),
            _f("pic_name", "Nama PIC", example="Bapak Slamet"),
            _f("rating", "Rating (0-5)", "float", example="4.5"),
            _f("is_active", "Aktif", "bool", default=True, example="TRUE"),
            _f("notes", "Catatan", example=""),
        ],
    },
    {
        "key": "agents", "sheet": "Mitra", "collection": "agents", "icon": "handshake",
        "desc": "Agen/broker/referral. Kode kosong = dibuat otomatis (AGN/TAHUN/URUT).",
        "key_fields": ["code", "phone"],
        "fields": [
            _f("code", "Kode mitra", example="", desc="Kosongkan untuk mitra baru."),
            _f("name", "Nama", required=True, example="PT Griya Mitra Andalan"),
            _f("partner_kind", "Jenis mitra", "enum", required=True, enum="partner_kind",
               example="kantor_broker"),
            _f("entity_type", "Bentuk", "enum", enum="partner_entity_type", default="individual",
               example="company"),
            _f("company", "Perusahaan", example=""),
            _f("phone", "No. HP", "phone", required=True, example="08121230001",
               desc="Unik antar mitra."),
            _f("email", "Email", "email", example=""),
            _f("nik", "NIK", example=""),
            _f("npwp", "NPWP", example=""),
            _f("address", "Alamat", example=""),
            _f("pic_name", "Nama PIC", example=""),
            _f("pic_phone", "HP PIC", "phone", example=""),
            _f("bank_name", "Bank", example="BCA"),
            _f("bank_account", "No. rekening", example=""),
            _f("bank_account_name", "Atas nama", example=""),
            _f("status", "Status", "enum", enum="partner_status_import", default="active",
               example="active"),
        ],
    },
    {
        "key": "materials", "sheet": "Material", "collection": "materials", "icon": "package",
        "desc": "Material per proyek untuk stok & permintaan lapangan.",
        "key_fields": ["project_code", "code"],
        "fields": [
            _f("project_code", "Kode proyek", required=True, ref_to="projects", example="GRIYA1"),
            _f("code", "Kode material", required=True, example="SMN"),
            _f("name", "Nama", required=True, example="Semen Portland"),
            _f("uom", "Satuan", "enum", enum="uom", default="unit", example="sak"),
            _f("budget_qty", "Anggaran qty", "float", default=0, example="250"),
        ],
    },
    {
        "key": "workers", "sheet": "Tenaga Kerja", "collection": "workers", "icon": "hardhat",
        "desc": "Tenaga kerja harian (absensi & upah). Kunci: nama.",
        "key_fields": ["name"],
        "fields": [
            _f("name", "Nama", required=True, example="Pak Slamet"),
            _f("role", "Peran", "enum", required=True, enum="labor_role", example="mandor"),
            _f("daily_wage", "Upah harian (Rp)", "int", required=True, example="220000"),
            _f("phone", "No. HP", "phone", example=""),
            _f("project_codes", "Kode proyek (bisa banyak)", "list", ref_to="projects",
               desc="Dipisah ;", example="GRIYA1"),
            _f("is_active", "Aktif", "bool", default=True, example="TRUE"),
            _f("note", "Catatan", example=""),
        ],
    },
    {
        "key": "accounts", "sheet": "Bagan Akun", "collection": "accounts", "icon": "book",
        "desc": "Akun tambahan CoA. Akun bawaan sistem sudah ada; isi hanya akun kustom.",
        "key_fields": ["code"],
        "fields": [
            _f("code", "Kode akun", required=True, example="6-1900"),
            _f("name", "Nama akun", required=True, example="Beban Lain-lain"),
            _f("type", "Jenis", "enum", required=True, enum="account_type", example="expense"),
            _f("parent_code", "Kode induk", example=""),
            _f("is_active", "Aktif", "bool", default=True, example="TRUE"),
        ],
    },
    {
        "key": "bank_accounts", "sheet": "Rekening Bank", "collection": "bank_accounts",
        "icon": "landmark", "desc": "Rekening perusahaan untuk rekonsiliasi bank.",
        "key_fields": ["account_no"],
        "fields": [
            _f("name", "Nama rekening", required=True, example="Rekening Operasional"),
            _f("bank_name", "Bank", required=True, example="Bank Mandiri"),
            _f("account_no", "No. rekening", required=True, example="1440012345678"),
            _f("holder", "Atas nama", example="PT Perusahaan"),
            _f("gl_account_code", "Kode akun GL", required=True, ref_to="accounts",
               example="1-1200", desc="Akun kas/bank di Bagan Akun"),
            _f("opening_balance", "Saldo awal (Rp)", "int", default=0, example="0"),
            _f("is_active", "Aktif", "bool", default=True, example="TRUE"),
            _f("note", "Catatan", example=""),
        ],
    },
]

ENTITY_BY_KEY = {e["key"]: e for e in ENTITIES}
ENTITY_BY_SHEET = {e["sheet"].lower(): e for e in ENTITIES}

LOCAL_ENUMS = {
    "unit_import_status": {"available": "Tersedia", "blocked": "Diblokir",
                           "sold": "Terjual", "handed_over": "Serah terima",
                           "reserved": "Dipesan (hanya unit lama)", "booked": "Booking (hanya unit lama)"},
    "partner_status_import": {"active": "Aktif", "inactive": "Nonaktif"},
}


def enum_options(group: str) -> dict:
    """value → label untuk sheet 'Daftar Nilai' & validasi."""
    if group in LOCAL_ENUMS:
        return LOCAL_ENUMS[group]
    try:
        return dict(ref.labels(group))
    except Exception:
        return {v: v for v in ref.values(group)}


def enum_groups_used() -> list:
    seen = []
    for e in ENTITIES:
        for f in e["fields"]:
            if f["enum"] and f["enum"] not in seen:
                seen.append(f["enum"])
    return seen


def public_entities() -> list:
    return [{"key": e["key"], "sheet": e["sheet"], "collection": e["collection"],
             "desc": e["desc"], "key_fields": e["key_fields"],
             "fields": [{k: f[k] for k in ("key", "label", "type", "required", "enum", "desc")}
                        for f in e["fields"]]} for e in ENTITIES]
