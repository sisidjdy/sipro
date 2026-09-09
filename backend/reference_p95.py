"""Kosakata Fase 95–97 — integrasi WhatsApp resmi (gateway, outbox, template Meta, opt-out)."""
from reference_groups import _o

GROUPS_P95 = {
    "wa_send_status": {
        "label": "Status Kirim WhatsApp", "strict": True,
        "help": ("`simulated` = pesan TIDAK dikirim ke Meta (mode simulasi, tercatat jujur). "
                 "`failed` = Meta/jaringan menolak — kode & alasannya tersimpan."),
        "options": [
            _o("queued", "Antre"), _o("sending", "Sedang dikirim"), _o("sent", "Terkirim"),
            _o("delivered", "Sampai"), _o("read", "Dibaca"), _o("failed", "Gagal"),
            _o("simulated", "Simulasi"), _o("received", "Diterima"), _o("cancelled", "Dibatalkan"),
            _o("skipped", "Dilewati"),
        ],
    },
    "wa_mode": {
        "label": "Mode Kirim WhatsApp", "strict": True,
        "options": [_o("simulation", "Simulasi"), _o("live", "Live (Meta Cloud API)")],
    },
    "wa_message_category": {
        "label": "Kategori Pesan WhatsApp", "strict": True,
        "options": [
            _o("utility", "Utility (transaksional)"), _o("marketing", "Marketing (promosi)"),
            _o("authentication", "Authentication (OTP)"), _o("service", "Service (balasan dalam sesi)"),
        ],
    },
    "wa_message_kind": {
        "label": "Jenis Pesan WhatsApp", "strict": True,
        "options": [
            _o("inbox", "Inbox"), _o("broadcast", "Broadcast"), _o("reminder", "Pengingat"),
            _o("otp", "OTP portal"), _o("document", "Dokumen"), _o("notification", "Notifikasi"),
            _o("test", "Pesan uji"), _o("playbook", "Playbook"),
        ],
    },
    "wa_meta_template_status": {
        "label": "Status Template di Meta", "strict": True,
        "help": "Status persetujuan resmi dari Meta. NOT_SUBMITTED = belum pernah diajukan.",
        "options": [
            _o("NOT_SUBMITTED", "Belum diajukan"), _o("PENDING", "Menunggu review Meta"),
            _o("APPROVED", "Disetujui Meta"), _o("REJECTED", "Ditolak Meta"),
            _o("PAUSED", "Dijeda Meta"), _o("DISABLED", "Dinonaktifkan Meta"),
        ],
    },
    "broadcast_status": {
        "label": "Status Broadcast", "strict": True,
        "options": [
            _o("queued", "Antre"), _o("sending", "Berjalan"), _o("paused", "Dijeda"),
            _o("completed", "Selesai"), _o("cancelled", "Dibatalkan"),
        ],
    },
    "wa_optout_source": {
        "label": "Sumber Opt-out WhatsApp", "strict": True,
        "options": [
            _o("inbound_keyword", "Balasan STOP/BERHENTI dari pembeli"), _o("manual", "Dicatat manual"),
            _o("import", "Impor"),
        ],
    },
}
