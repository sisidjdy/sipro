// Config-driven navigation (pola diadopsi dari `kn`, disesuaikan untuk SIPRO).
// PAGE_META (kicker+title untuk TopBar) + NAV_STRUCTURE (grouped, role-aware) +
// buildNavGroups(role) + ROLE_HOME_REGISTRY. Item "Segera Hadir" = disabled TANPA route.
//
// FASE 40c — IA V2 (acuan `docs/v2/23_IA_UX_BLUEPRINT.md` §3, peta lengkap di
// `docs/v2/40_PETA_NAV_V2.md`). Tujuh pintu menu dilebur menjadi hub bertab TANPA menghapus
// satu pun fitur:
//   Deal & Unit                                   -> CRM > Customer & Kontrak (tab Deal & Unit)
//   Progres & Mutu / Kalender / Kalibrasi / Field -> Proyek > Pembangunan (tab)
//   Perizinan & Dokumen                           -> Dokumen (tab Perizinan)
//   Site Plan (duplikat di 2 grup)                -> satu item, terlihat sesuai peran
// Rute lamanya SENGAJA tetap hidup (`/deals`, `/construction`, `/build-calendar`,
// `/build-calibration`, `/field`, `/permits`) supaya tautan lama, pintasan notifikasi, dan
// bookmark pemakai tidak rusak — hanya PINTU MASUKnya yang disatukan.
import {
  Home, ListChecks, Bell, Users2, ShieldCheck, Building2, HardHat,
  Wallet, FileText, MessagesSquare, UserPlus, ClipboardCheck, Boxes,
  Headset, Calculator, Wrench, ShoppingCart, BookOpen, Scale,
  CalendarDays, Landmark, Workflow, Database, History, Map as MapIcon,
  Building, Banknote, Coins, SlidersHorizontal, BarChart3, Handshake, Megaphone, Target,
  DatabaseBackup, } from "lucide-react";

export const PAGE_META = {
  "/": { kicker: "Work Hub", title: "Beranda" },
  "/tasks": { kicker: "Kerja", title: "Tugas & Papan Divisi" },
  "/notifications": { kicker: "Kerja", title: "Notifikasi" },
  "/leads": { kicker: "CRM", title: "Pipeline Lead" },
  "/leads/:id": { kicker: "CRM", title: "Profil Lead" },
  "/appointments": { kicker: "CRM", title: "Agenda & Survey" },
  "/inbox": { kicker: "CRM", title: "Percakapan (WhatsApp)" },
  "/wa-capture": { kicker: "CRM", title: "Kontak WA → Lead" },
  "/automation": { kicker: "Marketing", title: "Automasi & Channel" },
  "/campaigns": { kicker: "Marketing", title: "Kampanye & Biaya Iklan" },
  "/attribution": { kicker: "Marketing", title: "Atribusi & CAPI" },
  "/bi": { kicker: "Analitik & BI", title: "Dashboard Analitik" },
  "/deals": { kicker: "CRM", title: "Deal & Unit" },
  "/site-plan": { kicker: "Proyek", title: "Site Plan & Showroom" },
  "/customers": { kicker: "CRM", title: "Customer & Kontrak" },
  "/customers/:id": { kicker: "CRM", title: "Profil Pelanggan" },
  "/projects": { kicker: "Proyek", title: "Master Proyek" },
  "/build": { kicker: "Proyek", title: "Pembangunan" },
  "/construction": { kicker: "Proyek", title: "Progres & Mutu Konstruksi" },
  "/build-calendar": { kicker: "Proyek", title: "Kalender Jadwal" },
  "/build-calibration": { kicker: "Proyek", title: "Kalibrasi Template Jadwal" },
  "/materials": { kicker: "Proyek", title: "Material & Opname" },
  "/permits": { kicker: "Dokumen", title: "Perizinan" },
  "/field": { kicker: "Proyek", title: "Buku Harian & Punch List" },
  "/boq": { kicker: "Pengadaan", title: "RAB / BoQ (Anggaran)" },
  "/subcon": { kicker: "Pengadaan", title: "Subkontraktor & SPK" },
  "/procurement": { kicker: "Pengadaan", title: "Pengadaan, Vendor & 3-Way Match" },
  "/finance": { kicker: "Keuangan", title: "AR / AP / Komisi" },
  "/petty-cash": { kicker: "Keuangan", title: "Kas Bon (Uang Muka Karyawan)" },
  "/cash-bank": { kicker: "Keuangan", title: "Kas & Bank" },
  "/marketing-fee": { kicker: "CRM", title: "Mitra & Fee" },
  "/partners": { kicker: "CRM", title: "Mitra & Fee" },
  "/partners/:id": { kicker: "CRM", title: "Profil Mitra" },
  "/fixed-assets": { kicker: "Akuntansi", title: "Aset Tetap & Penyusutan" },
  "/corporate-financing": { kicker: "Akuntansi", title: "Pembiayaan Korporat" },
  "/accounting": { kicker: "Akuntansi", title: "Buku Besar & Jurnal" },
  "/accounting/reports": { kicker: "Akuntansi", title: "Laporan Keuangan" },
  "/tax": { kicker: "Akuntansi", title: "Perpajakan (PPN/PPh/BPHTB)" },
  "/complaints": { kicker: "Layanan", title: "Komplain & CS" },
  "/documents": { kicker: "Dokumen", title: "Dokumen & Perizinan" },
  "/config": { kicker: "Konfigurasi", title: "Pusat Konfigurasi" },
  "/legal": { kicker: "Konfigurasi", title: "Legal & Privasi" },
  "/profile": { kicker: "Akun", title: "Profil Saya" },
  "/projects/:id": { kicker: "Proyek", title: "Struktur Proyek & Unit" },
  "/units/:id": { kicker: "Proyek", title: "Unit 360" },
  "/admin/users": { kicker: "Admin", title: "Pengguna" },
  "/admin/permissions": { kicker: "Admin", title: "Hak Akses (RBAC)" },
  "/admin/organizations": { kicker: "Admin", title: "Organisasi (Tenant)" },
  "/admin/master-data": { kicker: "Admin", title: "Master Data & Integritas" },
  "/admin/audit": { kicker: "Admin", title: "Jejak Audit" },
  "/admin/data-management": { kicker: "Admin", title: "Manajemen Data" },
};

