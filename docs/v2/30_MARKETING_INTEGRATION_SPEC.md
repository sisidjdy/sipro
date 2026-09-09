# 30 — SPEC INTEGRASI DIGITAL MARKETING (Meta Ads, Google Ads, WhatsApp)

> Keputusan **D1**: **struktur siap-live + biaya iklan diinput manual/CSV dulu**; lead capture webhook tetap real; kredensial menyusul.
> Basis kode yang sudah ada: `routers/webhooks_router.py` (webhook publik), `capture_failures.py` (dead-letter), `capi.py` (CAPI feedback, simulasi/live otomatis), `routers/omnichannel_router.py` (channels, templates, attribution), `wa_playbooks.py`.
> Menutup CR-14 sisi data biaya + menyiapkan CR-9 (mitra) & Dok 31 (BI).

## 1. Prinsip kejujuran mode (dipertahankan dari Fase 17)
Setiap integrasi punya `mode`: `live` (kredensial ada & sehat) atau `simulation` (tanpa kredensial). UI **wajib** menampilkan lencana mode pada halaman terkait. Dilarang menampilkan angka seolah dari platform bila sumbernya simulasi/manual — label sumber data (`api|csv|manual`) selalu ditampilkan di tabel & grafik.

## 2. Matriks environment (satu tempat untuk semua kredensial)

| Env | Untuk | Mode bila kosong | Cara dapat |
|---|---|---|---|
| `META_APP_ID`, `META_APP_SECRET` | verifikasi webhook & Graph API | simulation | Meta App Dashboard |
| `META_VERIFY_TOKEN` | verifikasi endpoint webhook | wajib untuk live capture | dibuat sendiri |
| `META_PAGE_TOKEN` / `META_SYSTEM_USER_TOKEN` | tarik Lead Ads & data kampanye | simulation | Business Settings › System User |
| `META_AD_ACCOUNT_ID` | tarik spend/insights | manual/CSV | Ads Manager |
| `META_CAPI_TOKEN`, `META_PIXEL_ID` | CAPI (sudah dipakai `capi.py:32`) | simulation | Events Manager |
| `WHATSAPP_TOKEN`, `WHATSAPP_PHONE_ID` | WA Cloud API (sudah dibaca kode) | simulation | WABA › API Setup |
| `GOOGLE_ADS_DEVELOPER_TOKEN`, `GOOGLE_ADS_CLIENT_ID`, `GOOGLE_ADS_CLIENT_SECRET`, `GOOGLE_ADS_REFRESH_TOKEN`, `GOOGLE_ADS_CUSTOMER_ID` | Google Ads API (kampanye+spend) | manual/CSV | Google Ads API Center |
| `GOOGLE_ADS_CONV_TOKEN` | Enhanced Conversions (dipakai `capi.py:33`) | simulation | Google Ads |
| `TIKTOK_EVENTS_TOKEN`, `WEB_PIXEL_TOKEN` | opsional | simulation | — |

Semua dibaca lewat `os.environ.get` (pola yang sudah ada) — **tidak ada kredensial di kode**; status kesiapan ditampilkan di **Konfigurasi › Integrasi** (hanya "terisi/tidak", nilai tidak pernah ditampilkan).

## 3. Lead capture (REAL sekarang)

| Kanal | Endpoint | Catatan |
|---|---|---|
| Meta Lead Ads | `GET/POST /api/webhooks/meta` | GET = verifikasi `hub.challenge`; POST = `leadgen` → (live) tarik detail via Graph `/{leadgen_id}`; (simulasi) pakai payload uji |
| Google Lead Form | `POST /api/webhooks/google-lead` | verifikasi `google_key` (⚠️ konfirmasi nama header saat live) |
| TikTok Lead | `POST /api/webhooks/tiktok` | opsional |
| Form Website | `POST /api/webhooks/website` | + `utm_*`, `fbclid`, `gclid` |
| WhatsApp masuk | `POST /api/webhooks/whatsapp` | click-to-chat → lead + percakapan |
| **Mitra** (baru) | `POST /api/webhooks/partner/{partner_id}` | token per mitra, rate-limit, dedup ([25](25_PARTNER_SPEC.md) §4) |

**Atribusi yang disimpan pada lead** (sudah sebagian ada): `source, campaign, attribution{campaign_id, adset_id, ad_id, creative_id, form_id, utm_source, utm_medium, utm_campaign, utm_content, utm_term, fbclid, gclid, landing_url, referrer}`, `partner_id`, `first_touch{}`, `last_touch{}`.
**Dead-letter tetap wajib**: payload cacat masuk `capture_failures` (jangan pernah dibuang) — sudah berjalan.

