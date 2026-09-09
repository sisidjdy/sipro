"""SSOT reference registry — TAMBAHAN Fase 51 (Retensi↔Garansi, Pengingat WA, Portal Pembeli).

Digabungkan ke `reference.GROUPS` lewat `_PHASES` di `reference.py`.

Lubang nyata yang ditutup Fase 51 (hasil pembacaan kode terhadap API yang sudah jalan):

1. **Jaminan mutu bisa cair saat mutunya sedang dipersoalkan.** `retention_gate` (Fase 48)
   memeriksa masa pemeliharaan dan temuan punch list, tetapi TIDAK melihat `warranty_claims`
   — jalur keluhan pasca-huni yang baru lahir di Fase 50. Jadi retensi subkon bisa dicairkan
   persis ketika rumah sedang diperbaiki karena cacat pekerjaannya. Sekarang klaim garansi
   yang masih berjalan MENAHAN pencairan, dan penahanan itu hanya bisa diabaikan oleh peran
   ber-izin `override` dengan alasan ≥10 huruf (tercatat + melahirkan tugas penelaahan).
2. **Tanggal yang sudah dimiliki sistem tidak pernah memberi tahu siapa pun.** Tanggal jatuh
   tempo termin, tunggakan, dan tanggal habis garansi per bagian semuanya tersimpan — tetapi
   pengingat dikirim manual. Fase 51B menghitung kandidat pengingat dari data itu, mengirim
   lewat lapisan WhatsApp yang sudah ada, dan MENOLAK mengirim dua kali untuk periode yang
   sama (dedup). Bila kredensial WhatsApp belum ada, statusnya ditulis "simulasi" — tidak
   pernah "terkirim".
3. **Pembeli tidak bisa memegang buktinya sendiri.** BAST hanya bisa diunduh staf, kwitansi
   tidak bisa diunduh siapa pun, dan "pengakuan pembeli" yang DIWAJIBKAN mesin untuk menutup
   klaim garansi (Fase 50) selama ini diketik oleh staf atas nama pembeli. Fase 51C memberi
   pembeli tiga pintu itu di portalnya sendiri.
"""


def _o(value: str, label: str) -> dict:
    return {"value": value, "label": label}


GROUPS_P51: dict = {
    # ------------------------------------------------- 51A tahanan pencairan retensi
    "retention_block": {
        "label": "Penahan pencairan retensi",
        "strict": True,
        "help": ("Sebab retensi subkon belum boleh dicairkan. Tiga sebab pertama bisa "
                 "DIABAIKAN oleh Manajer Keuangan dengan alasan tertulis; dua terakhir "
                 "tidak bisa diabaikan karena menyangkut keadaan dokumen itu sendiri."),
        "options": [
            _o("maintenance_active", "Masa pemeliharaan masih berjalan"),
            _o("punch_open", "Masih ada temuan punch list terbuka"),
            _o("warranty_claim_active", "Masih ada klaim garansi berjalan"),
            _o("already_released", "Retensi sudah dicairkan"),
            _o("claim_not_approved", "Termin sumber retensi belum disetujui"),
        ],
    },
    "retention_state": {
        "label": "Status Retensi Subkon",
        "strict": True,
        "options": [
            _o("held", "Ditahan"),
            _o("release_requested", "Pencairan diajukan"),
            _o("released", "Sudah dicairkan"),
        ],
    },
    # ------------------------------------------------- 51B pengingat WhatsApp
    "reminder_kind": {
        "label": "Jenis Pengingat",
        "strict": True,
        "help": "Semua jenis dihitung dari data nyata; tidak ada daftar penerima manual.",
        "options": [
            _o("warranty_expiring", "Garansi hampir habis"),
            _o("installment_due", "Termin akan jatuh tempo"),
            _o("installment_overdue", "Termin terlambat (tunggakan)"),
            _o("arrears_warning", "Tunggakan lewat toleransi (pra-SP)"),
            _o("booking_fee_due", "Booking fee akan jatuh tempo"),
        ],
    },
    "reminder_status": {
        "label": "Status Pengingat",
        "strict": True,
        "help": ("'Simulasi' berarti pesan TIDAK benar-benar terkirim karena kredensial "
                 "WhatsApp belum diisi — isinya tersimpan supaya bisa diperiksa."),
        "options": [
            _o("terkirim", "Terkirim"),
            _o("simulasi", "Simulasi (kredensial WhatsApp belum ada)"),
            _o("gagal", "Gagal terkirim"),
            _o("dilewati", "Dilewati"),
        ],
    },
    "reminder_skip_reason": {
        "label": "Sebab Pengingat Dilewati",
        "strict": True,
        "options": [
            _o("no_phone", "Nomor WhatsApp penerima belum dicatat"),
            _o("already_sent", "Sudah diingatkan pada periode ini"),
            _o("template_missing", "Template WhatsApp belum ada/disetujui"),
            _o("disabled", "Pengingat otomatis dimatikan di Pusat Konfigurasi"),
        ],
    },
    "reminder_recipient": {
        "label": "Jenis Penerima Pengingat",
        "strict": True,
        "help": ("Rumah yang belum akad belum punya pelanggan, jadi penerimanya masih calon "
                 "pembeli (lead). Jenisnya ditulis apa adanya supaya id-nya tersimpan di "
                 "kolom yang benar — id lead TIDAK pernah ditulis ke `customer_id`."),
        "options": [
            _o("customer", "Pelanggan (sudah akad)"),
            _o("lead", "Calon pembeli (belum akad)"),
        ],
    },
    # ------------------------------------------------- 51C dokumen milik pembeli
    "portal_doc_kind": {
        "label": "Jenis Dokumen Pembeli",
        "strict": True,
        "options": [
            _o("bast", "Berita acara serah terima (BAST)"),
            _o("kwitansi", "Kwitansi penerimaan pembayaran"),
            _o("dokumen_transaksi", "Dokumen transaksi (SPR/PPJB/AJB)"),
        ],
    },
}
