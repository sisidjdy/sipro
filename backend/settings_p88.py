"""Setting Fase 88 — skor lead terkonfigurasi & kebijakan pelunasan serah terima.

Dipisah dari `settings_store.py` karena berkas itu mendekati batas 800 baris; dimuat dan
digabung ke `DEFAULTS` oleh `settings_store` (SSOT tetap satu registry).
"""


def _d(key, value, type_, group, label, help_, *, impact="", sensitive=False, minimum=None,
       maximum=None, options=None, src="SISTEM", ref_group=None):
    if ref_group:
        import reference as _ref
        options = list(_ref.values(ref_group))
    return {
        "key": key, "value": value, "type": type_, "group": group, "label": label,
        "help": help_, "impact": impact, "sensitive": sensitive, "min": minimum, "ref_group": ref_group,
        "max": maximum, "options": options or [], "source": src,
    }


DEFAULTS_P88: dict = {d["key"]: d for d in [
    # ============ Fase 88B/89: skor lead berbasis event terkonfigurasi ============
    _d("lead.score.events", [], "list", "lead", "Event skor lead",
       ("Daftar event yang menaikkan/menurunkan skor lead beserta poin, parameter (jendela hari, "
        "batas, ambang), status aktif, dan event kustom. Kosong = bawaan sistem. Disunting lewat "
        "Pusat Konfigurasi › Skor Lead (bukan JSON mentah)."),
       impact="Mengubah poin/aktif event mengubah urutan prioritas follow-up seluruh sales."),
    _d("lead.score.bands", {"hot_min": 70, "warm_min": 45}, "obj", "lead",
       "Ambang band skor (hot/warm)",
       "Skor ≥ hot_min = HOT, ≥ warm_min = WARM, di bawahnya COLD.",
       impact="Menurunkan ambang membuat lebih banyak lead tampak panas dari kenyataannya."),
    # ============ Fase 88E: pelunasan sebelum BAST ============
    _d("handover.settlement_policy", "wajib_lunas", "enum", "garansi",
       "Kebijakan pelunasan sebelum BAST",
       ("wajib_lunas: sisa tagihan > 0 MENAHAN BAST (hanya bisa diterobos Manajer Keuangan). "
        "minimal_persen: menahan hanya bila pembayaran < persen minimum. "
        "peringatan: sisa tagihan hanya menjadi PERINGATAN — BAST bisa terbit tanpa terobosan."),
       impact="Melonggarkan kebijakan ini berarti kunci bisa diserahkan sebelum rumah lunas.",
       sensitive=True, ref_group="handover_settlement_policy", src="DOC"),
    _d("handover.settlement_min_paid_pct", 90, "pct", "garansi",
       "Minimum terbayar sebelum BAST (%)",
       "Dipakai hanya bila kebijakan = minimal_persen.", sensitive=True, minimum=0, maximum=100),

    # ============ Fase 97C — aturan kirim WhatsApp ============
    _d("wa.send_window_start", "08:00", "str", "whatsapp", "Jam mulai kirim broadcast (WIB)",
       "Antrean broadcast/pesan massal hanya diproses mulai jam ini. Format HH:MM.",
       impact="Pesan yang antre sebelum jam ini menunggu, tidak dibuang."),
    _d("wa.send_window_end", "20:00", "str", "whatsapp", "Jam akhir kirim broadcast (WIB)",
       "Setelah jam ini antrean berhenti sampai jam mulai berikutnya. Format HH:MM."),
    _d("wa.rate_limit_per_sec", 20, "int", "whatsapp", "Batas laju kirim (pesan/detik)",
       "Jumlah pesan per detik yang dikirim ke Meta dari antrean. Bawaan Meta untuk nomor baru ±80/detik.",
       minimum=1, maximum=80),
    _d("wa.cost_marketing", 600, "money", "whatsapp", "Estimasi biaya percakapan MARKETING (Rp)",
       "Dipakai menghitung estimasi biaya broadcast promosi per penerima."),
    _d("wa.cost_utility", 300, "money", "whatsapp", "Estimasi biaya percakapan UTILITY (Rp)",
       "Pengingat tagihan, dokumen, notifikasi transaksi."),
    _d("wa.cost_authentication", 300, "money", "whatsapp", "Estimasi biaya percakapan AUTHENTICATION (Rp)",
       "OTP portal pembeli."),
    _d("wa.document_caption", "Halo {nama}, berikut {dokumen}{nomor} dari {org}. Simpan dokumen ini sebagai arsip Anda.",
       "str", "whatsapp", "Teks pengantar kirim dokumen via WhatsApp",
       "Placeholder: {nama}, {dokumen}, {nomor}, {org}. Dipakai saat sesi 24 jam terbuka (caption)."),
    _d("wa.document_template_code", "document_delivery", "str", "whatsapp",
       "Template UTILITY berheader dokumen untuk kirim PDF di luar sesi 24 jam",
       "Kode template `wa_templates` dengan header_type=document. Saat sesi tertutup, PDF dikirim sebagai "
       "parameter header template ini (wajib APPROVED saat live)."),
]}