## 4. Master kampanye (`campaigns`)
`platform(meta|google|tiktok|other), external_id, name, objective, project_id[], cluster_id[], audience_note, budget_daily, budget_total, start_date, end_date, status, owner_email, source(api|manual), last_synced_at`.
- **Manual sekarang**: user membuat kampanye + anggaran; `external_id` diisi bila tahu (agar cocok saat API menyala nanti).
- **Saat live**: sinkronisasi `campaigns` dari platform (adapter `ads_adapters/meta.py`, `ads_adapters/google.py`) — kontrak fungsi: `list_campaigns(period) -> [CampaignDTO]`, `daily_insights(period) -> [SpendDTO]`. Adapter simulasi mengembalikan data dari `campaigns`/`ad_spend` manual, **bukan angka karangan**.

## 5. Biaya iklan manual/CSV (`ad_spend`) — inti keputusan D1
**Kunci natural (idempoten):** `(org_id, platform, campaign_id, adset_id, ad_id, date)`.
**Kolom CSV wajib:** `date, platform, campaign_name, campaign_id?, adset_name?, adset_id?, ad_name?, ad_id?, spend, impressions?, clicks?, leads_platform?, currency?`.
**Alur impor:** unggah → **pratinjau/dry-run** (validasi format, mata uang, duplikat, kampanye tak dikenal) → pemetaan kolom (disimpan sebagai profil impor per platform) → commit → laporan hasil (baris masuk/diperbarui/ditolak + alasan). Semua impor tercatat: `imported_by, file_id, rows, checksum`.
**Entri manual harian**: form ringkas (tanggal, kampanye, biaya) untuk tim yang tidak mau CSV.
**Endpoint:**
```
GET  /api/ads/campaigns            (filter platform/proyek/status)
POST /api/ads/campaigns
GET  /api/ads/spend                (agregasi harian/mingguan/bulanan)
POST /api/ads/spend                (entri manual)
POST /api/ads/spend/import         (CSV: dry_run=true|false)
GET  /api/ads/spend/import/{id}    (laporan impor)
POST /api/ads/sync                 (aktif hanya bila kredensial live)
GET  /api/ads/health               (status mode per platform)
```

## 6. CAPI feedback (sudah ada, dirapikan)
`capi.py` tetap: event `Lead` (lead masuk), `InitiateCheckout` (booking/reservasi), `Purchase` (akad/AJB). V2 menambah:
- `SubmitApplication` saat SPR ditandatangani (nilai = total kontrak) — sinyal lebih awal untuk optimasi iklan.
- Field `event_id` (dedup platform) + `user_data` ter-hash (SHA-256 telepon/email) supaya siap live tanpa ubah kontrak.
- Halaman **Marketing › Atribusi & CAPI**: tabel event, mode transport, status kirim, tombol kirim ulang (bila live).

## 7. WhatsApp (WA Cloud API)
- Adapter `wa_adapter.py`: `send_template(to, template, params)`, `send_text(to, body)`, `mark_read`, `media_url`. Live bila `WHATSAPP_TOKEN` + `WHATSAPP_PHONE_ID` ada; jika tidak, simpan pesan sebagai `simulation` (sudah pola sekarang) dan tampilkan lencana.
- Template WA tetap dikelola di `wa_templates` + `wa_playbooks` (sudah ada), termasuk playbook follow-up untuk **reschedule/batal survei** ([24](24_CRM_LEAD_SPEC.md) §10) dan **penagihan termin** ([26](26_CUSTOMER_LEGAL_SPEC.md) §5).
- 24 jam window & kategori (utility/marketing) dihormati: pesan marketing di luar window wajib template disetujui — divalidasi sebelum kirim (cegah error 470 saat live).

## 8. Metrik yang lahir dari modul ini (dipakai [31](31_ANALYTICS_BI_SPEC.md))
`spend`, `impressions`, `clicks`, `CTR`, `CPC`, `leads`, `CPL = spend/leads`, `qualified_rate`, `cost_per_qualified`, `booking_rate`, `CAC`, `ROAS = revenue/spend`, `attribution funnel per campaign/adset/ad/creative`, `partner vs ads vs organik`.
Bila `spend` belum ada untuk periode, metrik berbasis biaya **wajib menampilkan "data biaya belum lengkap"**, bukan 0 (aturan kejujuran angka — pelajaran Fase 36/37).

## 9. Definition of Done
1. Webhook Meta/Google/website/WA/mitra menerima payload nyata & lead muncul dengan atribusi lengkap (uji dengan payload contoh; cacat → dead-letter).
2. CSV spend bisa diimpor 2× tanpa duplikasi (idempoten) dan laporan impor jelas.
3. Halaman Kampanye & Biaya Iklan menampilkan spend, CPL, CAC, ROAS dengan **label sumber data**.
4. Menyalakan kredensial (isi env) **tidak** mengubah kontrak API — hanya mengubah `mode` menjadi `live` (uji dengan token dummy → health menunjukkan live/gagal secara jujur).
5. Gate baru `verify_ads.py` + `run_all_gates.sh` PASS.
