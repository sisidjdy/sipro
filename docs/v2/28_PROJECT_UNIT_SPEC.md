# 28 — SPEC PROYEK → CLUSTER → BLOK → UNIT (master data & siteplan wiring)

> Menutup CR-05, CR-06, CR-33. Permintaan owner: *"proyek menyimpan beberapa cluster, cluster menyimpan beberapa blok, blok menyimpan beberapa unit, unit punya atribut tipe"* + *"wiring interaktif siteplan dengan unit harus jelas"* + *"jika unit terjual maka terikat dengan data customer"*.

## 1. Hierarki & kepemilikan data

```
project (1) ──► cluster (n) ──► block (n) ──► unit (n) ──► unit_type (ref)
   │                │              │            ├─► addon_items (n:m lewat kontrak/deal)
   │                │              │            ├─► customer/contract (bila terjual)
   │                │              │            └─► build_schedule (bila dibangun)
   │                │              └─► site_plan shapes (peta) ← wiring per unit
   │                └─► harga & target per cluster
   └─► izin proyek, RAB, target, budget
```

Boleh **cluster tunggal** (proyek kecil): sistem membuat cluster default `UTAMA` supaya struktur tetap konsisten (tidak ada jalur data khusus).

## 2. Skema koleksi

### `clusters`
`id, org_id, project_id, code, name, order, description, land_area, unit_target, price_policy{base_multiplier, premium_rules[]}, status(planning|selling|sold_out|closed), stats{units, available, held, booked, sold}, created_*`

### `blocks`
`id, org_id, project_id, cluster_id, code, name, order, unit_count, orientation, notes, stats{}`

### `unit_types`
`id, org_id, code, name, building_area, land_area_std, bedrooms, bathrooms, floors, base_price, spec{struktur, dinding, lantai, atap, plafon, kusen, sanitair, listrik, air}, image_file_ids[], brochure_file_id, active`
> Catatan: SSOT lama `unit_type` (enum teks "Tipe 45/90") tetap ada untuk kompatibilitas; migrasi memetakan enum → `unit_types.code` ([35](35_MIGRASI_DATA.md)).

### `units` (perluasan)
`project_id, cluster_id, block_id, unit_type_id, code, no, land_area, building_area, is_hook, corner_position, excess_land_m2, price_components{base, cluster_premium, block_premium, view_premium, hook, addons_total}, price, sales_status, build_status, customer_id, contract_id, deal_id, held_until, handover_at, status_history[], siteplan{shape_id, centroid}, blocked{reason, by, at}`

**Dua status paralel (W3, permintaan owner):**

| `sales_status` | Arti | Dipicu oleh |
|---|---|---|
| `available` | siap dijual | default / dilepas |
| `held` | dipegang reservasi (SPR belum sah) | `deals.reserve` |
| `booked` | sudah jadi customer & kontrak aktif | konversi lead→customer |
| `sold` | pelunasan/akad selesai | legal `pelunasan`/`akad` |
| `handed_over` | BAST | legal `bast` |
| `cancelled` | dibatalkan (kembali dijual = `available`) | pembatalan |
| `blocked` | tidak dijual (contoh: rumah contoh, sengketa) | admin, wajib alasan |

| `build_status` | Arti |
|---|---|
| `not_started` · `scheduled` · `in_progress` · `completed` · `handed_over` · `on_hold` |

Aturan: kedua status **tidak boleh saling menimpa**; tampilan tabel unit memiliki **dua kolom status** (permintaan owner).

## 3. Endpoint master (`routers/masterplan_router.py`)
```
GET/POST      /api/projects/{pid}/clusters          list/buat cluster
PUT/DELETE    /api/clusters/{id}                    ubah/hapus (tolak bila ada unit terjual)
GET/POST      /api/clusters/{id}/blocks             list/buat blok
PUT/DELETE    /api/blocks/{id}
GET/POST      /api/unit-types                       master tipe
GET/POST      /api/blocks/{id}/units                list/buat unit satuan
POST          /api/blocks/{id}/units/generate       generator massal {type, count, start_no, price_rule, hook_positions[]}
PATCH         /api/units/{id}                       ubah atribut (audit)
POST          /api/units/{id}/block                 blokir/buka blokir dengan alasan
POST          /api/units/import                     impor CSV/XLSX (validasi + dry-run + laporan baris gagal)
GET           /api/projects/{pid}/tree              pohon cluster→blok→unit (untuk navigasi & siteplan)
GET           /api/units/{id}/360                   agregat Unit 360 (penjualan+konstruksi+dokumen+riwayat)
```

