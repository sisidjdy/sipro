"""SSOT reference registry — TAMBAHAN Fase 28b (Site Plan lanjutan & Showroom publik).

Kenapa file terpisah? `reference.py` sudah mendekati batas compliance (≤800 baris,
gate `validate_compliance`). Grup di sini digabungkan ke `reference.GROUPS` sehingga
tetap SATU registry: satu-satunya sumber nilai enum untuk backend (validator Annotated)
maupun frontend (`GET /api/reference` → ReferenceSelect / Kamus Data).

`unit_orientation` menjadikan orientasi kavling data terkontrol (sebelumnya teks bebas
"Utara"/"utara"/"UTARA" — tidak bisa difilter maupun diagregasi).
"""


def _o(value: str, label: str) -> dict:
    return {"value": value, "label": label}


GROUPS_P28: dict = {
    "unit_orientation": {
        "label": "Orientasi Kavling", "strict": True, "options": [
            _o("utara", "Utara"), _o("timur_laut", "Timur laut"),
            _o("timur", "Timur"), _o("tenggara", "Tenggara"),
            _o("selatan", "Selatan"), _o("barat_daya", "Barat daya"),
            _o("barat", "Barat"), _o("barat_laut", "Barat laut"),
        ],
    },
}

# Sinonim orientasi (data lama berbentuk teks bebas berkapital).
SYNONYMS_P28: dict = {
    "unit_orientation": {
        "north": "utara", "east": "timur", "south": "selatan", "west": "barat",
        "timurlaut": "timur_laut", "baratlaut": "barat_laut", "baratdaya": "barat_daya",
        "u": "utara", "t": "timur", "s": "selatan", "b": "barat",
    },
}
