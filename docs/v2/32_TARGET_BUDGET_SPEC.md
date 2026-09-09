# 32 — SPEC TARGET PROYEK & BUDGET / REALISASI RAB

> Keputusan **D6**: basis target **unit DAN pendapatan**; sediakan **beberapa metode** rumus; item budget = **master yang bisa ditambah user**; overbudget **general lalu bisa didetailkan**; **harus link ke finance**.
> Menutup CR-16, CR-17. Basis yang sudah ada: `boq_items` + `/api/boq/summary` & `/control`, `purchase_orders`, `grns`, `ap_invoices`, `spk` + `progress_claims`, `material_txns`, `journal_entries`, `gl_reports.py`.

## 1. Alur kerja yang owner gambarkan
```
proyek dibuat → RAB konstruksi disusun (per unit/tipe/langkah)
            → budget operasional & lain-lain diisi user (master item bisa ditambah)
            → dari total biaya + harga jual + jumlah unit → TARGET (unit & pendapatan) dihitung
            → target bulanan DINAMIS mengikuti realisasi (re-baseline)
            → realisasi biaya masuk dari PO/AP/SPK/material/jurnal → REALISASI RAB
            → bandingkan: overbudget? margin? proyeksi selesai?
```

## 2. Target (`project_targets`)

```json
{
  "project_id": "...", "name": "Target 2026", "basis": "both",
  "method": "linear_remaining|s_curve|manual|velocity_forecast|revenue_first",
  "horizon": {"start": "2026-01", "end": "2027-12"},
  "unit_target": 120, "revenue_target": 19920000000,
  "recalc_policy": {"mode": "monthly", "keep_total": true, "lock_past": true},
  "periods": [{"period": "2026-08", "unit_plan": 6, "revenue_plan": 996000000,
               "unit_actual": 4, "revenue_actual": 664000000, "locked": false,
               "carry_over": 2, "note": ""}],
  "assumptions": {"avg_price": 166000000, "opex_monthly": 0, "start_selling": "2026-08"},
  "status": "draft|active|closed", "created_by": "", "history": []
}
```

### 2.1 Metode target (semua disediakan — user memilih)

| Metode | Rumus | Kapan dipakai |
|---|---|---|
| `linear_remaining` **(default)** | `target_bulan = ceil(sisa_unit / sisa_bulan)`; dihitung ulang setiap awal bulan (`recalc_policy.mode=monthly`) | proyek berjalan normal; kekurangan bulan lalu otomatis terserap |
| `s_curve` | bobot per bulan diisi user (Σ = 100%), `target_bulan = unit_target × weight_bulan` | ada musim (lebaran, akhir tahun, launching) |
| `manual` | user isi tiap bulan; sistem menghitung **deviasi** & memberi peringatan bila Σ ≠ total | manajemen ingin kendali penuh |
| `velocity_forecast` | `target = median(penjualan 3 bulan terakhir) × (1 + growth)`; menghasilkan **proyeksi tanggal selesai terjual** | untuk proyeksi realistis & peringatan dini |
| `revenue_first` | target pendapatan ditetapkan lalu diturunkan ke unit: `unit = ceil(revenue_target_bulan / avg_price)` | bila KPI perusahaan berbasis Rp |

**Dinamis (permintaan owner):** setiap awal bulan job `targets_recalc_tick` menulis periode baru dengan **jejak** (`history[]`: `{at, method, before, after, reason}`), periode lampau **dikunci** (`lock_past`) supaya laporan historis tidak berubah diam-diam. `carry_over` memperlihatkan kekurangan yang dipindah — sehingga "target naik" bisa dijelaskan, bukan misteri.

**Cakupan target**: `project`, opsional `cluster_id` dan/atau `owner_email` (target per sales) — total anak wajib ≤ total induk (divalidasi).

### 2.2 Endpoint
```
GET/POST /api/targets                      (filter project/status)
GET      /api/targets/{id}                 detail + periode + realisasi
PUT      /api/targets/{id}                 ubah (audit)
POST     /api/targets/{id}/recalc          hitung ulang manual (wajib alasan)
POST     /api/targets/{id}/activate|close
GET      /api/targets/{id}/progress        target vs realisasi per periode + proyeksi selesai
GET      /api/projects/{pid}/target-summary  ringkasan untuk kartu dashboard
```
Realisasi diambil dari `SLS-01` (unit) & `SLS-03/04` (nilai) — [31](31_ANALYTICS_BI_SPEC.md), **bukan** angka yang diinput ulang.

## 3. Master budget (`budget_items`) — bisa ditambah user (D6)

