# SIPRO Rebuild — Dokumen 14
# RBAC MATRIX (role × resource × action) — ditegakkan sejak Fase 0

> Status: SPESIFIKASI KEAMANAN (menutup kegagalan #1 SIPRO lama & Dok 09 gap #6). Bahasa: Indonesia.
> Ditegakkan via dependency `require_permission(resource, action)` + row-scope; diperiksa `verify_rbac.py` (setiap endpoint sensitif punya guard; peta izin FE≡BE).

---

## 1. PERAN (reconcile SIPRO + kebutuhan Dok 03/06)
| role | deskripsi | scope data |
|---|---|---|
| `super_admin` | teknis/platform | semua org |
| `owner` | pemilik/direksi (Control Tower) | semua dalam org |
| `sales_manager` | manajer penjualan | semua lead/deal dalam org |
| `marketing_admin` | admin marketing (distribusi lead, template dokumen) | lead/deal + templates |
| `sales` | sales/marketing inhouse | **hanya milik sendiri** (assigned_to) |
| `finance` | finance/collection | semua finance (AR/AP/retensi/pajak) |
| `project_manager` | manajer proyek | proyek yang ditugaskan |
| `site_engineer` | pelaksana lapangan/QC | proyek/unit yang ditugaskan |

> Catatan: SIPRO lama punya `super_admin, marketing_admin, marketing_inhouse, sales, management`. Mapping: `marketing_inhouse→sales`, `management→owner`, tambah `sales_manager/finance/project_manager/site_engineer`.

## 2. AKSI
`view_all` · `view_own` · `create` · `update` · `delete` · `approve` · `assign` · `sign`.

## 3. MATRIKS (ringkas; SSOT = `permission_settings`, dapat di-override admin)
| resource \ role | super_admin | owner | sales_manager | marketing_admin | sales | finance | project_manager | site_engineer |
|---|---|---|---|---|---|---|---|---|
| leads | all | all | all+assign | all+assign | **own** | view | – | – |
| deals | all | all | all | all | own | view | – | – |
| reservations/ppjb | all | all | all | create/update | create(own) | view | – | – |
| financing(KPR) | all | all | view | view | create(own) | update | – | – |
| commissions | all | all | view | view | view(own) | approve/pay | – | – |
| documents/templates | all | all | use | **manage templates** | use(own) | view | – | – |
| projects/units | all | all | view | view | view(avail) | view | **manage(assigned)** | view(assigned) |
| construction/QC | all | all | view | – | – | view | manage(assigned) | **update(assigned)** |
| boq/material/opname | all | all | – | – | – | view | manage | **input(assigned)** |
| progress_claim/termin | all | all | – | – | – | **approve/pay** | submit/verify | submit |
| finance AR/AP/retensi | all | all | view | – | – | **manage** | view | – |
| revenue_recognition | all | all | – | – | – | **manage** | – | – |
| tax_records | all | all | – | – | – | manage | – | – |
| omnichannel inbox | all | all | all | all | **own conv** | – | – | – |
| automation_rules | all | all | manage | manage | – | – | – | – |
| users/permissions | **manage** | manage | – | – | – | – | – | – |
| audit_logs | view | view | – | – | – | view(finance) | – | – |

("–" = tanpa akses default; "own" = row-scope milik sendiri; "assigned" = row-scope penugasan.)

## 4. ROW-LEVEL SCOPING (PORT SCOPED_ROLES, diperluas)
- `sales`: lead/deal/task/appointment/conversation di-filter `assigned_to = user.email` (⚑ tak bisa lihat milik orang lain).
- `project_manager`/`site_engineer`: project/unit/construction di-filter berdasarkan penugasan (`project_members`).
- Non-scoped role (owner/manager/finance/admin): lihat semua dalam **org** (⚑ tetap ter-scope org_id).

## 5. ENFORCEMENT & GATE
- Setiap endpoint sensitif memakai `Depends(require_permission(resource, action))` + terapkan scope query.
- **FE**: `navigationConfig` & tombol dibungkus cek izin (peta izin sama dgn BE).
- `verify_rbac.py`: (a) tiap endpoint mutasi punya guard; (b) daftar izin FE == BE; (c) role scope diuji (sales tak bisa GET lead milik lain → 403).
- **Login-bypass test** untuk testing_agent hanya di non-prod (ditandai; dihapus sebelum deploy) + `test_credentials.md`.

> ⚑ Aturan: menambah resource/endpoint ⇒ **wajib** tambah baris matriks + entry `permission_settings` + uji `verify_rbac` (governance Dok 04 §7).
