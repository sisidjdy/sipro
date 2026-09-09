# 52 — Kas & Bank (Fase 82): rekening/kas sebagai entitas akuntansi + analisis gap

## 1. Masalah yang ditutup
Sebelum Fase 82 uang perusahaan hanya diwakili dua akun GL (`1-1100 Kas`, `1-1200 Bank`). Master
rekening bank (Fase 47A) ada, tetapi semua rekening menunjuk `1-1200` yang sama; penerimaan AR,
pembayaran AP, komisi, kas bon, pajak, refund, dan pencairan KPR tidak menyebut rekening mana yang
dipakai. Akibat akuntansinya fatal: **saldo per rekening tidak ada**, rekonsiliasi bank hanya bisa
di level total, tidak ada buku kas/bank, tidak ada transfer antar rekening / setor / tarik tunai,
saldo awal rekening tidak dijurnal (neraca ≠ rekening), dan kas kecil tidak punya saldo.

## 2. Model
| Konsep | Implementasi |
|---|---|
| Akun induk | `1-1100`, `1-1200` ditandai `is_header=True`; **tidak boleh menerima posting**. `post_journal` otomatis mengarahkan baris di akun induk ke sub-akun rekening yang dipilih (`cash_account_id` di baris) atau rekening/kas **default** jenis itu. |
| Sub-akun | Setiap rekening/kas punya sub-akun: bank `1-1201..1-1299` (parent `1-1200`), kas `1-1101..1-1199` (parent `1-1100`). Nama = `"<Bank> — <nama rekening>"`. Prefix `1-11`/`1-12` tetap terbaca oleh laporan arus kas & neraca (klasifikasi via prefix). |
| Master terpadu | Koleksi `bank_accounts` diperluas: `kind` (`bank`/`cash`), `is_default` per jenis, `opening_balance`, `opening_date`, `opening_posted`, `opening_journal_id`. Rekening lama Fase 47 tetap dipakai (rekonsiliasi bank tidak berubah). |
| Saldo awal | Dijurnal otomatis saat rekening dibuat/diubah (sekali): Dr sub-akun / Cr `3-1950 Saldo Awal Kas & Bank` (ekuitas), `source_event=cashbank.opening:<id>` (idempoten). Setelah dijurnal, saldo awal terkunci. |
| Migrasi | `cash_bank.ensure_setup()` saat startup (awal & akhir lifespan, per org): backfill `kind`, bootstrap Kas Besar (`KAS-01`, `1-1101`) & Rekening Operasional bila kosong, sub-akun untuk rekening yang masih menumpang `1-1200`, pilih default, posting saldo awal, **pindahkan baris jurnal lama di akun induk ke rekening default** (`migrated_from` disimpan). Idempoten. |
| Wiring aliran uang | `cash_account_id` opsional di: `POST /finance/ar/receipts`, `POST /finance/ap/bills/{id}/pay` & `/pay-withholding`, `POST /finance/commissions/{id}/pay`, `POST /petty-cash/advances/{id}/disburse` (+ pengembalian sisa memakai rekening yang sama), `PUT /tax/records/{id}` (setor), `POST /cancellations/{id}/refund`, `POST /contracts/{id}/kpr/stage/pencairan`, `POST /financing/{id}/disburse`. Dokumen (kuitansi, payments_out, kas bon, komisi, pencairan KPR) menyimpan `cash_account_id/_name/_code`. Rekening fiktif/nonaktif → 400 di muka; tanpa id → default jenis (bank untuk transfer/KPR, kas untuk tunai). |
| Rekonsiliasi bank | `bank_match._apply` kini memakai rekening mutasi sebagai `cash_account_id` (AR, AP) dan sub-akunnya untuk biaya bank / jasa giro; pembatalan kuitansi membalik ke sub-akun kuitansi. |
| Transfer internal | Koleksi `cash_transfers` (`TRF/<tahun>/<n>`): `transfer`, `setor_tunai` (kas→bank), `tarik_tunai` (bank→kas), `isi_kas_kecil` (→kas). Status `pending → posted/rejected`. **SoD**: pembuat ≠ penyetuju; approve butuh izin `bank:approve` (finance_manager/owner/super_admin). Saldo asal harus cukup (nominal + biaya). Jurnal: Dr tujuan / Cr asal (nominal+biaya) / Dr `6-1600` biaya. |
| Buku Kas & Bank | `GET /cash-bank/book?account_id&date_from&date_to[&format=csv]`: saldo awal (Σ sebelum periode), mutasi dengan lawan akun & saldo berjalan, total masuk/keluar, CSV `;`. |
| Posisi Kas | `GET /cash-bank/position`: saldo buku tiap rekening, total kas/bank, mutasi bulan berjalan, daftar saldo negatif (jujur, bukan disembunyikan), transfer menunggu. |

