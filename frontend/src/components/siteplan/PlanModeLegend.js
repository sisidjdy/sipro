import React from "react";
import { cn } from "@/lib/utils";
import { Layers, HardHat, Banknote, Timer } from "lucide-react";
import { legendFor } from "@/components/siteplan/planStyles";
import { useReference } from "@/context/ReferenceContext";
import { SITE_PLAN } from "@/constants/testIds";

const MODE_BUTTONS = [
  { id: "sales", label: "Siklus Penjualan", icon: Layers, tid: SITE_PLAN.modeSales },
  { id: "build", label: "Progres Pembangunan", icon: HardHat, tid: SITE_PLAN.modeBuild },
  { id: "price", label: "Harga", icon: Banknote, tid: SITE_PLAN.modePrice },
  { id: "dom", label: "Lama Tak Terjual", icon: Timer, tid: SITE_PLAN.modeDom },
];

const HINTS = {
  sales: "Warna mengikuti tahap penjualan & legal setiap kavling.",
  build: "Warna mengikuti progres pembangunan per kavling.",
  price: "Peta panas harga: 5 pita kuantil dari sebaran harga proyek ini.",
  dom: "Peta panas lama dipasarkan: makin merah, makin lama kavling belum laku.",
};

/**
 * Pemilih mode warna + legenda interaktif (4 mode infografis).
 * Klik item legenda = sorot kategori itu di peta (kategori lain diredupkan).
 */
export default function PlanModeLegend({
  mode, onMode, units = [], highlight, onHighlight, scales,
}) {
  const { labelOf } = useReference();
  const items = legendFor(mode, units, labelOf, scales);

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
          Mode warna
        </span>
        <div className="inline-flex flex-wrap rounded-lg border bg-card p-0.5 shadow-sm">
          {MODE_BUTTONS.map((m) => {
            const Icon = m.icon;
            const on = mode === m.id;
            return (
              <button key={m.id} type="button" data-testid={m.tid}
                aria-pressed={on} onClick={() => onMode(m.id)}
                className={cn("inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-colors",
                  on ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-secondary")}>
                <Icon className="h-3.5 w-3.5" /> {m.label}
              </button>
            );
          })}
        </div>
        <span className="text-[11px] text-muted-foreground">{HINTS[mode]}</span>
      </div>

      <div data-testid={SITE_PLAN.legend}
        className="flex flex-wrap items-center gap-1.5 rounded-xl border bg-card px-2.5 py-2 shadow-[var(--shadow-card)]">
        {items.map((it) => {
          const on = highlight === it.key;
          return (
            <button key={it.key} type="button" data-testid={SITE_PLAN.legendItem}
              data-legend-status={it.key}
              onClick={() => onHighlight(on ? "" : it.key)}
              className={cn("inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs transition-all",
                on ? "border-primary bg-primary/10 font-semibold" : "border-transparent hover:bg-secondary")}>
              <span className="h-2.5 w-2.5 rounded-sm" style={{ backgroundColor: it.dot }} />
              <span>{it.label}</span>
              <span className="tabular-nums text-muted-foreground">{it.count}</span>
            </button>
          );
        })}
        {highlight ? (
          <button type="button" onClick={() => onHighlight("")}
            className="ml-1 text-[11px] text-primary underline">bersihkan sorotan</button>
        ) : null}
      </div>
    </div>
  );
}
