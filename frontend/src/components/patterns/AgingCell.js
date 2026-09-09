import React from "react";
import { cn } from "@/lib/utils";
import { AGING } from "@/constants/testIds";
import { formatHours, SLA_STATE_LABEL, SLA_STATE_TONE } from "@/utils/agingFilter";

/**
 * AgingCell — dua angka umur yang menentukan urgensi (blueprint IA V2 §2.5):
 *   • **umur total** sejak objek masuk (mis. lead dibuat),
 *   • **umur tahap** sejak objek masuk tahap sekarang.
 *
 * FASE 41 — ambang SLA TIDAK LAGI ditulis di komponen. Dulu tanda tangan komponen ini
 * punya `slaHours = 72` sebagai bawaan dan setiap daftar mengirim angkanya sendiri
 * (48 / 168 / 336 / 720), sehingga kalimat "lewat SLA" di tabel adalah klaim tanpa dasar
 * kebijakan dan tidak bisa diubah tanpa deploy. Sekarang server mengirim `stage_sla_hours`
 * (ambang efektif dari Pusat Konfigurasi) dan `sla_state` (`ok|over|over2|none`) PADA SETIAP
 * BARIS; komponen hanya menampilkannya.
 *
 * Warna BUKAN satu-satunya penanda (aturan aksesibilitas + gate `verify_ui_surfaces`):
 * selalu ada teksnya ("dalam SLA" / "lewat SLA" / "lewat 2× SLA" / "tanpa SLA").
 */
export default function AgingCell({ ageHours, stageAgeHours, slaHours, state, className }) {
  const stage = stageAgeHours ?? ageHours;
  const sla = slaHours === 0 ? null : slaHours;
  // `state` dari server adalah sumber utama; turunan lokal hanya jaring pengaman untuk
  // endpoint yang belum mengirimkannya (agar sel tidak pernah kosong).
  const level = state || (!sla ? "none"
    : Number(stage) > sla * 2 ? "over2" : Number(stage) > sla ? "over" : "ok");
  const note = SLA_STATE_LABEL[level] || SLA_STATE_LABEL.none;
  const title = sla
    ? `Umur total ${formatHours(ageHours)} · umur tahap ${formatHours(stage)} · `
      + `SLA tahap ${formatHours(sla)} (Pusat Konfigurasi)`
    : `Umur total ${formatHours(ageHours)} · umur tahap ${formatHours(stage)} · `
      + "tahap akhir: tidak ada janji waktu";

  return (
    <div data-testid={AGING.cell} data-aging-level={level} data-sla-hours={sla ?? ""}
      title={title} className={cn("leading-tight", className)}>
      <span data-testid={AGING.total} className="block text-sm tabular-nums">
        {formatHours(ageHours)}
      </span>
      <span data-testid={AGING.stage}
        className={cn("block text-xs tabular-nums", SLA_STATE_TONE[level])}>
        tahap {formatHours(stage)} · {note}
      </span>
    </div>
  );
}