### Endpoint `/cash-bank` (RBAC resource `bank`)
`GET /accounts[?active&kind]`, `POST /accounts`, `PUT /accounts/{id}`, `POST /accounts/{id}/set-default`,
`GET /position`, `GET /book`, `GET /transfers[?status]`, `POST /transfers`, `POST /transfers/{id}/approve|reject`.

### UI
Menu **Keuangan › Kas & Bank** (`/cash-bank`): tab Posisi Kas · Buku Kas & Bank (+CSV) · Transfer Internal
(ajukan/setujui/tolak) · Master Rekening & Kas. Komponen `CashAccountSelect` (memuat rekening aktif +
saldo, auto-pilih default per jenis) disematkan di: dialog Penerimaan AR, Bayar Tagihan AP, Pencairan
Kas Bon, Setor Pajak (status "paid"), Bayar Refund pembatalan, dan tahap **Pencairan KPR**
("Dana KPR masuk ke rekening" — default rekening bank default; sebaiknya rekening escrow).

### Pencairan KPR — wiring rekening (permintaan user)
Alur: bank KPR mencairkan → `KprPanel` tahap *pencairan* (atau `/financing/{id}/disburse`) mengirim
`cash_account_id` → `kpr_disburse.disburse()` → `finance_engine.apply_receipt(method="kpr", cash_account_id)`
→ kuitansi KWT menyimpan rekening → event `payment.received{cash_account_id}` → jurnal Dr **sub-akun
rekening penerima** / Cr `2-1400`. Entri pencairan di `financing.disbursements[]` menyimpan
`cash_account_id/_name`. Kelebihan (titipan) ikut ke rekening yang sama.

## 3. Uji & gate
- `backend/tests/test_p82_cash_bank.py` (4): master & default, saldo awal + CSV + duplikat, transfer SoD/posting/saldo/jurnal, kuitansi & jurnal mendarat di rekening pilihan + rekening fiktif ditolak.
- Gate lama disesuaikan ke sub-akun: `verify_f26_money.py` (`gl_balance` Σ sub-akun), `verify_p27_money.py` (`tb()` agregasi induk), `verify_quotation_labor.py`, `verify_tax_compliance.py`, `test_p76_78_allin_kpr.py`, `test_p78_ui_api.py`; `verify_bank_recon.py` kini memilih kuitansi hasil pencocokan (bukan kuitansi booking fee — bug gate pre-existing).

