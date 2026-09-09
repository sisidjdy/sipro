import React from "react";
import { Area, AreaChart, ResponsiveContainer, Tooltip, YAxis } from "recharts";
import { TrendingDown, TrendingUp, Minus } from "lucide-react";

import { cn } from "@/lib/utils";
import { formatMetric, formatMetricCompact } from "@/components/bi/MetricValue";
import { formatNumber } from "@/utils/formatters";
import { BI } from "@/constants/testIds";

/**
 * MetricSpark — visualisasi mini DI DALAM kartu metrik (keluhan pemakai: "banyak cards
 * tapi minim visualisasi"). Aturan kejujuran Fase 44 tetap berlaku: metrik `kosong`
 * tidak digambar sama sekali — sparkline nol palsu sama bohongnya dengan angka 0.
 *
 * Prioritas bentuk: deret waktu → sparkline area INTERAKTIF (hover = periode + nilai);
 * persen → bilah progres berlabel; rincian kategori → bilah proporsi top-4.
 */

export function TrendDelta({ series, unit }) {
  const rows = (series || []).filter((s) => s?.value !== null && s?.value !== undefined);
  if (rows.length < 2) return null;
  const prev = Number(rows[rows.length - 2].value);
  const last = Number(rows[rows.length - 1].value);
  const diff = last - prev;
  const Icon = diff > 0 ? TrendingUp : diff < 0 ? TrendingDown : Minus;
  const tone = diff > 0 ? "text-emerald-600 dark:text-emerald-400"
    : diff < 0 ? "text-rose-600 dark:text-rose-400" : "text-muted-foreground";
  return (
    <span data-testid={BI.cardTrend} className={cn("inline-flex items-center gap-1 text-[11px] font-medium tabular-nums", tone)}
      title={`Periode terakhir vs sebelumnya: ${formatMetric(prev, unit)} → ${formatMetric(last, unit)}`}>
      <Icon className="h-3 w-3" />
      {diff === 0 ? "tetap" : `${diff > 0 ? "+" : "−"}${formatMetric(Math.abs(diff), unit) ?? formatNumber(Math.abs(diff))}`}
      <span className="font-normal text-muted-foreground">vs sblm.</span>
    </span>
  );
}

function SparkTip({ active, payload, unit }) {
  if (!active || !payload?.length) return null;
  const row = payload[0].payload;
  return (
    <div className="rounded-md border bg-popover/95 px-2 py-1 text-[11px] shadow-lg backdrop-blur-md">
      <span className="text-muted-foreground">{row.bucket}</span>{" "}
      <span className="font-semibold tabular-nums">{formatMetricCompact(row.v, unit)}</span>
    </div>
  );
}

function Sparkline({ series, code, unit }) {
  // Deret kumulatif digambar dari `cumulative` (bukan `value` yang bisa datar): deret datar
  // membuat domain min=max sehingga garis menempel di atas dan area terisi penuh — terlihat
  // seperti balok pejal, bukan tren (temuan uji regresi). Domain juga diberi napas.
  const useCum = series.some((s) => s.cumulative !== undefined && s.cumulative !== null);
  const rows = series.map((s) => ({ ...s, v: Number(useCum ? s.cumulative : s.value) }));
  const vals = rows.map((r) => r.v);
  const lo = Math.min(...vals); const hi = Math.max(...vals);
  const pad = (hi - lo) || Math.abs(hi) || 1;
  const gid = `spark-${code}`;
  return (
    <div className="h-16 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={rows} margin={{ top: 4, right: 4, bottom: 0, left: 4 }}>
          <defs>
            <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="hsl(var(--chart-1))" stopOpacity={0.35} />
              <stop offset="100%" stopColor="hsl(var(--chart-1))" stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <YAxis hide domain={[Math.min(0, lo), hi + pad * 0.25]} />
          <Tooltip content={<SparkTip unit={unit} />} cursor={{ stroke: "hsl(var(--border))" }} />
          <Area type="monotone" dataKey="v" stroke="hsl(var(--chart-1))" strokeWidth={2}
            fill={`url(#${gid})`} isAnimationActive={false} dot={false}
            activeDot={{ r: 3.5, strokeWidth: 2, stroke: "hsl(var(--card))" }} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

function PctBar({ value }) {
  const pct = Math.max(0, Math.min(100, Number(value)));
  return (
    <div className="space-y-1.5">
      <div className="relative h-2.5 w-full overflow-hidden rounded-full bg-secondary">
        <div className="h-full rounded-full transition-[width] duration-700"
          style={{ width: `${pct}%`,
            background: "linear-gradient(90deg, hsl(var(--chart-1)) 0%, hsl(var(--chart-3)) 100%)" }} />
      </div>
      <div className="flex justify-between text-[11px] text-muted-foreground">
        <span>0%</span>
        <span className="font-medium text-foreground tabular-nums">{formatNumber(pct)}% tercapai</span>
        <span>100%</span>
      </div>
    </div>
  );
}

function TopBars({ breakdown, unit }) {
  const rows = breakdown
    .filter((r) => r && r.value !== null && r.value !== undefined)
    .sort((a, b) => Math.abs(Number(b.value)) - Math.abs(Number(a.value)))
    .slice(0, 4);
  if (!rows.length) return null;
  const max = Math.max(...rows.map((r) => Math.abs(Number(r.value)))) || 1;
  const more = breakdown.length - rows.length;
  return (
    <div className="space-y-2">
      {rows.map((r, i) => (
        <div key={r.key || r.label || i} className="flex items-center gap-2"
          title={`${r.label}: ${formatMetric(r.value, unit) ?? formatNumber(r.value)}`}>
          <span className="w-[34%] truncate text-[11px] text-muted-foreground">
            {r.label}
          </span>
          <div className="h-2 flex-1 overflow-hidden rounded-full bg-secondary">
            <div className="h-full rounded-full transition-[width] duration-500"
              style={{ width: `${(Math.abs(Number(r.value)) / max) * 100}%`,
                backgroundColor: `hsl(var(--chart-${(i % 5) + 1}))`,
                opacity: 0.95 - i * 0.12 }} />
          </div>
          <span className="shrink-0 whitespace-nowrap text-right text-[11px] font-medium tabular-nums">
            {formatMetricCompact(r.value, unit)}
          </span>
        </div>
      ))}
      {more > 0 ? (
        <p className="text-[10px] text-muted-foreground/70">+{more} kategori lain di “Rincian”</p>
      ) : null}
    </div>
  );
}

export default function MetricSpark({ metric }) {
  if (!metric || metric.state === "kosong") return null;
  const series = (metric.series || []).filter((s) => s?.value !== null && s?.value !== undefined);
  const breakdown = metric.breakdown || [];
  let body = null;
  if (series.length >= 2) body = <Sparkline series={series} code={metric.code} unit={metric.unit} />;
  else if (metric.unit === "pct" && metric.value !== null && metric.value !== undefined) {
    body = <PctBar value={metric.value} />;
  } else if (breakdown.length >= 2) body = <TopBars breakdown={breakdown} unit={metric.unit} />;
  if (!body) return null;
  return <div data-testid={BI.cardSpark} className="pt-1.5">{body}</div>;
}
