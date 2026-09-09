import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { FileDown, FileText } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  Table, TableHeader, TableBody, TableRow, TableHead, TableCell,
} from "@/components/ui/table";
import MetricCard from "@/components/patterns/MetricCard";
import EmptyState from "@/components/patterns/EmptyState";
import { LoadingCards, ErrorState } from "@/components/patterns/StateViews";
import { formatIDR, formatDateWIB } from "@/utils/formatters";
import api from "@/services/apiClient";
import { FINANCE } from "@/constants/testIds";

const AGING = [["current", "Lancar"], ["1-30", "1-30 hari"], ["31-60", "31-60 hari"],
  ["61-90", "61-90 hari"], [">90", "> 90 hari"]];

const REPORTS = {
  "ar-aging": { label: "Aging Piutang (AR)", columns: ["Kategori Umur", "Nilai"] },
  "ap-aging": { label: "Aging Utang (AP)", columns: ["Kategori Umur", "Nilai"] },
  "revenue": { label: "Pengakuan Pendapatan (RevRec)", columns: ["Unit", "Pendapatan", "COGS", "Margin", "Tgl BAST"] },
  "commissions": { label: "Komisi Sales", columns: ["Unit", "Sales", "Skema", "Komisi", "Status"] },
  "collections": { label: "Worklist Penagihan", columns: ["Unit", "Pembeli", "Jatuh Tempo", "Telat (hari)", "Tunggakan", "Denda"] },
  "cashflow": { label: "Proyeksi Arus Kas", columns: ["Periode", "Kas Masuk", "Kas Keluar", "Net", "Kumulatif"] },
};

async function buildRows(type) {
  if (type === "ar-aging") {
    const r = await api.get("/finance/ar/aging");
    const b = r.data.data?.buckets || {};
    return AGING.map(([k, l]) => [l, formatIDR(b[k] || 0)]);
  }
  if (type === "ap-aging") {
    const r = await api.get("/finance/ap/aging");
    const b = r.data.data?.buckets || {};
    return AGING.map(([k, l]) => [l, formatIDR(b[k] || 0)]);
  }
  if (type === "revenue") {
    const r = await api.get("/finance/reports/revenue");
    return (r.data.data?.rows || []).map((x) => [x.unit_code || "-", formatIDR(x.revenue),
      formatIDR(x.cogs), formatIDR(x.margin), formatDateWIB(x.recognized_at)]);
  }
  if (type === "commissions") {
    const r = await api.get("/finance/commissions");
    return (r.data.data || []).map((x) => [x.unit_code || "-", x.assigned_to || "-",
      x.scheme_name || "-", formatIDR(x.amount), x.status]);
  }
  if (type === "collections") {
    const r = await api.get("/finance/collections");
    return (r.data.data?.rows || []).map((x) => [x.unit_code || "-", x.lead_name || "-",
      formatDateWIB(x.next_due), String(x.days_overdue), formatIDR(x.overdue_amount), formatIDR(x.denda_estimate)]);
  }
  if (type === "cashflow") {
    const r = await api.get("/finance/cashflow", { params: { bucket: "month", horizon: 6 } });
    return (r.data.data?.periods || []).map((p) => [p.label, formatIDR(p.inflow),
      formatIDR(p.outflow), formatIDR(p.net), formatIDR(p.cumulative)]);
  }
  return [];
}

export default function ReportsPanel() {
  const [type, setType] = useState("ar-aging");
  const [summary, setSummary] = useState(null);
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [exporting, setExporting] = useState(false);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const [s, rws] = await Promise.all([api.get("/finance/summary"), buildRows(type)]);
      setSummary(s.data.data);
      setRows(rws);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat laporan.");
    } finally { setLoading(false); }
  }, [type]);

  useEffect(() => { load(); }, [load]);

  const meta = REPORTS[type];

  const exportCsv = () => {
    const esc = (s) => `"${String(s).replace(/"/g, '""')}"`;
    const lines = [meta.columns.map(esc).join(",")].concat(rows.map((r) => r.map(esc).join(",")));
    const blob = new Blob(["\ufeff" + lines.join("\n")], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = `laporan-${type}.csv`;
    document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
    toast.success("CSV diunduh.");
  };

  const exportPdf = async () => {
    setExporting(true);
    try {
      const res = await api.get(`/finance/reports/${type}/pdf`, { responseType: "blob" });
      const url = URL.createObjectURL(new Blob([res.data], { type: "application/pdf" }));
      const a = document.createElement("a");
      a.href = url; a.download = `laporan-${type}.pdf`;
      document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
      toast.success("PDF diunduh.");
    } catch (e) { toast.error("Gagal mengekspor PDF."); }
    finally { setExporting(false); }
  };

  return (
    <div data-testid={FINANCE.reportsPanel} className="space-y-5">
      {summary ? (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <MetricCard label="AR Outstanding" value={summary.ar_outstanding} tone="primary" format="idr" hint={`Belum tertagih ${summary.ar_outstanding_pct ?? 0}% dari total tagihan`} />
          <MetricCard label="AP Outstanding" value={summary.ap_outstanding} tone="amber" format="idr" />
          <MetricCard label="Kewajiban Kontrak" value={summary.contract_liability} tone="indigo" format="idr" />
          <MetricCard label="Pendapatan Diakui" value={summary.revenue_recognized} tone="emerald" format="idr" />
        </div>
      ) : null}

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="w-full sm:w-72">
          <Select value={type} onValueChange={setType}>
            <SelectTrigger data-testid={FINANCE.reportSelect}><SelectValue /></SelectTrigger>
            <SelectContent>
              {Object.entries(REPORTS).map(([k, v]) => <SelectItem key={k} value={k}>{v.label}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" data-testid={FINANCE.exportCsvBtn} onClick={exportCsv} disabled={!rows.length}>
            <FileDown className="mr-1.5 h-4 w-4" /> CSV
          </Button>
          <Button data-testid={FINANCE.exportPdfBtn} onClick={exportPdf} disabled={exporting}>
            <FileText className="mr-1.5 h-4 w-4" /> {exporting ? "Menyiapkan\u2026" : "PDF"}
          </Button>
        </div>
      </div>

      {loading ? (
        <LoadingCards count={3} />
      ) : error ? (
        <ErrorState message={error} onRetry={load} />
      ) : !rows.length ? (
        <EmptyState icon={FileText} title="Belum ada data" description={`Laporan "${meta.label}" belum memiliki data.`} />
      ) : (
        <div className="overflow-hidden rounded-xl border bg-card shadow-sm">
          <Table>
            <TableHeader>
              <TableRow>
                {meta.columns.map((c, i) => (
                  <TableHead key={c} className={i === 0 ? "" : "text-right"}>{c}</TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((r, ri) => (
                <TableRow key={ri} data-testid={FINANCE.reportRow}>
                  {r.map((cell, ci) => (
                    <TableCell key={ci} className={ci === 0 ? "font-medium" : "text-right tabular-nums"}>{cell}</TableCell>
                  ))}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  );
}
