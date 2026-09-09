import React, { useCallback, useEffect, useState } from "react";
import { CheckCircle2, AlertTriangle, Download } from "lucide-react";
import { Button } from "@/components/ui/button";
import { LoadingCards, ErrorState } from "@/components/patterns/StateViews";
import { formatIDR, formatDateWIB } from "@/utils/formatters";
import { downloadCsv } from "@/utils/csv";
import api from "@/services/apiClient";
import { GL } from "@/constants/testIds";

function Line({ row, onDrill }) {
  return (
    <button type="button" data-testid={GL.bsRow} data-account-code={row.code}
      aria-label={`Rincian akun ${row.code} ${row.name}`} onClick={() => onDrill(row.code)}
      className="flex w-full items-center justify-between gap-3 rounded-lg px-2 py-1.5 text-left text-sm hover:bg-accent/50">
      <span><span className="tabular-nums text-muted-foreground">{row.code}</span> {row.name}</span>
      <span className="tabular-nums">{formatIDR(row.balance)}</span>
    </button>
  );
}

function Total({ label, value, strong }) {
  return (
    <div className={`flex justify-between border-t px-2 py-1.5 text-sm ${strong ? "font-semibold" : ""}`}>
      <span>{label}</span><span className="tabular-nums">{formatIDR(value)}</span>
    </div>
  );
}

export default function BalanceSheetPanel({ period, onDrill }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const r = await api.get("/gl/reports/balance-sheet", { params: { as_of: period.date_to } });
      setData(r.data.data);
    } catch (e) { setError(e?.response?.data?.detail || "Gagal memuat neraca."); }
    finally { setLoading(false); }
  }, [period.date_to]);
  useEffect(() => { load(); }, [load]);

  if (loading) return <LoadingCards count={4} />;
  if (error) return <ErrorState message={error} onRetry={load} />;

  const cur = (arr, want) => arr.filter((r) => !!r.current === want);
  const exportCsv = () => {
    const rows = [
      ...data.assets.map((r) => [r.current ? "Aset Lancar" : "Aset Tidak Lancar", r.code, r.name, r.balance]),
      ["", "", "Total Aset", data.total_assets],
      ...data.liabilities.map((r) => [r.current ? "Liabilitas Jangka Pendek" : "Liabilitas Jangka Panjang", r.code, r.name, r.balance]),
      ["", "", "Total Liabilitas", data.total_liabilities],
      ...data.equity.map((r) => ["Ekuitas", r.code, r.name, r.balance]),
      ["", "", "Laba (Rugi) Berjalan", data.net_income],
      ["", "", "Total Liabilitas + Ekuitas", data.total_liab_equity],
    ];
    downloadCsv(`neraca_${data.as_of}`, ["Kelompok", "Kode", "Akun", "Saldo (IDR)"], rows);
  };

  return (
    <div data-testid={GL.bsPanel} className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="section-title">Neraca</p>
          <p className="text-xs text-muted-foreground">Posisi per {formatDateWIB(data.as_of)} · klik akun untuk drill-down</p>
        </div>
        <Button data-testid={GL.exportBtn} size="sm" variant="outline" onClick={exportCsv}>
          <Download className="mr-1.5 h-3.5 w-3.5" /> Ekspor CSV
        </Button>
      </div>

      <div data-testid={GL.bsBalanced} data-balanced={String(data.balanced)}
        className={`flex items-center gap-2 rounded-xl border p-3 text-sm ${data.balanced ? "border-emerald-200 bg-emerald-50 text-emerald-800" : "border-rose-200 bg-rose-50 text-rose-800"}`}>
        {data.balanced ? <CheckCircle2 className="h-4 w-4" /> : <AlertTriangle className="h-4 w-4" />}
        {data.balanced
          ? `Neraca seimbang — Aset ${formatIDR(data.total_assets)} = Liabilitas + Ekuitas ${formatIDR(data.total_liab_equity)}.`
          : "Neraca TIDAK seimbang — periksa jurnal periode ini."}
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="rounded-xl border bg-card p-4 shadow-[var(--shadow-card)]">
          <p className="font-heading text-sm font-semibold">Aset</p>
          <p className="mb-1 mt-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Aset Lancar</p>
          {cur(data.assets, true).length ? cur(data.assets, true).map((r) => <Line key={r.code} row={r} onDrill={onDrill} />)
            : <p className="px-2 py-1.5 text-sm text-muted-foreground">-</p>}
          <Total label="Jumlah Aset Lancar" value={data.current_assets} />
          <p className="mb-1 mt-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Aset Tidak Lancar</p>
          {cur(data.assets, false).length ? cur(data.assets, false).map((r) => <Line key={r.code} row={r} onDrill={onDrill} />)
            : <p className="px-2 py-1.5 text-sm text-muted-foreground">-</p>}
          <Total label="Jumlah Aset Tidak Lancar" value={data.noncurrent_assets} />
          <Total label="TOTAL ASET" value={data.total_assets} strong />
        </div>

        <div className="rounded-xl border bg-card p-4 shadow-[var(--shadow-card)]">
          <p className="font-heading text-sm font-semibold">Liabilitas &amp; Ekuitas</p>
          <p className="mb-1 mt-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Liabilitas Jangka Pendek</p>
          {cur(data.liabilities, true).length ? cur(data.liabilities, true).map((r) => <Line key={r.code} row={r} onDrill={onDrill} />)
            : <p className="px-2 py-1.5 text-sm text-muted-foreground">-</p>}
          <Total label="Jumlah Liabilitas Jangka Pendek" value={data.current_liabilities} />
          <p className="mb-1 mt-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Liabilitas Jangka Panjang</p>
          {cur(data.liabilities, false).length ? cur(data.liabilities, false).map((r) => <Line key={r.code} row={r} onDrill={onDrill} />)
            : <p className="px-2 py-1.5 text-sm text-muted-foreground">-</p>}
          <Total label="Jumlah Liabilitas Jangka Panjang" value={data.noncurrent_liabilities} />
          <Total label="Total Liabilitas" value={data.total_liabilities} strong />
          <p className="mb-1 mt-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Ekuitas</p>
          {data.equity.map((r) => <Line key={r.code} row={r} onDrill={onDrill} />)}
          <div className="flex justify-between px-2 py-1.5 text-sm">
            <span>Laba (Rugi) Berjalan</span>
            <span className={`tabular-nums ${data.net_income >= 0 ? "text-emerald-700" : "text-rose-700"}`}>
              {formatIDR(data.net_income)}
            </span>
          </div>
          <Total label="TOTAL LIABILITAS + EKUITAS" value={data.total_liab_equity} strong />
        </div>
      </div>
    </div>
  );
}
