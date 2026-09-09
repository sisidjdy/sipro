"""SSOT reference registry — TAMBAHAN Fase 50 (Serah Terima Unit, Garansi & Klaim Pasca-Huni).

Digabungkan ke `reference.GROUPS` lewat `_PHASES` di `reference.py`, jadi validator backend,
`/api/reference`, dan tab Kamus Data otomatis mengenalinya — layar TIDAK PERNAH menulis label
enum sendiri.

Lubang nyata yang ditutup Fase 50A (hasil audit kode terhadap API nyata):

1. **Serah terima unit tidak pernah terjadi di sistem.** Kamus `unit_status` sudah punya nilai
   `handed_over` sejak Fase 39, tetapi TIDAK ADA SATU JALAN pun yang menuliskannya: tidak ada
   berita acara (BAST) bernomor, tidak ada daftar periksa sebelum kunci diserahkan, dan
   `POST /ar/{deal}/bast` hanya mengakui pendapatan di buku besar. Akibatnya "rumah sudah
   diserahkan" hanya hidup di kepala orang: tanggal serah terima tidak bisa dibuktikan, dan
   semua kewajiban yang MULAI dari tanggal itu (garansi) tidak punya titik nol.
2. **Garansi bangunan tidak punya masa.** Setelan `retention.months` menyebut "masa retensi /
   garansi bangunan" sebagai SATU angka untuk semua pekerjaan — padahal struktur, atap,
   plumbing, dan finishing punya masa yang berbeda. Tanpa masa per bagian, keluhan pembeli
   tidak bisa dijawab "masih garansi" atau "sudah lewat" dengan dasar.
3. **Klaim garansi tidak punya jalur kerja.** Komplain pasca-huni masuk sebagai keluhan CS,
   lalu berhenti di sana: tidak melahirkan pekerjaan perbaikan yang bisa dilacak, tidak
   menuntut bukti foto perbaikan, tidak ada pemisahan tugas (yang mengerjakan = yang
   memeriksa), dan pembeli tidak pernah dimintai pengakuan bahwa perbaikannya benar selesai.
"""


def _o(value: str, label: str) -> dict:
    return {"value": value, "label": label}


GROUPS_P50: dict = {
    # ------------------------------------------------- 50A daftar periksa serah terima
    "handover_check_item": {
        "label": "Daftar periksa serah terima",
        "strict": True,
        "help": "Pemeriksaan yang dijalankan sebelum berita acara serah terima diterbitkan.",
        "options": [
            _o("pembangunan_selesai", "Pembangunan rumah sudah selesai"),
            _o("punch_terbuka", "Tidak ada temuan punch list yang masih terbuka"),
            _o("inspeksi_serah_terima", "Inspeksi serah terima sudah lolos"),
            _o("pelunasan_belum", "Kewajiban pembayaran pembeli sudah beres"),
            _o("dokumen_wajib_kurang", "Dokumen wajib serah terima sudah lengkap"),
            _o("bast_sudah_terbit", "Belum pernah diserahterimakan"),
        ],
    },
    "handover_check_state": {
        "label": "Hasil pemeriksaan serah terima",
        "strict": True,
        "options": [
            _o("ok", "Beres"),
            _o("blocking", "Menahan serah terima"),
            _o("warning", "Perlu diperhatikan (tidak menahan)"),
            _o("missing_data", "Belum ada data"),
        ],
    },
    "handover_state": {
        "label": "Status Berita Acara Serah Terima",
        "strict": True,
        "options": [
            _o("issued", "Sudah diserahterimakan"),
            _o("cancelled", "Dibatalkan (salah terbit)"),
        ],
    },
    # ------------------------------------------------------------- 50A masa garansi
    "warranty_category": {
        "label": "Bagian yang Digaransi",
        "strict": True,
        "help": ("Masa garansi berbeda per bagian pekerjaan; lamanya diatur di Pusat "
                 "Konfigurasi \u2192 Serah Terima & Garansi."),
        "options": [
            _o("struktur", "Struktur (pondasi, kolom, balok, sloof)"),
            _o("atap_plafon", "Atap & plafon (kebocoran)"),
            _o("dinding_lantai", "Dinding & lantai (keramik, retak rambut)"),
            _o("plumbing", "Sanitasi & plumbing (air bersih/kotor)"),
            _o("listrik", "Instalasi listrik"),
            _o("kusen", "Kusen, pintu & jendela"),
            _o("finishing", "Finishing (cat, nat, aksesori)"),
        ],
    },
    "warranty_state": {
        "label": "Keadaan Masa Garansi",
        "strict": True,
        "options": [
            _o("aktif", "Masih bergaransi"),
            _o("hampir_habis", "Hampir habis"),
            _o("habis", "Masa garansi sudah lewat"),
        ],
    },
    # --------------------------------------------------------- 50A klaim garansi
    "warranty_claim_state": {
        "label": "Status Klaim Garansi",
        "strict": True,
        "options": [
            _o("diajukan", "Diajukan (menunggu keputusan)"),
            _o("ditolak", "Ditolak beralasan"),
            _o("dikerjakan", "Diterima & sedang diperbaiki"),
            _o("selesai", "Perbaikan selesai (menunggu pemeriksaan)"),
            _o("diverifikasi", "Sudah diperiksa (menunggu pengakuan pembeli)"),
            _o("ditutup", "Ditutup (diakui pembeli)"),
        ],
    },
    "warranty_claim_source": {
        "label": "Asal Klaim Garansi",
        "strict": True,
        "options": [
            _o("portal_pembeli", "Portal pembeli"),
            _o("komplain_cs", "Komplain lewat CS"),
            _o("internal", "Temuan internal"),
        ],
    },
    "warranty_reject_reason": {
        "label": "Sebab Klaim Ditolak",
        "strict": True,
        "help": "Klaim yang ditolak tetap tercatat supaya pembeli mendapat jawaban tertulis.",
        "options": [
            _o("lewat_masa_garansi", "Masa garansi bagian ini sudah lewat"),
            _o("di_luar_lingkup", "Di luar lingkup garansi bangunan"),
            _o("kelalaian_pemakaian", "Kerusakan akibat pemakaian/perubahan pemilik"),
            _o("duplikat", "Sudah ada klaim yang sama"),
        ],
    },
}
