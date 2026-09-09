"""Kosakata Fase 100 (audit CFG-03/04 & UI-02) — pilihan enum Aturan Bisnis & status tiket
penghapusan data. Dulu kode mentah (`spr_signed`, `per_project_month`) tampil apa adanya di
dropdown Pusat Konfigurasi dan peta label tiket hidup di komponen React; kini satu registry."""
from reference_groups import _o

GROUPS_P100 = {
    "lead_won_trigger": {
        "label": "Pemicu Lead Menjadi Customer", "strict": True,
        "help": "Peristiwa yang mengakhiri lifecycle lead (setting `lead.won_trigger`).",
        "options": [
            _o("booking_fee_verified", "Booking fee terverifikasi"),
            _o("spr_signed", "SPR ditandatangani"),
            _o("ppjb_signed", "PPJB ditandatangani"),
            _o("ajb_signed", "AJB ditandatangani"),
        ],
    },
    "slik_gate": {
        "label": "Titik Wajib BI/SLIK Checking", "strict": True,
        "help": "Setting `slik.gate` — kapan hasil BI checking wajib ada.",
        "options": [
            _o("off", "Tidak diwajibkan"),
            _o("before_booking", "Sebelum booking / reservasi"),
            _o("before_spr", "Sebelum SPR diterbitkan"),
        ],
    },
    "attribution_model": {
        "label": "Model Atribusi Lead Mitra", "strict": True,
        "help": "Setting `partner.attribution_model` — mitra mana yang berhak bila lead dikirim lebih dari satu mitra.",
        "options": [
            _o("first_touch", "Mitra pertama yang mengirim"),
            _o("last_touch", "Mitra terakhir yang mengirim"),
            _o("manual_review", "Ditinjau manual oleh manajer"),
        ],
    },
    "docnum_scope": {
        "label": "Cakupan Nomor Dokumen", "strict": True,
        "help": "Setting `docnum.scope` — ruang hitung counter nomor dokumen.",
        "options": [
            _o("global", "Global (satu counter perusahaan)"),
            _o("per_project", "Per proyek"),
            _o("per_project_month", "Per proyek per bulan"),
        ],
    },
    "docnum_reset_policy": {
        "label": "Kebijakan Reset Nomor Dokumen", "strict": True,
        "help": "Setting `docnum.reset_policy` — kapan counter mulai dari 1 lagi.",
        "options": [
            _o("never", "Tidak pernah"), _o("yearly", "Setiap tahun"), _o("monthly", "Setiap bulan"),
        ],
    },
    "deletion_request_status": {
        "label": "Status Tiket Penghapusan Data", "strict": True,
        "help": "Status permintaan penghapusan data pribadi (halaman legal publik).",
        "options": [
            _o("open", "Baru"), _o("in_progress", "Diproses"), _o("done", "Selesai"), _o("rejected", "Ditolak"),
        ],
    },
    # Audit Tahap 7 §3 (CFG-04): jenis pesan WhatsApp MASUK — dulu hanya hidup di dropdown simulasi.
    "wa_inbound_type": {
        "label": "Jenis Pesan WhatsApp Masuk", "strict": True,
        "help": "Tipe objek `messages[].type` dari webhook Meta yang dikenali mesin inbound.",
        "options": [
            _o("text", "Teks"), _o("image", "Gambar (caption)"), _o("document", "Dokumen"),
            _o("location", "Lokasi"),
        ],
    },
}
