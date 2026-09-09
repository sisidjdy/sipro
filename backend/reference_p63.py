"""SSOT reference registry — TAMBAHAN Fase 63 (agenda kerja, bukan hanya janji temu jual).

Sampai Fase 62 `appointment_type` hanya mengenal empat jenis yang semuanya berbau penjualan
(meeting, survey lokasi, telepon, tanda tangan), sehingga rapat internal, kunjungan proyek,
dan rapat vendor/subkontraktor tidak punya tempat: orang menuliskannya sebagai "meeting"
lalu laporan tidak bisa memisahkan mana agenda jual dan mana agenda kerja.

Grup `appointment_type` di bawah SENGAJA memuat ulang empat nilai lama supaya data yang sudah
ada tetap sah (registry dimuat dengan `GROUPS.update`, jadi definisi ini menggantikan yang
lama secara utuh).
"""


def _o(value: str, label: str) -> dict:
    return {"value": value, "label": label}


GROUPS_P63: dict = {
    "appointment_type": {
        "label": "Jenis Agenda", "strict": True, "options": [
            # --- agenda penjualan (dipakai sejak Fase 14) ---
            _o("meeting", "Meeting"), _o("survey", "Survey lokasi"),
            _o("call", "Telepon"), _o("signing", "Tanda tangan"),
            # --- agenda kerja non-penjualan (Fase 63) ---
            _o("internal_meeting", "Rapat internal"),
            _o("site_visit", "Kunjungan proyek"),
            _o("vendor_meeting", "Rapat vendor/subkontraktor"),
            _o("other", "Lain-lain"),
        ],
    },
    "agenda_kind": {
        "label": "Golongan Agenda", "strict": True, "options": [
            _o("sales", "Terkait lead/pembeli"),
            _o("internal", "Internal (tanpa lead)"),
        ],
    },
}
