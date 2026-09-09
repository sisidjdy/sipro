import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  ComposedChart, Bar, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
} from "recharts";
import { Button } from "@/components/ui/button";
import {
  Table, TableHeader, TableBody, TableRow, TableHead, TableCell,
} from "@/components/ui/table";
import MetricCard from "@/components/patterns/MetricCard";
import { LoadingCards, ErrorState } from "@/components/patterns/StateViews";
import { formatIDR } from "@/utils/formatters";
import { legendLabel } from "@/utils/chartUi";
import api from "@/services/apiClient";
import { FINANCE } from "@/constants/testIds";

const compact = (v) => {
  const a = Math.abs(v || 0);
  if (a >= 1e9) return `${(v / 1e9).toFixed(1)}M`;
  if (a >= 1e6) return `${Math.round(v / 1e6)}jt`;
  if (a >= 1e3) return `${Math.round(v / 1e3)}rb`;
  return `${v || 0}`;
};

export default function CashflowPanel() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [bucket, setBucket] = useState("month");
  // Measure the chart container so we can pass explicit numeric width/height to
  // the chart (avoids Recharts' transient "width(-1)/height(-1)" console warning
  // that ResponsiveContainer emits on its first measurement frame).
  const [chartW, setChartW] = useState(0);
  const roRef = useRef(null);
  const attachChartWrap = useCallback((node) => {
    if (roRef.current) { roRef.current.disconnect(); roRef.current = null; }
    if (node) {
      const update = () => setChartW(Math.floor(node.getBoundingClientRect().width));
      const ro = new ResizeObserver(update);
      ro.observe(node);
      roRef.current = ro;
      update();
    }
  }, []);
  useEffect(() => () => { if (roRef.current) roRef.current.disconnect(); }, []);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const res = await api.get("/finance/cashflow", { params: { bucket, horizon: 6 } });
      setData(res.data.data);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat proyeksi arus kas.");
    } finally { setLoading(false); }
  }, [bucket]);

  useEffect(() => { load(); }, [load]);

  if (loading) return <LoadingCards count={4} />;
  if (error) return <ErrorState message={error} onRetry={load} />;
  if (!data) return null;

  const t = data.totals || {};
  const chartData = (data.periods || []).map((p) => ({
    name: p.label, Masuk: p.inflow, Keluar: -p.outflow, Kumulatif: p.cumulative,
  }));

  return (
    <div data-testid={FINANCE.cashflowPanel} className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="grid flex-1 grid-cols-2 gap-3 sm:grid-cols-4">
          <MetricCard label="Total Kas Masuk" value={t.inflow} tone="emerald" format="idr" />
          <MetricCard label="Total Kas Keluar" value={t.outflow} tone="rose" format="idr" />
          <MetricCard label="Net Proyeksi" value={t.net} tone="primary" format="idr" />
          <MetricCard label="Saldo Akhir (Runway)" value={t.ending} tone={t.ending < 0 ? "rose" : "indigo"} format="idr" />
        </div>
        <div className="inline-flex overflow-hidden rounded-lg border" data-testid={FINANCE.cashflowBucket}>
          <button onClick={() => setBucket("month")}
            className={`px-3 py-1.5 text-sm ${bucket === "month" ? "bg-primary text-primary-foreground" : "bg-card"}`}>
            Bulanan
          </button>
          <button onClick={() => setBucket("week")}
            className={`px-3 py-1.5 text-sm ${bucket === "week" ? "bg-primary text-primary-foreground" : "bg-card"}`}>
            Mingguan
          </button>
        </div>
      </div>

      <div className="rounded-xl border bg-card p-4 shadow-sm">
        <p className="mb-3 text-sm font-medium">Proyeksi Kas Masuk vs Keluar (6 periode)</p>
        <div ref={attachChartWrap} style={{ width: "100%", height: 300 }}>
          {chartW > 0 && (
          <ComposedChart width={chartW} height={300} data={chartData} margin={{ top: 8, right: 8, left: 4, bottom: 4 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
              <XAxis dataKey="name" tick={{ fontSize: 11 }} />
              <YAxis tickFormatter={compact} tick={{ fontSize: 11 }} width={48} />
              <Tooltip formatter={(v) => formatIDR(Math.abs(v))} />
              <Legend wrapperStyle={{ fontSize: 12 }} formatter={legendLabel} />
              <Bar dataKey="Masuk" fill="#10b981" radius={[4, 4, 0, 0]} />
              <Bar dataKey="Keluar" fill="#f43f5e" radius={[0, 0, 4, 4]} />
              <Line type="monotone" dataKey="Kumulatif" stroke="#4f46e5" strokeWidth={2} dot={{ r: 3 }} />
          </ComposedChart>
          )}
        </div>
      </div>

      <div className="overflow-hidden rounded-xl border bg-card shadow-sm">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Periode</TableHead>
              <TableHead className="text-right">Kas Masuk</TableHead>
              <TableHead className="text-right">Kas Keluar</TableHead>
              <TableHead className="text-right">Net</TableHead>
              <TableHead className="text-right">Kumulatif</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {(data.periods || []).map((p, i) => (
              <TableRow key={i} data-testid={FINANCE.cashflowRow}>
                <TableCell className="font-medium">{p.label}</TableCell>
                <TableCell className="text-right tabular-nums text-emerald-700">{formatIDR(p.inflow)}</TableCell>
                <TableCell className="text-right tabular-nums text-rose-700">{formatIDR(p.outflow)}</TableCell>
                <TableCell className={`text-right tabular-nums ${p.net < 0 ? "text-rose-700" : "text-foreground"}`}>{formatIDR(p.net)}</TableCell>
                <TableCell className={`text-right font-semibold tabular-nums ${p.cumulative < 0 ? "text-rose-700" : "text-indigo-700"}`}>{formatIDR(p.cumulative)}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
      <p className="text-[11px] italic text-muted-foreground">{data.note}</p>
    </div>
  );
}
