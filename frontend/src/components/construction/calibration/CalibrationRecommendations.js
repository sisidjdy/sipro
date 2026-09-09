import React from "react";
import { CheckCircle2, Lightbulb, RotateCcw, Wrench } from "lucide-react";

import { Button } from "@/components/ui/button";
import EmptyState from "@/components/patterns/EmptyState";
import RefLabel from "@/components/patterns/RefLabel";
import { KIND_TONE, changeText, stamp, targetFromDelayRow } from "@/utils/calibrationUi";
import { CALIB } from "@/constants/testIds";

/**
 * USULAN KALIBRASI (Fase 37) — rekomendasi Analitik Telat yang bisa dieksekusi di tempat.
 *
 * Setiap usulan membawa target template + angka template saat ini dari backend, jadi tidak
 * ada angka yang diketik ulang di UI dan tidak ada tafsir baru di frontend. Usulan yang
 * SUDAH dikalibrasi ditandai, bukan disuruh dikerjakan dua kali; tandanya hilang lagi bila
 * kalibrasinya dibatalkan.
 */
export default function CalibrationRecommendations({ recs, canCalibrate, onCalibrate, onUndo }) {
  const rows = recs || [];
  if (!rows.length) {
    return (
      <div data-testid={CALIB.recEmpty}>
        <EmptyState icon={Lightbulb} title="Belum ada usulan kalibrasi"
          description="Usulan muncul otomatis begitu ada pekerjaan yang berulang kali telat atau punya waktu tunggu wajib yang belum masuk tanggal rencana. Selama tidak ada bukti telat, template dianggap masih realistis." />
      </div>
    );
  }

  return (
    <div data-testid={CALIB.recPanel} className="space-y-2.5">
      {rows.map((r, i) => (
        <div key={`${r.kind}-${r.step_code || r.assigned_to || r.unit_type || i}`}
          data-testid={CALIB.recCard} data-kind={r.kind}
          className="rounded-xl border bg-card p-3 shadow-sm">
          <div className="flex flex-wrap items-start justify-between gap-2">
            <div className="min-w-0">
              <p className="text-sm font-semibold">{r.title}</p>
              <p className="mt-0.5 text-xs text-muted-foreground">{r.detail}</p>
            </div>
            {r.calibration ? (
              <span className={`shrink-0 rounded-full border px-2 py-0.5 text-[11px] font-medium
                ${KIND_TONE[r.calibration.kind] || "border-slate-200 bg-slate-50 text-slate-800"}`}>
                <RefLabel group="calibration_kind" value={r.calibration.kind} />
              </span>
            ) : null}
          </div>

          {!r.calibration ? (
            <p className="mt-2 rounded-lg border bg-secondary p-2 text-[11px] text-muted-foreground">
              {r.action} — ini bukan soal angka template, jadi tidak bisa (dan tidak boleh)
              diselesaikan dengan mengubah durasi.
            </p>
          ) : (
            <div className="mt-2 space-y-1.5">
              {(r.targets || []).map((t) => (
                <div key={t.template_id}
                  className="flex flex-wrap items-center justify-between gap-2 rounded-lg border bg-background p-2.5 text-xs">
                  <div className="min-w-0">
                    <p className="font-medium">
                      <span className="font-mono">{t.template_code}</span>{" "}
                      <span className="text-muted-foreground">{t.template_name}</span>
                    </p>
                    <p className="text-[11px] text-muted-foreground">
                      Sekarang: {t.current?.duration} hari kerja (hari {t.current?.day_from}–
                      {t.current?.day_to})
                      {t.current?.wait_days ? ` · tunggu ${t.current.wait_days} hari` : ""}
                      {" · "}versi {t.version}
                    </p>
                  </div>
                  {t.applied ? (
                    <div data-testid={CALIB.recApplied} className="flex items-center gap-2">
                      <span className="rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-[11px] font-medium text-emerald-800">
                        <CheckCircle2 className="mr-1 inline h-3 w-3" />
                        sudah diterapkan {changeText(t.applied)} · {stamp(t.applied.at)}
                      </span>
                      {canCalibrate ? (
                        <Button size="sm" variant="ghost" data-testid={CALIB.recUndo}
                          onClick={() => onUndo(t.applied)}>
                          <RotateCcw className="mr-1 h-3.5 w-3.5" /> Batalkan
                        </Button>
                      ) : null}
                    </div>
                  ) : (
                    <Button size="sm" data-testid={CALIB.recApply} data-template={t.template_code}
                      disabled={!canCalibrate}
                      onClick={() => onCalibrate(
                        targetFromDelayRow({ step_code: r.calibration.step_code, name: t.current?.name },
                          t),
                        r.calibration.kind, r.calibration.delta_days, "rekomendasi")}>
                      <Wrench className="mr-1 h-3.5 w-3.5" />
                      {canCalibrate ? "Pratinjau & terapkan" : "Hanya bisa dilihat"}
                    </Button>
                  )}
                </div>
              ))}
              {!(r.targets || []).length ? (
                <p className="rounded-lg border border-amber-200 bg-amber-50 p-2 text-[11px] text-amber-900">
                  Langkah <b>{r.calibration.step_code}</b> tidak ditemukan pada template
                  {" "}{(r.templates || []).join(", ") || "terkait"} — mungkin kodenya sudah
                  berubah. Periksa daftar langkah template di bawah.
                </p>
              ) : null}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
