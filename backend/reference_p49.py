"""SSOT reference registry — TAMBAHAN Fase 49 (Penutupan buku, laporan owner, pajak & kepatuhan).

Digabungkan ke `reference.GROUPS` lewat `_PHASES` di `reference.py`, jadi validator backend,
`/api/reference`, dan tab Kamus Data otomatis mengenalinya — layar TIDAK PERNAH menulis label
enum sendiri.

Lubang nyata yang ditutup Fase 49 (hasil audit kode terhadap API nyata):

1. **Tutup periode TANPA PEMERIKSAAN.** `POST /gl/periods/close` langsung menutup bulan walau
   mutasi bank belum dicocokkan, tagihan/uang muka masih menunggu keputusan, penyusutan bulan
   itu belum diposting, dan subledger tidak tie-out dengan buku besar.
2. **Tidak ada TUTUP TAHUN.** Laba tahun berjalan tidak pernah dipindah ke Laba Ditahan, jadi
   begitu ganti tahun akun pendapatan/beban menumpuk dan neraca berbohong.
3. **Arus kas hanya konsolidasi.** Owner tidak bisa melihat kas masuk/keluar PER PROYEK,
   padahal setiap proyek adalah pusat biaya sendiri.
4. **Faktur pajak sekali terbit, selamanya benar.** Tidak ada faktur PENGGANTI maupun
   PEMBATALAN, dan tidak ada ekspor berkas untuk diunggah ke Coretax.
5. **Potongan PPh tidak punya BUKTI POTONG.** Sistem memotong (fee mitra, jasa konstruksi)
   tetapi tidak pernah menerbitkan bukti potong bernomor yang bisa diberikan ke pihak yang
   dipotong — kewajiban PER-24/PJ/2021 tidak terpenuhi.
"""


def _o(value: str, label: str) -> dict:
    return {"value": value, "label": label}


