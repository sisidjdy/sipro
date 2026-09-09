import React from "react";
import { CheckCircle2, TrendingDown, Wrench } from "lucide-react";

import { Button } from "@/components/ui/button";
import EmptyState from "@/components/patterns/EmptyState";
import RefLabel from "@/components/patterns/RefLabel";
import { changeText, lateTone, targetFromDelayRow } from "@/utils/calibrationUi";
import { CALIB } from "@/constants/testIds";

/**
 * BUKTI TELAT PER LANGKAH — tabel yang sama dengan Analitik Telat (Fase 32), tetapi setiap
 * barisnya bisa langsung dikalibrasi. Inilah inti Fase 37: bukti dan tombol perbaikannya
 * berada pada baris yang sama, sehingga kalibrasi tidak lagi "nanti kalau ingat".
 */
export default function CalibrationStepTable({ steps, canCalibrate, onCalibrate }) {
  const rows = steps || [];
  if (!rows.length) {
    return (
      <div data-testid={CALIB.stepEmpty}>
        <EmptyState icon={TrendingDown} title="Belum ada langkah yang tercatat telat"
          description="Semua pekerjaan masih dalam rencana, jadi tidak ada bukti yang menuntut template dikalibrasi. Tabel ini terisi sendiri begitu ada pekerjaan lewat tenggat." />
      </div>
    );
  }

  return (
    <div data-testid={CALIB.stepPanel} className="overflow-x-auto rounded-xl border bg-card shadow-[var(--shadow-card)]">
      <table className="w-full text-xs">
        <thead className="bg-secondary text-left">
          <tr>
            {["Langkah", "Minggu", "Rumah telat", "Rata-rata", "Maks", "Rasio",
              "Durasi template", "Penyebab dominan", "Kalibrasi"].map((h) => (
                <th key={h} className="whitespace-nowrap px-2.5 py-2 font-semibold">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.step_code} data-testid={CALIB.stepRow} data-step={r.step_code}
              className="border-t align-top">
              <td className="px-2.5 py-2">
                <span className="font-mono font-semibold">{r.step_code}</span>
                <span className="ml-1.5 text-muted-foreground">{r.name}</span>
                {(r.unit_codes || []).length ? (
                  <p className="text-[11px] text-muted-foreground">
                    unit: {(r.unit_codes || []).join(", ")}
                  </p>
                ) : null}
              </td>
              <td className="px-2.5 py-2 tabular-nums">M{r.week}</td>
              <td className="px-2.5 py-2 font-semibold tabular-nums text-rose-700">
                {r.units_late}/{r.units_total}
              </td>
              <td className="px-2.5 py-2 tabular-nums">{r.avg_days} hari</td>
              <td className="px-2.5 py-2 tabular-nums">{r.max_days} hari</td>
              <td className={`px-2.5 py-2 font-semibold tabular-nums ${lateTone(r.late_rate)}`}>
                {r.late_rate}%
              </td>
              <td className="px-2.5 py-2 tabular-nums text-muted-foreground">
                {r.planned_days} hari{r.wait_days ? ` +${r.wait_days} tunggu` : ""}
              </td>
              <td className="px-2.5 py-2">
                {r.dominant_cause ? (
                  <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[11px] font-medium text-amber-900">
                    <RefLabel group="build_delay_cause" value={r.dominant_cause.cause} />
                    {" "}({r.dominant_cause.count})
                  </span>
                ) : <span className="text-muted-foreground">belum dijelaskan</span>}
              </td>
              <td className="px-2.5 py-2">
                <div className="flex flex-col gap-1.5">
                  {(r.targets || []).map((t) => (t.applied ? (
                    <span key={t.template_id} data-testid={CALIB.stepApplied}
                      data-template={t.template_code}
                      className="whitespace-nowrap rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-[11px] font-medium text-emerald-800">
                      <CheckCircle2 className="mr-1 inline h-3 w-3" />
                      {t.template_code} sudah {changeText(t.applied)}
                    </span>
                  ) : (
                    <Button key={t.template_id} size="sm" variant="outline"
                      className="h-7 whitespace-nowrap px-2 text-[11px]"
                      data-testid={CALIB.stepCalibrate} data-template={t.template_code}
                      disabled={!canCalibrate}
                      onClick={() => onCalibrate(targetFromDelayRow(r, t), "step_duration",
                        0, "tabel_telat")}>
                      <Wrench className="mr-1 h-3 w-3" /> {t.template_code}
                    </Button>
                  )))}
                  {!(r.targets || []).length ? (
                    <span className="text-[11px] text-muted-foreground">
                      langkah ini tidak ada di template mana pun
                    </span>
                  ) : null}
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
