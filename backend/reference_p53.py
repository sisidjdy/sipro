"""SSOT reference registry — TAMBAHAN Fase 53 (Lead → Pembeli, Kontrak, Akad, Dokumen Owner).

Digabungkan ke `reference.GROUPS` lewat `_PHASES` di `reference.py`.

## Lubang NYATA yang ditutup Fase 53 (dilaporkan pemilik produk, lalu dibuktikan di kode)

Laporan: *"saya masih belum menemukan bagaimana lead bisa menjadi customer"*, *"AJB itu
ketika akad kredit, seharusnya sudah di tahap customer"*, *"penawaran dan unit deal belum
ter-wiring dengan benar"*, *"bagaimana dokumen yang otomatis terbuat dari data yang saya
berikan? bagaimana saya mencetaknya?"*

Pembacaan kode membenarkan keempatnya:

1. **Tidak ada satu baris kode pun yang mengubah lead menjadi pembeli.** `db.customers`
   hanya ditulis oleh `POST /api/customers` (form manual, dan formnya bahkan tidak punya
   kolom lead) dan oleh seed. Padahal `build_engine._buyer_binding()` mencari pembeli dengan
   `customers.lead_id == deal.lead_id` — tautan yang tidak pernah ada untuk data nyata.
   Akibatnya: profil pembeli, portal pembeli, KPR, rencana bayar, dan BAST hanya
   "tersambung" pada data demo hasil seed.
2. **Penawaran melahirkan deal berbentuk LAIN.** `quotation_engine.convert()` menulis
   `{"stage": "reserved", "status": "active"}`, sedangkan seluruh sistem membaca
   `status == "reserved"`. Jadi deal hasil penawaran DITOLAK saat mau di-booking
   ("Deal harus berstatus 'reserved'"), tahap lead tidak maju, unit tidak terikat, masa keep
   unit tidak diset, dan AR tidak pernah lahir.
3. **Rantai legal menempel di `deals`, tanpa akad kredit.** PPJB→AJB ada, tetapi `akad_kredit`
   (peristiwa yang justru menentukan pada skema KPR) tidak ada sama sekali; AJB malah
   menuntut BAST lebih dulu, padahal pada KPR AJB terjadi SAAT akad.
4. **Dokumen owner belum pernah ada di sistem.** `document_templates` hanya berisi tiga teks
   pendek karangan seed (SPR/PPJB/AJB generik). Empat dokumen asli owner di
   `docs/source_templates/` (SPR Cash, SPR Cash Bertahap, SPR KPR, SPKT) — beserta format
   nomornya `5201/SPR-CASH/HL5/VIII/2026` — belum diterjemahkan menjadi template data.

Kamus di bawah ini adalah bahasa bersama untuk keadaan-keadaan baru itu. Sengaja SSOT:
layar tidak boleh mengarang label sendiri, dan sebab "kenapa belum boleh" harus punya kode
agar bisa diuji.
"""


def _o(value: str, label: str) -> dict:
    return {"value": value, "label": label}


