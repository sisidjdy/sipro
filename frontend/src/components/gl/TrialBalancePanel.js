import React, { useCallback, useEffect, useState } from "react";
import { CheckCircle2, AlertTriangle } from "lucide-react";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { LoadingCards, ErrorState } from "@/components/patterns/StateViews";
import { formatIDR } from "@/utils/formatters";
import api from "@/services/apiClient";
import { GL } from "@/constants/testIds";
import RefLabel from "@/components/patterns/RefLabel";

export default function TrialBalancePanel() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try { const r = await api.get("/gl/trial-balance"); setData(r.data.data); }
    catch (e) { setError(e?.response?.data?.detail || "Gagal memuat neraca saldo."); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  if (loading) return <LoadingCards count={5} />;
  if (error) return <ErrorState message={error} onRetry={load} />;
  return (
    <div className="space-y-4">
      <div data-testid={GL.tbBalanced} className={`flex items-center gap-2 rounded-xl border p-3 text-sm ${data.balanced ? "border-emerald-200 bg-emerald-50 text-emerald-800" : "border-rose-200 bg-rose-50 text-rose-800"}`}>
        {data.balanced ? <CheckCircle2 className="h-4 w-4" /> : <AlertTriangle className="h-4 w-4" />}
        {data.balanced ? "Neraca saldo seimbang (debit = kredit)." : "Neraca saldo TIDAK seimbang — periksa jurnal."}
      </div>
      <div className="overflow-hidden rounded-xl border bg-card shadow-[var(--shadow-card)]">
        <Table>
          <TableHeader><TableRow>
            <TableHead>Kode</TableHead><TableHead>Nama Akun</TableHead><TableHead>Tipe</TableHead>
            <TableHead className="text-right">Debit</TableHead><TableHead className="text-right">Kredit</TableHead>
          </TableRow></TableHeader>
          <TableBody>
            {data.rows.map((r) => (
              <TableRow key={r.code} data-testid={GL.tbRow}>
                <TableCell className="font-medium tabular-nums">{r.code}</TableCell>
                <TableCell className="text-sm">{r.name}</TableCell>
                <TableCell className="text-sm"><RefLabel group="account_type" value={r.type} /></TableCell>
                <TableCell className="text-right tabular-nums text-sm">{r.debit ? formatIDR(r.debit) : "-"}</TableCell>
                <TableCell className="text-right tabular-nums text-sm">{r.credit ? formatIDR(r.credit) : "-"}</TableCell>
              </TableRow>
            ))}
            <TableRow className="border-t-2">
              <TableCell colSpan={3} className="font-semibold">Total</TableCell>
              <TableCell className="text-right tabular-nums font-semibold">{formatIDR(data.total_debit)}</TableCell>
              <TableCell className="text-right tabular-nums font-semibold">{formatIDR(data.total_credit)}</TableCell>
            </TableRow>
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
