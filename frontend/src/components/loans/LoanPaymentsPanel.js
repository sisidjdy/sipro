import React, { useCallback, useEffect, useState } from "react";
import { Receipt } from "lucide-react";
import {
  Table, TableHeader, TableBody, TableRow, TableHead, TableCell,
} from "@/components/ui/table";
import EmptyState from "@/components/patterns/EmptyState";
import RefLabel from "@/components/patterns/RefLabel";
import { LoadingCards, ErrorState } from "@/components/patterns/StateViews";
import { formatIDR, formatDateWIB } from "@/utils/formatters";
import api from "@/services/apiClient";
import { LOANS } from "@/constants/testIds";

/** Riwayat semua pembayaran angsuran (bukti pembayaran bisa ditelusuri). */
export default function LoanPaymentsPanel() {
  const [rows, setRows] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const res = await api.get("/corp-financing/payments");
      setRows(res.data.data || []);
      setTotal(res.data.paid_total || 0);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat riwayat pembayaran angsuran.");
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  if (loading) return <LoadingCards count={2} />;
  if (error) return <ErrorState message={error} onRetry={load} />;

  return (
    <div data-testid={LOANS.paymentsPanel} className="space-y-4">
      <p className="text-sm text-muted-foreground">
        Total pembayaran angsuran tercatat:{" "}
        <span className="font-semibold tabular-nums text-foreground">{formatIDR(total)}</span>
      </p>
      {!rows.length ? (
        <EmptyState icon={Receipt} title="Belum ada pembayaran angsuran"
          description="Pembayaran angsuran akan tampil di sini beserta nomor jurnalnya." />
      ) : (
        <div className="overflow-hidden rounded-xl border bg-card shadow-sm">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Tanggal</TableHead>
                <TableHead>Fasilitas</TableHead>
                <TableHead>Angsuran</TableHead>
                <TableHead>Sumber Kas</TableHead>
                <TableHead>Jurnal</TableHead>
                <TableHead className="text-right">Pokok</TableHead>
                <TableHead className="text-right">Bunga</TableHead>
                <TableHead className="text-right">Total</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((r) => (
                <TableRow key={r.id} data-testid={LOANS.paymentRow}>
                  <TableCell className="text-sm">{formatDateWIB(r.paid_at)}</TableCell>
                  <TableCell>
                    <p className="text-sm font-medium">{r.lender}</p>
                    <p className="text-[11px] text-muted-foreground">{r.loan_no}</p>
                  </TableCell>
                  <TableCell>ke-{r.installment_no}</TableCell>
                  <TableCell className="text-sm">
                    <RefLabel group="cash_source" value={r.source} />
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">{r.entry_no}</TableCell>
                  <TableCell className="text-right tabular-nums">{formatIDR(r.principal_part)}</TableCell>
                  <TableCell className="text-right tabular-nums">{formatIDR(r.interest_part)}</TableCell>
                  <TableCell className="text-right font-medium tabular-nums">{formatIDR(r.amount)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  );
}
