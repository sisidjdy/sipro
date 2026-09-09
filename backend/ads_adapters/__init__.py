"""ads_adapters — satu KONTRAK untuk data platform iklan, dua mode yang jujur.

`list_campaigns(period)` dan `daily_insights(period)` punya bentuk hasil yang SAMA baik saat
kredensial terpasang (`live`) maupun tidak (`simulation`). Itu syarat DoD §9.4 spec
`docs/v2/30_MARKETING_INTEGRATION_SPEC.md`: mengisi env tidak boleh mengubah kontrak API,
hanya mengubah `mode`.

Mode simulasi TIDAK mengarang angka. Ia mengembalikan apa yang benar-benar ada di database
(`campaigns` + `ad_spend` hasil input manual/CSV) dan menandainya `source="manual"|"csv"`,
sehingga layar tidak pernah menampilkan angka seolah datang dari platform.
"""
from ads_adapters import google, meta  # noqa: F401  (registry di bawah)

ADAPTERS = {"meta": meta, "google": google}

# Peta env per integrasi (SSOT untuk halaman Status Integrasi). Nilainya TIDAK pernah
# dibaca ke luar server — hanya "terisi/tidak".
ENV_SPEC = {
    "meta_ads": {
        "platform": "meta",
        "env": ("META_APP_ID", "META_APP_SECRET", "META_VERIFY_TOKEN",
                "META_SYSTEM_USER_TOKEN", "META_AD_ACCOUNT_ID"),
        "purpose": "Verifikasi webhook Lead Ads, tarik kampanye & biaya harian dari Ads Manager.",
        "fallback": "Webhook tetap menerima payload uji; biaya iklan diinput manual/CSV.",
    },
    "google_ads": {
        "platform": "google",
        "env": ("GOOGLE_ADS_DEVELOPER_TOKEN", "GOOGLE_ADS_CLIENT_ID",
                "GOOGLE_ADS_CLIENT_SECRET", "GOOGLE_ADS_REFRESH_TOKEN",
                "GOOGLE_ADS_CUSTOMER_ID"),
        "purpose": "Tarik kampanye & biaya harian Google Ads, kirim Enhanced Conversions.",
        "fallback": "Lead Form tetap masuk lewat webhook; biaya diinput manual/CSV.",
    },
    "tiktok_ads": {
        "platform": None,
        "env": ("TIKTOK_EVENTS_TOKEN",),
        "purpose": "Kirim event konversi (Events API) untuk kampanye TikTok.",
        "fallback": "Event konversi dicatat sebagai simulasi dan bisa dikirim ulang nanti.",
    },
    "whatsapp": {
        "platform": None,
        "env": ("WHATSAPP_TOKEN", "WHATSAPP_PHONE_ID"),
        "purpose": "Kirim & terima pesan WhatsApp Cloud API (template, broadcast, inbox).",
        "fallback": "Pesan disimpan bermode simulasi; percakapan tetap utuh.",
    },
    "web_pixel": {
        "platform": None,
        "env": ("WEB_PIXEL_TOKEN",),
        "purpose": "Kirim event konversi dari form website ke pixel situs.",
        "fallback": "Event dicatat lokal (simulasi).",
    },
}


def get(platform: str):
    """Adapter platform, atau None bila platform itu belum punya adapter tarik-data."""
    return ADAPTERS.get(platform)


def modes() -> dict:
    return {name: mod.mode() for name, mod in ADAPTERS.items()}
