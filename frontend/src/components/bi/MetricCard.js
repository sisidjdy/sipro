import React from "react";
import { Link } from "react-router-dom";
import { ArrowUpRight, Sigma } from "lucide-react";

import { cn } from "@/lib/utils";
import { MetricNote, MetricStateBadge, MetricValue } from "@/components/bi/MetricValue";
import MetricSpark, { TrendDelta } from "@/components/bi/MetricSpark";
import { BI } from "@/constants/testIds";

/**
 * MetricCard — satu angka BI yang MENJELASKAN DIRINYA SENDIRI.
 *
 * Isinya bukan cuma angka: ada status kelengkapan, rumusnya (bisa dibaca tanpa membuka
 * dokumen), tautan drill-down ke daftar barisnya (blueprint: KPI tanpa drill = belum selesai),
 * tombol “rincian” untuk melihat pecahannya, dan — sejak keluhan "cards minim visualisasi" —
 * visualisasi mini (sparkline/progres/top-3) yang tetap tunduk pada aturan kejujuran:
 * metrik `kosong` TIDAK digambar.
 */
export default function MetricCard({ metric, onDetail, className }) {
  if (!metric) return null;
  const hasBreakdown = (metric.breakdown || []).length > 0;
  return (
    <div data-testid={BI.card} data-code={metric.code} data-state={metric.state}
      className={cn(
        "group relative flex flex-col gap-2 overflow-hidden rounded-xl border bg-card p-4",
        "transition-[border-color,box-shadow,transform] duration-200",
        "hover:-translate-y-0.5 hover:border-primary/40 hover:shadow-[0_8px_24px_-12px_hsl(var(--primary)/0.35)]",
        className)}>
      <span aria-hidden="true"
        className="pointer-events-none absolute inset-x-0 top-0 h-0.5 bg-gradient-to-r from-primary/70 via-primary/25 to-transparent opacity-0 transition-opacity duration-200 group-hover:opacity-100" />
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate text-xs font-medium uppercase tracking-wide text-muted-foreground">
            {metric.label}
          </p>
          <p className="text-[10px] text-muted-foreground/70">{metric.code}</p>
        </div>
        <MetricStateBadge state={metric.state} coverage={metric.coverage} />
      </div>
      <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
        <MetricValue metric={metric} />
        <TrendDelta series={metric.series} unit={metric.unit} />
      </div>
      <MetricSpark metric={metric} />
      <MetricNote metric={metric} />
      {metric.formula ? (
        <p data-testid={BI.cardFormula}
          className="flex items-start gap-1 text-[11px] text-muted-foreground">
          <Sigma className="mt-0.5 h-3 w-3 shrink-0" />
          <span className="break-words">{metric.formula.replace(/^Σ\s*/u, "")}</span>
        </p>
      ) : null}
      <div className="mt-auto flex items-center justify-between gap-2 pt-1">
        {metric.drill ? (
          <Link to={metric.drill} data-testid={BI.cardDrill} data-drill={metric.code}
            className="inline-flex items-center gap-1 text-xs font-medium text-primary hover:underline">
            Lihat daftar <ArrowUpRight className="h-3 w-3" />
          </Link>
        ) : <span />}
        {hasBreakdown && onDetail ? (
          <button type="button" onClick={() => onDetail(metric)}
            data-testid={BI.cardDetail} data-detail={metric.code}
            className="text-xs font-medium text-muted-foreground hover:text-foreground hover:underline">
            Rincian ({metric.breakdown.length})
          </button>
        ) : null}
      </div>
    </div>
  );
}
