"""reference_groups.py — GROUPS dasar (SSOT vocabulary inti).

Dipisah dari `reference.py` agar tiap berkas tetap di bawah batas 800 baris
(gate `validate_compliance.py`). REGISTRY tetap SATU: `reference.GROUPS` memuat
kamus ini lalu melengkapinya dengan grup per-fase (`reference_p<NN>.py`).
"""


def _o(value: str, label: str) -> dict:
    return {"value": value, "label": label}

# --------------------------------------------------------------------------
# GROUPS: value kanonik + label Indonesia. strict=True -> divalidasi backend.
# dynamic=True -> daftar dilengkapi nilai yang sudah ada di DB (boleh nilai baru).
# --------------------------------------------------------------------------
GROUPS: dict = {
    # ---------------- satuan & kategori pekerjaan ----------------
    "uom": {
        "label": "Satuan", "strict": True, "options": [
            _o("ls", "ls (lump sum)"), _o("unit", "unit"), _o("pcs", "pcs"),
            _o("buah", "buah"), _o("set", "set"), _o("titik", "titik"),
            _o("m", "m (meter)"), _o("m2", "m2 (meter persegi)"), _o("m3", "m3 (meter kubik)"),
            _o("kg", "kg"), _o("ton", "ton"), _o("sak", "sak"), _o("batang", "batang"),
            _o("lembar", "lembar"), _o("dus", "dus"), _o("roll", "roll"),
            _o("kaleng", "kaleng"), _o("hari", "hari"), _o("orang", "orang"),
        ],
    },
    "work_category": {
        "label": "Kategori Pekerjaan", "strict": True, "options": [
            _o("persiapan", "Persiapan"), _o("struktur", "Struktur"),
            _o("arsitektur", "Arsitektur"), _o("mep", "MEP (Mekanikal/Elektrikal/Plumbing)"),
            _o("finishing", "Finishing"), _o("lansekap", "Lansekap"),
            _o("infrastruktur", "Infrastruktur (Jalan & Drainase)"), _o("lainnya", "Lainnya"),
        ],
    },
    "inspection_category": {
        "label": "Kategori Inspeksi", "strict": True, "options": [
            _o("structural", "Struktur"), _o("architectural", "Arsitektur"),
            _o("mep", "MEP"), _o("finishing", "Finishing"),
            _o("handover", "Serah Terima"), _o("lainnya", "Lainnya"),
        ],
    },
    "subcon_specialty": {
        "label": "Bidang Subkontraktor", "strict": True, "options": [
            _o("struktur", "Struktur & Beton"), _o("mep", "MEP (Listrik & Plumbing)"),
            _o("arsitektur", "Arsitektur"), _o("finishing", "Finishing"),
            _o("tanah", "Tanah & Urugan"), _o("infrastruktur", "Jalan & Drainase"),
            _o("lansekap", "Lansekap"), _o("supplier", "Supplier Material"),
            _o("lainnya", "Lainnya"),
        ],
    },
    "weather": {
        "label": "Cuaca", "strict": True, "options": [
            _o("cerah", "Cerah"), _o("cerah_berawan", "Cerah berawan"),
            _o("berawan", "Berawan"), _o("hujan_ringan", "Hujan ringan"),
            _o("hujan_lebat", "Hujan lebat"), _o("badai", "Badai/Angin kencang"),
        ],
    },
    # ---------------- sales / CRM ----------------
    "lead_stage": {
        "label": "Tahap Lead", "strict": True, "options": [
            _o("acquisition", "Akuisisi"), _o("nurturing", "Nurturing"),
            _o("appointment", "Appointment"), _o("booking", "Booking"),
            _o("won", "Menang"), _o("recycle", "Daur ulang"), _o("lost", "Hilang"),
        ],
    },
    "lead_source": {
        "label": "Sumber Lead", "strict": True, "options": [
            _o("walk_in", "Walk-in"), _o("meta_ads", "Meta Ads"),
            _o("google_lead", "Google Ads"), _o("tiktok_ads", "TikTok Ads"),
            _o("whatsapp", "WhatsApp"), _o("website", "Website"),
            _o("referral", "Referral"), _o("manual", "Manual"), _o("import", "Import"),
            _o("showroom_public", "Showroom publik (peta online)"),
        ],
    },
    "score_band": {
        "label": "Kualitas Lead", "strict": True, "options": [
            _o("hot", "Hot"), _o("warm", "Warm"), _o("cold", "Cold"),
        ],
    },
    "channel_type": {
        "label": "Jenis Channel", "strict": True, "options": [
            _o("whatsapp", "WhatsApp"), _o("meta_lead_ads", "Meta Lead Ads"),
            _o("google_lead", "Google Lead Form"), _o("tiktok_lead", "TikTok Lead"),
            _o("website", "Form Website"),
        ],
    },
    "wa_template_category": {
        "label": "Kategori Template WA", "strict": True, "options": [
            _o("utility", "Utility"), _o("marketing", "Marketing"),
            _o("authentication", "Authentication"),
        ],
    },
    "appointment_type": {
        "label": "Jenis Agenda", "strict": True, "options": [
            _o("meeting", "Meeting"), _o("survey", "Survey lokasi"),
            _o("call", "Telepon"), _o("signing", "Tanda tangan"),
        ],
    },
    # ---------------- unit & proyek ----------------
    "unit_type": {
        "label": "Tipe Unit", "strict": False, "dynamic": True,
        "sources": [{"collection": "units", "field": "type"},
                    {"collection": "unit_types", "field": "name"}],
        "options": [
            _o("Tipe 36/72", "Tipe 36/72"), _o("Tipe 45/90", "Tipe 45/90"),
            _o("Tipe 54/105", "Tipe 54/105"), _o("Tipe 70/120", "Tipe 70/120"),
            _o("Kavling", "Kavling siap bangun"), _o("Ruko", "Ruko"),
        ],
    },
    "unit_status": {
        "label": "Status Unit", "strict": True, "options": [
            _o("available", "Tersedia"), _o("reserved", "Reserved"),
            _o("booked", "Booked"), _o("sold", "Terjual"),
        ],
    },
    "construction_status": {
        "label": "Status Konstruksi", "strict": True, "options": [
            _o("not_started", "Belum mulai"), _o("in_progress", "Berjalan"),
            _o("qc_hold", "QC hold"), _o("done", "Selesai"),
        ],
    },
    "project_status": {
        "label": "Status Proyek", "strict": True, "options": [
            _o("planning", "Perencanaan"), _o("active", "Aktif"),
            _o("on_hold", "Ditahan"), _o("completed", "Selesai"),
            _o("archived", "Diarsipkan"),
        ],
    },
    # ---------------- perizinan & lapangan ----------------
    "permit_type": {
        # Fase lanjutan: tidak lagi strict — organisasi boleh menambah jenis izin sendiri
        # (setting `permit.types_custom`), dan jenis yang sudah terpakai di DB tetap muncul.
        "label": "Jenis Perizinan", "strict": False, "dynamic": True,
        "source": {"collection": "permits", "field": "type"},
        "options": [
            _o("KRK", "KRK"), _o("IMB", "IMB"), _o("PBG", "PBG"), _o("SLF", "SLF"),
            _o("AMDAL", "AMDAL"), _o("ANDALALIN", "ANDALALIN"),
            _o("SITE_PLAN", "Pengesahan Site Plan"), _o("ADDENDUM", "Addendum"),
            _o("LAINNYA", "Lainnya"),
        ],
    },
    "permit_authority": {
        "label": "Instansi Penerbit", "strict": False, "dynamic": True,
        "source": {"collection": "permits", "field": "authority"},
        "options": [
            _o("DPMPTSP", "DPMPTSP"), _o("Dinas PU", "Dinas PU"),
            _o("Dinas Tata Ruang", "Dinas Tata Ruang"), _o("DLH", "DLH"),
            _o("Dinas Perhubungan", "Dinas Perhubungan"), _o("BPN", "BPN/ATR"),
            _o("PLN", "PLN"), _o("PDAM", "PDAM"),
        ],
    },
    "permit_status": {
        "label": "Status Perizinan", "strict": True, "options": [
            _o("not_started", "Belum diproses"), _o("in_progress", "Diproses"),
            _o("submitted", "Diajukan"), _o("approved", "Disetujui"),
            _o("rejected", "Ditolak"), _o("expired", "Kedaluwarsa"),
        ],
    },
    "punch_severity": {
        "label": "Tingkat Temuan", "strict": True, "options": [
            _o("low", "Rendah"), _o("medium", "Sedang"), _o("high", "Tinggi"),
            _o("critical", "Kritis"),
        ],
    },
    # ---------------- task & kolaborasi ----------------
    "task_type": {
        "label": "Jenis Tugas", "strict": True, "options": [
            _o("todo", "To-do"), _o("contact", "Kontak"), _o("follow_up", "Follow-up"),
            _o("review", "Review"), _o("approval", "Persetujuan"),
            _o("inspection", "Inspeksi"), _o("payment", "Pembayaran"),
        ],
    },
    "task_status": {
        "label": "Status Tugas", "strict": True, "options": [
            _o("open", "Terbuka"), _o("in_progress", "Dikerjakan"),
            _o("submitted", "Menunggu verifikasi"),
            _o("snoozed", "Ditunda"), _o("done", "Selesai"), _o("cancelled", "Dibatalkan"),
        ],
    },
    "priority": {
        "label": "Prioritas", "strict": True, "options": [
            _o("low", "Rendah"), _o("medium", "Sedang"), _o("high", "Tinggi"),
            _o("urgent", "Urgent"),
        ],
    },
    # ---------------- layanan pelanggan ----------------
    "complaint_category": {
        "label": "Kategori Komplain", "strict": True, "options": [
            _o("konstruksi", "Konstruksi/Bangunan"), _o("pembayaran", "Pembayaran"),
            _o("dokumen", "Dokumen & Legal"), _o("fasilitas", "Fasilitas & Lingkungan"),
            _o("layanan", "Layanan/Respon"), _o("lainnya", "Lainnya"),
        ],
    },
    "complaint_status": {
        "label": "Status Komplain", "strict": True, "options": [
            _o("open", "Baru"), _o("in_progress", "Ditangani"),
            _o("resolved", "Selesai"), _o("closed", "Ditutup"),
        ],
    },
    "kyc_status": {
        "label": "Status KYC", "strict": True, "options": [
            _o("draft", "Draft"), _o("submitted", "Diajukan"),
            _o("verified", "Terverifikasi"), _o("rejected", "Ditolak"),
        ],
    },
    # ---------------- keuangan ----------------
    "account_type": {
        "label": "Tipe Akun", "strict": True, "options": [
            _o("asset", "Aset"), _o("liability", "Liabilitas"), _o("equity", "Ekuitas"),
            _o("revenue", "Pendapatan"), _o("expense", "Beban"),
        ],
    },
    "payment_method": {
        "label": "Metode Pembayaran", "strict": True, "options": [
            _o("transfer", "Transfer bank"), _o("cash", "Tunai"),
            _o("virtual_account", "Virtual account"), _o("cheque", "Cek/Giro"),
            _o("kpr", "Pencairan KPR"),
        ],
    },
    "po_type": {
        "label": "Jenis PO", "strict": True, "options": [
            _o("material", "Material"), _o("subcon", "Jasa Subkontraktor"),
            _o("general", "Umum / jasa lain"),
        ],
    },
    "po_status": {
        "label": "Status PO", "strict": True, "options": [
            _o("draft", "Draft"), _o("approved", "Disetujui"),
            _o("partially_received", "Diterima sebagian"), _o("received", "Diterima"),
            _o("cancelled", "Batal"),
        ],
    },
    "spk_status": {
        "label": "Status SPK", "strict": True, "options": [
            _o("draft", "Draft"), _o("active", "Aktif"),
            _o("completed", "Selesai"), _o("cancelled", "Batal"),
        ],
    },
    "punch_status": {
        "label": "Status Punch List", "strict": True, "options": [
            _o("open", "Terbuka"), _o("in_progress", "Dikerjakan"),
            _o("verified", "Diverifikasi"), _o("closed", "Selesai"),
        ],
    },
    "threeway_status": {
        "label": "Hasil 3-Way Match", "strict": True, "options": [
            _o("matched", "Cocok"), _o("flagged", "Ditandai (perlu tinjauan)"),
        ],
    },
    "stock_movement": {
        "label": "Jenis Mutasi Stok", "strict": True, "options": [
            _o("in", "Penerimaan / GRN (masuk)"), _o("out", "Pengeluaran / Issue (keluar)"),
        ],
    },
    "qc_result": {
        "label": "Hasil QC", "strict": True, "options": [
            _o("pass", "Lulus"), _o("fail", "Gagal"),
        ],
    },
    "signer_role": {
        "label": "Peran Penanda Tangan", "strict": True, "options": [
            _o("buyer", "Pembeli"), _o("seller", "Penjual"), _o("sales", "Sales"),
            _o("witness", "Saksi"), _o("notary", "Notaris"),
        ],
    },
    "scheme_basis": {
        "label": "Dasar Termin", "strict": True, "options": [
            _o("percent", "Persen (%) dari harga"), _o("fixed", "Nominal tetap (Rp)"),
        ],
    },
    # ---------------- KPR / pembiayaan ----------------
    "financing_status": {
        "label": "Status KPR", "strict": True, "options": [
            _o("draft", "Draft"), _o("submitted", "Diajukan"), _o("approved", "Disetujui"),
            _o("rejected", "Ditolak"), _o("disbursing", "Pencairan berjalan"),
            _o("done", "Selesai (cair penuh)"),
        ],
    },
    "slik_status": {
        "label": "Hasil BI/SLIK Checking", "strict": True, "options": [
            _o("pending", "Menunggu"), _o("clear", "Clear (lancar) → disetujui"),
            _o("flagged", "Flagged (perlu review)"), _o("rejected", "Rejected (ditolak)"),
        ],
    },
    "financing_bank": {
        # Fase 27: satu daftar bank dipakai bersama (KPR pembeli, rekening agen/mitra) —
        # sengaja TIDAK diduplikasi jadi grup "bank" tersendiri.
        "label": "Bank / Lembaga Keuangan", "strict": False, "dynamic": True,
        "source": {"collection": "financing_apps", "field": "bank_name"},
        "options": [
            _o("BTN", "Bank BTN"), _o("BNI", "Bank BNI"), _o("BRI", "Bank BRI"),
            _o("Mandiri", "Bank Mandiri"), _o("BCA", "Bank BCA"),
            _o("CIMB Niaga", "CIMB Niaga"), _o("Permata", "Bank Permata"),
            _o("Danamon", "Bank Danamon"), _o("BSI", "Bank Syariah Indonesia"),
            _o("Muamalat", "Bank Muamalat"), _o("BJB", "Bank BJB"),
            _o("Panin", "Bank Panin"), _o("Maybank", "Maybank Indonesia"),
            _o("OCBC", "OCBC Indonesia"),
        ],
    },
    "tax_type": {
        "label": "Jenis Pajak", "strict": True, "options": [
            _o("ppn", "PPN"), _o("pph", "PPh Final"), _o("bphtb", "BPHTB"),
        ],
    },
    "commission_basis": {
        "label": "Dasar Komisi", "strict": True, "options": [
            _o("price", "Harga jual"), _o("net", "Nilai bersih (harga − PPN)"),
            _o("dp", "DP / kewajiban kontrak"),
        ],
    },
    "commission_trigger": {
        "label": "Pemicu Komisi", "strict": True, "options": [
            _o("booked", "Saat booking"), _o("paid_off", "Saat pelunasan (lunas)"),
            _o("akad", "Saat akad/AJB"),
        ],
    },
    "user_role": {
        # Peran dinamis: peran kustom (koleksi `roles`) ikut tampil di dropdown; validasi
        # keanggotaan dilakukan `admin_router` (is_known_role), bukan pydantic strict.
        "label": "Peran Pengguna", "strict": False, "dynamic": True,
        "source": {"collection": "roles", "field": "code", "label_field": "label", "label_format": "{label}"},
        "options": [
            _o("super_admin", "Super Admin"), _o("owner", "Owner/Direksi"),
            _o("sales_manager", "Sales Manager"), _o("marketing_admin", "Marketing Admin"),
            _o("sales", "Sales"), _o("finance", "Finance"),
            _o("project_manager", "Project Manager"), _o("site_engineer", "Site Engineer"),
            # Fase 29 — divisi yang tadinya tanpa pemimpin/anggota sendiri
            _o("dm_supervisor", "Supervisor Digital Marketing"),
            _o("dm_staff", "Staf Digital Marketing"),
            _o("finance_manager", "Supervisor Keuangan"),
            _o("legal_admin", "Admin Legal & Kepatuhan"),
        ],
    },
    # ================= Fase 26 — sisa vocabulary yang tadinya tercecer =================
    # ---------------- agenda, aktivitas & percakapan ----------------
    "appointment_status": {
        "label": "Status Agenda", "strict": True, "options": [
            _o("scheduled", "Terjadwal"), _o("done", "Selesai"),
            _o("cancelled", "Dibatalkan"), _o("no_show", "Tidak hadir"),
        ],
    },
    "activity_type": {
        "label": "Jenis Aktivitas", "strict": False, "dynamic": True,
        "source": {"collection": "activities", "field": "type"},
        "options": [
            _o("comment", "Komentar"), _o("system", "Sistem"), _o("contact", "Kontak"),
            _o("follow_up", "Follow-up"), _o("review", "Review"), _o("lead", "Lead"),
            _o("deal", "Deal"), _o("project", "Proyek"), _o("document", "Dokumen"),
            _o("finance", "Keuangan"), _o("financing", "KPR"), _o("survey", "Survei"),
            _o("complaint", "Komplain"), _o("material", "Material"),
            _o("procurement", "Pengadaan"), _o("permit", "Perizinan"),
            _o("commission", "Komisi"), _o("customer", "Pelanggan"),
            _o("manual", "Manual"), _o("receipt", "Penerimaan"),
        ],
    },
    "msg_direction": {
        "label": "Arah Pesan", "strict": True, "options": [
            _o("in", "Masuk (dari pelanggan)"), _o("out", "Keluar (dari agen)"),
        ],
    },
    "automation_trigger": {
        "label": "Pemicu Automasi", "strict": True, "options": [
            _o("message.received", "Pesan masuk diterima"),
            _o("lead.captured", "Lead baru masuk"),
            _o("no_response", "Tidak ada respon (idle)"),
        ],
    },
    "automation_action": {
        "label": "Aksi Automasi", "strict": True, "options": [
            _o("create_task", "Buat tugas"), _o("send_template", "Kirim template WA"),
            _o("suggest_stage", "Sarankan pindah tahap"), _o("notify", "Kirim notifikasi"),
        ],
    },
    # ---------------- survei & inspeksi ----------------
    "survey_check_status": {
        "label": "Status Item Checklist", "strict": True, "options": [
            _o("na", "Belum dinilai"), _o("ok", "Sesuai"), _o("issue", "Ada masalah"),
        ],
    },
    "survey_result": {
        "label": "Hasil Survei", "strict": True, "options": [
            _o("recommended", "Direkomendasikan"),
            _o("needs_followup", "Perlu tindak lanjut"),
            _o("not_recommended", "Tidak direkomendasikan"),
        ],
    },
    "survey_status": {
        "label": "Status Survei", "strict": True, "options": [
            _o("in_progress", "Sedang berjalan"), _o("completed", "Selesai"),
        ],
    },
    "faktur_status": {
        "label": "Status Faktur Pajak", "strict": True, "options": [
            _o("issued", "Terbit"), _o("cancelled", "Dibatalkan"),
        ],
    },
    "inspection_item_result": {
        "label": "Hasil Item Inspeksi", "strict": True, "options": [
            _o("pending", "Belum diperiksa"), _o("pass", "Lulus"),
            _o("fail", "Gagal"), _o("na", "Tidak berlaku"),
        ],
    },
    "inspection_status": {
        "label": "Status Inspeksi", "strict": True, "options": [
            _o("in_progress", "Sedang diperiksa"), _o("passed", "Lulus"),
            _o("failed", "Gagal (perlu perbaikan)"),
        ],
    },
    # ---------------- dokumen, deal & legal ----------------
    "document_status": {
        "label": "Status Dokumen", "strict": True, "options": [
            _o("draft", "Draft"), _o("finalized", "Final (siap tanda tangan)"),
            _o("signed", "Ditandatangani"),
        ],
    },
    "deal_status": {
        "label": "Status Deal", "strict": True, "options": [
            _o("reserved", "Reservasi"), _o("booked", "Booking"),
            _o("completed", "Selesai (AJB)"), _o("cancelled", "Batal"),
        ],
    },
    "legal_stage": {
        "label": "Tahap Legal", "strict": True, "options": [
            _o("reserved", "Reservasi"), _o("booked", "Booking"),
            _o("ppjb", "PPJB ditandatangani"), _o("ajb", "AJB / akad"),
        ],
    },
    "unit_payment_status": {
        "label": "Status Pembayaran Unit", "strict": True, "options": [
            _o("none", "Belum ada pembayaran"), _o("booking_fee", "Baru booking fee"),
            _o("partial", "Sebagian"), _o("paid_off", "Lunas"),
        ],
    },
    # ---------------- keuangan (subledger) ----------------
    "ar_status": {
        "label": "Status Piutang", "strict": True, "options": [
            _o("unpaid", "Belum bayar"), _o("partial", "Sebagian"), _o("paid", "Lunas"),
        ],
    },
    "ap_status": {
        "label": "Status Tagihan Vendor", "strict": True, "options": [
            _o("pending_approval", "Menunggu persetujuan"), _o("approved", "Disetujui"),
            _o("partial", "Dibayar sebagian"), _o("paid", "Lunas"),
        ],
    },
    "commission_status": {
        "label": "Status Komisi", "strict": True, "options": [
            _o("pending", "Menunggu"), _o("approved", "Disetujui"), _o("paid", "Dibayar"),
        ],
    },
    "collection_bucket": {
        "label": "Kelompok Penagihan", "strict": True, "options": [
            _o("current", "Lancar"), _o("due_soon", "Jatuh tempo dekat"),
            _o("overdue", "Menunggak"),
        ],
    },
    "deposit_txn": {
        "label": "Jenis Mutasi Titipan", "strict": True, "options": [
            _o("in", "Titipan masuk (kelebihan bayar)"),
            _o("apply", "Dipakai untuk termin"),
            _o("refund", "Dikembalikan ke pelanggan"),
        ],
    },
    "tax_status": {
        "label": "Status Pajak", "strict": True, "options": [
            _o("pending", "Belum dilaporkan"), _o("reported", "Sudah dilapor (SPT)"),
            _o("paid", "Sudah disetor"),
        ],
    },
    # ---------------- pengadaan & material ----------------
    "requisition_status": {
        "label": "Status Permintaan Material", "strict": True, "options": [
            _o("submitted", "Diajukan"), _o("approved", "Disetujui"),
            _o("partially_issued", "Dikeluarkan sebagian"), _o("issued", "Dikeluarkan penuh"),
            _o("rejected", "Ditolak"),
        ],
    },
    "claim_status": {
        "label": "Status Klaim Termin", "strict": True, "options": [
            _o("draft", "Draft"), _o("submitted", "Diajukan"),
            _o("verified", "Diverifikasi lapangan"), _o("approved", "Disetujui (jadi tagihan)"),
            _o("rejected", "Ditolak"),
        ],
    },
    "change_order_status": {
        "label": "Status Change Order", "strict": True, "options": [
            _o("draft", "Draft"), _o("approved", "Disetujui"), _o("rejected", "Ditolak"),
        ],
    },
    # ---------------- organisasi (multi-tenant) ----------------
    "org_status": {
        "label": "Status Organisasi", "strict": True, "options": [
            _o("active", "Aktif"), _o("suspended", "Ditangguhkan"),
        ],
    },
    # ---------------- relasi vendor (dinamis dari data yang ada) ----------------
    "vendor": {
        "label": "Vendor / Subkontraktor", "strict": False, "dynamic": True,
        "sources": [{"collection": "subcontractors", "field": "name"},
                    {"collection": "ap_invoices", "field": "vendor"},
                    {"collection": "purchase_orders", "field": "vendor"}],
        "options": [],
    },
    # ---------------- template & notifikasi ----------------
    "document_template": {
        "label": "Template Dokumen", "strict": False, "dynamic": True,
        "source": {"collection": "document_templates", "field": "code"},
        "options": [
            _o("SPR", "Surat Pemesanan Rumah (SPR)"),
            _o("PPJB", "Perjanjian Pengikatan Jual Beli (PPJB)"),
            _o("AJB", "Akta Jual Beli (AJB)"),
        ],
    },
    "inspection_template": {
        "label": "Template Inspeksi", "strict": False, "dynamic": True,
        "source": {"collection": "inspection_templates", "field": "code"},
        "options": [
            _o("QC-STR", "Inspeksi Struktur"), _o("QC-MEP", "Inspeksi MEP"),
            _o("QC-HO", "Inspeksi Serah Terima (Handover)"),
        ],
    },
    "wa_template_status": {
        "label": "Status Template WA", "strict": True, "options": [
            _o("pending", "Menunggu review Meta"), _o("approved", "Disetujui"),
            _o("rejected", "Ditolak"),
        ],
    },
    "notification_type": {
        "label": "Jenis Notifikasi", "strict": False, "dynamic": True,
        "source": {"collection": "notifications", "field": "type"},
        "options": [
            _o("info", "Informasi"), _o("finance", "Keuangan"), _o("sla", "SLA"),
            _o("material", "Material"), _o("approval", "Persetujuan"),
        ],
    },
}
