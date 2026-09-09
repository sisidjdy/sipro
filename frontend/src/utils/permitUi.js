// permitUi — pemetaan NADA WARNA + kalimat untuk kesehatan izin & kesiapan mulai bangun
// (Fase 46). Label enum SELALU dari SSOT `/api/reference` lewat StatusPill/RefLabel; di sini
// hanya nada warna (memakai kelas pill yang SUDAH ada, jadi tidak ada CSS baru) dan kalimat
// penjelas yang tidak boleh berbohong saat datanya belum ada.

/** kesehatan izin → tone pill yang sudah ada di index.css */
export const HEALTH_TONE = {
  ok: "approved",
  expiring: "due-today",
  expired: "overdue",
  in_process: "submitted",
  rejected: "rejected",
  missing: "draft",
};

/** kesiapan mulai bangun → tone pill */
export const READINESS_TONE = {
  ready: "approved",
  warning: "due-today",
  blocked: "overdue",
  started: "in_progress",
};

export const SEVERITY_TONE = {
  blocker: "border-rose-200 bg-rose-50 text-rose-900",
  warning: "border-amber-200 bg-amber-50 text-amber-900",
  info: "border-sky-200 bg-sky-50 text-sky-900",
};

/**
 * Kalimat masa berlaku izin. JUJUR: izin tanpa tanggal berlaku tidak ditulis "aman",
 * melainkan "masa berlaku belum dicatat" — itu informasi yang harus dilengkapi admin.
 */
export function expiryText(permit) {
  if (!permit) return "belum ada data";
  if (!permit.expiry_known && !permit.expiry_at) return "masa berlaku belum dicatat";
  const day = String(permit.expiry_at || "").slice(0, 10);
  const left = permit.days_to_expiry;
  if (left === null || left === undefined) return day;
  if (left < 0) return `${day} · kedaluwarsa ${Math.abs(left)} hari lalu`;
  if (left === 0) return `${day} · berakhir hari ini`;
  return `${day} · sisa ${left} hari`;
}

/** Persen yang boleh digambar — null/undefined ditulis "belum ada data", bukan 0%. */
export function pctText(value, suffix = "%") {
  if (value === null || value === undefined) return "belum ada data";
  return `${value}${suffix}`;
}

/** Deviasi rencana vs realisasi: tanda + nada warna, tanpa mengarang nol. */
export function deviationText(value) {
  if (value === null || value === undefined) return "belum ada data";
  return `${value > 0 ? "+" : ""}${value}%`;
}

export function deviationClass(value) {
  if (value === null || value === undefined) return "text-muted-foreground";
  if (value <= -10) return "text-rose-700";
  if (value < 0) return "text-amber-700";
  return "text-emerald-700";
}

/** Ringkasan alasan gerbang untuk baris tabel (maks 2, sisanya dihitung). */
export function reasonSummary(codes = [], labelOf) {
  if (!codes.length) return "";
  const names = codes.slice(0, 2).map((c) => labelOf("build_gate_code", c) || c);
  const more = codes.length - names.length;
  return names.join(" · ") + (more > 0 ? ` +${more} lain` : "");
}
