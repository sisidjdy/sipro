import React from "react";
import { AlertTriangle } from "lucide-react";

import { useReference } from "@/context/ReferenceContext";
import {
  DAY_TONE, KIND_DOT, KIND_ORDER, WEEKDAY_HEADER, leadingBlanks,
} from "@/utils/calendarUi";
import { CAL } from "@/constants/testIds";

/**
 * GRID BULANAN — satu layar untuk melihat SEMUA tenggat rumah.
 *
 * Yang disengaja terlihat pada tiap sel:
 *   * jenis hari (hari kerja penuh / setengah hari / libur mingguan / hari libur bernama),
 *     karena tenggat yang mendarat di hari libur adalah sumber "telat palsu";
 *   * jumlah acara per jenis (titik berwarna + angka), bukan daftar panjang — detail
 *     dibuka on-demand di panel hari (progressive disclosure);
 *   * penanda bentrok, supaya perencana tahu hari mana yang perlu dibereskan lebih dulu.
 */
export default function CalendarMonthGrid({ days, selected, onPick }) {
  const { labelOf } = useReference();
  const blanks = leadingBlanks(days);

  return (
    <div className="rounded-xl border bg-card p-2 sm:p-3 shadow-[var(--shadow-card)]">
      <div className="grid grid-cols-7 gap-1 pb-1">
        {WEEKDAY_HEADER.map((w) => (
          <div key={w} className="px-1 text-center text-[11px] font-semibold text-muted-foreground">
            {w}
          </div>
        ))}
      </div>
      <div data-testid={CAL.grid} className="grid grid-cols-7 gap-1">
        {Array.from({ length: blanks }).map((_, i) => (
          <div key={`blank-${i}`} className="min-h-[84px] rounded-lg bg-transparent" />
        ))}
        {(days || []).map((d) => {
          const active = selected === d.date;
          const kinds = KIND_ORDER.filter((k) => (d.counts || {})[k]);
          return (
            <button key={d.date} type="button" data-testid={CAL.day} data-date={d.date}
              data-workday={d.is_workday ? "1" : "0"}
              data-conflicts={d.conflict_count || 0}
              aria-label={`${d.date} — ${d.total} acara${d.holiday ? `, libur ${d.holiday}` : ""}`}
              onClick={() => onPick(d.date)}
              className={`min-h-[84px] rounded-lg border p-1.5 text-left transition
                ${DAY_TONE[d.kind] || "bg-card"}
                ${active ? "ring-2 ring-primary" : "hover:border-primary/40"}
                ${d.is_today ? "border-primary" : "border-border"}
                ${d.is_past && !d.is_today ? "opacity-80" : ""}`}>
              <div className="flex items-start justify-between gap-1">
                <span className={`text-xs font-semibold tabular-nums ${d.is_today
                  ? "rounded-md bg-primary px-1.5 text-primary-foreground"
                  : "text-foreground"}`}>
                  {Number(String(d.date).slice(8, 10))}
                </span>
                {d.conflict_count ? (
                  <span className="inline-flex items-center gap-0.5 rounded-full bg-amber-100 px-1 text-[10px] font-semibold text-amber-900">
                    <AlertTriangle className="h-2.5 w-2.5" />{d.conflict_count}
                  </span>
                ) : null}
              </div>

              {d.holiday ? (
                <p className="mt-0.5 line-clamp-2 text-[10px] font-medium leading-tight text-rose-800">
                  {d.holiday}
                </p>
              ) : !d.is_workday ? (
                <p className="mt-0.5 text-[10px] text-muted-foreground">
                  {labelOf("calendar_day_kind", d.kind)}
                </p>
              ) : d.half_day ? (
                <p className="mt-0.5 text-[10px] text-sky-800">Setengah hari</p>
              ) : null}

              <div className="mt-1 flex flex-wrap gap-1">
                {kinds.map((k) => (
                  <span key={k} data-testid={CAL.dayBadge} data-kind={k}
                    aria-label={`${labelOf("calendar_event_kind", k)}: ${d.counts[k]}`}
                    className="inline-flex items-center gap-1 rounded-full border bg-background px-1.5 text-[10px] font-medium">
                    <span className={`h-1.5 w-1.5 rounded-full ${KIND_DOT[k]}`} />
                    {d.counts[k]}
                  </span>
                ))}
              </div>
              {d.late ? (
                <p className="mt-1 text-[10px] font-semibold text-rose-700">{d.late} telat</p>
              ) : null}
            </button>
          );
        })}
      </div>

      <div data-testid={CAL.legend}
        className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1.5 border-t pt-2 text-[11px] text-muted-foreground">
        {KIND_ORDER.map((k) => (
          <span key={k} className="inline-flex items-center gap-1.5">
            <span className={`h-2 w-2 rounded-full ${KIND_DOT[k]}`} />
            {labelOf("calendar_event_kind", k)}
          </span>
        ))}
        <span className="inline-flex items-center gap-1.5">
          <span className="h-3 w-3 rounded border border-rose-200 bg-rose-50" /> hari libur
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="h-3 w-3 rounded border bg-secondary" /> libur mingguan
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="h-3 w-3 rounded border border-sky-200 bg-sky-50" /> setengah hari
        </span>
      </div>
    </div>
  );
}
