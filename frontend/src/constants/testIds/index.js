// constants/testIds/ — central registry of data-testid values used by the
// end-to-end testing agent (qabot) to locate and interact with UI elements
// during automated tests. UI without testids cannot be automatically verified.
//
// Structure: each feature lives in its own file (auth.js, cart.js, ...) and
// is re-exported from here, so consumers can do a single import like
// `import { LOGIN, CART } from '@/constants/testIds'` (or relative).
//
// Adding a new feature:
//   1. Create constants/testIds/<feature>.js
//   2. Export named objects (e.g. `export const PROFILE = { ... }`)
//   3. Re-export here: `export * from './<feature>';`

export * from './offline';
// Fase 100 — wizard koneksi WhatsApp Cloud API (diagnosa, daftarkan nomor, langganan webhook)
export * from './p100';
export * from './legal';
export * from './profile';
// Fase 71 — aturan penomoran dokumen & kode master
export * from './p71';
// Fase 72 — Studio Site Plan
export * from './p72';
// Fase 69 — mesin harga: skema diskon, promo, kupon + reservasi ber-breakdown
export * from './p69';
// Fase 69 — mesin harga: skema diskon, promo, kupon + reservasi ber-breakdown
export * from './p69';
// Fase 59 — laporan keringanan denda, kandidat tunggakan, laporan utang refund
export * from './p59';
// Fase 60 — konfigurasi tampilan dokumen (kop/footer/tanda tangan/baris biaya)
export * from './p60';
// Fase 61 — cetak SPK subkontraktor & PO pengadaan
export * from './p61';
// Fase 62 — surat peringatan tunggakan, berita acara opname & punch list, lampiran SPK,
// dan pengiriman dokumen ke WhatsApp subkontraktor/vendor/pembeli
export * from './p62';
// Fase 62 — surat peringatan tunggakan, berita acara opname & punch list, lampiran SPK,
// dan pengiriman dokumen ke WhatsApp subkontraktor/vendor/pembeli
export * from './p62';
export * from './auth';
export * from './home';
export * from './sales';
export * from './p75';
export * from './p75';
export * from './construction';
export * from './finance';
export * from './customers';
export * from './portal';
export * from './complaints';
export * from './permits';
export * from './field';
export * from './procurement';
export * from './gl';
export * from './appointments';
export * from './tax';
export * from './subconClaims';
export * from './inspection';
export * from './omni';
export * from './master';
export * from './sitePlan';
// Fase 27
export * from './pettyCash';
export * from './assets';
export * from './corpFinancing';
export * from './marketingFee';
// Fase 28b
export * from './showroom';
// Fase 31 — jadwal pembangunan berbukti per unit
export * from './build';
// Fase 33 — lingkup SPK, opname berbukti, kendali biaya RAB
export * from './opname';
// Fase 36 — Kalender Jadwal & master kalender kerja
export * from './buildCalendar';
// Fase 37 — Kalibrasi sekali klik durasi/waktu tunggu template jadwal
export * from './buildCalibration';
// Fase 39 — Pusat Konfigurasi + hierarki proyek/unit
export * from './configCenter';
export * from './stages';
// Fase 39b — checklist dokumen syarat (dipakai di layar lead & pelanggan)
export * from './docChecklist';
// Fase 40 — IA & Design System V2 (DataTable/FilterBar/TabPage/KPI drill-down + halaman kanonik)
export * from './ia';
// Fase 41 — umur tahap & kebijakan SLA (satu sumber ambang untuk semua daftar)
export * from './aging';
// Fase 47 — rekonsiliasi bank, bukti transfer pelanggan, penawaran, absensi & upah
export * from './p47';
export * from './p48';
// Fase 42 — Mitra & Fee (master mitra, aturan fee, atribusi, analitik)
export * from './partners';
// Fase 43 — Kampanye & Biaya Iklan, Atribusi & CAPI, status integrasi, webhook lead mitra
export * from './ads';
// Fase 44 — Analitik & BI (5 dashboard persona + kamus metrik)
export * from './bi';

export * from './budget';
// Fase 46 — hub Pembangunan unit-centric: Papan Unit, kesiapan mulai bangun, Unit 360 →
// tab Pembangunan, dan izin bertingkat (proyek → cluster → blok → unit)
export * from './buildHub';
// Fase 49 — penutupan buku (bulan & tahun), paket laporan owner, arus kas per proyek,
// e-Faktur & ekspor berkas, bukti potong (e-Bupot), rekap SPT Masa PPN
export * from './p49';
// Fase 50 — serah terima unit (BAST), masa garansi per bagian, klaim garansi pasca-huni,
// dan antrean perangkat terpadu (absensi + buku harian + punch list + foto)
export * from './p50';
// Tab yang DIAKTIFKAN setelah audit peta jalan: Kontrak & Harga + Rencana Bayar (profil
// pelanggan) dan Fee Mitra (profil lead) — sebelumnya mati dengan label nomor fase yang
// sudah lewat, padahal datanya sudah ada.
export * from './crmContract';
// Fase 51 — retensi subkon ditahan klaim garansi (51A), pengingat WhatsApp otomatis (51B),
// portal pembeli: unduh BAST & kwitansi + pengakuan penyelesaian klaim (51C)
export * from './p51';
// Fase 53 — konversi lead → PEMBELI, kontrak & tahap legal (termasuk akad kredit),
// sub-alur KPR, dan generator dokumen ASLI owner (SPR 3 varian + SPKT) yang bisa dicetak
export * from './p53';
// Fase 54 — ketahanan sesi: perpanjangan diam-diam, peringatan sebelum sesi berakhir, dan
// kembali ke halaman yang sama sesudah masuk ulang
export * from './p54';
// Fase 56 — pembatalan kontrak & refund berjurnal: janji pasal pembatalan SPR (potongan
// 35%/50%, refund menyusul penjualan ulang) akhirnya bisa dijalankan & dipertanggungjawabkan
export * from './p56';
export * from './p57';
// Fase 58 — toleransi keterlambatan & denda keterlambatan berjurnal: tenggang yang
// disusun pemakai (dan tercetak pada SPR) akhirnya dipakai penagihan, layar, dan portal.
export * from './p58';
export * from './p68';
// Manajemen Data — migrasi Excel, backup & restore.
export * from './dataMgmt';
export * from './p80';
export * from './p81';
export * from './p82';
// Fase 84 — kas kecil imprest (pengeluaran langsung + pengisian ulang).
export * from './p84';
// Fase 85–87 — kunci periode kas, giro mundur, bukti kas BKM/BKK.
export * from './p85';
// Fase 89 — skor lead berbasis event terkonfigurasi.
export * from './p89';
// Fase 91 — dashboard keuangan interaktif, tab Piutang/Utang, riwayat dokumen terbit.
export * from './p91';
// Fase 92 — drill-down KPI Beranda, Pipeline Lead, Pembangunan.
export * from './p92';
// Fase 93 — drill-down Marketing, Detail Proyek, ekspor CSV popup.
export * from './p93';
// Fase 94–95 — integrasi WhatsApp: gateway, webhook Meta, kontak WA → lead.
export * from './p94';
export * from './p97';
