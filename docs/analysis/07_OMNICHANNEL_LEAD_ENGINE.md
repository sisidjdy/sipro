# SIPRO Rebuild — Dokumen 07
# OMNICHANNEL LEAD ENGINE: WhatsApp In-Chat + Ads Lead Capture + Conversational CRM

> Status: RISET MENDALAM (domain yang hilang di analisis awal). Bahasa: Indonesia.
> Sinergi: menjawab pain **SL-1 respons lambat** & **SL-2 lead bocor** (Dok 05), menjadi sumber utama **event** untuk **Guided Work Engine** (Dok 03 §6.5), dan wujud nyata visi **"Slack tapi ERP"** (Dok 03 §3) di sisi eksternal (pelanggan) — bukan hanya internal.
> Root-cause acuan: Dok 01 §1.3 (S3/S4), Dok 05 §1, Dok 06 §P1/P6.

---

## 0. KENAPA INI DOMAIN INTI (bukan pelengkap)

Grounded (Dok 05/06): **speed-to-lead adalah metrik #1** — lead dihubungi >5 menit turun peluang qualified **~21x**; sumber portal/ads hanya konversi **0,4–1,2%** sehingga **kecepatan + kualitas capture** menentukan ROI iklan. Maka rantai **Iklan → Capture instan → Percakapan (WA) → Trigger lifecycle → Task sales** adalah **mesin konversi utama** developer, bukan modul komunikasi terpisah.

**Fakta SIPRO lama (grounded, lihat kode):**
- `whatsapp/send` = **SIMULASI** (langsung set status "sent"); tak ada inbound/webhook; incoming detection **NOT STARTED**.
- `auto_followup_rules` punya `trigger_event` (mis. `lead.created`) + `channel` (whatsapp/in_app) + template variabel — **tapi hanya jalan via `/simulate-followup` manual**.
- WA muncul di **lead timeline** (`server.py:1018`) → niatnya percakapan menempel ke lead.
- `meta_ads/google_ads/tiktok_ads` hanya **label sumber**; **tak ada webhook capture**.

→ Artinya: **niat produk sudah benar, eksekusi 0%.** SIPRO baru harus menjadikannya **nyata & real-time**.

---

## BAGIAN A — SEAMLESS LEAD CAPTURE (Ads → SIPRO, real-time)

### A1. Prinsip (grounded 2026)
- **Webhook, bukan polling**: lead masuk CRM **<30 detik** (biasanya 5–10 dtk). Penting karena Meta hanya simpan lead **90 hari** & speed-to-lead menentukan konversi.
- **Tangkap konteks penuh**: `campaign_id`, `adset_id`, `creative_id`, `form_id`, timestamp, field form → untuk **atribusi ROI** (campaign spend vs closure, Dok 06 §3).
- **Feedback loop (CAPI)**: kirim event hilir (**Qualified / Opportunity / Closed-Won**) **kembali ke Meta** → algoritma belajar cari **"conversion leads"**, bukan sekadar pengisi form. Target: kirim dalam 7 hari, ≥50 event/minggu/adset.
- **Dedup** via kunci unik (phone E.164 / email / lead_id ads) — cegah lead ganda.

### A2. Arsitektur capture (SIPRO)
```
Meta/Google/TikTok Lead Form  ──webhook──▶  POST /api/webhooks/leads/{provider}
Landing page / Web form       ──POST────▶  POST /api/webhooks/leads/web
                                              │
                                              ├─ verifikasi signature + verify_token
                                              ├─ normalisasi (phone E.164) + dedup
                                              ├─ create/merge lead (source, campaign, adset, creative)
                                              ├─ emit event: lead.captured  ──▶ Event Bus (F3)
                                              │      └─ Guided Work Engine (F4): auto-assign instan + Task "Hubungi ≤5 menit" + SLA
                                              │      └─ (opsional) auto first-touch: kirim WA template sapaan
                                              └─ (kelak) CAPI: kirim status hilir balik ke Meta
```
- **Multi-provider adapter**: satu kontrak internal, adapter per sumber (Meta Lead Ads, Google Lead Form Extensions, TikTok Instant Form, web form, CSV import lama).
- **Graduated funnel** (kualitas): cold 2–3 field / warm 4–5 / hot 5–7 (pilihan form ads memengaruhi kualitas & prioritas).
- **Keamanan**: verifikasi signature webhook; kredензial di `.env`; rate-limit; idempotency-key.

