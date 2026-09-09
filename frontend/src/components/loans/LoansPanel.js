import React, { useCallback, useEffect, useState } from "react";
import { Banknote, Plus, AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Table, TableHeader, TableBody, TableRow, TableHead, TableCell,
} from "@/components/ui/table";
import MetricCard from "@/components/patterns/MetricCard";
import StatusPill from "@/components/patterns/StatusPill";
import EmptyState from "@/components/patterns/EmptyState";
import RefLabel from "@/components/patterns/RefLabel";
import ReferenceSelect from "@/components/patterns/ReferenceSelect";
import { LoadingCards, ErrorState } from "@/components/patterns/StateViews";
import AddLoanDialog from "@/components/loans/AddLoanDialog";
import LoanDetailSheet from "@/components/loans/LoanDetailSheet";
import { formatIDR, formatDateWIB } from "@/utils/formatters";
import api from "@/services/apiClient";
import { LOANS } from "@/constants/testIds";

/** Daftar fasilitas pembiayaan + KPI sisa pokok / jatuh tempo / tunggakan. */
export default function LoansPanel() {
  const [rows, setRows] = useState([]);
  const [summary, setSummary] = useState(null);
  const [status, setStatus] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [openAdd, setOpenAdd] = useState(false);
  const [detailId, setDetailId] = useState(null);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const [list, sum] = await Promise.all([
        api.get("/corp-financing/loans", { params: status ? { status } : {} }),
        api.get("/corp-financing/summary"),
      ]);
      setRows(list.data.data || []);
      setSummary(sum.data.data || null);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat fasilitas pembiayaan.");
    } finally { setLoading(false); }
  }, [status]);

  useEffect(() => { load(); }, [load]);

  if (loading) return <LoadingCards count={4} />;
  if (error) return <ErrorState message={error} onRetry={load} />;

  return (
    <div data-testid={LOANS.panel} className="space-y-5">
      <div data-testid={LOANS.summary} className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <MetricCard label="Sisa Pokok Utang" value={summary?.outstanding_principal || 0}
          tone="rose" format="idr" hint={`${summary?.active_count || 0} fasilitas aktif`} />
        <MetricCard label="Angsuran Bulan Ini" value={summary?.due_this_month || 0}
          tone="amber" format="idr" hint={`Periode ${summary?.current_period || "-"}`} />
        <MetricCard label="Angsuran Terlambat" value={summary?.overdue_amount || 0}
          tone="rose" format="idr" hint={`${summary?.overdue_count || 0} angsuran lewat jatuh tempo`} />
        <MetricCard label="Bunga Dibayar" value={summary?.interest_paid_total || 0}
          tone="indigo" format="idr" hint="Akun 6-1600" />
      </div>

      {summary?.overdue_count ? (
        <div className="flex items-start gap-2 rounded-xl border border-rose-200 bg-rose-50 p-3">
          <AlertTriangle className="mt-0.5 h-4 w-4 text-rose-600" />
          <p className="text-sm text-rose-800">
            {summary.overdue_count} angsuran sudah lewat jatuh tempo
            ({formatIDR(summary.overdue_amount)}). Segera bayar agar tidak menimbulkan denda bank.
          </p>
        </div>
      ) : null}

      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="w-56 space-y-1">
          <span className="text-xs text-muted-foreground">Status fasilitas</span>
          <ReferenceSelect group="loan_status" value={status} onChange={setStatus}
            allowEmpty emptyLabel="Semua status" testId={LOANS.statusFilter} />
        </div>
        <Button data-testid={LOANS.addBtn} onClick={() => setOpenAdd(true)}>
          <Plus className="mr-1.5 h-4 w-4" /> Tambah Fasilitas
        </Button>
      </div>

      {!rows.length ? (
        <div data-testid={LOANS.empty}>
          <EmptyState icon={Banknote} title="Belum ada fasilitas pembiayaan"
            description="Catat kredit investasi, modal kerja, atau leasing agar jadwal angsuran & bunganya terbukukan otomatis."
            actionLabel="Tambah Fasilitas" onAction={() => setOpenAdd(true)} />
        </div>
      ) : (
        <div data-testid={LOANS.table} className="overflow-hidden rounded-xl border bg-card shadow-sm">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>No.</TableHead>
                <TableHead>Pemberi Pinjaman</TableHead>
                <TableHead>Jenis</TableHead>
                <TableHead className="text-right">Pokok</TableHead>
                <TableHead className="text-right">Sisa Pokok</TableHead>
                <TableHead>Bunga / Tenor</TableHead>
                <TableHead>Angsuran Berikut</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="col-actions-head text-right">Aksi</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((r) => (
                <TableRow key={r.id} data-testid={LOANS.row} data-status={r.status}>
                  <TableCell className="font-medium">{r.no}</TableCell>
                  <TableCell>
                    <p className="text-sm">{r.lender}</p>
                    <p className="text-[11px] text-muted-foreground">
                      <RefLabel group="lender_type" value={r.lender_type} />
                    </p>
                  </TableCell>
                  <TableCell className="text-sm">
                    <RefLabel group="loan_type" value={r.loan_type} />
                    <p className="text-[11px] text-muted-foreground">
                      <RefLabel group="amortization_method" value={r.amortization_method} />
                    </p>
                  </TableCell>
                  <TableCell className="text-right tabular-nums">{formatIDR(r.principal)}</TableCell>
                  <TableCell className="text-right font-semibold tabular-nums">
                    {formatIDR(r.outstanding_principal)}
                  </TableCell>
                  <TableCell className="text-sm">
                    {r.interest_rate_pct}%/th · {r.tenor_months} bln
                    <p className="text-[11px] text-muted-foreground">
                      {r.metrics?.installments_paid || 0}/{r.metrics?.installments_total || 0} angsuran lunas
                    </p>
                  </TableCell>
                  <TableCell className="text-sm">
                    {r.metrics?.next_due_date ? (
                      <>
                        <p className="tabular-nums">{formatIDR(r.metrics.next_due_amount)}</p>
                        <p className={`text-[11px] ${r.metrics.overdue_count ? "text-rose-600" : "text-muted-foreground"}`}>
                          jatuh tempo {formatDateWIB(r.metrics.next_due_date)}
                        </p>
                      </>
                    ) : "—"}
                  </TableCell>
                  <TableCell><StatusPill status={r.status} group="loan_status" /></TableCell>
                  <TableCell className="col-actions text-right">
                    <Button size="sm" variant="ghost" data-testid={LOANS.detailBtn}
                      onClick={() => setDetailId(r.id)}>
                      {r.status === "draft" ? "Cairkan / Detail" : "Detail & Angsuran"}
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      <AddLoanDialog open={openAdd} onOpenChange={setOpenAdd} onSaved={load} />
      <LoanDetailSheet loanId={detailId} onClose={() => setDetailId(null)} onChanged={load} />
    </div>
  );
}
