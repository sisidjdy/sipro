# SIPRO Rebuild — Dokumen 15
# FINANCE MODEL & PAJAK (PSAK 72) — agar tidak "false-green"

> Status: SPESIFIKASI AKUNTANSI (menutup Dok 09 gap #8). Bahasa: Indonesia.
> Prinsip: **pendapatan diakui saat Serah Terima (BAST) — point-in-time** (PSAK 72). DP/termin sebelum BAST = **kewajiban kontrak**. Angka pajak = **acuan konfigurasi** (default umum); **wajib dikonfirmasi penasihat pajak saat go-live**.
> Ruang lingkung: worksheet-level yang **benar** (AR/AP/retensi/contract-liability/RevRec + pajak). **GL double-entry penuh & e-Faktur = fase lanjut** (dinyatakan jujur, bukan diklaim ada).

---

## 1. ALUR UANG & AKUN (konsep)
```
Pembeli bayar DP/cicilan/KPR ──▶ receipts ──▶ AR item paid ──▶ contract_liabilities.balance ↑ (BELUM pendapatan)
Biaya subcon (termin) ────────▶ ap_bills (net) + retentions(held) ──▶ payments_out
Konstruksi berjalan ──────────▶ (biaya = aset dalam penyelesaian, konsep)
╔ SERAH TERIMA (unit.bast) ║ ──▶ revenue_recognitions: revenue ↑, COGS ↑ ; contract_liabilities.balance ──▶ 0
Masa pemeliharaan selesai ────▶ retentions.released ──▶ payments_out (retensi)
```

## 2. AR (PIUTANG PEMBELI) — PORT billing→AR
- `ar_schedules.items[]` = jadwal (DP, cicilan/termin, pelunasan/KPR). Tiap item: amount(int IDR), due_date, status, paid_amount.
- `receipts` apply ke item → recalc `paid`/`outstanding` (⚑ outstanding=total−paid) → update `units.payment_status` → **naikkan `contract_liabilities.balance`** → emit `payment.*` (paid_off → handler cek komisi/aktivasi deal).
- **Aging buckets**: current / 1–30 / 31–60 / 61–90 / >90. **DSO** = (AR outstanding / penjualan) × hari.

## 3. AP (UTANG SUBCON) + RETENSI
- Dari `progress_claims` verified: `ap_bills.net = claimed − retention_held`; `retentions.held`.
- `payments_out` (approved_by ⚑) mengurangi AP. Retensi dilepas saat `release_due_at` (scheduler) → payments_out retensi.
- **AP aging** serupa AR.

## 4. CONTRACT LIABILITY & REVENUE RECOGNITION (inti PSAK 72)
- `contract_liabilities.balance` (per deal) **naik** tiap receipt; **BUKAN** pendapatan.
- Saat `unit.bast` (BAST signed): buat `revenue_recognitions{revenue, cogs, recognized_at}`; **nolkan** contract_liability terkait. ⚑ revenue **hanya** muncul di titik ini.
- Dashboard: **Contract-liability vs Revenue diakui** (transparansi ke owner).

## 5. PAJAK (konfigurabel; default acuan)
| pajak | pihak | dasar (base) | rate default | jatuh tempo |
|---|---|---|---|---|
| **PPN** (primary, developer PKP) | dikenakan ke pembeli, disetor developer | harga jual (DPP) | **12%** (konfigurabel; sebagian transaksi 11%) | sesuai faktur/termin |
| **BPHTB** | pembeli | (NPOP − NPOPTKP) | **5%** | sebelum/saat AJB |
| **PPh final pengalihan hak** | penjual/developer | harga jual | **2,5%** (umum) / **1%** (RS/subsidi) | sebelum AJB |
- `tax_records{type, base, rate, amount, due_date, status, doc_ref}`; reminder via scheduler. **Rumus disimpan konfigurabel** agar mudah dikoreksi tanpa ubah kode.
- **e-Faktur / pelaporan pajak resmi = fase lanjut** (worksheet dulu).

## 6. CASH-FLOW PROJECTION
- Proyeksi = Σ(AR item due per minggu/bulan) − Σ(AP+termin+retensi due) → **runway**. Sumber: due_date di ar_schedules & ap_bills/retentions.
- Alarm bila proyeksi kas negatif (grounded pain FN-3: subcon tak terbayar → mangkrak).

## 7. ANTI-FRAUD (grounded FN-6)
- **3-way match**: PO/requisition → GRN → ap_bill (material) sebelum bayar.
- **Approval berjenjang** (payments_out.approved_by; RBAC finance).
- **Jejak audit** semua mutasi finance (`audit_logs`).
- **Segregation of duties** via RBAC (yang input ≠ yang approve).

## 8. KPI FINANCE (ke Finance Home)
AR aging & DSO · % overdue · cash-flow runway · contract-liability vs revenue · AP aging & retensi jatuh tempo.

## 9. INVARIAN (gate)
⚑ receipt ⇒ contract_liability naik · revenue hanya saat BAST · AP.net = claimed−retention · outstanding=total−paid · pembayaran termin butuh qc_gate_passed.

> ⚑ **Kejujuran:** bila GL/e-Faktur belum ada, dashboard & summary **menyatakan** "worksheet-level (belum GL penuh)". Dilarang mengklaim pembukuan penuh yang belum ada (RC-10).
