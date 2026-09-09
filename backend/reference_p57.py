"""SSOT reference registry — TAMBAHAN Fase 57A (skema pembayaran yang bisa dikonfigurasi).

Kenapa perlu? Sebelum ini termin cash keras / cash bertahap / KPR disusun di dalam KODE
(`contracts_engine.scheme_terms_spec`) dari beberapa ambang di Pusat Konfigurasi. Akibatnya
pengembang yang bisnisnya berbeda — DP nominal, 12× cicilan, pelunasan mengikuti peristiwa
lain — tidak punya jalan lain selain minta ubah kode. Sebagai SaaS itu tidak bisa diterima.

Semua kode di bawah dipakai layar & dokumen sebagai LABEL. Kode baru wajib mendarat di sini
lebih dahulu; kalau tidak, layar akan menampilkan kode mentah kepada pemakai.
"""


def _o(value: str, label: str, **extra) -> dict:
    return {"value": value, "label": label, **extra}


GROUPS_P57: dict = {
    "payment_scheme_kind": {
        "label": "Jenis Skema Pembayaran",
        "strict": True,
        "help": ("Jenis menentukan TAHAP LEGAL dan komponen biaya yang berlaku: hanya jenis "
                 "KPR yang punya akad kredit, biaya bank, asuransi, dan plafon. Nama & "
                 "termin boleh apa saja, tetapi jenisnya harus jujur."),
        "options": [
            _o("cash_keras", "Cash keras (tunai, pelunasan sekali)"),
            _o("cash_bertahap", "Cash bertahap (cicilan langsung ke developer)"),
            _o("kpr", "KPR (pembiayaan bank)"),
        ],
    },
    "term_basis": {
        "label": "Dasar Nilai Termin",
        "strict": True,
        "options": [
            _o("percent", "Persen dari harga jual"),
            _o("amount", "Nominal tetap (Rp)"),
            _o("remaining", "Sisa harga (setelah termin lain)"),
        ],
    },
    "term_due_mode": {
        "label": "Cara Menentukan Jatuh Tempo",
        "strict": True,
        "help": ("Jatuh tempo yang bergantung PERISTIWA (pembangunan 100%, akad kredit) "
                 "tidak boleh dicetak sebagai tanggal pasti — layar & dokumen wajib "
                 "mengatakan bahwa tanggalnya perkiraan."),
        "options": [
            _o("offset_days", "Sejumlah hari setelah kontrak aktif"),
            _o("monthly_day", "Tanggal tertentu setiap bulan"),
            _o("event", "Mengikuti peristiwa (tanggal belum pasti)"),
        ],
    },
    "term_due_event": {
        "label": "Peristiwa Pemicu Jatuh Tempo",
        "strict": True,
        "options": [
            _o("build_start", "Sebelum pembangunan dimulai"),
            _o("build_complete", "Setelah pembangunan 100%"),
            _o("akad_kredit", "Setelah akad kredit"),
            _o("ppjb", "Setelah PPJB ditandatangani"),
            _o("bast", "Setelah serah terima (BAST)"),
            _o("ajb", "Setelah AJB"),
        ],
    },
    "scheme_block": {
        "label": "Sebab Skema Belum Bisa Dipakai/Disimpan",
        "strict": True,
        "options": [
            _o("tanpa_termin", "Belum ada satu pun termin"),
            _o("persen_bukan_100", "Jumlah persen termin bukan 100%"),
            _o("sisa_ganda", "Lebih dari satu termin 'sisa harga'"),
            _o("sisa_bukan_terakhir", "Termin 'sisa harga' harus paling akhir"),
            _o("persen_melebihi_100", "Persen termin melebihi/menyamai 100% padahal ada sisa"),
            _o("nominal_tanpa_sisa", "Ada termin nominal tetapi tidak ada termin 'sisa harga'"),
            _o("nilai_tidak_wajar", "Nilai termin harus lebih besar dari nol"),
            _o("kode_dipakai", "Kode skema sudah dipakai skema lain"),
            _o("skema_terpakai", "Skema sedang dipakai kontrak yang uangnya sudah masuk"),
            _o("bukan_proyek_ini", "Skema tidak berlaku untuk proyek kontrak ini"),
            _o("jenis_beda", "Jenis skema berbeda dengan jenis kontrak"),
            _o("sudah_ada_penerimaan", "Sudah ada penerimaan pada kontrak ini"),
        ],
    },
}
