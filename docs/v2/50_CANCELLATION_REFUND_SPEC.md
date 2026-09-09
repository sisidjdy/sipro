# 50 — SPEC: PEMBATALAN KONTRAK & REFUND BERJURNAL (Fase 56C)

> SSOT fitur pembatalan. Gate penjaga: `scripts/verify_cancellation_refund.py` (gate 47),
> dibuktikan bergigi oleh `scripts/mutasi_56.py` (47 mutan, 47 TERTANGKAP / 0 LOLOS).
> POC isolasi: `poc/poc_56.py` (67 pemeriksaan).

## 1) Lubang yang ditutup

Dokumen SPR yang dicetak sistem ini (Fase 53E) sudah **menjanjikan** angka kepada pembeli:

| Janji di SPR | Sumber nilainya |
|---|---|
| potongan 35% bila mundur sebelum pembangunan | `cancellation.cut_before_build_pct` |
| potongan 50% bila pembangunan sudah berjalan | `cancellation.cut_during_build_pct` |
| refund dibayar setelah unit terjual kembali | `cancellation.refund_requires_resale` |

Sebelum Fase 56C **tidak ada satu pun endpoint atau layar yang bisa menjalankan janji itu**:

1. KPR yang DITOLAK bank hanya *mengusulkan* nominal refund; tidak ada yang membukukannya.
2. `POST /deals/{id}/cancel` hanya menulis `status="cancelled"` dan melepas unit — uang
   pembeli tetap berdiri sebagai kewajiban `2-1400` tanpa penyelesaian.
3. Tab "Rencana Bayar" menulis apa adanya bahwa "mesin pembatalan/refund berjurnal belum
   ada" — pengakuan jujur yang ditutup di fase ini.

## 2) Tiga tangan yang berbeda (pemisahan tugas)

| Peran | Izin | Yang dikerjakan |
|---|---|---|
| Manajer Sales / Marketing Admin | `cancellation:create` | **mengajukan** (alasan wajib ≥10 huruf) |
| Manajer Keuangan / Direksi | `cancellation:approve` | **memutuskan** — di sinilah jurnal lahir |
| Keuangan (kasir) | `cancellation:update` | **membayar refund** dari kas/bank |
| Manajer Keuangan | `cancellation:override` | mengabaikan penahanan "menunggu penjualan ulang" |

Pengaju **tidak boleh** memutuskan pengajuannya sendiri — dijaga MESIN (`cx.decide`), bukan
hanya oleh tombol yang disembunyikan layar.

## 3) Keadaan (`cancel_state`, Kamus Data)

```
diajukan → disetujui → refund_sebagian → selesai
        ↘ ditolak (beralasan)
```

* `diajukan` — **belum ada jurnal**. Pengajuan adalah NIAT, bukan peristiwa uang.
* `disetujui` — jurnal keputusan lahir, unit kembali ke stok, AR dibatalkan, Berita Acara
  Pembatalan terbit.
* `refund_sebagian` / `selesai` — mengikuti pembayaran refund.

## 4) Jurnal

**Keputusan (satu jurnal, berimbang):**

| Akun | D | K | Keterangan |
|---|---|---|---|
| `2-1400` Uang Muka Penjualan | uang yang diterima | | kewajiban kepada pembeli diselesaikan |
| `2-1450` Titipan Pelanggan | saldo titipan | | titipan dikembalikan PENUH |
| `4-1200` Pendapatan Lain-lain | | potongan | potongan pembatalan (35%/50%) |
| `2-1460` Utang Refund Pembatalan | | sisanya | kewajiban NYATA kepada pembeli |

**Pembayaran refund (per pembayaran):** `Dr 2-1460` / `Cr 1-1100 kas` atau `1-1200 bank`
sesuai caranya. Idempoten lewat `client_ref`; nominal tidak boleh melebihi sisa; setelah
lunas `2-1460` untuk pembatalan itu kembali NOL.

## 5) Gerbang penolakan (`cancel_block`, semuanya DISEBUTKAN sebabnya)

`kontrak_belum_ada`, `kontrak_sudah_batal`, `pengajuan_berjalan`, `sudah_ajb`, `sudah_bast`,
`bukti_menunggu_verifikasi`. Layar menampilkan kalimat sebab — bukan tombol mati.

## 6) Penahanan refund (`refund_hold`)

`sudah_lunas` (diperiksa PALING DAHULU), `belum_disetujui`, `refund_nol`,
`menunggu_penjualan_ulang`. Yang terakhir adalah ketentuan SPR dan hanya boleh diabaikan
Manajer Keuangan dengan alasan tertulis ≥10 huruf (tercatat pada baris pembayaran & audit).

## 7) Endpoint

| Method | Path | Izin |
|---|---|---|
| GET | `/api/cancellations/preview?contract_id=` | `cancellation:view` |
| GET | `/api/cancellations` (filter state/contract/customer/q) | `cancellation:view` |
| GET | `/api/cancellations/{id}` | `cancellation:view` |
| POST | `/api/cancellations` | `cancellation:create` |
| POST | `/api/cancellations/{id}/decision` | `cancellation:approve` |
| POST | `/api/cancellations/{id}/refund` | `cancellation:update` (+`override`) |
| GET | `/api/cancellations/by-contract/{id}/document` | `cancellation:view` |
| GET | `/api/portal/cancellations` | sesi portal pembeli |

## 8) Layar

| Layar | Berkas | Isi |
|---|---|---|
| Profil pembeli → Kontrak & Legal | `components/contracts/CancellationPanel.js` | pratinjau hitungan, ajukan, kartu keputusan, bayar refund, riwayat, cetak berita acara |
| Keuangan → Pembatalan & Refund (`/finance?tab=cancellations`) | `components/finance/CancellationsPanel.js` | daftar lintas pembeli, utang refund belum dibayar, baris yang tertahan + sebabnya |
| Portal pembeli → Pembatalan | `components/portal/panels/CancellationPanel.js` | angka yang SAMA dengan pembukuan, dasar aturan, yang sedang ditunggu, riwayat pengembalian, berita acara |

Aturan kejujuran yang dipegang layar: label keadaan & sebab dibaca dari Kamus Data,
"belum diisi" bukan Rp 0, dan **tidak ada nomor akun yang tampil kepada pembeli**.

## 9) Dokumen

`BAP` — *Berita Acara Pembatalan Pesanan & Perhitungan Pengembalian Dana*. Template disimpan
sebagai DATA (`document_templates`, bisa diperbaiki admin tanpa deploy), bernomor
`{urut}/{kode}/{proyek}/{romawi}/{tahun}`, dan bisa dicetak PDF oleh staf maupun pembeli
(lewat sesi portal, bukan tautan mentah bertoken).

## 10) Yang SENGAJA tidak dilakukan aplikasi ini

* Pembatalan **setelah AJB/BAST** — itu pembalikan jual beli yang harus lewat notaris.
* Menghapus kuitansi yang sudah dipegang pembeli (pembatalan ≠ menghapus bukti).
* Membayar refund tanpa keputusan, atau melebihi sisa utang refund.