### A3. Yang dibangun
- Koleksi `lead_capture_events` (raw payload + status proses), `ad_sources`/atribusi di `leads`.
- Endpoint webhook per provider + halaman **Settings › Integrasi Ads** (hubungkan akun, map field form → field lead, uji lead).
- **Auto-assign + task instan** (mesin yang sama dengan Work Hub) → memenuhi 5-minute rule.

---

## BAGIAN B — WHATSAPP IN-CHAT INBOX (Conversational CRM di dalam SIPRO)

### B1. Prinsip (grounded WA Cloud API 2026)
- **Inbound webhook** (`messages` + `message_status`) → simpan ke inbox in-app; **outbound** via Graph API.
- **24-jam session window**: dalam 24 jam sejak pesan terakhir pelanggan → boleh kirim **session message gratis**; di luar → **wajib template pra-approved Meta** (berbayar). Sistem harus **menandai window** & memandu agen (badge "Sesi aktif 24j" / "Perlu template").
- **Template management**: kelola template disetujui Meta (sapaan, reminder appointment, info pembayaran, follow-up).
- **Percakapan terikat entitas**: tiap conversation tertaut ke `lead`/`customer`/`deal` → muncul di **timeline & Work Hub** (bukan chat lepas).

### B2. Gambaran produk (UX)
- **Inbox WhatsApp di dalam SIPRO** (seperti Slack/WA Web, tapi ERP):
  - Kiri: daftar percakapan (filter: milik saya / belum dibalas / SLA / stage lead).
  - Tengah: **thread chat** (bubble in/out, status terkirim/dibaca, lampiran/foto), **composer** (teks/template/lampiran) dengan **indikator window 24j**.
  - Kanan: **panel konteks record** (lead/deal/unit terkait, stage, Next-Best-Action, tombol "Majukan stage", "Buat appointment", "Buat SPR") + **catatan internal** (tak terkirim ke pelanggan, mendukung @mention rekan).
- **Assignment percakapan** → pemilik lead; **kolaborasi** via internal note + @mention (Work Hub).
- **Quick reply / snippet** & **template** satu klik; **auto-log** semua ke activity feed.

### B3. Yang dibangun
- Koleksi `conversations`, `messages` (arah in/out, type, status, template_id, media ref), `wa_templates`, `wa_sessions` (window 24j), `channel_accounts` (nomor WABA).
- Endpoint: `GET /api/inbox/conversations`, `GET /api/inbox/conversations/{id}`, `POST /api/inbox/conversations/{id}/send` (path literal), webhook `POST /api/webhooks/whatsapp` (+ `GET` verify), `GET/POST /api/wa-templates`.
- **Object storage** (F7) untuk media masuk/keluar.

---

## BAGIAN C — TRIGGER PERCAKAPAN → LEAD LIFECYCLE (jantung otomasi)

> Inilah yang owner maksud: **chat in-system yang men-trigger status lead lifecycle.** Mengubah `auto_followup_rules` SIPRO (yang mati/manual) menjadi **engine event nyata**.

| Sinyal | Aturan (configurable) | Efek pada lifecycle | Task/Followup |
|---|---|---|---|
| **Pesan WA masuk dari nomor tak dikenal** | match/create lead | Lead baru → `acquisition` | Task "Hubungi ≤5 mnt" + auto-assign |
| **Balasan pelanggan dalam window 24j** | aktivitas terdeteksi | `acquisition → nurturing` (kontak pertama) + hitung `response_time` (idempotent) | — |
| **Keyword intent** ("harga", "KPR", "survey", "booking") | rule keyword | usulkan naik ke `appointment`/`booking` (NBA) | Task tindak lanjut sesuai intent |
| **Tidak ada balasan X hari** | SLA no-response | usulkan `recycle` | Task re-engage + template re-engagement |
| **Appointment dikonfirmasi via chat** | rule | `nurturing → appointment` | Task siapkan survey |
| **Broadcast (stage acquisition saja)** | kampanye template + opt-out | tetap stage; catat outreach | batasi ke acquisition (hindari spam) |

- **Config-driven** (bukan hardcode): editor **Automation Rules** (trigger → kondisi → aksi), pola monday/HubSpot; disimpan di `automation_rules`.
- **Idempotent** via `source_event` (pola SIPRO yang benar) agar tak dobel task.
- **Human-in-the-loop**: perubahan stage sensitif = **usulan NBA** (agen konfirmasi), bukan otomatis penuh — cegah salah-klasifikasi (pelajaran benchmark: AI klasifikasi + saran, manusia putuskan).

