import React from "react";
import { CheckCircle2, Flag, Layers, Wrench } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import EmptyState from "@/components/patterns/EmptyState";
import RefLabel from "@/components/patterns/RefLabel";
import {
  changeText, dayRange, lateTone, stamp, targetFromTemplateStep,
} from "@/utils/calibrationUi";
import { CALIB } from "@/constants/testIds";

/**
 * SELURUH LANGKAH TEMPLATE dalam satu layar (Fase 37).
 *
 * Tabel telat hanya memuat langkah yang SUDAH terbukti telat. Perencana tetap perlu bisa
 * mengalibrasi langkah lain (mis. waktu tunggu curing yang belum pernah masuk rencana)
 * tanpa pindah layar dan tanpa mengetik ulang seluruh template. Angka di sini adalah angka
 * template yang berlaku SEKARANG, langsung dari backend — bukan salinan yang bisa basi.
 */
export default function CalibrationTemplatePanel({
  templates, selectedId, onSelect, canCalibrate, onCalibrate,
}) {
  const list = templates || [];
  const tpl = list.find((t) => t.id === selectedId) || list[0] || null;

  if (!list.length) {
    return (
      <div data-testid={CALIB.tplEmpty}>
        <EmptyState icon={Layers} title="Belum ada template jadwal"
          description="Kalibrasi bekerja di atas template jadwal pembangunan. Buat template lebih dulu di Progres & Mutu → Template Jadwal." />
      </div>
    );
  }

  return (
    <div data-testid={CALIB.tplPanel} className="space-y-3 rounded-xl border bg-card p-3 shadow-sm">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="space-y-1.5">
          <p className="text-[11px] font-medium text-muted-foreground">Template jadwal</p>
          <Select value={tpl?.id || ""} onValueChange={onSelect}>
            <SelectTrigger data-testid={CALIB.tplSelect} className="w-full sm:w-96"
              aria-label="Template jadwal yang dikalibrasi"
              title={tpl ? `${tpl.code} — ${tpl.name} (v${tpl.version})` : undefined}>
              <SelectValue placeholder="Pilih template…" />
            </SelectTrigger>
            <SelectContent>
              {list.map((t) => (
                <SelectItem key={t.id} value={t.id}>
                  {t.code} — {t.name} (v{t.version})
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        {tpl ? (
          <div data-testid={CALIB.tplMeta} className="text-[11px] text-muted-foreground">
            <p>
              <b className="text-foreground">{tpl.steps_count} langkah</b> · total{" "}
              <b className="text-foreground">{tpl.total_days} hari kerja</b> ·{" "}
              {tpl.work_days_per_week} hari kerja/minggu
            </p>
            <p>
              tipe unit: {(tpl.unit_types || []).join(", ") || "semua tipe"} ·{" "}
              {tpl.calibrated_steps} langkah berkalibrasi aktif · {tpl.late_steps} langkah
              punya bukti telat
            </p>
            <p>
              {tpl.last_calibrated_at
                ? `terakhir dikalibrasi ${stamp(tpl.last_calibrated_at)} oleh ${tpl.last_calibrated_by}`
                : "template ini belum pernah dikalibrasi"}
            </p>
          </div>
        ) : null}
      </div>

      <div className="overflow-x-auto rounded-lg border bg-card shadow-[var(--shadow-card)]">
        <table className="w-full text-xs">
          <thead className="bg-secondary text-left">
            <tr>
              {["Mg", "Langkah", "Rencana", "Durasi", "Waktu tunggu", "Bobot", "Bukti telat",
                "Kalibrasi", ""].map((h, i) => (
                  <th key={`${h}-${i}`} className="whitespace-nowrap px-2.5 py-2 font-semibold">
                    {h}
                  </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {(tpl?.steps || []).map((s) => (
              <tr key={s.code} data-testid={CALIB.tplRow} data-step={s.code}
                className={`border-t align-top ${s.applied ? "bg-emerald-50/50" : ""}`}>
                <td className="px-2.5 py-2 tabular-nums text-muted-foreground">M{s.week}</td>
                <td className="px-2.5 py-2">
                  <span className="font-mono font-semibold">{s.code}</span>
                  <span className="ml-1.5">{s.name}</span>
                  {s.hold_point ? (
                    <span className="ml-1.5 rounded-full border border-rose-200 bg-rose-50 px-1.5 py-0.5 text-[10px] font-medium text-rose-800">
                      <Flag className="mr-0.5 inline h-2.5 w-2.5" />hold point
                    </span>
                  ) : null}
                </td>
                <td className="whitespace-nowrap px-2.5 py-2 tabular-nums">{dayRange(s)}</td>
                <td className="whitespace-nowrap px-2.5 py-2 font-medium tabular-nums">
                  {s.duration} hari
                </td>
                <td className="px-2.5 py-2 tabular-nums">
                  {s.wait_days ? (
                    <span title={s.wait_reason || ""}>{s.wait_days} hari</span>
                  ) : <span className="text-muted-foreground">—</span>}
                </td>
                <td className="px-2.5 py-2 tabular-nums text-muted-foreground">{s.weight}</td>
                <td className="px-2.5 py-2">
                  {s.late ? (
                    <span className={`font-medium tabular-nums ${lateTone(s.late.late_rate)}`}>
                      {s.late.units_late}/{s.late.units_total} telat · {s.late.avg_days} hari
                    </span>
                  ) : <span className="text-muted-foreground">—</span>}
                </td>
                <td className="px-2.5 py-2">
                  {s.applied ? (
                    <span data-testid={CALIB.tplApplied} data-step={s.code}
                      className="inline-block rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-[11px] font-medium text-emerald-800">
                      <CheckCircle2 className="mr-1 inline h-3 w-3" />
                      <RefLabel group="calibration_kind" value={s.applied.kind} />{" "}
                      {changeText(s.applied)} · {stamp(s.applied.at)}
                    </span>
                  ) : <span className="text-muted-foreground">belum</span>}
                </td>
                <td className="px-2.5 py-2 text-right">
                  <Button size="sm" variant="outline" className="h-7 px-2 text-[11px]"
                    data-testid={CALIB.tplCalibrate} data-step={s.code}
                    disabled={!canCalibrate}
                    onClick={() => onCalibrate(targetFromTemplateStep(tpl, s), "step_duration",
                      0, "daftar_template")}>
                    <Wrench className="mr-1 h-3 w-3" /> Kalibrasi
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-[11px] text-muted-foreground">
        Bobot, checklist, dan penugasan langkah tidak diubah oleh kalibrasi — yang berubah
        hanya durasi/waktu tunggu beserta pergeseran langkah setelahnya. Untuk mengubah isi
        pekerjaan (checklist, foto minimal, hold point), pakai Template Jadwal.
      </p>
    </div>
  );
}
