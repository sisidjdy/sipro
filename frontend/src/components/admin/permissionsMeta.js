// Konstanta tampilan layar Hak Akses (SSOT label aksi: backend/rbac_labels.ACTION_META).
export const ACTION_LABEL = {
  all: "Semua aksi", manage: "Kelola penuh", view: "Lihat", view_all: "Lihat semua",
  view_own: "Lihat milik sendiri", create: "Buat", update: "Ubah", delete: "Hapus",
  approve: "Setujui", assign: "Tugaskan", sign: "Tanda tangan", verify: "Verifikasi",
  override: "Terobos aturan", cancel: "Batalkan",
};
export const WEIGHT_CLS = { 1: "border-slate-200 bg-secondary", 2: "border-sky-200 bg-sky-50 text-sky-900", 3: "border-rose-200 bg-rose-50 text-rose-900" };

export const SOURCE_BADGE = {
  matrix: { text: "matriks", cls: "border-slate-300 bg-slate-100 text-slate-700" },
  inherited: { text: "warisan", cls: "border-violet-300 bg-violet-50 text-violet-700" },
  granted: { text: "dari kode", cls: "border-sky-300 bg-sky-50 text-sky-700" },
  full_access: { text: "akses penuh", cls: "border-emerald-300 bg-emerald-50 text-emerald-700" },
  revoked: { text: "dicabut admin", cls: "border-rose-300 bg-rose-50 text-rose-700" },
};

export const sortActions = (list) => [...new Set(list)].sort();
export const sameSet = (a, b) => sortActions(a || []).join("|") === sortActions(b || []).join("|");