---

## BAGIAN D — INTEGRASI KE WORK HUB & EVENT BUS (sinergi arsitektur)

- **Inbox WA = salah satu "channel"** di Work Hub (Dok 03 §3.4). Pesan masuk → **activity** + (bila perlu) **task**; @mention rekan untuk bantuan.
- **Event Bus (F3)** menyalurkan: `lead.captured`, `message.received`, `message.sent`, `conversation.assigned`, `keyword.matched` → **Guided Work Engine (F4)** menghasilkan task & Next-Best-Action.
- **Notifikasi (F10)**: pesan baru / SLA breach / @mention → inbox notifikasi + (kelak) push.
- **Atribusi** mengalir ke Finance (komisi per-sumber) & analitik (campaign ROI, CPL/CPQL, Dok 06 §3).

---

## BAGIAN E — MODEL DOMAIN TAMBAHAN (masuk ENTITY_REGISTRY)

| Koleksi | Fungsi | Terkait |
|---|---|---|
| `channel_accounts` | Nomor WABA / akun ads terhubung (per org) | multi-tenant scope |
| `conversations` | Percakapan (channel, lead/customer/deal ref, owner, status, window_expiry) | leads/customers/deals |
| `messages` | Pesan in/out (type, body, media, status, template_id, wa_message_id) | conversations |
| `wa_templates` | Template disetujui Meta (kategori, bahasa, variabel) | — |
| `automation_rules` | Trigger→kondisi→aksi (config-driven) | events, tasks |
| `lead_capture_events` | Raw payload webhook ads/web + status proses (audit/dedup) | leads |

> Semua ber-`org_id`, UUID, audit. Kredensial integrasi **tidak** di FE; simpan `.env`/settings ter-mask (pola aman).

---

## BAGIAN F — IMPLEMENTASI (fase, guardrail, integrasi)

### F1. Fase (masuk roadmap Dok 04 sebagai EPIC 1.7 "Omnichannel & Conversational Engine")
1. **Capture dulu** (dampak tertinggi, risiko sedang): webhook Meta Lead Ads + web form → lead + auto-assign + task 5-menit. *(Google/TikTok menyusul via adapter.)*
2. **WA Inbox** (inbound webhook + outbound send + inbox UI + window 24j + template).
3. **Automation rules engine** (trigger percakapan → lifecycle) menggantikan `simulate-followup`.
4. **CAPI feedback loop** (kirim status hilir ke Meta) + broadcast acquisition + analitik ROI.

### F2. Integrasi pihak-3 (WAJIB via jalur resmi)
- Ambil playbook via **integration_playbook_expert_v2** untuk: **WhatsApp Business Cloud API (Meta)** & **Meta Lead Ads Webhook + Conversions API**. Minta kredensial ke owner (WABA ID, phone number ID, access token, verify token, app secret; Meta App + Page + Lead Access). Simpan di `.env`. **Jangan** implementasi tanpa playbook.
- Fallback saat kredensial belum ada: **mode simulasi jujur** (ditandai jelas "SIMULASI") agar flow & UI tetap dapat diuji — **bukan** diklaim nyata (anti RC-10 false-green).

### F3. Guardrail khusus
- Endpoint webhook harus **verifikasi signature**; uji dengan payload sampel; idempotency.
- `verify_api_contract` + `ux_audit` (inbox punya loading/empty/error; composer punya state); `verify_rbac` (inbox hanya owner/manager); `verify_tenant_scope` (percakapan ber-org).

### F4. Outcome/KPI (ref Dok 06 §3)
- Median **speed-to-lead ≤5 menit**; % lead ads terkontak <30 dtk (auto first-touch).
- **CPL/CPQL** & **Cost-per-Closing** per campaign/creative (atribusi).
- **Response rate** & **first-response time** WA; konversi per sumber (stratifikasi).

---

## RINGKAS (sinergi)
Domain ini menyatukan **iklan → percakapan → lifecycle → task → finance** menjadi satu mesin konversi. Ia **memakai** Event Bus + Guided Work Engine + Work Hub + Activity layer (fondasi F3/F4/F5), **menjawab** pain SL-1/SL-2 (Dok 05), **melayani** persona Sales & Pembeli (Dok 06), dan **mewujudkan** "Slack tapi ERP" ke sisi eksternal. Tanpa domain ini, Work Hub hanya internal; dengan domain ini, SIPRO menutup celah terbesar SIPRO lama.
