"""SSOT reference registry — TAMBAHAN Fase 56 (Pembatalan Kontrak & Refund Berjurnal).

Digabungkan ke `reference.GROUPS` lewat `_PHASES` di `reference.py`.

## Lubang NYATA yang ditutup Fase 56C

Dokumen SPR yang **sudah bisa dicetak sistem ini** (Fase 53E) memuat pasal pembatalan:
potongan **35%** bila pembeli mundur sebelum pembangunan, **50%** bila pembangunan sudah
berjalan, dan pengembalian dana dilakukan setelah unit terjual kembali. Ketiga angka itu
dibaca dari Pusat Konfigurasi (`cancellation.cut_before_build_pct`,
`cancellation.cut_during_build_pct`, `cancellation.refund_requires_resale`) — jadi
**janjinya sudah tercetak dan ditandatangani pembeli**.

Yang tidak ada sampai fase ini: **cara menjalankannya.**

  * KPR yang DITOLAK bank hanya *mengusulkan* nominal refund di layar (`kpr_engine`
    `rejection.refund_amount`) — tidak ada satu pun endpoint yang membukukannya.
  * `POST /deals/{id}/cancel` hanya menulis `status="cancelled"` dan melepas unit. Uang
    pembeli yang sudah masuk (`2-1400 Uang Muka Penjualan`) **tetap tercatat sebagai
    kewajiban tanpa penyelesaian** — laporan keuangan menyimpan utang kepada orang yang
    kontraknya sudah tidak ada.
  * Tab "Rencana Bayar" pada profil pembeli menulis apa adanya bahwa "mesin
    pembatalan/refund berjurnal belum ada" — pengakuan jujur yang sudah waktunya ditutup.

Kamus di bawah ini adalah bahasa bersama untuk keadaan-keadaan itu: layar tidak boleh
mengarang label sendiri, dan setiap "kenapa belum boleh" wajib punya kode agar bisa diuji.
"""


def _o(value: str, label: str) -> dict:
    return {"value": value, "label": label}


GROUPS_P56: dict = {
    "cancel_state": {
        "label": "Status Pembatalan",
        "strict": True,
        "help": ("Pengaju bukan pemutus. `diajukan` = menunggu keputusan Manajer Keuangan; "
                 "`disetujui` = jurnal potongan & utang refund sudah lahir; `selesai` = "
                 "refund sudah dibayar penuh."),
        "options": [
            _o("diajukan", "Diajukan (menunggu keputusan)"),
            _o("disetujui", "Disetujui (utang refund terbit)"),
            _o("ditolak", "Ditolak beralasan"),
            _o("refund_sebagian", "Refund dibayar sebagian"),
            _o("selesai", "Selesai (refund lunas)"),
        ],
    },
    "cancel_block": {
        "label": "Sebab Pembatalan Belum Bisa Diajukan",
        "strict": True,
        "help": ("Dipakai layar untuk MENYEBUTKAN sebab, bukan mematikan tombol tanpa "
                 "penjelasan. Kode di sini wajib sama dengan kode di mesin."),
        "options": [
            _o("kontrak_belum_ada", "Belum ada kontrak"),
            _o("kontrak_sudah_batal", "Kontrak sudah dibatalkan"),
            _o("pengajuan_berjalan", "Sudah ada pengajuan yang menunggu keputusan"),
            _o("sudah_ajb", "AJB sudah ditandatangani"),
            _o("sudah_bast", "Rumah sudah diserahterimakan (BAST)"),
            _o("bukti_menunggu_verifikasi", "Ada bukti transfer yang belum diverifikasi"),
        ],
    },
    "cancel_basis": {
        "label": "Dasar Potongan Pembatalan",
        "strict": True,
        "help": ("Dibaca dari keadaan pembangunan unit yang NYATA, bukan diketik pengaju — "
                 "potongan 35% vs 50% menentukan nominal yang dikembalikan."),
        "options": [
            _o("belum_mulai", "Pembangunan belum dimulai"),
            _o("sedang_dibangun", "Pembangunan sedang berjalan"),
            _o("sudah_selesai", "Pembangunan sudah selesai"),
        ],
    },
    "refund_method": {
        "label": "Cara Pembayaran Refund",
        "strict": True,
        "options": [
            _o("transfer", "Transfer bank"),
            _o("tunai", "Tunai (kas)"),
        ],
    },
    "refund_hold": {
        "label": "Sebab Refund Belum Bisa Dibayar",
        "strict": True,
        "help": ("Ketentuan SPR: pengembalian dana menyusul penjualan ulang unit. Penahanan "
                 "ini bisa DIABAIKAN Manajer Keuangan dengan alasan tertulis — keputusan "
                 "yang tercatat, bukan tombol yang diam-diam bisa ditekan."),
        "options": [
            _o("menunggu_penjualan_ulang", "Menunggu unit terjual kembali"),
            _o("belum_disetujui", "Pembatalan belum disetujui"),
            _o("refund_nol", "Tidak ada dana yang perlu dikembalikan"),
            _o("sudah_lunas", "Refund sudah dibayar penuh"),
        ],
    },
}
