# 42 — SPEC PENGADAAN & SUBKON LANJUTAN (Fase 48)

> Dasar: audit API nyata `scripts/_audit48.py` (bukan dugaan) atas modul yang sudah ada sejak
> Fase 12/16/17/33. Cakupan diminta owner: (a) PO→GRN→3-way→AP, (b) kontrak subkon + termin +
> **retensi & potongan**, (c) permintaan material lapangan → PO, (d) evaluasi & daftar harga
> vendor, (e) stok/gudang per proyek.

---

## 1. Yang SUDAH ADA sebelum Fase 48 (jangan dibangun ulang)

| Modul | Kemampuan |
|---|---|
| `procurement_router.py` | PO (buat/setujui/batal, ambang nilai tinggi > Rp 500 jt milik Owner), GRN bertahap + sinkron stok, 3-way match (menandai), tagihan AP |
| `subcon_router.py`, `subcon_claims_router.py`, `opname.py` | Subkontraktor, SPK, lingkup item, termin berbasis opname (earned value dari item terverifikasi), change order, retensi **ditahan** di tagihan |
| `materials_router.py` | Stok per proyek + buku besar mutasi, opname stok, RAB per material, permintaan material (ajukan/setujui/keluarkan dari stok) |

## 2. Sembilan lubang yang ditutup Fase 48

| Kode | Lubang (bukti audit) | Penutup |
|---|---|---|
| G1 | Vendor hanya TEKS BEBAS (`/vendors` → 404) | Master `vendors` + `vendor_id` pada PO (nama disimpan sebagai **snapshot**) |
| G2 | Tidak ada daftar harga → harga PO tanpa pembanding | `vendor_prices` + `price-compare` + `price-check` (ambang 10%) |
| G3 | `rating` subkon hanya angka yang diketik | `vendor_engine.evaluate_vendor/evaluate_subcon` (berbukti) + `vendor_assessments` (penilaian manusia, terpisah) |
| G4 | Permintaan disetujui tidak punya jalan ke pembelian | `shortage()` + `POST /materials/requisitions/{id}/to-po` (idempoten) |
| G5 | GRN tidak bisa dibalik | `grn_returns` + `POST /procurement/returns` |
| G6 | Retensi menumpuk tanpa jalan pencairan | `subcon_retentions` + gerbang (`maintenance_until` & punch list) + pencairan berjurnal |
| G7 | Tidak ada uang muka & potongan/denda | `subcon_advances`, `subcon_deductions`, `attach_deductions()` |
| G8 | Stok tanpa transfer / batas minimum / nilai | `material_transfers`, `min_qty` + `stock-alerts`, `valuation` (rata-rata bergerak) |
| G9 | 3-way match hanya menandai | `evaluate_bill()` keadaan **`held`** → tagihan DITOLAK; terobosan khusus `finance_manager` + alasan ≥10 huruf |

## 3. Prinsip yang dijaga (dan diuji gate 34–36 + `mutasi_48.py`)

* **P-1 Satu kebenaran.** Rumus 3-way pindah ke `procurement_extra.evaluate_bill()`; router, gate, dan uji-mutasi memakai fungsi yang sama.
* **P-2 Klaim ≠ pelunasan.** Tagihan yang melebihi barang diterima TIDAK LAHIR; terobosan berjejak (`override_by`, `override_reason`) + tugas tinjauan otomatis.
* **P-3 Jujur soal data kosong.** Tidak ada acuan harga → `no_reference`; vendor tanpa transaksi → `missing_data` (skor `null`, **bukan 0**); material tanpa harga masuk → `missing_price`.
* **P-4 Pemisahan tugas.** Lapangan/PM mengajukan; finance membayar; **hanya `finance_manager`** memutuskan uang muka & mencairkan retensi; pengaju ≠ pencair.
* **P-5 Bisa dibalik & berjejak.** Retur, pembatalan potongan, terobosan 3-way — semuanya wajib beralasan (≥10 huruf) dan tercatat di `audit_logs` + aktivitas.
* **P-6 Idempoten.** PO dari permintaan yang sama tidak lahir dua kali; retensi satu tagihan satu baris (index unik `ap_bill_id`); harga vendor untuk kunci alami sama = koreksi + riwayat.

