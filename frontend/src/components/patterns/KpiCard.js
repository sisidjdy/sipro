import React from "react";
import { Link } from "react-router-dom";
import { ArrowUpRight, TrendingDown, TrendingUp } from "lucide-react";

import { cn } from "@/lib/utils";
import { KPI } from "@/constants/testIds";

/**
 * KpiCard — angka ringkas yang WAJIB bisa ditelusuri (blueprint IA V2 §7.3:
 * “Angka pada KPI wajib bisa di-drill-down ke daftar barisnya. Tanpa drill-down =
 * dianggap tidak selesai”).
 *
 * Karena itu `to` (tautan ke daftar terfilter) adalah bagian dari kontrak: bila diberikan,
 * seluruh kartu menjadi tautan sungguhan (bisa dibuka di tab baru, bisa di-hover untuk
 * melihat tujuannya) — bukan div dengan onClick.
 */
const TONE = {
  primary: { text: "text-primary", bar: "bg-primary", chip: "bg-accent text-accent-foreground" },
  amber: { text: "text-amber-600", bar: "bg-amber-500", chip: "bg-amber-50 text-amber-900" },
  rose: { text: "text-rose-600", bar: "bg-rose-500", chip: "bg-rose-50 text-rose-800" },
  emerald: { text: "text-emerald-600", bar: "bg-emerald-500", chip: "bg-emerald-50 text-emerald-800" },
  sky: { text: "text-sky-700", bar: "bg-sky-500", chip: "bg-sky-50 text-sky-800" },
  muted: { text: "text-muted-foreground", bar: "bg-muted-foreground/40", chip: "bg-secondary" },
};

export default function KpiCard({
  label, value, hint, delta = null, tone = "primary", icon: Icon = null, to = null,
  drillLabel = "Lihat daftar", testId, className, onOpen = null,
}) {
  const t = TONE[tone] || TONE.primary;
  const body = (
    <>
      {/* Garis aksen atas: memberi kartu angka "berat visual" dan menandai jenis kabarnya
          (biru = informasi, merah = perlu perhatian) — dulu semua kartu tampak sama. */}
      <span aria-hidden="true"
        className={cn("absolute inset-x-0 top-0 h-[3px] rounded-t-xl", t.bar)} />
      <div className="flex items-start justify-between gap-2">
        <p className="eyebrow">{label}</p>
        {Icon ? (
          <span className={cn("flex h-7 w-7 items-center justify-center rounded-lg", t.chip)}>
            <Icon className="h-3.5 w-3.5" />
          </span>
        ) : null}
      </div>
      <p data-testid={`${testId || KPI.card}-value`}
        className="mt-2 font-heading text-[26px] font-semibold leading-none tabular-nums">
        {value}
      </p>
      <div className="mt-2 flex items-center gap-1.5">
        {delta !== null && delta !== undefined ? (
          <span className={cn("inline-flex items-center gap-0.5 rounded-full px-1.5 py-0.5 text-xs font-semibold tabular-nums",
            Number(delta) < 0 ? "bg-rose-50 text-rose-700" : "bg-emerald-50 text-emerald-700")}>
            {Number(delta) < 0 ? <TrendingDown className="h-3 w-3" />
              : <TrendingUp className="h-3 w-3" />}
            {Math.abs(Number(delta))}%
          </span>
        ) : null}
        {hint ? <span className="truncate text-xs text-muted-foreground">{hint}</span> : null}
      </div>
      {to || onOpen ? (
        <span className="mt-2.5 inline-flex items-center gap-1 text-xs font-semibold text-primary">
          {onOpen ? "Lihat rincian" : drillLabel}
          <ArrowUpRight className="h-3 w-3 transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5" />
        </span>
      ) : null}
    </>
  );

  const base = cn("group relative block overflow-hidden rounded-xl border border-border bg-card p-4 pt-4 text-left shadow-[var(--shadow-card)]",
    "transition-[box-shadow,border-color,transform] duration-150",
    (to || onOpen) && "hover:-translate-y-0.5 hover:border-primary/40 hover:shadow-[var(--shadow-raised)]",
    className);

  // Fase 92: `onOpen` → kartu menjadi tombol yang membuka popup rincian (bukan tautan).
  if (onOpen) {
    return (
      <button type="button" onClick={onOpen} data-testid={testId || KPI.card} data-drill={to || undefined}
        className={cn(base, "w-full")}>
        {body}
      </button>
    );
  }
  if (!to) {
    return <div data-testid={testId || KPI.card} className={base}>{body}</div>;
  }
  return (
    <Link to={to} data-testid={testId || KPI.card} data-drill={to} className={base}>
      {body}
    </Link>
  );
}
