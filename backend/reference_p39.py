"""SSOT reference registry — TAMBAHAN Fase 39 (Fondasi Data V2).

Alasan file terpisah sama seperti Fase 27–37: `reference.py` sudah menyentuh batas gate
compliance (<=800 baris). Grup di sini digabungkan ke `reference.GROUPS` (lihat `_PHASES`)
sehingga seluruh dropdown/label frontend tetap SATU sumber (`GET /api/reference`).

Fase 39 menambah vocabulary untuk: hierarki proyek (cluster/blok/tipe), add-on/spek
tambahan, komponen biaya + perlakuan finance, master dokumen syarat, skema pembayaran,
mitra, target, dan alasan-alasan yang jadi data analitik (pelepasan unit, reschedule,
pembatalan survei).

Catatan penting (kejujuran data): tiga grup lama DIPERLUAS di sini — `unit_status`,
`construction_status`, `lead_source`. Nilai lama TETAP ADA (tidak ada migrasi paksa);
yang ditambah hanya nilai baru yang memang dibutuhkan proses bisnis:
  * unit_status        + handed_over, blocked
  * construction_status + scheduled, on_hold
  * lead_source        + partner, event, inhouse_marketing
"""


def _o(value: str, label: str) -> dict:
    return {"value": value, "label": label}