| Field | Isi |
|---|---|
| `project_id`, `cluster_id?`, `unit_id?` | cakupan biaya |
| `category` | SSOT baru `budget_category`: `lahan`, `konstruksi`, `prasarana`, `perizinan`, `operasional`, `marketing`, `komisi_fee`, `pembiayaan`, `pajak`, `overhead`, `lainnya` (**bisa ditambah admin**) |
| `code`, `name`, `description` | mis. `OPS-GAJI`, "Gaji tim proyek" |
| `planned_amount`, `currency` | rencana |
| `gl_account` | akun GL untuk mencocokkan realisasi (wajib bila ingin realisasi otomatis) |
| `match_rule` | `by_gl_account` \| `by_boq_item` \| `by_cost_ref` \| `manual` |
| `boq_item_ids[]` | bila kategori konstruksi mengacu RAB |
| `owner_role`, `period` | penanggung jawab & periode anggaran (bulanan/proyek) |
| `revision[]` | riwayat perubahan anggaran `{at, by, from, to, reason}` |
| `active`, `order`, `note` | |

**Hubungan RAB ↔ budget:** `boq_items` tetap sumber rincian teknis konstruksi. `budget_items` kategori `konstruksi` **meringkas** RAB (tidak menggandakan angka): `planned_amount = Σ boq_items terkait` (dihitung, read-only) agar tidak ada dua kebenaran.

## 4. Realisasi & OVERBUDGET (general → detail)

**Sumber realisasi (semua wajib punya `cost_ref`, W5):**

| Sumber | Koleksi | Saat diakui |
|---|---|---|
| Pembelian material | `purchase_orders` → `grns` → `ap_invoices` | komitmen (PO) & aktual (GRN/AP) |
| Pemakaian material | `material_txns` (opname) | saat dipakai |
| Borongan subkon | `spk` → `progress_claims` | klaim terverifikasi |
| Biaya operasional | `journal_entries` (via kas/bank/AP) | posting jurnal |
| Kas bon | `cash_advances` (Fase 27) | penyelesaian |
| Fee mitra & komisi | `marketing_fees`, `commissions` | approved |
| Pajak & pembiayaan | `tax_records`, `loans` | posting |

**Tiga lapis tampilan (permintaan owner):**
1. **General (proyek)**: `rencana_total`, `komitmen`, `realisasi`, `sisa`, `%`, status `aman | waspada (≥90%) | overbudget (>100%)`.
2. **Per kategori**: tabel kategori × (rencana, komitmen, realisasi, selisih, %).
3. **Detail item → dokumen sumber**: klik item → daftar PO/AP/klaim/jurnal penyusun angkanya (audit trail lengkap, tidak ada angka tanpa asal).

**Rumus:**
```
komitmen   = Σ PO open (belum GRN) + Σ SPK belum diklaim
realisasi  = Σ AP invoice + Σ klaim terverifikasi + Σ jurnal biaya langsung + Σ pemakaian material
exposure   = realisasi + komitmen           (dipakai untuk peringatan dini)
variance   = rencana − exposure             (negatif = akan overbudget)
margin     = pendapatan diakui − realisasi_total
margin_pro = (harga jual seluruh unit) − (RAB total + budget operasional total)
```
**Peringatan otomatis** (`[CFG] budget.alert_pct` default 90): saat `exposure/rencana ≥ 90%` → notifikasi + tugas ke `owner_role`; saat >100% → status overbudget + wajib **revisi anggaran beralasan** atau **change order**.

**Endpoint**
```
GET/POST /api/budget/items                     master (filter project/kategori)
PUT      /api/budget/items/{id}                ubah (revisi wajib alasan)
GET      /api/budget/summary?project_id=       lapis 1 (general)
GET      /api/budget/by-category?project_id=   lapis 2
GET      /api/budget/items/{id}/realization    lapis 3 (dokumen sumber)
GET      /api/budget/rab-vs-actual?project_id=&group_by=item|step|unit|type
GET      /api/budget/margin?project_id=
POST     /api/budget/items/{id}/revise         revisi anggaran (alasan + approval)
```

## 5. Link ke finance (tidak boleh terputus)
- Setiap dokumen biaya **wajib** memilih `budget_item_id` (atau `boq_item_id`) saat dibuat — validasi di PO, AP, SPK, kas bon, jurnal manual. `[CFG] budget.enforce_cost_ref` default **true** untuk dokumen baru (dokumen lama dibiarkan, ditandai `unmapped` dan muncul di laporan "biaya belum terpetakan" agar bisa dirapikan bertahap).
- Laporan keuangan yang sudah ada (`gl_reports.py`) tidak diubah rumusnya; BI hanya **membaca**.
- Target pendapatan dibandingkan dengan **pendapatan diakui** (`revenue_recognitions`) dan **kas masuk** (`receipts`) — keduanya ditampilkan agar tidak tertukar.

## 6. Definition of Done
1. User bisa membuat target dengan 5 metode; mengubah metode menampilkan pratinjau dampak sebelum disimpan.
2. Target bulanan berubah otomatis tiap bulan dengan jejak alasan; periode lampau tidak berubah.
3. Setiap angka realisasi bisa ditelusuri sampai dokumen sumber (uji klik-tembus 3 lapis).
4. Overbudget muncul di 3 lapis + peringatan 90% berfungsi (uji dengan data buatan).
5. Dokumen biaya baru tidak bisa dibuat tanpa `cost_ref` bila enforce nyala (uji negatif).
6. Invarian INV-10 lulus; gate baru `verify_budget_target.py`; `run_all_gates.sh` PASS.
