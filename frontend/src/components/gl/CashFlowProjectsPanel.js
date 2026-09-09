import React, { useCallback, useEffect, useState } from "react";
import { Waypoints, CheckCircle2, AlertTriangle } from "lucide-react";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import EmptyState from "@/components/patterns/EmptyState";
import MetricCard from "@/components/patterns/MetricCard";
import { LoadingCards, ErrorState } from "@/components/patterns/StateViews";
import { formatIDR } from "@/utils/formatters";
import api from "@/services/apiClient";
import { P49 } from "@/constants/testIds";

const money = (n) => (
  <span className={`tabular-nums ${Number(n) < 0 ? "text-rose-700" : ""}`}>{formatIDR(n)}</span>
);

/**
 * Arus kas PER PROYEK (Fase 49C) — menjawab "proyek mana yang menghisap kas".
 *
 * Dua kejujuran yang dijaga di layar: baris **Tidak teralokasi** selalu ditampilkan (bukan
 * disembunyikan supaya tabel terlihat rapi), dan bukti **tie-out** ke arus kas konsolidasi
 * ditulis sebagai angka — kalau ada selisih, laporan ini menyatakan dirinya tidak boleh dipakai.
 */
export default function CashFlowProjectsPanel({ period }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const res = await api.get("/gl/reports/cash-flow-projects", {
        params: { date_from: period?.date_from, date_to: period?.date_to },
      });
      setData(res.data.data || null);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat arus kas per proyek.");
    } finally { setLoading(false); }
  }, [period?.date_from, period?.date_to]);

  useEffect(() => { load(); }, [load]);

  if (loading) return <LoadingCards count={4} />;
  if (error) return <ErrorState message={error} onRetry={load} />;

  const rows = data?.rows || [];
  const un = data?.unassigned;
  const tie = data?.tie_out || {};
  const con = data?.consolidated || {};

  return (
    <div data-testid={P49.cfProjectsPanel} className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="flex items-center gap-1.5 font-heading text-base font-semibold">
            <Waypoints className="h-4 w-4 text-primary" /> Arus Kas per Proyek
          </p>
          <p className="text-xs text-muted-foreground">{data?.detail}</p>
        </div>
        <div data-testid={P49.cfTieOut} data-matches={String(!!tie.matches)}
          className={`max-w-md rounded-xl border p-3 text-xs ${tie.matches
            ? "border-emerald-200 bg-emerald-50 text-emerald-900"
            : "border-rose-200 bg-rose-50 text-rose-900"}`}>
          <p className="flex items-center gap-1.5 font-semibold">
            {tie.matches ? <CheckCircle2 className="h-3.5 w-3.5" /> : <AlertTriangle className="h-3.5 w-3.5" />}
            {tie.matches ? "Tie-out cocok" : "Tie-out SELISIH"}
          </p>
          <p className="mt-1">{tie.detail}</p>
          <p className="mt-1 tabular-nums">
            Σ proyek {formatIDR(tie.sum_projects)} · konsolidasi {formatIDR(tie.consolidated_net_change)} · selisih {formatIDR(tie.diff)}
          </p>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
        <MetricCard label="Kas awal" value={con.opening_cash} format="idr" tone="slate" />
        <MetricCard label="Kas akhir" value={con.closing_cash} format="idr" tone="primary" />
        <MetricCard label="Perubahan kas" value={con.net_change} format="idr"
          tone={(con.net_change || 0) >= 0 ? "emerald" : "rose"} />
        <MetricCard label="Operasi" value={con.operating} format="idr" tone="sky" />
        <MetricCard label="Investasi & pendanaan"
          value={(con.investing || 0) + (con.financing || 0)} format="idr" tone="violet" />
      </div>

      {!rows.length && !un ? (
        <EmptyState icon={Waypoints} title="Belum ada mutasi kas pada periode ini"
          description="Begitu ada penerimaan/pembayaran kas, laporan ini membaginya per proyek beserta bukti tie-out." />
      ) : (
        <div className="overflow-hidden rounded-xl border bg-card shadow-[var(--shadow-card)]">
          <Table>
            <TableHeader><TableRow>
              <TableHead>Proyek</TableHead>
              <TableHead className="text-right">Kas masuk</TableHead>
              <TableHead className="text-right">Kas keluar</TableHead>
              <TableHead className="text-right">Operasi</TableHead>
              <TableHead className="text-right">Investasi</TableHead>
              <TableHead className="text-right">Pendanaan</TableHead>
              <TableHead className="text-right">Perubahan kas</TableHead>
              <TableHead className="text-right">Jurnal</TableHead>
            </TableRow></TableHeader>
            <TableBody>
              {rows.map((r) => (
                <TableRow key={r.project_id} data-testid={P49.cfProjectRow} data-project={r.project_id}>
                  <TableCell className="text-sm font-medium">
                    {r.project_name}
                    {r.project_code ? (
                      <span className="ml-1 text-[11px] text-muted-foreground">({r.project_code})</span>
                    ) : null}
                  </TableCell>
                  <TableCell className="text-right text-sm">{money(r.inflow)}</TableCell>
                  <TableCell className="text-right text-sm">{money(r.outflow)}</TableCell>
                  <TableCell className="text-right text-sm">{money(r.operating)}</TableCell>
                  <TableCell className="text-right text-sm">{money(r.investing)}</TableCell>
                  <TableCell className="text-right text-sm">{money(r.financing)}</TableCell>
                  <TableCell className="text-right text-sm font-semibold">{money(r.net_change)}</TableCell>
                  <TableCell className="text-right tabular-nums text-sm text-muted-foreground">{r.entries}</TableCell>
                </TableRow>
              ))}
              {un ? (
                <TableRow data-testid={P49.cfUnassignedRow} className="bg-amber-50/60">
                  <TableCell className="text-sm font-medium text-amber-900">
                    {un.project_name}
                    <span className="ml-1 text-[11px] font-normal text-amber-800">
                      (kas nyata yang belum bisa ditelusuri ke satu proyek)
                    </span>
                  </TableCell>
                  <TableCell className="text-right text-sm">{money(un.inflow)}</TableCell>
                  <TableCell className="text-right text-sm">{money(un.outflow)}</TableCell>
                  <TableCell className="text-right text-sm">{money(un.operating)}</TableCell>
                  <TableCell className="text-right text-sm">{money(un.investing)}</TableCell>
                  <TableCell className="text-right text-sm">{money(un.financing)}</TableCell>
                  <TableCell className="text-right text-sm font-semibold">{money(un.net_change)}</TableCell>
                  <TableCell className="text-right tabular-nums text-sm text-muted-foreground">{un.entries}</TableCell>
                </TableRow>
              ) : null}
              <TableRow className="bg-secondary/60">
                <TableCell className="text-sm font-semibold">Σ semua baris</TableCell>
                <TableCell colSpan={5} />
                <TableCell className="text-right text-sm font-semibold">{money(tie.sum_projects)}</TableCell>
                <TableCell />
              </TableRow>
            </TableBody>
          </Table>
        </div>
      )}

      <p className="text-[11px] text-muted-foreground">
        Akun kas yang dibaca: {(data?.cash_accounts || []).join(", ") || "-"}. Proyek disimpulkan
        dari dokumen sumber jurnal; yang tidak bisa dibuktikan tetap tampil sebagai
        “tidak teralokasi”, bukan dibagi rata.
      </p>
    </div>
  );
}
