import React, { useCallback, useEffect, useState } from "react";
import { CheckCircle2, AlertTriangle } from "lucide-react";
import { LoadingCards, ErrorState } from "@/components/patterns/StateViews";
import { formatIDR } from "@/utils/formatters";
import api from "@/services/apiClient";
import { GL } from "@/constants/testIds";

function LineRow({ label, code, value, bold }) {
  return (
    <div className={`flex justify-between gap-4 py-1.5 text-sm ${bold ? "border-t font-semibold" : ""}`}>
      <span>{code ? <span className="tabular-nums text-muted-foreground">{code} </span> : null}{label}</span>
      <span className="tabular-nums">{formatIDR(value)}</span>
    </div>
  );
}

function Section({ title, children }) {
  return (
    <div className="rounded-xl border bg-card p-4 shadow-[var(--shadow-card)]">
      <p className="mb-1 text-sm font-semibold">{title}</p>
      {children}
    </div>
  );
}

export default function StatementsPanel() {
  const [inc, setInc] = useState(null);
  const [bs, setBs] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const [ri, rb] = await Promise.all([api.get("/gl/income-statement"), api.get("/gl/balance-sheet")]);
      setInc(ri.data.data); setBs(rb.data.data);
    } catch (e) { setError(e?.response?.data?.detail || "Gagal memuat laporan keuangan."); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  if (loading) return <LoadingCards count={4} />;
  if (error) return <ErrorState message={error} onRetry={load} />;

  return (
    <div className="grid gap-5 lg:grid-cols-2">
      <div data-testid={GL.incomeStatement} className="space-y-4">
        <Section title="Laporan Laba Rugi">
          <p className="mb-1 mt-2 text-xs font-medium uppercase text-muted-foreground">Pendapatan</p>
          {inc.revenue.length ? inc.revenue.map((r) => <LineRow key={r.code} code={r.code} label={r.name} value={r.balance} />) : <p className="py-1 text-sm text-muted-foreground">Belum ada pendapatan.</p>}
          <LineRow label="Total Pendapatan" value={inc.total_revenue} bold />
          <p className="mb-1 mt-3 text-xs font-medium uppercase text-muted-foreground">Beban</p>
          {inc.expenses.length ? inc.expenses.map((r) => <LineRow key={r.code} code={r.code} label={r.name} value={r.balance} />) : <p className="py-1 text-sm text-muted-foreground">Belum ada beban.</p>}
          <LineRow label="Total Beban" value={inc.total_expense} bold />
          <div className={`mt-3 flex justify-between rounded-lg p-3 text-sm font-semibold ${inc.net_income >= 0 ? "bg-emerald-50 text-emerald-800" : "bg-rose-50 text-rose-800"}`}>
            <span>Laba (Rugi) Bersih</span><span className="tabular-nums">{formatIDR(inc.net_income)}</span>
          </div>
        </Section>
      </div>
      <div data-testid={GL.balanceSheet} className="space-y-4">
        <Section title="Neraca">
          <p className="mb-1 mt-2 text-xs font-medium uppercase text-muted-foreground">Aset</p>
          {bs.assets.map((r) => <LineRow key={r.code} code={r.code} label={r.name} value={r.balance} />)}
          <LineRow label="Total Aset" value={bs.total_assets} bold />
          <p className="mb-1 mt-3 text-xs font-medium uppercase text-muted-foreground">Liabilitas</p>
          {bs.liabilities.length ? bs.liabilities.map((r) => <LineRow key={r.code} code={r.code} label={r.name} value={r.balance} />) : <p className="py-1 text-sm text-muted-foreground">-</p>}
          <LineRow label="Total Liabilitas" value={bs.total_liabilities} bold />
          <p className="mb-1 mt-3 text-xs font-medium uppercase text-muted-foreground">Ekuitas</p>
          {bs.equity.map((r) => <LineRow key={r.code} code={r.code} label={r.name} value={r.balance} />)}
          <LineRow label="Laba Berjalan" value={bs.net_income} />
          <LineRow label="Total Liabilitas + Ekuitas" value={bs.total_liab_equity} bold />
          <div data-testid="balance-sheet-balanced" className={`mt-3 flex items-center gap-2 rounded-lg p-3 text-sm ${bs.balanced ? "bg-emerald-50 text-emerald-800" : "bg-rose-50 text-rose-800"}`}>
            {bs.balanced ? <CheckCircle2 className="h-4 w-4" /> : <AlertTriangle className="h-4 w-4" />}
            {bs.balanced ? "Neraca seimbang (Aset = Liabilitas + Ekuitas)." : "Neraca tidak seimbang."}
          </div>
        </Section>
      </div>
    </div>
  );
}
