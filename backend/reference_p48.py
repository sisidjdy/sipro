"""SSOT reference registry — TAMBAHAN Fase 48 (Pengadaan & Subkon lanjutan).

Digabungkan ke `reference.GROUPS` lewat `_PHASES` di `reference.py`, jadi validator backend,
`/api/reference`, dan tab Kamus Data otomatis mengenalinya — layar TIDAK PERNAH menulis label
enum sendiri.

Sembilan lubang nyata yang ditutup Fase 48 (hasil audit `scripts/_audit48.py` terhadap API
nyata, bukan dugaan):

1. **Vendor hanya TEKS BEBAS** di PO/tagihan (`/vendors` → 404). Salah tulis nama = vendor
   "baru"; tidak ada NPWP, termin bayar, rekening, maupun riwayat.
2. **Tidak ada daftar harga vendor** sehingga harga PO tidak punya pembanding — tidak ada
   dasar "harga wajar".
3. **Tidak ada evaluasi vendor/subkon berbukti**; `subcontractors.rating` hanya angka yang
   diisi tangan tanpa bukti.
4. **Permintaan material yang disetujui tidak punya jalan ke pembelian.** Bila stok kurang,
   pembelian lahir tanpa jejak permintaan lapangan.
5. **GRN tidak bisa dibalik** (retur barang) — barang rusak/salah kirim/kelebihan terima
   membuat stok & 3-way match berbohong.
6. **Retensi subkon hanya menumpuk** dan tidak pernah bisa dicairkan (tidak ada daftar
   retensi, masa pemeliharaan, maupun gerbang pencairan).
7. **Tidak ada uang muka & potongan/denda subkon** padahal pembayaran termin nyata selalu
   dipotong hal-hal itu.
8. **Stok belum punya** transfer antar proyek, batas stok minimum, dan nilai persediaan.
9. **3-way match hanya MEMBERI TANDA**, tidak pernah MENAHAN tagihan yang melebihi barang
   diterima.
"""


def _o(value: str, label: str) -> dict:
    return {"value": value, "label": label}


GROUPS_P48: dict = {
    # ---------------- 48A master vendor & harga ----------------
    "vendor_category": {
        "label": "Kategori Vendor", "strict": True, "options": [
            _o("material", "Pemasok material"),
            _o("alat", "Penyewaan alat"),
            _o("jasa", "Penyedia jasa"),
            _o("subkon", "Subkontraktor pekerjaan"),
        ],
    },
    "price_source": {
        "label": "Sumber Harga", "strict": True, "options": [
            _o("manual", "Dicatat manual (survei harga)"),
            _o("penawaran", "Dari penawaran vendor"),
            _o("kontrak", "Harga kontrak berjangka"),
            _o("realisasi", "Dari realisasi PO terakhir"),
        ],
    },
    "price_check_state": {
        "label": "Hasil Uji Harga", "strict": True, "options": [
            _o("wajar", "Wajar (di dalam ambang)"),
            _o("lebih_murah", "Lebih murah dari acuan"),
            _o("di_atas_acuan", "Di atas harga acuan (perlu alasan)"),
            _o("no_reference", "Belum ada harga acuan"),
        ],
    },
    # ---------------- 48B permintaan → PO, retur, 3-way ----------------
    "po_source": {
        "label": "Asal PO", "strict": True, "options": [
            _o("manual", "Dibuat manual"),
            _o("requisition", "Dari permintaan material lapangan"),
        ],
    },
    "return_kind": {
        "label": "Sebab Retur Barang", "strict": True, "options": [
            _o("rusak", "Barang rusak / cacat"),
            _o("salah_kirim", "Salah kirim (tidak sesuai PO)"),
            _o("kelebihan", "Kelebihan kirim"),
            _o("mutu", "Ditolak mutu (uji lapangan)"),
        ],
    },
    "threeway_state": {
        "label": "Keadaan 3-Way Match", "strict": True, "options": [
            _o("matched", "Cocok (boleh ditagih)"),
            _o("held", "DITAHAN — melebihi barang diterima/PO"),
            _o("overridden", "Ditahan lalu diterobos manajer keuangan (beralasan)"),
        ],
    },
    # ---------------- 48C uang muka, potongan, retensi ----------------
    "advance_state": {
        "label": "Status Uang Muka", "strict": True, "options": [
            _o("draft", "Diajukan"),
            _o("approved", "Disetujui (menunggu pembayaran)"),
            _o("paid", "Sudah dibayar"),
            _o("closed", "Selesai (habis dipotong termin)"),
            _o("rejected", "Ditolak"),
        ],
    },
    "deduction_kind": {
        "label": "Jenis Potongan Termin", "strict": True, "options": [
            _o("advance", "Angsuran uang muka"),
            _o("penalty", "Denda keterlambatan"),
            _o("material", "Bon material dari gudang kami"),
            _o("other", "Potongan lain (beralasan)"),
        ],
    },
    "deduction_state": {
        "label": "Status Potongan", "strict": True, "options": [
            _o("pending", "Menunggu termin berikutnya"),
            _o("applied", "Sudah dipotong di termin"),
            _o("cancelled", "Dibatalkan (beralasan)"),
        ],
    },
    "retention_state": {
        "label": "Status Retensi", "strict": True, "options": [
            _o("held", "Ditahan"),
            _o("release_requested", "Pencairan diajukan"),
            _o("released", "Sudah dicairkan"),
        ],
    },
    "retention_block_code": {
        "label": "Sebab Retensi Belum Bisa Dicairkan", "strict": True, "options": [
            _o("maintenance_active", "Masa pemeliharaan belum lewat"),
            _o("punch_open", "Masih ada temuan punch list terbuka"),
            _o("already_released", "Retensi sudah dicairkan"),
            _o("claim_not_approved", "Termin sumber retensi belum disetujui"),
        ],
    },
    # ---------------- 48D evaluasi ----------------
    "eval_criteria": {
        "label": "Kriteria Penilaian", "strict": True, "options": [
            _o("timeliness", "Ketepatan waktu"),
            _o("quality", "Mutu barang/pekerjaan"),
            _o("price", "Kewajaran harga"),
            _o("service", "Pelayanan & komunikasi"),
            _o("safety", "Keselamatan kerja (K3)"),
        ],
    },
    "eval_grade": {
        "label": "Peringkat Vendor", "strict": True, "options": [
            _o("A", "A — sangat baik (≥ 85)"),
            _o("B", "B — baik (70–84)"),
            _o("C", "C — cukup (55–69)"),
            _o("D", "D — perlu pembinaan (< 55)"),
            _o("missing_data", "Belum ada data (tidak boleh dikarang)"),
        ],
    },
    # ---------------- 48E stok ----------------
    "stock_alert_state": {
        "label": "Peringatan Stok", "strict": True, "options": [
            _o("ok", "Aman (di atas batas minimum)"),
            _o("below_min", "Di bawah batas minimum"),
            _o("empty", "Stok habis"),
            _o("no_min", "Batas minimum belum ditetapkan"),
        ],
    },
}


