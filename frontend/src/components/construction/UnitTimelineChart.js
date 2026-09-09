import React from "react";
import {
  Area, AreaChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";

import { legendLabel } from "@/utils/chartUi";
import { BUILD } from "@/constants/testIds";

/**
 * Kurva rencana vs realisasi per MINGGU untuk satu unit.
 *
 * Berbeda dengan Kurva-S proyek yang memakai `planned_pct` yang diketik manual, kurva ini
 * dihitung dari JADWAL NYATA: bobot item per minggu dan tanggal verifikasinya.
 */
export default function UnitTimelineChart({ timeline, deviation = 0 }) {
  const points = timeline?.points || [];
  if (!points.length) return null;
  const behind = deviation <= -10;
  return (
    <div data-testid={BUILD.timeline} className="rounded-xl border bg-card p-3 shadow-sm">
      <div className="mb-1 flex flex-wrap items-center justify-between gap-2">
        <h4 className="text-sm font-semibold">Rencana vs realisasi per minggu</h4>
        <span className={`rounded-full border px-2 py-0.5 text-[11px] ${behind
          ? "border-rose-200 bg-rose-50 text-rose-700"
          : "border-emerald-200 bg-emerald-50 text-emerald-700"}`}>
          {deviation >= 0 ? `Sesuai rencana (+${deviation}%)` : `Tertinggal ${Math.abs(deviation)}%`}
        </span>
      </div>
      <ResponsiveContainer width="100%" height={200}>
        <AreaChart data={points} margin={{ top: 8, right: 12, left: -18, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
          <XAxis dataKey="name" tick={{ fontSize: 10 }} />
          <YAxis domain={[0, 100]} tick={{ fontSize: 10 }} unit="%" />
          <Tooltip formatter={(v) => `${v}%`} />
          <Legend wrapperStyle={{ fontSize: 11 }} formatter={legendLabel} />
          <Area type="monotone" dataKey="planned" name="Rencana" stroke="#f59e0b"
            fill="#fef3c7" strokeWidth={2} />
          <Area type="monotone" dataKey="actual" name="Terverifikasi" stroke="#0d9488"
            fill="#ccfbf1" strokeWidth={2.5} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
