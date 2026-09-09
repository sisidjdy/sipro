"""SSOT reference registry — TAMBAHAN Fase 58 (Toleransi keterlambatan & denda berjurnal).

Digabungkan ke `reference.GROUPS` lewat `_PHASES` di `reference.py`.

## Lubang NYATA yang ditutup Fase 58

Sejak Fase 57A pemakai BISA menyusun termin sendiri, termasuk **toleransi (tenggang)**
per termin — dan kalimat toleransi itu ikut tercetak pada dokumen SPR yang ditandatangani
pembeli ("cicilan wajib dibayar tanggal 7; toleransi paling lambat tanggal 20"). Yang tidak
ada sampai fase ini: **tenggangnya tidak pernah dipakai siapa pun.**

  * `units`/`ar_invoices` tidak menyimpan `grace_days`, jadi jadwal tagihan kehilangan angka
    toleransi begitu skema diterjemahkan menjadi termin.
  * Tab **Rencana Bayar** menandai satu termin **TERLAMBAT** pada hari H+1 — padahal
    kontraknya sendiri memberi tenggang belasan hari. Layar menuduh pembeli menunggak
    lebih cepat daripada perjanjiannya.
  * Denda keterlambatan hanya ada sebagai angka **perkiraan worksheet**
    (`finance_reports.compute_denda`) dengan tarif & tenggang yang HANYA hidup di
    `DEFAULT_COLLECTION` — di luar Pusat Konfigurasi — dan bila diterapkan tidak pernah
    berjurnal: piutang & pendapatan denda tidak muncul di buku besar mana pun.
  * Tidak ada jalan resmi untuk **meringankan** denda; padahal keringanan adalah keputusan
    manajerial yang paling sering dipakai dan paling perlu jejak.

Kamus di bawah ini adalah bahasa bersama untuk keadaan-keadaan itu: layar tidak boleh
mengarang label sendiri, dan setiap "kenapa denda belum bisa ditagihkan" wajib punya kode
agar bisa diuji.
"""


def _o(value: str, label: str) -> dict:
    return {"value": value, "label": label}


GROUPS_P58: dict = {
    "late_state": {
        "label": "Keadaan Termin terhadap Jatuh Tempo",
        "strict": True,
        "help": ("Dihitung dari tanggal jatuh tempo + TOLERANSI yang tertulis pada termin "
                 "(bukan dari status yang diketik orang). `dalam_tenggang` adalah keadaan "
                 "yang dulu tidak ada: termin lewat tanggal tetapi MASIH di dalam masa "
                 "toleransi yang dijanjikan kontrak — belum menunggak."),
        "options": [
            _o("lunas", "Lunas"),
            _o("menunggu", "Menunggu jatuh tempo"),
            _o("dalam_tenggang", "Dalam masa toleransi"),
            _o("terlambat", "Terlambat (lewat toleransi)"),
        ],
    },
    "late_fee_block": {
        "label": "Sebab Denda Belum Bisa Ditagihkan",
        "strict": True,
        "help": ("Dipakai layar untuk MENYEBUTKAN sebab, bukan mematikan tombol tanpa "
                 "penjelasan. Kode di sini wajib sama dengan kode di mesin."),
        "options": [
            _o("tanpa_tagihan", "Belum ada jadwal tagihan"),
            _o("tidak_ada_tunggakan", "Tidak ada termin yang lewat jatuh tempo"),
            _o("masih_tenggang", "Masih di dalam masa toleransi kontrak"),
            _o("denda_nol", "Denda terhitung nol (di bawah batas minimum)"),
            _o("sudah_ditagihkan", "Denda periode ini sudah ditagihkan"),
            _o("tagihan_dibatalkan", "Tagihan sudah dibatalkan"),
        ],
    },
    "late_fee_state": {
        "label": "Status Denda Keterlambatan",
        "strict": True,
        "help": ("Denda yang sudah ditagihkan BERJURNAL (piutang & pendapatan denda). "
                 "Keringanan tidak menghapus jejaknya: ia membalik jurnalnya dan wajib "
                 "beralasan tertulis."),
        "options": [
            _o("ditagihkan", "Ditagihkan (belum dibayar)"),
            _o("dibayar", "Sudah dibayar"),
            _o("diringankan", "Diringankan (dibalik beralasan)"),
        ],
    },
}