def _labels(group: str) -> dict:
    return {o["value"]: o["label"] for o in GROUPS_P48[group]["options"]}


VENDOR_CATEGORY_LABEL = _labels("vendor_category")
PRICE_CHECK_LABEL = _labels("price_check_state")
RETURN_KIND_LABEL = _labels("return_kind")
THREEWAY_LABEL = _labels("threeway_state")
ADVANCE_LABEL = _labels("advance_state")
DEDUCTION_KIND_LABEL = _labels("deduction_kind")
DEDUCTION_STATE_LABEL = _labels("deduction_state")
RETENTION_LABEL = _labels("retention_state")
BLOCK_LABEL = _labels("retention_block_code")
STOCK_ALERT_LABEL = _labels("stock_alert_state")

# Ambang & kebijakan — DITULIS SEKALI di sini supaya engine, gate, dan layar memakai angka
# yang sama (tidak ada dua kebenaran).
PRICE_WARN_PCT = 10.0          # harga PO di atas acuan sebanyak ini → peringatan beralasan
MAINTENANCE_DAYS_DEFAULT = 90  # masa pemeliharaan bawaan bila SPK tidak menyebutkan
THREEWAY_TOLERANCE = 0.005     # 0,5% toleransi pembulatan (sama dengan procurement_router)
EVAL_WEIGHTS = {"timeliness": 35, "quality": 35, "price": 20, "service": 10}

# Akun GL yang dipakai Fase 48.
GL_BANK = "1-1200"
GL_INVENTORY = "1-1400"
GL_WIP = "1-1600"
GL_SUBCON_ADVANCE = "1-1800"    # Uang Muka Subkontraktor & Vendor (ditambahkan ke CoA)
GL_AP = "2-1100"
GL_RETENTION_PAYABLE = "2-1200"
GL_OTHER_INCOME = "4-1200"

# Potongan termin → akun kredit lawannya (dipakai `gl_engine._gl_ap_approved`).
DEDUCTION_GL = {
    "advance": GL_SUBCON_ADVANCE,
    "penalty": GL_OTHER_INCOME,
    "material": GL_INVENTORY,
    "other": GL_OTHER_INCOME,
}
