"""SSOT reference registry — TAMBAHAN Fase 34 (jadwal massal & geser serentak).

Alasan file terpisah sama seperti Fase 31/33: `reference.py` sudah menyentuh batas
gate compliance. Grup di sini digabungkan ke `reference.GROUPS` sehingga dropdown
frontend tetap SATU sumber (`/api/reference`) dan tidak ada nilai yang diketik bebas.
"""


def _o(value: str, label: str) -> dict:
    return {"value": value, "label": label}


GROUPS_P34: dict = {
    # Pola gelombang penjadwalan massal — realitas lapangan: tukang & material tidak
    # bisa masuk ke 20 rumah pada hari yang sama.
    "build_bulk_wave": {
        "label": "Pola Mulai Pembangunan", "strict": True, "options": [
            _o("same", "Serentak — semua unit mulai tanggal yang sama"),
            _o("per_block", "Bertahap per blok — tiap blok mundur beberapa hari"),
            _o("per_unit", "Bertahap per unit — tiap unit mundur beberapa hari"),
        ],
    },
    # Cakupan penggeseran tanggal (dipakai dialog geser massal).
    "build_shift_scope": {
        "label": "Cakupan Penggeseran", "strict": True, "options": [
            _o("project", "Seluruh unit terjadwal di proyek ini"),
            _o("block", "Satu blok/cluster"),
            _o("selection", "Unit yang saya pilih sendiri"),
        ],
    },
}

WAVE_LABEL = {o["value"]: o["label"] for o in GROUPS_P34["build_bulk_wave"]["options"]}
