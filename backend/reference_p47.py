"""SSOT reference registry — TAMBAHAN Fase 47 (Uang masuk & pekerjaan yang bisa dipertanggungjawabkan).

Kenapa berkas terpisah: `reference.py` sudah menyentuh batas gate compliance. Grup di sini
digabungkan ke `reference.GROUPS` (lihat `_PHASES` di `reference.py`) sehingga tetap SATU
registry — validator backend, `/api/reference`, dan tab Kamus Data otomatis mengenalinya dan
layar TIDAK PERNAH menuliskan label enum sendiri.

Empat celah nyata yang ditutup Fase 47 (semua diverifikasi dengan membaca kode, bukan dugaan):

1. **Uang masuk tidak pernah dibandingkan dengan rekening.** Penerimaan hanya bisa dicatat
   manual (`POST /api/ar/receipts`); tidak ada mutasi bank, tidak ada daftar "belum cocok".
   Akibatnya "sudah bayar" versi sistem tidak bisa dibuktikan ke rekening bank.
2. **Pelanggan tidak punya jalan resmi menyetor bukti transfer.** Portal 100% baca-saja,
   sehingga bukti transfer berkeliaran di WhatsApp dan status pembayaran jadi tafsir.
3. **Tidak ada penawaran/simulasi harga.** Sales menghitung di luar sistem, sehingga angka
   yang dijanjikan ke pembeli tidak bisa direkonstruksi dan diskon tidak berjejak.
4. **Tenaga kerja harian hanya sebuah ANGKA di buku harian** (`site_diaries.workforce`).
   Tidak ada daftar orang, absensi, upah, maupun biaya upah yang masuk pembukuan —
   padahal `docs/v2/29` §1 menjanjikan "absensi mandor" di tab Lapangan.
"""


def _o(value: str, label: str) -> dict:
    return {"value": value, "label": label}


GROUPS_P47: dict = {
    # ---------------- mutasi rekening ----------------
    "bank_txn_direction": {
        "label": "Arah Mutasi Bank", "strict": True, "options": [
            _o("in", "Uang masuk (kredit rekening)"),
            _o("out", "Uang keluar (debit rekening)"),
        ],
    },
    "bank_match_state": {
        "label": "Status Pencocokan", "strict": True, "options": [
            _o("unmatched", "Belum dicocokkan"),
            _o("matched", "Sudah dicocokkan"),
            _o("ignored", "Diabaikan (beralasan)"),
        ],
    },
    "bank_match_kind": {
        "label": "Jenis Pencocokan", "strict": True, "options": [
            _o("ar_deal", "Pembayaran pembeli (termin AR)"),
            _o("payment_intake", "Bukti transfer dari portal pelanggan"),
            _o("ap_bill", "Pembayaran tagihan vendor (AP)"),
            _o("labor_payroll", "Pembayaran upah tenaga kerja"),
            _o("bank_fee", "Biaya administrasi/bunga bank (beban)"),
            _o("bank_interest", "Jasa giro / bunga diterima"),
        ],
    },
    "import_row_state": {
        "label": "Hasil Baris Impor", "strict": True, "options": [
            _o("new", "Baru (akan ditulis)"),
            _o("updated", "Diperbarui (keterangan/saldo berubah)"),
            _o("unchanged", "Sudah ada, tidak berubah"),
            _o("rejected", "Ditolak (data tidak sah)"),
        ],
    },
    # ---------------- bukti transfer dari pelanggan ----------------
    "payment_intake_state": {
        "label": "Status Bukti Transfer", "strict": True, "options": [
            _o("pending", "Menunggu verifikasi finance"),
            _o("verified", "Terverifikasi (tagihan sudah berkurang)"),
            _o("rejected", "Ditolak (dengan alasan)"),
        ],
    },
    # ---------------- penawaran (quotation) ----------------
    "quotation_state": {
        "label": "Status Penawaran", "strict": True, "options": [
            _o("draft", "Draf"),
            _o("awaiting_approval", "Menunggu persetujuan diskon"),
            _o("approved", "Disetujui"),
            _o("sent", "Terkirim ke calon pembeli"),
            _o("converted", "Menjadi reservasi/SPR"),
            _o("expired", "Kedaluwarsa (masa berlaku habis)"),
            _o("rejected", "Diskon ditolak"),
            _o("superseded", "Diganti revisi terbaru"),
        ],
    },
    "estimate_state": {
        "label": "Kelengkapan Perhitungan", "strict": True, "options": [
            _o("complete", "Lengkap (bisa dihitung)"),
            _o("missing_data", "Belum ada data (tidak boleh dikarang)"),
        ],
    },
    # ---------------- tenaga kerja harian ----------------
    "labor_role": {
        "label": "Peran Tenaga Kerja", "strict": True, "options": [
            _o("mandor", "Mandor"),
            _o("tukang", "Tukang"),
            _o("laden", "Laden / pembantu tukang"),
            _o("operator", "Operator alat"),
            _o("keamanan", "Keamanan proyek"),
        ],
    },
    "attendance_status": {
        "label": "Kehadiran", "strict": True, "options": [
            _o("full", "Hadir penuh"),
            _o("half", "Setengah hari"),
            _o("absent", "Tidak hadir (tanpa upah)"),
            _o("leave", "Izin / sakit (tanpa upah)"),
        ],
    },
    "payroll_state": {
        "label": "Status Rekap Upah", "strict": True, "options": [
            _o("draft", "Draf (bisa diubah)"),
            _o("submitted", "Diajukan ke keuangan"),
            _o("approved", "Disetujui (menunggu pembayaran)"),
            _o("paid", "Sudah dibayar"),
            _o("rejected", "Ditolak keuangan"),
        ],
    },
}


def _labels(group: str) -> dict:
    return {o["value"]: o["label"] for o in GROUPS_P47[group]["options"]}


DIRECTION_LABEL = _labels("bank_txn_direction")
MATCH_STATE_LABEL = _labels("bank_match_state")
MATCH_KIND_LABEL = _labels("bank_match_kind")
ROW_STATE_LABEL = _labels("import_row_state")
INTAKE_LABEL = _labels("payment_intake_state")
QUOTATION_LABEL = _labels("quotation_state")
LABOR_ROLE_LABEL = _labels("labor_role")
ATTENDANCE_LABEL = _labels("attendance_status")
PAYROLL_LABEL = _labels("payroll_state")

# Kehadiran yang MENGHASILKAN upah + faktor harinya. Ditulis SEKALI di sini supaya papan
# absensi, rekap upah, dan gate memakai angka yang sama (tidak ada dua rumus).
ATTENDANCE_DAY_FACTOR = {"full": 1.0, "half": 0.5, "absent": 0.0, "leave": 0.0}
# Pencocokan yang boleh DIBATALKAN dari layar rekonsiliasi. Pembayaran vendor & upah
# sengaja TIDAK ada di sini: pembatalannya menyentuh dokumen lain (tagihan AP, rekap upah)
# sehingga harus dibatalkan dari halaman aslinya agar tidak ada dua kebenaran.
UNMATCHABLE_KINDS = ("ar_deal", "payment_intake", "bank_fee", "bank_interest")
# Akun GL yang dipakai pencocokan non-subledger (biaya bank & jasa giro).
GL_BANK = "1-1200"
GL_BANK_FEE = "6-1600"
GL_OTHER_INCOME = "4-1200"
GL_CONTRACT_LIABILITY = "2-1400"
GL_WIP = "1-1600"
GL_WAGE_PAYABLE = "2-1100"
