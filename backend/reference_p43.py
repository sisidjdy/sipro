"""SSOT reference registry — TAMBAHAN Fase 43 (Kampanye, Biaya Iklan, Atribusi & CAPI).

Alasan file terpisah sama seperti fase sebelumnya: `reference.py` sudah menyentuh batas gate
compliance (≤800 baris). Grup di sini digabungkan ke `reference.GROUPS` lewat `_PHASES`,
sehingga validator backend, `GET /api/reference`, dan tab Kamus Data mengenalinya tanpa
kosakata kembar.

Keputusan kosakata yang perlu dijelaskan:
  * `capi_event_name` memakai nama event **apa adanya milik platform** (`Lead`,
    `SubmitApplication`, `InitiateCheckout`, `Purchase`) sebagai VALUE, karena nilai itulah
    yang benar-benar dikirim ke Meta/Google — menerjemahkannya ke bahasa Indonesia di level
    data akan membuat payload salah saat kredensial dinyalakan. Yang diterjemahkan hanya
    LABEL-nya (dipakai layar), persis pola grup lain.
  * `ad_spend_source` memisahkan `manual|csv|api`. Ini bukan hiasan: satu tabel biaya iklan
    bisa berisi angka dari tiga asal yang tingkat kepercayaannya berbeda, dan spec
    `docs/v2/30_MARKETING_INTEGRATION_SPEC.md` §1 melarang menampilkan angka seolah dari
    platform padahal diketik tangan.
  * `ads_cost_status` (`complete|partial|missing`) adalah kosakata KEJUJURAN ANGKA: metrik
    berbasis biaya (CPL/CAC/ROAS) tidak boleh ditampilkan sebagai 0 ketika biayanya belum
    diinput — pelajaran Fase 36/37 yang ditulis ulang di spec §8.
  * `integration_mode` (`live|simulation`) SATU grup untuk dua tempat: transport event CAPI
    dan lencana kesiapan integrasi. Dulu tiap layar menulis sendiri teks "SIMULASI".
"""


def _o(value: str, label: str) -> dict:
    return {"value": value, "label": label}


GROUPS_P43: dict = {
    # ---------------- master kampanye ----------------
    "ad_platform": {
        "label": "Platform Iklan", "strict": True, "options": [
            _o("meta", "Meta Ads (Facebook/Instagram)"), _o("google", "Google Ads"),
            _o("tiktok", "TikTok Ads"), _o("other", "Lainnya / offline"),
        ],
    },
    "campaign_objective": {
        "label": "Tujuan Kampanye", "strict": True, "options": [
            _o("leads", "Kumpulkan lead (form)"), _o("messages", "Percakapan WhatsApp"),
            _o("traffic", "Kunjungan situs/landing"), _o("awareness", "Awareness / jangkauan"),
            _o("conversions", "Konversi di situs"), _o("other", "Lainnya"),
        ],
    },
    "campaign_status": {
        "label": "Status Kampanye", "strict": True, "options": [
            _o("draft", "Draf (belum jalan)"), _o("active", "Aktif"),
            _o("paused", "Dijeda"), _o("ended", "Berakhir"),
        ],
    },
    # ---------------- biaya iklan ----------------
    "ad_spend_source": {
        "label": "Asal Angka Biaya", "strict": True, "options": [
            _o("manual", "Input manual"), _o("csv", "Impor CSV"),
            _o("api", "Tarikan API platform"),
        ],
    },
    "ads_import_status": {
        "label": "Status Impor Biaya", "strict": True, "options": [
            _o("preview", "Pratinjau (belum disimpan)"), _o("committed", "Sudah disimpan"),
            _o("failed", "Gagal (berkas ditolak)"),
        ],
    },
    "ads_row_status": {
        "label": "Hasil Baris Impor", "strict": True, "options": [
            _o("new", "Baris baru"), _o("update", "Memperbarui angka lama"),
            _o("unchanged", "Sama dengan data tersimpan"), _o("rejected", "Ditolak"),
        ],
    },
    "ads_period": {
        "label": "Rentang Agregasi", "strict": True, "options": [
            _o("daily", "Harian"), _o("weekly", "Mingguan"), _o("monthly", "Bulanan"),
        ],
    },
    "ads_cost_status": {
        "label": "Kelengkapan Data Biaya", "strict": True, "options": [
            _o("complete", "Biaya lengkap"), _o("partial", "Biaya belum lengkap"),
            _o("missing", "Biaya belum diinput"),
        ],
    },
    "ads_attribution_level": {
        "label": "Tingkat Atribusi", "strict": True, "options": [
            _o("campaign", "Kampanye"), _o("adset", "Ad set / grup iklan"),
            _o("ad", "Iklan"), _o("creative", "Materi (creative)"),
        ],
    },
    "ads_channel_group": {
        "label": "Kelompok Kanal", "strict": True, "options": [
            _o("ads", "Iklan berbayar"), _o("partner", "Mitra / referral"),
            _o("organic", "Organik & walk-in"),
        ],
    },
    # ---------------- CAPI ----------------
    "capi_event_name": {
        "label": "Event Konversi (CAPI)", "strict": True, "options": [
            _o("Lead", "Lead masuk"),
            _o("SubmitApplication", "SPR ditandatangani"),
            _o("InitiateCheckout", "Booking / reservasi unit"),
            _o("Purchase", "AJB / pelunasan"),
        ],
    },
    "capi_status": {
        "label": "Status Kirim Event", "strict": True, "options": [
            _o("sent", "Terkirim ke platform"), _o("failed", "Gagal kirim"),
            _o("pending", "Menunggu kirim"),
            # `simulated` ADA karena tanpa kredensial tidak ada paket yang benar-benar keluar.
            # Sebelum Fase 43 baris seperti ini berstatus "sent" — layar audit menampilkan
            # "Terkirim" untuk event yang tidak pernah dikirim ke mana pun.
            _o("simulated", "Dicatat (simulasi, belum dikirim)"),
        ],
    },
    "integration_mode": {
        "label": "Mode Integrasi", "strict": True, "options": [
            _o("live", "Live (kredensial terpasang)"),
            _o("simulation", "Simulasi (tanpa kredensial)"),
        ],
    },
    "integration_target": {
        "label": "Integrasi", "strict": True, "options": [
            _o("meta_ads", "Meta Ads & Lead Ads"), _o("google_ads", "Google Ads"),
            _o("tiktok_ads", "TikTok Ads"), _o("whatsapp", "WhatsApp Cloud API"),
            _o("web_pixel", "Web Pixel situs"),
        ],
    },
}

# Sinonim Fase 43. Judul kolom laporan platform memakai nama dagang ("Meta Ads", "Facebook",
# "Google Ads"), sementara kosakata kami memakai nama platform pendek. Tanpa peta ini setiap
# baris CSV hasil ekspor Ads Manager ditolak "platform tidak dikenal" dan pemakai harus
# mengedit berkas ekspornya dengan tangan.
SYNONYMS_P43: dict = {
    "ad_platform": {
        "meta_ads": "meta", "facebook": "meta", "facebook_ads": "meta", "fb": "meta",
        "instagram": "meta", "ig": "meta", "meta_lead_ads": "meta",
        "google_ads": "google", "adwords": "google", "google_lead": "google",
        "tiktok_ads": "tiktok", "tiktok_lead": "tiktok",
        "lainnya": "other", "offline": "other", "manual": "other",
    },
}
