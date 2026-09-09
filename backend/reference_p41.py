"""SSOT reference registry — TAMBAHAN Fase 41 (jam tahap) & Fase 42 (mitra & fee).

Alasan file terpisah sama seperti fase sebelumnya: `reference.py` menyentuh batas gate
compliance (≤800 baris). Grup di sini digabungkan ke `reference.GROUPS` lewat `_PHASES`,
sehingga validator backend, `GET /api/reference`, dan tab Kamus Data mengenalinya tanpa
kosakata kembar.

Dua grup lama DIPERLUAS di sini (nilai lama TETAP ADA, tidak ada migrasi paksa):
  * `agent_status`          + `suspended`, `expired`  — mitra ditangguhkan / kontrak lewat
    masa berlaku adalah keadaan nyata yang memblokir lead & fee baru
    (`docs/v2/25_PARTNER_SPEC.md` §2). Sebelumnya hanya ada active/inactive/blacklist,
    sehingga "kontrak habis" harus dipalsukan menjadi "tidak aktif".
  * `marketing_fee_trigger` + 6 pemicu Fase 42 (`booking_fee_verified`, `spr_signed`,
    `ppjb_signed`, `akad_kredit`, `ajb_signed`, `full_payment`). Dulu pemicu fee memakai
    kosakata sendiri (`booking/ppjb/dp_lunas/akad/bast`) yang tidak bisa memetakan pemicu
    aturan mitra 1:1 — dan satu field `trigger` tidak boleh berisi dua kosakata tanpa label.
"""


def _o(value: str, label: str) -> dict:
    return {"value": value, "label": label}


GROUPS_P41: dict = {
    # ---------------- Fase 41 — jam tahap / aging ----------------
    "sla_state": {
        "label": "Keadaan SLA", "strict": True, "options": [
            _o("ok", "Dalam SLA"), _o("over", "Lewat SLA"),
            _o("over2", "Lewat 2× SLA"), _o("none", "Tanpa SLA (tahap akhir)"),
        ],
    },
    "aging_entity": {
        "label": "Objek Umur Tahap", "strict": True, "options": [
            _o("lead", "Lead"), _o("deal", "Deal & Unit"), _o("task", "Tugas"),
            _o("complaint", "Komplain"), _o("customer", "Pembeli"),
            _o("ar_invoice", "Tagihan (AR)"), _o("document", "Dokumen"),
        ],
    },
    # ---------------- Fase 42 — mitra & aturan fee ----------------
    "partner_entity_type": {
        "label": "Bentuk Mitra", "strict": True, "options": [
            _o("individual", "Perorangan (PPh 21)"), _o("company", "Badan usaha (PPh 23)"),
        ],
    },
    "partner_price_base": {
        "label": "Dasar Harga Fee", "strict": True, "options": [
            _o("gross", "Harga jual (bruto)"), _o("after_discount", "Harga setelah diskon"),
            _o("nett", "Harga nett"),
        ],
    },
    "partner_tier_mode": {
        "label": "Mode Tingkat Fee", "strict": True, "options": [
            _o("percent", "Persen dari harga"), _o("fixed", "Nominal tetap"),
        ],
    },
    "partner_fee_period": {
        "label": "Periode Perhitungan Tingkat", "strict": True, "options": [
            _o("monthly", "Bulanan"), _o("quarterly", "Kuartalan"),
            _o("project", "Sepanjang proyek"),
        ],
    },
    "partner_qualify_rule": {
        "label": "Syarat Lead Terkualifikasi", "strict": True, "options": [
            _o("contacted", "Sudah dihubungi (kontak pertama tercatat)"),
            _o("survey_attended", "Survey dihadiri (status selesai)"),
            _o("booking", "Sampai tahap booking"),
        ],
    },
    "partner_rule_status": {
        "label": "Status Aturan Fee", "strict": True, "options": [
            _o("active", "Berlaku"), _o("inactive", "Tidak berlaku"),
        ],
    },
    # Jenis potongan PPh atas fee mitra. WAJIB terdaftar di sini: `models_p41.FeeTax.pph_type`
    # divalidasi lewat grup ini, jadi selama grup belum ada SETIAP pembuatan aturan fee yang
    # menyertakan blok `tax` mati dengan 500 (KeyError) di lapisan validasi request — bukan
    # 400 berbahasa Indonesia. Nilainya sengaja sama dengan `partner_fee.TAX_TYPES`
    # (mesin hitung murni tanpa I/O) supaya tidak ada kosakata kembar.
    "partner_tax_type": {
        "label": "Jenis Potongan PPh Fee", "strict": True, "options": [
            _o("pph21", "PPh 21 (mitra perorangan)"),
            _o("pph23", "PPh 23 (mitra badan usaha)"),
            _o("none", "Tanpa potongan PPh"),
        ],
    },
    "partner_conflict_status": {
        "label": "Status Sengketa Atribusi", "strict": True, "options": [
            _o("pending_review", "Menunggu peninjauan"), _o("resolved", "Diputuskan aturan"),
            _o("overridden", "Diputuskan manual"),
        ],
    },
    # ---------------- grup lama yang DIPERLUAS ----------------
    "agent_status": {
        "label": "Status Mitra / Agen", "strict": True, "options": [
            _o("active", "Aktif"), _o("suspended", "Ditangguhkan"),
            _o("inactive", "Tidak aktif"), _o("expired", "Kontrak kedaluwarsa"),
            _o("blacklist", "Daftar hitam"),
        ],
    },
    "marketing_fee_trigger": {
        "label": "Pemicu Marketing Fee", "strict": True, "options": [
            _o("booking", "Booking / NUP (istilah lama)"),
            _o("ppjb", "PPJB ditandatangani (istilah lama)"),
            _o("dp_lunas", "DP lunas (istilah lama)"),
            _o("akad", "Akad KPR / AJB (istilah lama)"),
            _o("bast", "Serah terima (istilah lama)"),
            _o("booking_fee_verified", "Booking fee terverifikasi"),
            _o("spr_signed", "SPR / reservasi ditandatangani"),
            _o("ppjb_signed", "PPJB ditandatangani"),
            _o("akad_kredit", "Akad kredit (KPR)"),
            _o("ajb_signed", "AJB ditandatangani"),
            _o("full_payment", "Pelunasan"),
        ],
    },
}
