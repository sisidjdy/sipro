import React, { useCallback, useEffect, useState } from "react";
import { Download, TrendingUp, TrendingDown, Minus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { LoadingKpis, ErrorState } from "@/components/patterns/StateViews";
import { formatIDR } from "@/utils/formatters";
import { downloadCsv } from "@/utils/csv";
import api from "@/services/apiClient";
import { GL } from "@/constants/testIds";

function Growth({ pct }) {
  if (pct === null || pct === undefined) {
    return <span className="inline-flex items-center gap-1 text-[11px] text-muted-foreground">
      <Minus className="h-3 w-3" /> tanpa pembanding</span>;
  }
  const up = pct >= 0;
  const Icon = up ? TrendingUp : TrendingDown;
  return (
    <span className={`inline-flex items-center gap-1 text-[11px] font-medium ${up ? "text-emerald-700" : "text-rose-700"}`}>
      <Icon className="h-3 w-3" /> {up ? "+" : ""}{pct}% vs periode lalu
    </span>
  );
}

function Kpi({ label, value, hint, tone = "text-foreground" }) {
  return (
    <div data-testid={GL.plMetric} data-metric={label}
      className="rounded-xl border bg-card p-4 shadow-sm">
      <p className="text-xs font-medium text-muted-foreground">{label}</p>
      <p className={`mt-1.5 font-heading text-xl font-semibold tabular-nums ${tone}`}>{formatIDR(value)}</p>
      <div className="mt-1">{hint}</div>
    </div>
  );
}

function Rows({ title, rows, onDrill, emptyText }) {
  return (
    <div className="mt-4">
      <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">{title}</p>
      {rows.length ? rows.map((r) => (
        <button key={r.code} type="button" data-testid={GL.plRow} data-account-code={r.code}
          aria-label={`Rincian akun ${r.code} ${r.name}`}
          onClick={() => onDrill(r.code)}
          className="flex w-full items-center justify-between gap-4 rounded-lg px-2 py-1.5 text-left text-sm hover:bg-accent/50">
          <span><span className="tabular-nums text-muted-foreground">{r.code}</span> {r.name}</span>
          <span className="tabular-nums">{formatIDR(r.amount)}</span>
        </button>
      )) : <p className="px-2 py-1.5 text-sm text-muted-foreground">{emptyText}</p>}
    </div>
  );
}

export default function IncomeStatementPanel({ period, onDrill }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const r = await api.get("/gl/reports/income-statement", {
        params: { date_from: period.date_from, date_to: period.date_to, compare: true },
      });
      setData(r.data.data);
    } catch (e) { setError(e?.response?.data?.detail || "Gagal memuat laporan laba rugi."); }
    finally { setLoading(false); }
  }, [period.date_from, period.date_to]);
  useEffect(() => { load(); }, [load]);

  const exportCsv = () => {
    const rows = [
      ...data.revenue.map((r) => ["Pendapatan", r.code, r.name, r.amount]),
      ["", "", "Total Pendapatan", data.total_revenue],
      ...data.cogs.map((r) => ["HPP", r.code, r.name, r.amount]),
      ["", "", "Total HPP", data.total_cogs],
      ["", "", "Laba Kotor", data.gross_profit],
      ...data.opex.map((r) => ["Beban Operasi", r.code, r.name, r.amount]),
      ["", "", "Total Beban Operasi", data.total_opex],
      ["", "", "Laba (Rugi) Bersih", data.net_income],
    ];
    downloadCsv(`laba-rugi_${period.date_from}_${period.date_to}`,
      ["Kelompok", "Kode", "Akun", "Jumlah (IDR)"], rows);
  };

  if (loading) return <LoadingKpis count={4} />;
  if (error) return <ErrorState message={error} onRetry={load} />;

  return (
    <div data-testid={GL.plPanel} className="space-y-4">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Kpi label="Pendapatan" value={data.total_revenue} tone="text-primary"
          hint={<Growth pct={data.growth?.revenue_pct} />} />
        <Kpi label="Laba Kotor" value={data.gross_profit}
          hint={<span className="text-[11px] text-muted-foreground">Marjin {data.gross_margin_pct}%</span>} />
        <Kpi label="Total Beban" value={data.total_expense} tone="text-amber-700"
          hint={<Growth pct={data.growth?.expense_pct} />} />
        <Kpi label="Laba (Rugi) Bersih" value={data.net_income}
          tone={data.net_income >= 0 ? "text-emerald-700" : "text-rose-700"}
          hint={<span className="text-[11px] text-muted-foreground">Marjin bersih {data.net_margin_pct}%</span>} />
      </div>

      <div className="rounded-xl border bg-card p-4 shadow-[var(--shadow-card)]">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <p className="section-title">Laporan Laba Rugi</p>
            <p className="text-xs text-muted-foreground">Periode {data.period.label} · klik akun untuk drill-down</p>
          </div>
          <Button data-testid={GL.exportBtn} size="sm" variant="outline" onClick={exportCsv}>
            <Download className="mr-1.5 h-3.5 w-3.5" /> Ekspor CSV
          </Button>
        </div>

        <Rows title="Pendapatan" rows={data.revenue} onDrill={onDrill}
          emptyText="Belum ada pendapatan diakui pada periode ini." />
        <div className="flex justify-between border-t px-2 py-1.5 text-sm font-semibold">
          <span>Total Pendapatan</span><span className="tabular-nums">{formatIDR(data.total_revenue)}</span>
        </div>

        <Rows title="Beban Pokok Penjualan (HPP)" rows={data.cogs} onDrill={onDrill}
          emptyText="Belum ada HPP pada periode ini." />
        <div className="flex justify-between border-t px-2 py-1.5 text-sm font-semibold">
          <span>Laba Kotor</span><span className="tabular-nums">{formatIDR(data.gross_profit)}</span>
        </div>

        <Rows title="Beban Operasi" rows={data.opex} onDrill={onDrill}
          emptyText="Belum ada beban operasi pada periode ini." />
        <div className="flex justify-between border-t px-2 py-1.5 text-sm font-semibold">
          <span>Total Beban Operasi</span><span className="tabular-nums">{formatIDR(data.total_opex)}</span>
        </div>

        <div className={`mt-3 flex justify-between rounded-lg p-3 text-sm font-semibold ${data.net_income >= 0 ? "bg-emerald-50 text-emerald-900" : "bg-rose-50 text-rose-900"}`}>
          <span>Laba (Rugi) Bersih</span>
          <span className="tabular-nums">{formatIDR(data.net_income)}</span>
        </div>
        {data.previous ? (
          <p className="mt-2 text-[11px] text-muted-foreground">
            Pembanding {data.previous.label}: pendapatan {formatIDR(data.previous.total_revenue)} ·
            beban {formatIDR(data.previous.total_expense)} · laba {formatIDR(data.previous.net_income)}
          </p>
        ) : null}
      </div>
    </div>
  );
}
