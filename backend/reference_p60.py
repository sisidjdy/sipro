"""SSOT reference registry — TAMBAHAN Fase 60 (konfigurasi layout dokumen).

Tagline/bidang usaha pada kop surat sebelumnya diketik bebas, sehingga satu organisasi
bisa menuliskan bidang usahanya berbeda-beda antar dokumen. Grup ini menjadikannya
kosakata bersama, tetap `dynamic` supaya daftar bisa bertumbuh dari data yang ada.
"""


def _o(value: str, label: str) -> dict:
    return {"value": value, "label": label}


GROUPS_P60: dict = {
    "business_field": {
        "label": "Bidang Usaha", "strict": False, "dynamic": True, "options": [
            _o("Pengembang Properti", "Pengembang Properti"),
            _o("Pengembang Perumahan & Kawasan", "Pengembang Perumahan & Kawasan"),
            _o("Kontraktor Umum", "Kontraktor Umum"),
            _o("Konsultan Perencana & Pengawas", "Konsultan Perencana & Pengawas"),
            _o("Manajemen Properti", "Manajemen Properti"),
            _o("Agen & Pemasaran Properti", "Agen & Pemasaran Properti"),
            _o("Supplier Material Bangunan", "Supplier Material Bangunan"),
        ],
    },
}
