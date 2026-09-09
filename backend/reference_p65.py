"""SSOT reference registry — TAMBAHAN Fase 65 (saluran notifikasi).

Preferensi notifikasi memperkenalkan tiga saluran (`inapp`, `push`, `wa`). Labelnya harus
tunggal: dialog preferensi, gate, dan kelak laporan audit harus menyebutnya dengan kata
yang sama, jadi daftarnya hidup di registry seperti kosakata enum lainnya.
"""


def _o(value: str, label: str) -> dict:
    return {"value": value, "label": label}


GROUPS_P65: dict = {
    "notification_channel": {
        "label": "Saluran Notifikasi", "strict": True, "options": [
            _o("inapp", "Masuk daftar & lonceng"),
            _o("push", "Dorongan seketika"),
            _o("wa", "Ikut ringkasan WhatsApp"),
        ],
    },
}
