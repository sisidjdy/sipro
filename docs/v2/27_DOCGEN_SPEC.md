# 27 — SPEC GENERATOR DOKUMEN (SPR & SPKT dari template asli owner)

> Keputusan **D8**: dokumen bisa di-generate sistem. Sumber template: `docs/source_templates/` (4 file .docx asli owner, disimpan permanen sebagai acuan legal).
> Basis kode yang sudah ada: `backend/pdf_utils.py` (reportlab), `document_templates` (SSOT `document_template`), `routers/documents_router.py` (create → finalize → sign → pdf), `sequences.py` (penomoran).

## 1. Daftar template yang WAJIB ada

| Kode | Nama | Dipakai saat | Skema | File asli |
|---|---|---|---|---|
| `SPR_CASH` | Surat Pesanan Rumah — Cash Keras | terbitkan SPR | `cash_keras` | `SPR_CASH_HARMONY_LAND_5.docx` |
| `SPR_CASH_STAGED` | Surat Pesanan Rumah — Cash Bertahap | terbitkan SPR | `cash_bertahap` | `SPR_CASH_BERTAHAP_HARMONY_LAND_5.docx` |
| `SPR_KPR` | Surat Pesanan Rumah — KPR | terbitkan SPR | `kpr` | `SPR_KPR_HARMONY_LAND_5.docx` |
| `SPKT` | Surat Pernyataan Kelebihan Tanah | ada add-on `kelebihan_tanah` | semua | `SPKT_HARMONY_LAND_5.docx` |
| `PPJB`, `AJB`, `BAST`, `KWITANSI`, `SURAT_PEMBATALAN`, `SURAT_REFUND` | dokumen lanjutan | tahap legal / pembatalan | semua | dibuat mengikuti gaya yang sama (⚠️ minta contoh owner bila ada) |

## 2. Penomoran dokumen
Format dari contoh `[DOC]`: `5201/SPR-CASH/HL5/VIII/2026` — `{seq}/{doc_code}/{project_code}/{roman_month}/{year}`.
Implementasi: `sequences.next_number(kind=f"{doc_code}:{project_code}", ...)` dengan `[CFG] docnum.reset_policy` = `never|yearly|monthly` dan `[CFG] docnum.scope` = `global|per_project|per_project_month` (⚠️ **OQ-5** — default sementara: `per_project`, reset `yearly`, lebar 4).
Nomor **dipesan saat dokumen difinalisasi** (bukan saat draft) agar tidak ada lubang nomor; nomor batal dicatat di `counters` dengan alasan.

## 3. Field map — SPR (ketiga varian)

| Placeholder | Sumber data | Catatan |
|---|---|---|
| `spr_number` | `deals.spr_number` (§2) | |
| `scheme_label` | `payment_scheme` → label | "tunai (cash keras)" / "tunai (cash bertahap)" / "fasilitas KPR" |
| `customer_name` | `leads.name` / `customers.name` | |
| `customer_phone` | `leads.phone` | |
| `property_name` | `projects.name` | "Harmony Land 5" |
| `property_address` | `projects.address` (**field baru**) | `[DOC]` "Jl. Pamagersari, Desa Gunungmanik, Kec. Tanjungsari, Kab. Sumedang" |
| `developer_name` | `projects.developer_name` (**baru**) | `[DOC]` "PT. Harmony Cahaya Land" |
| `unit_block` | `blocks.code` + `units.no` | `[DOC]` "A-11" — sekarang belum ada entitas blok (CR-05) |
| `unit_type_label` | `unit_types.name` | "tipe 30/60" |
| `building_area`, `land_area` | `units.building_area`, `units.land_area` | `[DOC]` 30m² / 60m² |
| `selling_price` | komponen `unit_price` | `[DOC]` Rp166.000.000 |
| `dp_percent`, `dp_amount` | termin DP di `payment_plans` | `[DOC]` KPR contoh 0% |
| `plafon_kredit` | `kpr_applications.requested_plafon` | hanya `SPR_KPR` |
| `booking_fee` | komponen `booking_fee` | `[DOC]` Rp1.000.000 |
| `bphtb`, `notary_fee`, `bank_fee`, `pph`, `insurance` | komponen biaya | `bank_fee`/`insurance` hanya KPR |
| `hook_fee` | add-on `posisi_unit` | `[DOC]` Rp3.000.000 |
| `addon_rows[]` | add-on lain (spek bangunan dll) | **baris dinamis** (permintaan owner) |
| `promo_discount` | komponen `promo_discount` | `[DOC]` "Potongan all in Rp2.000.000" |
| `subtotal`, `total` | `[CALC]` §3.2 Dok 26 | wajib cocok dengan kontrak |
| `installment_count`, `installment_amount`, `installment_amount_words` | termin cicilan | hanya `SPR_CASH_STAGED` (`[DOC]` 6×) |
| `due_day`, `grace_day` | `[CFG]` | `[DOC]` 7 dan 20 |
| `payoff_days`, `payoff_grace_days` | `[CFG]` | `[DOC]` 30 + 7 (cash keras) |
| `city`, `document_date` | `projects.city` / tanggal terbit | `[DOC]` "Bandung"/"Sumedang" |
| `marketing_name` | user penerbit | tanda tangan kiri |
| `signature_customer`, `signature_marketing` | e-sign / scan | §6 |

