// calibrationUi — pembantu tampilan KALIBRASI TEMPLATE (Fase 37).
//
// Label enum SELALU dari SSOT `/api/reference` (lewat RefLabel/ReferenceSelect); di sini
// hanya nada warna, format angka/tanggal, dan aturan kecil yang dipakai bersama oleh
// beberapa panel supaya tidak ada dua tafsir angka yang sama di layar.

export const KIND_DEFAULT = "step_duration";

/** Jenis kalibrasi yang butuh angka hari dari pengguna. `wait_into_plan` menghitung
 *  sendiri kekurangan jeda dari template (pengguna tidak boleh mengarang angka). */
export const KINDS_WITH_DELTA = ["step_duration", "wait_time"];

export const KIND_TONE = {
  step_duration: "border-sky-200 bg-sky-50 text-sky-900",
  wait_time: "border-violet-200 bg-violet-50 text-violet-900",
  wait_into_plan: "border-amber-200 bg-amber-50 text-amber-900",
};

export function needsDelta(kind) {
  return KINDS_WITH_DELTA.includes(kind);
}

/** Penanda idempotensi: klik ganda / jaringan mengulang kirim tidak boleh jadi 2 kalibrasi. */
export function newClientRef() {
  return `ui37-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
}

export function dayRange(step) {
  if (!step) return "—";
  return `hari ${step.day_from}–${step.day_to}`;
}

export function durationDays(step) {
  if (!step) return 0;
  if (step.duration) return Number(step.duration);
  return Number(step.day_to || 0) - Number(step.day_from || 0) + 1;
}

export function durationText(step) {
  return `${durationDays(step)} hari kerja`;
}

export function waitText(step) {
  const w = Number(step?.wait_days || 0);
  return w ? `${w} hari tunggu` : "tanpa waktu tunggu";
}

/** Tanda + / − yang tidak ambigu (tanda minus tipografis, bukan hubung). */
export function deltaText(n) {
  const v = Number(n || 0);
  if (!v) return "0 hari";
  return v > 0 ? `+${v} hari` : `\u2212${Math.abs(v)} hari`;
}

/** Perubahan NYATA satu kalibrasi dalam satu frasa pendek.
 *
 * `deltaText` sendirian tidak cukup jujur: pada `wait_into_plan` pengguna tidak mengetik
 * jumlah hari (sistem menghitung kekurangan jeda), sehingga `delta_days` = 0 sementara
 * tanggal rencana benar-benar bergeser `shift_days` hari. Badge/riwayat yang hanya membaca
 * `delta_days` berbunyi "sudah diterapkan 0 hari" — perencana menyimpulkan tidak ada yang
 * berubah padahal template bergeser 3 hari. Angka pergeseran datang dari backend (tidak
 * dihitung di sini) supaya pratinjau, hasil, dan riwayat tetap satu suara.
 */
export function changeText(cal) {
  const d = Number(cal?.delta_days || 0);
  const s = Number(cal?.shift_days || 0);
  if (d) return deltaText(d);
  if (s) return `${deltaText(s)} (geser rencana)`;
  return "tanpa perubahan hari";
}

export function lateTone(rate = 0) {
  const r = Number(rate || 0);
  if (r >= 50) return "text-rose-700";
  if (r >= 25) return "text-amber-700";
  return "text-muted-foreground";
}

/** '2026-08-15T20:31:02+00:00' → '15-08-2026 20:31' (tanpa kamus bulan tambahan). */
export function stamp(iso) {
  const s = String(iso || "");
  if (s.length < 10) return s || "—";
  const d = `${s.slice(8, 10)}-${s.slice(5, 7)}-${s.slice(0, 4)}`;
  return s.length >= 16 ? `${d} ${s.slice(11, 16)}` : d;
}

/** Ringkasan satu baris pratinjau: sebelum → sesudah dalam bahasa yang sama di semua panel. */
export function rowShift(row) {
  const b = row?.before || {};
  const a = row?.after || {};
  const days = `hari ${b.day_from}–${b.day_to} → hari ${a.day_from}–${a.day_to}`;
  const wait = Number(b.wait_days || 0) !== Number(a.wait_days || 0)
    ? ` · tunggu ${b.wait_days} → ${a.wait_days} hari` : "";
  return days + wait;
}

/** Angka awal yang masuk akal untuk tiap jenis kalibrasi (boleh diubah pengguna).
 *
 * Sengaja KONSERVATIF: untuk durasi, angka usulan hanya dipakai bila datang dari mesin
 * rekomendasi (yang baru bicara setelah minimal 2 rumah telat). Bila perencana membuka
 * kalibrasi sendiri dari tabel/daftar langkah, bawaannya 1 hari — rata-rata telat satu
 * rumah bisa 22 hari dan itu bukan angka yang layak dipasang diam-diam sebagai bawaan.
 * Buktinya tetap ditampilkan di dialog supaya keputusannya sadar, bukan asal terima.
 */
export function suggestedDelta(kind, step, fromRec) {
  if (Number(fromRec)) return Number(fromRec);
  if (kind === "wait_time") return 1;
  if (kind === "step_duration") return 1;
  return 0;
}

/** Apakah rekomendasi ini punya target yang BELUM dikalibrasi (jadi masih perlu dikerjakan). */
export function recPending(rec) {
  if (!rec?.calibration) return false;
  return (rec.targets || []).some((t) => !t.applied);
}

export function countPending(recs) {
  return (recs || []).filter(recPending).length;
}

/** Semua langkah template yang punya kalibrasi aktif (dipakai kartu ringkasan). */
export function countCalibrated(templates) {
  return (templates || []).reduce((n, t) => n + Number(t.calibrated_steps || 0), 0);
}

/** Target kalibrasi dari satu baris langkah template (bentuk yang dipahami dialog). */
export function targetFromTemplateStep(tpl, step) {
  return {
    template_id: tpl.id,
    template_code: tpl.code,
    template_name: tpl.name,
    step_code: step.code,
    step_name: step.name,
    current: step,
    late: step.late || null,
    applied: step.applied || null,
  };
}

/** Target kalibrasi dari tabel langkah telat / kartu rekomendasi. */
export function targetFromDelayRow(row, t) {
  // Kartu rekomendasi tidak selalu membawa statistik telat (mis. usulan waktu tunggu
  // yang lahir dari template, bukan dari hitungan per rumah). Jangan menampilkan
  // "undefined/undefined rumah telat" — lebih baik jujur bahwa buktinya tidak dibawa.
  const hasLate = Number.isFinite(Number(row?.units_total));
  return {
    template_id: t.template_id,
    template_code: t.template_code,
    template_name: t.template_name,
    step_code: row.step_code,
    step_name: row.name || t.current?.name,
    current: t.current,
    late: hasLate ? {
      units_total: row.units_total, units_late: row.units_late,
      avg_days: row.avg_days, max_days: row.max_days, late_rate: row.late_rate,
      dominant_cause: row.dominant_cause, unit_codes: row.unit_codes,
    } : null,
    applied: t.applied || null,
  };
}
