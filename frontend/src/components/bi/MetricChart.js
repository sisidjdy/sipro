import React, { useMemo } from "react";
import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart, Pie, PieChart,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";

import ChartFrame from "@/components/patterns/ChartFrame";
import { legendLabel } from "@/utils/chartUi";
import { formatMetric, formatMetricCompact } from "@/components/bi/MetricValue";
import { formatCompact, formatNumber } from "@/utils/formatters";
import { BI } from "@/constants/testIds";

/**
 * MetricChart — grafik dipilih dari PERTANYAANNYA, bukan dari selera (Dok 31 §8):
 *   deret waktu kumulatif  → area (mis. unit terjual)
 *   deret waktu biasa      → garis + bayangan area tipis
 *   perbandingan kategori  → bar horizontal (label terbaca, tanpa memiringkan teks)
 *   komposisi (≤6 irisan)  → donut dengan total di tengah, sisanya digabung “lainnya”
 * Warna mengikuti token tema (`--chart-1..5`) supaya mode gelap ikut benar; tooltip
 * dibuat sendiri (kaca buram + bayangan) karena tooltip bawaan putih polos menabrak tema.
 */
const PALETTE = [1, 2, 3, 4, 5].map((n) => `hsl(var(--chart-${n}))`);
const MAX_SLICES = 6;

const AXIS_TICK = { fontSize: 11, fill: "hsl(var(--muted-foreground))" };
const GRID_STROKE = "hsl(var(--border))";

export function ChartTip({ active, payload, label, format, nameFor }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border bg-popover/95 px-3 py-2 shadow-xl backdrop-blur-md">
      {label ? <p className="mb-1 text-[11px] font-medium text-muted-foreground">{label}</p> : null}
      {payload.map((p, i) => (
        <p key={i} className="flex items-center gap-1.5 text-xs text-popover-foreground">
          <span className="h-2 w-2 shrink-0 rounded-full"
            style={{ backgroundColor: p.color || p.payload?.fill || PALETTE[0] }} />
          <span className="text-muted-foreground">{nameFor ? nameFor(p) : p.name}</span>
          <span className="ml-auto pl-3 font-semibold tabular-nums">{format(p.value)}</span>
        </p>
      ))}
    </div>
  );
}

function sliceForPie(rows) {
  // `rows` sudah disaring dari nilai kosong sebelum masuk sini, jadi TIDAK ADA fallback
  // `|| 0` — fallback semacam itu akan mengubah "belum ada data" menjadi irisan bernilai nol
  // yang terlihat seperti fakta.
  const sorted = [...rows].sort((a, b) => b.value - a.value);
  if (sorted.length <= MAX_SLICES) return sorted;
  const head = sorted.slice(0, MAX_SLICES - 1);
  const rest = sorted.slice(MAX_SLICES - 1);
  return [...head, {
    key: "lainnya", label: "Lainnya",
    value: rest.reduce((sum, r) => sum + Number(r.value), 0),
  }];
}

