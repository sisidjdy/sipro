// Fase 40 — IA & Design System V2. Registry testid untuk pola yang dipakai SEMUA daftar &
// halaman kanonik. Satu nama untuk satu maksud: penguji tidak perlu menghafal per halaman.
export const DT = {
  root: "data-table",
  search: "data-table-search",
  columns: "data-table-columns",
  columnOption: "data-table-column-option",
  export: "data-table-export",
  density: "data-table-density",
  refresh: "data-table-refresh",
  selectAll: "data-table-select-all",
  rowSelect: "data-table-row-select",
  row: "data-table-row",
  sort: "data-table-sort",
  bulkBar: "data-table-bulk",
  bulkClear: "data-table-bulk-clear",
  pagination: "data-table-pagination",
  total: "data-table-total",
};

export const FILTER = {
  bar: "filter-bar",
  trigger: "filter-trigger",
  option: "filter-option",
  text: "filter-text",
  from: "filter-from",
  to: "filter-to",
  chip: "filter-chip",
  chipClear: "filter-chip-clear",
  reset: "filter-reset",
  count: "filter-active-count",
};

export const TABPAGE = {
  root: "tab-page",
  tabs: "tab-page-tabs",
  tab: "tab-page-tab",
  panel: "tab-page-panel",
  soon: "tab-page-soon",
};

export const AGING = {
  cell: "aging-cell",
  total: "aging-total",
  stage: "aging-stage",
};

export const KPI = {
  card: "kpi-card",
  value: "kpi-card-value",
  drill: "kpi-card-drill",
};

export const TIMELINE = {
  feed: "timeline-feed",
  item: "timeline-item",
  actor: "timeline-actor",
  empty: "timeline-empty",
};

export const CHART = {
  frame: "chart-frame",
  title: "chart-frame-title",
  empty: "chart-frame-empty",
  download: "chart-frame-download",
};

// Fase 52 — keadaan SATU PANEL (bukan satu halaman). Dipakai setiap tab/panel yang datanya
// ditolak izin atau gagal dimuat, supaya penguji bisa membedakan tiga hal yang selama ini
// tertukar di layar: "tidak boleh dilihat", "belum ada data", dan "gagal dimuat".
export const PANELSTATE = {
  denied: "panel-denied",
  unavailable: "panel-unavailable",
  retry: "panel-retry-button",
  omitted: "panel-omitted-sources",
};

// Halaman kanonik (US-40-2): objek besar dibuka sebagai HALAMAN, bukan drawer.
export const LEADPROFILE = {
  page: "lead-profile-page",
  header: "lead-profile-header",
  waBtn: "lead-profile-wa",
  callBtn: "lead-profile-call",
  summary: "lead-profile-summary",
  nba: "lead-profile-nba",
  notFound: "lead-profile-not-found",
  // Fase 52 — spanduk jujur "sebagian panel tidak ditampilkan". Halaman TETAP HIDUP walau
  // satu panel samping ditolak 403; spanduk ini menyebut panel mana dan mengapa.
  partial: "lead-profile-partial",
};

export const CUSTPROFILE = {
  page: "customer-profile-page",
  header: "customer-profile-header",
  summary: "customer-profile-summary",
  notFound: "customer-profile-not-found",
  // Tab Timeline: dulu SELALU kosong karena hanya membaca `activities` ber-entity_type
  // "customer" — koleksi itu tidak pernah punya baris seperti itu. Sekarang jejaknya
  // dirangkai backend dari kwitansi, BAST, klaim garansi, komplain, dokumen, dan aktivitas
  // lead/unit miliknya; catatan sumber menyebut apa yang dipakai & apa yang belum ada.
  timelineSources: "customer-profile-timeline-sources",
  // Fase 52 — spanduk jujur yang sama untuk profil pelanggan.
  partial: "customer-profile-partial",
};

// Hub hasil peleburan menu (Fase 40c) — tetap satu halaman per objek, tab untuk konteks.
export const HUB = {
  build: "build-hub-page",
  crm: "crm-hub-page",
  docs: "documents-hub-page",
  navSoon: "nav-coming-soon",
  // Peta menu lama→baru yang bisa dibuka DARI DALAM aplikasi (US-40c-1): pemakai lama
  // tidak boleh harus membuka dokumentasi untuk menemukan fiturnya.
  navMapBtn: "nav-map-button",
  navMapDialog: "nav-map-dialog",
  navMapRow: "nav-map-row",
  navMapSearch: "nav-map-search",
  // Fase 52 — dua keadaan yang HARUS bisa dibedakan penguji pada dialog peta menu:
  // benar-benar ada menu terkunci (diderivasi dari navigationConfig) vs tidak ada satu pun.
  // Dulu kotak "BELUM DIBANGUN" selalu dirender dari daftar tangan yang sudah kedaluwarsa,
  // sehingga super admin diberi tahu tiga menu hidup itu "terkunci".
  navMapLocked: "nav-map-locked",
  navMapAllOpen: "nav-map-all-open",
};