const ALL = [
  "super_admin", "owner", "sales_manager", "marketing_admin",
  "sales", "finance", "project_manager", "site_engineer",
  // Fase 29 — divisi Digital Marketing & supervisor Keuangan
  "dm_supervisor", "dm_staff", "finance_manager",
  "legal_admin",
];
// Legal & Privasi: admin legal + peran yang berhadapan dengan pembeli (izin `legal` di RBAC).
const LEGAL_SIDE = ["super_admin", "owner", "legal_admin", "sales_manager", "marketing_admin",
  "dm_supervisor", "finance_manager"];
const SALES_SIDE = ["super_admin", "owner", "sales_manager", "marketing_admin", "sales",
  "dm_supervisor", "dm_staff"];
const OMNI_SIDE = ["super_admin", "owner", "sales_manager", "marketing_admin",
  "dm_supervisor", "dm_staff"];
const PROJECT_SIDE = ["super_admin", "owner", "project_manager", "site_engineer"];
const PROCUREMENT_SIDE = ["super_admin", "owner", "project_manager", "site_engineer", "finance",
  "finance_manager"];
const FINANCE_SIDE = ["super_admin", "owner", "finance", "finance_manager"];
// Marketing fee: diajukan sales/marketing, disetujui & dibayar finance/owner.
const MARKETING_FEE_SIDE = ["super_admin", "owner", "finance", "finance_manager", "sales_manager",
  "marketing_admin", "dm_supervisor"];
const ADMIN_SIDE = ["super_admin", "owner"];
const uniq = (...lists) => [...new Set(lists.flat())];
// Site Plan dipakai penjualan (showroom, kunci unit) DAN proyek (peta kavling): satu item,
// bukan dua baris menu yang menuju halaman yang sama.
const SITEPLAN_SIDE = uniq(SALES_SIDE, PROJECT_SIDE);
// "Dokumen" kini juga rumah bagi PERIZINAN, jadi peran proyek & keuangan ikut melihatnya;
// tab di dalamnya menyesuaikan izin nyata (lihat `pages/DocumentsPage.js`).
const DOCS_SIDE = uniq(SALES_SIDE, PROJECT_SIDE, FINANCE_SIDE);
// Fase 43 — "Kampanye & Biaya Iklan" dilihat sisi marketing DAN sisi keuangan: yang membuat
// kampanye adalah marketing, tetapi yang harus mempertanggungjawabkan biayanya (dan
// membukukannya sebagai beban pemasaran) adalah keuangan.
const ADS_SIDE = uniq(OMNI_SIDE, FINANCE_SIDE);

