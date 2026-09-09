import React, { useCallback, useEffect, useState } from "react";
import { Download, ShieldCheck, AlertTriangle, TriangleAlert, HelpCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { LoadingCards, ErrorState } from "@/components/patterns/StateViews";
import { formatIDR } from "@/utils/formatters";
import { downloadCsv } from "@/utils/csv";
import api from "@/services/apiClient";
import { GL } from "@/constants/testIds";

const STATUS = {
  healthy: { label: "Sehat", cls: "border-emerald-200 bg-emerald-50 text-emerald-800", Icon: ShieldCheck },
  watch: { label: "Perlu perhatian", cls: "border-amber-200 bg-amber-50 text-amber-900", Icon: AlertTriangle },
  risk: { label: "Berisiko", cls: "border-rose-200 bg-rose-50 text-rose-800", Icon: TriangleAlert },
  na: { label: "Data belum cukup", cls: "border-slate-200 bg-slate-50 text-slate-700", Icon: HelpCircle },
};

export default function RatiosPanel({ period }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const r = await api.get("/gl/reports/ratios", {
        params: { date_from: period.date_from, date_to: period.date_to },
      });
      setData(r.data.data);
    } catch (e) { setError(e?.response?.data?.detail || "Gagal memuat analisa rasio."); }
    finally { setLoading(false); }
  }, [period.date_from, period.date_to]);
  useEffect(() => { load(); }, [load]);

  if (loading) return <LoadingCards count={4} />;
  if (error) return <ErrorState message={error} onRetry={load} />;

  const exportCsv = () => {
    const rows = data.groups.flatMap((g) => g.items.map((i) => [
      g.label, i.name, i.value === null ? "-" : i.value, i.unit, i.benchmark, STATUS[i.status].label]));
    downloadCsv(`analisa-rasio_${period.date_from}_${period.date_to}`,
      ["Kelompok", "Rasio", "Nilai", "Satuan", "Benchmark", "Status"], rows);
  };

  const inp = data.inputs;
  return (
    <div data-testid={GL.ratioPanel} className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="section-title">Analisa Rasio Keuangan</p>
          <p className="text-xs text-muted-foreground">
            Periode {data.period.label} · {data.counts.healthy} sehat · {data.counts.watch} perhatian ·
            {" "}{data.counts.risk} berisiko · {data.counts.na} belum cukup data
          </p>
        </div>
        <Button data-testid={GL.exportBtn} size="sm" variant="outline" onClick={exportCsv}>
          <Download className="mr-1.5 h-3.5 w-3.5" /> Ekspor CSV
        </Button>
      </div>

      {data.groups.map((g) => (
        <div key={g.key} className="space-y-2">
          <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{g.label}</p>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {g.items.map((i) => {
              const st = STATUS[i.status];
              return (
                <div key={i.name} data-testid={GL.ratioCard} data-ratio={i.name} data-status={i.status}
                  className="rounded-xl border bg-card p-4 shadow-sm">
                  <p className="text-xs font-medium text-muted-foreground">{i.name}</p>
                  <p className="mt-1.5 font-heading text-2xl font-semibold tabular-nums">
                    {i.value === null ? "—" : `${i.value}${i.unit === "%" ? "%" : "×"}`}
                  </p>
                  <span className={`mt-2 inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium ${st.cls}`}>
                    <st.Icon className="h-3 w-3" /> {st.label}
                  </span>
                  <p className="mt-2 text-[11px] text-muted-foreground">
                    Benchmark {i.benchmark}{i.unit === "%" ? "%" : "×"} · {i.hint}
                  </p>
                </div>
              );
            })}
          </div>
        </div>
      ))}

      <div className="rounded-xl border bg-card p-4 shadow-[var(--shadow-card)]">
        <p className="mb-2 font-heading text-sm font-semibold">Dasar perhitungan</p>
        <div className="grid gap-2 text-sm sm:grid-cols-2 lg:grid-cols-3">
          {[["Aset lancar", inp.current_assets], ["Liabilitas jangka pendek", inp.current_liabilities],
          ["Kas & bank", inp.cash], ["Persediaan + WIP", inp.inventory_wip],
          ["Total aset", inp.total_assets], ["Total liabilitas", inp.total_liabilities],
          ["Ekuitas (termasuk laba berjalan)", inp.equity], ["Pendapatan periode", inp.revenue],
          ["Laba bersih periode", inp.net_income]].map(([label, value]) => (
            <div key={label} className="flex justify-between gap-2 border-b py-1 last:border-b-0">
              <span className="text-muted-foreground">{label}</span>
              <span className="tabular-nums">{formatIDR(value)}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