**Klausa yang dirender dari `[CFG]` (bukan teks mati)** — supaya perubahan kebijakan tidak perlu ubah kode:
`booking_fee_refund_bi_fail=100%`, `booking_fee_refund_kpr_rejected=50%`, `booking_fee_forfeit_no_clarity_days=7`, `cut_before_build=35%`, `cut_during_build=50%`, `arrears_months_to_cancel=2`, `shgb_months=6`, `notary_scope_text`, `bank_fee_scope_text`, `allin_scope_text`.

## 4. Field map — SPKT (kelebihan tanah)

| Placeholder | Sumber | Catatan |
|---|---|---|
| `spkt_number` | `sequences` (`SPKT`) | |
| `spr_number_ref` | `deals.spr_number` | SPKT selalu merujuk SPR |
| `customer_name`, `customer_phone`, `property_name`, `property_address`, `unit_block` | sama dengan SPR | |
| `standard_land_area` | `unit_types.land_area_std` | `[DOC]` |
| `excess_land_m2_estimated` | add-on `kelebihan_tanah.qty` | ditandai **estimasi** |
| `excess_price_per_m2_list` | master add-on | `[DOC]` **Rp2.000.000/m²** |
| `excess_price_per_m2_agreed` | `agreed_price` pada add-on | `[DOC]` **Rp1.250.000/m²** |
| `excess_total_estimated` | `[CALC]` qty × agreed | |
| `bphtb_excess` | komponen | `[DOC]` |
| `total` | `[CALC]` | |
| `final_measurement_clause` | `[CFG]` | "mengikuti hasil pengukuran akhir" |
| `payoff_before_akad_clause` | `[CFG]` | `[DOC]` wajib lunas sebelum akad kredit |

> ⚠️ **OQ-1 masih terbuka**: dokumen asli memuat **dua** harga/m² (Rp2.000.000 di tabel, Rp1.250.000 di klausa). Sistem menyediakan **dua field** (list & agreed) dan menampilkan peringatan bila `agreed < list` tanpa persetujuan `sales_manager`. Jangan hard-code salah satu.

## 5. Aturan generate (anti-dokumen bohong)
1. **Satu sumber angka**: dokumen hanya boleh merender angka dari `contracts.price_breakdown[]` / `payment_plans.terms[]`. Dilarang menghitung ulang di layer template.
2. **Draft → final**: `POST /api/documents` (draft, boleh regenerate) → `POST /api/documents/{id}/finalize` (nomor dipesan, isi dibekukan, hash SHA-256 disimpan) → `POST /api/documents/{id}/sign`.
3. **Perubahan setelah final** hanya lewat **dokumen baru** (adendum/change order) dengan referensi ke nomor lama; dokumen lama tidak pernah diedit (jejak audit).
4. **Validasi pra-generate** (gagal ⇒ 400 dengan daftar alasan): dokumen syarat mandatory belum verified; komponen wajib kosong; total tidak seimbang; add-on `kelebihan_tanah` tanpa SPKT; skema KPR tanpa `requested_plafon`.
5. **Watermark "DRAFT"** untuk dokumen belum final; hilang setelah finalize (pola `photo_utils.py` watermark sudah ada).
6. **Arsip**: PDF final diunggah ke storage (`storage.py`) dan ditautkan ke `lead`, `customer`, `contract`, dan `unit` sekaligus (W7) — sehingga muncul di semua profil.

## 6. Tanda tangan
- **Default**: cetak → tanda tangan basah → **unggah scan** (`doc_submissions` dengan requirement `spr_signed_scan`) → status dokumen `signed`.
- **Opsional e-sign**: `ESIGN_BASE_URL` + `ESIGN_API_KEY` sudah dibaca kode (`grep os.environ` → ada). Bila kosong → UI menyembunyikan tombol e-sign dan menampilkan alur unggah scan (jujur, bukan tombol mati).
- Setiap tanda tangan menyimpan `{signer_role, name, at, ip, method(wet_scan|esign), file_id}` (SSOT `signer_role` sudah ada).

## 7. Teknis rendering
- **Pilihan 1 (dipakai)**: render HTML terstruktur → PDF via reportlab platypus (`pdf_utils.py` sudah ada) dengan komponen: header developer, tabel biaya, blok klausa, blok tanda tangan.
- **Pilihan 2 (opsional nanti)**: isi `.docx` asli sebagai template (`docxtpl`) bila owner ingin tata letak identik 100%. Butuh dependensi baru — **jangan** dipasang sebelum owner minta.
- Template disimpan sebagai **data** di `document_templates` (`sections[]`, `variables[]`, `clauses[]`, `version`) sehingga admin bisa mengubah kalimat tanpa deploy; setiap perubahan menaikkan `version` dan dokumen menyimpan `template_version` yang dipakai.

## 8. Definition of Done
1. Tiga varian SPR + SPKT ter-generate dengan angka **identik** dengan kontrak (uji: ubah add-on → angka dokumen berubah).
2. Nomor dokumen tidak pernah dobel & tidak bolong (uji paralel 20 permintaan).
3. Dokumen final tidak bisa diubah; adendum wajib dokumen baru (uji negatif).
4. Klausa (7 hari, 35%, 50%, 2 bulan, 6 bulan) dibaca dari `[CFG]` — diuji dengan mengubah setting lalu regenerate.
5. PDF muncul di Profil Lead, Profil Customer, dan Unit 360.
6. Gate baru `verify_docgen.py` + `run_all_gates.sh` PASS.