## 4. Fase 83 — Rekonsiliasi per rekening (menutup P0 #1)
- `bank_recon.py`: untuk satu rekening, saldo rekening pada **tanggal mutasi terakhir** dibanding saldo **sub-akun GL rekening itu** pada tanggal yang sama (bukan lagi total `1-1200`). Selisih diurai:
  - `bank_only` — mutasi rekening `unmatched` ≤ tanggal (belum ada di buku);
  - `book_only` — baris jurnal sub-akun yang `source_id`-nya tidak muncul di `bank_matches` (belum ada di rekening), tiap item bisa **diberi alasan** (`bank_recon_notes`: setoran dalam perjalanan, cek belum kliring, beda tanggal, biaya bank belum diimpor, salah catat, lainnya+catatan) — dokumentasi saja, angka tidak berubah;
  - `statement_opening` — saldo rekening tersirat sebelum mutasi pertama (= saldo akhir − Σ mutasi), tanda periode sebelumnya belum diimpor;
  - `residual` = (rekening + book_only) − (buku + bank_only) − statement_opening → **0 = selisih terurai tuntas**; ≠0 dilaporkan sebagai "residu tak terjelaskan".
  - Status: `seimbang` / `dijelaskan` / `belum_dijelaskan` / `tanpa_data`.
- Endpoint: `GET /bank/reconciliation?account_id[&as_of]` (bentuk lama tetap + field baru), `GET /bank/reconciliation/overview` (semua rekening bank + ringkasan status), `POST /bank/reconciliation/explain|unexplain` (`bank:update`). `GET /bank/accounts` kini hanya rekening bank (kas dikecualikan).
- UI Rekonsiliasi Bank: tabel ikhtisar per rekening (klik = pilih), panel uraian dua keranjang + tombol "Beri alasan", KPI Selisih membedakan "terurai" vs "ada residu".
- Uji: `tests/test_p83_bank_recon.py` 4/4 (identitas rekonsiliasi, alasan hanya dokumentasi, RBAC), gate `verify_bank_recon.py` PASSED.
- Catatan jujur: urutan baris dalam satu tanggal di CSV tidak tersimpan, sehingga "saldo akhir" memakai baris terakhir tanggal terakhir berdasarkan urutan impor.
## 5. Fase 84 — Kas kecil imprest (menutup P0 #2)
- `petty_expense.py`: pengeluaran **langsung** kas kecil (bukan kas bon) — dibayar tunai saat itu, berbukti, langsung dijurnal **Dr beban/WIP per kategori (`CASHBON_ACCOUNT`) / Cr sub-akun kas kecil**, `source_event=petty.expense:<id>`, nomor `KK/<tahun>/<n>` (aturan penomoran `petty_expense`).
  - Validasi di muka: kas harus `kind=cash` aktif; nominal ≤ `petty_cash.max_expense` (di atasnya → kas bon / AP); bukti wajib bila `petty_cash.require_proof`; saldo kas cukup; tanggal tidak di masa depan; kategori dari SSOT `cashbon_category`.
  - **Void** (`bank:approve`, SoD pencatat ≠ pembatal, alasan ≥5) = jurnal balik `petty.expense.void:<id>`; dokumen tetap ada berstatus `voided`.
- **Imprest**: batas dana tetap per kas (`bank_accounts.imprest_limit`, opsional) atau bawaan org `petty_cash.imprest_limit`; ambang `petty_cash.replenish_threshold_pct`. `GET /petty-cash/imprest` → per kas: saldo, batas, ambang, `month_spent/count`, pengisian yang masih pending, **`suggested_replenish` = batas − saldo − pending** bila saldo < ambang; status `cukup / perlu_isi / menunggu_isi / melebihi_batas`.
- `POST /petty-cash/imprest/{id}/replenish` mengajukan transfer internal `isi_kas_kecil` (dari rekening bank default atau `from_account_id`) sebesar usulan → tetap **pending** sampai disetujui (SoD Fase 82). Ditolak bila saldo masih di atas ambang, sudah ada pengisian pending, atau pengisian melampaui batas.
- Endpoint (`routers/petty_expense_router.py`, resource RBAC `bank`): `GET /petty-cash/imprest`, `POST /petty-cash/imprest/{id}/replenish`, `GET/POST /petty-cash/expenses`, `POST /petty-cash/expenses/{id}/void`. Pusat Konfigurasi grup baru **Kas Kecil (Imprest)** (4 kunci `petty_cash.*`).
- UI: Kas & Bank › tab **Kas Kecil** — kartu imprest per kas (saldo vs batas, bar, status, tombol "Ajukan pengisian Rp X"), daftar pengeluaran (filter kas/status, bukti, jurnal, batalkan), dialog "Catat Pengeluaran" (kas, kategori SSOT, nominal, keterangan, tanggal, penerima, proyek, `EvidenceUploader` bukti). Master kas: kolom "Batas dana tetap (imprest)".
- Uji: `tests/test_p84_petty_expense.py` 4/4 (bukti & batas, jurnal + void SoD + saldo pulih, usulan pengisian di bawah ambang, RBAC & rekening bank ditolak).
- Catatan jujur: Kas Besar (bukan kas kecil) ikut dinilai terhadap batas imprest bawaan → tampil "Melebihi batas" (informatif); setel `imprest_limit` per kas bila kas besar memang boleh besar.

