import React, { useCallback, useEffect, useState } from "react";
import { CheckCircle2, AlertTriangle, Download, ArrowDownCircle, ArrowUpCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { LoadingKpis, ErrorState } from "@/components/patterns/StateViews";
import { formatIDR } from "@/utils/formatters";
import { downloadCsv } from "@/utils/csv";
import api from "@/services/apiClient";
import { GL } from "@/constants/testIds";

const SECTIONS = [
  ["operating", "Arus Kas dari Aktivitas Operasi", "Penerimaan pembeli, pembayaran vendor/komisi/pajak, belanja material & konstruksi."],
  ["investing", "Arus Kas dari Aktivitas Investasi", "Perolehan/pelepasan aset tetap & investasi jangka panjang."],
  ["financing", "Arus Kas dari Aktivitas Pendanaan", "Setoran modal, penarikan/pembayaran pinjaman bank & leasing."],
];

function Section({ id, title, hint, section, onDrill }) {
  return (
    <div className="rounded-xl border bg-card p-4 shadow-[var(--shadow-card)]">
      <p className="font-heading text-sm font-semibold">{title}</p>
      <p className="mb-2 text-[11px] text-muted-foreground">{hint}</p>
      {section.lines.length ? section.lines.map((r) => (
        <button key={r.code} type="button" data-testid={GL.cfRow} data-account-code={r.code}
          data-section={id} aria-label={`Rincian arus kas akun ${r.code}`}
          onClick={() => onDrill(r.code)}
          className="flex w-full items-center justify-between gap-3 rounded-lg px-2 py-1.5 text-left text-sm hover:bg-accent/50">
          <span className="inline-flex items-center gap-1.5">
            {r.amount >= 0 ? <ArrowDownCircle className="h-3.5 w-3.5 text-emerald-600" />
              : <ArrowUpCircle className="h-3.5 w-3.5 text-rose-600" />}
            <span className="tabular-nums text-muted-foreground">{r.code}</span> {r.name}
          </span>
          <span className={`tabular-nums ${r.amount >= 0 ? "text-emerald-700" : "text-rose-700"}`}>
            {formatIDR(r.amount)}
          </span>
        </button>
      )) : <p className="px-2 py-1.5 text-sm text-muted-foreground">Tidak ada arus kas pada kelompok ini.</p>}
      <div className="mt-1 flex justify-between border-t px-2 py-1.5 text-sm font-semibold">
        <span>Arus kas bersih</span>
        <span className="tabular-nums">{formatIDR(section.total)}</span>
      </div>
    </div>
  );
}

export default function CashFlowStatementPanel({ period, onDrill }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const r = await api.get("/gl/reports/cash-flow", {
        params: { date_from: period.date_from, date_to: period.date_to },
      });
      setData(r.data.data);
    } catch (e) { setError(e?.response?.data?.detail || "Gagal memuat laporan arus kas."); }
    finally { setLoading(false); }
  }, [period.date_from, period.date_to]);
  useEffect(() => { load(); }, [load]);

  if (loading) return <LoadingKpis count={5} />;
  if (error) return <ErrorState message={error} onRetry={load} />;

  const exportCsv = () => {
    const rows = [["", "", "Kas & bank awal periode", data.opening_cash]];
    SECTIONS.forEach(([key, title]) => {
      data[key].lines.forEach((r) => rows.push([title, r.code, r.name, r.amount]));
      rows.push([title, "", "Subtotal", data[key].total]);
    });
    rows.push(["", "", "Kenaikan (penurunan) kas", data.net_change]);
    rows.push(["", "", "Kas & bank akhir periode", data.closing_cash]);
    downloadCsv(`arus-kas_${period.date_from}_${period.date_to}`,
      ["Aktivitas", "Kode", "Keterangan", "Jumlah (IDR)"], rows);
  };

  return (
    <div data-testid={GL.cfPanel} className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="section-title">Laporan Arus Kas (metode langsung)</p>
          <p className="text-xs text-muted-foreground">
            Periode {data.period.label} · sumber: mutasi akun kas &amp; bank ({data.cash_accounts.join(", ")})
          </p>
        </div>
        <Button data-testid={GL.exportBtn} size="sm" variant="outline" onClick={exportCsv}>
          <Download className="mr-1.5 h-3.5 w-3.5" /> Ekspor CSV
        </Button>
      </div>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        {[["Kas awal", data.opening_cash, "text-foreground"],
        ["Operasi", data.operating.total, data.operating.total >= 0 ? "text-emerald-700" : "text-rose-700"],
        ["Investasi", data.investing.total, data.investing.total >= 0 ? "text-emerald-700" : "text-rose-700"],
        ["Pendanaan", data.financing.total, data.financing.total >= 0 ? "text-emerald-700" : "text-rose-700"],
        ["Kas akhir", data.closing_cash, "text-primary"]].map(([label, value, tone]) => (
          <div key={label} data-testid={GL.plMetric} data-metric={label}
            className="rounded-xl border bg-card p-4 shadow-sm">
            <p className="text-xs font-medium text-muted-foreground">{label}</p>
            <p className={`mt-1.5 font-heading text-lg font-semibold tabular-nums ${tone}`}>{formatIDR(value)}</p>
          </div>
        ))}
      </div>

      <div data-testid={GL.cfReconciled} data-reconciled={String(data.reconciled)}
        className={`flex items-center gap-2 rounded-xl border p-3 text-sm ${data.reconciled ? "border-emerald-200 bg-emerald-50 text-emerald-800" : "border-rose-200 bg-rose-50 text-rose-800"}`}>
        {data.reconciled ? <CheckCircle2 className="h-4 w-4" /> : <AlertTriangle className="h-4 w-4" />}
        {data.reconciled
          ? `Rekonsiliasi cocok — kas awal ${formatIDR(data.opening_cash)} + perubahan ${formatIDR(data.net_change)} = kas akhir ${formatIDR(data.closing_cash)}.`
          : "Rekonsiliasi tidak cocok — ada mutasi kas yang belum terklasifikasi."}
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        {SECTIONS.map(([key, title, hint]) => (
          <Section key={key} id={key} title={title} hint={hint} section={data[key]} onDrill={onDrill} />
        ))}
      </div>
    </div>
  );
}
