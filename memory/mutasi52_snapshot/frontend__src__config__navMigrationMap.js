// navMigrationMap.js — PETA MENU LAMA -> BARU (Fase 40c).
//
// Ini bukan dokumentasi tempelan: isinya dipakai LANGSUNG oleh dialog "Peta Menu Baru" di
// sidebar, sehingga pemakai lama bisa mencari nama menu yang ia hafal dan langsung dibawa ke
// tempat barunya. Satu baris = satu fitur; `to` WAJIB rute yang benar-benar ada (dijaga gate
// `scripts/verify_ia_v2.py`), jadi peta ini tidak bisa membusuk diam-diam.
//
// FASE 52 — CACAT NYATA YANG DITUTUP DI BERKAS INI (dilaporkan pemakai super admin:
// "saya super admin namun ada menu yang tidak bisa saya akses"):
// dulu daftar "BELUM DIBANGUN (TAMPIL TERKUNCI DI SIDEBAR)" di dialog ini ditulis TANGAN
// dan berisi tiga menu beserta NOMOR FASE:
//     Kampanye & Biaya Iklan — Fase 44
//     Atribusi & CAPI        — Fase 44
//     Analitik & BI          — Fase 45
// Ketiganya SUDAH DIBANGUN dan bisa dibuka (`/campaigns`, `/attribution`, `/bi` menjawab 200
// dan tampil penuh untuk super admin), serta sidebar TIDAK mengunci satu pun dari mereka.
// Jadi aplikasi memberi tahu pemiliknya bahwa tiga menu "belum dibangun & terkunci" padahal
// menu itu ada di sidebarnya dan berisi data — layar berbohong, dan pemakai wajar menyimpulkan
// "ada menu yang tidak bisa saya akses".
//
// Aturan sekarang (sama semangatnya dengan aturan `soon` di `TabPage`):
//   1. Daftar terkunci TIDAK LAGI ditulis tangan. Ia DIDERIVASI dari `navigationConfig.js`
//      (`comingSoonItems()`), satu-satunya sumber yang tahu menu mana yang benar-benar
//      dirender terkunci. Bila kelak ada item `comingSoon: true`, ia muncul sendiri; begitu
//      item itu diberi `path` dan tidak lagi `comingSoon`, ia hilang sendiri.
//   2. Tidak ada NOMOR FASE di layar. Urutan pengerjaan pernah berubah, sehingga janji
//      bernomor kedaluwarsa dan berubah menjadi kebohongan.
import { comingSoonItems } from "./navigationConfig";

