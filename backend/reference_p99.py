"""Kosakata Fase 99 — tugas ad-hoc (jenis record terkait) & template header dokumen WhatsApp."""
from reference_groups import _o

GROUPS_P99 = {
    "task_related_type": {
        "label": "Jenis Record Terkait Tugas", "strict": True,
        "help": "Objek yang bisa dikaitkan pada tugas ad-hoc supervisor (CreateTaskDialog).",
        "options": [
            _o("lead", "Lead"), _o("deal", "Deal / Booking"), _o("unit", "Unit"),
            _o("customer", "Pembeli"), _o("project", "Proyek"),
        ],
    },
    "wa_template_header": {
        "label": "Header Template WhatsApp", "strict": True,
        "help": ("Format HEADER template Meta. `document` wajib untuk template UTILITY pengantar PDF "
                 "agar dokumen tetap bisa dikirim di luar sesi 24 jam saat live."),
        "options": [
            _o("none", "Tanpa header"), _o("text", "Teks"), _o("document", "Dokumen (PDF)"),
            _o("image", "Gambar"),
        ],
    },
}
