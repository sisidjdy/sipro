import React, { useCallback, useEffect, useState } from "react";
import { Banknote, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Table, TableHeader, TableBody, TableRow, TableHead, TableCell,
} from "@/components/ui/table";
import EmptyState from "@/components/patterns/EmptyState";
import { LoadingCards, ErrorState } from "@/components/patterns/StateViews";
import { formatIDR, formatDateTimeWIB } from "@/utils/formatters";
import api from "@/services/apiClient";

/**
 * Riwayat pembayaran keluar (GET /finance/ap/payments).
 * Temuan audit: koleksi `payments_out` sudah lama DITULIS setiap pembayaran tagihan,
 * tetapi tidak ada endpoint maupun tampilan — jadi bukti pembayaran tak bisa ditelusuri.
 */
export default function PaymentsHistoryPanel({ refreshKey = 0 }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const r = await api.get("/finance/ap/payments", { params: { limit: 50 } });
      setData(r.data);
    } catch (e) { setError(e?.response?.data?.detail || "Gagal memuat riwayat pembayaran."); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load, refreshKey]);

  if (loading) return <LoadingCards count={2} />;
  if (error) return <ErrorState message={error} onRetry={load} />;

  const rows = data?.data || [];

  return (
    <div data-testid="ap-payments-panel" className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm font-semibold">
          Riwayat Pembayaran ({data?.total || 0}) ·{" "}
          <span className="text-muted-foreground">total {formatIDR(data?.summary?.paid_total || 0)}</span>
        </p>
        <Button data-testid="ap-payments-refresh" size="sm" variant="outline" onClick={load}>
          <RefreshCw className="mr-1.5 h-4 w-4" /> Muat ulang
        </Button>
      </div>
      {!rows.length ? (
        <EmptyState icon={Banknote} title="Belum ada pembayaran"
          description="Pembayaran tagihan vendor/subkontraktor akan tercatat di sini." />
      ) : (
        <div className="overflow-hidden rounded-xl border bg-card shadow-[var(--shadow-card)]">
          <Table>
            <TableHeader><TableRow>
              <TableHead>Waktu</TableHead><TableHead>Vendor</TableHead>
              <TableHead className="text-right">Jumlah</TableHead>
              <TableHead>Catatan</TableHead><TableHead>Oleh</TableHead>
            </TableRow></TableHeader>
            <TableBody>
              {rows.map((p) => (
                <TableRow key={p.id} data-testid="ap-payment-row" data-payment-id={p.id}
                  data-payment-vendor={p.vendor}>
                  <TableCell className="whitespace-nowrap text-xs">{formatDateTimeWIB(p.created_at)}</TableCell>
                  <TableCell className="text-sm font-medium">{p.vendor}</TableCell>
                  <TableCell className="text-right tabular-nums font-semibold">{formatIDR(p.amount)}</TableCell>
                  <TableCell className="max-w-[220px] truncate text-xs text-muted-foreground">{p.note || "-"}</TableCell>
                  <TableCell className="text-xs text-muted-foreground">{p.actor}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  );
}