export const NAV_MIGRATION = [
  { old: "Deal & Unit", now: "CRM › Customer & Kontrak → tab “Deal & Unit”",
    to: "/customers?hub=deal",
    why: "Unit, deal, pembeli, dan dokumennya adalah SATU alur bisnis." },
  { old: "Customer & KPR", now: "CRM › Customer & Kontrak → tab “Pembeli”",
    to: "/customers?hub=pembeli",
    why: "Satu pintu untuk pembeli; profil lengkap ada di halaman /customers/:id." },
  { old: "Lead", now: "CRM › Pipeline Lead", to: "/leads",
    why: "Nama menu disamakan dengan isinya (pipeline), profil di /leads/:id." },
  { old: "Inbox WA", now: "CRM › Percakapan (WA)", to: "/inbox",
    why: "Istilah “percakapan” dipakai konsisten dengan template & playbook WA." },
  { old: "Automasi & Channel", now: "Marketing › Automasi & Channel", to: "/automation",
    why: "Domain marketing dipisah dari CRM penjualan." },
  { old: "Proyek & Unit", now: "Proyek › Master Proyek", to: "/projects",
    why: "Struktur proyek→cluster→blok→unit; Unit 360 di /units/:id." },
  { old: "Progres & Mutu", now: "Proyek › Pembangunan → tab “Progres & Mutu”",
    to: "/build?hub=progres", why: "Empat menu pembangunan dilebur jadi satu hub bertab." },
  { old: "Kalender Jadwal", now: "Proyek › Pembangunan → tab “Kalender Jadwal”",
    to: "/build?hub=kalender", why: "Jadwal & progres dibaca bergantian; jangan pindah menu." },
  { old: "Buku Harian & Punch", now: "Proyek › Pembangunan → tab “Buku Harian & Punch”",
    to: "/build?hub=lapangan", why: "Laporan lapangan menempel pada konteks pembangunan." },
  { old: "Kalibrasi Jadwal", now: "Proyek › Pembangunan → tab “Kalibrasi Jadwal”",
    to: "/build?hub=kalibrasi", why: "Kalibrasi = tindak lanjut dari analitik jadwal." },
  { old: "(baru)", now: "Proyek › Pembangunan → tab “Papan Unit”",
    to: "/build?hub=unit",
    why: "Tabel unit LINTAS proyek: cari/filter status bangun (mis. semua unit QC hold)." },
  { old: "Perizinan & Dokumen", now: "Dokumen → tab “Perizinan”", to: "/documents?hub=perizinan",
    why: "Daftar global izin masuk Dokumen; izin per objek tetap di Unit 360 & Proyek." },
  { old: "Site Plan & Showroom", now: "Proyek › Site Plan", to: "/site-plan",
    why: "Satu baris menu untuk penjualan & proyek (dulu muncul dua kali)." },
  { old: "Work Hub", now: "Kerja › Tugas & Papan Divisi", to: "/tasks",
    why: "Nama menu memakai bahasa Indonesia & menyebut isinya." },
  { old: "Kas Bon", now: "Keuangan › Kas Bon", to: "/petty-cash",
    why: "Pengeluaran kas berada satu grup dengan keuangan lain." },
  { old: "Marketing Fee", now: "CRM › Mitra & Fee → tab “Tagihan Fee”",
    to: "/partners?hub=tagihan",
    why: "Tagihan fee tidak berdiri sendiri: ia lahir dari aturan fee mitra (Fase 42). "
      + "Rute /marketing-fee tetap hidup sebagai alias." },
  { old: "Master Agen", now: "CRM › Mitra & Fee → tab “Master Mitra”",
    to: "/partners?hub=mitra",
    why: "Master agen menjadi master MITRA: kontrak, aturan fee, atribusi lead, analitik." },
  // ---------------------------------------------------------------------------------
  // Fase 52 — tiga menu di bawah ini DULU tertulis "belum dibangun & terkunci" di dialog
  // ini. Semuanya sudah hidup; sekarang mereka jadi baris peta yang BISA DIKLIK supaya
  // pemakai yang mencarinya menemukan tempatnya, bukan pengumuman bahwa menunya tidak ada.
  // ---------------------------------------------------------------------------------
  { old: "Kampanye & Biaya Iklan (dulu terkunci)", now: "Marketing › Kampanye & Biaya Iklan",
    to: "/campaigns",
    why: "Sudah aktif: biaya iklan per kampanye masuk sistem dan bisa dipertemukan dengan "
      + "lead serta penjualannya. Tidak lagi terkunci." },
  { old: "Atribusi & CAPI (dulu terkunci)", now: "Marketing › Atribusi & CAPI",
    to: "/attribution",
    why: "Sudah aktif: asal-usul lead (kampanye/mitra) dan pengiriman ulang event konversi "
      + "ke platform iklan. Tidak lagi terkunci." },
  { old: "Analitik & BI (dulu terkunci)", now: "Analitik & BI › Dashboard Analitik",
    to: "/bi",
    why: "Sudah aktif: metrik eksekutif, penjualan, marketing, proyek, dan kinerja tim — "
      + "termasuk kamus metrik yang menyebut metrik mana yang datanya belum ada." },
];

/**
 * Fitur yang BENAR-BENAR belum dibangun — DIDERIVASI dari `navigationConfig.js`.
 *
 * Sengaja bukan daftar tangan lagi (lihat catatan Fase 52 di atas): satu-satunya yang boleh
 * mengaku "terkunci" adalah item yang MEMANG dirender terkunci oleh sidebar
 * (`comingSoon: true`). Hari ini daftarnya KOSONG — dan kosong itulah kebenarannya.
 */
export const NAV_SOON = comingSoonItems();

/** Versi ber-peran: hanya menu terkunci yang memang muncul di sidebar peran tersebut. */
export function navSoonFor(role) {
  return comingSoonItems(role);
}
