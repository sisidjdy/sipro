# FIELD_MAP — nama field uang per bentuk dokumen (SSOT untuk manusia & gate)

Pola B audit: dua dokumen berbentuk mirip memakai nama field berbeda untuk konsep yang sama,
dan salah baca menghasilkan **nol yang diam** (bukan galat). Peta ini adalah kebenarannya;
`scripts/verify_field_names.py` menolak pola akses yang bertentangan dengannya.

| Dokumen / objek | Variabel lazim | Jumlah tagihan | Sudah dibayar | Sisa |
|---|---|---|---|---|
| `ar_invoices` (level INVOICE) | `inv` | `total` | `paid` | `outstanding` |
| `ar_invoices.items[]` (TERMIN) | `it`, `item` | `amount` | **`paid_amount`** | hitung: `amount - paid_amount` |
| `booking_fee_invoices` | `inv`, `bf` | `amount` | `paid` | `outstanding` |
| `receipts` | `doc`, `rc` | `amount` | — | — |
| `wa_reminders` | `r` | `amount` (= sisa yang diingatkan) | — | — |

Aturan:
1. Item termin **tidak punya** `paid`. Membaca `item.get("paid")` selalu `None` → 0.
2. Invoice **tidak punya** `paid_amount`.
3. Status item: `unpaid | partial | paid` (ikut `finance_engine.allocate_payment`).

Cacat yang lahir dari pelanggaran peta ini: WA-02 (`wa_reminder_engine`), DOC-01 (`ar_router`
invoice PDF). Keduanya ditutup 2026-09-06 dan dijaga gate `verify_field_names.py`.