GROUPS_P39: dict = {
    # ---------------- status ganda unit (penjualan vs pembangunan) ----------------
    # `units.status` = STATUS PENJUALAN, `units.construction_status` = STATUS PEMBANGUNAN.
    # Keduanya berjalan paralel dan tidak boleh saling menimpa.
    "unit_status": {
        "label": "Status Penjualan Unit", "strict": True, "options": [
            _o("available", "Tersedia"), _o("reserved", "Dipegang (SPR/keep)"),
            _o("booked", "Booking (customer)"), _o("sold", "Terjual (lunas/akad)"),
            _o("handed_over", "Sudah serah terima"), _o("blocked", "Tidak dijual"),
        ],
    },
    "construction_status": {
        "label": "Status Pembangunan", "strict": True, "options": [
            _o("not_started", "Belum dibangun"), _o("scheduled", "Sudah dijadwalkan"),
            _o("in_progress", "Sedang dibangun"), _o("qc_hold", "Tertahan mutu (QC)"),
            # Fase 50A: nilai ini SUDAH LAMA ditulis oleh finalisasi inspeksi kategori
            # "handover" (`inspection_router.finalize`) tetapi tidak pernah terdaftar di
            # kamus data. Akibatnya pill status menampilkan kode mentah dan gate integritas
            # data berhak menyebutnya "status tak dikenal". Sekarang nilainya sah dan
            # berlabel manusia — inilah keadaan yang dibaca daftar periksa serah terima.
            _o("ready_handover", "Siap serah terima"),
            _o("done", "Sudah dibangun"), _o("on_hold", "Dihentikan sementara"),
        ],
    },
    "lead_source": {
        "label": "Sumber Lead", "strict": True, "options": [
            _o("walk_in", "Walk-in"), _o("meta_ads", "Meta Ads"),
            _o("google_lead", "Google Ads"), _o("tiktok_ads", "TikTok Ads"),
            _o("whatsapp", "WhatsApp"), _o("website", "Website"),
            _o("referral", "Referral"), _o("manual", "Manual"), _o("import", "Import"),
            _o("showroom_public", "Showroom publik (peta online)"),
            _o("partner", "Mitra / pihak ketiga"), _o("event", "Event / pameran"),
            _o("inhouse_marketing", "Marketing inhouse"),
        ],
    },
    # ---------------- hierarki proyek ----------------
    "cluster_status": {
        "label": "Status Cluster", "strict": True, "options": [
            _o("planning", "Perencanaan"), _o("selling", "Dijual"),
            _o("sold_out", "Habis terjual"), _o("closed", "Ditutup"),
        ],
    },
    "unit_type_ref": {
        "label": "Tipe Unit (master)", "strict": False, "dynamic": True, "allow_new": False,
        "source": {"collection": "unit_types", "field": "code"},
        "options": [],
    },
    # ---------------- add-on / spek tambahan ----------------
    "addon_category": {
        "label": "Kategori Spek Tambahan", "strict": False, "dynamic": True,
        "source": {"collection": "addon_items", "field": "category"},
        "options": [
            _o("spek_bangunan", "Spek bangunan"), _o("kelebihan_tanah", "Kelebihan tanah"),
            _o("posisi_unit", "Posisi unit (hook/sudut)"), _o("interior", "Interior"),
            _o("utilitas", "Utilitas (listrik/air)"), _o("lansekap", "Lansekap/taman"),
            _o("lainnya", "Lainnya"),
        ],
    },
    "addon_pricing_mode": {
        "label": "Cara Hitung Harga Add-on", "strict": True, "options": [
            _o("lump_sum", "Nominal tetap (lump sum)"), _o("per_m2", "Per m²"),
            _o("per_item", "Per item/unit hitung"), _o("percent_of_price", "Persen dari harga unit"),
        ],
    },
    # ---------------- komponen biaya & perlakuan finance ----------------
    "finance_treatment": {
        "label": "Perlakuan Keuangan", "strict": True, "options": [
            _o("revenue", "Pendapatan developer"),
            _o("pass_through", "Titipan pelanggan (diteruskan ke pihak ketiga)"),
            _o("discount", "Potongan/diskon"), _o("deposit", "Titipan/uang muka awal"),
            _o("tax_out", "Pajak dipungut/disetor"),
            _o("info", "Informasi (bukan tagihan)"),
        ],
    },
    "price_component_group": {
        "label": "Kelompok Komponen Harga", "strict": True, "options": [
            _o("harga", "Harga jual"), _o("tambahan", "Tambahan (add-on)"),
            _o("biaya", "Biaya transaksi"), _o("potongan", "Potongan/promo"),
            _o("pajak", "Pajak"), _o("pembiayaan", "Pembiayaan (KPR)"),
        ],
    },
    "payment_scheme": {
        "label": "Skema Pembayaran", "strict": False, "dynamic": True,
        "source": {"collection": "payment_scheme_templates", "field": "code"},
        "options": [
            _o("cash_keras", "Cash keras"), _o("cash_bertahap", "Cash bertahap"),
            _o("kpr", "KPR (Kredit Pemilikan Rumah)"),
        ],
    },
    # ---------------- master dokumen syarat ----------------
    "doc_requirement_group": {
        "label": "Kelompok Dokumen Syarat", "strict": False, "dynamic": True,
        "source": {"collection": "doc_requirements", "field": "group"},
        "options": [
            _o("identitas", "Identitas"), _o("keuangan", "Keuangan"), _o("kpr", "KPR/Bank"),
            _o("legal", "Legal"), _o("unit", "Unit & Perizinan"), _o("mitra", "Mitra"),
            _o("lainnya", "Lainnya"),
        ],
    },
    "doc_submission_status": {
        "label": "Status Dokumen Diserahkan", "strict": True, "options": [
            _o("pending", "Menunggu verifikasi"), _o("verified", "Terverifikasi"),
            _o("rejected", "Ditolak"), _o("expired", "Kedaluwarsa"),
        ],
    },
    # ---------------- alasan (data berharga untuk analitik) ----------------
    "reservation_release_reason": {
        "label": "Alasan Unit Dilepas", "strict": True, "options": [
            _o("customer_cancel", "Pembeli membatalkan"), _o("upgrade_unit", "Pindah unit (naik)"),
            _o("downgrade_unit", "Pindah unit (turun)"), _o("financing_failed", "Pembiayaan gagal"),
            _o("doc_incomplete", "Dokumen tidak lengkap"), _o("duplicate", "Data ganda"),
            _o("admin_error", "Kesalahan admin"), _o("expired", "Masa keep habis"),
        ],
    },
    "appointment_reschedule_reason": {
        "label": "Alasan Jadwal Diubah", "strict": True, "options": [
            _o("customer_request", "Permintaan pembeli"), _o("customer_no_show", "Pembeli tidak datang"),
            _o("weather", "Cuaca"), _o("pic_conflict", "PIC bentrok jadwal"),
            _o("unit_not_ready", "Unit belum siap dilihat"),
            _o("document_incomplete", "Dokumen belum lengkap"),
            _o("transport", "Kendala transportasi"), _o("other", "Lainnya"),
        ],
    },
    "appointment_cancel_reason": {
        "label": "Alasan Survei Dibatalkan", "strict": True, "options": [
            _o("customer_cancel", "Pembeli membatalkan"), _o("lost_interest", "Tidak berminat lagi"),
            _o("price_mismatch", "Harga tidak cocok"), _o("financing_failed", "Pembiayaan gagal"),
            _o("duplicate", "Data ganda"), _o("wrong_number", "Nomor salah/tidak aktif"),
            _o("other", "Lainnya"),
        ],
    },
    # ---------------- mitra / pihak ketiga ----------------
    "partner_kind": {
        "label": "Jenis Mitra", "strict": True, "options": [
            _o("agen_perorangan", "Agen perorangan"), _o("kantor_broker", "Kantor broker"),
            _o("aggregator", "Aggregator lead"), _o("referral_pembeli", "Referral pembeli"),
            _o("influencer", "Influencer/afiliasi"), _o("korporat", "Korporat/instansi"),
        ],
    },
    "partner_fee_basis": {
        "label": "Dasar Fee Mitra", "strict": True, "options": [
            _o("percent_price", "Persen dari harga"), _o("fixed_per_deal", "Nominal tetap per transaksi"),
            _o("fixed_per_unit_type", "Nominal per tipe unit"), _o("tier_volume", "Berjenjang per jumlah"),
            _o("tier_value", "Berjenjang per nilai"), _o("per_lead_qualified", "Per lead terkualifikasi"),
            _o("hybrid", "Gabungan"),
        ],
    },
    "partner_fee_trigger": {
        "label": "Pemicu Hak Fee", "strict": True, "options": [
            _o("booking_fee_verified", "Booking fee terverifikasi"), _o("spr_signed", "SPR ditandatangani"),
            _o("ppjb_signed", "PPJB ditandatangani"), _o("akad_kredit", "Akad kredit (KPR)"),
            _o("ajb_signed", "AJB ditandatangani"), _o("full_payment", "Pelunasan"),
        ],
    },
    # ---------------- target & anggaran ----------------
    "target_method": {
        "label": "Metode Target", "strict": True, "options": [
            _o("linear_remaining", "Sisa unit ÷ sisa bulan (dinamis)"),
            _o("s_curve", "Bobot kurva-S (diisi user)"), _o("manual", "Manual per bulan"),
            _o("velocity_forecast", "Proyeksi dari kecepatan penjualan"),
            _o("revenue_first", "Target pendapatan lalu diturunkan ke unit"),
        ],
    },
    "budget_category": {
        "label": "Kategori Anggaran", "strict": False, "dynamic": True,
        "source": {"collection": "budget_items", "field": "category"},
        "options": [
            _o("lahan", "Lahan"), _o("konstruksi", "Konstruksi (RAB)"),
            _o("prasarana", "Prasarana & fasum"), _o("perizinan", "Perizinan"),
            _o("operasional", "Operasional"), _o("marketing", "Marketing & iklan"),
            _o("komisi_fee", "Komisi & fee mitra"), _o("pembiayaan", "Pembiayaan/bunga"),
            _o("pajak", "Pajak"), _o("overhead", "Overhead"), _o("lainnya", "Lainnya"),
        ],
    },
    # ---------------- booking fee & KPR (dipakai Fase 42–44) ----------------
    "booking_fee_status": {
        "label": "Status Booking Fee", "strict": True, "options": [
            _o("unverified", "Belum diverifikasi"), _o("recorded", "Tercatat (bukti ada)"),
            _o("verified", "Terverifikasi finance"), _o("applied", "Dialihkan ke termin"),
            _o("forfeited", "Hangus"), _o("refunded", "Dikembalikan"),
        ],
    },
    "kpr_stage": {
        "label": "Tahap KPR", "strict": True, "options": [
            _o("berkas_lengkap", "Berkas lengkap"), _o("diajukan_ke_bank", "Diajukan ke bank"),
            _o("appraisal", "Survei & appraisal bank"), _o("sp3k", "SP3K/SPK diterbitkan"),
            _o("akad_kredit", "Akad kredit"), _o("pencairan", "Pencairan dana"),
            _o("ditolak", "Ditolak bank"), _o("batal", "Dibatalkan"),
        ],
    },
    # ---------------- Fase 39b: akun GL & label jejak setting ----------------
    # Kode akun GL DULU diketik bebas di form add-on & komponen biaya. Satu salah ketik
    # ("4-1100 " atau "41100") membuat nilai add-on masuk ke akun yang tidak ada di bagan
    # akun — ketahuan hanya saat tutup buku. Sekarang daftarnya datang dari bagan akun
    # (koleksi `accounts`) LENGKAP DENGAN NAMA akun, dan `allow_new=False` berarti akun baru
    # harus dibuat lebih dulu di halaman Akuntansi (bukan diketik di sini).
    "gl_account": {
        "label": "Akun GL", "strict": False, "dynamic": True, "allow_new": False,
        "source": {"collection": "accounts", "field": "code", "label_field": "name",
                   "label_format": "{value} — {label}"},
        "options": [],
    },
    # Label asal & dasar nilai setting: dipakai Pusat Konfigurasi. Ditaruh di SSOT supaya
    # tidak ada peta label kembar di frontend (temuan E5 audit_forms_deep).
    "setting_origin": {
        "label": "Asal Nilai Setting", "strict": True, "options": [
            _o("default", "Bawaan sistem"), _o("org", "Diubah organisasi"),
            _o("project", "Khusus proyek"),
        ],
    },
    "setting_source": {
        "label": "Dasar Nilai Setting", "strict": True, "options": [
            _o("DOC", "Dokumen legal"), _o("SISTEM", "Usulan sistem"),
        ],
    },
    # Konteks berlakunya syarat dokumen (`doc_requirements.applies_to`). Daftar ini DULU
    # ditulis ulang sebagai `CONTEXT_OPTIONS` di frontend, sehingga menambah konteks baru
    # berarti mengubah kode di dua tempat — dan checklist di layar lead menampilkan string
    # mentah "lead_stage:booking" kepada sales.
    "doc_context": {
        "label": "Konteks Syarat Dokumen", "strict": False, "options": [
            _o("lead_stage:acquisition", "Lead — tahap Akuisisi"),
            _o("lead_stage:nurturing", "Lead — tahap Nurturing"),
            _o("lead_stage:appointment", "Lead — tahap Appointment"),
            _o("lead_stage:booking", "Lead — tahap Booking (keep unit)"),
            _o("lead_stage:spr", "Lead — penerbitan SPR"),
            _o("lead_stage:won", "Lead — menang (siap jadi pelanggan)"),
            _o("payment_scheme:kpr", "Skema bayar KPR"),
            _o("payment_scheme:cash_bertahap", "Skema bayar Cash bertahap"),
            _o("payment_scheme:cash_keras", "Skema bayar Cash keras"),
            _o("customer:legal", "Pelanggan — legal & administrasi"),
            _o("partner:onboarding", "Mitra — pendaftaran"),
            _o("unit:permit", "Unit — perizinan"),
        ],
    },
}
