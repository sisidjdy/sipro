# 51 — TOLERANSI KETERLAMBATAN & DENDA BERJURNAL (Fase 58)

SSOT fitur. Bila dokumen ini dan kode berbeda, **kode yang menang** — dan dokumen ini yang
harus diperbaiki (bukan sebaliknya).

## 1) Masalah yang ditutup

Dokumen SPR yang dicetak sistem ini berbunyi: *"cicilan wajib dibayar setiap tanggal 7;
toleransi paling lambat tanggal 20"*. Sejak Fase 57A pemakai bahkan menyusun toleransi itu
sendiri per termin (`payment_schemes.items[].grace_days`). Sampai Fase 57 angka itu **tidak
dipakai siapa pun**:

| Gejala | Akibat nyata |
|---|---|
| `ar_invoices.items` tidak membawa `grace_days` | toleransi hilang begitu skema diterjemahkan menjadi tagihan |
| Layar menandai TERLAMBAT pada H+1 | aplikasi menuduh pembeli menunggak lebih cepat daripada perjanjiannya sendiri |
| Denda hanya angka worksheet (`finance_reports.compute_denda`) dengan tarif di `DEFAULT_COLLECTION` | kebijakan penagihan tidak bisa diubah pemilik usaha tanpa deploy, dan berbeda dari yang tertulis di dokumen |
| Denda yang diterapkan tidak berjurnal | pembeli ditagih sesuatu yang tidak ada di buku besar; tidak ada laporan "berapa denda kita" |
| Tidak ada jalan resmi meringankan denda | keputusan yang paling sering diambil manusia tidak punya jejak |

## 2) Kebijakan (Pusat Konfigurasi, grup `pembayaran`)

| Kunci | Bawaan | Arti |
|---|---|---|
| `payment.late.grace_days` | 7 | toleransi BAWAAN bila termin tidak menyebut sendiri |
| `payment.late.rate_pct_month` | 2 | tarif denda per bulan dari tunggakan termin (sensitif) |
| `payment.late.max_pct_of_term` | 5 | batas denda per termin (sensitif) |
| `payment.late.min_charge` | 50.000 | denda di bawah ini tidak diterbitkan |

**Toleransi yang tertulis pada TERMIN selalu menang** atas angka bawaan
(`late_fee_engine.grace_of`).

## 3) Keadaan termin (Kamus Data `late_state`)

`lunas` · `menunggu` · **`dalam_tenggang`** (baru: lewat tanggal, belum menunggak) ·
`terlambat` (lewat toleransi). Hari denda dihitung `days_past_due − grace`, prorata
`rate/100 × hari/30`, dibatasi `max_pct_of_term`, diabaikan bila `< min_charge`.

## 4) Jurnal

| Peristiwa | Jurnal | Idempotensi |
|---|---|---|
| Denda ditagihkan | **Dr 1-1300** Piutang Usaha / **Cr 4-1400** Pendapatan Denda Keterlambatan | `source_event = late_fee:{deal}:{termin}:{YYYY-MM}` |
| Keringanan | **Dr 4-1400** / **Cr 1-1300** | `source_event = late_fee_waive:{penalty_id}` |

Yang ditagihkan adalah **selisih** denda berjalan dengan yang sudah ditagihkan **dan** yang
sudah diringankan (`_waived_days_map`) — keringanan tidak bisa dianulir dengan menekan
"Tagihkan denda" lagi.

## 5) Pemisahan tugas (RBAC resource `late_fee`)

| Aksi | Izin | Peran |
|---|---|---|
| melihat | `late_fee:view` | keuangan, manajer keuangan, manajer sales, marketing, PM (sales: hanya miliknya) |
| menagihkan (berjurnal) | `late_fee:create` | keuangan, manajer keuangan |
| **meringankan** | `late_fee:override` | **hanya manajer keuangan** — wajib alasan ≥ 10 huruf |

## 6) Endpoint

```
GET  /api/finance/late-fees/policy            kebijakan + kalimat aturan
GET  /api/finance/late-fees/{deal_id}         keadaan tiap termin, denda berjalan & tertagih
POST /api/finance/late-fees/{deal_id}/apply   tagihkan denda (berjurnal, idempoten)
POST /api/finance/late-fees/{deal_id}/waive/{penalty_id}   keringanan beralasan
```

Tombol lama `POST /api/finance/collections/{deal_id}/late-fee` **tetap ada** dan sekarang
memakai mesin yang sama (tidak ada rumus & jurnal kedua).

## 7) Layar

* **Profil pembeli → Rencana Bayar**: keadaan termin dari server (termasuk *"dalam masa
  toleransi · sisa N hari"*), spanduk tenggang, dan panel **Toleransi keterlambatan & denda**
  (kalimat aturan, ringkasan, tombol *Tagihkan denda*, daftar denda + *Beri keringanan*).
* **Portal pembeli → Pembayaran**: kartu toleransi & denda dengan angka yang SAMA dengan
  pembukuan, tanpa nomor akun GL.
* **Keuangan → Penagihan**: tunggakan kini terpisah dari `in_grace_amount`.

## 8) Guardrail

* `scripts/verify_late_fee.py` — **GATE 49**, 67 pemeriksaan (K kode, K-UI layar, D perilaku
  HTTP + jurnal), terdaftar di `scripts/run_all_gates.sh`.
* `scripts/mutasi_58.py` — **31 mutan** (`memory/gatelogs/mutasi_58_hasil.tsv`).
