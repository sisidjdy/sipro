"""SSOT reference registry — TAMBAHAN Fase 59.

Tiga utang yang dibayar fase ini (semua lahir dari catatan "tugas berikutnya" Fase 58):

1. **Laporan keringanan denda.** Keringanan sudah berjejak per transaksi sejak Fase 58,
   tetapi tidak ada satu pun layar yang bisa menjawab pertanyaan rapat direksi: *siapa
   meringankan apa, berapa, kapan, dan dengan alasan apa*. Jejak yang hanya bisa dibaca
   satu-satu per pembeli bukan pertanggungjawaban.
2. **Tunggakan yang sudah melewati batas kontrak.** SPR menuliskan hak developer
   membatalkan sepihak setelah tunggakan `payment.staged.arrears_months_to_cancel` bulan.
   Pasalnya tercetak, mesinnya belum pernah menunjuk siapa yang sudah melewatinya. Fase ini
   MENGUSULKAN (daftar kandidat + tugas kepada Manajer Keuangan) — keputusan membatalkan
   tetap ditekan manusia lewat alur Fase 56 yang sudah ada.
3. **Utang refund (`2-1460`).** Nominalnya sudah berjurnal, tetapi tidak ada laporan yang
   menyebut KAPAN uang itu harus keluar. Kewajiban tanpa tanggal tidak bisa dipakai
   merencanakan kas.

Kamus di bawah adalah bahasa bersama untuk keadaan-keadaan itu. Layar tidak boleh mengarang
labelnya sendiri, dan setiap keadaan wajib punya kode agar bisa diuji.
"""


def _o(value: str, label: str) -> dict:
    return {"value": value, "label": label}


GROUPS_P59: dict = {
    "arrears_stage": {
        "label": "Tahap Tunggakan terhadap Batas Kontrak",
        "strict": True,
        "help": ("Dihitung dari termin yang LEWAT TOLERANSI (mesin denda Fase 58), bukan dari "
                 "status yang diketik orang. `kandidat_batal` berarti tunggakannya sudah "
                 "melewati batas yang tertulis di SPR — bukan berarti kontraknya batal: "
                 "pembatalan tetap keputusan manusia lewat alur Fase 56."),
        "options": [
            _o("aman", "Belum menunggak melewati batas"),
            _o("perhatian", "Menunggak, satu bulan lagi mencapai batas"),
            _o("kandidat_batal", "Sudah melewati batas tunggakan kontrak"),
        ],
    },
    "refund_due_state": {
        "label": "Keadaan Jatuh Tempo Utang Refund",
        "strict": True,
        "help": ("Utang refund (akun 2-1460) yang tidak punya tanggal tidak bisa dipakai "
                 "merencanakan kas. `tertahan` adalah kejujuran yang wajib: selama ketentuan "
                 "SPR menahan pembayaran sampai unit terjual kembali, tanggalnya BELUM ADA — "
                 "dan itu bukan 'jatuh tempo hari ini' maupun 'Rp 0'."),
        "options": [
            _o("terjadwal", "Terjadwal (belum jatuh tempo)"),
            _o("segera", "Jatuh tempo dalam 7 hari"),
            _o("terlewat", "Sudah lewat jatuh tempo"),
            _o("tertahan", "Tertahan ketentuan SPR (belum bisa dijadwalkan)"),
            _o("lunas", "Sudah dibayar penuh"),
        ],
    },
    "refund_age_bucket": {
        "label": "Umur Utang Refund",
        "strict": True,
        "help": ("Dihitung dari tanggal KEPUTUSAN pembatalan (saat utangnya lahir di buku "
                 "besar), bukan dari tanggal pengajuan — pengajuan belum melahirkan "
                 "kewajiban apa pun."),
        "options": [
            _o("0-30", "0-30 hari"),
            _o("31-60", "31-60 hari"),
            _o("61-90", "61-90 hari"),
            _o(">90", "Lebih dari 90 hari"),
        ],
    },
}