GROUPS_P53: dict = {
    # --------------------------------------------------------------- kontrak pembeli
    "contract_state": {
        "label": "Status Kontrak",
        "strict": True,
        "help": ("Kontrak lahir saat lead menjadi pembeli. `draft` = angka masih boleh "
                 "dirapikan (biaya BPHTB/notaris/bank belum tentu sudah diketahui); "
                 "`active` = kontrak dipakai sebagai dasar tagihan dan dokumen."),
        "options": [
            _o("draft", "Draft (masih bisa dirapikan)"),
            _o("active", "Aktif (dasar tagihan & dokumen)"),
            _o("completed", "Selesai (lunas + serah terima + AJB)"),
            _o("cancelled", "Dibatalkan"),
        ],
    },
    "contract_legal_stage": {
        "label": "Tahap Legal Kontrak",
        "strict": True,
        "help": ("Urutan legal MILIK PEMBELI (keputusan owner D4). Pada skema KPR, `ajb` "
                 "terjadi setelah `akad_kredit`; pada skema tunai, `ajb` menyusul "
                 "`pelunasan` dan `bast`."),
        "options": [
            _o("belum", "Belum ada tahap legal"),
            _o("ppjb", "PPJB ditandatangani"),
            _o("akad_kredit", "Akad kredit (KPR)"),
            _o("pelunasan", "Pelunasan dikonfirmasi Keuangan"),
            _o("bast", "Serah terima kunci (BAST)"),
            _o("ajb", "AJB ditandatangani notaris"),
            _o("sertifikat", "Sertifikat (SHGB) diserahkan"),
        ],
    },
    # --------------------------------------------------------------- sebab "belum boleh"
    "convert_block": {
        "label": "Penahan konversi Lead → Pembeli",
        "strict": True,
        "help": ("Sebab lead belum boleh menjadi pembeli. Kodenya SSOT supaya layar "
                 "menyebut sebab yang SAMA dengan yang ditegakkan server."),
        "options": [
            _o("deal_belum_ada", "Belum ada reservasi unit"),
            _o("deal_belum_booking", "Reservasi belum dikonfirmasi (booking)"),
            _o("deal_batal", "Reservasi sudah dibatalkan/kedaluwarsa"),
            _o("spr_belum_tanda_tangan", "SPR belum ditandatangani"),
            _o("data_diri_kosong", "Nama/telepon pembeli belum lengkap"),
            _o("sudah_pembeli", "Lead ini sudah menjadi pembeli"),
        ],
    },
    "legal_block": {
        "label": "Penahan tahap legal",
        "strict": True,
        "help": ("Gerbang bukti tiap tahap legal. Tahap tidak bisa dimajukan hanya karena "
                 "seseorang mengklik tombol — buktinya harus ada di data."),
        "options": [
            _o("urutan_salah", "Tahap sebelumnya belum selesai"),
            _o("dp_belum_bayar", "DP/termin pertama belum terbayar"),
            _o("biaya_belum_diisi", "Komponen biaya wajib belum diisi"),
            _o("sp3k_belum", "SP3K bank belum diterbitkan / tanpa bukti"),
            _o("kelebihan_tanah_belum_lunas", "Kelebihan tanah belum lunas (wajib sebelum akad)"),
            _o("spkt_belum_ada", "SPKT (surat kelebihan tanah) belum diterbitkan"),
            _o("belum_lunas", "Kewajiban pembeli belum lunas"),
            _o("bast_belum", "Serah terima (BAST) belum dilakukan"),
            _o("akad_belum", "Akad kredit belum dilaksanakan"),
            _o("bukan_kpr", "Tahap ini hanya untuk skema KPR"),
        ],
    },
    "docgen_block": {
        "label": "Penahan penerbitan dokumen",
        "strict": True,
        "help": ("Sebab dokumen tidak boleh diterbitkan. Dokumen yang memuat angka salah "
                 "lebih berbahaya daripada dokumen yang belum ada."),
        "options": [
            _o("kontrak_belum_ada", "Belum ada kontrak (lead belum menjadi pembeli)"),
            _o("skema_tidak_cocok", "Template ini bukan untuk skema pembayaran kontrak"),
            _o("tanpa_kelebihan_tanah", "Tidak ada add-on kelebihan tanah — SPKT tidak perlu"),
            _o("plafon_belum_ada", "Plafon KPR belum diisi"),
            _o("harga_nol", "Harga unit masih nol"),
            _o("sudah_final", "Dokumen final tidak bisa diubah — terbitkan adendum baru"),
            _o("booking_fee_belum", "Booking fee belum tercatat/terverifikasi"),
            _o("slik_belum", "Pra-skrining BI/SLIK belum lolos"),
            _o("demografi_belum_lengkap", "Data demografi pembeli wajib belum lengkap"),
            _o("skema_deal_beda", "Jenis skema kontrak berbeda dari skema pembayaran deal"),
        ],
    },
    # --------------------------------------------------------------- dokumen generator
    "docgen_template": {
        "label": "Template Dokumen (generator)",
        "strict": False,
        "dynamic": True,
        "source": {"collection": "document_templates", "field": "code"},
        "help": ("Template yang bisa di-generate sistem. Varian SPR mengikuti SKEMA "
                 "pembayaran kontrak — bukan pilihan bebas, supaya isi dokumen tidak "
                 "pernah bertentangan dengan kontraknya."),
        "options": [
            _o("SPR_CASH", "Surat Pesanan Rumah — Cash Keras"),
            _o("SPR_CASH_STAGED", "Surat Pesanan Rumah — Cash Bertahap"),
            _o("SPR_KPR", "Surat Pesanan Rumah — KPR"),
            _o("SPKT", "Surat Pernyataan Kelebihan Tanah"),
            _o("PPJB", "Perjanjian Pengikatan Jual Beli"),
            _o("AJB", "Akta Jual Beli"),
            _o("SPR", "Surat Pemesanan Rumah (template lama)"),
        ],
    },
    "component_fill_state": {
        "label": "Keadaan Komponen Biaya",
        "strict": True,
        "help": ("Biaya yang BELUM DIKETAHUI ditulis 'belum diisi' — bukan Rp 0. Menulis 0 "
                 "berarti mengaku biayanya tidak ada, dan itu belum tentu benar."),
        "options": [
            _o("filled", "Sudah diisi"),
            _o("empty", "Belum diisi (bukan nol)"),
            _o("not_applicable", "Tidak berlaku untuk skema ini"),
        ],
    },
}