export const NAV_STRUCTURE = [
  { type: "standalone", id: "home", label: "Beranda", icon: Home, path: "/", roles: ALL },
  {
    type: "group", groupId: "work", label: "Kerja", roles: ALL,
    items: [
      { id: "tasks", label: "Tugas & Papan Divisi", icon: ListChecks, path: "/tasks", roles: ALL,
        resource: "work_tasks" },
      { id: "notifications", label: "Notifikasi", icon: Bell, path: "/notifications", roles: ALL },
    ],
  },
  {
    type: "group", groupId: "crm", label: "CRM", roles: SALES_SIDE,
    items: [
      { id: "leads", label: "Pipeline Lead", icon: UserPlus, path: "/leads", roles: SALES_SIDE,
        resource: "leads" },
      { id: "appointments", label: "Agenda & Survey", icon: CalendarDays, path: "/appointments",
        roles: SALES_SIDE, resource: "appointments" },
      { id: "customers", label: "Customer & Kontrak", icon: Users2, path: "/customers",
        roles: SALES_SIDE, resource: "customers" },
      { id: "inbox", label: "Percakapan (WA)", icon: MessagesSquare, path: "/inbox",
        roles: SALES_SIDE, resource: "inbox" },
      // Fase 95/97 — antrean "Kontak WA → Lead" (/wa-capture) BUKAN pintu sidebar (anggaran 30 pintu,
      // gate verify_ia_v2): dibuka dari Inbox WhatsApp dan tombol "Capture dari WA" di Pipeline Lead.
      // Fase 42 — menu dibuka: master mitra + aturan fee + tagihan fee + atribusi + analitik.
      // "Marketing Fee" tidak lagi menjadi baris sidebar sendiri; ia hidup sebagai tab
      // "Tagihan Fee" di dalam hub ini (rute /marketing-fee tetap ada sebagai alias).
      { id: "partners", label: "Mitra & Fee", icon: Handshake, path: "/partners",
        roles: uniq(SALES_SIDE, MARKETING_FEE_SIDE), resource: "partners" },
    ],
  },
  {
    // Fase 43: grup ini kini juga dilihat sisi KEUANGAN untuk item "Kampanye & Biaya Iklan" —
    // biaya iklan adalah beban pemasaran yang mereka bukukan, jadi memberi izin `ads:view`
    // tanpa memberi pintu masuknya sama dengan izin yang tidak pernah bisa dipakai.
    type: "group", groupId: "marketing", label: "Marketing", roles: ADS_SIDE,
    items: [
      { id: "automation", label: "Automasi & Channel", icon: Workflow, path: "/automation",
        roles: OMNI_SIDE, resource: "automation_rules" },
      { id: "campaigns", label: "Kampanye & Biaya Iklan", icon: Megaphone, path: "/campaigns",
        roles: ADS_SIDE, resource: "ads" },
      { id: "attribution", label: "Atribusi & CAPI", icon: Target, path: "/attribution",
        roles: OMNI_SIDE, resource: "ads" },
    ],
  },
  {
    type: "group", groupId: "project", label: "Proyek", roles: SITEPLAN_SIDE,
    items: [
      { id: "projects", label: "Master Proyek", icon: Building2, path: "/projects",
        roles: PROJECT_SIDE, resource: "projects" },
      { id: "build", label: "Pembangunan", icon: HardHat, path: "/build", roles: PROJECT_SIDE,
        resource: "construction" },
      { id: "materials", label: "Material & Opname", icon: Boxes, path: "/materials",
        roles: PROJECT_SIDE, resource: "materials" },
      { id: "site-plan", label: "Site Plan", icon: MapIcon, path: "/site-plan",
        roles: SITEPLAN_SIDE },
    ],
  },
  {
    type: "group", groupId: "procurement", label: "Pengadaan", roles: PROCUREMENT_SIDE,
    items: [
      { id: "boq", label: "RAB / BoQ", icon: Calculator, path: "/boq", roles: PROCUREMENT_SIDE,
        resource: "boq" },
      { id: "subcon", label: "Subkontraktor & SPK", icon: Wrench, path: "/subcon",
        roles: PROCUREMENT_SIDE, resource: "subcon" },
      { id: "procurement", label: "Pengadaan & Vendor", icon: ShoppingCart, path: "/procurement",
        roles: PROCUREMENT_SIDE, resource: "procurement" },
    ],
  },
  {
    type: "group", groupId: "finance", label: "Keuangan", roles: ALL,
    items: [
      { id: "finance", label: "AR / AP / Komisi", icon: Wallet, path: "/finance",
        roles: FINANCE_SIDE, resource: "finance" },
      { id: "petty-cash", label: "Kas Bon", icon: Coins, path: "/petty-cash", roles: ALL,
        resource: "petty_cash" },
      { id: "cash-bank", label: "Kas & Bank", icon: Landmark, path: "/cash-bank", roles: FINANCE_SIDE,
        resource: "bank" },
    ],
  },
  {
    type: "group", groupId: "accounting", label: "Akuntansi", roles: FINANCE_SIDE,
    items: [
      { id: "accounting", label: "Buku Besar & Jurnal", icon: BookOpen, path: "/accounting",
        roles: FINANCE_SIDE, resource: "gl" },
      { id: "accounting-reports", label: "Laporan Keuangan", icon: Scale,
        path: "/accounting/reports", roles: FINANCE_SIDE, resource: "gl" },
      { id: "fixed-assets", label: "Aset Tetap", icon: Building, path: "/fixed-assets",
        roles: FINANCE_SIDE, resource: "fixed_assets" },
      { id: "corp-financing", label: "Pembiayaan Korporat", icon: Banknote,
        path: "/corporate-financing", roles: FINANCE_SIDE, resource: "loans" },
      { id: "tax", label: "Perpajakan", icon: Landmark, path: "/tax", roles: FINANCE_SIDE,
        resource: "tax" },
    ],
  },
  {
    type: "group", groupId: "service", label: "Layanan", roles: SALES_SIDE,
    items: [
      { id: "complaints", label: "Komplain & CS", icon: Headset, path: "/complaints",
        roles: SALES_SIDE, resource: "complaints" },
    ],
  },
  {
    type: "group", groupId: "docs", label: "Dokumen", roles: DOCS_SIDE,
    items: [
      { id: "documents", label: "Dokumen & Perizinan", icon: FileText, path: "/documents",
        roles: DOCS_SIDE, resource: "documents" },
    ],
  },
  {
    type: "group", groupId: "analytics", label: "Analitik & BI", roles: ALL,
    items: [
      // Fase 44: DIBUKA. Lima dashboard persona + kamus metrik, semuanya dihitung dari data
      // operasional yang sama (lapisan `backend/metrics`), dengan aturan kejujuran angka:
      // metrik yang datanya belum ada menulis "belum ada data", tidak pernah 0.
      { id: "bi", label: "Analitik & BI", icon: BarChart3, path: "/bi", roles: ALL,
        resource: "analytics" },
    ],
  },
  {
    type: "group", groupId: "config", label: "Konfigurasi", roles: LEGAL_SIDE,
    items: [
      { id: "config-center", label: "Pusat Konfigurasi", icon: SlidersHorizontal,
        path: "/config", roles: ADMIN_SIDE },
      { id: "legal", label: "Legal & Privasi", icon: Scale, path: "/legal", roles: LEGAL_SIDE,
        resource: "legal" },
    ],
  },
  {
    type: "group", groupId: "admin", label: "Admin", roles: ALL,
    items: [
      { id: "admin-orgs", label: "Organisasi", icon: Building2, path: "/admin/organizations", roles: ADMIN_SIDE },
      // Pengguna: tampil untuk peran mana pun yang diberi izin `users` di Hak Akses.
      { id: "admin-users", label: "Pengguna", icon: Users2, path: "/admin/users", roles: ALL,
        resource: "users" },
      { id: "admin-perms", label: "Hak Akses", icon: ShieldCheck, path: "/admin/permissions", roles: ADMIN_SIDE },
      { id: "admin-master", label: "Master Data", icon: Database, path: "/admin/master-data", roles: ADMIN_SIDE },
      { id: "admin-audit", label: "Jejak Audit", icon: History, path: "/admin/audit", roles: ADMIN_SIDE },
      { id: "admin-datamgmt", label: "Manajemen Data", icon: DatabaseBackup, path: "/admin/data-management", roles: ADMIN_SIDE },
    ],
  },
];

