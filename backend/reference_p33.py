"""SSOT reference — TAMBAHAN Fase 33 (opname berbukti & termin berbasis item pekerjaan).

Semua label status/mode di UI Fase 33 diambil dari sini (bukan diketik di komponen),
sehingga istilah yang dilihat pengguna konsisten dan bisa diubah di satu tempat.
"""


def _o(value: str, label: str) -> dict:
    return {"value": value, "label": label}


GROUPS_P33: dict = {
    "spk_scope_mode": {
        "label": "Dasar Pembayaran SPK", "strict": True, "options": [
            _o("items", "Per item pekerjaan (berbukti)"),
            _o("lumpsum", "Borongan lump-sum (persen manual)"),
        ],
    },
    "scope_item_state": {
        "label": "Status Pekerjaan dalam Lingkup SPK", "strict": True, "options": [
            _o("open", "Belum selesai dikerjakan"),
            _o("unverified", "Menunggu verifikasi supervisor"),
            _o("claimable", "Terverifikasi — siap ditagih"),
            _o("pending", "Dalam pengajuan termin"),
            _o("billed", "Sudah ditagih"),
        ],
    },
    "opname_exclude_reason": {
        "label": "Alasan Baris Dikeluarkan saat Opname", "strict": False, "options": [
            _o("mutu_belum_sesuai", "Mutu belum sesuai spesifikasi"),
            _o("volume_kurang", "Volume terpasang kurang dari rencana"),
            _o("bukti_kurang", "Bukti foto/checklist belum memadai"),
            _o("perbaikan_berjalan", "Masih menunggu perbaikan"),
            _o("lainnya", "Alasan lain (tulis di catatan)"),
        ],
    },
}