GROUPS_P49: dict = {
    # --------------------------------------------------------------- 49A tutup periode
    "closing_check_item": {
        "label": "Daftar periksa tutup buku",
        "strict": True,
        "help": "Pemeriksaan yang dijalankan sebelum sebuah bulan boleh ditutup.",
        "options": [
            _o("jurnal_seimbang", "Semua jurnal periode ini seimbang"),
            _o("bank_belum_dicocokkan", "Mutasi bank sudah dicocokkan atau diabaikan beralasan"),
            _o("bukti_transfer_menunggu", "Tidak ada bukti transfer pelanggan yang menunggu verifikasi"),
            _o("tagihan_menunggu", "Tidak ada tagihan vendor/subkon yang menunggu persetujuan"),
            _o("uang_muka_menunggu", "Tidak ada uang muka subkon yang menunggu keputusan"),
            _o("rekap_upah_menunggu", "Tidak ada rekap upah harian yang menunggu keputusan"),
            _o("penyusutan_belum_diposting", "Penyusutan aset tetap bulan ini sudah diposting"),
            _o("tieout_subledger", "Subledger tie-out dengan buku besar"),
            _o("tahanan_3way", "Tagihan yang ditahan 3-way match sudah dituntaskan"),
        ],
    },
    "closing_check_state": {
        "label": "Hasil pemeriksaan tutup buku",
        "strict": True,
        "options": [
            _o("ok", "Beres"),
            _o("blocking", "Menahan penutupan"),
            _o("warning", "Perlu diperhatikan (tidak menahan)"),
            _o("missing_data", "Belum ada data"),
        ],
    },
    "year_closing_state": {
        "label": "Status tutup tahun",
        "strict": True,
        "options": [
            _o("open", "Belum ditutup"),
            _o("closed", "Sudah ditutup"),
            _o("reopened", "Dibuka kembali (jurnal penutup dibalik)"),
        ],
    },
    # --------------------------------------------------------------- 49E faktur pajak
    "faktur_state": {
        "label": "Status faktur pajak",
        "strict": True,
        "options": [
            _o("issued", "Terbit"),
            _o("replaced", "Diganti faktur pengganti"),
            _o("cancelled", "Dibatalkan"),
        ],
    },
    "tax_export_format": {
        "label": "Format ekspor pajak",
        "strict": True,
        "help": ("Coretax memakai XML hasil konversi template resmi; CSV disediakan untuk "
                 "ditempel ke template Excel sebelum dikonversi."),
        "options": [
            _o("coretax_xml", "XML (impor Coretax)"),
            _o("excel_csv", "CSV (tempel ke template Excel)"),
        ],
    },
    "vat_return_state": {
        "label": "Hasil rekap PPN masa",
        "strict": True,
        "options": [
            _o("kurang_bayar", "Kurang bayar (harus disetor)"),
            _o("lebih_bayar", "Lebih bayar (dikompensasi/restitusi)"),
            _o("nihil", "Nihil"),
            _o("missing_data", "Belum ada data"),
        ],
    },
    # --------------------------------------------------------------- 49F bukti potong
    "withholding_kind": {
        "label": "Jenis pemotongan PPh",
        "strict": True,
        "options": [
            _o("pph23", "PPh Pasal 23 (jasa/sewa selain tanah & bangunan)"),
            _o("pph21", "PPh Pasal 21 (orang pribadi)"),
            _o("pph4_2_konstruksi", "PPh Pasal 4(2) final — jasa konstruksi"),
            _o("pph4_2_sewa", "PPh Pasal 4(2) final — sewa tanah & bangunan"),
        ],
    },
    "withholding_basis": {
        "label": "Dasar pemotongan",
        "strict": True,
        "help": "Dari mana potongan lahir — dipakai untuk tie-out ke kas yang benar-benar keluar.",
        "options": [
            _o("ap_payment", "Pembayaran tagihan vendor/subkon"),
            _o("partner_fee", "Pembayaran fee mitra"),
            _o("manual", "Pencatatan manual (bukti dari luar sistem)"),
        ],
    },
    "withholding_party_kind": {
        "label": "Bentuk pihak yang dipotong",
        "strict": True,
        "help": "Menentukan identitas yang dipakai: badan memakai NPWP, orang pribadi NPWP/NIK.",
        "options": [
            _o("company", "Badan (PT/CV/koperasi)"),
            _o("individual", "Orang pribadi"),
        ],
    },
    "withholding_object_code": {
        "label": "Kode objek pajak (bukti potong)",
        # SENGAJA tidak strict: lampiran KEP-143/PJ/2022 berisi ratusan kode dan berubah
        # lewat keputusan DJP. Daftar di bawah hanya kode yang sering dipakai perusahaan
        # properti/konstruksi; kode lain tetap boleh diisi bebas dengan pola NN-NNN-NN,
        # supaya sistem tidak MENGARANG klasifikasi pajak pihak lain.
        "strict": False,
        "help": ("Kode objek pajak pada bukti potong unifikasi (KEP-143/PJ/2022). Bila kode "
                 "yang dibutuhkan tidak ada di daftar, tulis manual dengan pola NN-NNN-NN "
                 "sesuai arahan staf pajak."),
        "options": [
            _o("24-104-29", "PPh 23 — jasa perawatan/perbaikan/pemeliharaan"),
            _o("28-409-08", "PPh 4(2) — jasa perencanaan konstruksi (berkualifikasi)"),
            _o("28-409-09", "PPh 4(2) — jasa perencanaan konstruksi (tanpa kualifikasi)"),
            _o("28-409-10", "PPh 4(2) — pelaksanaan konstruksi (kualifikasi kecil)"),
            _o("28-409-11", "PPh 4(2) — pelaksanaan konstruksi (menengah & besar)"),
            _o("28-409-12", "PPh 4(2) — pelaksanaan konstruksi (tanpa kualifikasi)"),
            _o("28-409-13", "PPh 4(2) — pengawasan konstruksi (berkualifikasi)"),
            _o("28-409-14", "PPh 4(2) — pengawasan konstruksi (tanpa kualifikasi)"),
            _o("28-409-22", "PPh 4(2) — pekerjaan konstruksi, sertifikat kualifikasi kecil"),
            _o("28-409-23", "PPh 4(2) — pekerjaan konstruksi, tanpa sertifikat"),
            _o("28-409-24", "PPh 4(2) — pekerjaan konstruksi, sertifikat selain kecil"),
            _o("28-409-27", "PPh 4(2) — jasa konsultansi konstruksi bersertifikat"),
        ],
    },
    "withholding_state": {
        "label": "Status bukti potong",
        "strict": True,
        "help": ("PER-24/PJ/2021: nomor bukti potong TIDAK berubah saat dibetulkan; bukti yang "
                 "dibatalkan tidak boleh dipakai lagi."),
        "options": [
            _o("issued", "Terbit"),
            _o("corrected", "Dibetulkan (nomor tetap)"),
            _o("cancelled", "Dibatalkan"),
        ],
    },
}
