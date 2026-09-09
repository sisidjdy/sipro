import React, { useCallback, useEffect, useState } from "react";
import { CheckCircle2, AlertTriangle, Download } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { LoadingCards, ErrorState } from "@/components/patterns/StateViews";
import { formatNumber, formatIDR } from "@/utils/formatters";
import { downloadCsv } from "@/utils/csv";
import api from "@/services/apiClient";
import { GL } from "@/constants/testIds";

const n = (v) => (v ? formatNumber(v) : "-");

/**
 * Neraca Lajur (worksheet) — format klasik siap audit:
 * Saldo Awal | Transaksi (posting otomatis subledger) | Penyesuaian (jurnal manual)
 * | Saldo Akhir | kolom Laba/Rugi | kolom Neraca.
 */
export default function WorksheetPanel({ period, onDrill }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const r = await api.get("/gl/reports/worksheet", {
        params: { date_from: period.date_from, date_to: period.date_to },
      });
      setData(r.data.data);
    } catch (e) { setError(e?.response?.data?.detail || "Gagal memuat neraca lajur."); }
    finally { setLoading(false); }
  }, [period.date_from, period.date_to]);
  useEffect(() => { load(); }, [load]);

  if (loading) return <LoadingCards count={5} />;
  if (error) return <ErrorState message={error} onRetry={load} />;

  const t = data.totals;
  const exportCsv = () => {
    const headers = ["Kode", "Akun", "Saldo Awal D", "Saldo Awal K", "Transaksi D", "Transaksi K",
      "Penyesuaian D", "Penyesuaian K", "Saldo Akhir D", "Saldo Akhir K",
      "Laba Rugi D", "Laba Rugi K", "Neraca D", "Neraca K"];
    const rows = data.rows.map((r) => [r.code, r.name, r.open_debit, r.open_credit,
      r.trx_debit, r.trx_credit, r.adj_debit, r.adj_credit, r.end_debit, r.end_credit,
      r.pl_debit, r.pl_credit, r.bs_debit, r.bs_credit]);
    rows.push(["", "TOTAL", t.open_debit, t.open_credit, t.trx_debit, t.trx_credit,
      t.adj_debit, t.adj_credit, t.end_debit, t.end_credit, t.pl_debit, t.pl_credit,
      t.bs_debit, t.bs_credit]);
    downloadCsv(`neraca-lajur_${period.date_from}_${period.date_to}`, headers, rows);
  };

  return (
    <div data-testid={GL.wsPanel} className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="section-title">Neraca Lajur (Worksheet)</p>
          <p className="text-xs text-muted-foreground">
            Periode {data.period.label} · {data.rows.length} akun bergerak · klik baris untuk drill-down
          </p>
        </div>
        <Button data-testid={GL.exportBtn} size="sm" variant="outline" onClick={exportCsv}>
          <Download className="mr-1.5 h-3.5 w-3.5" /> Ekspor CSV
        </Button>
      </div>

      <div data-testid={GL.wsBalanced} data-balanced={String(data.balanced)}
        className={`flex flex-wrap items-center gap-2 rounded-xl border p-3 text-sm ${data.balanced ? "border-emerald-200 bg-emerald-50 text-emerald-800" : "border-rose-200 bg-rose-50 text-rose-800"}`}>
        {data.balanced ? <CheckCircle2 className="h-4 w-4" /> : <AlertTriangle className="h-4 w-4" />}
        {data.balanced ? "Saldo akhir seimbang (debit = kredit)." : "Saldo akhir tidak seimbang — periksa jurnal."}
        <span className="ml-auto">
          Laba (Rugi) periode: <b className={`tabular-nums ${data.net_income >= 0 ? "text-emerald-800" : "text-rose-800"}`}>{formatIDR(data.net_income)}</b>
        </span>
      </div>

      <div className="overflow-hidden rounded-xl border bg-card shadow-[var(--shadow-card)]">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="whitespace-nowrap">Kode</TableHead>
              <TableHead className="min-w-[190px]">Nama Akun</TableHead>
              <TableHead className="text-right">Awal D</TableHead>
              <TableHead className="text-right">Awal K</TableHead>
              <TableHead className="text-right">Transaksi D</TableHead>
              <TableHead className="text-right">Transaksi K</TableHead>
              <TableHead className="text-right">Penyesuaian D</TableHead>
              <TableHead className="text-right">Penyesuaian K</TableHead>
              <TableHead className="text-right">Akhir D</TableHead>
              <TableHead className="text-right">Akhir K</TableHead>
              <TableHead className="text-right">L/R D</TableHead>
              <TableHead className="text-right">L/R K</TableHead>
              <TableHead className="text-right">Neraca D</TableHead>
              <TableHead className="text-right">Neraca K</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {data.rows.map((r) => (
              <TableRow key={r.code} data-testid={GL.wsRow} data-account-code={r.code}
                className="cursor-pointer hover:bg-accent/40" onClick={() => onDrill(r.code)}>
                <TableCell className="tabular-nums text-xs font-medium">{r.code}</TableCell>
                <TableCell className="text-sm">{r.name}</TableCell>
                <TableCell className="text-right tabular-nums text-xs">{n(r.open_debit)}</TableCell>
                <TableCell className="text-right tabular-nums text-xs">{n(r.open_credit)}</TableCell>
                <TableCell className="text-right tabular-nums text-xs">{n(r.trx_debit)}</TableCell>
                <TableCell className="text-right tabular-nums text-xs">{n(r.trx_credit)}</TableCell>
                <TableCell className="text-right tabular-nums text-xs">{n(r.adj_debit)}</TableCell>
                <TableCell className="text-right tabular-nums text-xs">{n(r.adj_credit)}</TableCell>
                <TableCell className="text-right tabular-nums text-xs font-medium">{n(r.end_debit)}</TableCell>
                <TableCell className="text-right tabular-nums text-xs font-medium">{n(r.end_credit)}</TableCell>
                <TableCell className="text-right tabular-nums text-xs">{n(r.pl_debit)}</TableCell>
                <TableCell className="text-right tabular-nums text-xs">{n(r.pl_credit)}</TableCell>
                <TableCell className="text-right tabular-nums text-xs">{n(r.bs_debit)}</TableCell>
                <TableCell className="text-right tabular-nums text-xs">{n(r.bs_credit)}</TableCell>
              </TableRow>
            ))}
            <TableRow className="border-t-2 bg-secondary/60">
              <TableCell colSpan={2} className="font-semibold">TOTAL</TableCell>
              <TableCell className="text-right tabular-nums text-xs font-semibold">{n(t.open_debit)}</TableCell>
              <TableCell className="text-right tabular-nums text-xs font-semibold">{n(t.open_credit)}</TableCell>
              <TableCell className="text-right tabular-nums text-xs font-semibold">{n(t.trx_debit)}</TableCell>
              <TableCell className="text-right tabular-nums text-xs font-semibold">{n(t.trx_credit)}</TableCell>
              <TableCell className="text-right tabular-nums text-xs font-semibold">{n(t.adj_debit)}</TableCell>
              <TableCell className="text-right tabular-nums text-xs font-semibold">{n(t.adj_credit)}</TableCell>
              <TableCell className="text-right tabular-nums text-xs font-semibold">{n(t.end_debit)}</TableCell>
              <TableCell className="text-right tabular-nums text-xs font-semibold">{n(t.end_credit)}</TableCell>
              <TableCell className="text-right tabular-nums text-xs font-semibold">{n(t.pl_debit)}</TableCell>
              <TableCell className="text-right tabular-nums text-xs font-semibold">{n(t.pl_credit)}</TableCell>
              <TableCell className="text-right tabular-nums text-xs font-semibold">{n(t.bs_debit)}</TableCell>
              <TableCell className="text-right tabular-nums text-xs font-semibold">{n(t.bs_credit)}</TableCell>
            </TableRow>
          </TableBody>
        </Table>
      </div>
      <p className="text-[11px] text-muted-foreground">
        Kolom <b>Transaksi</b> = posting otomatis dari subledger (pembayaran, AP, komisi, RevRec, pajak).
        Kolom <b>Penyesuaian</b> = jurnal manual yang dibuat di menu Jurnal Umum.
      </p>
    </div>
  );
}