/**
 * buildNavGroups(role, can) — grup + item yang boleh dilihat peran ini.
 *
 * Fase RBAC-nav: bila `can` (dari `useAuth`) diberikan, item yang punya `resource` juga
 * diperiksa terhadap izin EFEKTIF (`can(resource, "view")`). Dengan ini pencabutan izin di
 * layar Hak Akses benar-benar MENYEMBUNYIKAN menunya, bukan hanya membuat halamannya 403.
 * Tanpa `can` (mis. audit gate) perilaku lama berbasis peran tetap berlaku.
 *
 * Item "Segera Hadir" TETAP DI GRUP ASALNYA (tidak lagi dikumpulkan ke satu grup di dasar
 * sidebar). Alasannya UX: pemakai perlu tahu DI MANA fitur itu akan muncul ("Kampanye ada
 * di Marketing"), dan grup asalnya adalah satu-satunya tempat yang menjawab itu. Grup yang
 * seluruh isinya belum jadi tetap ditampilkan supaya peta jalannya jujur.
 */
export function buildNavGroups(role, can = null) {
  // Peran kustom tanpa induk (`nav_role` null) tidak ada di daftar `roles` mana pun:
  // menunya murni mengikuti izin efektif (`can`) — item tanpa `resource` tidak tampil.
  const custom = !!can && !ALL.includes(role);
  const roleOk = (it) => it.roles.includes(role) || (custom && !!it.resource);
  const visible = (it) => roleOk(it)
    && (!can || !it.resource || can(it.resource, it.action || "view"));
  const result = [];
  for (const entry of NAV_STRUCTURE) {
    if (!entry.roles.includes(role) && !custom) continue;
    if (entry.type === "standalone") {
      if (visible(entry)) result.push(entry);
      continue;
    }
    const roleItems = entry.items.filter(visible);
    if (roleItems.length) result.push({ ...entry, items: roleItems });
  }
  return result;
}

