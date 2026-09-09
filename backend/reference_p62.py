"""SSOT reference registry — TAMBAHAN Fase 62 (dokumen lapangan & peringatan tunggakan).

Tingkat surat peringatan dan jenis lampiran SPK sebelumnya tidak punya kosakata: kalau
dibiarkan bebas, "SP2" dan "Peringatan 2" akan hidup berdampingan pada data yang sama dan
laporan tidak bisa menghitungnya.
"""


def _o(value: str, label: str) -> dict:
    return {"value": value, "label": label}


GROUPS_P62: dict = {
    "warning_level": {
        "label": "Tingkat Surat Peringatan", "strict": True, "options": [
            _o("1", "SP1 — Peringatan pertama"),
            _o("2", "SP2 — Peringatan kedua"),
            _o("3", "SP3 — Peringatan ketiga & terakhir"),
        ],
    },
    "spk_attachment_kind": {
        "label": "Jenis Lampiran SPK", "strict": True, "options": [
            _o("gambar_kerja", "Gambar kerja"),
            _o("spesifikasi", "Spesifikasi teknis"),
            _o("lainnya", "Lampiran lain"),
        ],
    },
}