## 4. Harga unit (dapat dijelaskan, bukan angka ajaib)
```
price = unit_type.base_price
      + cluster.price_policy premium         (mis. +5% untuk cluster premium)
      + block premium                        (mis. blok dekat taman)
      + view/position premium                (hook, sudut, hadap)
      + Σ addon terpilih (saat reservasi)     → lihat §5
      - diskon/promo (butuh peran approval)
```
Setiap komponen disimpan di `units.price_components` + `contracts.price_breakdown[]` sehingga SPR & finance konsisten ([26](26_CUSTOMER_LEGAL_SPEC.md) §3, [27](27_DOCGEN_SPEC.md) §3).
**Riwayat harga**: `unit_price_history[]` `{at, by, from, to, reason}` — wajib alasan bila unit sudah pernah dipromosikan/di-hold.

## 5. Master ADD-ON / spek tambahan (permintaan baru owner)
Detail field ada di [26](26_CUSTOMER_LEGAL_SPEC.md) §4. Yang berkaitan dengan unit:
- Add-on bisa **melekat pada unit** (mis. unit hook → otomatis usul add-on `posisi_unit`; unit dengan `excess_land_m2>0` → otomatis usul add-on `kelebihan_tanah` + wajib SPKT).
- **Tidak** mengubah `unit_type.base_price`; add-on selalu komponen terpisah agar laporan bisa memisahkan pendapatan inti vs tambahan.
- Endpoint master: `GET/POST /api/addon-items`, `PUT /api/addon-items/{id}`, `GET /api/units/{id}/suggested-addons`.

## 6. Wiring Site Plan ↔ Unit (CR-23)
- `site_plans` (sudah ada, Fase 25/28b) menyimpan shape per unit. V2: shape wajib menyimpan `unit_id` (bukan hanya kode) + `block_id`, dan `units.siteplan.shape_id` menyimpan balikannya (dua arah, dijaga invarian).
- Klik shape → buka **Unit 360** (halaman kanonik), bukan drawer terbatas.
- Warna peta = `sales_status`; **pola/garis** = `build_status` (dua dimensi tetap terbaca, dan tetap punya legenda teks — gate `verify_ui_surfaces.py`).
- Mode aksi per peran: `sales` → hold/booking; `pm/site` → lihat progres & mulai bangun; `owner` → read-only + analitik; `publik/showroom` → hanya unit `available` tanpa data pribadi (sudah ada `PublicShowroom`).
- Editor peta (`MappingStudio.js`) diperluas: tempel shape ke blok, penomoran otomatis, deteksi shape tanpa unit / unit tanpa shape (**laporan konsistensi** wajib nol sebelum fase ditutup).

## 7. UI (menggantikan `pages/ProjectsPage.js` yang minim informasi)
**`/projects`** — tabel proyek: nama, lokasi, jumlah cluster/blok/unit, terjual/tersedia, progres konstruksi rata-rata, nilai kontrak, target vs realisasi, status.
**`/projects/:id`** — tab: Ringkasan · **Struktur (tree cluster→blok→unit + tabel unit)** · Target & Realisasi · RAB vs Realisasi · Perizinan · Site Plan · Tim.
**Tabel unit** (wajib fitur lengkap): kolom `kode, cluster, blok, no, tipe, LT/LB, hook, harga, status penjualan, status bangun, customer, PIC, umur status`; filter multi + sort + kolom pilihan + ekspor + aksi massal (ubah harga dengan alasan, blokir, generate unit).
**`/units/:id` Unit 360** — lihat [23](23_IA_UX_BLUEPRINT.md) §4.3.

## 8. Definition of Done
1. User bisa membuat proyek → cluster → blok → unit (satuan, massal, dan impor CSV) tanpa menyentuh database.
2. Setiap unit punya `cluster_id` & `block_id` (tidak ada lagi blok hasil `code.split`) — diverifikasi migrasi + INV.
3. Siteplan: 0 shape tanpa unit, 0 unit tanpa shape untuk proyek yang dipetakan.
4. Unit terjual otomatis terikat `customer_id` + `contract_id`; membuka Unit 360 memperlihatkan pembayaran & konstruksi.
5. Dua status paralel tampil dan tidak pernah saling menimpa (uji negatif).
6. Gate baru `verify_masterplan.py` + `run_all_gates.sh` PASS.