/**
 * comingSoonItems(role) — menu yang BENAR-BENAR dirender terkunci (`comingSoon: true`).
 *
 * Fase 52: satu-satunya sumber kebenaran untuk pertanyaan "menu apa yang belum dibangun".
 * Sebelum ini dialog "Peta Menu" menyimpan daftarnya SENDIRI (ditulis tangan, lengkap dengan
 * nomor fase) sehingga tiga menu yang sudah hidup — Kampanye & Biaya Iklan, Atribusi & CAPI,
 * dan Analitik & BI — masih diumumkan "belum dibangun & terkunci" kepada super admin. Peta
 * yang berbohong itu lebih berbahaya daripada tidak ada peta: pemiliknya menyimpulkan ada
 * fitur yang tidak bisa ia akses padahal menunya ada di sidebarnya dan berisi data.
 *
 * Karena diderivasi, daftar ini ikut berubah sendiri saat sebuah item diberi `path` dan
 * atribut `comingSoon`-nya dilepas. Tidak ada nomor fase: yang ditulis adalah `note`
 * (nama pekerjaannya), sesuai aturan yang sama pada `soon` di `TabPage`.
 */
export function comingSoonItems(role = null) {
  const out = [];
  for (const entry of NAV_STRUCTURE) {
    if (entry.type !== "group" || !Array.isArray(entry.items)) continue;
    if (role && !entry.roles.includes(role)) continue;
    for (const it of entry.items) {
      if (!it.comingSoon) continue;
      if (role && !it.roles.includes(role)) continue;
      out.push({ label: it.label, where: entry.label, note: it.note || null });
    }
  }
  return out;
}

/** Jumlah baris menu yang benar-benar bisa diklik untuk satu peran (dipakai gate IA V2). */
export function countNavItems(role) {
  return buildNavGroups(role).reduce((n, g) => n
    + (g.type === "standalone" ? 1 : g.items.filter((it) => !it.comingSoon).length), 0);
}

export const ROLE_HOME_REGISTRY = {
  super_admin: { path: "/", label: "Control Tower" },
  owner: { path: "/", label: "Control Tower" },
  sales_manager: { path: "/", label: "Performa Tim" },
  marketing_admin: { path: "/", label: "Performa Tim" },
  sales: { path: "/", label: "Hari Saya" },
  finance: { path: "/", label: "Keuangan" },
  project_manager: { path: "/", label: "Proyek" },
  site_engineer: { path: "/", label: "Proyek" },
  legal_admin: { path: "/legal", label: "Legal & Privasi" },
};

export const ICONS = { ClipboardCheck };
