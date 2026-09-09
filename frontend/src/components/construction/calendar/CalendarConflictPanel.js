import React from "react";
import { AlertTriangle, ArrowRight, CalendarX2, ShieldCheck } from "lucide-react";

import { Button } from "@/components/ui/button";
import RefLabel from "@/components/patterns/RefLabel";
import { CONFLICT_TONE, longDate, monthLabel } from "@/utils/calendarUi";
import { CAL } from "@/constants/testIds";

/**
 * PANEL BENTROK — inti nilai Fase 36: masalah jadwal terlihat SEBELUM terjadi.
 *
 * Tiga jenis bentrok (pilihan owner): beban pelaksana menumpuk, pekerjaan kritis/hold point
 * bertabrakan, dan tenggat yang jatuh pada hari libur / bukan hari kerja. Setiap baris
 * menjelaskan dengan bahasa manusia + ambang yang dipakai, lalu menawarkan jalan keluar
 * (buka hari itu / geser jadwal lewat dialog Fase 34).
 *
 * Ditambah "pandangan ke depan": bentrok terbesar sering berada 1–2 bulan lagi, jadi
 * pengguna tidak perlu menebak bulan mana yang bermasalah.
 */
export default function CalendarConflictPanel({
  conflicts, summary, outlook, thresholds, canShift, onOpenDay, onShift, onJumpMonth,
}) {
  const rows = conflicts || [];
  const totals = (summary || {}).conflicts || {};

  return (
    <div data-testid={CAL.conflictPanel} className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="inline-flex items-center gap-1.5 font-heading text-sm font-semibold">
          <AlertTriangle className="h-4 w-4 text-amber-600" />
          Bentrok jadwal bulan ini
          <span className="rounded-full bg-secondary px-2 py-0.5 text-[11px] tabular-nums">
            {rows.length}
          </span>
        </h3>
        {thresholds ? (
          <p className="text-[11px] text-muted-foreground">
            Ambang: maks {thresholds.max_items_per_person_per_day} tenggat/pelaksana/hari ·{" "}
            maks {thresholds.max_critical_per_day} pekerjaan kritis/hari
          </p>
        ) : null}
      </div>

      {!rows.length ? (
        <div data-testid={CAL.conflictEmpty}
          className="rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-900">
          <p className="inline-flex items-center gap-1.5 font-medium">
            <ShieldCheck className="h-4 w-4" /> Tidak ada bentrok pada bulan ini
          </p>
          <p className="mt-0.5 text-xs">
            Beban pelaksana masih di bawah ambang, tidak ada tumpukan pekerjaan kritis, dan
            tidak ada tenggat yang mendarat di hari libur.
          </p>
        </div>
      ) : (
        <div className="space-y-2">
          {rows.map((c, i) => (
            <div key={`${c.kind}-${c.date}-${i}`} data-testid={CAL.conflictRow}
              data-kind={c.kind} data-date={c.date}
              className={`rounded-xl border p-3 ${CONFLICT_TONE[c.kind] || "bg-card"}`}>
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="text-xs font-semibold">
                    <RefLabel group="calendar_conflict_kind" value={c.kind} />
                    <span className="ml-1.5 font-normal">· {longDate(c.date)}</span>
                    {c.severity ? (
                      <span className="ml-1.5 rounded-full border bg-background/70 px-1.5 py-0.5 text-[10px]">
                        <RefLabel group="priority" value={c.severity} />
                      </span>
                    ) : null}
                  </p>
                  <p className="mt-1 text-xs">{c.detail}</p>
                  {(c.unit_codes || []).length ? (
                    <p className="mt-1 text-[11px] opacity-80">
                      Unit: {c.unit_codes.join(", ")}
                    </p>
                  ) : null}
                  {c.suggested_date ? (
                    <p className="mt-1 inline-flex items-center gap-1 text-[11px] font-medium">
                      <CalendarX2 className="h-3 w-3" /> Saran hari kerja terdekat:{" "}
                      {longDate(c.suggested_date)}
                    </p>
                  ) : null}
                </div>
                <div className="flex shrink-0 flex-col gap-1.5">
                  <Button size="sm" variant="outline" data-testid={CAL.conflictOpen}
                    aria-label={`Lihat detail ${c.date}`}
                    onClick={() => onOpenDay(c.date)}>
                    Lihat hari itu
                  </Button>
                  {canShift ? (
                    <Button size="sm" variant="secondary" data-testid={CAL.conflictShift}
                      aria-label={`Geser jadwal untuk ${c.date}`}
                      onClick={() => onShift(c)}>
                      Geser jadwal
                    </Button>
                  ) : null}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {(outlook || []).length ? (
        <div data-testid={CAL.outlook} className="rounded-xl border bg-card p-3 shadow-[var(--shadow-card)]">
          <p className="text-xs font-semibold">Pandangan ke depan</p>
          <div className="mt-1.5 flex flex-wrap gap-2">
            {outlook.map((o) => (
              <button key={o.month} type="button" data-testid={CAL.outlookRow}
                data-month={o.month} aria-label={`Buka ${monthLabel(o.month)}`}
                onClick={() => onJumpMonth(o.month)}
                className={`inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5
                  text-[11px] transition hover:border-primary/40 ${o.conflicts.total
                    ? "border-amber-300 bg-amber-50 text-amber-900"
                    : "border-border bg-background text-muted-foreground"}`}>
                <span className="font-medium">{monthLabel(o.month)}</span>
                <span className="tabular-nums">{o.events} acara</span>
                {o.conflicts.total ? (
                  <span className="font-semibold tabular-nums">
                    {o.conflicts.total} bentrok
                  </span>
                ) : <span>aman</span>}
                <ArrowRight className="h-3 w-3" />
              </button>
            ))}
          </div>
          <p className="mt-1.5 text-[11px] text-muted-foreground">
            Total bentrok bulan ini: {totals.overload || 0} beban pelaksana ·{" "}
            {totals.critical_stack || 0} tumpukan kritis · {totals.non_workday || 0} hari libur
          </p>
        </div>
      ) : null}
    </div>
  );
}