## 6. Fase 85 — Tutup periode Kas & Bank per rekening (menutup P0 #1 sisa & P0 #3)
- `cash_period_lock.py`, koleksi `cash_period_locks`. Kunci per (rekening, bulan): **bank** hanya bila rekonsiliasi Fase 83 per akhir bulan berstatus `seimbang`/`dijelaskan` dan mutasi terakhir yang diimpor sudah di bulan itu; **kas** hanya bila hasil opname (fisik) = saldo buku akhir bulan. Bulan berjalan tidak bisa dikunci. `closing_balance` disimpan = saldo awal tetap periode berikutnya.
- Penegakan di `gl.post_journal` (`cash_period_lock.resolve_date`): baris ke sub-akun yang terkunci dengan tanggal ≤ akhir periode terkunci → jurnal **manual ditolak** (400 "…sudah dikunci…"), posting **otomatis digeser** ke hari pertama sesudah kunci + memo "posting digeser (kunci kas …)". Pembalikan (unmatch, void) tetap bertanggal hari ini → saldo penutup terkunci tidak berubah.
- Endpoint (`routers/cash_control_router.py`): `GET /cash-bank/locks` (per rekening: terkunci s.d., saldo penutup, riwayat), `GET /cash-bank/locks/preview?account_id&period[&counted_balance]` (kelayakan + alasan), `POST /cash-bank/locks` & `POST /cash-bank/locks/{id}/unlock` (`bank:approve`, alasan wajib, jejak tersimpan).
- UI: tab **Tutup Periode** — tabel rekening (saldo, terkunci s.d., saldo penutup), dialog kunci dengan pratinjau hidup (layak/belum + sebab), buka kunci beralasan, riwayat.

