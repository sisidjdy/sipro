import React from "react";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import ChartFrame from "@/components/patterns/ChartFrame";
import { formatIDR } from "@/utils/formatters";
import { P91 } from "@/constants/testIds";

const ORDER = [["current", "Lancar"], ["1-30", "1–30 hari"], ["31-60", "31–60 hari"], ["61-90", "61–90 hari"], [">90", "> 90 hari"]];
const short = (v) => (v >= 1e9 ? `${(v / 1e9).toFixed(1)} M` : v >= 1e6 ? `${Math.round(v / 1e6)} jt` : String(v));

/** Grafik batang aging piutang vs utang; klik batang → rincian bucket. */
export default function AgingChart({ ar = {}, ap = {}, onSelect }) {
  const rows = ORDER.map(([key, label]) => ({ key, label, ar: ar[key] || 0, ap: ap[key] || 0 }));
  const hasData = rows.some((r) => r.ar || r.ap);
  return (
    <ChartFrame title="Aging Piutang vs Utang" testId={P91.agingChart} height={260}
      description="Klik batang untuk melihat tagihan penyusunnya."
      rows={hasData ? rows : []} csvName="aging-ar-ap"
      csvColumns={[{ key: "label", header: "Bucket" }, { key: "ar", header: "Piutang" }, { key: "ap", header: "Utang" }]}>
      <ResponsiveContainer width="100%" height="100%" minWidth={0} initialDimension={{ width: 320, height: 260 }}>
        <BarChart data={rows} margin={{ top: 8, right: 8, left: 8, bottom: 0 }} barGap={4}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="hsl(var(--border))" />
          <XAxis dataKey="label" tick={{ fontSize: 11 }} axisLine={false} tickLine={false} />
          <YAxis tickFormatter={short} tick={{ fontSize: 11 }} axisLine={false} tickLine={false} width={56} />
          <Tooltip formatter={(v, n) => [formatIDR(v), n === "ar" ? "Piutang (AR)" : "Utang (AP)"]}
            contentStyle={{ borderRadius: 8, fontSize: 12 }} cursor={{ fill: "hsl(var(--accent))", opacity: 0.4 }} />
          <Legend formatter={(v) => (v === "ar" ? "Piutang (AR)" : "Utang (AP)")} wrapperStyle={{ fontSize: 12 }} />
          <Bar dataKey="ar" fill="hsl(var(--primary))" radius={[6, 6, 0, 0]} className="cursor-pointer"
            onClick={(d) => onSelect?.({ key: "ar_bucket", bucket: d.key, label: `Aging piutang · ${d.label}` })} />
          <Bar dataKey="ap" fill="#d97706" radius={[6, 6, 0, 0]} className="cursor-pointer"
            onClick={(d) => onSelect?.({ key: "ap_bucket", bucket: d.key, label: `Aging utang · ${d.label}` })} />
        </BarChart>
      </ResponsiveContainer>
    </ChartFrame>
  );
}