export default function MetricChart({ metric, kind = "auto", title, description, height }) {
  const rows = useMemo(() => {
    if (!metric) return [];
    if (kind === "series" || (kind === "auto" && (metric.series || []).length)) {
      return (metric.series || []).map((s) => ({ ...s, label: s.bucket }));
    }
    return (metric.breakdown || []).filter((r) => r && r.value !== null && r.value !== undefined);
  }, [metric, kind]);
  const isSeries = kind === "series" || (kind === "auto" && (metric?.series || []).length > 0);
  const cumulative = isSeries && rows.some((r) => r.cumulative !== undefined);
  const csvColumns = isSeries
    ? [{ key: "bucket", header: "Periode" }, { key: "value", header: metric?.label || "Nilai" },
       ...(cumulative ? [{ key: "cumulative", header: "Kumulatif" }] : [])]
    : [{ key: "label", header: "Kategori" }, { key: "value", header: metric?.label || "Nilai" }];
  const tip = (value) => formatMetric(value, metric?.unit) ?? formatNumber(value);
  const gid = `bi-grad-${(metric?.code || "x").toLowerCase()}`;

  // Tinggi grafik mengikuti ISI, bukan angka tetap. Bar kategori dengan 12 baris di dalam
  // kotak 256 px membuat label saling menempel sampai tidak terbaca (keluhan pemakai:
  // "visualisasi terlalu kecil, tumpang tindih"). Deret waktu & donut cukup tinggi tetap,
  // tetapi bar horizontal tumbuh 36 px per kategori.
  const catHeight = Math.min(720, Math.max(300, 36 * rows.length + 64));
  const boxHeight = height || (isSeries || kind === "pie" ? 320 : catHeight);
  // Lebar sumbu kategori mengikuti label terpanjang supaya nama tidak terpotong "…" padahal
  // ruangnya ada — dibatasi 220 px agar area grafiknya tidak habis oleh teks.
  const labelWidth = Math.min(220, Math.max(110,
    8 * rows.reduce((n, r) => Math.max(n, String(r.label ?? "").length), 0)));

  const pieRows = kind === "pie" ? sliceForPie(rows) : [];
  const pieTotal = pieRows.reduce((s, r) => s + Number(r.value), 0);
  const barMax = Math.max(...rows.map((r) => Math.abs(Number(r.value))), 0) || 1;

  return (
    <ChartFrame testId={BI.chart} title={title || metric?.label || "Grafik"}
      description={description || metric?.formula} rows={rows} csvColumns={csvColumns}
      csvName={`bi-${(metric?.code || "metrik").toLowerCase()}`} height={boxHeight}
      emptyText={metric?.state === "kosong"
        ? (metric?.note || "Data untuk metrik ini belum ada — grafik sengaja tidak digambar.")
        : "Belum ada rincian untuk digambarkan."}>
      <ResponsiveContainer width="100%" height="100%">
        {kind === "pie" ? (
          <PieChart margin={{ top: 8, right: 8, bottom: 8, left: 8 }}>
            <Pie data={pieRows} dataKey="value" nameKey="label" innerRadius="58%"
              outerRadius="78%" paddingAngle={3} cornerRadius={5} strokeWidth={0}>
              {pieRows.map((row, i) => (
                <Cell key={row.key || i} fill={PALETTE[i % PALETTE.length]} />
              ))}
            </Pie>
            {/* Total di tengah donat: jawaban pertama yang dicari mata, tanpa menjumlah irisan. */}
            <text x="50%" y="46%" textAnchor="middle" dominantBaseline="central"
              className="fill-foreground font-heading" fontSize={18} fontWeight={600}>
              {formatMetricCompact(pieTotal, metric?.unit)}
            </text>
            <text x="50%" y="56%" textAnchor="middle" dominantBaseline="central"
              fill="hsl(var(--muted-foreground))" fontSize={11}>
              total
            </text>
            <Tooltip content={<ChartTip format={tip} nameFor={(p) => p.name} />} />
            <Legend verticalAlign="bottom" height={44} iconSize={9} iconType="circle"
              wrapperStyle={{ fontSize: 12, lineHeight: "18px" }} formatter={legendLabel} />
          </PieChart>
        ) : cumulative ? (
          <AreaChart data={rows} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
            <defs>
              <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={PALETTE[0]} stopOpacity={0.32} />
                <stop offset="100%" stopColor={PALETTE[0]} stopOpacity={0.02} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" vertical={false} stroke={GRID_STROKE} />
            <XAxis dataKey="bucket" tick={AXIS_TICK} minTickGap={16} axisLine={false} tickLine={false} />
            <YAxis tick={AXIS_TICK} width={72} axisLine={false} tickLine={false}
              tickFormatter={(v) => formatCompact(v)} />
            <Tooltip content={<ChartTip format={tip}
              nameFor={(p) => (p.dataKey === "cumulative" ? "Kumulatif" : "Periode")} />} />
            <Area type="monotone" dataKey="cumulative" stroke={PALETTE[0]} fill={`url(#${gid})`}
              strokeWidth={2.5} activeDot={{ r: 4, strokeWidth: 2, stroke: "hsl(var(--card))" }} />
          </AreaChart>
        ) : isSeries ? (
          <AreaChart data={rows} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
            <defs>
              <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={PALETTE[2]} stopOpacity={0.22} />
                <stop offset="100%" stopColor={PALETTE[2]} stopOpacity={0.02} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" vertical={false} stroke={GRID_STROKE} />
            <XAxis dataKey="bucket" tick={AXIS_TICK} minTickGap={16} axisLine={false} tickLine={false} />
            <YAxis tick={AXIS_TICK} width={72} axisLine={false} tickLine={false}
              tickFormatter={(v) => formatCompact(v)} />
            <Tooltip content={<ChartTip format={tip} nameFor={() => metric?.label || "Nilai"} />} />
            <Area type="monotone" dataKey="value" stroke={PALETTE[2]} fill={`url(#${gid})`}
              strokeWidth={2.5} dot={{ r: 3, strokeWidth: 0, fill: PALETTE[2] }}
              activeDot={{ r: 4.5, strokeWidth: 2, stroke: "hsl(var(--card))" }} />
          </AreaChart>
        ) : (
          <BarChart data={rows} layout="vertical"
            margin={{ top: 4, left: 8, right: 24, bottom: 4 }} barCategoryGap="18%">
            <defs>
              <linearGradient id={gid} x1="0" y1="0" x2="1" y2="0">
                <stop offset="0%" stopColor={PALETTE[0]} stopOpacity={0.55} />
                <stop offset="100%" stopColor={PALETTE[0]} stopOpacity={1} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke={GRID_STROKE} />
            <XAxis type="number" tick={AXIS_TICK} axisLine={false} tickLine={false}
              tickFormatter={(v) => formatCompact(v)} />
            <YAxis type="category" dataKey="label" tick={AXIS_TICK} width={labelWidth}
              interval={0} axisLine={false} tickLine={false} />
            <Tooltip cursor={{ fill: "hsl(var(--secondary))", opacity: 0.5 }}
              content={<ChartTip format={tip} nameFor={() => metric?.label || "Nilai"} />} />
            <Bar dataKey="value" fill={`url(#${gid})`} radius={[0, 5, 5, 0]} maxBarSize={24}>
              {/* Baris tertinggi disorot penuh; sisanya memudar mengikuti nilainya supaya
                  perbandingan terbaca sekilas tanpa membaca angka satu-satu. */}
              {rows.map((r, i) => (
                <Cell key={r.key || i}
                  fillOpacity={0.45 + 0.55 * (Math.abs(Number(r.value)) / barMax)} />
              ))}
            </Bar>
          </BarChart>
        )}
      </ResponsiveContainer>
    </ChartFrame>
  );
}
