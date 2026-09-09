import React, { useCallback, useEffect, useState } from "react";
import { Download, Building2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import EmptyState from "@/components/patterns/EmptyState";
import { LoadingCards, ErrorState } from "@/components/patterns/StateViews";
import { formatIDR } from "@/utils/formatters";
import { downloadCsv } from "@/utils/csv";
import api from "@/services/apiClient";
import { GL } from "@/constants/testIds";

/**
 * Laba Rugi per PROYEK (segment reporting). Jurnal tidak menyimpan project_id,
 * jadi backend melacak proyek lewat sumber jurnal (deal/tagihan AP/komisi/RevRec/pajak).
 * Nilai yang tidak dapat dilacak ditampilkan apa adanya sebagai "Tidak teralokasi".
 */
export default function ProjectPLPanel({ period }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const r = await api.get("/gl/reports/projects", {
        params: { date_from: period.date_from, date_to: period.date_to },
      });
      setData(r.data.data);
    } catch (e) { setError(e?.response?.data?.detail || "Gagal memuat laporan per proyek."); }
    finally { setLoading(false); }
  }, [period.date_from, period.date_to]);
  useEffect(() => { load(); }, [load]);

  if (loading) return <LoadingCards count={4} />;
  if (error) return <ErrorState message={error} onRetry={load} />;

  const exportCsv = () => {
    const rows = data.rows.map((r) => [r.project_code || "-", r.project_name, r.revenue, r.cogs,
      r.gross_profit, r.opex, r.net_income, `${r.margin_pct}%`, r.capex_wip]);
    downloadCsv(`laba-rugi-per-proyek_${period.date_from}_${period.date_to}`,
      ["Kode", "Proyek", "Pendapatan", "HPP", "Laba Kotor", "Beban", "Laba Bersih", "Marjin", "Belanja WIP/Material"], rows);
  };

  const t = data.totals;
  return (
    <div data-testid={GL.projPanel} className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="section-title">Laporan Keuangan per Proyek</p>
          <p className="text-xs text-muted-foreground">Periode {data.period.label} · segmentasi dari sumber jurnal</p>
        </div>
        <Button data-testid={GL.exportBtn} size="sm" variant="outline" onClick={exportCsv}
          disabled={!data.rows.length}>
          <Download className="mr-1.5 h-3.5 w-3.5" /> Ekspor CSV
        </Button>
      </div>

      {!data.rows.length ? (
        <EmptyState icon={Building2} title="Belum ada aktivitas keuangan proyek pada periode ini"
          description="Pilih periode lain, atau catat transaksi (pembayaran, tagihan AP, komisi, BAST) agar laporan per proyek terbentuk." />
      ) : (
        <div className="overflow-hidden rounded-xl border bg-card shadow-[var(--shadow-card)]">
          <Table>
            <TableHeader><TableRow>
              <TableHead>Proyek</TableHead>
              <TableHead className="text-right">Pendapatan</TableHead>
              <TableHead className="text-right">HPP</TableHead>
              <TableHead className="text-right">Laba Kotor</TableHead>
              <TableHead className="text-right">Beban</TableHead>
              <TableHead className="text-right">Laba Bersih</TableHead>
              <TableHead className="text-right">Marjin</TableHead>
              <TableHead className="text-right">Belanja WIP/Material</TableHead>
            </TableRow></TableHeader>
            <TableBody>
              {data.rows.map((r) => (
                <TableRow key={r.project_id || "unallocated"} data-testid={GL.projRow}
                  data-project-name={r.project_name}>
                  <TableCell className="text-sm font-medium">
                    {r.project_name}
                    {r.project_code ? <span className="ml-1 text-xs text-muted-foreground">({r.project_code})</span> : null}
                  </TableCell>
                  <TableCell className="text-right tabular-nums text-sm">{formatIDR(r.revenue)}</TableCell>
                  <TableCell className="text-right tabular-nums text-sm">{formatIDR(r.cogs)}</TableCell>
                  <TableCell className="text-right tabular-nums text-sm">{formatIDR(r.gross_profit)}</TableCell>
                  <TableCell className="text-right tabular-nums text-sm">{formatIDR(r.opex)}</TableCell>
                  <TableCell className={`text-right tabular-nums text-sm font-medium ${r.net_income >= 0 ? "text-emerald-700" : "text-rose-700"}`}>
                    {formatIDR(r.net_income)}
                  </TableCell>
                  <TableCell className="text-right tabular-nums text-sm">{r.margin_pct}%</TableCell>
                  <TableCell className="text-right tabular-nums text-sm">{formatIDR(r.capex_wip)}</TableCell>
                </TableRow>
              ))}
              <TableRow className="border-t-2 bg-secondary/60">
                <TableCell className="font-semibold">TOTAL</TableCell>
                <TableCell className="text-right tabular-nums font-semibold">{formatIDR(t.revenue)}</TableCell>
                <TableCell className="text-right tabular-nums font-semibold">{formatIDR(t.cogs)}</TableCell>
                <TableCell className="text-right tabular-nums font-semibold">{formatIDR(t.revenue - t.cogs)}</TableCell>
                <TableCell className="text-right tabular-nums font-semibold">{formatIDR(t.opex)}</TableCell>
                <TableCell className="text-right tabular-nums font-semibold">{formatIDR(t.net_income)}</TableCell>
                <TableCell />
                <TableCell className="text-right tabular-nums font-semibold">{formatIDR(t.capex_wip)}</TableCell>
              </TableRow>
            </TableBody>
          </Table>
        </div>
      )}
      <p className="text-[11px] text-muted-foreground">
        “Belanja WIP/Material” = pengeluaran yang dikapitalisasi ke Aset Proyek dalam Penyelesaian
        atau Persediaan Material (belum menjadi beban sampai pendapatan diakui).
      </p>
    </div>
  );
}
