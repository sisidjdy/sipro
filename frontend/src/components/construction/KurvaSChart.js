import React from "react";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from "recharts";
import { legendLabel } from "@/utils/chartUi";
import { CONSTRUCTION } from "@/constants/testIds";

// Kurva-S: cumulative planned vs actual completion (%). Amber=plan, Teal=actual.
export default function KurvaSChart({ curve }) {
  const points = curve?.points || [];
  const behind = curve?.behind;
  const dev = curve?.deviation ?? 0;
  return (
    <div data-testid={CONSTRUCTION.curve} className="rounded-xl border bg-card p-4 shadow-sm">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-semibold">Kurva-S (Rencana vs Aktual)</h3>
        <span className={`rounded-full border px-2 py-0.5 text-xs ${
          behind ? "border-rose-200 bg-rose-50 text-rose-700" : "border-emerald-200 bg-emerald-50 text-emerald-700"}`}>
          {behind ? `Tertinggal ${Math.abs(dev)}%` : `On-track (${dev >= 0 ? "+" : ""}${dev}%)`}
        </span>
      </div>
      <ResponsiveContainer width="100%" height={260}>
        <LineChart data={points} margin={{ top: 8, right: 16, left: -12, bottom: 4 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
          <XAxis dataKey="name" tick={{ fontSize: 10 }} interval={0} angle={-12} textAnchor="end" height={50} />
          <YAxis domain={[0, 100]} tick={{ fontSize: 11 }} unit="%" />
          <Tooltip formatter={(v) => `${v}%`} />
          <Legend wrapperStyle={{ fontSize: 12 }} formatter={legendLabel} />
          <Line type="monotone" dataKey="planned" name="Rencana" stroke="#f59e0b" strokeWidth={2} dot={{ r: 3 }} />
          <Line type="monotone" dataKey="actual" name="Aktual" stroke="#0d9488" strokeWidth={2.5} dot={{ r: 3 }} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
