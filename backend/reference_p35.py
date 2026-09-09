"""SSOT reference registry — TAMBAHAN Fase 35 (Papan Mandor tahan sinyal hilang).

Alasan file terpisah sama seperti Fase 31/33/34: `reference.py` sudah menyentuh batas
gate compliance. Grup di sini digabungkan ke `reference.GROUPS` sehingga label yang
dilihat mandor tetap SATU sumber (`/api/reference`) — dulu peta label antrean offline
ditulis ulang di `services/offlineSync.js` sehingga bisa menyimpang dari kamus data.

Catatan penting: nilai di sini menggambarkan keadaan ANTREAN DI PERANGKAT (bukan status
dokumen di server). Sengaja dipisahkan dari `slik_status`/`ap_status` dsb. supaya tidak
ada kebingungan saat dibaca di tab Kamus Data.
"""


def _o(value: str, label: str) -> dict:
    return {"value": value, "label": label}


GROUPS_P35: dict = {
    # Keadaan satu pekerjaan yang tersimpan di perangkat mandor.
    "offline_queue_status": {
        "label": "Status Antrean Perangkat", "strict": True, "options": [
            _o("pending", "Menunggu jaringan"),
            _o("sending", "Sedang dikirim…"),
            _o("rejected", "Ditolak server — perlu tindakan"),
        ],
    },
    # Jenis aksi lapangan yang boleh diantrekan saat sinyal hilang. Daftar ini SENGAJA
    # pendek: hanya aksi milik pelaksana sendiri. Verifikasi/penolakan supervisor TIDAK
    # boleh diantrekan offline karena harus melihat bukti terbaru dari server.
    "offline_queue_kind": {
        "label": "Jenis Antrean Perangkat", "strict": True, "options": [
            _o("build_submit", "Ajukan hasil kerja"),
            _o("build_start", "Mulai dikerjakan"),
            # Fase 50B: antrean yang sama sekarang membawa pekerjaan lapangan lain yang
            # paling sering dikerjakan tanpa sinyal. Sebelumnya ketiga hal ini hanya bisa
            # dikirim saat online — jadi absensi seharian bisa hilang atau (kalau ditekan
            # ulang) masuk dua kali menjadi upah ganda.
            _o("attendance_submit", "Absensi tenaga kerja"),
            _o("field_diary", "Buku harian proyek"),
            _o("punch_create", "Temuan punch list baru"),
            _o("punch_status", "Ubah status temuan punch list"),
            _o("warranty_claim", "Klaim garansi"),
            _o("warranty_fix", "Bukti perbaikan garansi"),
            _o("handover_issue", "Berita acara serah terima"),
        ],
    },
}
