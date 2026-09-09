import React from "react";
import { cn } from "@/lib/utils";
import { SITE_PLAN } from "@/constants/testIds";

export const PLOT_TONE = {
  available: {
    label: "Tersedia",
    swatch: "bg-emerald-500",
    tile: "border-emerald-300 bg-emerald-50 hover:border-emerald-500 text-emerald-950",
  },
  reserved: {
    label: "Reserved (hold)",
    swatch: "bg-amber-500",
    tile: "border-amber-300 bg-amber-50 hover:border-amber-500 text-amber-950",
  },
  booked: {
    label: "Booked",
    swatch: "bg-indigo-500",
    tile: "border-indigo-300 bg-indigo-50 hover:border-indigo-500 text-indigo-950",
  },
  sold: {
    label: "Terjual (AJB)",
    swatch: "bg-slate-500",
    tile: "border-slate-300 bg-slate-100 hover:border-slate-500 text-slate-900",
  },
};

export default function PlanLegend({ counts = {} }) {
  return (
    <div data-testid={SITE_PLAN.legend}
      className="flex flex-wrap items-center gap-x-4 gap-y-2 rounded-xl border bg-card px-3 py-2 shadow-[var(--shadow-card)]">
      <span className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
        Legenda
      </span>
      {Object.entries(PLOT_TONE).map(([key, tone]) => (
        <span key={key} data-testid={SITE_PLAN.legendItem} data-legend-status={key}
          className="inline-flex items-center gap-1.5 text-xs">
          <span className={cn("h-2.5 w-2.5 rounded-sm", tone.swatch)} />
          <span className="text-foreground">{tone.label}</span>
          <span className="font-semibold tabular-nums text-muted-foreground">
            {counts[key] ?? 0}
          </span>
        </span>
      ))}
    </div>
  );
}