## 7. Fase 86 — Giro / cek mundur (PDC) (menutup P0 #4)
- `pdc_engine.py`, koleksi `pdc_instruments`, nomor `GIRO/…`. Akun baru CoA: `1-1350 Giro / Cek Belum Cair` (aset) dan `2-1480 Giro Diterima Belum Cair (Kontra)` (kewajiban).
- **Diterima**: Dr 1-1350 / Cr 2-1480 (memorandum; AR TIDAK berkurang — uang belum ada). Warkat kembar (bank+nomor) ditolak; deal wajib punya jadwal AR.
- **Kliring** (`bank:update`, pilih rekening bank aktif): pasangan dibalik, lalu `finance_engine.apply_receipt(method="cheque", cash_account_id)` → kwitansi KWT, alokasi termin, kelebihan → titipan; giro tanpa deal → Dr bank / Cr 2-1450 Titipan Pelanggan. **Tolakan**/**batal**: pasangan dibalik, alasan wajib, notifikasi keuangan; AR tetap terbuka.
- Endpoint `/pdc`: `GET` (ringkasan: di tangan, jatuh tempo ≤7 hari, lewat tempo, ditolak), `POST`, `POST /{id}/clear|bounce|cancel`.
- UI: tab **Giro Mundur** — KPI, tabel, dialog terima (jenis cek/BG, bank SSOT `financing_bank`, nomor, nominal, jatuh tempo, cari tagihan AR), dialog kliring (rekening bank + tanggal), tolakan/batal via alasan.
- Catatan jujur: 1-1350/2-1480 selalu bersaldo sama (memorandum). Cara ini dipilih supaya AR hanya berkurang lewat satu mesin (`apply_receipt`), bukan dua.

## 8. Fase 87 — Bukti Kas Masuk/Keluar (BKM/BKK) (menutup P0 #5 bagian dokumen)
- `cash_voucher.py`, koleksi `cash_vouchers`. Hook di `gl.post_journal`: setiap baris jurnal ke sub-akun kas/bank menerbitkan satu bukti bernomor — debit → **BKM/…**, kredit → **BKK/…** (aturan penomoran `cash_voucher_in/out`). Idempoten per (jurnal, sub-akun); jurnal lama diterbitkan susulan saat startup (`backfill`). Bukti = turunan jurnal (sumber kebenaran tetap `journal_entries`), menyimpan lawan akun, memo, sumber.
- Endpoint: `GET /cash-bank/vouchers?kind&account_id&date_from&date_to&q&skip&limit` (+ Σ masuk/keluar), `GET /cash-bank/vouchers/{id}`, `GET /cash-bank/vouchers/{id}/pdf` (kop `doc_layout` kode `BKM`/`BKK`; pihak diisi dari kwitansi/AP/kas bon/kas kecil/giro bila terlacak).
- UI: tab **Bukti Kas (BKM/BKK)** — filter jenis/rekening/cari, tabel bernomor dengan tombol cetak PDF, muat lebih.
- Belum: *payment run* (pembayaran massal AP) — masih per tagihan.

## 9. Analisis gap Finance & Accounting yang tersisa (backlog terurut)
**P0 — akuntansi belum utuh**
1. ~~Rekonsiliasi bank ↔ sub-akun~~ — **selesai Fase 83** (§4); kunci periode setelah seimbang — **selesai Fase 85** (§6).
2. ~~Kas kecil (imprest)~~ — **selesai Fase 84** (§5). Sisa: jadwal pengingat otomatis ke kasir bila di bawah ambang >N hari.
3. ~~Tutup periode Kas & Bank~~ — **selesai Fase 85** (§6).
4. ~~Cek/giro mundur (PDC)~~ — **selesai Fase 86** (§7). Sisa: biaya tolakan giro & denda otomatis.
5. ~~BKK/BKM bernomor & tercetak~~ — **selesai Fase 87** (§8). Sisa: **payment run** AP massal.

**P1 — pelaporan & kontrol**
6. Laporan arus kas langsung per rekening (bukan hanya klasifikasi operasi/investasi/pendanaan).
7. Aging AR/AP sudah ada tetapi belum ada **jadwal pembayaran vendor (cash forecast) vs posisi kas** → peringatan kas tidak cukup.
8. Mata uang & bunga: rekening valas, bunga deposito otomatis, biaya admin bulanan terjadwal.
9. Limit otorisasi berjenjang untuk transfer (nominal > X butuh dua penyetuju).
10. Jurnal koreksi rekening (reklas antar sub-akun) dengan alasan wajib + jejak.

**P2 — hal yang belum menyebut rekening (masih ke default)**
11. Pembayaran upah harian (`labor_engine.pay_payroll`), marketing fee, pinjaman korporat (pencairan/angsuran), perolehan aset tetap, kuitansi biaya all-in (`cost_receipt`), booking fee — sudah benar di sub-akun default, tetapi UI-nya belum menyediakan pemilih rekening.
12. Ekspor buku kas ke XLSX/PDF bertanda tangan; impor mutasi otomatis (open banking/ CSV terjadwal).
