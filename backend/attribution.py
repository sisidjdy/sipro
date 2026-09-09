"""attribution.py — Fase 43: bentuk baku ATRIBUSI lead (satu tempat, dipakai semua kanal).

Kenapa dipisah dari `engine.process_lead_capture`:

1. **Atribusi punya aturan sendiri dan harus sama di semua pintu masuk.** Lead bisa datang
   dari 6 webhook, form showroom publik, portal mitra, dan input manual. Selama bentuk
   atribusinya ditulis ulang di setiap pintu, satu pintu akan lupa satu field — dan biaya
   iklan berhenti bertemu leadnya tanpa ada yang sadar.
2. **`campaign_id` lebih dipercaya daripada nama kampanye.** Nama kampanye bisa diganti
   kapan saja di Ads Manager; ID-nya tidak. Karena itu keduanya disimpan.
3. **`first_touch` / `last_touch` disimpan sebagai FAKTA**, bukan dihitung ulang belakangan.
   Admin boleh mengganti model atribusi (first/last touch) di Pusat Konfigurasi; kalau
   sentuhannya tidak pernah dicatat, mengganti model hanya mengubah tebakan.
"""

ATTRIBUTION_FIELDS = (
    "campaign_id", "adset_id", "ad_id", "creative_id", "form_id",
    "utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term",
    "fbclid", "gclid", "landing_url", "referrer",
)


def build(payload: dict) -> dict:
    """Atribusi lengkap dari payload webhook/form (field yang tidak ada -> None)."""
    data = payload or {}
    return {field: data.get(field) for field in ATTRIBUTION_FIELDS}


def campaign_of(payload: dict) -> str:
    """Nama kampanye: `campaign` bila ada, kalau tidak `utm_campaign` (form website)."""
    data = payload or {}
    return data.get("campaign") or data.get("utm_campaign")


def touch(*, at: str, provider: str, source: str, attribution: dict, campaign: str = None,
          partner_id: str = None) -> dict:
    """Satu 'sentuhan' — dipakai untuk first_touch & last_touch."""
    return {"at": at, "provider": provider, "source": source, "campaign": campaign,
            "campaign_id": (attribution or {}).get("campaign_id"),
            "ad_id": (attribution or {}).get("ad_id"), "partner_id": partner_id}