## 4. Uang & jurnal

| Peristiwa | Jurnal |
|---|---|
| Uang muka subkon dibayar | Dr **1-1800** Uang Muka Subkontraktor & Vendor / Cr 1-1200 Bank |
| Termin subkon disetujui | Dr biaya/WIP (bruto) / Cr 2-1100 (net) + Cr 2-1200 (retensi) + Cr **1-1800** (angsuran uang muka) + Cr 4-1200 (denda) + Cr 1-1400 (bon material) |
| Retensi dicairkan | Dr 2-1200 Utang Retensi / Cr 2-1100 Utang Usaha → dibayar lewat jalur AP biasa (Dr 2-1100 / Cr 1-1200) |
| Penerimaan barang (GRN) | mutasi stok `in` **berharga** (dasar nilai persediaan rata-rata bergerak) |
| Retur barang | mutasi stok `out` + `received_value` PO turun (tidak boleh di bawah nilai tertagih) |

`net = bruto − retensi − Σ potongan`, dan **Σ debit = Σ kredit = bruto** — dibuktikan gate 35 (R5b).

## 5. Kontrak API baru

```
GET/POST  /api/vendors                     GET/PUT /api/vendors/{id}
GET/POST  /api/vendors/price-list          GET /api/vendors/price-compare | price-check
GET       /api/vendors/evaluations         GET /api/vendors/{id}/evaluation
POST      /api/vendors/{id}/assessment
GET/POST  /api/procurement/returns
GET       /api/materials/requisitions/{id}/shortage
POST      /api/materials/requisitions/{id}/to-po
POST      /api/procurement/bills           (+ override_hold, override_reason)
GET/POST  /api/subcon/advances             POST /api/subcon/advances/{id}/decision | pay
GET/POST  /api/subcon/deductions           POST /api/subcon/deductions/{id}/cancel
GET       /api/subcon/retentions           POST /api/subcon/retentions/{id}/request-release | release
GET       /api/subcon/evaluations          GET/POST /api/subcon/subcontractors/{id}/evaluation | assessment
GET/POST  /api/materials/transfers         GET /api/materials/stock-alerts | valuation
PUT       /api/materials/{id}/min-stock
```

## 6. Layar (tanpa pintu sidebar baru)

| Halaman | Tab baru |
|---|---|
| `/procurement` | **Retur Barang**, **Vendor**, **Daftar Harga**, **Evaluasi Vendor** (tab lama: PO, 3-Way Match) |
| `/subcon` | **Uang Muka & Potongan**, **Retensi**, **Evaluasi** (tab lama: Subkontraktor, SPK, Progress & Termin) |
| `/materials` | **Kendali Stok** (peringatan minimum, transfer antar proyek, nilai persediaan) + tombol **Buat PO** pada permintaan material |

## 7. RBAC

| Resource | Peran |
|---|---|
| `vendors` | PM & finance: lihat/buat/ubah · site: lihat · `finance_manager`: + `manage` (menonaktifkan vendor) |
| `subcon_finance` | site: lihat/ajukan · PM: + ubah · finance: + `approve` (membayar) · **`finance_manager`: `manage`** (memutuskan uang muka, mencairkan retensi) |
| `procurement` | tak berubah; terobosan 3-way khusus `finance_manager`/owner |
| `materials` | transfer antar proyek butuh `approve` (PM/owner) — mandor tidak memindahkan barang antar proyek sendirian |

## 8. Guardrail

* Gate **34** `verify_procurement_vendor.py` (15 pemeriksaan) — vendor, harga, permintaan→PO, retur, 3-way menahan, evaluasi.
* Gate **35** `verify_subcon_retention.py` (14) — uang muka, potongan, jurnal seimbang, gerbang retensi, SoD.
* Gate **36** `verify_stock_control.py` (8) — transfer, peringatan, valuasi jujur.
* `poc/poc_48.py` (61 pemeriksaan) + `scripts/mutasi_48.py` (24 mutasi) + `scripts/_fixture48.py` (bahan uji sendiri, dibuang bersih).
