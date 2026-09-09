// buildUi — pemetaan NADA WARNA (bukan label) untuk jadwal pembangunan Fase 31.
// Label enum SELALU diambil dari SSOT `/api/reference` lewat StatusPill/RefLabel,
// sehingga tidak ada kamus label ganda di frontend.

export const ITEM_TONE = {
  blocked: "draft",
  ready: "open",
  in_progress: "in_progress",
  submitted: "submitted",
  rework: "rejected",
  done: "completed",
};

export const SCHEDULE_TONE = {
  not_started: "not_started",
  in_progress: "in_progress",
  at_risk: "overdue",
  on_hold: "snoozed",
  done: "completed",
};

/** Selisih hari (positif = terlambat) antara tanggal rencana dan hari ini. */
export function daysLate(planned) {
  if (!planned) return 0;
  const a = new Date(`${String(planned).slice(0, 10)}T00:00:00`);
  const b = new Date();
  b.setHours(0, 0, 0, 0);
  return Math.max(0, Math.round((b - a) / 86400000));
}

/** Tanggal pendek untuk kartu jadwal: 12 Agu 2026. */
export function shortDate(value) {
  if (!value) return "-";
  const d = new Date(`${String(value).slice(0, 10)}T00:00:00`);
  if (Number.isNaN(d.getTime())) return String(value).slice(0, 10);
  return d.toLocaleDateString("id-ID", { day: "numeric", month: "short", year: "numeric" });
}

/** Warna bar progres dibanding rencana (hijau = sesuai, merah = tertinggal jauh). */
export function deviationTone(deviation = 0) {
  if (deviation <= -10) return "text-rose-700";
  if (deviation < 0) return "text-amber-700";
  return "text-emerald-700";
}

/** Ringkasan checklist: berapa item kritis dan berapa yang sudah lulus. */
export function checklistStat(item) {
  const rows = item?.checklist || [];
  return {
    total: rows.length,
    critical: rows.filter((c) => c.critical).length,
    passed: rows.filter((c) => c.result === "pass").length,
  };
}
