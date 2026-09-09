// calendarUi — NADA WARNA & pembantu tampilan Kalender Jadwal (Fase 36).
// Label enum SELALU dari SSOT `/api/reference` (RefLabel/ReferenceSelect); di sini hanya
// pemetaan warna/ikon dan format tanggal supaya tidak ada kamus label ganda di frontend.

export const WEEKDAY_HEADER = ["Sen", "Sel", "Rab", "Kam", "Jum", "Sab", "Min"];

/** Warna titik/pil per jenis acara (bukan label — label dari SSOT). */
export const KIND_TONE = {
  work_deadline: "bg-sky-100 text-sky-900 border-sky-200",
  schedule_start: "bg-emerald-100 text-emerald-900 border-emerald-200",
  schedule_finish: "bg-indigo-100 text-indigo-900 border-indigo-200",
  inspection: "bg-violet-100 text-violet-900 border-violet-200",
  punch: "bg-amber-100 text-amber-900 border-amber-200",
  task: "bg-slate-100 text-slate-800 border-slate-200",
};

export const KIND_DOT = {
  work_deadline: "bg-sky-500",
  schedule_start: "bg-emerald-500",
  schedule_finish: "bg-indigo-500",
  inspection: "bg-violet-500",
  punch: "bg-amber-500",
  task: "bg-slate-400",
};

/** Latar sel kalender menurut jenis hari (libur/off dibedakan supaya terlihat jujur). */
export const DAY_TONE = {
  full: "bg-card",
  half: "bg-sky-50/60",
  off: "bg-secondary",
  holiday: "bg-rose-50",
};

export const CONFLICT_TONE = {
  overload: "border-amber-300 bg-amber-50 text-amber-900",
  critical_stack: "border-rose-300 bg-rose-50 text-rose-900",
  non_workday: "border-violet-300 bg-violet-50 text-violet-900",
};

const MONTHS = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus",
  "September", "Oktober", "November", "Desember"];

/** '2026-08' → 'Agustus 2026'. */
export function monthLabel(month) {
  const m = String(month || "");
  const idx = Number(m.slice(5, 7)) - 1;
  if (Number.isNaN(idx) || idx < 0 || idx > 11) return m;
  return `${MONTHS[idx]} ${m.slice(0, 4)}`;
}

/** '2026-08-17' → '17 Agustus 2026'. */
export function longDate(value) {
  const s = String(value || "").slice(0, 10);
  if (s.length !== 10) return s;
  const idx = Number(s.slice(5, 7)) - 1;
  return `${Number(s.slice(8, 10))} ${MONTHS[idx] || ""} ${s.slice(0, 4)}`;
}

/** Berapa sel kosong sebelum tanggal 1 (grid dimulai hari Senin). */
export function leadingBlanks(days) {
  if (!days || !days.length) return 0;
  return Number(days[0].weekday || 0);
}

/** Urutan jenis acara yang stabil untuk legenda & filter. */
export const KIND_ORDER = ["work_deadline", "schedule_start", "schedule_finish",
  "inspection", "punch", "task"];
