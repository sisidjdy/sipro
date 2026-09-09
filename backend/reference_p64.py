"""SSOT reference registry — TAMBAHAN Fase 64 (kategori pusat notifikasi).

Kategori notifikasi dihitung dari data yang sudah ada (`notif_center.category_of`), tetapi
LABELNYA harus tunggal: sebelum ini layar notifikasi tidak punya kategori sama sekali, dan
kalau tiap panel menulis daftarnya sendiri, "Keuangan" dan "Finance" akan hidup bersamaan.
"""


def _o(value: str, label: str) -> dict:
    return {"value": value, "label": label}


GROUPS_P64: dict = {
    "notification_category": {
        "label": "Kategori Notifikasi", "strict": True, "options": [
            _o("tugas", "Tugas & tenggat"),
            _o("keuangan", "Keuangan"),
            _o("penjualan", "Penjualan & pembeli"),
            _o("proyek", "Proyek & lapangan"),
            _o("layanan", "Keluhan & garansi"),
            _o("sebutan", "Sebutan (@mention)"),
            _o("sistem", "Info sistem"),
        ],
    },
    "notification_state": {
        "label": "Keadaan Notifikasi", "strict": True, "options": [
            _o("action", "Perlu tindakan"),
            _o("unread", "Belum dibaca"),
            _o("read", "Sudah dilihat"),
            _o("all", "Semua"),
        ],
    },
}
