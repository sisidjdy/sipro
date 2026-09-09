# SIPRO Rebuild — Dokumen 16
# API CONTRACT (konvensi + katalog endpoint) — dasar verify_api_contract

> Status: SPESIFIKASI ANTARMUKA. Bahasa: Indonesia.
> Semua endpoint diawali **`/api`** (Kubernetes ingress). Diperiksa `verify_api_contract.py` (dup route, FE→route ada, FE field ⊆ BE response).

---

## 1. KONVENSI GLOBAL
- **Auth:** Bearer token (header) **atau** cookie httpOnly (`access_token`). Endpoint sensitif: `Depends(require_permission(...))`.
- **Envelope sukses:** list → `{ "data": [...], "total": <int?> }`; single → `{ "data": {...} }`; aksi → `{ "data": {...} }` atau `{ "message": "..." }`.
- **Error:** `{ "detail": "<pesan Bahasa Indonesia>" }` + kode: `400` validasi/guard, `401` auth, `403` RBAC, `404` not found, `409` konflik (mis. double-booking), `422` pydantic, `500` server.
- **Paginasi:** query `skip` (default 0) + `limit` (default 50, max 200). Response sertakan `total`.
- **Filter:** query param eksplisit (mis. `?stage=nurturing&assigned_to=...&project_id=...`).
- **Tanggal:** ISO-8601 UTC string. **Uang:** integer IDR. **Phone:** E.164.
- **Route literal > dinamis:** taruh path literal sebelum `/{id}` (hindari tabrakan; pelajaran verify_api_contract). Contoh: `/deals/summary` sebelum `/deals/{id}`.
- **Idempotency:** webhook & aksi kritis terima `Idempotency-Key` / dedup internal.

## 2. KATALOG ENDPOINT (ringkas per modul; detail request/response dikunci saat build tiap EPIC)
### Auth & Admin
`POST /api/auth/login` · `POST /api/auth/refresh` · `POST /api/auth/logout` · `GET /api/auth/me` · `GET/PUT /api/admin/permissions` · `GET/POST/PUT /api/admin/users`.
### Work Hub
`GET /api/work/tasks` (filter mine/overdue/type/status) · `POST /api/work/tasks` · `PUT /api/work/tasks/{id}` · `POST /api/work/tasks/{id}/complete|snooze` · `GET /api/work/home` (Role-Home KPI+NBA) · `GET /api/activities?entity_type&entity_id` · `POST /api/activities` · `POST /api/activities/{id}/comment` · `GET /api/notifications` · `POST /api/notifications/{id}/read`.
### Sales/CRM
`GET/POST /api/leads` · `GET/PUT /api/leads/{id}` · `POST /api/leads/assign` · `POST /api/leads/{id}/accept` · `POST /api/leads/{id}/transition` · `GET /api/leads/stats` · `GET/POST /api/appointments` · `GET/POST/PUT /api/customers` · `GET/POST /api/deals` · `GET /api/deals/summary` · `POST /api/deals/{id}/reserve|book` · `POST /api/deals/expire-sweep` (juga scheduler) · `GET/POST /api/reservations` · `GET/POST /api/financing` · `GET/POST /api/commissions` · `POST /api/commissions/{id}/approve|pay` · `GET/POST/PUT /api/commission-rules`.
### Omnichannel (Dok 07)
`GET /api/inbox/conversations` · `GET /api/inbox/conversations/{id}` · `POST /api/inbox/conversations/{id}/send` · `POST /api/inbox/conversations/{id}/assign` · `GET/POST /api/wa-templates` · `GET/POST/PUT /api/automation-rules` · `POST /api/webhooks/whatsapp` (+`GET` verify) · `POST /api/webhooks/leads/{provider}` · `GET/POST /api/channel-accounts`.
### Project/Construction
`GET/POST/PUT /api/projects` · `POST /api/projects/{id}/generate-units` · `GET /api/units` · `GET /api/units/{id}` · `GET/POST /api/boq` · `GET/POST /api/subcontractors` · `GET/POST /api/work-packages` · `GET/POST /api/construction/units` · `PUT /api/construction/units/{unit_id}/progress` · `POST /api/construction/units/{unit_id}/qc` · `GET /api/construction/summary` · `GET/POST /api/progress-claims` · `POST /api/progress-claims/{id}/verify|pay` · `GET/POST /api/materials` · `POST /api/materials/txn` · `GET/POST /api/stock-opname` · `GET/POST /api/change-orders` · `GET/POST /api/permits`.
### Finance
`GET/POST /api/finance/ar` · `POST /api/finance/receipts` · `GET /api/finance/ar-aging` · `GET/POST /api/finance/ap` · `POST /api/finance/payments-out` · `GET/POST /api/finance/retentions` · `POST /api/finance/revenue-recognize` (atau via event BAST) · `GET/POST /api/finance/tax` · `GET /api/finance/cashflow` · `GET /api/finance/summary`.
### Dokumen (CLONE F1)
`GET/POST/PUT/DELETE /api/document-templates[...]` · `GET/POST /api/documents` · `GET/PUT/DELETE /api/documents/{id}` · `POST /api/documents/{id}/finalize|sign` · `GET /api/documents/{id}/pdf` · `GET /api/deals/{id}/documents`.
### Files
`POST /api/attachments` (upload) · `GET /api/attachments?entity_type&entity_id`.
### Customer Portal (M1)
`GET /api/portal/me` · `GET /api/portal/progress` · `GET /api/portal/payments` · `GET /api/portal/documents` · `POST /api/portal/complaints`.

## 3. ATURAN GATE
- Setiap endpoint yang dipanggil FE **harus ada** di BE (verify_api_contract cek B).
- Field yang dirender FE **harus ada** di response BE (cek C) → cegah label kosong senyap.
- Tak boleh duplicate route (cek A).
> ⚑ Menambah endpoint ⇒ update dok ini + CODEBASE_MAP; jalankan verify_api_contract.
